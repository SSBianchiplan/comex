"""Casos de uso. Toda escrita numa transação; invariantes garantidas pelo banco (P1)."""
from starlette.concurrency import run_in_threadpool
import json
from datetime import datetime, timezone, timedelta
from .db import fetch, fetch1, carregar_ref
from . import engine

BRT = timezone(timedelta(hours=-3))

async def projeto_base(conn, pid, lock=False):
    p = await fetch1(conn, 'SELECT * FROM projeto WHERE id = %s' + (' FOR UPDATE' if lock else ''), pid)
    if not p: raise LookupError(f'projeto {pid} não encontrado')
    return p

async def calcular(conn, pid: int) -> dict:
    """Recalcula embalagem, estufagem, cotação (rascunho) e cronograma e persiste."""
    p = await projeto_base(conn, pid, lock=True)
    ref = await carregar_ref(conn)
    itens = await fetch(conn, 'SELECT * FROM item_carga WHERE projeto_id = %s ORDER BY ordem', pid)
    if not itens: raise ValueError('projeto sem itens de carga')
    r = await run_in_threadpool(engine.calcular, p, itens, ref)   # cálculo pesado fora do laço de eventos
    congelado = (await fetch1(conn, 'SELECT congela_carga FROM ref_estado WHERE codigo = %s', p['estado']))['congela_carga']
    if r['est']['sem']: raise ValueError(f"{len(r['est']['sem'])} unidade(s) sem contêiner compatível — rever seções")
    if not congelado:
        await conn.execute('DELETE FROM conteiner WHERE projeto_id = %s', (pid,))
        await conn.execute('DELETE FROM volume WHERE projeto_id = %s', (pid,))
        vid = {}
        for v in r['vols']:
            c = v['cx']
            row = await fetch1(conn, '''INSERT INTO volume (projeto_id,item_id,seq,equipamento_n,secao_n,sscc,ext_comp_mm,ext_larg_mm,ext_alt_mm,
                int_comp_mm,int_larg_mm,int_alt_mm,peso_liq_kg,tara_kg,valor_usd,dessecante_un,barreira_m2,madeira_m3,custo_emb_brl)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                pid, v['item_id'], v['seq'], v['eq'], v['sec'], v['sscc'], c['L'], c['W'], c['H'], c['il'], c['iw'], c['ih'],
                v['kg'], round(c['tara'], 2), round(v['valorU'], 2), c['nDes'], round(c['aBar'], 2), round(c['volMad'], 4), round(c['custoBRL'], 2))
            vid[v['seq']] = row['id']
        for b in r['est']['bins']:
            cont = await fetch1(conn, '''INSERT INTO conteiner (projeto_id,ordem,tipo,numero,lacre,cg_long_pct,cg_trans_pct,area_pct,sobrealtura_mm,deslocamento_mm)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                pid, b['ordem'], b['T'], b['numero'], b['lacre'], round(b['cogX'], 2), round(b['cogY'], 2), round(min(100, b['areaUso']), 2), b['oh'], b['desloc'])
            for n, it in enumerate(b['itens'], 1):
                for nivel, v in enumerate(it['u']['vols'], 1):
                    await conn.execute('''INSERT INTO alocacao (volume_id,conteiner_id,pilha_n,nivel,x_mm,y_mm,comp_mm,larg_mm,rotacionado)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (vid[v['seq']], cont['id'], n, nivel, it['x'], it['y'], it['l'], it['w'], it['rot']))
    # cotação: rascunho novo substitui rascunho anterior (aprovada permanece)
    await conn.execute("DELETE FROM cotacao WHERE projeto_id = %s AND status = 'RASCUNHO'", (pid,))
    ver = (await fetch1(conn, 'SELECT COALESCE(max(versao),0)+1 v FROM cotacao WHERE projeto_id = %s', pid))['v']
    k = r['cot']
    cot = await fetch1(conn, '''INSERT INTO cotacao (projeto_id,versao,incoterm,rota_id,cambio_usd_brl,seguro_pct,fob_usd,base_aduaneira_usd,tributos_usd,
        logistica_usd,vendedor_usd,comprador_usd) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
        pid, ver, p['incoterm'], p['rota_id'], p['cambio_usd_brl'], p['seguro_pct'], round(k['fob'], 2), round(k['base'], 2),
        round(k['trib'], 2), round(k['logistica'], 2), round(k['vendedor'], 2), round(k['comprador'], 2))
    for l in k['linhas']:
        await conn.execute('INSERT INTO cotacao_linha (cotacao_id,componente,conteiner_ordem,descricao,valor_usd,pagador) VALUES (%s,%s,%s,%s,%s,%s)',
                           (cot['id'], l['componente'], l['conteiner_ordem'], l['descricao'], l['valor_usd'], l['pagador']))
    # marcos: atualiza previsão, preserva realizado
    codigos = [m['codigo'] for m in r['marcos']]
    await conn.execute('DELETE FROM marco WHERE projeto_id = %s AND data_real IS NULL AND NOT (codigo = ANY(%s))', (pid, codigos))
    await conn.execute('UPDATE marco SET ordem = ordem + 100 WHERE projeto_id = %s', (pid,))
    for m in r['marcos']:
        await conn.execute('''INSERT INTO marco (projeto_id,ordem,codigo,descricao,fase,critico,data_prevista) VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (projeto_id,codigo) DO UPDATE SET ordem = EXCLUDED.ordem, descricao = EXCLUDED.descricao, fase = EXCLUDED.fase,
            critico = EXCLUDED.critico, data_prevista = EXCLUDED.data_prevista''',
            (pid, m['ordem'], m['codigo'], m['descricao'], m['fase'], m['critico'], m['data_prevista']))
    # documentos
    rota = r['rota']
    # documento cujo custo é do comprador no Incoterm vigente não é emitido pelo vendedor
    await conn.execute('''INSERT INTO documento (projeto_id,tipo,status) SELECT %s, codigo, 'PENDENTE' FROM ref_documento ON CONFLICT DO NOTHING''', (pid,))
    await conn.execute('''UPDATE documento d SET status = CASE
          WHEN d.tipo = 'CO' AND NOT %s THEN 'NAO_APLICA'
          WHEN r.componente_pagador IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ref_incoterm_componente ic
               WHERE ic.incoterm = %s AND ic.componente = r.componente_pagador) THEN 'NAO_APLICA'
          ELSE 'PENDENTE' END
        FROM ref_documento r WHERE r.codigo = d.tipo AND d.projeto_id = %s AND d.status <> 'EMITIDO' ''', (rota['exige_co'], p['incoterm'], pid))
    return dict(volumes=len(r['vols']), conteineres=[b['T'] for b in r['est']['bins']], cotacao_id=cot['id'],
                congelado=congelado, logistica_usd=round(k['logistica'], 2))

