# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

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
