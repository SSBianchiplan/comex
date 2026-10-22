# GPlanSiS|COMEX — Comércio exterior e logística de exportação

Planejamento e rastreabilidade de exportação de painéis elétricos: embalagem ISPM-15, estufagem de contêiner, cotação por Incoterm 2020, cronograma reverso até a entrega e ledger EPCIS encadeado por SHA-256.
Stack: PostgreSQL 16 · FastAPI/psycopg 3 · Keycloak 26 (OIDC) · PWA (nginx) · Docker Compose + Traefik. Versão 1.2.

## Produção atual: https://comex.gplansis.com (Caddy)

```bash
bash deploy/enviar.sh      # rsync para /opt/gplansis-comex, compose com docker-compose.prod.yml, Caddy
```
- Sem Traefik: o Caddy do host (`deploy/comex.caddy`) manda `/auth/*` para o Keycloak (127.0.0.1:8931) e o resto para o nginx (127.0.0.1:8933). O Keycloak fica na mesma origem, sem DNS próprio.
- O `.env` é gerado no servidor na primeira publicação, com segredos aleatórios (chmod 600), e nunca sai de lá.
- Console do Keycloak e realm master não são publicados (404). Para abrir: `ssh -L 8931:127.0.0.1:8931 $HOST` e http://localhost:8931/auth/admin/ (usuário `admin`, senha `KC_ADMIN_PASSWORD` do `.env` do servidor).

## Gestão de usuários

Admin master: o e-mail de `COMEX_ADMIN_EMAIL` (papel `comex-admin`, com todos os papéis). A senha temporária é `COMEX_SENHA_ADMIN` do `.env`, e a troca é obrigatória no primeiro acesso.

Quem tem `comex-admin` vê o botão **Usuários** na folha da sessão (toque no avatar). Ali dá para criar usuário (o e-mail é o login, a senha temporária aparece uma única vez), marcar papéis, gerar nova senha temporária e desativar/reativar. Desativar derruba as sessões abertas. Ninguém desativa a própria conta nem remove o próprio papel de administração.

A API fala com a Admin API do Keycloak pela rede interna, como o cliente confidencial `comex-admin-api` (service account com `manage-users`, `view-users`, `query-users` e `view-realm`). Só os quatro papéis COMEX podem ser atribuídos.

| Método | Rota | Função |
|---|---|---|
| GET/POST | `/api/usuarios` | Listar / criar (retorna `senha_temporaria`) |
| PATCH | `/api/usuarios/{id}` | `ativo`, `papeis`, `primeiro_nome`, `sobrenome` |
| POST | `/api/usuarios/{id}/senha` | Nova senha temporária |

## Três formas de rodar

**1. Produção (Docker + Traefik)**
```bash
cp .env.example .env            # senhas (banco, API, Keycloak, admin, demo), DOMINIO e KC_HOST
docker compose up -d --build
```

**2. Local completo (Docker, sem Traefik)** — app em http://localhost:8080, Keycloak em http://localhost:8180
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

**3. VS Code (desenvolvimento, com depuração)**
1. Abra a pasta no VS Code e aceite as extensões recomendadas.
2. `Terminal → Run Task → COMEX: instalar dependências Python`
3. `Run Task → COMEX: subir banco e Keycloak locais (5433 e 8180)` — sobe o PostgreSQL, semeia os 3 demos e importa o realm.
4. **F5** — "sem login" (rápido, AUTH_MODE=desligado) ou "com login (Keycloak local)". Abre http://localhost:8000 com API e PWA na mesma origem, com breakpoints no Python.
5. Testes: configuração "COMEX: testes da API" ou a aba Testing. RED-TEAM: `Run Task → COMEX: RED-TEAM do banco`.

Ordem de subida no Docker: `db` (001→005 no primeiro boot) → `seed` (3 demos, idempotente) e `keycloak` (importa o realm) → `api` → `web`.
O frontend detecta a API em `/api/saude`. Sem ela, entra no **modo demonstração** com os mesmos 3 projetos e as mesmas regras, e avisa que as alterações não vão para o banco.

## Autenticação e perfis

Login pelo Keycloak (realm `gplansis`) com Authorization Code + PKCE S256. O PWA é um cliente público: não guarda segredo, e os tokens ficam na sessão da aba e são renovados antes de expirar. A API valida cada token (assinatura via JWKS, emissor, audiência `comex-api`, expiração) e autoriza por papel.

| Papel | Pode |
|---|---|
| `comex-leitura` | Consultar embarques, cotações, cronograma, ledger e packing list |
| `comex-logistica` | Tudo da leitura + editar carga e embalagem, recalcular, registrar eventos do ledger, emitir documentos |
| `comex-comercial` | Tudo da leitura + criar clientes e embarques, editar e aprovar cotações |
| `comex-admin` | Todos os papéis |

