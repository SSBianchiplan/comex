"""Testes unitários do gerenciador de usuários contra um Keycloak falso em memória (httpx.MockTransport).
Cobrem criação com senha temporária, filtro de papéis, proteção da própria conta e ocultação de service accounts."""
import asyncio, importlib, json, os, uuid
import httpx, pytest
from fastapi import HTTPException

class FakeKC:
    def __init__(self):
        self.users = {}; self.roles = {}; self.chamadas = []
        self.add('service-account-comex-admin-api', [])
    def add(self, login, papeis, **kw):
        uid = str(uuid.uuid4()); self.users[uid] = {'id': uid, 'username': login, 'enabled': True, **kw}
        self.roles[uid] = set(papeis); return uid
    def __call__(self, req: httpx.Request):
        p = req.url.path.split('/admin/realms/gplansis')[-1]; m = req.method
        self.chamadas.append((m, p))
        if p.endswith('/openid-connect/token'):
            return httpx.Response(200, json={'access_token': 't', 'expires_in': 300})
        corpo = json.loads(req.content) if req.content else None
        if p == '/users' and m == 'GET': return httpx.Response(200, json=list(self.users.values()))
        if p == '/users' and m == 'POST':
            if any(u['username'] == corpo['username'] for u in self.users.values()): return httpx.Response(409, json={})
            uid = self.add(corpo['username'], [], **{k: v for k, v in corpo.items() if k not in ('username', 'credentials')})
            self.users[uid]['_cred'] = corpo['credentials']
            return httpx.Response(201, headers={'Location': f'http://kc/admin/realms/gplansis/users/{uid}'})
        partes = p.strip('/').split('/')
        if partes[0] == 'roles' and len(partes) == 2: return httpx.Response(200, json={'id': partes[1], 'name': partes[1]})
        if partes[0] == 'roles' and partes[2] == 'users':
            return httpx.Response(200, json=[self.users[u] for u, r in self.roles.items() if partes[1] in r])
        uid = partes[1]
        if uid not in self.users: return httpx.Response(404, json={})
        if len(partes) == 2 and m == 'GET': return httpx.Response(200, json=self.users[uid])
        if len(partes) == 2 and m == 'PUT': self.users[uid].update(corpo); return httpx.Response(204)
        if partes[2] == 'role-mappings':
            if m == 'GET': return httpx.Response(200, json=[{'name': r} for r in self.roles[uid]])
            nomes = {r['name'] for r in corpo}
            self.roles[uid] = self.roles[uid] | nomes if m == 'POST' else self.roles[uid] - nomes
            return httpx.Response(204)
        if partes[2] in ('logout', 'reset-password'): return httpx.Response(204)
        return httpx.Response(400)

@pytest.fixture
def ctx(monkeypatch):
    os.environ.update(KC_ADMIN_SECRET='s', KC_INTERNO_URL='http://kc')
    from app import usuarios as m; importlib.reload(m)
    kc = FakeKC(); real = httpx.AsyncClient
    monkeypatch.setattr(m.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(kc), **kw))
    yield m, kc
    os.environ.pop('KC_ADMIN_SECRET'); importlib.reload(m)

def adm(login='chefe@x.com'):
    from app.auth import Usuario
    return Usuario(login=login, nome='Chefe', papeis={'comex-admin'})

def test_criar_com_senha_temporaria_e_papeis(ctx):
    m, kc = ctx
    r = asyncio.run(m.criar('Ana@X.com', 'Ana', 'Souza', ['comex-leitura', 'comex-logistica']))
    assert r['login'] == 'ana@x.com' and r['papeis'] == ['comex-leitura', 'comex-logistica']
    assert len(r['senha_temporaria']) == 16 and kc.users[r['id']]['_cred'][0]['temporary'] is True
    assert kc.users[r['id']]['requiredActions'] == ['UPDATE_PASSWORD']

def test_papel_fora_do_comex_recusado(ctx):
    m, _ = ctx
    with pytest.raises(ValueError): asyncio.run(m.criar('b@x.com', 'B', '', ['realm-admin']))

def test_email_duplicado_409(ctx):
    m, kc = ctx; kc.add('c@x.com', [])
    with pytest.raises(HTTPException) as e: asyncio.run(m.criar('c@x.com', 'C', '', []))
    assert e.value.status_code == 409

def test_lista_esconde_service_account(ctx):
    m, kc = ctx; kc.add('d@x.com', ['comex-leitura'], firstName='Dora')
    assert [u['login'] for u in asyncio.run(m.listar())] == ['d@x.com']

def test_nao_desativa_nem_rebaixa_a_si_mesmo(ctx):
    m, kc = ctx; uid = kc.add('chefe@x.com', ['comex-admin'])
    with pytest.raises(ValueError): asyncio.run(m.alterar(uid, adm(), ativo=False))
    with pytest.raises(ValueError): asyncio.run(m.alterar(uid, adm(), papeis=['comex-leitura']))

def test_desativar_outro_derruba_sessao_e_troca_papeis(ctx):
    m, kc = ctx; uid = kc.add('e@x.com', ['comex-leitura'])
    r = asyncio.run(m.alterar(uid, adm(), ativo=False, papeis=['comex-comercial']))
    assert r['ativo'] is False and r['papeis'] == ['comex-comercial'] and ('POST', f'/users/{uid}/logout') in kc.chamadas

def test_redefinir_senha_e_404(ctx):
    m, kc = ctx; uid = kc.add('f@x.com', [])
    assert len(asyncio.run(m.redefinir_senha(uid))['senha_temporaria']) == 16
    with pytest.raises(LookupError): asyncio.run(m.redefinir_senha('nao-existe'))
