SET search_path = comex, public;

-- ---------- dias úteis com feriados ----------
CREATE OR REPLACE FUNCTION fn_dia_util(d date) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT extract(isodow FROM d) < 6 AND NOT EXISTS (SELECT 1 FROM comex.ref_feriado f WHERE f.data = d)
$$;
CREATE OR REPLACE FUNCTION fn_dias_uteis_antes(d date, n int) RETURNS date LANGUAGE plpgsql STABLE AS $$
DECLARE x date := d; BEGIN
  WHILE n > 0 LOOP x := x - 1; IF comex.fn_dia_util(x) THEN n := n - 1; END IF; END LOOP; RETURN x; END $$;

-- ---------- INV-CMX-009: transição de estado do projeto só por tabela ----------
CREATE OR REPLACE FUNCTION fn_projeto_transicao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado IS DISTINCT FROM NEW.estado AND NOT EXISTS (
       SELECT 1 FROM comex.ref_transicao WHERE de = OLD.estado AND para = NEW.estado) THEN
    RAISE EXCEPTION 'INV-CMX-009: transição de estado % -> % não permitida', OLD.estado, NEW.estado
      USING ERRCODE = 'check_violation';
  END IF;
  NEW.atualizado_em := now();
  IF ROW(OLD.rota_id, OLD.incoterm, OLD.cambio_usd_brl, OLD.seguro_pct, OLD.entrega_alvo, OLD.dia_saida, OLD.parametros)
     IS DISTINCT FROM ROW(NEW.rota_id, NEW.incoterm, NEW.cambio_usd_brl, NEW.seguro_pct, NEW.entrega_alvo, NEW.dia_saida, NEW.parametros) THEN
    NEW.versao := OLD.versao + 1;
  END IF;
  -- INV-CMX-012: rota e parâmetros de embalagem congelam após embalar
  IF (SELECT congela_carga FROM comex.ref_estado WHERE codigo = OLD.estado)
     AND (OLD.rota_id IS DISTINCT FROM NEW.rota_id OR OLD.parametros IS DISTINCT FROM NEW.parametros) THEN
    RAISE EXCEPTION 'INV-CMX-012: rota e parâmetros de embalagem congelados no estado %', OLD.estado
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_projeto_transicao BEFORE UPDATE ON projeto FOR EACH ROW EXECUTE FUNCTION fn_projeto_transicao();

-- ---------- INV-CMX-010: carga, volumes e estufagem congelam após EMBALADO ----------
CREATE OR REPLACE FUNCTION fn_carga_congelada() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE pid bigint; st text;
BEGIN
  IF TG_TABLE_NAME = 'alocacao' THEN
    SELECT c.projeto_id INTO pid FROM comex.conteiner c WHERE c.id = COALESCE(NEW.conteiner_id, OLD.conteiner_id);
  ELSE
    pid := COALESCE(NEW.projeto_id, OLD.projeto_id);
  END IF;
  SELECT estado INTO st FROM comex.projeto WHERE id = pid;
  IF st IS NOT NULL AND (SELECT congela_carga FROM comex.ref_estado WHERE codigo = st) THEN
    RAISE EXCEPTION 'INV-CMX-010: % congelado — projeto no estado %', TG_TABLE_NAME, st USING ERRCODE = 'check_violation';
  END IF;
  RETURN COALESCE(NEW, OLD);
END $$;
CREATE TRIGGER tg_item_congelado  BEFORE INSERT OR UPDATE OR DELETE ON item_carga FOR EACH ROW EXECUTE FUNCTION fn_carga_congelada();
CREATE TRIGGER tg_vol_congelado   BEFORE INSERT OR UPDATE OR DELETE ON volume     FOR EACH ROW EXECUTE FUNCTION fn_carga_congelada();
CREATE TRIGGER tg_cont_congelado  BEFORE INSERT OR UPDATE OR DELETE ON conteiner  FOR EACH ROW EXECUTE FUNCTION fn_carga_congelada();
CREATE TRIGGER tg_aloc_congelada  BEFORE INSERT OR UPDATE OR DELETE ON alocacao   FOR EACH ROW EXECUTE FUNCTION fn_carga_congelada();

