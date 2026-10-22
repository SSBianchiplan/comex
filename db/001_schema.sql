-- =====================================================================
-- GPlanSiS|COMEX — Logística de exportação de painéis elétricos
-- PostgreSQL 16 · schema comex
-- Invariantes INV-CMX-001..023 (ver LEIAME.md). Cada uma nasce no DDL.
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE SCHEMA IF NOT EXISTS comex;
SET search_path = comex, public;

-- INV-CMX-003: SSCC GS1 de 18 dígitos com dígito verificador módulo 10
CREATE OR REPLACE FUNCTION fn_sscc_valido(c text) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE s int := 0; i int;
BEGIN
  IF c !~ '^[0-9]{18}$' THEN RETURN false; END IF;
  FOR i IN 1..17 LOOP s := s + substr(c, 18 - i, 1)::int * CASE WHEN i % 2 = 1 THEN 3 ELSE 1 END; END LOOP;
  RETURN (10 - s % 10) % 10 = substr(c, 18, 1)::int;
END $$;

-- INV-CMX-004: número de contêiner ISO 6346 (3 letras dono + categoria U/J/Z + 6 dígitos + DV)
CREATE OR REPLACE FUNCTION fn_iso6346_dv(p text) RETURNS int LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE s int := 0; i int; ch text; v int; x int := 10; letras text := 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'; tab int[] := '{}';
BEGIN
  FOR i IN 1..26 LOOP IF x % 11 = 0 THEN x := x + 1; END IF; tab := tab || x; x := x + 1; END LOOP;
  FOR i IN 1..10 LOOP
    ch := substr(p, i, 1);
    v := CASE WHEN ch ~ '[0-9]' THEN ch::int ELSE tab[position(ch IN letras)] END;
    s := s + v * (2 ^ (i - 1))::int;
  END LOOP;
  RETURN (s % 11) % 10;
END $$;
CREATE OR REPLACE FUNCTION fn_iso6346_valido(c text) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT c ~ '^[A-Z]{3}[UJZ][0-9]{7}$' AND comex.fn_iso6346_dv(substr(c,1,10)) = substr(c,11,1)::int
$$;

-- ============================ REFERÊNCIA ============================
CREATE TABLE ref_tipo_conteiner (
  codigo text PRIMARY KEY, nome text NOT NULL,
  comp_int_mm int NOT NULL CHECK (comp_int_mm > 0), larg_int_mm int NOT NULL CHECK (larg_int_mm > 0), alt_int_mm int NOT NULL CHECK (alt_int_mm > 0),
  porta_larg_mm int, porta_alt_mm int,
  tara_kg int NOT NULL CHECK (tara_kg > 0), payload_kg int NOT NULL CHECK (payload_kg > 0),
  teto_aberto boolean NOT NULL DEFAULT false, flat_rack boolean NOT NULL DEFAULT false,
  sobrealtura_max_mm int NOT NULL DEFAULT 0 CHECK (sobrealtura_max_mm >= 0),
  pes smallint NOT NULL CHECK (pes IN (20,40)),
  CONSTRAINT ck_tipo_porta CHECK (teto_aberto OR (porta_larg_mm > 0 AND porta_alt_mm > 0))
);
CREATE TABLE ref_tipo_embalagem (
  codigo text PRIMARY KEY, nome text NOT NULL,
  fator_abertura numeric(4,3) NOT NULL CHECK (fator_abertura > 0 AND fator_abertura <= 1),
  barreira boolean NOT NULL
);
CREATE TABLE ref_ncm (codigo text PRIMARY KEY CHECK (codigo ~ '^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$'), descricao text NOT NULL);
CREATE TABLE ref_rota (
  id text PRIMARY KEY, nome text NOT NULL,
  porto_origem text NOT NULL DEFAULT 'Portonave — Navegantes/SC', porto_destino text NOT NULL, pais text NOT NULL,
  transito_dias int NOT NULL CHECK (transito_dias BETWEEN 1 AND 90), transbordo boolean NOT NULL DEFAULT false,
  tributo_pct numeric(6,3) NOT NULL CHECK (tributo_pct >= 0 AND tributo_pct <= 200),
  base_aduaneira text NOT NULL CHECK (base_aduaneira IN ('FOB','CIF')),
  acordo text NOT NULL, exige_co boolean NOT NULL DEFAULT false, ativo boolean NOT NULL DEFAULT true
);
-- INV-CMX-018: uma tarifa vigente por rota × tipo × período
CREATE TABLE ref_rota_frete (
  rota_id text NOT NULL REFERENCES ref_rota(id), tipo_conteiner text NOT NULL REFERENCES ref_tipo_conteiner(codigo),
  frete_usd numeric(12,2) NOT NULL CHECK (frete_usd > 0), vigencia daterange NOT NULL,
  fonte text NOT NULL DEFAULT 'estimativa indicativa set/2026',
  CONSTRAINT ex_frete_vigencia EXCLUDE USING gist (rota_id WITH =, tipo_conteiner WITH =, vigencia WITH &&)
);
COMMENT ON CONSTRAINT ex_frete_vigencia ON ref_rota_frete IS 'INV-CMX-018: tarifa única por rota/tipo/período';
CREATE TABLE ref_incoterm (codigo text PRIMARY KEY CHECK (codigo ~ '^[A-Z]{3}$'), risco text NOT NULL, recomendado_conteiner boolean NOT NULL, seguro_minimo text);
CREATE TABLE ref_componente_custo (codigo text PRIMARY KEY, nome text NOT NULL, ordem smallint NOT NULL UNIQUE);
CREATE TABLE ref_incoterm_componente (
  incoterm text NOT NULL REFERENCES ref_incoterm(codigo), componente text NOT NULL REFERENCES ref_componente_custo(codigo),
  PRIMARY KEY (incoterm, componente)
);
CREATE TABLE ref_custo_param (chave text PRIMARY KEY, valor numeric(14,4) NOT NULL CHECK (valor >= 0), moeda text NOT NULL CHECK (moeda IN ('USD','BRL','PCT','UN')), descricao text NOT NULL);
CREATE TABLE ref_feriado (data date PRIMARY KEY, nome text NOT NULL, abrangencia text NOT NULL DEFAULT 'nacional');
CREATE TABLE ref_estado (codigo text PRIMARY KEY, ordem smallint NOT NULL UNIQUE, nome text NOT NULL, congela_carga boolean NOT NULL DEFAULT false);
CREATE TABLE ref_transicao (de text REFERENCES ref_estado(codigo), para text REFERENCES ref_estado(codigo), PRIMARY KEY (de, para));
CREATE TABLE ref_etapa (
  codigo text PRIMARY KEY, ordem smallint NOT NULL UNIQUE CHECK (ordem > 0), nome text NOT NULL,
  tipo_epcis text NOT NULL CHECK (tipo_epcis IN ('ObjectEvent','AggregationEvent','TransactionEvent','TransformationEvent')),
  biz_step text NOT NULL, estado_destino text NOT NULL REFERENCES ref_estado(codigo), marco_codigo text, local_padrao text NOT NULL
);
CREATE TABLE ref_documento (codigo text PRIMARY KEY, nome text NOT NULL, componente_pagador text REFERENCES ref_componente_custo(codigo), ordem smallint NOT NULL);

