"""Carga dos 3 projetos demo. Idempotente: não faz nada se já houver projetos.
Cada demo percorre o fluxo real (cálculo → aprovação humana → eventos) com datas coerentes,
e todas as escritas passam pelas mesmas regras do banco que a operação usa."""
import asyncio, json
from datetime import date, datetime, time, timedelta, timezone
from .db import pool, fetch, fetch1
from . import servico

BRT = timezone(timedelta(hours=-3))
I = lambda codigo, tag, nome, qtd, secoes, L, W, H, kg, valor, ncm, emb='crate', pilha=1: dict(
    codigo=codigo, tag=tag, nome=nome, qtd=qtd, secoes=secoes, comp_mm=L, larg_mm=W, alt_mm=H, peso_kg=kg, valor_usd=valor, ncm=ncm, embalagem=emb, pilha_max=pilha)

DEMOS = [
  dict(codigo='CMX-26-0147', titulo='Refinaria — pacote elétrico e automação', rota='USHOU', incoterm='DAP', entrega=date(2026, 12, 15),
       cliente=('ACME Process Industries LLC', 'EUA', 'Houston, TX', 'Óleo e gás'), consig='ACME PROCESS INDUSTRIES LLC', ate='PASSAPORTES', aprovar=False,
       itens=[I('CCM', 'CCM-01 / CCM-02', 'CCM — Centro de Controle de Motores', 2, 2, 2400, 600, 2300, 1350, 185000, '8537.10.90'),
              I('QGBT', 'QGBT-01 / QGBT-02', 'QGBT — Quadro Geral de Baixa Tensão', 2, 2, 1600, 1000, 2300, 1250, 160000, '8537.10.90'),
              I('RIO', 'RIO-01', 'Painel de Remota (I/O distribuído)', 1, 1, 800, 500, 2000, 220, 28000, '8537.10.90'),
              I('PLC', 'PLC-01', 'Painel PLC / CLP', 1, 1, 1600, 600, 2200, 480, 95000, '8537.10.20'),
              I('IHM', 'IHM-01 / IHM-02', 'Painéis IHM (console pedestal)', 2, 1, 800, 600, 1400, 140, 22000, '8537.10.90'),
              I('KIT', 'KIT-SP-01', 'Kit de componentes e sobressalentes', 1, 3, 1200, 800, 900, 780, 60000, '8538.90.90', 'caixa', 2),
              I('BAN', 'BAN-01 / BAN-02', 'Bancadas metálicas', 2, 1, 2000, 800, 900, 190, 6000, '9403.20.90', 'engradado', 2),
              I('MT', 'PMT-01', 'Painéis de Média Tensão 15 kV (6 cubículos)', 1, 3, 1500, 1600, 2350, 1500, 340000, '8537.20.90'),
              I('DJ', 'PMT-01-DJ', 'Disjuntores extraíveis MT (enviados à parte)', 1, 1, 1800, 1100, 1100, 950, 80000, '8535.21.00')]),
  dict(codigo='CMX-26-0139', titulo='Mineração de cobre — sala elétrica e acionamentos', rota='CLSAI', incoterm='CIP', entrega=date(2026, 10, 19),
       cliente=('Minera Andes Cobre SpA', 'Chile', 'Antofagasta', 'Mineração'), consig='MINERA ANDES COBRE SPA', ate='EBL', aprovar=True,
       itens=[I('CCM', 'CCM-11 / 12 / 13', 'CCM inteligente — moinhos e bombas', 3, 2, 2400, 600, 2300, 1400, 170000, '8537.10.90'),
              I('QGBT', 'QGBT-10', 'QGBT principal 4.000 A', 1, 3, 1600, 1000, 2300, 1300, 210000, '8537.10.90'),
              I('VFD', 'VFD-01 / VFD-02', 'Painel de inversores de média potência', 2, 1, 2400, 800, 2300, 1650, 145000, '8504.40.90'),
              I('MT', 'PMT-10', 'Painéis de Média Tensão 23 kV (4 cubículos)', 1, 2, 1600, 1700, 2300, 1600, 260000, '8537.20.90'),
              I('DJ', 'PMT-10-DJ', 'Disjuntores extraíveis MT', 1, 1, 1600, 1100, 1100, 700, 56000, '8535.21.00'),
              I('RIO', 'RIO-11 / RIO-12', 'Painéis de remota em campo', 2, 1, 800, 500, 2000, 230, 26000, '8537.10.90'),
              I('PLC', 'PLC-10', 'Painel PLC redundante', 1, 1, 1600, 600, 2200, 520, 118000, '8537.10.20'),
              I('IHM', 'IHM-10', 'Console IHM da sala de controle', 1, 1, 1600, 800, 1200, 180, 30000, '8537.10.90'),
              I('KIT', 'KIT-SP-10', 'Kit de sobressalentes de comissionamento', 1, 2, 1200, 800, 900, 650, 42000, '8538.90.90', 'caixa', 2)]),
  dict(codigo='CMX-26-0121', titulo='Planta química — atualização de automação', rota='NLRTM', incoterm='FCA', entrega=date(2026, 9, 14),
       cliente=('Nordzee Chemicals B.V.', 'Países Baixos', 'Rotterdam', 'Química'), consig='NORDZEE CHEMICALS B.V.', ate='ENTREGA', aprovar=True,
       itens=[I('PLC', 'PLC-21', 'Painel PLC com rede redundante', 1, 1, 1200, 600, 2000, 410, 88000, '8537.10.20'),
              I('RIO', 'RIO-21 / 22 / 23', 'Painéis de remota Ex (zona 2)', 3, 1, 800, 500, 2000, 210, 31000, '8537.10.90'),
              I('IHM', 'IHM-21 / IHM-22', 'Painéis IHM de campo', 2, 1, 800, 600, 1400, 130, 19000, '8537.10.90'),
              I('KIT', 'KIT-SP-21', 'Kit de componentes', 1, 2, 1200, 800, 900, 520, 24000, '8538.90.90', 'caixa', 2),
              I('BAN', 'BAN-21', 'Bancada metálica de manutenção', 1, 1, 2000, 800, 900, 180, 5200, '9403.20.90', 'engradado', 2)]),
]
ORDEM = ['PEDIDO', 'PASSAPORTES', 'FAT', 'EMBALAGEM', 'ESTUFAGEM', 'DUE', 'GATE_IN', 'EMBARQUE', 'EBL', 'CHEGADA', 'DESEMBARACO', 'ENTREGA']
MARCO = {'FAT': 'fat', 'EMBALAGEM': 'insp', 'ESTUFAGEM': 'estuf', 'DUE': 'estuf', 'GATE_IN': 'cut', 'EMBARQUE': 'etd', 'EBL': 'bl',
         'CHEGADA': 'eta', 'DESEMBARACO': 'lib', 'ENTREGA': 'ent'}
