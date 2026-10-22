from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

# Limites contra DoS de cálculo (o motor de estufagem é síncrono e cresce mais que linearmente
# com o número de volumes). Um embarque real tem dezenas de volumes; os tetos ficam folgados.
MAX_ITENS = 100            # linhas de carga por projeto/simulação
MAX_QTD = 200              # unidades por linha
MAX_VOLUMES = 600          # soma de qtd × seções (volumes gerados)
TXT = 200                  # textos livres
PARAM_NUM = ('fl', 'ft', 'tp', 'tt', 'skid', 'deck', 'densComp', 'densPinus', 'fe', 'umid', 'diasArm', 'a', 'e',
             'mHigro', 'cHigro', 'uniDes', 'margemPorta', 'folgaLat', 'folgaPorta')

def _parametros(v):
    """Só as chaves do motor (PARAM_PADRAO), números finitos de 0 a 100000 (a > 0); barreira 'Al' ou 'PE'."""
    if v is None: return v
    if len(v) > len(PARAM_NUM) + 1: raise ValueError('parâmetros demais')
    for k, x in v.items():
        if k == 'barreira':
            if x not in ('Al', 'PE'): raise ValueError("barreira deve ser 'Al' ou 'PE'")
        elif k in PARAM_NUM:
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not (0 <= x <= 100000) or (k == 'a' and x == 0):
                raise ValueError(f'parâmetro {k} deve ser número entre 0 e 100000' + (' (maior que 0)' if k == 'a' else ''))
        else:
            raise ValueError(f'parâmetro desconhecido: {k}')
    return v

def _volumes(itens):
    if sum(i.qtd * i.secoes for i in itens) > MAX_VOLUMES:
        raise ValueError(f'carga acima de {MAX_VOLUMES} volumes (qtd × seções)')
    return itens

class ItemIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=20)
    tag: str = Field(max_length=TXT); nome: str = Field(max_length=TXT)
    qtd: int = Field(ge=0, le=MAX_QTD); secoes: int = Field(ge=1, le=20)
    comp_mm: int = Field(ge=100, le=12000); larg_mm: int = Field(ge=100, le=4000); alt_mm: int = Field(ge=100, le=4000)
    peso_kg: float = Field(gt=0, le=30000); valor_usd: float = Field(ge=0, le=1e9)
    ncm: str = Field(max_length=12); embalagem: Literal['crate', 'caixa', 'engradado']; pilha_max: int = Field(1, ge=1, le=3)

class ProjetoIn(BaseModel):
    codigo: str = Field(pattern=r'^CMX-\d{2}-\d{4}$')
    titulo: str = Field(max_length=TXT); cliente_id: int; consignatario: str = Field(max_length=TXT)
    rota_id: str = Field(max_length=20); incoterm: str = Field(max_length=3)
    cambio_usd_brl: float = Field(gt=0, le=1000); seguro_pct: float = Field(ge=0, le=5)
    entrega_alvo: date; dia_saida: int = Field(ge=1, le=6)
    parametros: dict = {}
    itens: list[ItemIn] = Field([], max_length=MAX_ITENS)
    _p = field_validator('parametros')(_parametros)
    _v = field_validator('itens')(_volumes)

class ProjetoPatch(BaseModel):
    titulo: Optional[str] = Field(None, max_length=TXT); consignatario: Optional[str] = Field(None, max_length=TXT)
    rota_id: Optional[str] = Field(None, max_length=20); incoterm: Optional[str] = Field(None, max_length=3)
    cambio_usd_brl: Optional[float] = Field(None, gt=0, le=1000); seguro_pct: Optional[float] = Field(None, ge=0, le=5)
    entrega_alvo: Optional[date] = None; dia_saida: Optional[int] = Field(None, ge=1, le=6)
    parametros: Optional[dict] = None
    _p = field_validator('parametros')(_parametros)

class ClienteIn(BaseModel):
    nome: str; pais: str; cidade: Optional[str] = None; segmento: Optional[str] = None; contato: Optional[str] = None

class Aprovacao(BaseModel):
    aprovado_por: Optional[str] = Field(None, min_length=3)   # ignorado com AUTH_MODE=oidc (vem do token)
    aprovado_em: Optional[datetime] = None

class EventoIn(BaseModel):
    etapa: Optional[str] = None
    ts: Optional[datetime] = None
    registrado_por: Optional[str] = Field(None, min_length=3)  # ignorado com AUTH_MODE=oidc
    dados: dict = {}

class DocumentoPatch(BaseModel):
    status: Literal['PENDENTE', 'EMITIDO', 'NAO_APLICA']
    numero: Optional[str] = None
    emitido_em: Optional[datetime] = None

class SimularIn(BaseModel):
    rota_id: str = Field(max_length=20); incoterm: str = Field(max_length=3)
    cambio_usd_brl: float = Field(gt=0, le=1000); seguro_pct: float = Field(ge=0, le=5)
    entrega_alvo: date; dia_saida: int = Field(ge=1, le=6)
    parametros: dict = {}
    itens: list[ItemIn] = Field(min_length=1, max_length=MAX_ITENS)
    _p = field_validator('parametros')(_parametros)
    _v = field_validator('itens')(_volumes)

Papel = Literal['comex-leitura', 'comex-logistica', 'comex-comercial', 'comex-admin']

class UsuarioIn(BaseModel):
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', max_length=254)
    primeiro_nome: str = Field(min_length=1, max_length=80); sobrenome: str = Field('', max_length=80)
    papeis: list[Papel] = ['comex-leitura']

class UsuarioPatch(BaseModel):
    ativo: Optional[bool] = None; papeis: Optional[list[Papel]] = None
    primeiro_nome: Optional[str] = Field(None, min_length=1, max_length=80); sobrenome: Optional[str] = Field(None, max_length=80)
