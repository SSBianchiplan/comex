"""Motor GPlanSiS|COMEX — domínio puro, sem framework nem banco (P5).
Recebe dados de referência como dicionários (carregados do PostgreSQL) e devolve
volumes, estufagem, cotação e cronograma. Determinístico: mesma entrada, mesma saída."""
from __future__ import annotations
import hashlib, json, math
from dataclasses import dataclass, field
from datetime import date, timedelta

PARAM_PADRAO = dict(fl=50, ft=50, tp=15, tt=18, skid=100, deck=25, densComp=600, densPinus=520, fe=0.35,
                    barreira='Al', umid=18, diasArm=90, a=6, e=0.7, mHigro=5, cHigro=10, uniDes=0.033,
                    margemPorta=60, folgaLat=40, folgaPorta=100)
PREFIXO_GS1 = '7890123'   # fictício (789 = GS1 Brasil)

# ------------------------------------------------------------------ identificação
def sscc(serial: int) -> str:
    base = '3' + PREFIXO_GS1 + str(serial).zfill(17 - 1 - len(PREFIXO_GS1))
    s = sum(int(base[16 - i]) * (3 if i % 2 == 0 else 1) for i in range(17))
    return base + str((10 - s % 10) % 10)

def iso6346_dv(p: str) -> int:
    tab, x = {}, 10
    for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        if x % 11 == 0: x += 1
        tab[ch] = x; x += 1
    s = sum((int(c) if c.isdigit() else tab[c]) * 2 ** i for i, c in enumerate(p[:10]))
    return (s % 11) % 10

def numero_conteiner(projeto_id: int, ordem: int) -> str:
    p = 'GPSU' + str(projeto_id * 100 + ordem).zfill(6)[-6:]
    return p + str(iso6346_dv(p))

def lacre(projeto_id: int, ordem: int) -> str:
    return 'BR' + str(2600000 + projeto_id * 100 + ordem).zfill(7)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def merkle(folhas: list[str]) -> str:
    if not folhas: return ''
    n = [sha256(f) for f in folhas]
    while len(n) > 1:
        n = [sha256(n[i] + (n[i + 1] if i + 1 < len(n) else n[i])) for i in range(0, len(n), 2)]
    return n[0]

# ------------------------------------------------------------------ embalagem
def embalar(it: dict, P: dict, emb: dict, custos: dict, tt_rota: int) -> dict:
    """Caixa ISPM-15: geometria real, tara por componente, dessecante DIN 55474."""
    m = lambda v: v / 1000
    il, iw, ih = it['comp_mm'] + 2 * P['fl'], it['larg_mm'] + 2 * P['fl'], it['alt_mm'] + P['ft']
    tw = P['tp']
    L, W, H = il + 2 * tw, iw + 2 * tw, ih + P['skid'] + P['deck'] + P['tt']
    a_par = 2 * m(L) * m(ih) + 2 * m(W) * m(ih)
    a_teto = m(L) * m(W)
    fa = float(emb['fator_abertura'])
    vol_painel = (a_par * m(tw) + a_teto * m(P['tt'])) * fa
    m_painel = vol_painel * P['densComp']
    m_estr = m_painel * P['fe']
    vol_deck = m(L) * m(W) * m(P['deck'])
    n_skid = 4 if W > 1200 else 3
    peso = float(it['peso_kg'])
    vol_skid = n_skid * m(L) * 0.1 * m(P['skid']) * (1.5 if peso > 2000 else 1)
    m_base = (vol_deck + vol_skid) * P['densPinus']
    a_bar = 2 * (m(il) * m(iw) + m(il) * m(ih) + m(iw) * m(ih)) * 1.15
    v_int = m(il) * m(iw) * m(ih)
    t_dias = tt_rota + P['diasArm'] + 20
    if emb['barreira']:
        wdd = 0.1 if P['barreira'] == 'Al' else 1.0
        n_des = math.ceil((1 / P['a']) * (v_int * P['umid'] + P['mHigro'] * P['cHigro'] + a_bar * P['e'] * wdd * t_dias))
        m_bar = a_bar * (0.13 if P['barreira'] == 'Al' else 0.05)
    else:
        n_des, m_bar = 0, a_bar * 0.04
    m_ferr = 0.03 * (m_painel + m_estr + m_base)
    tara = m_painel + m_estr + m_base + m_bar + n_des * P['uniDes'] + m_ferr
    vol_mad = vol_painel * (1 + P['fe']) + vol_deck + vol_skid
    custo = (vol_mad * custos['madeira_m3'] + custos['mao_caixa'] + n_des * custos['dessecante_un']
             + a_bar * (custos['barreira_m2'] if emb['barreira'] else custos['vci_m2']))
    return dict(L=round(L), W=round(W), H=round(H), il=il, iw=iw, ih=ih, tara=tara, bruto=peso + tara,
                m3=m(L) * m(W) * m(H), nDes=n_des, aBar=a_bar, volMad=vol_mad, custoBRL=custo,
                tDias=t_dias, Vint=v_int, cargaLin=peso / max(m(L), m(W)))

