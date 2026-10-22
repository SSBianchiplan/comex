from contextlib import asynccontextmanager
import csv, io, json, urllib.parse
from datetime import date, datetime
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
import logging
import psycopg
from psycopg.types.range import Range
from .db import pool, fetch, fetch1, carregar_ref
from . import servico, engine
from .schemas import MAX_ITENS, _volumes, ProjetoIn, ProjetoPatch, ItemIn, ClienteIn, Aprovacao, EventoIn, DocumentoPatch, SimularIn, UsuarioIn, UsuarioPatch
from fastapi import Depends
from . import auth
from .auth import Usuario, LER, OPERAR, LOGISTICA, COMERCIAL, ADMIN
from . import usuarios
import os

@asynccontextmanager
async def ciclo(app):
    await pool.open(); yield; await pool.close()

app = FastAPI(title='GPlanSiS|COMEX API', version='1.2.0', lifespan=ciclo,
              description='Logística de exportação de painéis elétricos — embalagem, estufagem, cotação, cronograma e ledger EPCIS.')
# Em produção o nginx serve front e API na mesma origem: CORS fica fechado salvo lista explícita
_origens = [o.strip() for o in os.getenv('CORS_ORIGINS', '').split(',') if o.strip()]
if _origens:
    app.add_middleware(CORSMiddleware, allow_origins=_origens, allow_methods=['GET', 'POST', 'PUT', 'PATCH'], allow_headers=['Content-Type'])

@app.exception_handler(psycopg.Error)
async def erro_banco(req: Request, e: psycopg.Error):
    diag = getattr(e, 'diag', None); estado = getattr(e, 'sqlstate', None)
    msg = (diag.message_primary if diag and diag.message_primary else str(e)).strip()
    code = {'23514': 409, '23505': 409, '23503': 422, '23P01': 409, '42501': 403, '22P02': 422, 'P0001': 409}.get(estado, 500)
    if code == 500:   # erro interno: detalhes só no log, nunca para o cliente
        logging.getLogger('comex').error('erro de banco %s em %s %s: %s', estado, req.method, req.url.path, msg)
        return JSONResponse(status_code=500, content={'erro': 'erro interno no banco de dados'})
    return JSONResponse(status_code=code, content={'erro': msg, 'sqlstate': estado})
@app.exception_handler(LookupError)
async def nao_achado(req, e): return JSONResponse(status_code=404, content={'erro': str(e)})
@app.exception_handler(ValueError)
async def invalido(req, e): return JSONResponse(status_code=422, content={'erro': str(e)})

def enc(o):
    if isinstance(o, (date, datetime)): return o.isoformat()
    if isinstance(o, (bytes, memoryview)): return bytes(o).hex()
    if isinstance(o, Range): return {'inicio': o.lower, 'fim': o.upper}
    if isinstance(o, set): return sorted(o)
    raise TypeError(type(o))
def csv_seguro(v):
    """Neutraliza injeção de fórmula em planilhas (=, +, -, @, tab, CR no início da célula)."""
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + v
    return v

def J(d, status=200): return JSONResponse(status_code=status, content=json.loads(json.dumps(d, default=enc)))

@app.get('/api/saude')
async def saude():
    async with pool.connection() as c:
        r = await fetch1(c, "SELECT version() v, (SELECT count(*) FROM projeto) projetos")
    return {'ok': True, 'postgres': r['v'].split(',')[0], 'projetos': r['projetos']}

@app.get('/api/config')
async def config():
    return auth.config_publica()

@app.get('/api/eu')
async def eu(u: Usuario = Depends(auth.usuario_atual)):
    return {'login': u.login, 'nome': u.nome, 'email': u.email, 'papeis': sorted(u.papeis), 'auth': auth.MODO == 'oidc'}

@app.get('/api/referencias')
async def referencias(u: Usuario = Depends(LER)):
    async with pool.connection() as c:
        return J({k: await fetch(c, f'SELECT * FROM {t}') for k, t in {
            'tipos_conteiner': 'ref_tipo_conteiner ORDER BY pes, alt_int_mm', 'rotas': 'ref_rota ORDER BY nome',
            'fretes': "ref_rota_frete WHERE vigencia @> current_date", 'incoterms': 'ref_incoterm',
            'incoterm_componentes': 'ref_incoterm_componente', 'componentes': 'ref_componente_custo ORDER BY ordem',
            'custos': 'ref_custo_param', 'feriados': 'ref_feriado ORDER BY data', 'etapas': 'ref_etapa ORDER BY ordem',
            'estados': 'ref_estado ORDER BY ordem', 'embalagens': 'ref_tipo_embalagem', 'ncm': 'ref_ncm ORDER BY codigo',
            'documentos': 'ref_documento ORDER BY ordem'}.items()})