async def aprovar_cotacao(conn, pid, cid, aprovado_por, aprovado_em=None):
    await projeto_base(conn, pid, lock=True)
    c = await fetch1(conn, 'SELECT * FROM cotacao WHERE id = %s AND projeto_id = %s', cid, pid)
    if not c: raise LookupError('cotação não encontrada')
    await conn.execute("UPDATE cotacao SET status = 'SUBSTITUIDA' WHERE projeto_id = %s AND status = 'APROVADA'", (pid,))
    await conn.execute("UPDATE cotacao SET status = 'APROVADA', aprovado_por = %s, aprovado_em = %s WHERE id = %s",
                       (aprovado_por, aprovado_em or datetime.now(timezone.utc), cid))
    await conn.execute("""UPDATE documento SET status = 'EMITIDO', numero = %s, emitido_em = %s
        WHERE projeto_id = %s AND tipo = 'BOOKING' AND status = 'PENDENTE'""", (f'BKG-{pid:04d}-{cid}', aprovado_em or datetime.now(timezone.utc), pid))
    return await fetch1(conn, 'SELECT id, status, aprovado_por, aprovado_em FROM cotacao WHERE id = %s', cid)

async def dados_padrao(conn, p, etapa):
    """Payload EPCIS derivado do estado persistido."""
    pid = p['id']
    vols = await fetch(conn, 'SELECT seq, sscc, peso_liq_kg, peso_bruto_kg, ext_comp_mm, ext_larg_mm, ext_alt_mm FROM volume WHERE projeto_id = %s ORDER BY seq', pid)
    conts = await fetch(conn, 'SELECT * FROM vw_conteiner_carga WHERE projeto_id = %s ORDER BY ordem', pid)
    rota = await fetch1(conn, 'SELECT * FROM ref_rota WHERE id = %s', p['rota_id'])
    if etapa == 'PEDIDO':
        cot = await fetch1(conn, "SELECT fob_usd FROM cotacao WHERE projeto_id = %s ORDER BY versao DESC LIMIT 1", pid)
        return dict(ref=p['codigo'], consignatario=p['consignatario'], incoterm=f"{p['incoterm']} {rota['nome']}", fob_usd=cot and cot['fob_usd'])
    if etapa == 'PASSAPORTES': return dict(volumes=len(vols), sscc=[v['sscc'] for v in vols])
    if etapa == 'FAT': return dict(relatorio=f"FAT-{p['codigo']}", resultado='aprovado')
    if etapa == 'EMBALAGEM':
        pl = [dict(sscc=v['sscc'], gw=v['peso_bruto_kg'], nw=v['peso_liq_kg'], dim=f"{v['ext_comp_mm']}x{v['ext_larg_mm']}x{v['ext_alt_mm']}") for v in vols]
        return dict(packing_list_sha256=engine.sha256(json.dumps(pl, sort_keys=True)), volumes=len(vols), bruto_kg=round(sum(v['peso_bruto_kg'] for v in vols), 1))
    if etapa == 'ESTUFAGEM':
        out = []
        for c in conts:
            ss = [r['sscc'] for r in await fetch(conn, 'SELECT v.sscc FROM alocacao a JOIN volume v ON v.id = a.volume_id WHERE a.conteiner_id = %s ORDER BY v.seq', c['id'])]
            out.append(dict(conteiner=c['numero'], lacre=c['lacre'], tipo=c['tipo'], vgm_kg=round(c['vgm_kg']), volumes=len(ss), merkle_root=engine.merkle(ss)))
        return dict(conteineres=out)
    if etapa == 'DUE': return dict(due=f"26BR{pid:04d}{len(vols):04d}", nfe_cfop='7101')
    if etapa == 'GATE_IN': return dict(conteineres=[c['numero'] for c in conts], vgm_kg=[round(c['vgm_kg']) for c in conts])
    if etapa == 'EMBARQUE': return dict(porto=rota['porto_origem'])
    if etapa == 'EBL': return dict(bl=f"GPSBL{pid:04d}", tipo='eBL negociável', padrao='DCSA')
    if etapa == 'CHEGADA': return dict(porto=rota['porto_destino'])
    if etapa == 'DESEMBARACO': return dict(liberado=True)
    if etapa == 'ENTREGA': return dict(volumes_recebidos=len(vols), avarias=0)
    return {}

