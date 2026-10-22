# Política de segurança

## Versões suportadas
| Versão | Suporte |
|---|---|
| 1.2.x (em produção em comex.gplansis.com) | ✅ |
| < 1.2 | ❌ |

## Como relatar uma vulnerabilidade
**Não abra issue pública.** Envie um e-mail para **contato@gplansis.com** com o assunto `[SEGURANÇA] GPlanSiS|Comex`, contendo:
- descrição do problema e impacto;
- passos para reproduzir (ou prova de conceito);
- versão/commit, navegador e ambiente usados.

Confirmamos o recebimento assim que possível, mantemos você informado sobre a correção e damos crédito na publicação, se desejar.

## Escopo
Autenticação OIDC e validação de tokens, papéis e autorização (API e banco), integridade do ledger e dos documentos versionados, upload de arquivos, gestão de usuários pela Admin API do Keycloak, CSP e cabeçalhos do nginx, exposição do console do Keycloak.

Testes devem ser feitos numa **instância local** com os projetos demo — **não** teste contra comex.gplansis.com nem tente acessar dados de outras pessoas. Uma forma rápida de achar furos é propor um ataque novo para `db/090_redteam.sql`.