-- ---------- INV-CMX-005/007: alocação cabe no piso e respeita o payload ----------
CREATE OR REPLACE FUNCTION fn_alocacao_valida() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE t comex.ref_tipo_conteiner; carga numeric; vproj bigint; cproj bigint;
BEGIN
  SELECT r.* INTO t FROM comex.conteiner c JOIN comex.ref_tipo_conteiner r ON r.codigo = c.tipo WHERE c.id = NEW.conteiner_id;
  SELECT projeto_id INTO vproj FROM comex.volume WHERE id = NEW.volume_id;
  SELECT projeto_id INTO cproj FROM comex.conteiner WHERE id = NEW.conteiner_id;
  IF vproj <> cproj THEN
    RAISE EXCEPTION 'INV-CMX-006: volume e contêiner de projetos diferentes' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.x_mm + NEW.comp_mm > t.comp_int_mm OR (NOT t.flat_rack AND NEW.y_mm + NEW.larg_mm > t.larg_int_mm) THEN
    RAISE EXCEPTION 'INV-CMX-007: volume % fora do piso do contêiner %', NEW.volume_id, t.codigo USING ERRCODE = 'check_violation';
  END IF;
  SELECT COALESCE(sum(v.peso_bruto_kg),0) INTO carga FROM comex.alocacao a JOIN comex.volume v ON v.id = a.volume_id
   WHERE a.conteiner_id = NEW.conteiner_id AND a.volume_id <> NEW.volume_id;
  carga := carga + (SELECT peso_bruto_kg FROM comex.volume WHERE id = NEW.volume_id);
  IF carga > t.payload_kg THEN
    RAISE EXCEPTION 'INV-CMX-005: carga % kg excede payload % kg do %', carga, t.payload_kg, t.codigo USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_alocacao_valida BEFORE INSERT OR UPDATE ON alocacao FOR EACH ROW EXECUTE FUNCTION fn_alocacao_valida();

-- ---------- cotação aprovada é imutável ----------
CREATE OR REPLACE FUNCTION fn_cotacao_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'RASCUNHO' THEN RAISE EXCEPTION 'INV-CMX-013: cotação % não pode ser apagada', OLD.status USING ERRCODE='check_violation'; END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'SUBSTITUIDA' OR (OLD.status = 'APROVADA' AND NEW.status <> 'SUBSTITUIDA')
     OR (OLD.status = 'APROVADA' AND ROW(NEW.fob_usd,NEW.logistica_usd,NEW.vendedor_usd,NEW.incoterm) IS DISTINCT FROM ROW(OLD.fob_usd,OLD.logistica_usd,OLD.vendedor_usd,OLD.incoterm)) THEN
    RAISE EXCEPTION 'INV-CMX-013: cotação aprovada é imutável' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_cotacao_imutavel BEFORE UPDATE OR DELETE ON cotacao FOR EACH ROW EXECUTE FUNCTION fn_cotacao_imutavel();
CREATE OR REPLACE FUNCTION fn_linha_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT status FROM comex.cotacao WHERE id = COALESCE(NEW.cotacao_id, OLD.cotacao_id)) <> 'RASCUNHO' THEN
    RAISE EXCEPTION 'INV-CMX-013: linhas de cotação aprovada são imutáveis' USING ERRCODE = 'check_violation';
  END IF;
  RETURN COALESCE(NEW, OLD);
END $$;
CREATE TRIGGER tg_linha_imutavel BEFORE INSERT OR UPDATE OR DELETE ON cotacao_linha FOR EACH ROW EXECUTE FUNCTION fn_linha_imutavel();

