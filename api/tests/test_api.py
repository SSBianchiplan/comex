"""Testes de integração da API contra um banco semeado (python -m app.seed).
Uso: API_URL=http://localhost:8800 DATABASE_URL=postgresql://... pytest -q api/tests
Os testes que escrevem usam o projeto CMX-26-0147 (planejado); os demais só leem."""
import os, httpx, psycopg, pytest

API = os.getenv('API_URL', 'http://localhost:8800') + '/api'
DSN = os.getenv('DATABASE_URL', 'postgresql://comex_api:api@localhost:5432/gpscomex')
c = httpx.Client(timeout=30)
ITEM = {'codigo': 'X', 'tag': 'X', 'nome': 'X', 'qtd': 1, 'secoes': 1, 'comp_mm': 800, 'larg_mm': 600, 'alt_mm': 2000,
        'peso_kg': 200, 'valor_usd': 1, 'ncm': '8537.10.90', 'embalagem': 'crate', 'pilha_max': 1}

def pid(sufixo):
    return next(p['id'] for p in c.get(API + '/projetos').json() if p['codigo'].endswith(sufixo))

def test_saude():
    r = c.get(API + '/saude'); assert r.status_code == 200 and r.json()['ok'] and r.json()['projetos'] >= 3

def test_carteira_tres_estagios():
    est = {p['codigo']: p['estado'] for p in c.get(API + '/projetos').json()}
    assert est['CMX-26-0147'] not in ('ENTREGUE', 'CANCELADO') and est['CMX-26-0139'] in ('EMBARCADO', 'CHEGOU', 'DESEMBARACADO', 'ENTREGUE') and est['CMX-26-0121'] == 'ENTREGUE'

def test_ledger_integro_nos_tres():
    for s in ('0147', '0139', '0121'):
        v = c.get(f'{API}/projetos/{pid(s)}/ledger/verificar').json(); assert v['integro'] and v['blocos']

def test_detalhe_consistente():
    d = c.get(f'{API}/projetos/{pid("0139")}').json()
    assert len(d['volumes']) == 20 and all(v['conteiner_id'] for v in d['volumes'])
    assert sum(x['volumes'] for x in d['conteineres']) == 20 and len(d['ledger']) == 9

def test_referencias_serializa_vigencia():
    r = c.get(API + '/referencias'); assert r.status_code == 200 and r.json()['fretes'][0]['vigencia']['inicio']

def test_simular_valido_e_invalido():
    ok = c.post(API + '/simular', json={'rota_id': 'CLSAI', 'incoterm': 'CIP', 'cambio_usd_brl': 5.1, 'seguro_pct': 0.25,
                                        'entrega_alvo': '2027-03-01', 'dia_saida': 4, 'itens': [ITEM]})
    assert ok.status_code == 200 and ok.json()['volumes'] == 1
    assert c.post(API + '/simular', json={'rota_id': 'CLSAI'}).status_code == 422
    assert c.post(API + '/simular', json={'rota_id': 'XXXXX', 'incoterm': 'CIP', 'cambio_usd_brl': 5, 'seguro_pct': 0,
                                          'entrega_alvo': '2027-03-01', 'dia_saida': 4, 'itens': [ITEM]}).status_code == 422

def test_embarcado_recusa_alteracao_com_codigo_inv():
    r = c.put(f'{API}/projetos/{pid("0139")}/itens', json=[ITEM])
    assert r.status_code == 409 and 'INV-CMX-010' in r.json()['erro']
    r = c.patch(f'{API}/projetos/{pid("0139")}', json={'rota_id': 'USHOU'})
    assert r.status_code == 409 and 'INV-CMX-012' in r.json()['erro']

def test_etapa_fora_de_ordem():
    r = c.post(f'{API}/projetos/{pid("0121")}/ledger', json={'etapa': 'FAT', 'registrado_por': 'teste.api'})
    assert r.status_code == 409 and 'INV-CMX-011' in r.json()['erro']

def test_documento_inexistente_404():
    assert c.patch(f'{API}/projetos/{pid("0147")}/documentos/NAOEXISTE', json={'status': 'EMITIDO', 'numero': 'x'}).status_code == 404

def test_packing_list_csv():
    r = c.get(f'{API}/projetos/{pid("0139")}/packing-list.csv')
    assert r.status_code == 200 and r.text.count('\n') == 21 and 'SSCC' in r.text