def gerar_volumes(projeto_id: int, itens: list[dict], P: dict, ref: 'Ref', tt: int) -> list[dict]:
    vols, n = [], 0
    for it in sorted(itens, key=lambda x: x['ordem']):
        for q in range(it['qtd']):
            for s in range(it['secoes']):
                n += 1
                cx = embalar(it, P, ref.embalagens[it['embalagem']], ref.custos, tt)
                vols.append(dict(seq=n, item_id=it.get('id'), codigo=it['codigo'], tag=it['tag'], nome=it['nome'],
                                 ncm=it['ncm'], eq=q + 1, sec=s + 1, secoes=it['secoes'], pilha=it['pilha_max'],
                                 kg=float(it['peso_kg']), valorU=float(it['valor_usd']) / it['secoes'],
                                 emb=it['embalagem'], cx=cx, sscc=sscc(projeto_id * 10000 + n)))
    return vols

# ------------------------------------------------------------------ estufagem
def unidades_carga(vols: list[dict], ref: 'Ref') -> list[dict]:
    out, grupos = [], {}
    for v in vols:
        if v['pilha'] > 1: grupos.setdefault(v['codigo'], []).append(v)
        else: out.append(dict(vols=[v], L=v['cx']['L'], W=v['cx']['W'], H=v['cx']['H'], kg=v['cx']['bruto'], id=v['codigo']))
    lim = ref.tipos['40HC']['alt_int_mm'] - 60
    for k, g in grupos.items():
        i = 0
        while i < len(g):
            col, h = [g[i]], g[i]['cx']['H']; i += 1
            while i < len(g) and len(col) < g[0]['pilha'] and h + g[i]['cx']['H'] <= lim:
                col.append(g[i]); h += g[i]['cx']['H']; i += 1
            out.append(dict(vols=col, L=col[0]['cx']['L'], W=col[0]['cx']['W'], H=h, kg=sum(v['cx']['bruto'] for v in col), id=k))
    return out

def cabe(u: dict, T: str, P: dict, ref: 'Ref') -> bool:
    C = ref.tipos[T]; mn, mx = min(u['L'], u['W']), max(u['L'], u['W'])
    if C['flat_rack']: return u['H'] <= 4200
    if mn > C['larg_int_mm'] - P['folgaLat'] or mx > C['comp_int_mm'] - P['folgaPorta']: return False
    if C['teto_aberto']: return u['H'] <= C['alt_int_mm'] + C['sobrealtura_max_mm']
    return u['H'] <= min(C['alt_int_mm'], C['porta_alt_mm']) - P['margemPorta'] and mn <= C['porta_larg_mm'] - P['margemPorta']

def classe(u, P, ref):
    for T in ('40HC', '40OT', '40FR'):
        if cabe(u, T, P, ref): return T
    return None

@dataclass
class Bin:
    T: str; L: int; W: int
    free: list = field(default_factory=list); itens: list = field(default_factory=list)
    kg: float = 0.0; maxH: int = 0

def novo_bin(T, P, ref):
    C = ref.tipos[T]
    W = C['larg_int_mm'] if C['flat_rack'] else C['larg_int_mm'] - P['folgaLat']
    L = C['comp_int_mm'] - P['folgaPorta']
    return Bin(T, L, W, free=[dict(x=0, y=0, w=L, h=W)])

def tentar(b: Bin, u: dict):
    best = None
    for f in b.free:
        for w, h, rot in ((u['L'], u['W'], False), (u['W'], u['L'], True)):
            if w <= f['w'] and h <= f['h']:
                sc = f['x'] * 10000 + f['y']
                if best is None or sc < best['sc']: best = dict(x=f['x'], y=f['y'], w=w, h=h, rot=rot, sc=sc)
    return best

