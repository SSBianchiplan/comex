<p align="center">
  <a href="https://comex.gplansis.com"><img src=".github/capa.png" alt="GPlanSiS|Comex — do painel na fábrica ao contêiner no navio, cada embarque com prova" width="100%"></a>
</p>

<h1 align="center">GPlanSiS|Comex</h1>

<p align="center">
  <strong>Planejamento e rastreabilidade de exportação de painéis elétricos: embalagem ISPM-15, estufagem de contêiner, cotação por Incoterm 2020, cronograma reverso até a entrega e ledger GS1 EPCIS encadeado por SHA-256.</strong><br>
  O motor calcula; o banco decide o que é aceito.
</p>

<p align="center">
  <a href="https://comex.gplansis.com"><img alt="No ar" src="https://img.shields.io/badge/no%20ar-comex.gplansis.com-EB6A20?style=flat-square"></a>
  <img alt="Versão" src="https://img.shields.io/badge/vers%C3%A3o-1.2.0-2D3336?style=flat-square">
  <a href="LICENSE"><img alt="licença MIT" src="https://img.shields.io/badge/licen%C3%A7a-MIT-2ea44f?style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-2D3336?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-psycopg%203-2D3336?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16-2D3336?style=flat-square&logo=postgresql&logoColor=white">
  <img alt="Keycloak" src="https://img.shields.io/badge/Keycloak-26%20%C2%B7%20OIDC-2D3336?style=flat-square&logo=keycloak&logoColor=white">
  <img alt="PWA" src="https://img.shields.io/badge/PWA-instal%C3%A1vel-2D3336?style=flat-square">
  <a href="CONTRIBUTING.md"><img alt="Contribuições bem-vindas" src="https://img.shields.io/badge/contribui%C3%A7%C3%B5es-bem--vindas-F6A709?style=flat-square"></a>
</p>

<p align="center">
  <a href="https://comex.gplansis.com"><b>➜ Abrir o GPlanSiS|Comex em comex.gplansis.com</b></a> ·
  <a href="https://comex.gplansis.com/app.html?demo=1">ver demonstração sem login</a>
</p>

---

## O que é

O **GPlanSiS|Comex** organiza a exportação de equipamentos grandes — CCMs, QGBTs, painéis de média tensão, remotas, PLCs — **de trás para frente**: a partir da data de entrega no site do cliente, calcula as caixas de embalagem, escolhe e arruma os contêineres, cota o frete pela divisão de custos do Incoterm e monta o cronograma até o pedido. Cada etapa vira um bloco de um **ledger encadeado por SHA-256**, e cada documento do embarque é guardado em versões imutáveis com hash.

A regra não mora só na tela nem só na API: são **29 invariantes** (`INV-CMX-001` a `029`) impostas pelo **PostgreSQL** com CHECK, triggers e permissões. Um script de RED-TEAM tenta violar cada uma direto no banco — estufar sem cotação aprovada, reescrever o ledger, aprovar em nome de outra pessoa, trocar um PDF por um executável — e só passa se o banco recusar com o código certo.

## Funcionalidades

### Planejar — carga e embalagem
- Carga por **seção de transporte** (o painel é dividido nas juntas de barramento): dimensões, peso, valor, NCM sugerido, embalagem e empilhamento.
- Caixas **ISPM-15** (madeira tratada, carimbo IPPC), peso líquido/bruto/tara, cubagem e **centro de gravidade** por volume.
- **Passaporte digital** de cada volume com **SSCC GS1** (18 dígitos, dígito verificador) e marcação.