Aprovar e registrar evento são ações separadas de propósito: quem aprova o frete não assina a estufagem.

**A identidade é garantida pelo banco, não só pela API.** Em cada transação a API grava `comex.usuario` e `comex.papeis` a partir do token (`SET LOCAL`). Os triggers recusam aprovação ou evento em nome de outra pessoa (INV-CMX-024) ou sem o papel exigido (INV-CMX-025). Com login ativo, o nome e a data enviados no corpo são ignorados: o aprovador, o assinante e o horário do evento vêm do token e do servidor.

Usuários demo (`comercial.demo`, `logistica.demo`, `leitura.demo`) usam a senha temporária de `COMEX_SENHA_DEMO`, com troca obrigatória no primeiro acesso. **Em produção, desative-os** e crie os usuários reais no console do Keycloak, que só abre para as faixas de `ADMIN_IP_ALLOW`.

`AUTH_MODE=desligado` existe só para laboratório: API aberta, usuário local com todos os papéis.

## Arquitetura

```
web (nginx, PWA) ──/api──► api (FastAPI) ──► PostgreSQL 16 · schema comex
      │  login PKCE              │ valida JWT (JWKS)
      └──────► Keycloak 26 ◄─────┘   (banco próprio "keycloak" no mesmo PostgreSQL)
                                 │                 ├─ referência: contêineres, rotas, tarifas com vigência, Incoterms, custos, feriados, etapas
                                 └─ engine.py      ├─ operação: projeto, item_carga, volume, conteiner, alocacao, cotacao, marco, documento
                                    (domínio puro) └─ ledger_evento (append-only, hash por trigger)
```

- **A verdade mora no banco.** O motor calcula; o banco decide o que é aceito.
- **Privilégio mínimo.** A API e o seed conectam como `comex_api` (membro de `comex_app`): podem inserir no ledger, mas não alterá-lo nem apagá-lo. Só o RED-TEAM e a manutenção usam o dono do schema.
- **Motor determinístico.** Paridade JS × Python × banco nos 3 demos (SSCC, CG e custo; diferença máxima de 1 centavo).
- **Estado é projeção do ledger.** Registrar uma etapa muda o estado e realiza os marcos por trigger.
- **Gate humano.** Cotação só é aprovada com aprovador identificado; estufagem exige cotação aprovada.

## Invariantes (todas verificadas pelo RED-TEAM)

| ID | Regra (RFC-2119) | Mecanismo |
|---|---|---|
| INV-CMX-001 | Dimensões e peso de item DEVEM estar em faixa física válida | CHECK |
| INV-CMX-002 | Quantidade ≥ 0, seções 1–20, empilhamento 1–3 | CHECK |
| INV-CMX-003 | SSCC DEVE ter 18 dígitos com DV GS1 válido e ser único | CHECK `fn_sscc_valido` + UNIQUE |
| INV-CMX-004 | Número de contêiner DEVE ser ISO 6346 com DV válido | CHECK `fn_iso6346_valido` |
| INV-CMX-005 | Carga alocada NÃO DEVE exceder o payload do tipo | trigger `fn_alocacao_valida` |
| INV-CMX-006 | Volume em no máximo um contêiner, do mesmo projeto | PK + trigger |
| INV-CMX-007 | Volume DEVE caber no piso do contêiner | trigger |
| INV-CMX-008 | Ledger é append-only; hash e seq calculados pelo banco | trigger + REVOKE (papel `comex_app`) |
| INV-CMX-009 | Estado só muda por transição cadastrada | `ref_transicao` + trigger |
| INV-CMX-010 | Itens, volumes, contêineres e alocação congelam após EMBALADO | trigger `fn_carga_congelada` |
| INV-CMX-011 | Etapas do ledger em ordem estrita, sem pular nem repetir | trigger + UNIQUE |
| INV-CMX-012 | Rota e parâmetros de embalagem congelam após EMBALADO | trigger |
| INV-CMX-013 | Cotação só é aprovada com aprovador; aprovada é imutável | CHECK `ck_cot_gate` + triggers |
| INV-CMX-014 | No máximo uma cotação aprovada por projeto | índice único parcial |
| INV-CMX-015 | Documento emitido DEVE ter número e data | CHECK |
| INV-CMX-016 | Peso bruto = líquido + tara | coluna gerada |
| INV-CMX-017 | Câmbio > 0; seguro 0–5 % | CHECK |
| INV-CMX-018 | Uma tarifa por rota × tipo × período | EXCLUDE gist |
| INV-CMX-019 | Caixa externa DEVE exceder o conteúdo | CHECK |
| INV-CMX-020 | CG longitudinal e transversal ≤ 15 % do centro | CHECK |
| INV-CMX-021 | Evento não pode ser anterior ao último nem estar no futuro | trigger |
| INV-CMX-022 | Estufagem exige cotação aprovada | trigger |
| INV-CMX-023 | Embalar exige volumes calculados; estufar exige alocação completa | trigger |
| INV-CMX-024 | Com sessão autenticada, aprovador e assinante DEVEM ser o usuário do token | trigger + `SET LOCAL comex.usuario` |
| INV-CMX-025 | Aprovar exige papel comercial; registrar evento exige papel logística | trigger + `SET LOCAL comex.papeis` |
| INV-CMX-026 | Arquivo de documento é append-only: nova versão, nunca sobrescrita nem apagada | trigger + REVOKE |
| INV-CMX-027 | Versão e SHA-256 calculados pelo banco; o hash do documento só pode ser o da última versão | trigger |
| INV-CMX-028 | Tipo permitido, conteúdo com a assinatura do tipo declarado (PDF, PNG, JPG, XML, XLSX, DOCX), tamanho real = declarado, até 10 MB | trigger + CHECK |
| INV-CMX-029 | Documento emitido não volta a pendente; emissão e anexo exigem papel operacional e registram o usuário | trigger |