-- ---------- LEDGER: hash, ordem de etapas, estado ----------
CREATE OR REPLACE FUNCTION fn_ledger_payload(e comex.ledger_evento) RETURNS bytea LANGUAGE sql IMMUTABLE AS $$
  SELECT e.prev_hash || convert_to(
    e.projeto_id::text || '|' || e.seq::text || '|' || to_char(e.ts AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"') || '|' ||
    e.etapa || '|' || e.tipo_epcis || '|' || e.biz_step || '|' || e.local || '|' || e.dados::text || '|' || e.registrado_por, 'UTF8')
$$;

CREATE OR REPLACE FUNCTION fn_ledger_antes() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ult comex.ledger_evento; et comex.ref_etapa; ult_ordem int; p comex.projeto;
BEGIN
  -- serializa inserções do mesmo projeto (sem corrida na sequência)
  SELECT * INTO p FROM comex.projeto WHERE id = NEW.projeto_id FOR UPDATE;
  SELECT * INTO et FROM comex.ref_etapa WHERE codigo = NEW.etapa;
  SELECT * INTO ult FROM comex.ledger_evento WHERE projeto_id = NEW.projeto_id ORDER BY seq DESC LIMIT 1;
  ult_ordem := COALESCE((SELECT ordem FROM comex.ref_etapa WHERE codigo = ult.etapa), 0);
  -- INV-CMX-011: etapas em ordem estrita, sem pular
  IF et.ordem <> ult_ordem + 1 THEN
    RAISE EXCEPTION 'INV-CMX-011: etapa % fora de ordem (esperada ordem %)', NEW.etapa, ult_ordem + 1 USING ERRCODE = 'check_violation';
  END IF;
  -- INV-CMX-021: tempo monotônico e sem evento no futuro
  IF ult.ts IS NOT NULL AND NEW.ts < ult.ts THEN
    RAISE EXCEPTION 'INV-CMX-021: evento anterior ao último registrado' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.ts > now() + interval '1 day' THEN
    RAISE EXCEPTION 'INV-CMX-021: evento no futuro não pode ser registrado' USING ERRCODE = 'check_violation';
  END IF;
  -- INV-CMX-022: estufar exige cotação aprovada (frete contratado por decisão humana)
  IF NEW.etapa = 'ESTUFAGEM' AND NOT EXISTS (SELECT 1 FROM comex.cotacao WHERE projeto_id = NEW.projeto_id AND status = 'APROVADA') THEN
    RAISE EXCEPTION 'INV-CMX-022: estufagem exige cotação aprovada' USING ERRCODE = 'check_violation';
  END IF;
  -- INV-CMX-023: embalar exige volumes calculados; estufar exige alocação completa
  IF NEW.etapa = 'EMBALAGEM' AND NOT EXISTS (SELECT 1 FROM comex.volume WHERE projeto_id = NEW.projeto_id) THEN
    RAISE EXCEPTION 'INV-CMX-023: não há volumes calculados' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.etapa = 'ESTUFAGEM' AND EXISTS (SELECT 1 FROM comex.volume v LEFT JOIN comex.alocacao a ON a.volume_id = v.id
                                           WHERE v.projeto_id = NEW.projeto_id AND a.volume_id IS NULL) THEN
    RAISE EXCEPTION 'INV-CMX-023: há volumes sem contêiner' USING ERRCODE = 'check_violation';
  END IF;
  NEW.seq := COALESCE(ult.seq, 0) + 1;
  NEW.tipo_epcis := et.tipo_epcis;
  NEW.biz_step := et.biz_step;
  NEW.prev_hash := COALESCE(ult.hash, '\x0000000000000000000000000000000000000000000000000000000000000000'::bytea);
  NEW.hash := public.digest(comex.fn_ledger_payload(NEW), 'sha256');
  RETURN NEW;
END $$;
CREATE TRIGGER tg_ledger_antes BEFORE INSERT ON ledger_evento FOR EACH ROW EXECUTE FUNCTION fn_ledger_antes();

CREATE OR REPLACE FUNCTION fn_ledger_depois() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE et comex.ref_etapa; mo int;
BEGIN
  SELECT * INTO et FROM comex.ref_etapa WHERE codigo = NEW.etapa;
  UPDATE comex.projeto SET estado = et.estado_destino WHERE id = NEW.projeto_id AND estado <> et.estado_destino;
  IF et.marco_codigo IS NOT NULL THEN
    SELECT ordem INTO mo FROM comex.marco WHERE projeto_id = NEW.projeto_id AND codigo = et.marco_codigo;
    -- marco da etapa e todos os anteriores ainda abertos passam a realizados
    UPDATE comex.marco SET data_real = (NEW.ts AT TIME ZONE 'America/Sao_Paulo')::date
     WHERE projeto_id = NEW.projeto_id AND data_real IS NULL AND ordem <= mo;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_ledger_depois AFTER INSERT ON ledger_evento FOR EACH ROW EXECUTE FUNCTION fn_ledger_depois();

-- INV-CMX-008: UPDATE/DELETE proibidos mesmo para o dono (o REVOKE cobre os demais papéis)
CREATE OR REPLACE FUNCTION fn_ledger_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'INV-CMX-008: ledger é append-only (% bloqueado)', TG_OP USING ERRCODE = 'insufficient_privilege'; END $$;
CREATE TRIGGER tg_ledger_append_only BEFORE UPDATE OR DELETE ON ledger_evento FOR EACH ROW EXECUTE FUNCTION fn_ledger_append_only();
CREATE TRIGGER tg_ledger_no_truncate BEFORE TRUNCATE ON ledger_evento FOR EACH STATEMENT EXECUTE FUNCTION fn_ledger_append_only();

-- Verificação independente da cadeia
CREATE OR REPLACE FUNCTION fn_ledger_verificar(p_projeto bigint)
RETURNS TABLE(seq int, etapa text, hash_ok boolean, elo_ok boolean) LANGUAGE sql STABLE AS $$
  SELECT e.seq, e.etapa,
         public.digest(comex.fn_ledger_payload(e), 'sha256') = e.hash,
         e.prev_hash = COALESCE(lag(e.hash) OVER (ORDER BY e.seq), '\x0000000000000000000000000000000000000000000000000000000000000000'::bytea)
  FROM comex.ledger_evento e WHERE e.projeto_id = p_projeto ORDER BY e.seq
$$;

-- ---------- VIEWS ----------
CREATE OR REPLACE VIEW vw_packing_list AS
SELECT p.codigo AS projeto, v.seq, i.tag, i.nome, v.secao_n, i.secoes, i.ncm, v.sscc,
       v.ext_comp_mm, v.ext_larg_mm, v.ext_alt_mm, v.peso_liq_kg, v.tara_kg, v.peso_bruto_kg, v.m3,
       c.numero AS conteiner, c.tipo, c.lacre
FROM comex.volume v JOIN comex.item_carga i ON i.id = v.item_id JOIN comex.projeto p ON p.id = v.projeto_id
LEFT JOIN comex.alocacao a ON a.volume_id = v.id LEFT JOIN comex.conteiner c ON c.id = a.conteiner_id;

CREATE OR REPLACE VIEW vw_conteiner_carga AS
SELECT c.*, t.nome AS tipo_nome, t.payload_kg, t.tara_kg AS tara_cont_kg,
       COALESCE(sum(v.peso_bruto_kg),0) AS carga_kg, COALESCE(sum(v.peso_bruto_kg),0) + t.tara_kg AS vgm_kg,
       count(v.id) AS volumes, COALESCE(sum(v.m3),0) AS m3
FROM comex.conteiner c JOIN comex.ref_tipo_conteiner t ON t.codigo = c.tipo
LEFT JOIN comex.alocacao a ON a.conteiner_id = c.id LEFT JOIN comex.volume v ON v.id = a.volume_id
GROUP BY c.id, t.codigo;

CREATE OR REPLACE VIEW vw_projeto_resumo AS
SELECT p.id, p.codigo, p.titulo, cl.nome AS cliente, p.consignatario, p.rota_id, r.nome AS destino, p.incoterm, p.estado, e.nome AS estado_nome,
       p.entrega_alvo, p.versao,
       (SELECT count(*) FROM comex.volume v WHERE v.projeto_id = p.id) AS volumes,
       (SELECT COALESCE(sum(peso_liq_kg),0) FROM comex.volume v WHERE v.projeto_id = p.id) AS peso_liq_kg,
       (SELECT COALESCE(sum(peso_bruto_kg),0) FROM comex.volume v WHERE v.projeto_id = p.id) AS peso_bruto_kg,
       (SELECT COALESCE(sum(m3),0) FROM comex.volume v WHERE v.projeto_id = p.id) AS m3,
       (SELECT string_agg(n || '×' || tipo, ' + ' ORDER BY tipo) FROM (SELECT tipo, count(*) n FROM comex.conteiner c WHERE c.projeto_id = p.id GROUP BY tipo) x) AS conteineres,
       (SELECT data_prevista FROM comex.marco m WHERE m.projeto_id = p.id AND m.codigo = 'etd') AS etd,
       (SELECT jsonb_build_object('codigo', codigo, 'descricao', descricao, 'data', data_prevista) FROM comex.marco m
         WHERE m.projeto_id = p.id AND m.data_real IS NULL ORDER BY ordem LIMIT 1) AS proximo_marco,
       (SELECT jsonb_build_object('id', id, 'status', status, 'vendedor_usd', vendedor_usd, 'logistica_usd', logistica_usd)
          FROM comex.cotacao c WHERE c.projeto_id = p.id AND c.status <> 'SUBSTITUIDA' ORDER BY (status='APROVADA') DESC, versao DESC LIMIT 1) AS cotacao,
       (SELECT count(*) FROM comex.ledger_evento l WHERE l.projeto_id = p.id) AS eventos,
       (SELECT bool_and(hash_ok AND elo_ok) FROM comex.fn_ledger_verificar(p.id)) AS ledger_integro
FROM comex.projeto p JOIN comex.cliente cl ON cl.id = p.cliente_id JOIN comex.ref_rota r ON r.id = p.rota_id JOIN comex.ref_estado e ON e.codigo = p.estado;

-- ---------- PRIVILÉGIOS: papel da aplicação sem UPDATE/DELETE no ledger ----------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'comex_app') THEN CREATE ROLE comex_app NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA comex TO comex_app;
GRANT SELECT ON ALL TABLES IN SCHEMA comex TO comex_app;
GRANT INSERT, UPDATE, DELETE ON projeto, cliente, item_carga, volume, conteiner, alocacao, cotacao, cotacao_linha, marco, documento TO comex_app;
GRANT INSERT ON ledger_evento TO comex_app;
REVOKE UPDATE, DELETE, TRUNCATE ON ledger_evento FROM comex_app, PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA comex TO comex_app;

