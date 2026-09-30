# chatwoot

Canal **Chatwoot** para o [Hermes Agent](https://github.com/NousResearch/hermes-agent): o agente atende os
clientes nas caixas de entrada do Chatwoot e passa a conversa para um atendente humano quando precisa.

O Hermes entra no Chatwoot como **Agent Bot**. Funciona com qualquer canal ligado à caixa de entrada
(WhatsApp, site, Instagram, e-mail, API).

## O que faz

- **Responde clientes**: cada mensagem recebida na caixa de entrada vai para o agente, e a resposta volta pelo Chatwoot.
- **Contexto por conversa**: cada conversa do Chatwoot é uma sessão do Hermes. O agente lembra do que já foi dito nela.
- **Imagens e áudios**: o agente recebe as imagens e os áudios enviados pelo cliente.
- **Transferência para humano**: quando o cliente pede ou o agente não resolve, a conversa passa para a fila humana
  (situação "Aberta") com uma nota interna.
- **Para quando um humano assume**: o agente só responde conversas na situação "Pendente". Em "Aberta" ele se cala.
- **Devolução ao agente**: mude a conversa para "Pendente" no Chatwoot e o agente volta a atender.
- **Escolha do agente**: a aba permite escolher qual agente (perfil) do Hermes atende.
- **Proteções**: mensagens de cliente que começam com `/` são tratadas como texto comum, e pedidos de aprovação
  de comando nunca são enviados ao cliente (são negados na hora).

## Instalação

```bash
hermes plugins install AstraOnlineWeb/hermes-plugins/chatwoot --enable
```

Reinicie o Hermes. O [auto instalador](https://github.com/AstraOnlineWeb/hermes-autoinstall) já instala este
plugin e prepara o endereço do webhook.

## Configuração

No painel do Hermes, abra a aba **Chatwoot**.

### Automática

1. Informe o endereço do Chatwoot, o ID da conta e o token de acesso de um administrador
   (no Chatwoot: Configurações do perfil > Token de acesso).
2. Clique em **Buscar caixas de entrada** e marque as que o agente vai atender.
3. Escolha o nome do bot e o agente do Hermes, e clique em **Conectar**.

O plugin cria o bot no Chatwoot, liga o bot às caixas escolhidas, grava a configuração e reinicia o gateway.
O token de administrador é usado só nessa hora e não fica guardado.

### Manual

Para usar um bot que já existe: informe o endereço do Chatwoot e o token do bot. Depois copie o webhook
mostrado na aba para o campo de URL do bot no Chatwoot e ligue o bot à caixa de entrada.

## Endereço do webhook

O Chatwoot precisa alcançar o Hermes em:

```
https://SEU-HERMES/chatwoot/webhook/<segredo>
```

O canal escuta na porta **8646** do Hermes (só em `127.0.0.1` por padrão). O proxy precisa encaminhar
`/chatwoot/webhook/*` para essa porta. O auto instalador já faz isso. Em outras instalações:

**Caddy**

```
@chatwoot path /chatwoot/webhook/*
handle @chatwoot {
	reverse_proxy 127.0.0.1:8646
}
```

**Traefik (labels do serviço do Hermes)**

```
traefik.http.routers.hermes-chatwoot.rule=Host(`hermes.seudominio.com.br`) && PathPrefix(`/chatwoot/webhook`)
traefik.http.routers.hermes-chatwoot.entrypoints=websecure
traefik.http.routers.hermes-chatwoot.tls.certresolver=letsencryptresolver
traefik.http.routers.hermes-chatwoot.service=hermes-chatwoot
traefik.http.services.hermes-chatwoot.loadbalancer.server.port=8646
```

Em container, defina `CHATWOOT_WEBHOOK_HOST=0.0.0.0` para o proxy alcançar a porta.

## Como o agente transfere

O agente termina a resposta com o marcador `[TRANSFERIR]`. O plugin remove o marcador, envia a mensagem ao
cliente, muda a conversa para "Aberta" e deixa uma nota interna. O agente já recebe essa instrução; para
ajustar quando transferir, escreva as regras no `SOUL.md` do agente.

## Variáveis

Ficam no `.env` do Hermes. A aba grava as principais.

| Variável | Padrão | Descrição |
|---|---|---|
| `CHATWOOT_BASE_URL` | | endereço do Chatwoot |
| `CHATWOOT_BOT_TOKEN` | | token de acesso do Agent Bot |
| `CHATWOOT_WEBHOOK_SECRET` | gerado | segredo que compõe o endereço do webhook |
| `CHATWOOT_WEBHOOK_PORT` | `8646` | porta local do webhook |
| `CHATWOOT_WEBHOOK_HOST` | `127.0.0.1` | endereço de escuta. Em container, `0.0.0.0` |
| `CHATWOOT_REPLY_STATUSES` | `pending` | situações em que o agente responde, separadas por vírgula |
| `CHATWOOT_ALLOW_ALL_USERS` | `true` | atende qualquer contato |
| `CHATWOOT_PUBLIC_URL` | endereço do painel | endereço público do Hermes usado no webhook |
| `CHATWOOT_HOME_CHANNEL` | | conversa padrão para avisos e agendamentos, no formato `conta:conversa` |

## Segurança

Quem escreve nesse canal são **clientes**, não o dono do sistema.

- Use um agente (perfil) próprio para atendimento, com as ferramentas de terminal e de arquivos desligadas.
- Não deixe esse agente no modo de autorização "Não perguntar" com terminal ligado: um cliente pode tentar
  induzir o agente a executar comandos.
- O webhook é protegido por um segredo no endereço. Não divulgue o endereço.
- Para atender clientes em volume, prefira chave de API do provedor de IA. Assinaturas pessoais podem não
  permitir esse uso.

## Observações

- A aba usa o cabeçalho `api-access-token` (com traço) ao falar com o Chatwoot, porque alguns proxies descartam
  cabeçalhos com sublinhado.
- Requer Chatwoot com Agent Bots pela API (testado na versão 4.18).
- "Desconectar" remove a configuração do Hermes. O bot continua existindo no Chatwoot.