def colocar(b: Bin, u: dict, p: dict):
    b.itens.append(dict(u=u, x=p['x'], y=p['y'], l=p['w'], w=p['h'], rot=p['rot']))
    b.kg += u['kg']; b.maxH = max(b.maxH, u['H'])
    nf = []
    for f in b.free:
        if p['x'] >= f['x'] + f['w'] or p['x'] + p['w'] <= f['x'] or p['y'] >= f['y'] + f['h'] or p['y'] + p['h'] <= f['y']:
            nf.append(f); continue
        if p['x'] > f['x']: nf.append(dict(x=f['x'], y=f['y'], w=p['x'] - f['x'], h=f['h']))
        if p['x'] + p['w'] < f['x'] + f['w']: nf.append(dict(x=p['x'] + p['w'], y=f['y'], w=f['x'] + f['w'] - p['x'] - p['w'], h=f['h']))
        if p['y'] > f['y']: nf.append(dict(x=f['x'], y=f['y'], w=f['w'], h=p['y'] - f['y']))
        if p['y'] + p['h'] < f['y'] + f['h']: nf.append(dict(x=f['x'], y=p['y'] + p['h'], w=f['w'], h=f['y'] + f['h'] - p['y'] - p['h']))
    def contido(a, i):
        for j, c in enumerate(nf):
            if j != i and a['x'] >= c['x'] and a['y'] >= c['y'] and a['x'] + a['w'] <= c['x'] + c['w'] and a['y'] + a['h'] <= c['y'] + c['h']:
                if a != c or j < i: return True
        return False
    b.free = [a for i, a in enumerate(nf) if not contido(a, i)]

def aceita(b: Bin, u, P, ref):
    C = ref.tipos[b.T]
    if b.kg + u['kg'] > C['payload_kg']: return None
    if C['teto_aberto']:
        if u['H'] > C['alt_int_mm'] + C['sobrealtura_max_mm']: return None
    elif not cabe(u, b.T, P, ref): return None
    return tentar(b, u)

def estufar(vols, P, ref):
    us = [dict(u, cls=classe(u, P, ref)) for u in unidades_carga(vols, ref)]
    sem = [u for u in us if not u['cls']]
    ordk = lambda u: (-(u['L'] * u['W']), -u['kg'])
    bins: list[Bin] = []
    for T in ('40FR', '40OT', '40HC'):
        for u in sorted([u for u in us if u['cls'] == T], key=ordk):
            ok = False
            for b in bins:
                p = aceita(b, u, P, ref)
                if p: colocar(b, u, p); ok = True; break
            if not ok:
                b = novo_bin(T, P, ref); p = aceita(b, u, P, ref)
                if p: colocar(b, u, p); bins.append(b)
                else: sem.append(u)
    for i, b in enumerate(bins):                       # rebaixa 40HC → 20DV / 40DV
        if b.T != '40HC': continue
        for T in ('20DV', '40DV'):
            if not all(cabe(it['u'], T, P, ref) for it in b.itens): continue
            nb, ok = novo_bin(T, P, ref), True
            for it in sorted(b.itens, key=lambda it: ordk(it['u'])):
                p = aceita(nb, it['u'], P, ref)
                if not p: ok = False; break
                colocar(nb, it['u'], p)
            if ok: bins[i] = nb; break
    out = []
    for b in bins:
        C = ref.tipos[b.T]
        usadoX = max(it['x'] + it['l'] for it in b.itens); usadoY = max(it['y'] + it['w'] for it in b.itens)
        cx0 = sum(it['u']['kg'] * (it['x'] + it['l'] / 2) for it in b.itens) / b.kg
        cy0 = sum(it['u']['kg'] * (it['y'] + it['w'] / 2) for it in b.itens) / b.kg
        dx = round(max(0, min(b.L - usadoX, C['comp_int_mm'] / 2 - cx0)))
        dy = round(max(0, min(b.W - usadoY, b.W / 2 - cy0)))
        for it in b.itens: it['x'] += dx; it['y'] += dy
        cx = cx0 + dx; cy = cy0 + dy
        oh = max(0, b.maxH - C['alt_int_mm']) if (C['teto_aberto'] and not C['flat_rack']) else 0
        vs = [v for it in b.itens for v in it['u']['vols']]
        out.append(dict(T=b.T, L=b.L, W=b.W, itens=b.itens, kg=b.kg, maxH=b.maxH, desloc=dx, deslocY=dy,
                        cogX=(cx - C['comp_int_mm'] / 2) / C['comp_int_mm'] * 100, cogY=(cy - b.W / 2) / b.W * 100,
                        areaUso=sum(it['l'] * it['w'] for it in b.itens) / (C['comp_int_mm'] * C['larg_int_mm']) * 100,
                        pesoUso=b.kg / C['payload_kg'] * 100, oh=oh,
                        oogW=bool(C['flat_rack'] and any(it['w'] > C['larg_int_mm'] for it in b.itens)),
                        vols=vs, m3=sum(v['cx']['m3'] for v in vs), vgm=b.kg + C['tara_kg']))
    return dict(bins=out, sem=sem)