HORA = {'DUE': 15, 'EMBALAGEM': 17}

async def semear():
    await pool.open()
    try:
        await _semear()
    finally:
        await pool.close()   # sem fechar o pool o processo não termina e o compose espera o seed para sempre

async def _semear():
    async with pool.connection() as c:
        if (await fetch1(c, 'SELECT count(*) n FROM projeto'))['n']:
            print('seed: projetos já existem — nada a fazer'); return
        for d in DEMOS:
            async with c.transaction():
                cl = await fetch1(c, 'INSERT INTO cliente (nome,pais,cidade,segmento) VALUES (%s,%s,%s,%s) RETURNING id', *d['cliente'])
                p = await fetch1(c, '''INSERT INTO projeto (codigo,titulo,cliente_id,consignatario,rota_id,incoterm,cambio_usd_brl,seguro_pct,entrega_alvo,dia_saida)
                    VALUES (%s,%s,%s,%s,%s,%s,5.10,0.25,%s,4) RETURNING id''', d['codigo'], d['titulo'], cl['id'], d['consig'], d['rota'], d['incoterm'], d['entrega'])
                pid = p['id']
                for n, it in enumerate(d['itens'], 1):
                    await c.execute('''INSERT INTO item_carga (projeto_id,ordem,codigo,tag,nome,qtd,secoes,comp_mm,larg_mm,alt_mm,peso_kg,valor_usd,ncm,embalagem,pilha_max)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (pid, n, it['codigo'], it['tag'], it['nome'], it['qtd'], it['secoes'],
                        it['comp_mm'], it['larg_mm'], it['alt_mm'], it['peso_kg'], it['valor_usd'], it['ncm'], it['embalagem'], it['pilha_max']))
                calc = await servico.calcular(c, pid)
                marcos = {m['codigo']: m['data_prevista'] for m in await fetch(c, 'SELECT codigo, data_prevista FROM marco WHERE projeto_id = %s', pid)}
                agora = datetime.now(BRT)
                inicio = min(datetime.combine(marcos['cot'] - timedelta(days=14), time(9), BRT), agora - timedelta(minutes=5))
                if d['codigo'] == 'CMX-26-0147': inicio = agora - timedelta(minutes=5)
                for etapa in ORDEM[:ORDEM.index(d['ate']) + 1]:
                    if etapa == 'FAT' and d['aprovar']:
                        cot = await fetch1(c, "SELECT id FROM cotacao WHERE projeto_id = %s AND status = 'RASCUNHO'", pid)
                        await servico.aprovar_cotacao(c, pid, cot['id'], 'coord.logistica@exportador.demo', datetime.combine(marcos['book'], time(11), BRT))
                    ts = inicio + timedelta(minutes=ORDEM.index(etapa)) if etapa in ('PEDIDO', 'PASSAPORTES') else \
                         datetime.combine(marcos[MARCO[etapa]], time(HORA.get(etapa, 10)), BRT)
                    await servico.registrar_evento(c, pid, etapa, 'coord.logistica@exportador.demo', min(ts, agora))
                print(f"seed: {d['codigo']} → {calc['volumes']} volumes, {'+'.join(calc['conteineres'])}, até {d['ate']}")

if __name__ == '__main__':
    asyncio.run(semear())
