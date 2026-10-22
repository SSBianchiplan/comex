"""Correções da auditoria de 2026-10: limites contra DoS de cálculo (M18), padrão oidc, CSV sem fórmula,
realm sem reset de senha e sem redirect fixo para localhost. Os testes marcados com `api` usam a API no ar
(API_URL, como test_api.py); os demais são unitários."""
import importlib, json, os, pathlib
import httpx, pytest
from pydantic import ValidationError

from app import schemas

RAIZ = pathlib.Path(__file__).resolve().parents[2]
API = os.getenv('API_URL', 'http://localhost:8800') + '/api'
ITEM = {'codigo': 'X', 'tag': 'X', 'nome': 'X', 'qtd': 1, 'secoes': 1, 'comp_mm': 800, 'larg_mm': 600, 'alt_mm': 2000,
        'peso_kg': 200, 'valor_usd': 1, 'ncm': '8537.10.90', 'embalagem': 'crate', 'pilha_max': 1}
SIM = {'rota_id': 'CLSAI', 'incoterm': 'CIP', 'cambio_usd_brl': 5.1, 'seguro_pct': 0.25, 'entrega_alvo': '2027-03-01', 'dia_saida': 4}

def sim(**kw): return {**SIM, 'itens': [ITEM], **kw}

# ---------------------------------------------------------------- unitários
def test_limites_de_carga():
    schemas.SimularIn(**sim(itens=[{**ITEM, 'qtd': 30, 'secoes': 20}]))                       # 600 volumes: no limite
    for ruim in ({**ITEM, 'qtd': 31, 'secoes': 20},                                            # 620 volumes
                 {**ITEM, 'qtd': 201},                                                         # qtd acima do teto
                 {**ITEM, 'nome': 'x' * 201}):                                                 # texto longo
        with pytest.raises(ValidationError): schemas.SimularIn(**sim(itens=[ruim]))
    with pytest.raises(ValidationError): schemas.SimularIn(**sim(itens=[ITEM] * 101))          # itens demais
    with pytest.raises(ValidationError): schemas.ProjetoIn(codigo='CMX-26-9999', titulo='t', cliente_id=1, consignatario='c',
                                                           **SIM, itens=[{**ITEM, 'qtd': 200, 'secoes': 20}])

def test_parametros_do_motor():
    assert schemas.SimularIn(**sim(parametros={'fl': 0, 'a': 6.5, 'barreira': 'PE'})).parametros['barreira'] == 'PE'
    for ruim in ({'a': 0}, {'fl': -1}, {'fl': 1e9}, {'fl': True}, {'fl': 'x'}, {'barreira': 'Zn'}, {'__class__': 1},
                 {'fl': float('nan')}):
        with pytest.raises(ValidationError): schemas.SimularIn(**sim(parametros=ruim))
    with pytest.raises(ValidationError): schemas.ProjetoPatch(parametros={'desconhecido': 1})

def test_auth_mode_padrao_e_oidc(monkeypatch):
    from app import auth
    try:
        monkeypatch.delenv('AUTH_MODE', raising=False); importlib.reload(auth)
        assert auth.MODO == 'oidc' and auth.config_publica()['auth'] is True
        monkeypatch.setenv('AUTH_MODE', 'aberto')
        with pytest.raises(RuntimeError): importlib.reload(auth)
    finally:
        monkeypatch.setenv('AUTH_MODE', 'desligado'); importlib.reload(auth)

def test_csv_sem_formula():
    from app.main import csv_seguro
    assert [csv_seguro(v) for v in ('=HYPERLINK("x")', '+1', '-1', '@SUM(A1)', '\tx', 'CCM-01', 7)] == \
           ["'=HYPERLINK(\"x\")", "'+1", "'-1", "'@SUM(A1)", "'\tx", 'CCM-01', 7]

def test_realm_sem_reset_e_sem_localhost_fixo():
    realm = json.loads((RAIZ / 'keycloak' / 'realm-gplansis.json').read_text())
    assert realm['resetPasswordAllowed'] is False and realm['bruteForceProtected'] is True
    web = next(c for c in realm['clients'] if c['clientId'] == 'comex-web')
    assert not [u for u in web['redirectUris'] if u.startswith('http://localhost')]

def test_imagens_corrigidas():
    compose = (RAIZ / 'docker-compose.yml').read_text()
    assert 'quay.io/keycloak/keycloak:26.7.5' in compose and '26.0.7' not in compose
    assert (RAIZ / 'web' / 'Dockerfile').read_text().startswith('FROM nginx:1.30.')
    req = (RAIZ / 'api' / 'requirements.txt').read_text()
    assert 'starlette==1.9.0' in req and 'certifi==2026.10.19' in req and '*' not in req

# ---------------------------------------------------------------- API no ar
def _api():
    try: return httpx.get(API + '/saude', timeout=3).status_code == 200
    except httpx.HTTPError: return False

api = pytest.mark.skipif(not _api(), reason='API fora do ar (API_URL)')

@api
def test_simular_recusa_carga_gigante():
    c = httpx.Client(timeout=30)
    assert c.post(API + '/simular', json=sim(itens=[{**ITEM, 'qtd': 200, 'secoes': 20}] * 100)).status_code == 422
    assert c.post(API + '/simular', json=sim(parametros={'a': 0})).status_code == 422
    r = c.post(API + '/simular', json=sim(itens=[{**ITEM, 'qtd': 30, 'secoes': 20}]))
    assert r.status_code == 200 and r.json()['volumes'] == 600

@api
def test_put_itens_limitado():
    c = httpx.Client(timeout=30)
    p = next(p['id'] for p in c.get(API + '/projetos').json() if p['codigo'] == 'CMX-26-0147')
    assert c.put(f'{API}/projetos/{p}/itens', json=[{**ITEM, 'qtd': 31, 'secoes': 20}]).status_code == 422
    assert c.put(f'{API}/projetos/{p}/itens', json=[ITEM] * 101).status_code == 422