# ------------------------------------------------------------------ cotação
COMPONENTES = ['emb', 'carg', 'rodo', 'despE', 'thcO', 'frete', 'seg', 'thcD', 'entrega', 'desc', 'despI', 'trib']

def cotar(bins, vols, rota, incoterm, fx, seguro_pct, ref):
    K = ref.custos; fx = float(fx)
    fob = sum(v['valorU'] for v in vols)
    linhas = []
    def add(comp, desc, usd, ordem=None): linhas.append(dict(componente=comp, descricao=desc, valor_usd=round(usd, 2), conteiner_ordem=ordem))
    add('emb', f'{len(vols)} caixas ISPM-15', sum(v['cx']['custoBRL'] for v in vols) / fx)
    frete_tot = 0
    for i, b in enumerate(bins, 1):
        C = ref.tipos[b['T']]; p = C['pes']; esp = C['teto_aberto']
        fr = ref.fretes[(rota['id'], b['T'])]
        mar = fr + K[f'baf_{p}'] + (K['oog_altura'] if b['oh'] > 0 else 0) + (K['oog_largura'] if b['oogW'] else 0) + K['isps']
        frete_tot += mar
        add('carg', f"{b['T']} #{i}", (K['estuf_esp'] if esp else K[f'estuf_{p}']) / fx, i)
        rk = 'rodo_FR' if C['flat_rack'] else 'rodo_OT' if esp else f'rodo_{p}'
        add('rodo', f"{b['T']} #{i}", K[rk] / fx, i)
        add('thcO', f"{b['T']} #{i}", (K['thcO_esp'] if esp else K[f'thcO_{p}']) / fx, i)
        add('frete', f"{b['T']} #{i} — base {fr:.0f} + BAF/EFS + ISPS" + (' + OOG' if b['oh'] or b['oogW'] else ''), mar, i)
        add('thcD', f"{b['T']} #{i}", K[f'thcD_{p}'] * (K['fator_esp_dest'] if esp else 1), i)
        add('entrega', f"{b['T']} #{i}", K['entrega_esp'] if esp else K[f'entrega_{p}'], i)
    add('frete', 'Emissão de B/L', K['bl']); frete_tot += K['bl']
    add('despE', 'Despachante + DU-E' + (' + certificado de origem' if rota['exige_co'] else ''), (K['desp_br'] + (K['co_br'] if rota['exige_co'] else 0)) / fx)
    seg = (fob + frete_tot) * 1.1 * float(seguro_pct) / 100
    add('seg', f'{float(seguro_pct):.2f}% sobre 110% CIF', seg)
    add('despI', 'Despachante no destino', K['desp_dest'])
    base = fob if rota['base_aduaneira'] == 'FOB' else fob + frete_tot + seg
    trib = base * float(rota['tributo_pct']) / 100
    add('trib', f"{float(rota['tributo_pct']):.1f}% sobre base {rota['base_aduaneira']}", trib)
    vend_set = ref.incoterms[incoterm]
    for l in linhas: l['pagador'] = 'VENDEDOR' if l['componente'] in vend_set else 'COMPRADOR'
    logistica = sum(l['valor_usd'] for l in linhas if l['componente'] != 'trib')
    vendedor = sum(l['valor_usd'] for l in linhas if l['pagador'] == 'VENDEDOR')
    comprador = sum(l['valor_usd'] for l in linhas if l['pagador'] == 'COMPRADOR')
    return dict(linhas=linhas, fob=fob, base=base, trib=trib, logistica=logistica, vendedor=vendedor, comprador=comprador)