-- aprovação da cotação realiza os marcos comerciais (cotação e booking)
CREATE OR REPLACE FUNCTION fn_cotacao_aprovada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'APROVADA' AND OLD.status = 'RASCUNHO' THEN
    UPDATE comex.cotacao SET status = 'SUBSTITUIDA' WHERE projeto_id = NEW.projeto_id AND status = 'RASCUNHO' AND id <> NEW.id;
    UPDATE comex.marco SET data_real = (NEW.aprovado_em AT TIME ZONE 'America/Sao_Paulo')::date
     WHERE projeto_id = NEW.projeto_id AND codigo IN ('cot','book') AND data_real IS NULL;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_cotacao_aprovada AFTER UPDATE ON cotacao FOR EACH ROW EXECUTE FUNCTION fn_cotacao_aprovada();

-- ---------- INV-CMX-024/025: identidade e papel vêm da sessão autenticada ----------
-- A API grava por transação: SET LOCAL comex.usuario / comex.papeis (a partir do token OIDC).
-- Quando definidos, o banco exige que o nome gravado seja o do usuário autenticado
-- e que ele tenha o papel da ação. Sem sessão autenticada (seed, manutenção), não se aplica.
CREATE OR REPLACE FUNCTION fn_sessao_confere(nome text, papel text, acao text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE u text := nullif(current_setting('comex.usuario', true), ''); p text := coalesce(current_setting('comex.papeis', true), '');
BEGIN
  IF u IS NULL THEN RETURN; END IF;
  IF nome IS DISTINCT FROM u THEN
    RAISE EXCEPTION 'INV-CMX-024: % em nome de "%", mas o usuário autenticado é "%"', acao, nome, u USING ERRCODE = 'check_violation';
  END IF;
  IF NOT (string_to_array(papel, ',') && string_to_array(p, ',') OR 'comex-admin' = ANY(string_to_array(p, ','))) THEN
    RAISE EXCEPTION 'INV-CMX-025: % exige o papel %', acao, replace(papel, ',', ' ou ') USING ERRCODE = 'insufficient_privilege';
  END IF;
END $$;

CREATE OR REPLACE FUNCTION fn_cotacao_sessao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'APROVADA' AND OLD.status = 'RASCUNHO' THEN
    PERFORM comex.fn_sessao_confere(NEW.aprovado_por, 'comex-comercial', 'aprovação de cotação');
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_cotacao_sessao BEFORE UPDATE ON cotacao FOR EACH ROW EXECUTE FUNCTION fn_cotacao_sessao();

CREATE OR REPLACE FUNCTION fn_ledger_sessao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM comex.fn_sessao_confere(NEW.registrado_por, 'comex-logistica', 'evento do ledger');
  RETURN NEW;
END $$;
-- nome começa com "tg_ledger_0" para rodar antes de tg_ledger_antes (ordem alfabética)
CREATE TRIGGER tg_ledger_0_sessao BEFORE INSERT ON ledger_evento FOR EACH ROW EXECUTE FUNCTION fn_ledger_sessao();
GRANT EXECUTE ON FUNCTION fn_sessao_confere(text, text, text) TO comex_app;


-- =====================================================================
-- DOCUMENTOS COM ANEXO (v1.2)
-- =====================================================================
ALTER TABLE documento ADD COLUMN IF NOT EXISTS emitido_por text;

-- INV-CMX-029: emissão registra quem emitiu; com sessão autenticada, é o usuário do token
CREATE OR REPLACE FUNCTION fn_documento_emissao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'EMITIDO' AND OLD.status IS DISTINCT FROM 'EMITIDO' THEN
    NEW.emitido_por := COALESCE(NEW.emitido_por, nullif(current_setting('comex.usuario', true), ''), 'sistema');
    PERFORM comex.fn_sessao_confere(NEW.emitido_por, 'comex-logistica,comex-comercial', 'emissão de documento');
  END IF;
  IF NEW.hash_arquivo IS DISTINCT FROM OLD.hash_arquivo AND NEW.hash_arquivo IS DISTINCT FROM
     (SELECT a.sha256 FROM comex.documento_arquivo a WHERE a.documento_id = NEW.id ORDER BY a.versao DESC LIMIT 1) THEN
    RAISE EXCEPTION 'INV-CMX-027: hash do documento só pode ser o da última versão armazenada' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'EMITIDO' AND NEW.status <> 'EMITIDO' THEN
    RAISE EXCEPTION 'INV-CMX-029: documento emitido não volta a pendente — emita nova versão do arquivo' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_documento_emissao BEFORE UPDATE ON documento FOR EACH ROW EXECUTE FUNCTION fn_documento_emissao();

CREATE TABLE documento_arquivo (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  documento_id bigint NOT NULL REFERENCES documento(id) ON DELETE RESTRICT,
  versao       int NOT NULL,
  nome_arquivo text NOT NULL CHECK (length(nome_arquivo) BETWEEN 1 AND 200 AND nome_arquivo !~ '[/\\]'),
  mime         text NOT NULL CHECK (mime IN ('application/pdf','image/png','image/jpeg','application/xml','text/xml',
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
  tamanho      int NOT NULL CHECK (tamanho BETWEEN 1 AND 10485760),                       -- INV-CMX-028: até 10 MB
  conteudo     bytea NOT NULL,
  sha256       text NOT NULL,
  enviado_por  text NOT NULL CHECK (length(trim(enviado_por)) > 2),
  enviado_em   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (documento_id, versao),
  CONSTRAINT ck_arquivo_tamanho_real CHECK (octet_length(conteudo) = tamanho)
);
CREATE INDEX ix_arquivo_documento ON documento_arquivo(documento_id, versao DESC);
ALTER TABLE documento_arquivo ALTER COLUMN conteudo SET STORAGE EXTERNAL;   -- binário já comprimido: sem TOAST-compress

CREATE OR REPLACE FUNCTION fn_arquivo_antes() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE cab bytea := substring(NEW.conteudo FROM 1 FOR 8); ok boolean;
BEGIN
  PERFORM 1 FROM comex.documento WHERE id = NEW.documento_id FOR UPDATE;           -- serializa versões do mesmo documento
  -- INV-CMX-028: tipo permitido, tamanho declarado igual ao recebido (divergência = upload truncado)
  IF NEW.mime NOT IN ('application/pdf','image/png','image/jpeg','application/xml','text/xml',
       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/vnd.openxmlformats-officedocument.wordprocessingml.document') THEN
    RAISE EXCEPTION 'INV-CMX-028: tipo de arquivo não permitido (%)', NEW.mime USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.tamanho IS DISTINCT FROM octet_length(NEW.conteudo) THEN
    RAISE EXCEPTION 'INV-CMX-028: tamanho declarado (%) difere do recebido (%) — upload incompleto', NEW.tamanho, octet_length(NEW.conteudo) USING ERRCODE = 'check_violation';
  END IF;
  -- INV-CMX-028: assinatura do conteúdo DEVE corresponder ao tipo declarado
  ok := CASE
    WHEN NEW.mime = 'application/pdf' THEN substring(cab FROM 1 FOR 4) = '\x25504446'::bytea                 -- %PDF
    WHEN NEW.mime = 'image/png'       THEN cab = '\x89504e470d0a1a0a'::bytea
    WHEN NEW.mime = 'image/jpeg'      THEN substring(cab FROM 1 FOR 3) = '\xffd8ff'::bytea
    WHEN NEW.mime IN ('application/xml','text/xml') THEN ltrim(convert_from(substring(NEW.conteudo FROM 1 FOR 64), 'UTF8'), E' \t\r\n\ufeff') LIKE '<%'
    ELSE substring(cab FROM 1 FOR 4) = '\x504b0304'::bytea                                                   -- ZIP (xlsx/docx)
  END;
  IF NOT ok THEN
    RAISE EXCEPTION 'INV-CMX-028: conteúdo do arquivo não corresponde ao tipo %', NEW.mime USING ERRCODE = 'check_violation';
  END IF;
  PERFORM comex.fn_sessao_confere(NEW.enviado_por, 'comex-logistica,comex-comercial', 'anexo de documento');
  -- INV-CMX-027: versão e hash calculados pelo banco (valores enviados são descartados)
  NEW.versao := COALESCE((SELECT max(versao) FROM comex.documento_arquivo WHERE documento_id = NEW.documento_id), 0) + 1;
  NEW.sha256 := encode(public.digest(NEW.conteudo, 'sha256'), 'hex');
  NEW.enviado_em := now();
  RETURN NEW;
END $$;
CREATE TRIGGER tg_arquivo_antes BEFORE INSERT ON documento_arquivo FOR EACH ROW EXECUTE FUNCTION fn_arquivo_antes();

CREATE OR REPLACE FUNCTION fn_arquivo_depois() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE comex.documento SET hash_arquivo = NEW.sha256 WHERE id = NEW.documento_id;
  RETURN NEW;
END $$;
CREATE TRIGGER tg_arquivo_depois AFTER INSERT ON documento_arquivo FOR EACH ROW EXECUTE FUNCTION fn_arquivo_depois();

-- INV-CMX-026: arquivo é append-only (nova versão, nunca sobrescrita)
CREATE OR REPLACE FUNCTION fn_arquivo_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'INV-CMX-026: arquivo de documento é imutável (% bloqueado) — envie nova versão', TG_OP USING ERRCODE = 'insufficient_privilege'; END $$;
CREATE TRIGGER tg_arquivo_imutavel BEFORE UPDATE OR DELETE ON documento_arquivo FOR EACH ROW EXECUTE FUNCTION fn_arquivo_append_only();
CREATE TRIGGER tg_arquivo_no_truncate BEFORE TRUNCATE ON documento_arquivo FOR EACH STATEMENT EXECUTE FUNCTION fn_arquivo_append_only();

GRANT SELECT, INSERT ON documento_arquivo TO comex_app;
REVOKE UPDATE, DELETE, TRUNCATE ON documento_arquivo FROM comex_app, PUBLIC;
