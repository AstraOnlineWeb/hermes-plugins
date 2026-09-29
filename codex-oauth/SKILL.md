---
name: connect-codex
description: Conectar o Hermes à assinatura ChatGPT/Codex via OAuth (device code) usando as ferramentas do plugin codex-oauth.
version: 1.0.0
---

# Conectar Codex via OAuth

## Quando usar
- O usuário pede para "conectar", "logar" ou "usar" a conta ChatGPT / Codex / OpenAI por assinatura.
- Nenhum provedor de LLM está configurado e o usuário tem assinatura ChatGPT Plus/Pro/Team.

## Procedimento
1. `codex_oauth_status` — se `ready` for true, informe que já está conectado e pare.
2. `codex_oauth_start` — mostre ao usuário, sem alterar, `verification_url` e `user_code`.
   Diga que o código vale 15 minutos e que ele deve fazer login na conta que tem a assinatura.
3. Aguarde o usuário dizer que aprovou (ou consulte a cada ~10 s) com `codex_oauth_check`.
   - `approved`: tokens salvos. Siga para o passo 4.
   - `expired`/`error`: explique e ofereça `codex_oauth_start` com `force=true`.
4. `codex_oauth_set_model` (padrão `gpt-5.5`; alternativas em `suggested_models`).
5. Avise que o gateway precisa ser reiniciado para o novo provedor valer em todas as sessões.

## Armadilhas
- Nunca invente ou "corrija" o código; ele é sensível a caracteres.
- Não peça senha nem chave de API: o fluxo é feito no navegador do usuário.
- Se `codex_oauth_start` disser `already_connected`, não gere outro código sem o usuário pedir.

## Verificação
`codex_oauth_status` deve retornar `logged_in: true` e `model.provider: openai-codex`.