# ------------------------------------------------------------------ cronograma
def cronograma(entrega: date, dia_saida: int, rota: dict, n_vols: int, esp: bool, feriados: set[date]) -> list[dict]:
    util = lambda d: d.isoweekday() < 6 and d not in feriados
    def wd_back(d, n):
        while n > 0:
            d -= timedelta(days=1)
            if util(d): n -= 1
        return d
    def wd_fwd(d, n):
        while n > 0:
            d += timedelta(days=1)
            if util(d): n -= 1
        return d
    def prox_util(d):
        while not util(d): d += timedelta(days=1)
        return d
    tt, tb = rota['transito_dias'], 4 if rota['transbordo'] else 0
    etd = entrega - timedelta(days=tt + tb + 5 + 2 + 3)
    while etd.isoweekday() != dia_saida: etd -= timedelta(days=1)
    eta = etd + timedelta(days=tt + tb); lib = prox_util(eta + timedelta(days=5)); ent = wd_fwd(lib, 2)
    cut = wd_back(etd, 2); draft = wd_back(etd, 3); estuf = wd_back(cut, 1); insp = wd_back(estuf, 1)
    emb_d = max(3, math.ceil(n_vols / 4)); emb_ini = wd_back(insp, emb_d)
    fat = wd_back(emb_ini, 1); cx = wd_back(emb_ini, 6)
    book = etd - timedelta(days=28 if esp else 21); cot = book - timedelta(days=7)
    M = [('cot', cot, 'Cotação e contratação do frete (NVOCC/armador)', 'PRE', True),
         ('book', book, 'Booking confirmado' + (' — equipamento especial exige 4 semanas' if esp else ''), 'PRE', True),
         ('cx', cx, 'Pedido de caixas ISPM-15 (madeira HT, carimbo IPPC)', 'PRE', False),
         ('fat', fat, 'FAT concluído e liberação de qualidade', 'PRE', True),
         ('emb', emb_ini, f'Início da embalagem ({emb_d} dias úteis, {n_vols} volumes)', 'PRE', False),
         ('insp', insp, 'Inspeção de embalagem, fotos e indicadores de choque/inclinação', 'PRE', False),
         ('estuf', estuf, 'Estufagem na fábrica, peação, lacre + NF-e e registro da DU-E', 'PRE', True),
         ('draft', draft, 'Deadline draft (instrução de embarque / SI)', 'PRE', False),
         ('cut', cut, 'Cut-off de carga e VGM (SOLAS) no terminal', 'PRE', True),
         ('etd', etd, 'ETD — saída do navio em Portonave, Navegantes/SC', 'MAR', True),
         ('bl', etd + timedelta(days=2), 'Emissão do eBL (padrão DCSA) e envio de documentos', 'MAR', False)]
    if rota['transbordo']: M.append(('tb', etd + timedelta(days=round(tt / 2)), 'Transbordo (hub)', 'MAR', False))
    M += [('eta', eta, 'ETA — chegada em ' + rota['porto_destino'], 'MAR', True),
          ('lib', lib, 'Desembaraço de importação e liberação do terminal', 'POS', False),
          ('ent', ent, 'Entrega no site do cliente', 'POS', True)]
    return [dict(ordem=i + 1, codigo=c, data_prevista=d, descricao=t, fase=f, critico=cr) for i, (c, d, t, f, cr) in enumerate(M)]

# ------------------------------------------------------------------ referência
@dataclass
class Ref:
    tipos: dict; embalagens: dict; rotas: dict; fretes: dict; incoterms: dict; custos: dict; feriados: set

def calcular(projeto: dict, itens: list[dict], ref: Ref) -> dict:
    P = {**PARAM_PADRAO, **(projeto.get('parametros') or {})}
    rota = ref.rotas[projeto['rota_id']]
    vols = gerar_volumes(projeto['id'], itens, P, ref, rota['transito_dias'])
    est = estufar(vols, P, ref)
    for i, b in enumerate(est['bins'], 1):
        b['ordem'] = i; b['numero'] = numero_conteiner(projeto['id'], i); b['lacre'] = lacre(projeto['id'], i)
    cot = cotar(est['bins'], vols, rota, projeto['incoterm'], projeto['cambio_usd_brl'], projeto['seguro_pct'], ref)
    esp = any(ref.tipos[b['T']]['teto_aberto'] for b in est['bins'])
    marcos = cronograma(projeto['entrega_alvo'], projeto['dia_saida'], rota, len(vols), esp, ref.feriados)
    return dict(P=P, vols=vols, est=est, cot=cot, marcos=marcos, rota=rota)