### RED-TEAM e testes

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d gpscomex -f /redteam/090_redteam.sql'   # 54 PASS / 0 FAIL
API_URL=http://localhost:8000 pytest -q api/tests                                                 # 30 passed (banco recém-semeado)
```

O RED-TEAM tenta violar cada invariante direto no banco e só passa se o erro citar a invariante esperada. Roda em transação desfeita. Os testes de API cobrem carteira, detalhe, simulação, recusas 409 com código INV, 404, CSV, fluxo de aprovação e evento, e o bloqueio de UPDATE no ledger pelo papel da aplicação. Os de autenticação (`test_auth.py`) usam um JWKS local, sem Keycloak: token válido, expirado, de outro emissor, de outra audiência e com assinatura falsa, filtro de papéis e autorização por papel.

## API (OpenAPI em `/docs`)

| Método | Rota | Função |
|---|---|---|
| GET | `/api/saude` | Saúde e versão do PostgreSQL (pública) |
| GET | `/api/config` | Configuração de login para o PWA (pública) |
| GET | `/api/eu` | Usuário autenticado e papéis |
| GET | `/api/referencias` | Tabelas de referência (tarifas vigentes, Incoterms, etapas…) |
| GET/POST | `/api/clientes` | Clientes |
| GET/POST | `/api/projetos` | Carteira (`vw_projeto_resumo`) / criar projeto com itens |
| GET/PATCH | `/api/projetos/{id}` | Detalhe completo / alterar e recalcular |
| PUT | `/api/projetos/{id}/itens` | Substituir itens e recalcular |
| POST | `/api/projetos/{id}/calcular` | Recalcular embalagem, estufagem, cotação e cronograma |
| POST | `/api/projetos/{id}/cotacoes/{cid}/aprovar` | Aprovação humana da cotação |
| POST | `/api/projetos/{id}/ledger` | Registrar a próxima etapa (ou uma etapa nomeada) |
| GET | `/api/projetos/{id}/ledger/verificar` | Verificação da cadeia pelo banco |
| PATCH | `/api/projetos/{id}/documentos/{tipo}` | Emitir documento (número; emissor vem da sessão) |
| POST | `/api/projetos/{id}/documentos/{tipo}/arquivos` | Anexar arquivo (multipart, até 10 MB) — cria nova versão |
| GET | `/api/projetos/{id}/documentos/{tipo}/arquivos/{versao}` | Baixar versão; cabeçalho `X-Content-SHA256` |
| GET | `/api/projetos/{id}/packing-list.csv` | Packing list (CSV pt-BR) |
| POST | `/api/simular` | Cálculo sem persistência |

Uma violação de invariante vira HTTP 409 com o código `INV-CMX-xxx` no corpo; a interface mostra a mensagem.

## Projetos demo

| Código | Destino | Incoterm | Estágio | Carga |
|---|---|---|---|---|
| CMX-26-0147 | Houston, EUA | DAP | Planejado (2/12) — cotação em rascunho | 21 vol · 23,96 t · 1×40OT + 1×40HC |
| CMX-26-0139 | San Antonio, Chile | CIP | Embarcado (9/12) — eBL emitido | 20 vol · 26,78 t · 2×40HC |
| CMX-26-0121 | Rotterdam, NL | FCA | Entregue (12/12) | 9 vol · 3,54 t · 1×20DV |

## Documentos com prova de integridade

Cada documento do embarque (fatura, packing list, NF-e/DU-E, certificado de origem, ISPM-15, booking, VGM, eBL, seguro, FAT, desembaraço) tem status, número, emissor e arquivos versionados. O responsável segue o Incoterm: documento pago pelo comprador aparece como tal e não é emitido pelo vendedor.

- O arquivo é guardado no PostgreSQL (`documento_arquivo`), em versões imutáveis. O banco calcula o SHA-256 e recusa conteúdo que não corresponde ao tipo declarado: um executável renomeado para `.pdf` não entra.
- Cada evento do ledger registrado depois do anexo carrega `documentos_sha256` com o hash vigente de cada documento. A tela mostra "ancorado no bloco #n", e trocar o arquivo depois gera uma nova versão com hash diferente, sem apagar a ancorada.
- No download, o navegador recalcula o SHA-256 e só salva o arquivo se conferir com o banco.
- Volume: com arquivos de até 10 MB por versão, o banco cresce com os anexos. Inclua isso no dimensionamento de disco e backup; se o volume crescer muito, migre o conteúdo para armazenamento de objetos mantendo o hash no banco.

## Frontend e PWA

- `web/index.html` é a página inicial pública (o que o sistema faz, regras, simulador de Incoterm com os números do motor, dúvidas), com os CTAs **Entrar no sistema** (`app.html`) e **Ver demonstração** (`app.html?demo=1`, sem login). `web/app.html` é o aplicativo; o PWA instalado abre direto nele.
- **Novo embarque pela interface** (papel comercial): código sugerido, cliente existente ou novo, destino, Incoterm, entrega e itens de partida (modelo completo, painel em branco ou cópia de outro embarque). O projeto nasce em RASCUNHO; o pedido é o primeiro evento do ledger.
- Tela de login, sessão com nome e papéis na folha de ajustes, e ações exibidas conforme o papel. O perfil de leitura vê tudo travado.

- Layout responsivo com trilho lateral no desktop, trilho compacto até 1.100 px e barra inferior até 760 px. Tabelas que não cabem no contêiner viram cartões em qualquer largura.
- Auditoria automática de layout em 360, 390, 430, 768, 1024, 1280 e 1440 px, nos 3 projetos e em todas as telas, nos dois modos: 0 elementos fora de card, 0 textos cortados, 0 rolagem horizontal.
- PWA instalável (Chrome sem erros de manifest nem de instalabilidade), service worker com shell em cache: abre offline e nunca guarda `/api/` em cache.
- Temas claro, escuro e sistema.

## Operação

- Recriar do zero (**destrutivo**): task "COMEX: recriar banco do zero" ou `DATABASE_URL=<dono> db/reset.sh` seguido de `python -m app.seed`.
- Backup: `pg_dump -Fc -n comex`. O ledger é trilha probatória: teste o restore e verifique a cadeia depois.
- CORS fica fechado (front e API na mesma origem). Para outro front, defina `CORS_ORIGINS`.
- nginx envia CSP (com a origem do Keycloak), HSTS, `frame-ancestors 'none'`, nosniff, Referrer-Policy e Permissions-Policy em **todas** as rotas. Os cabeçalhos ficam em `seguranca.inc`, incluído em cada location, porque um `add_header` na location anula os herdados do server.
- Backup do Keycloak: o banco `keycloak` entra no mesmo `pg_dump` do cluster. O realm versionado (`keycloak/realm-gplansis.json`) não tem segredos.

## Premissas e limitações

- Fretes, THC, BAF/EFS e custos de embalagem são **estimativas indicativas** (set/2026). Confirme com NVOCC ou armador antes de fechar preço.
- EUA: Section 301 (25 % + 12,5 %) + MFN 2,7 % = 40,2 % — verifique o HTS e as exclusões por item.
- Prefixo GS1 (7890123) e código de dono ISO 6346 (GPS) são fictícios; substitua pelos registrados.
- O link publicado no claude.ai roda só em modo demonstração, sem login.
- No modo demonstração, emitir e anexar funcionam, mas o arquivo não é guardado (só nome e SHA-256 calculado no navegador).
- O tema de login do Keycloak é o padrão; um tema GPlanSiS (Keycloakify ou tema FreeMarker) fica para a próxima onda.
- Offline ou sem API, o app entra em modo demonstração. Não há fila de sincronização: o que for alterado nesse modo não vai para o banco.
