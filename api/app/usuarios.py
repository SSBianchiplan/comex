"""Gestão de usuários do COMEX pela Admin API do Keycloak (papel comex-admin).

A API fala com o Keycloak pela rede interna, como o cliente confidencial comex-admin-api
(service account com manage-users/view-users/query-users/view-realm do realm-management).
Só os papéis COMEX podem ser atribuídos: nada de realm-management nem papéis do master.
A senha criada ou redefinida é temporária (UPDATE_PASSWORD no primeiro acesso) e volta
uma única vez na resposta, para o administrador entregar ao usuário."""
import os, secrets, string, time
import httpx
from fastapi import HTTPException
from .auth import PAPEIS, Usuario

BASE = os.getenv('KC_INTERNO_URL', 'http://keycloak:8080').rstrip('/')        # inclui o relative path, se houver
REALM = os.getenv('KC_REALM', 'gplansis')
CLIENTE = os.getenv('KC_ADMIN_CLIENT', 'comex-admin-api')
SEGREDO = os.getenv('KC_ADMIN_SECRET', '')
ADMIN = f'{BASE}/admin/realms/{REALM}'

_tok = {'v': None, 'exp': 0.0}

def configurado() -> bool:
    return bool(SEGREDO)

async def _token(c: httpx.AsyncClient) -> str:
    if _tok['v'] and _tok['exp'] - time.time() > 20:
        return _tok['v']
    r = await c.post(f'{BASE}/realms/{REALM}/protocol/openid-connect/token',
                     data={'grant_type': 'client_credentials', 'client_id': CLIENTE, 'client_secret': SEGREDO})
    if r.status_code != 200:
        raise HTTPException(502, 'Keycloak recusou a credencial do gerenciador de usuários')
    j = r.json(); _tok.update(v=j['access_token'], exp=time.time() + j.get('expires_in', 60))
    return _tok['v']

async def _kc(metodo: str, caminho: str, **kw) -> httpx.Response:
    if not configurado():
        raise HTTPException(503, 'gerenciador de usuários não configurado (KC_ADMIN_SECRET)')
    async with httpx.AsyncClient(timeout=10) as c:
        h = {'Authorization': 'Bearer ' + await _token(c)}
        r = await c.request(metodo, ADMIN + caminho, headers=h, **kw)
    if r.status_code == 404:
        raise LookupError('usuário não encontrado')
    if r.status_code in (401, 403):
        raise HTTPException(502, 'o gerenciador de usuários não tem permissão no Keycloak')
    if r.status_code == 409:
        raise HTTPException(409, 'já existe um usuário com este e-mail')
    if r.status_code >= 400:
        try: msg = r.json().get('errorMessage') or r.json().get('error') or r.text
        except ValueError: msg = r.text
        raise HTTPException(502 if r.status_code >= 500 else 422, f'Keycloak: {msg}')
    return r

def senha_temporaria() -> str:
    # 16 caracteres com as quatro classes: atende a política do realm (length(10))
    alfa = string.ascii_letters + string.digits + '-_.!@#'
    while True:
        s = ''.join(secrets.choice(alfa) for _ in range(16))
        if all(any(ch in g for ch in s) for g in (string.ascii_lowercase, string.ascii_uppercase, string.digits, '-_.!@#')):
            return s

def _papeis_validos(papeis) -> list[str]:
    fora = set(papeis) - set(PAPEIS)
    if fora:
        raise ValueError(f'papel não permitido: {", ".join(sorted(fora))}')
    return sorted(set(papeis))

async def _papeis_realm(nomes) -> list[dict]:
    return [(await _kc('GET', f'/roles/{n}')).json() for n in nomes]

async def _definir_papeis(uid: str, papeis: list[str]):
    atuais = {r['name'] for r in (await _kc('GET', f'/users/{uid}/role-mappings/realm')).json() if r['name'] in PAPEIS}
    novos = set(papeis)
    if novos - atuais:
        await _kc('POST', f'/users/{uid}/role-mappings/realm', json=await _papeis_realm(sorted(novos - atuais)))
    if atuais - novos:
        await _kc('DELETE', f'/users/{uid}/role-mappings/realm', json=await _papeis_realm(sorted(atuais - novos)))

def _visao(u: dict, papeis: set) -> dict:
    nome = ' '.join(x for x in (u.get('firstName'), u.get('lastName')) if x).strip()
    return {'id': u['id'], 'login': u['username'], 'email': u.get('email'), 'nome': nome or u['username'],
            'primeiro_nome': u.get('firstName') or '', 'sobrenome': u.get('lastName') or '',
            'ativo': u.get('enabled', False), 'papeis': sorted(papeis),
            'pendente': u.get('requiredActions') or [], 'criado_em': u.get('createdTimestamp')}

async def listar() -> list[dict]:
    usuarios = (await _kc('GET', '/users', params={'max': 500, 'briefRepresentation': 'false'})).json()
    por_papel = {}
    for p in PAPEIS:
        for u in (await _kc('GET', f'/roles/{p}/users', params={'max': 1000})).json():
            por_papel.setdefault(u['id'], set()).add(p)
    return sorted((_visao(u, por_papel.get(u['id'], set())) for u in usuarios
                   if not u['username'].startswith('service-account-')), key=lambda x: x['nome'].lower())

async def _um(uid: str) -> dict:
    u = (await _kc('GET', f'/users/{uid}')).json()
    if u['username'].startswith('service-account-'):
        raise LookupError('usuário não encontrado')
    papeis = {r['name'] for r in (await _kc('GET', f'/users/{uid}/role-mappings/realm')).json() if r['name'] in PAPEIS}
    return _visao(u, papeis)

async def criar(email: str, primeiro_nome: str, sobrenome: str, papeis) -> dict:
    papeis = _papeis_validos(papeis)
    senha = senha_temporaria()
    r = await _kc('POST', '/users', json={
        'username': email.lower(), 'email': email.lower(), 'firstName': primeiro_nome, 'lastName': sobrenome,
        'enabled': True, 'emailVerified': True, 'requiredActions': ['UPDATE_PASSWORD'],
        'credentials': [{'type': 'password', 'value': senha, 'temporary': True}]})
    uid = r.headers['Location'].rstrip('/').rsplit('/', 1)[-1]
    if papeis:
        await _definir_papeis(uid, papeis)
    return {**await _um(uid), 'senha_temporaria': senha}

async def alterar(uid: str, quem: Usuario, ativo=None, papeis=None, primeiro_nome=None, sobrenome=None) -> dict:
    atual = await _um(uid)
    proprio = atual['login'] == quem.login
    if proprio and ativo is False:
        raise ValueError('você não pode desativar a própria conta')
    if proprio and papeis is not None and 'comex-admin' not in papeis:
        raise ValueError('você não pode remover o próprio papel de administração')
    if papeis is not None:
        papeis = _papeis_validos(papeis)
    corpo = {}
    if ativo is not None: corpo['enabled'] = ativo
    if primeiro_nome is not None: corpo['firstName'] = primeiro_nome
    if sobrenome is not None: corpo['lastName'] = sobrenome
    if corpo:
        await _kc('PUT', f'/users/{uid}', json=corpo)
    if papeis is not None:
        await _definir_papeis(uid, papeis)
    if ativo is False:
        await _kc('POST', f'/users/{uid}/logout')          # derruba as sessões abertas
    return await _um(uid)

async def redefinir_senha(uid: str) -> dict:
    await _um(uid)
    senha = senha_temporaria()
    await _kc('PUT', f'/users/{uid}/reset-password', json={'type': 'password', 'value': senha, 'temporary': True})
    return {'id': uid, 'senha_temporaria': senha}
