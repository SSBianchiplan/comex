## O que muda
<!-- Resumo da mudança e o porquê. Referencie a issue: "Fecha #123". -->

## Tipo
- [ ] Correção de bug
- [ ] Nova funcionalidade
- [ ] Documentação
- [ ] Refatoração / manutenção

## Como testei
<!-- Passos, ambiente (local/Docker), navegadores. Cole o resumo do `pytest` e do RED-TEAM. -->

## Capturas
<!-- Se mexeu na interface, antes/depois — só com os 3 projetos demo, nunca com embarques reais. -->

## Checklist
- [ ] `pytest -q api/tests` passa (banco recém-semeado)
- [ ] RED-TEAM do banco (`db/090_redteam.sql`) continua 100% PASS; regra nova ganhou caso de ataque
- [ ] Invariante nova está no banco (CHECK/trigger) e tem código `INV-CMX-xxx`, não só na API ou na tela
- [ ] Paridade do motor: JS (`web/app.html`) × Python (`api/app/engine.py`) × banco nos 3 demos
- [ ] Permissão por papel conferida na API e no banco
- [ ] Sem segredos, `.env`, dumps ou dados reais de importação/exportação no commit
- [ ] `CHANGELOG.md` atualizado (se visível para o usuário)
