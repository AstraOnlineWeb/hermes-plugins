# codex-oauth

Plugin para o [Hermes Agent](https://github.com/NousResearch/hermes-agent) que conecta o agente às
suas **assinaturas**, sem chave de API:

- **ChatGPT / Codex** (Plus, Pro ou Team), por OAuth device code.
- **Claude Max** (Anthropic), por OAuth PKCE.

O login pode ser feito pela aba do painel, pelo chat de qualquer canal ou pela CLI. A aba do painel
funciona mesmo quando o chat está em "Setup Required", que é o estado do Hermes sem nenhum provedor
configurado.

## Instalação

```bash
hermes plugins install AstraOnlineWeb/hermes-plugins/codex-oauth --enable
hermes gateway restart
```

Em Docker, rode o mesmo comando com `docker exec <container>` na frente e reinicie o contêiner.

## Uso

### Pelo painel (recomendado)

Menu lateral, aba **Codex / Claude**.

**Codex**: clique em "Conectar ao Codex". A página mostra o link e o código. Abra o link, entre na
conta ChatGPT, digite o código. A página detecta a aprovação sozinha, salva os tokens e define
`openai-codex` como provedor padrão.

**Claude**: clique em "Conectar ao Claude" e depois em "Abrir". Autorize na conta Claude. A Anthropic
mostra um código; cole no campo e confirme. Depois escolha o modelo e clique em "Usar Claude como padrão".

### Pelo chat

| Comando | O que faz |
|---|---|
| `/codex-login` | inicia o login Codex e mostra link e código |
| `/codex-status` | mostra se está conectado e qual modelo está ativo |
| `/codex-model <modelo>` | define o modelo Codex padrão, ou lista os sugeridos |
| `/claude-login` | inicia o login Claude e mostra a URL de autorização |
| `/claude-code <código>` | conclui o login Claude com o código exibido pela Anthropic |
| `/claude-status` | mostra se o Claude está conectado |
| `/claude-model <modelo>` | define o modelo Claude padrão |

Os comandos de barra precisam de uma sessão aberta. Sem nenhum provedor configurado, use a aba do painel.

### Pela CLI

```bash
hermes codex-oauth login            # mostra link e código e espera a aprovação
hermes codex-oauth status
hermes codex-oauth set-model gpt-5.5
hermes codex-oauth claude-login     # mostra a URL e pede o código
hermes codex-oauth claude-set-model claude-sonnet-4-6
```

## O que o plugin registra

| Tipo | Nomes |
|---|---|
| Ferramentas Codex | `codex_oauth_status`, `codex_oauth_start`, `codex_oauth_check`, `codex_oauth_set_model`, `codex_oauth_cancel` |
| Ferramentas Claude | `claude_oauth_status`, `claude_oauth_start`, `claude_oauth_submit`, `claude_oauth_set_model` |
| Comandos de barra | os sete da tabela acima |
| CLI | `hermes codex-oauth ...` |
| Aba no painel | **Codex / Claude**, em `/codex` |
| System prompt | `codex-oauth.guide`, que ensina o agente a conduzir o login |
| Skill | `codex-oauth:connect-codex` |

## Configuração opcional

Em `config.yaml`:

```yaml
plugins:
  entries:
    codex-oauth:
      settings:
        default_model: gpt-5.5     # modelo aplicado após o login Codex
        auto_set_model: true       # false = só salva os tokens
```

## Problemas comuns

**"The 'gpt-5.4' model is not supported when using Codex with a ChatGPT account"**
Cada plano ChatGPT libera um conjunto diferente de modelos no Codex. Troque na aba, no cartão
"Modelo padrão", ou com `/codex-model`. O padrão do plugin é `gpt-5.5`; se o seu plano recusar, tente outro da lista.

**O login do Claude é recusado**
A Anthropic só aceita esse fluxo em contas **Claude Max com créditos extras de uso**. Contas Pro não
funcionam. A alternativa é cadastrar `ANTHROPIC_API_KEY` na página de chaves.

**O chat continua em "Setup Required" depois de conectar**
O plugin reavalia esse estado sozinho. Se persistir, recarregue a página ou reinicie o dashboard.

**Os logins sumiram**
Os tokens de renovação são de uso único. Se o disco do servidor encher, o Hermes gasta o token e não
consegue gravar o novo. Libere espaço e conecte de novo.

## Segurança

- O plugin não recebe senha nem chave. O login acontece no navegador, nos domínios da OpenAI e da Anthropic.
- Os tokens são gravados pelo próprio Hermes em `auth.json`, no mesmo lugar do `hermes auth add`.
- Identificadores internos do fluxo, como `device_auth_id` e o verificador PKCE, nunca saem do servidor.
- Quem tem acesso ao chat do agente consegue iniciar um login. Mantenha as listas de usuários permitidos dos canais restritas.

## Desenvolvimento

```bash
hermes plugins validate .
python -m pytest tests -q
```

Licença MIT.

---

## Suporte e serviços

Precisa de ajuda para melhorar, customizar ou implementar o projeto?

📱 **WhatsApp:** [+55 61 9 9687-8959](https://wa.me/5561996878959)

💼 Temos uma equipe especializada para:

- ✅ Customizações e melhorias
- ✅ Implementação e deploy completo
- ✅ Configuração de arquitetura SaaS
- ✅ Integração com outras APIs
- ✅ Desenvolvimento de features específicas
- ✅ Suporte técnico dedicado
- ✅ Consultoria em automação WhatsApp
- ✅ Treinamento e documentação
