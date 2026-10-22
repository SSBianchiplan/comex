import os
from decimal import Decimal
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from .engine import Ref

DSN = os.getenv('DATABASE_URL', 'postgresql://comex:comex@localhost:5432/gpscomex')
pool = AsyncConnectionPool(DSN, min_size=1, max_size=10, open=False,
                           kwargs={'row_factory': dict_row, 'options': '-c search_path=comex,public -c lock_timeout=5s'})

def num(r: dict) -> dict:
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()}

async def fetch(conn, sql, *args):
    cur = await conn.execute(sql, args or None)
    return [num(r) for r in await cur.fetchall()]

async def fetch1(conn, sql, *args):
    r = await fetch(conn, sql, *args)
    return r[0] if r else None

async def carregar_ref(conn) -> Ref:
    ref = Ref(
        tipos={r['codigo']: r for r in await fetch(conn, 'SELECT * FROM ref_tipo_conteiner')},
        embalagens={r['codigo']: r for r in await fetch(conn, 'SELECT * FROM ref_tipo_embalagem')},
        rotas={r['id']: r for r in await fetch(conn, 'SELECT * FROM ref_rota')},
        fretes={(r['rota_id'], r['tipo_conteiner']): r['frete_usd'] for r in
                await fetch(conn, 'SELECT * FROM ref_rota_frete WHERE vigencia @> current_date')},
        incoterms={}, custos={r['chave']: r['valor'] for r in await fetch(conn, 'SELECT * FROM ref_custo_param')},
        feriados={r['data'] for r in await fetch(conn, 'SELECT data FROM ref_feriado')})
    for r in await fetch(conn, 'SELECT * FROM ref_incoterm_componente'):
        ref.incoterms.setdefault(r['incoterm'], set()).add(r['componente'])
    return ref
