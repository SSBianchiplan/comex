# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [1.2.1] — 2026-10-22
Correções da auditoria de segurança de outubro de 2026.

### Segurança
- Keycloak 26.0.7 → **26.7.5** (CVE-2026-18963 / GHSA-4gv3-mc9p-5wqc, tomada de conta pelo reset de senha, e demais avisos da linha 26.0). O banco do Keycloak migra sozinho na subida; o tema de login foi portado para o `template.ftl` do 26.7.
- Realm: `resetPasswordAllowed: false` e sem redirect fixo para `http://localhost:*` (a 2ª URI vem de `COMEX_URL_DEV`, só no compose local).
- FastAPI 0.149 + Starlette 1.9.0 (GHSA-7f5h-v6xp-fcq8, GHSA-82w8-qh3p-5jfq e outros), certifi 2026.10.19 (GHSA-6q48-6c7w-9gw2), dependências com versão exata.
- nginx 1.27 (sem suporte) → 1.30.6 estável, `server_tokens off`.
- `/api/simular` e o cálculo de projeto com limites (100 itens, 200 por linha, 600 volumes, parâmetros do motor validados) e fora do laço de eventos.
- `AUTH_MODE` passa a valer `oidc` por padrão no código; valor desconhecido impede a subida.
- Erro interno do banco não volta mais ao cliente; CSV do packing list neutraliza fórmulas.
- `deploy/enviar.sh` sem `rsync --delete`.

### Corrigido
- O seed não terminava quando os projetos já existiam (pool aberto) e travava o `compose up`.

## [1.2.0] — 2026-10-22
Primeira publicação do código, igual ao que está no ar em comex.gplansis.com.

### Incluído
- Motor de embalagem ISPM-15, estufagem com centro de gravidade, cotação por Incoterm 2020 e cronograma reverso.
- Ledger GS1 EPCIS encadeado por SHA-256 com 12 etapas e verificação pelo banco.
- Documentos do embarque com arquivos versionados e hash ancorado no ledger.
- 29 invariantes `INV-CMX-001` a `029` no PostgreSQL e RED-TEAM com 54 ataques.
- Login pelo Keycloak (OIDC + PKCE), 4 papéis, identidade gravada na transação e gestão de usuários pela interface.
- PWA com modo demonstração, página pública com simulador de Incoterm, temas claro/escuro.

### Publicação
- E-mail e nome pessoais removidos do realm do Keycloak, do `.env.example` e do `LEIAME.md`; o admin master agora vem de `COMEX_ADMIN_EMAIL`.
- README, capa, guias de contribuição e segurança, modelos de issue e PR, licença MIT.