@app.get('/api/clientes')
async def clientes(u: Usuario = Depends(LER)):
    async with pool.connection() as c: return J(await fetch(c, 'SELECT * FROM cliente ORDER BY nome'))
@app.post('/api/clientes', status_code=201)
async def novo_cliente(x: ClienteIn, u: Usuario = Depends(COMERCIAL)):
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        return J(await fetch1(c, 'INSERT INTO cliente (nome,pais,cidade,segmento,contato) VALUES (%s,%s,%s,%s,%s) RETURNING *', x.nome, x.pais, x.cidade, x.segmento, x.contato), 201)

@app.get('/api/projetos')
async def projetos(u: Usuario = Depends(LER)):
    async with pool.connection() as c: return J(await fetch(c, 'SELECT * FROM vw_projeto_resumo ORDER BY entrega_alvo'))

@app.post('/api/projetos', status_code=201)
async def novo_projeto(x: ProjetoIn, u: Usuario = Depends(COMERCIAL)):
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        p = await fetch1(c, '''INSERT INTO projeto (codigo,titulo,cliente_id,consignatario,rota_id,incoterm,cambio_usd_brl,seguro_pct,entrega_alvo,dia_saida,parametros)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id''', x.codigo, x.titulo, x.cliente_id, x.consignatario, x.rota_id, x.incoterm,
            x.cambio_usd_brl, x.seguro_pct, x.entrega_alvo, x.dia_saida, json.dumps(x.parametros))
        await gravar_itens(c, p['id'], x.itens)
        calc = await servico.calcular(c, p['id']) if x.itens else None
        return J({'id': p['id'], 'calculo': calc}, 201)

@app.get('/api/projetos/{pid}')
async def projeto(pid: int, u: Usuario = Depends(LER)):
    async with pool.connection() as c: return J(await servico.detalhe(c, pid))

@app.patch('/api/projetos/{pid}')
async def alterar_projeto(pid: int, x: ProjetoPatch, u: Usuario = Depends(OPERAR)):
    campos = x.model_dump(exclude_none=True)
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        if campos:
            sets = ', '.join(f"{k} = %s{'::jsonb' if k == 'parametros' else ''}" for k in campos)
            vals = [json.dumps(v) if k == 'parametros' else v for k, v in campos.items()]
            await c.execute(f'UPDATE projeto SET {sets} WHERE id = %s', (*vals, pid))
        calc = await servico.calcular(c, pid)
        return J({'ok': True, 'calculo': calc})