-- ============================ OPERAÇÃO ============================
CREATE TABLE cliente (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, nome text NOT NULL UNIQUE,
  pais text NOT NULL, cidade text, segmento text, contato text
);
CREATE TABLE projeto (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  codigo text NOT NULL UNIQUE CHECK (codigo ~ '^CMX-[0-9]{2}-[0-9]{4}$'),
  titulo text NOT NULL, cliente_id bigint NOT NULL REFERENCES cliente(id), consignatario text NOT NULL,
  rota_id text NOT NULL REFERENCES ref_rota(id), incoterm text NOT NULL REFERENCES ref_incoterm(codigo),
  cambio_usd_brl numeric(8,4) NOT NULL CHECK (cambio_usd_brl > 0),                     -- INV-CMX-017
  seguro_pct numeric(5,3) NOT NULL CHECK (seguro_pct >= 0 AND seguro_pct <= 5),
  entrega_alvo date NOT NULL, dia_saida smallint NOT NULL CHECK (dia_saida BETWEEN 1 AND 6),
  parametros jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(parametros) = 'object'),
  estado text NOT NULL DEFAULT 'RASCUNHO' REFERENCES ref_estado(codigo),
  versao int NOT NULL DEFAULT 1, criado_em timestamptz NOT NULL DEFAULT now(), atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE item_carga (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projeto_id bigint NOT NULL REFERENCES projeto(id) ON DELETE CASCADE,
  ordem smallint NOT NULL, codigo text NOT NULL, tag text NOT NULL, nome text NOT NULL,
  qtd int NOT NULL CHECK (qtd >= 0),                                                   -- INV-CMX-002
  secoes int NOT NULL CHECK (secoes BETWEEN 1 AND 20),
  comp_mm int NOT NULL CHECK (comp_mm BETWEEN 100 AND 12000),                          -- INV-CMX-001
  larg_mm int NOT NULL CHECK (larg_mm BETWEEN 100 AND 4000),
  alt_mm  int NOT NULL CHECK (alt_mm  BETWEEN 100 AND 4000),
  peso_kg numeric(10,2) NOT NULL CHECK (peso_kg > 0 AND peso_kg <= 30000),
  valor_usd numeric(14,2) NOT NULL CHECK (valor_usd >= 0),
  ncm text NOT NULL REFERENCES ref_ncm(codigo), embalagem text NOT NULL REFERENCES ref_tipo_embalagem(codigo),
  pilha_max smallint NOT NULL DEFAULT 1 CHECK (pilha_max BETWEEN 1 AND 3),
  UNIQUE (projeto_id, codigo), UNIQUE (projeto_id, ordem)
);
CREATE TABLE volume (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projeto_id bigint NOT NULL REFERENCES projeto(id) ON DELETE CASCADE,
  item_id bigint NOT NULL REFERENCES item_carga(id) ON DELETE CASCADE,
  seq int NOT NULL CHECK (seq > 0), equipamento_n int NOT NULL CHECK (equipamento_n > 0), secao_n int NOT NULL CHECK (secao_n > 0),
  sscc text NOT NULL UNIQUE CHECK (fn_sscc_valido(sscc)),                              -- INV-CMX-003
  ext_comp_mm int NOT NULL, ext_larg_mm int NOT NULL, ext_alt_mm int NOT NULL,
  int_comp_mm int NOT NULL, int_larg_mm int NOT NULL, int_alt_mm int NOT NULL,
  peso_liq_kg numeric(10,2) NOT NULL CHECK (peso_liq_kg > 0),
  tara_kg numeric(10,2) NOT NULL CHECK (tara_kg > 0),
  peso_bruto_kg numeric(10,2) GENERATED ALWAYS AS (peso_liq_kg + tara_kg) STORED,        -- INV-CMX-016
  m3 numeric(10,4) GENERATED ALWAYS AS (ext_comp_mm::numeric * ext_larg_mm * ext_alt_mm / 1e9) STORED,
  valor_usd numeric(14,2) NOT NULL CHECK (valor_usd >= 0),
  dessecante_un int NOT NULL CHECK (dessecante_un >= 0), barreira_m2 numeric(10,2) NOT NULL CHECK (barreira_m2 >= 0),
  madeira_m3 numeric(10,4) NOT NULL CHECK (madeira_m3 >= 0), custo_emb_brl numeric(12,2) NOT NULL CHECK (custo_emb_brl >= 0),
  UNIQUE (projeto_id, seq),
  CONSTRAINT ck_volume_envelope CHECK (ext_comp_mm > int_comp_mm AND ext_larg_mm > int_larg_mm AND ext_alt_mm > int_alt_mm)
);
COMMENT ON CONSTRAINT ck_volume_envelope ON volume IS 'INV-CMX-019: dimensão externa da caixa DEVE exceder a interna';
CREATE TABLE conteiner (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projeto_id bigint NOT NULL REFERENCES projeto(id) ON DELETE CASCADE,
  ordem smallint NOT NULL, tipo text NOT NULL REFERENCES ref_tipo_conteiner(codigo),
  numero text NOT NULL UNIQUE CHECK (fn_iso6346_valido(numero)),                       -- INV-CMX-004
  lacre text NOT NULL UNIQUE,
  cg_long_pct numeric(6,2) NOT NULL, cg_trans_pct numeric(6,2) NOT NULL,
  area_pct numeric(6,2) NOT NULL CHECK (area_pct BETWEEN 0 AND 100),
  sobrealtura_mm int NOT NULL DEFAULT 0 CHECK (sobrealtura_mm >= 0),
  deslocamento_mm int NOT NULL DEFAULT 0 CHECK (deslocamento_mm >= 0),
  UNIQUE (projeto_id, ordem),
  CONSTRAINT ck_cont_cg CHECK (abs(cg_long_pct) <= 15 AND abs(cg_trans_pct) <= 15)
);
COMMENT ON CONSTRAINT ck_cont_cg ON conteiner IS 'INV-CMX-020: CG NÃO DEVE se afastar mais de 15% do centro';
CREATE TABLE alocacao (
  volume_id bigint PRIMARY KEY REFERENCES volume(id) ON DELETE CASCADE,                -- INV-CMX-006
  conteiner_id bigint NOT NULL REFERENCES conteiner(id) ON DELETE CASCADE,
  pilha_n int NOT NULL, nivel smallint NOT NULL CHECK (nivel BETWEEN 1 AND 3),
  x_mm int NOT NULL CHECK (x_mm >= 0), y_mm int NOT NULL CHECK (y_mm >= 0),
  comp_mm int NOT NULL CHECK (comp_mm > 0), larg_mm int NOT NULL CHECK (larg_mm > 0),
  rotacionado boolean NOT NULL
);
CREATE TABLE cotacao (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projeto_id bigint NOT NULL REFERENCES projeto(id) ON DELETE CASCADE,
  versao int NOT NULL, incoterm text NOT NULL REFERENCES ref_incoterm(codigo), rota_id text NOT NULL REFERENCES ref_rota(id),
  cambio_usd_brl numeric(8,4) NOT NULL CHECK (cambio_usd_brl > 0), seguro_pct numeric(5,3) NOT NULL,
  fob_usd numeric(14,2) NOT NULL, base_aduaneira_usd numeric(14,2) NOT NULL, tributos_usd numeric(14,2) NOT NULL,
  logistica_usd numeric(14,2) NOT NULL, vendedor_usd numeric(14,2) NOT NULL, comprador_usd numeric(14,2) NOT NULL,
  status text NOT NULL DEFAULT 'RASCUNHO' CHECK (status IN ('RASCUNHO','APROVADA','SUBSTITUIDA')),
  aprovado_por text, aprovado_em timestamptz, criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (projeto_id, versao),
  CONSTRAINT ck_cot_gate CHECK (status = 'RASCUNHO' OR (aprovado_por IS NOT NULL AND length(trim(aprovado_por)) > 2 AND aprovado_em IS NOT NULL))
);
COMMENT ON CONSTRAINT ck_cot_gate ON cotacao IS 'INV-CMX-013: cotação só sai de RASCUNHO com aprovador humano identificado';
CREATE UNIQUE INDEX ux_cotacao_aprovada ON cotacao (projeto_id) WHERE status = 'APROVADA';  -- INV-CMX-014
CREATE TABLE cotacao_linha (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cotacao_id bigint NOT NULL REFERENCES cotacao(id) ON DELETE CASCADE,
  componente text NOT NULL REFERENCES ref_componente_custo(codigo), conteiner_ordem smallint,
  descricao text NOT NULL, valor_usd numeric(14,2) NOT NULL CHECK (valor_usd >= 0),
  pagador text NOT NULL CHECK (pagador IN ('VENDEDOR','COMPRADOR'))
);
CREATE TABLE marco (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projeto_id bigint NOT NULL REFERENCES projeto(id) ON DELETE CASCADE,
  ordem smallint NOT NULL, codigo text NOT NULL, descricao text NOT NULL,
  fase text NOT NULL CHECK (fase IN ('PRE','MAR','POS')), critico boolean NOT NULL DEFAULT false,
  data_prevista date NOT NULL, data_real date,
  UNIQUE (projeto_id, codigo),
  CONSTRAINT ck_marco_real CHECK (data_real IS NULL OR data_real <= CURRENT_DATE + 1)
);
-- INV-CMX-008: ledger append-only, SHA-256 encadeado, sequência contígua por projeto
CREATE TABLE ledger_evento (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projeto_id bigint NOT NULL REFERENCES projeto(id),
  seq int NOT NULL, ts timestamptz NOT NULL, etapa text NOT NULL REFERENCES ref_etapa(codigo),
  tipo_epcis text NOT NULL, biz_step text NOT NULL, local text NOT NULL,
  dados jsonb NOT NULL DEFAULT '{}'::jsonb,
  registrado_por text NOT NULL CHECK (length(trim(registrado_por)) > 2),
  prev_hash bytea NOT NULL, hash bytea NOT NULL, registrado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (projeto_id, seq), UNIQUE (projeto_id, etapa)
);
CREATE TABLE documento (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projeto_id bigint NOT NULL REFERENCES projeto(id) ON DELETE CASCADE,
  tipo text NOT NULL REFERENCES ref_documento(codigo),
  status text NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE','EMITIDO','NAO_APLICA')),
  numero text, hash_arquivo text CHECK (hash_arquivo IS NULL OR hash_arquivo ~ '^[0-9a-f]{64}$'), emitido_em timestamptz,
  UNIQUE (projeto_id, tipo),
  CONSTRAINT ck_doc_emitido CHECK (status <> 'EMITIDO' OR (numero IS NOT NULL AND emitido_em IS NOT NULL))
);
COMMENT ON CONSTRAINT ck_doc_emitido ON documento IS 'INV-CMX-015: documento emitido DEVE ter número e data';

CREATE INDEX ix_item_projeto ON item_carga(projeto_id);
CREATE INDEX ix_volume_projeto ON volume(projeto_id);
CREATE INDEX ix_volume_item ON volume(item_id);
CREATE INDEX ix_conteiner_projeto ON conteiner(projeto_id);
CREATE INDEX ix_alocacao_cont ON alocacao(conteiner_id);
CREATE INDEX ix_marco_projeto ON marco(projeto_id, ordem);
CREATE INDEX ix_ledger_projeto ON ledger_evento(projeto_id, seq);
CREATE INDEX ix_cotacao_projeto ON cotacao(projeto_id, versao DESC);
CREATE INDEX ix_linha_cotacao ON cotacao_linha(cotacao_id);
CREATE INDEX ix_documento_projeto ON documento(projeto_id);