### Embarcar — contêineres e frete
- **Estufagem**: o motor testa cada volume contra vão de porta, altura e largura de cada equipamento (20' DV, 40' DV, 40' HC, Open Top, Flat Rack), escolhe o menor que resolve, arruma o piso por *MaxRects*, empilha só o que é empilhável e **centraliza o CG** (longitudinal e transversal ≤ 15%). Carga fora de gabarito vira alerta de OOG para o booking.
- Número de contêiner **ISO 6346** com dígito verificador, lacre e **VGM** (SOLAS, método 2).
- **Cotação por Incoterm 2020**: frete base por rota com vigência, BAF/EFS, OOG, ISPS, THC de origem e destino, rodoviário, seguro e câmbio — e **quem paga cada linha** conforme o Incoterm escolhido, inclusive tributos estimados no destino.
- **Aprovação humana** da cotação: sem ela a estufagem é bloqueada (INV-CMX-013/022).

### Acompanhar — agenda e ledger
- **Cronograma reverso** em dias úteis, com feriados nacionais e saída semanal do serviço: data de entrega → trânsito → navio → cut-off → estufagem → embalagem → FAT → booking → cotação, com marcos críticos e aviso de programação inviável.
- **Ledger GS1 EPCIS 2.0**: 12 etapas do pedido à entrega, em ordem estrita, com hash e sequência calculados **pelo banco**; tabela append-only (UPDATE, DELETE e TRUNCATE recusados) e **verificação da cadeia** por `fn_ledger_verificar()`.

### Documentar — compliance
- Fatura, packing list, NF-e/DU-E, certificado de origem, ISPM-15, booking, VGM, eBL, seguro, FAT e desembaraço com status, número e emissor; o responsável segue o Incoterm.
- **Arquivos versionados no PostgreSQL**: SHA-256 calculado pelo banco, assinatura de conteúdo conferida (PDF, PNG, JPG, XML, XLSX, DOCX), até 10 MB; cada evento do ledger **ancora** o hash vigente dos documentos. No download o navegador recalcula o hash e só salva se conferir.
- **Packing list em CSV** (pt-BR).

### Acesso e segurança
- Login único pelo **Keycloak** (OpenID Connect, Authorization Code + PKCE S256); a API valida assinatura (JWKS), emissor, audiência e expiração.
- 4 papéis: `comex-leitura`, `comex-logistica`, `comex-comercial`, `comex-admin`. **Quem aprova o frete não assina a estufagem.**
- **A identidade é garantida pelo banco**: a API grava usuário e papéis da sessão com `SET LOCAL`, e os triggers recusam aprovação ou evento em nome de outra pessoa ou sem o papel exigido (INV-CMX-024/025).
- **Gestão de usuários** pela própria interface (admin): criar, papéis, senha temporária, desativar — pela Admin API do Keycloak com um cliente de privilégio mínimo.
- nginx com CSP, HSTS, `frame-ancestors 'none'` e demais cabeçalhos em todas as rotas; console do Keycloak não publicado.

### Aplicativo
- **PWA** instalável, responsivo de 360 px a desktop, temas claro/escuro/sistema; service worker guarda só o shell (nunca `/api/`).
- **Modo demonstração** sem login ou sem API, com os mesmos 3 projetos e as mesmas regras do motor (nada vai para o banco).
- Página inicial pública com **simulador de Incoterm** usando os números do motor.

## Telas

| Visão geral do embarque | Estufagem e seleção de contêiner |
|---|---|
| ![Visão geral com indicadores, carteira de embarques, pendências e linha do tempo](.github/telas/visao-geral.png) | ![Plano de estufagem do 40' Open Top com centro de gravidade e VGM](.github/telas/estufagem.png) |
| **Cotação de frete por Incoterm** | **Ledger encadeado por SHA-256** |
| ![Cotação com mercado, aprovação humana e frete por contêiner](.github/telas/cotacao.png) | ![Ledger do embarque com verificação da cadeia pelo PostgreSQL](.github/telas/ledger.png) |

> Capturas feitas numa instância local com os **3 projetos demo fictícios** do `api/app/seed.py` (clientes, cargas e números inventados) — nenhum dado real de exportação.

## Arquitetura

```mermaid
flowchart LR
    subgraph Navegador
        LP["index.html<br/>página pública + simulador"]
        APP["app.html<br/>PWA (motor JS, modo demo)"]
    end
    CADDY["Caddy / Traefik<br/>TLS"]
    subgraph Compose["Docker Compose (gplansis-comex)"]
        WEB["web · nginx<br/>estáticos + CSP/HSTS"]
        API["api · FastAPI<br/>engine.py (motor puro)"]
        KC["keycloak 26<br/>realm gplansis"]
        DB[("PostgreSQL 16<br/>schema comex<br/>29 invariantes · ledger append-only")]
        SEED["seed<br/>3 projetos demo"]
    end

    APP -- "login PKCE" --> CADDY --> KC
    APP -- "/api (Bearer JWT)" --> CADDY --> WEB --> API
    LP --> CADDY
    API -- "comex_api (sem UPDATE/DELETE no ledger)<br/>SET LOCAL usuário e papéis" --> DB
    API -- "JWKS · Admin API" --> KC
    KC --> DB
    SEED --> DB
```

- **A verdade mora no banco.** O motor (`api/app/engine.py`, espelhado em JS no PWA) calcula; o banco decide o que é aceito. Paridade JS × Python × banco nos 3 demos (diferença máxima de 1 centavo).
- **Privilégio mínimo.** A API e o seed conectam como `comex_api` (membro de `comex_app`): inserem no ledger, mas não o alteram nem apagam. Só o RED-TEAM e a manutenção usam o dono do schema.
- **Estado é projeção do ledger.** Registrar uma etapa muda o estado do embarque e realiza os marcos por trigger.
- Em produção (comex.gplansis.com) o Caddy do host manda `/auth/*` para o Keycloak e o resto para o nginx, na mesma origem; o compose base também traz rótulos para Traefik.

## Stack

| Camada | Tecnologia |
|---|---|
| Banco | PostgreSQL 16 (CHECK, triggers PL/pgSQL, EXCLUDE gist, pgcrypto, btree_gist) |
| API | Python 3.12, FastAPI, psycopg 3 + psycopg-pool, Pydantic v2, PyJWT |
| Identidade | Keycloak 26 (OIDC, PKCE), tema de login próprio (FreeMarker) |
| Interface | HTML, CSS e JavaScript sem build, PWA, fontes Barlow / Barlow Condensed / JetBrains Mono (Google Fonts) |
| Servidor web | nginx 1.30 (template com CSP) |
| Implantação | Docker Compose; Caddy (produção atual) ou Traefik |
| Testes | pytest + httpx (API, autenticação com JWKS local, gestão de usuários) e RED-TEAM em SQL |

## Como rodar localmente

### Mais rápido: só o navegador
Abra `web/app.html?demo=1` (ou a [demonstração no ar](https://comex.gplansis.com/app.html?demo=1)). Sem API, o app entra no modo demonstração com os 3 projetos.

### Completo com Docker (sem Traefik)
```bash
git clone https://github.com/SSBianchiplan/comex.git
cd comex
cp .env.example .env          # troque todas as senhas e o COMEX_ADMIN_EMAIL
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```
App em <http://localhost:8080>, Keycloak em <http://localhost:8180>, PostgreSQL em `localhost:5433`. Ordem de subida: `db` (scripts 001→005 no primeiro boot) → `seed` e `keycloak` (importa o realm) → `api` → `web`. Os usuários demo (`comercial.demo`, `logistica.demo`, `leitura.demo`) usam a senha de `COMEX_SENHA_DEMO`, com troca obrigatória no primeiro acesso.

### API + PWA sem Docker e sem login (desenvolvimento)
Com um PostgreSQL 16 próprio:
```bash
createdb gpscomex
for f in db/001_schema.sql db/002_regras.sql db/003_referencia.sql; do psql -d gpscomex -v ON_ERROR_STOP=1 -f "$f"; done
psql -d gpscomex -c "CREATE ROLE comex_api LOGIN PASSWORD 'senha-local' IN ROLE comex_app"

python3 -m venv .venv && .venv/bin/pip install -r api/requirements.txt -r api/requirements-dev.txt
export DATABASE_URL=postgresql://comex_api:senha-local@localhost:5432/gpscomex
(cd api && ../.venv/bin/python -m app.seed)                       # 3 projetos demo
(cd api && AUTH_MODE=desligado WEB_DIR=../web ../.venv/bin/uvicorn app.main:app --port 8000)
```
Abra <http://localhost:8000/app.html>. `AUTH_MODE=desligado` é só para laboratório: API aberta, usuário local com todos os papéis. No VS Code, as tarefas e configurações de depuração de [`.vscode/`](.vscode) fazem o mesmo com F5.

### Testes e RED-TEAM
```bash
# API (com a API rodando e o banco recém-semeado)
PYTHONPATH=api API_URL=http://localhost:8000 DATABASE_URL=$DATABASE_URL .venv/bin/pytest -q api/tests   # 38 passed (30 de integração + 8 de segurança)

# RED-TEAM: tenta violar cada invariante direto no banco (transação desfeita)
psql -d gpscomex -f db/090_redteam.sql                                                                   # 54 PASS / 0 FAIL
# no Docker: docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d gpscomex -f /redteam/090_redteam.sql'
```

### Produção
`deploy/enviar.sh` sincroniza o código para o servidor, gera o `.env` com segredos aleatórios **no próprio servidor** na primeira vez e instala o bloco do Caddy ([`deploy/comex.caddy`](deploy/comex.caddy), que importa um snippet `seguranca_hub` do hub GPlanSiS — ajuste se for usar fora dele). Notas de operação, backup e premissas em [`LEIAME.md`](LEIAME.md).

## API (OpenAPI em `/docs`)

| Método | Rota | Função |
|---|---|---|
| GET | `/api/saude`, `/api/config` | Saúde e configuração de login (públicas) |
| GET | `/api/eu` | Usuário autenticado e papéis |
| GET | `/api/referencias` | Tarifas vigentes, Incoterms, contêineres, etapas… |
| GET/POST | `/api/clientes`, `/api/projetos` | Clientes; carteira / criar embarque com itens |
| GET/PATCH | `/api/projetos/{id}` | Detalhe completo / alterar e recalcular |
| PUT | `/api/projetos/{id}/itens` | Substituir itens e recalcular |
| POST | `/api/projetos/{id}/calcular` | Recalcular embalagem, estufagem, cotação e cronograma |
| POST | `/api/projetos/{id}/cotacoes/{cid}/aprovar` | Aprovação humana da cotação |
| POST | `/api/projetos/{id}/ledger` | Registrar a próxima etapa |
| GET | `/api/projetos/{id}/ledger/verificar` | Verificação da cadeia pelo banco |
| PATCH / POST / GET | `/api/projetos/{id}/documentos/{tipo}[/arquivos[/{versao}]]` | Emitir, anexar nova versão, baixar com `X-Content-SHA256` |
| GET | `/api/projetos/{id}/packing-list.csv` | Packing list |
| POST | `/api/simular` | Cálculo sem persistência |
| GET/POST/PATCH | `/api/usuarios[/{id}[/senha]]` | Gestão de usuários (admin) |

Uma violação de invariante vira **HTTP 409** com o código `INV-CMX-xxx` no corpo; a interface mostra a mensagem.

## Estrutura de pastas

```
comex/
├── api/
│   ├── app/
│   │   ├── main.py        # rotas FastAPI (e serve web/ quando WEB_DIR existe)
│   │   ├── engine.py      # motor puro: embalagem, estufagem, CG, cotação, cronograma
│   │   ├── servico.py     # orquestra motor + banco
│   │   ├── auth.py        # OIDC/JWKS, papéis, SET LOCAL da identidade
│   │   ├── usuarios.py    # gestão de usuários pela Admin API do Keycloak
│   │   ├── db.py, schemas.py
│   │   └── seed.py        # 3 projetos demo fictícios pelo fluxo real
│   ├── tests/             # API, autenticação e usuários
│   ├── Dockerfile, requirements*.txt
├── db/
│   ├── 001_schema.sql     # tabelas do schema comex
│   ├── 002_regras.sql     # invariantes: CHECKs, triggers, permissões, ledger
│   ├── 003_referencia.sql # contêineres, rotas, tarifas indicativas, Incoterms, feriados, etapas
│   ├── 004/005_*.sh       # papel comex_api e banco do Keycloak
│   ├── 090_redteam.sql    # ataques a cada invariante
│   └── reset.sh           # recria o schema (destrutivo)
├── web/                   # index.html (público), app.html (PWA), sw.js, manifest, ícones, nginx
├── keycloak/              # realm gplansis (sem segredos) e tema de login
├── deploy/                # comex.caddy e enviar.sh
├── docker-compose.yml     # base (Traefik) · .local.yml · .prod.yml (Caddy)
├── .vscode/               # tarefas e depuração
└── LEIAME.md              # notas de operação
```

## Variáveis de ambiente

| Variável | Uso |
|---|---|
| `DB_USER`, `DB_PASSWORD` | Dono do banco `gpscomex` (manutenção e RED-TEAM) |
| `API_DB_PASSWORD` | Senha do papel `comex_api` usado pela API e pelo seed |
| `KC_DB_PASSWORD` | Senha do banco do Keycloak |
| `KC_ADMIN_PASSWORD` | Admin bootstrap do Keycloak |
| `KC_ADMIN_SECRET` | Segredo do cliente `comex-admin-api` (gestão de usuários) |
| `COMEX_ADMIN_EMAIL` | Login do admin master criado na importação do realm |
| `COMEX_SENHA_ADMIN`, `COMEX_SENHA_DEMO` | Senhas temporárias (troca obrigatória no 1º acesso) |
| `DOMINIO`, `COMEX_URL`, `KC_HOST`, `KC_URL` | Endereços públicos |
| `ADMIN_IP_ALLOW` | Faixas que podem abrir o console do Keycloak (Traefik) |
| `TRAEFIK_NETWORK`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER` | Integração com Traefik |
| `AUTH_MODE` | `oidc` (padrão no compose) ou `desligado` (só laboratório) |
| `CORS_ORIGINS` | Só se o front rodar em outra origem |
| `DATABASE_URL`, `OIDC_ISSUER`, `WEB_DIR` | Execução fora do Docker |

Modelo em [`.env.example`](.env.example). Nunca versione o `.env`. O sistema não usa nenhuma API externa (Siscomex, câmbio etc.): câmbio, tarifas e taxas são parâmetros editáveis.

## Premissas e limitações

- Fretes, THC, BAF/EFS e custos de embalagem são **estimativas indicativas** (set/2026) — confirme com NVOCC/armador antes de ofertar. NCM/HS e tributos no destino devem ser validados pelo despachante.
- O prefixo GS1 (7890123) e o código de dono ISO 6346 (GPS) são **fictícios**; substitua pelos registrados.
- Arquivos de documentos ficam no PostgreSQL (até 10 MB por versão): dimensione disco e backup.
- Offline ou sem API, o app entra em modo demonstração; não há fila de sincronização.

## Contribua

O Comex junta logística real (ISPM-15, ISO 6346, SOLAS VGM, Incoterms, GS1) com uma disciplina rara: **regra de negócio provada no banco**. É um ótimo projeto para quem trabalha com exportação, engenharia de dados ou PostgreSQL. **Toda ajuda conta.**

**Por onde começar (boas primeiras issues):**
- 🌐 **Integrações opcionais e configuráveis**: cotação PTAX do Banco Central para o câmbio, consulta de NCM/TEC — sempre como sugestão editável, sem chave embutida no código.
- 📦 **Novos equipamentos e embalagens**: 45' HC, reefer, flat rack colapsável, paletes; mais testes do *MaxRects* com cargas difíceis.
- 🗺️ **Novas rotas e tarifas de referência** em `db/003_referencia.sql` (com vigência e fonte).
- 🧪 **Testes do motor** (`engine.py`) com pytest/hypothesis e um teste automático de paridade JS × Python.
- 🛠️ **CI**: workflow do GitHub Actions subindo PostgreSQL 16, rodando o RED-TEAM e o `pytest`.
- 📄 **Geração de documentos** (packing list e fatura em PDF/XLSX) a partir dos dados do embarque.
- 🌍 **Internacionalização** (inglês e espanhol) — exportação conversa com o comprador lá fora.
- ♿ **Acessibilidade** do plano de estufagem e da linha do tempo (alternativas textuais, teclado).

Leia o [guia de contribuição](CONTRIBUTING.md), abra uma [issue](../../issues/new/choose) para combinar a ideia e mande seu pull request. Siga o [código de conduta](CODE_OF_CONDUCT.md). Encontrou uma falha de segurança? Veja a [política de segurança](SECURITY.md) — não abra issue pública.

## Licença

Código próprio sob a **[licença MIT](LICENSE)** — Copyright (c) 2026 GPlanSiS.

Nenhum código de terceiros está copiado no repositório. Dependências instaladas por `pip`: FastAPI, Pydantic e PyJWT (MIT), uvicorn (BSD-3-Clause), psycopg e psycopg-pool (LGPL-3.0, usados como biblioteca, sem modificação), python-multipart (Apache-2.0). Imagens Docker usadas: PostgreSQL (PostgreSQL License), Keycloak (Apache-2.0), nginx (BSD-2-Clause). Fontes **Barlow**, **Barlow Condensed**, **JetBrains Mono** e **Allerta Stencil** carregadas do Google Fonts (SIL Open Font License 1.1).

## Créditos

Desenvolvido pela **[GPlanSiS|Group](https://gplansis.com)** · contato: [contato@gplansis.com](mailto:contato@gplansis.com)

<p align="center"><a href="https://comex.gplansis.com"><b>comex.gplansis.com</b></a></p>