async def gravar_itens(c, pid, itens: list[ItemIn]):
    await c.execute('DELETE FROM item_carga WHERE projeto_id = %s', (pid,))
    for i, it in enumerate(itens, 1):
        await c.execute('''INSERT INTO item_carga (projeto_id,ordem,codigo,tag,nome,qtd,secoes,comp_mm,larg_mm,alt_mm,peso_kg,valor_usd,ncm,embalagem,pilha_max)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (pid, i, it.codigo, it.tag, it.nome, it.qtd, it.secoes, it.comp_mm, it.larg_mm, it.alt_mm, it.peso_kg, it.valor_usd, it.ncm, it.embalagem, it.pilha_max))

@app.put('/api/projetos/{pid}/itens')
async def substituir_itens(pid: int, itens: list[ItemIn], u: Usuario = Depends(OPERAR)):
    if len(itens) > MAX_ITENS: raise ValueError(f'no máximo {MAX_ITENS} itens de carga')
    _volumes(itens)
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        await servico.projeto_base(c, pid, lock=True)
        await gravar_itens(c, pid, itens)
        return J({'ok': True, 'calculo': await servico.calcular(c, pid)})

@app.post('/api/projetos/{pid}/calcular')
async def recalcular(pid: int, u: Usuario = Depends(OPERAR)):
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        return J(await servico.calcular(c, pid))

@app.post('/api/projetos/{pid}/cotacoes/{cid}/aprovar')
async def aprovar(pid: int, cid: int, x: Aprovacao, u: Usuario = Depends(COMERCIAL)):
    quem = u.login if auth.MODO == 'oidc' else x.aprovado_por
    if not quem: raise ValueError('informe aprovado_por')
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        return J(await servico.aprovar_cotacao(c, pid, cid, quem, x.aprovado_em))

@app.post('/api/projetos/{pid}/ledger', status_code=201)
async def evento(pid: int, x: EventoIn, u: Usuario = Depends(LOGISTICA)):
    quem = u.login if auth.MODO == 'oidc' else x.registrado_por
    if not quem: raise ValueError('informe registrado_por')
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        return J(await servico.registrar_evento(c, pid, x.etapa, quem, x.ts if auth.MODO != 'oidc' else None, x.dados), 201)

@app.get('/api/projetos/{pid}/ledger/verificar')
async def verificar(pid: int, u: Usuario = Depends(LER)):
    async with pool.connection() as c:
        v = await fetch(c, 'SELECT * FROM fn_ledger_verificar(%s)', pid)
        return J({'integro': all(r['hash_ok'] and r['elo_ok'] for r in v), 'blocos': v})

@app.patch('/api/projetos/{pid}/documentos/{tipo}')
async def documento(pid: int, tipo: str, x: DocumentoPatch, u: Usuario = Depends(OPERAR)):
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        return J(await fetch1(c, '''UPDATE documento SET status = %s, numero = COALESCE(%s, numero),
            emitido_em = COALESCE(%s, emitido_em, CASE WHEN %s = 'EMITIDO' THEN now() END),
            emitido_por = CASE WHEN %s = 'EMITIDO' AND status <> 'EMITIDO' THEN %s ELSE emitido_por END
            WHERE projeto_id = %s AND tipo = %s RETURNING *''',
            x.status, x.numero, x.emitido_em, x.status, x.status, u.login, pid, tipo)
            or _nao_achou(f'documento {tipo} não encontrado'))

TIPOS_ARQUIVO = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.xml': 'application/xml',
                 '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                 '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
LIMITE = 10 * 1024 * 1024

@app.post('/api/projetos/{pid}/documentos/{tipo}/arquivos', status_code=201)
async def anexar(pid: int, tipo: str, arquivo: UploadFile = File(...), u: Usuario = Depends(OPERAR)):
    nome = os.path.basename((arquivo.filename or '').replace('\\', '/'))[:200]
    mime = TIPOS_ARQUIVO.get(os.path.splitext(nome)[1].lower())
    if not nome or not mime: raise HTTPException(415, 'tipo de arquivo não aceito (PDF, PNG, JPG, XML, XLSX ou DOCX)')
    dados = await arquivo.read(LIMITE + 1)
    if len(dados) > LIMITE: raise HTTPException(413, 'arquivo acima de 10 MB')
    quem = u.login if auth.MODO == 'oidc' else 'dev.local'
    async with pool.connection() as c, c.transaction():
        await auth.sessao(c, u)
        d = await fetch1(c, 'SELECT id FROM documento WHERE projeto_id = %s AND tipo = %s', pid, tipo) or _nao_achou(f'documento {tipo} não encontrado')
        r = await fetch1(c, '''INSERT INTO documento_arquivo (documento_id, versao, nome_arquivo, mime, tamanho, conteudo, sha256, enviado_por)
            VALUES (%s, 0, %s, %s, %s, %s, '', %s) RETURNING versao, nome_arquivo, mime, tamanho, sha256, enviado_por, enviado_em''',
            d['id'], nome, mime, len(dados), dados, quem)
        return J(r, 201)

@app.get('/api/projetos/{pid}/documentos/{tipo}/arquivos/{versao}')
async def baixar(pid: int, tipo: str, versao: int, u: Usuario = Depends(LER)):
    async with pool.connection() as c:
        cur = await c.execute('''SELECT a.nome_arquivo, a.mime, a.conteudo, a.sha256 FROM documento_arquivo a JOIN documento d ON d.id = a.documento_id
            WHERE d.projeto_id = %s AND d.tipo = %s AND a.versao = %s''', (pid, tipo, versao))
        r = await cur.fetchone()
    if not r: raise LookupError('arquivo não encontrado')
    return Response(content=bytes(r['conteudo']), media_type=r['mime'], headers={
        'Content-Disposition': f"attachment; filename*=UTF-8''{urllib.parse.quote(r['nome_arquivo'])}",
        'X-Content-SHA256': r['sha256'], 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

def _nao_achou(msg):
    raise LookupError(msg)

@app.get('/api/projetos/{pid}/packing-list.csv')
async def packing_csv(pid: int, u: Usuario = Depends(LER)):
    async with pool.connection() as c:
        p = await servico.projeto_base(c, pid)
        rows = await fetch(c, 'SELECT * FROM vw_packing_list WHERE projeto = %s ORDER BY seq', p['codigo'])
    buf = io.StringIO(); w = csv.writer(buf, delimiter=';')
    w.writerow(['Vol', 'TAG', 'Descrição', 'Seção', 'NCM', 'SSCC', 'C mm', 'L mm', 'A mm', 'Líquido kg', 'Tara kg', 'Bruto kg', 'm³', 'Contêiner', 'Tipo', 'Lacre'])
    for r in rows:
        w.writerow([csv_seguro(x) for x in [r['seq'], r['tag'], r['nome'], f"{r['secao_n']}/{r['secoes']}", r['ncm'], r['sscc'], r['ext_comp_mm'], r['ext_larg_mm'], r['ext_alt_mm'],
                    f"{r['peso_liq_kg']:.1f}".replace('.', ','), f"{r['tara_kg']:.1f}".replace('.', ','), f"{r['peso_bruto_kg']:.1f}".replace('.', ','),
                    f"{r['m3']:.3f}".replace('.', ','), r['conteiner'], r['tipo'], r['lacre']]])
    return StreamingResponse(iter(['\ufeff' + buf.getvalue()]), media_type='text/csv; charset=utf-8',
                             headers={'Content-Disposition': f'attachment; filename="packing-list-{p["codigo"]}.csv"'})

@app.post('/api/simular')
async def simular(x: SimularIn, u: Usuario = Depends(LER)):
    """Cálculo sem persistência (não grava nada)."""
    async with pool.connection() as c: ref = await carregar_ref(c)
    if x.rota_id not in ref.rotas: raise ValueError(f'rota {x.rota_id} inexistente')
    if x.incoterm not in ref.incoterms: raise ValueError(f'Incoterm {x.incoterm} inexistente')
    projeto = {**x.model_dump(exclude={'itens'}), 'id': 0}
    itens = [dict(i.model_dump(), ordem=n, id=None) for n, i in enumerate(x.itens, 1)]
    r = await run_in_threadpool(engine.calcular, projeto, itens, ref)   # não trava o laço de eventos
    return J({'volumes': len(r['vols']), 'sem_conteiner': len(r['est']['sem']),
              'conteineres': [dict(tipo=b['T'], volumes=len(b['vols']), carga_kg=round(b['kg']), sobrealtura_mm=b['oh']) for b in r['est']['bins']],
              'cotacao': r['cot'], 'marcos': r['marcos']})

# Gestão de usuários (Keycloak Admin API) — só comex-admin
@app.get('/api/usuarios')
async def lista_usuarios(u: Usuario = Depends(ADMIN)):
    return await usuarios.listar()

@app.post('/api/usuarios', status_code=201)
async def novo_usuario(x: UsuarioIn, u: Usuario = Depends(ADMIN)):
    return JSONResponse(status_code=201, content=await usuarios.criar(x.email, x.primeiro_nome, x.sobrenome, x.papeis))

@app.patch('/api/usuarios/{uid}')
async def altera_usuario(uid: str, x: UsuarioPatch, u: Usuario = Depends(ADMIN)):
    return await usuarios.alterar(uid, u, **x.model_dump(exclude_none=True))

@app.post('/api/usuarios/{uid}/senha')
async def senha_usuario(uid: str, u: Usuario = Depends(ADMIN)):
    return await usuarios.redefinir_senha(uid)

# Frontend PWA na mesma origem (opcional): se WEB_DIR existir, serve / depois das rotas /api
import os
from fastapi.staticfiles import StaticFiles
_web = os.getenv('WEB_DIR', os.path.join(os.path.dirname(__file__), '..', '..', 'web'))
if os.path.isdir(_web):
    app.mount('/', StaticFiles(directory=_web, html=True), name='web')
