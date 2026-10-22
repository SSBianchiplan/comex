"""Autenticação OIDC (Keycloak) e autorização por papel.

AUTH_MODE=oidc      → exige Bearer token válido (assinatura via JWKS, iss, aud, exp).
AUTH_MODE=desligado → desenvolvimento/demonstração: usuário local com todos os papéis.
O usuário e os papéis do token são gravados na transação (comex.usuario / comex.papeis),
e o banco recusa aprovação ou evento em nome de outra pessoa (INV-CMX-024/025)."""
import os, time
from dataclasses import dataclass, field
import jwt
from fastapi import Depends, HTTPException, Request

MODO = os.getenv('AUTH_MODE', 'desligado').lower()
ISSUER = os.getenv('OIDC_ISSUER', '').rstrip('/')                 # público: o "iss" do token
JWKS_URL = os.getenv('OIDC_JWKS_URL') or (ISSUER + '/protocol/openid-connect/certs' if ISSUER else '')  # pode ser interno
AUDIENCE = os.getenv('OIDC_AUDIENCE', 'comex-api')
CLIENT_WEB = os.getenv('OIDC_CLIENT_WEB', 'comex-web')
PAPEIS = ('comex-leitura', 'comex-logistica', 'comex-comercial', 'comex-admin')

@dataclass
class Usuario:
    login: str
    nome: str
    email: str | None = None
    papeis: set = field(default_factory=set)
    def tem(self, *p): return 'comex-admin' in self.papeis or any(x in self.papeis for x in p)

_jwks = None
def _cliente_jwks():
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600, timeout=5)
    return _jwks

def validar(token: str) -> Usuario:
    try:
        chave = _cliente_jwks().get_signing_key_from_jwt(token).key
        c = jwt.decode(token, chave, algorithms=['RS256', 'ES256'], audience=AUDIENCE, issuer=ISSUER,
                       leeway=30, options={'require': ['exp', 'iat', 'iss', 'sub']})
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, 'token expirado', headers={'WWW-Authenticate': 'Bearer error="invalid_token"'})
    except (jwt.PyJWTError, Exception) as e:
        raise HTTPException(401, f'token inválido: {type(e).__name__}', headers={'WWW-Authenticate': 'Bearer error="invalid_token"'})
    papeis = {p for p in (c.get('realm_access') or {}).get('roles', []) if p in PAPEIS}
    login = c.get('preferred_username') or c.get('email') or c['sub']
    return Usuario(login=login, nome=c.get('name') or login, email=c.get('email'), papeis=papeis)

async def usuario_atual(request: Request) -> Usuario:
    if MODO != 'oidc':
        return Usuario(login='dev.local', nome='Desenvolvimento local', papeis={'comex-admin'})
    h = request.headers.get('authorization', '')
    if not h.lower().startswith('bearer '):
        raise HTTPException(401, 'autenticação necessária', headers={'WWW-Authenticate': 'Bearer'})
    return validar(h[7:].strip())

def exige(*papeis):
    async def dep(u: Usuario = Depends(usuario_atual)) -> Usuario:
        if not u.tem(*papeis):
            raise HTTPException(403, f'papel necessário: {" ou ".join(papeis)}')
        return u
    return dep

LER = exige('comex-leitura', 'comex-logistica', 'comex-comercial')
OPERAR = exige('comex-logistica', 'comex-comercial')
LOGISTICA = exige('comex-logistica')
COMERCIAL = exige('comex-comercial')
ADMIN = exige('comex-admin')

async def sessao(conn, u: Usuario):
    """Grava a identidade na transação corrente (SET LOCAL). Só com AUTH_MODE=oidc."""
    if MODO == 'oidc':
        await conn.execute("SELECT set_config('comex.usuario', %s, true), set_config('comex.papeis', %s, true)",
                           (u.login, ','.join(sorted(u.papeis))))

def config_publica():
    return {'auth': MODO == 'oidc', 'issuer': ISSUER or None, 'client_id': CLIENT_WEB if MODO == 'oidc' else None,
            'usuarios': MODO == 'oidc' and bool(os.getenv('KC_ADMIN_SECRET'))}
