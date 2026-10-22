from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

class ItemIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=20)
    tag: str; nome: str
    qtd: int = Field(ge=0); secoes: int = Field(ge=1, le=20)
    comp_mm: int = Field(ge=100, le=12000); larg_mm: int = Field(ge=100, le=4000); alt_mm: int = Field(ge=100, le=4000)
    peso_kg: float = Field(gt=0, le=30000); valor_usd: float = Field(ge=0)
    ncm: str; embalagem: Literal['crate', 'caixa', 'engradado']; pilha_max: int = Field(1, ge=1, le=3)

class ProjetoIn(BaseModel):
    codigo: str = Field(pattern=r'^CMX-\d{2}-\d{4}$')
    titulo: str; cliente_id: int; consignatario: str
    rota_id: str; incoterm: str
    cambio_usd_brl: float = Field(gt=0); seguro_pct: float = Field(ge=0, le=5)
    entrega_alvo: date; dia_saida: int = Field(ge=1, le=6)
    parametros: dict = {}
    itens: list[ItemIn] = []

class ProjetoPatch(BaseModel):
    titulo: Optional[str] = None; consignatario: Optional[str] = None
    rota_id: Optional[str] = None; incoterm: Optional[str] = None
    cambio_usd_brl: Optional[float] = Field(None, gt=0); seguro_pct: Optional[float] = Field(None, ge=0, le=5)
    entrega_alvo: Optional[date] = None; dia_saida: Optional[int] = Field(None, ge=1, le=6)
    parametros: Optional[dict] = None

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
    rota_id: str; incoterm: str
    cambio_usd_brl: float = Field(gt=0); seguro_pct: float = Field(ge=0, le=5)
    entrega_alvo: date; dia_saida: int = Field(ge=1, le=6)
    parametros: dict = {}
    itens: list[ItemIn] = Field(min_length=1)

Papel = Literal['comex-leitura', 'comex-logistica', 'comex-comercial', 'comex-admin']

class UsuarioIn(BaseModel):
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', max_length=254)
    primeiro_nome: str = Field(min_length=1, max_length=80); sobrenome: str = Field('', max_length=80)
    papeis: list[Papel] = ['comex-leitura']

class UsuarioPatch(BaseModel):
    ativo: Optional[bool] = None; papeis: Optional[list[Papel]] = None
    primeiro_nome: Optional[str] = Field(None, min_length=1, max_length=80); sobrenome: Optional[str] = Field(None, max_length=80)
