# Como contribuir com o GPlanSiS|Comex

Obrigado pelo interesse! Este guia explica como propor mudanças de forma que a revisão seja rápida.

## Antes de começar
- Leia o [código de conduta](CODE_OF_CONDUCT.md).
- Para mudanças maiores que uma correção pontual, **abra uma issue primeiro** (modelos "Ideia" ou "Bug") e combine a abordagem.
- Falhas de segurança **não** vão em issue pública: siga a [política de segurança](SECURITY.md).

## Ambiente de desenvolvimento
Siga [Como rodar localmente](README.md#como-rodar-localmente). O caminho mais curto é a API com `AUTH_MODE=desligado` servindo o PWA (`WEB_DIR=../web`) contra um PostgreSQL 16 com `db/001` a `003` aplicados e o seed dos 3 demos — ou as tarefas e o F5 do VS Code (`.vscode/`).

O frontend (`web/`) não tem etapa de build: edite e recarregue (se o service worker segurar uma versão antiga, use recarga forçada ou suba `VERSAO` em `web/sw.js`).

## Organização do código
- `db/002_regras.sql` — **onde moram as regras**: CHECKs, triggers e permissões de cada `INV-CMX-xxx`.
- `api/app/engine.py` — motor puro (sem banco): embalagem, estufagem, CG, cotação, cronograma. O mesmo cálculo existe em JS em `web/app.html` para o modo demonstração.
- `api/app/servico.py` — orquestra motor e banco; `main.py` — rotas; `auth.py` — OIDC e papéis.
- `db/090_redteam.sql` — um ataque por invariante.

## Regras do projeto
- **Invariante nova vai para o banco** com código `INV-CMX-xxx` e ganha um caso no RED-TEAM. A API e a tela só repetem a regra para dar uma mensagem melhor.
- **Paridade do motor**: mudou o cálculo em `engine.py`? Mude também em `web/app.html` e confira os 3 demos (diferença máxima de 1 centavo).
- **Ledger é append-only**: nunca escreva código que precise de UPDATE/DELETE em `ledger_evento` ou `documento_arquivo`.
- **Papel no servidor**: toda ação nova confere o papel na API e, quando grava, no banco (`comex.papeis`).
- **Gate humano**: nada aprova cotação ou registra evento sem uma pessoa identificada.
- **Interface em português do Brasil**, textos curtos e diretos; sem dependências de build.
- **Dados**: use só os projetos demo. Nunca inclua faturas, DU-E, conhecimentos, NCM de clientes, nomes de compradores reais, segredos, `.env` ou dumps em commits, testes, issues ou capturas. Integrações externas (câmbio, NCM, Siscomex) entram só por variável de ambiente, nunca com chave no código.

## Antes de abrir o PR
```bash
psql -d gpscomex -f db/090_redteam.sql                       # todos PASS
PYTHONPATH=api API_URL=http://localhost:8000 pytest -q api/tests   # banco recém-semeado
```

## Pull requests
1. Faça um fork e crie uma branch a partir de `main` (`feat/…`, `fix/…`, `docs/…`).
2. Commits pequenos, com mensagem no imperativo explicando o porquê.
3. Preencha o modelo do PR: o que mudou, como testou, capturas se mexer na interface.
4. Atualize o `CHANGELOG.md` quando a mudança for visível para quem usa.

## Dúvidas
Abra uma issue com o modelo "Pergunta" ou escreva para contato@gplansis.com.