DOC_POR_ETAPA = {'FAT': ['FAT'], 'EMBALAGEM': ['INVOICE', 'PACKING', 'ISPM15'], 'DUE': ['NFE_DUE', 'CO'],
                 'GATE_IN': ['VGM'], 'EMBARQUE': ['SEGURO'], 'EBL': ['EBL'], 'DESEMBARACO': ['IMPORT']}

async def registrar_evento(conn, pid, etapa, registrado_por, ts=None, dados=None):
    p = await projeto_base(conn, pid, lock=True)
    if not etapa:
        prox = await fetch1(conn, '''SELECT e.codigo FROM ref_etapa e WHERE e.ordem = COALESCE((SELECT max(r.ordem) FROM ledger_evento l
               JOIN ref_etapa r ON r.codigo = l.etapa WHERE l.projeto_id = %s), 0) + 1''', pid)
        if not prox: raise ValueError('todas as etapas já foram registradas')
        etapa = prox['codigo']
    et = await fetch1(conn, 'SELECT * FROM ref_etapa WHERE codigo = %s', etapa)
    if not et: raise ValueError(f'etapa {etapa} inexistente')
    rota = await fetch1(conn, 'SELECT * FROM ref_rota WHERE id = %s', p['rota_id'])
    local = {'CHEGADA': rota['porto_destino'], 'DESEMBARACO': rota['porto_destino'], 'ENTREGA': 'Site do cliente — ' + rota['nome']}.get(etapa, et['local_padrao'])
    payload = {**await dados_padrao(conn, p, etapa), **(dados or {})}
    # ancoragem: o evento carrega o hash da versão vigente de cada documento anexado até aqui
    anexos = await fetch(conn, "SELECT tipo, hash_arquivo FROM documento WHERE projeto_id = %s AND hash_arquivo IS NOT NULL ORDER BY tipo", pid)
    if anexos: payload['documentos_sha256'] = {a['tipo']: a['hash_arquivo'] for a in anexos}
    ev = await fetch1(conn, '''INSERT INTO ledger_evento (projeto_id, seq, ts, etapa, tipo_epcis, biz_step, local, dados, registrado_por, prev_hash, hash)
        VALUES (%s, 0, %s, %s, '', '', %s, %s::jsonb, %s, ''::bytea, ''::bytea) RETURNING id, seq, etapa, ts, encode(hash,'hex') hash''',
        pid, ts or datetime.now(timezone.utc), etapa, local, json.dumps(payload, ensure_ascii=False), registrado_por)
    for tipo in DOC_POR_ETAPA.get(etapa, []):
        await conn.execute("""UPDATE documento SET status = 'EMITIDO', numero = %s, emitido_em = %s
            WHERE projeto_id = %s AND tipo = %s AND status = 'PENDENTE'""", (f'{tipo}-{p["codigo"][-7:]}', ev['ts'], pid, tipo))
    return ev

