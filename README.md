# Hermes Plugins

Plugins da comunidade para o [Hermes Agent](https://github.com/NousResearch/hermes-agent), da Nous Research.
Feitos para quem roda o Hermes em servidor próprio e quer usar assinatura em vez de chave de API,
e conversar com o agente pelo celular.

| Plugin | O que faz |
|---|---|
| [`codex-oauth`](codex-oauth/) | Conecta as assinaturas **ChatGPT/Codex** e **Claude Max** por OAuth, direto pelo painel, pelo chat ou pela CLI. Funciona mesmo com o chat em "Setup Required". |
| [`hermes-pwa`](hermes-pwa/) | App de celular em formato **PWA**, estilo mensageiro: todas as sessões, troca de agente, imagens, arquivos e mensagens de voz com transcrição. |

## Instalação

```bash
hermes plugins install AstraOnlineWeb/hermes-plugins/codex-oauth --enable
hermes plugins install AstraOnlineWeb/hermes-plugins/hermes-pwa --enable
hermes gateway restart
```

Reinicie também o dashboard, ou o contêiner inteiro, para as abas novas aparecerem.

### Em Docker (imagem oficial `nousresearch/hermes-agent`)

```bash
docker exec <container> hermes plugins install AstraOnlineWeb/hermes-plugins/codex-oauth --enable
docker exec <container> hermes plugins install AstraOnlineWeb/hermes-plugins/hermes-pwa --enable
docker restart <container>          # em Swarm: docker service update --force <serviço>
```

Os plugins ficam no volume de dados (`/opt/data/plugins`), então sobrevivem a atualizações da imagem.

### Conferir

```bash
hermes plugins list
```

Os dois devem aparecer como `enabled`. No painel surgem as abas **Codex / Claude** e **PWA**.

### Atualizar

```bash
hermes plugins update codex-oauth
hermes plugins update hermes-pwa
```

## Requisitos

- Hermes Agent v0.21 ou mais novo, com o dashboard acessível por HTTPS.
- Para o `hermes-pwa`: API server do gateway ligado. Veja o [README do plugin](hermes-pwa/).
- Para o `codex-oauth`: assinatura ChatGPT Plus, Pro ou Team, ou Claude Max com créditos extras.

## Segurança

- Nenhum plugin guarda senha ou chave no código. Domínio, chaves e caminhos são lidos do ambiente do Hermes.
- Os logins OAuth acontecem no navegador do usuário, nos domínios da OpenAI e da Anthropic. Os tokens são gravados pelo próprio Hermes.
- Todas as rotas dos plugins passam pela autenticação do dashboard.

## Desenvolvimento

```bash
hermes plugins validate codex-oauth
hermes plugins validate hermes-pwa
python -m pytest codex-oauth/tests hermes-pwa/tests -q
```

## Licença

MIT. Projeto independente, sem vínculo com a Nous Research.

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
