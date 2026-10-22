"""Testes unitários da camada OIDC sem Keycloak: um JWKS local assina e publica a chave.
Cobrem assinatura, emissor, audiência, expiração, filtro de papéis e autorização por papel."""
import asyncio, importlib, json, os, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import jwt, pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OUTRA = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(CHAVE.public_key())); JWK.update(kid='k1', use='sig', alg='RS256')

class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        b = json.dumps({'keys': [JWK]}).encode(); self.send_response(200)
        self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

@pytest.fixture(scope='module')
def auth():
    srv = HTTPServer(('127.0.0.1', 0), _H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ.update(AUTH_MODE='oidc', OIDC_ISSUER='https://id.teste/realms/t', OIDC_AUDIENCE='comex-api',
                      OIDC_JWKS_URL=f'http://127.0.0.1:{srv.server_port}/certs')
    from app import auth as m; importlib.reload(m); yield m
    srv.shutdown(); os.environ['AUTH_MODE'] = 'desligado'; importlib.reload(m)

def tok(chave=CHAVE, **kw):
    agora = int(time.time())
    c = {'iss': 'https://id.teste/realms/t', 'aud': 'comex-api', 'sub': 'u1', 'iat': agora, 'exp': agora + 300,
         'preferred_username': 'carla', 'name': 'Carla', 'realm_access': {'roles': ['comex-comercial', 'offline_access']}}
    c.update(kw); return jwt.encode(c, chave, algorithm='RS256', headers={'kid': 'k1'})

def test_token_valido_e_filtro_de_papeis(auth):
    u = auth.validar(tok()); assert u.login == 'carla' and u.papeis == {'comex-comercial'}

@pytest.mark.parametrize('caso,kw', [('expirado', {'exp': int(time.time()) - 120}), ('emissor', {'iss': 'https://outro/realms/t'}),
                                     ('audiencia', {'aud': 'account'}), ('assinatura', {'chave': OUTRA})])
def test_token_recusado(auth, caso, kw):
    chave = kw.pop('chave', CHAVE)
    with pytest.raises(HTTPException) as e: auth.validar(tok(chave, **kw))
    assert e.value.status_code == 401

def test_autorizacao_por_papel(auth):
    u = auth.validar(tok())
    assert asyncio.run(auth.COMERCIAL(u)) is u
    with pytest.raises(HTTPException) as e: asyncio.run(auth.LOGISTICA(u))
    assert e.value.status_code == 403
    adm = auth.validar(tok(realm_access={'roles': ['comex-admin']}))
    assert asyncio.run(auth.LOGISTICA(adm)) is adm

def test_config_publica(auth):
    assert auth.config_publica() == {'auth': True, 'issuer': 'https://id.teste/realms/t', 'client_id': 'comex-web', 'usuarios': False}