def test_fluxo_aprovacao_e_evento():
    p = pid('0147'); d = c.get(f'{API}/projetos/{p}').json()
    if not any(x['status'] == 'APROVADA' for x in d['cotacoes']):
        assert c.post(f'{API}/projetos/{p}/ledger', json={'etapa': 'ESTUFAGEM', 'registrado_por': 'teste.api'}).status_code == 409
        rasc = next(x for x in d['cotacoes'] if x['status'] == 'RASCUNHO')
        assert c.post(f'{API}/projetos/{p}/cotacoes/{rasc["id"]}/aprovar', json={'aprovado_por': 'x'}).status_code == 422
        r = c.post(f'{API}/projetos/{p}/cotacoes/{rasc["id"]}/aprovar', json={'aprovado_por': 'teste.api@exportador.demo'})
        assert r.status_code == 200 and r.json()['status'] == 'APROVADA'
    antes = len(c.get(f'{API}/projetos/{p}').json()['ledger'])
    if antes < 3:
        r = c.post(f'{API}/projetos/{p}/ledger', json={'registrado_por': 'teste.api'}); assert r.status_code == 201 and len(r.json()['hash']) == 64
    assert c.get(f'{API}/projetos/{p}/ledger/verificar').json()['integro']

def test_papel_da_aplicacao_nao_altera_ledger():
    with psycopg.connect(DSN) as con:
        with pytest.raises(psycopg.Error):
            con.execute("UPDATE comex.ledger_evento SET local = 'x'")

# ---------- documentos com anexo ----------
import hashlib
PDF = b'%PDF-1.4\n% GPlanSiS|COMEX teste\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'

def test_anexo_hash_calculado_pelo_banco_e_download_integro():
    p = pid('0147')
    r = c.post(f'{API}/projetos/{p}/documentos/FAT/arquivos', files={'arquivo': ('relatorio FAT.pdf', PDF, 'application/pdf')})
    assert r.status_code == 201, r.text
    j = r.json(); assert j['sha256'] == hashlib.sha256(PDF).hexdigest() and j['versao'] >= 1
    d = c.get(f'{API}/projetos/{p}/documentos/FAT/arquivos/{j["versao"]}')
    assert d.status_code == 200 and d.content == PDF and d.headers['x-content-sha256'] == j['sha256']
    assert 'attachment' in d.headers['content-disposition']
    doc = next(x for x in c.get(f'{API}/projetos/{p}').json()['documentos'] if x['tipo'] == 'FAT')
    assert doc['hash_arquivo'] == j['sha256']

def test_anexo_recusa_conteudo_falso_tipo_e_tamanho():
    p = pid('0147')
    r = c.post(f'{API}/projetos/{p}/documentos/FAT/arquivos', files={'arquivo': ('nota.pdf', b'MZ\x90\x00executavel', 'application/pdf')})
    assert r.status_code == 409 and 'INV-CMX-028' in r.json()['erro']
    assert c.post(f'{API}/projetos/{p}/documentos/FAT/arquivos', files={'arquivo': ('x.html', b'<html>', 'text/html')}).status_code == 415
    grande = b'%PDF' + b'0' * (10 * 1024 * 1024)
    assert c.post(f'{API}/projetos/{p}/documentos/FAT/arquivos', files={'arquivo': ('g.pdf', grande, 'application/pdf')}).status_code == 413

def test_nova_versao_preserva_a_anterior():
    p = pid('0147'); outro = PDF.replace(b'teste', b'revisao')
    c.post(f'{API}/projetos/{p}/documentos/FAT/arquivos', files={'arquivo': ('v.pdf', PDF, 'application/pdf')})
    c.post(f'{API}/projetos/{p}/documentos/FAT/arquivos', files={'arquivo': ('v2.pdf', outro, 'application/pdf')})
    vs = [a for a in c.get(f'{API}/projetos/{p}').json()['arquivos'] if a['tipo'] == 'FAT']
    assert len(vs) >= 2 and vs[0]['sha256'] == hashlib.sha256(outro).hexdigest() and vs[0]['versao'] > vs[1]['versao']

def test_emissao_e_ancoragem_no_ledger():
    p = pid('0147')
    r = c.patch(f'{API}/projetos/{p}/documentos/INVOICE', json={'status': 'EMITIDO', 'numero': 'INV-2026-0147'})
    assert r.status_code == 200 and r.json()['emitido_por']
    c.post(f'{API}/projetos/{p}/documentos/INVOICE/arquivos', files={'arquivo': ('invoice.pdf', PDF, 'application/pdf')})
    led = c.get(f'{API}/projetos/{p}').json()['ledger']
    if len(led) < 12:
        ev = c.post(f'{API}/projetos/{p}/ledger', json={'registrado_por': 'teste.api'}); assert ev.status_code == 201, ev.text
        ult = c.get(f'{API}/projetos/{p}').json()['ledger'][-1]
        assert ult['dados']['documentos_sha256']['INVOICE'] == hashlib.sha256(PDF).hexdigest()
    assert c.patch(f'{API}/projetos/{p}/documentos/INVOICE', json={'status': 'PENDENTE'}).status_code == 409
