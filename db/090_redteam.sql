-- RED-TEAM: cada teste TENTA violar uma invariante direto no banco.
-- PASS = o banco recusou. FAIL = a invariante não existe de fato.
-- Roda dentro de uma transação desfeita ao final: não altera dados.
BEGIN;
SET search_path = comex, public;
CREATE TEMP TABLE rt (inv text, caso text, resultado text, msg text);

-- esperado: trecho que DEVE aparecer na mensagem (código INV ou nome da constraint).
-- Recusa por outro motivo conta como FAIL: o teste não provou a invariante.
CREATE OR REPLACE FUNCTION pg_temp.tenta(inv text, caso text, sql text, esperado text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE sql;
    INSERT INTO rt VALUES (inv, caso, 'FAIL', 'o banco aceitou');
  EXCEPTION WHEN OTHERS THEN
    INSERT INTO rt VALUES (inv, caso, CASE WHEN SQLERRM ILIKE '%' || esperado || '%' THEN 'PASS' ELSE 'FAIL' END, left(SQLERRM, 95));
  END;
END $$;

DO $$
DECLARE p_plan bigint; p_emb bigint; p_fim bigint; v1 bigint; v2 bigint; c20 bigint; cot bigint; it bigint; doc bigint;
BEGIN
  SELECT id INTO p_plan FROM projeto WHERE codigo = 'CMX-26-0147';
  SELECT id INTO p_emb  FROM projeto WHERE codigo = 'CMX-26-0139';
  SELECT id INTO p_fim  FROM projeto WHERE codigo = 'CMX-26-0121';
  SELECT id INTO it FROM item_carga WHERE projeto_id = p_plan ORDER BY ordem LIMIT 1;
  SELECT id INTO v1 FROM volume WHERE projeto_id = p_plan ORDER BY seq LIMIT 1;
  SELECT id INTO cot FROM cotacao WHERE projeto_id = p_fim AND status = 'APROVADA';

  PERFORM pg_temp.tenta('INV-CMX-001','item com altura negativa', format('UPDATE item_carga SET alt_mm = -1 WHERE id = %s', it), '_check');
  PERFORM pg_temp.tenta('INV-CMX-001','item com peso zero', format('UPDATE item_carga SET peso_kg = 0 WHERE id = %s', it), '_check');
  PERFORM pg_temp.tenta('INV-CMX-002','zero seções', format('UPDATE item_carga SET secoes = 0 WHERE id = %s', it), '_check');
  PERFORM pg_temp.tenta('INV-CMX-002','empilhamento 5 alturas', format('UPDATE item_carga SET pilha_max = 5 WHERE id = %s', it), '_check');
  PERFORM pg_temp.tenta('INV-CMX-003','SSCC com DV errado', format('UPDATE volume SET sscc = ''378901230000100019'' WHERE id = %s', v1), 'sscc');
  PERFORM pg_temp.tenta('INV-CMX-003','SSCC duplicado', format('UPDATE volume SET sscc = (SELECT sscc FROM volume WHERE projeto_id = %s AND seq = 2) WHERE id = %s', p_plan, v1), 'sscc');
  PERFORM pg_temp.tenta('INV-CMX-004','contêiner com DV ISO 6346 errado',
    format('UPDATE conteiner SET numero = ''GPSU0001012'' WHERE projeto_id = %s AND ordem = 1', p_plan), 'conteiner_numero_check');
  PERFORM pg_temp.tenta('INV-CMX-005','volume de 30 t num 20DV (payload)',
    format($q$UPDATE volume SET peso_liq_kg = 29000 WHERE id = %s$q$, v1) || '; ' ||
    format($q$INSERT INTO conteiner (projeto_id,ordem,tipo,numero,lacre,cg_long_pct,cg_trans_pct,area_pct) VALUES (%s,9,'20DV','GPSU000109' || fn_iso6346_dv('GPSU000109'),'BR9999999',0,0,1)$q$, p_plan) || '; ' ||
    format($q$UPDATE alocacao SET conteiner_id = (SELECT id FROM conteiner WHERE projeto_id=%s AND ordem=9), x_mm=0, y_mm=0 WHERE volume_id = %s$q$, p_plan, v1), 'INV-CMX-005');
  PERFORM pg_temp.tenta('INV-CMX-006','volume em dois contêineres',
    format('INSERT INTO alocacao SELECT volume_id, conteiner_id, pilha_n, nivel, x_mm, y_mm, comp_mm, larg_mm, rotacionado FROM alocacao WHERE volume_id = %s', v1), 'alocacao_pkey');
  INSERT INTO projeto (codigo,titulo,cliente_id,consignatario,rota_id,incoterm,cambio_usd_brl,seguro_pct,entrega_alvo,dia_saida)
    SELECT 'CMX-99-9999','red team',cliente_id,'x','USHOU','DAP',5,0.2,'2027-01-01',4 FROM projeto WHERE id = p_plan;
  INSERT INTO conteiner (projeto_id,ordem,tipo,numero,lacre,cg_long_pct,cg_trans_pct,area_pct)
    SELECT id,1,'40HC','GPSU999901' || fn_iso6346_dv('GPSU999901'),'BR0000001',0,0,1 FROM projeto WHERE codigo = 'CMX-99-9999';
  PERFORM pg_temp.tenta('INV-CMX-006','volume alocado em contêiner de outro projeto',
    format('UPDATE alocacao SET conteiner_id = (SELECT c.id FROM conteiner c JOIN projeto p ON p.id = c.projeto_id WHERE p.codigo = ''CMX-99-9999'') WHERE volume_id = %s', v1), 'INV-CMX-006');
  PERFORM pg_temp.tenta('INV-CMX-007','volume além do piso do contêiner', format('UPDATE alocacao SET x_mm = 11000 WHERE volume_id = %s', v1), 'INV-CMX-007');
  PERFORM pg_temp.tenta('INV-CMX-008','UPDATE no ledger', format('UPDATE ledger_evento SET dados = ''{"peso":"alterado"}'' WHERE projeto_id = %s AND seq = 1', p_fim), 'INV-CMX-008');
  PERFORM pg_temp.tenta('INV-CMX-008','DELETE no ledger', format('DELETE FROM ledger_evento WHERE projeto_id = %s', p_fim), 'INV-CMX-008');
  PERFORM pg_temp.tenta('INV-CMX-008','TRUNCATE no ledger', 'TRUNCATE ledger_evento', 'INV-CMX-008');
  PERFORM pg_temp.tenta('INV-CMX-008','papel da aplicação tenta UPDATE (REVOKE)',
    format('SET LOCAL ROLE comex_app; UPDATE ledger_evento SET local = ''x'' WHERE projeto_id = %s', p_fim), 'permission denied');
  PERFORM pg_temp.tenta('INV-CMX-009','pular de PLANEJADO para EMBARCADO', format('UPDATE projeto SET estado = ''EMBARCADO'' WHERE id = %s', p_plan), 'INV-CMX-009');
  PERFORM pg_temp.tenta('INV-CMX-009','voltar de ENTREGUE para PLANEJADO', format('UPDATE projeto SET estado = ''PLANEJADO'' WHERE id = %s', p_fim), 'INV-CMX-009');
  PERFORM pg_temp.tenta('INV-CMX-010','alterar item após embalar', format('UPDATE item_carga SET qtd = 5 WHERE projeto_id = %s', p_emb), 'INV-CMX-010');
  PERFORM pg_temp.tenta('INV-CMX-010','apagar volume após embalar', format('DELETE FROM volume WHERE projeto_id = %s', p_emb), 'INV-CMX-010');
  PERFORM pg_temp.tenta('INV-CMX-010','mover alocação após estufar', format('UPDATE alocacao SET x_mm = x_mm + 10 WHERE conteiner_id IN (SELECT id FROM conteiner WHERE projeto_id = %s)', p_emb), 'INV-CMX-010');
  PERFORM pg_temp.tenta('INV-CMX-011','registrar ENTREGA pulando etapas',
    format($q$INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%s,0,now(),'ENTREGA','','','x','red.team','','')$q$, p_plan), 'INV-CMX-011');
  PERFORM pg_temp.tenta('INV-CMX-011','repetir etapa já registrada',
    format($q$INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%s,0,now(),'PEDIDO','','','x','red.team','','')$q$, p_plan), 'INV-CMX-011');
  PERFORM pg_temp.tenta('INV-CMX-012','trocar rota após embalar', format('UPDATE projeto SET rota_id = ''USHOU'' WHERE id = %s', p_emb), 'INV-CMX-012');
  PERFORM pg_temp.tenta('INV-CMX-013','aprovar cotação sem aprovador',
    format('UPDATE cotacao SET status = ''APROVADA'' WHERE projeto_id = %s AND status = ''RASCUNHO''', p_plan), 'ck_cot_gate');
  PERFORM pg_temp.tenta('INV-CMX-013','alterar valor de cotação aprovada', format('UPDATE cotacao SET vendedor_usd = 1 WHERE id = %s', cot), 'INV-CMX-013');
  PERFORM pg_temp.tenta('INV-CMX-013','apagar cotação aprovada', format('DELETE FROM cotacao WHERE id = %s', cot), 'INV-CMX-013');
  PERFORM pg_temp.tenta('INV-CMX-013','inserir linha em cotação aprovada',
    format($q$INSERT INTO cotacao_linha (cotacao_id,componente,descricao,valor_usd,pagador) VALUES (%s,'frete','x',1,'VENDEDOR')$q$, cot), 'INV-CMX-013');
  PERFORM pg_temp.tenta('INV-CMX-014','segunda cotação aprovada no mesmo projeto',
    format($q$INSERT INTO cotacao (projeto_id,versao,incoterm,rota_id,cambio_usd_brl,seguro_pct,fob_usd,base_aduaneira_usd,tributos_usd,logistica_usd,vendedor_usd,comprador_usd,status,aprovado_por,aprovado_em)
              VALUES (%s,99,'FCA','NLRTM',5,0.2,1,1,0,1,1,0,'APROVADA','red.team',now())$q$, p_fim), 'ux_cotacao_aprovada');
  PERFORM pg_temp.tenta('INV-CMX-015','documento emitido sem número',
    format('UPDATE documento SET status = ''EMITIDO'', numero = NULL WHERE projeto_id = %s AND tipo = ''FAT''', p_plan), 'ck_doc_emitido');
  PERFORM pg_temp.tenta('INV-CMX-016','forçar peso bruto divergente', format('UPDATE volume SET peso_bruto_kg = 1 WHERE id = %s', v1), 'peso_bruto_kg');
  PERFORM pg_temp.tenta('INV-CMX-017','câmbio zero', format('UPDATE projeto SET cambio_usd_brl = 0 WHERE id = %s', p_plan), 'cambio_usd_brl_check');
  PERFORM pg_temp.tenta('INV-CMX-018','tarifa sobreposta na mesma vigência',
    $q$INSERT INTO ref_rota_frete (rota_id,tipo_conteiner,frete_usd,vigencia) VALUES ('USHOU','40HC',1000,daterange('2026-09-01','2026-10-01'))$q$, 'ex_frete_vigencia');
  PERFORM pg_temp.tenta('INV-CMX-019','caixa menor que o conteúdo', format('UPDATE volume SET ext_alt_mm = int_alt_mm WHERE id = %s', v1), 'ck_volume_envelope');
  PERFORM pg_temp.tenta('INV-CMX-020','CG deslocado 40%%', format('UPDATE conteiner SET cg_long_pct = 40 WHERE projeto_id = %s AND ordem = 1', p_plan), 'ck_cont_cg');
  PERFORM pg_temp.tenta('INV-CMX-021','evento com data futura',
    format($q$INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%s,0,now()+interval '10 days','FAT','','','x','red.team','','')$q$, p_plan), 'INV-CMX-021');
  PERFORM pg_temp.tenta('INV-CMX-021','evento anterior ao último',
    format($q$INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%s,0,'2020-01-01','FAT','','','x','red.team','','')$q$, p_plan), 'INV-CMX-021');
  PERFORM pg_temp.tenta('INV-CMX-022','estufar sem cotação aprovada',
    format($q$INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%1$s,0,now(),'FAT','','','x','red.team','',''); 
              INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%1$s,0,now(),'EMBALAGEM','','','x','red.team','','');
              INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%1$s,0,now(),'ESTUFAGEM','','','x','red.team','','')$q$, p_plan), 'INV-CMX-022');
  PERFORM pg_temp.tenta('INV-CMX-024','aprovar em nome de outro usuário autenticado',
    format($q$SELECT set_config('comex.usuario','maria.comercial',true), set_config('comex.papeis','comex-comercial',true);
              UPDATE cotacao SET status='APROVADA', aprovado_por='joao.outro', aprovado_em=now() WHERE projeto_id=%s AND status='RASCUNHO'$q$, p_plan), 'INV-CMX-024');
  PERFORM pg_temp.tenta('INV-CMX-025','logística tenta aprovar cotação',
    format($q$SELECT set_config('comex.usuario','ana.logistica',true), set_config('comex.papeis','comex-logistica',true);
              UPDATE cotacao SET status='APROVADA', aprovado_por='ana.logistica', aprovado_em=now() WHERE projeto_id=%s AND status='RASCUNHO'$q$, p_plan), 'INV-CMX-025');
  PERFORM pg_temp.tenta('INV-CMX-025','comercial tenta registrar evento do ledger',
    format($q$SELECT set_config('comex.usuario','maria.comercial',true), set_config('comex.papeis','comex-comercial',true);
              INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%s,0,now(),'FAT','','','x','maria.comercial','','')$q$, p_plan), 'INV-CMX-025');
  PERFORM pg_temp.tenta('INV-CMX-024','evento assinado com nome diferente do token',
    format($q$SELECT set_config('comex.usuario','ana.logistica',true), set_config('comex.papeis','comex-logistica',true);
              INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash) VALUES (%s,0,now(),'FAT','','','x','alguem.mais','','')$q$, p_plan), 'INV-CMX-024');
  PERFORM set_config('comex.usuario','',true); PERFORM set_config('comex.papeis','',true);
  -- ---------- documentos com anexo ----------
  SELECT id INTO doc FROM documento WHERE projeto_id = p_plan AND tipo = 'FAT';
  INSERT INTO documento_arquivo (documento_id,versao,nome_arquivo,mime,tamanho,conteudo,sha256,enviado_por)
    VALUES (doc,0,'fat.pdf','application/pdf',14,convert_to('%PDF-1.4 teste','UTF8'),'x','red.team');
  PERFORM pg_temp.tenta('INV-CMX-026','sobrescrever conteúdo do arquivo', format($q$UPDATE documento_arquivo SET conteudo = convert_to('%%PDF-falso','UTF8') WHERE documento_id = %s$q$, doc), 'INV-CMX-026');
  PERFORM pg_temp.tenta('INV-CMX-026','apagar versão do arquivo', format('DELETE FROM documento_arquivo WHERE documento_id = %s', doc), 'INV-CMX-026');
  PERFORM pg_temp.tenta('INV-CMX-026','TRUNCATE nos arquivos', 'TRUNCATE documento_arquivo', 'INV-CMX-026');
  PERFORM pg_temp.tenta('INV-CMX-027','gravar hash do documento à mão', format($q$UPDATE documento SET hash_arquivo = repeat('a',64) WHERE id = %s$q$, doc), 'INV-CMX-027');
  PERFORM pg_temp.tenta('INV-CMX-028','PNG declarado como PDF',
    format($q$INSERT INTO documento_arquivo (documento_id,versao,nome_arquivo,mime,tamanho,conteudo,sha256,enviado_por) VALUES (%s,0,'x.pdf','application/pdf',8,'\x89504e470d0a1a0a'::bytea,'','red.team')$q$, doc), 'INV-CMX-028');
  PERFORM pg_temp.tenta('INV-CMX-028','executável renomeado para .pdf',
    format($q$INSERT INTO documento_arquivo (documento_id,versao,nome_arquivo,mime,tamanho,conteudo,sha256,enviado_por) VALUES (%s,0,'nota.pdf','application/pdf',4,'\x4d5a9000'::bytea,'','red.team')$q$, doc), 'INV-CMX-028');
  PERFORM pg_temp.tenta('INV-CMX-028','tipo HTML fora da lista',
    format($q$INSERT INTO documento_arquivo (documento_id,versao,nome_arquivo,mime,tamanho,conteudo,sha256,enviado_por) VALUES (%s,0,'x.html','text/html',6,convert_to('<html>','UTF8'),'','red.team')$q$, doc), 'tipo de arquivo não permitido');
  PERFORM pg_temp.tenta('INV-CMX-028','tamanho declarado diferente do real',
    format($q$INSERT INTO documento_arquivo (documento_id,versao,nome_arquivo,mime,tamanho,conteudo,sha256,enviado_por) VALUES (%s,0,'x.pdf','application/pdf',999,convert_to('%%PDF-1.4','UTF8'),'','red.team')$q$, doc), 'upload incompleto');
  PERFORM pg_temp.tenta('INV-CMX-029','documento emitido volta a pendente',
    format($q$UPDATE documento SET status = 'EMITIDO', numero = 'FAT-1', emitido_em = now() WHERE id = %1$s; UPDATE documento SET status = 'PENDENTE' WHERE id = %1$s$q$, doc), 'INV-CMX-029');
  PERFORM pg_temp.tenta('INV-CMX-029','leitura tenta anexar arquivo',
    format($q$SELECT set_config('comex.usuario','lia.leitura',true), set_config('comex.papeis','comex-leitura',true);
              INSERT INTO documento_arquivo (documento_id,versao,nome_arquivo,mime,tamanho,conteudo,sha256,enviado_por) VALUES (%s,0,'x.pdf','application/pdf',8,convert_to('%%PDF-1.4','UTF8'),'','lia.leitura')$q$, doc), 'INV-CMX-025');
  PERFORM pg_temp.tenta('INV-CMX-029','anexar em nome de outra pessoa',
    format($q$SELECT set_config('comex.usuario','ana.logistica',true), set_config('comex.papeis','comex-logistica',true);
              INSERT INTO documento_arquivo (documento_id,versao,nome_arquivo,mime,tamanho,conteudo,sha256,enviado_por) VALUES (%s,0,'x.pdf','application/pdf',8,convert_to('%%PDF-1.4','UTF8'),'','outra.pessoa')$q$, doc), 'INV-CMX-024');
  PERFORM set_config('comex.usuario','',true); PERFORM set_config('comex.papeis','',true);
  DECLARE v int; h text; BEGIN
    SELECT versao, sha256 INTO v, h FROM documento_arquivo WHERE documento_id = doc ORDER BY versao DESC LIMIT 1;
    INSERT INTO rt VALUES ('INV-CMX-027','versão e hash forjados na inserção',
      CASE WHEN v = 1 AND h = encode(digest(convert_to('%PDF-1.4 teste','UTF8'),'sha256'),'hex')
                AND (SELECT hash_arquivo FROM documento WHERE id = doc) = h THEN 'PASS' ELSE 'FAIL' END,
      'versão enviada 0 → gravada ' || v || '; sha256 recalculado e propagado ao documento');
  END;

  -- forjar hash/seq: o trigger DEVE descartar os valores enviados e recalcular
  DECLARE h bytea; sq int; ok boolean; r text;
  BEGIN
  BEGIN
    INSERT INTO ledger_evento (projeto_id,seq,ts,etapa,tipo_epcis,biz_step,local,registrado_por,prev_hash,hash)
    VALUES (p_plan,77,now(),'FAT','','','x','red.team','\xdead','\xbeef') RETURNING hash, seq INTO h, sq;
    SELECT bool_and(hash_ok AND elo_ok) INTO ok FROM fn_ledger_verificar(p_plan);
    r := CASE WHEN h <> '\xbeef'::bytea AND sq <> 77 AND ok THEN 'PASS' ELSE 'FAIL' END || '|seq enviado 77 → gravado ' || sq || '; hash recalculado; cadeia íntegra: ' || ok;
    RAISE EXCEPTION 'desfaz';
  EXCEPTION WHEN raise_exception THEN NULL;
  END;
  INSERT INTO rt VALUES ('INV-CMX-008','forjar hash e seq na inserção', split_part(r,'|',1), split_part(r,'|',2));
  END;
END $$;

SELECT inv, caso, resultado, msg FROM rt ORDER BY inv, caso;
SELECT count(*) FILTER (WHERE resultado = 'PASS') AS pass, count(*) FILTER (WHERE resultado = 'FAIL') AS fail FROM rt;
ROLLBACK;