async def detalhe(conn, pid):
    p = await projeto_base(conn, pid)
    resumo = await fetch1(conn, 'SELECT * FROM vw_projeto_resumo WHERE id = %s', pid)
    return dict(
        projeto=p, resumo=resumo,
        cliente=await fetch1(conn, 'SELECT * FROM cliente WHERE id = %s', p['cliente_id']),
        itens=await fetch(conn, 'SELECT * FROM item_carga WHERE projeto_id = %s ORDER BY ordem', pid),
        volumes=await fetch(conn, '''SELECT v.*, i.codigo, i.tag, i.nome, i.ncm, i.embalagem, i.secoes, a.conteiner_id, a.x_mm, a.y_mm, a.comp_mm aloc_comp, a.larg_mm aloc_larg, a.nivel, a.pilha_n, a.rotacionado
            FROM volume v JOIN item_carga i ON i.id = v.item_id LEFT JOIN alocacao a ON a.volume_id = v.id WHERE v.projeto_id = %s ORDER BY v.seq''', pid),
        conteineres=await fetch(conn, 'SELECT * FROM vw_conteiner_carga WHERE projeto_id = %s ORDER BY ordem', pid),
        cotacoes=await fetch(conn, "SELECT * FROM cotacao WHERE projeto_id = %s AND status <> 'SUBSTITUIDA' ORDER BY versao DESC", pid),
        linhas=await fetch(conn, '''SELECT l.* FROM cotacao_linha l JOIN cotacao c ON c.id = l.cotacao_id
            WHERE c.projeto_id = %s AND c.status <> 'SUBSTITUIDA' ORDER BY l.cotacao_id, l.id''', pid),
        marcos=await fetch(conn, 'SELECT * FROM marco WHERE projeto_id = %s ORDER BY ordem', pid),
        ledger=await fetch(conn, '''SELECT seq, ts, etapa, tipo_epcis, biz_step, local, dados, registrado_por,
            encode(prev_hash,'hex') prev_hash, encode(hash,'hex') hash FROM ledger_evento WHERE projeto_id = %s ORDER BY seq''', pid),
        verificacao=await fetch(conn, 'SELECT * FROM fn_ledger_verificar(%s)', pid),
        documentos=await fetch(conn, '''SELECT d.*, r.nome, r.componente_pagador FROM documento d JOIN ref_documento r ON r.codigo = d.tipo
            WHERE d.projeto_id = %s ORDER BY r.ordem''', pid),
        arquivos=await fetch(conn, '''SELECT d.tipo, a.versao, a.nome_arquivo, a.mime, a.tamanho, a.sha256, a.enviado_por, a.enviado_em
            FROM documento_arquivo a JOIN documento d ON d.id = a.documento_id WHERE d.projeto_id = %s ORDER BY d.tipo, a.versao DESC''', pid))
