# hermes-pwa

App de celular para o [Hermes Agent](https://github.com/NousResearch/hermes-agent) em formato **PWA**:
uma interface limpa, estilo mensageiro, instalável na tela inicial do Android e do iPhone.

Não é um serviço separado. É um plugin de dashboard: o próprio painel do Hermes serve o app, atrás do
mesmo login, e conversa com o API server do gateway. Por isso você vê no celular as sessões de todos
os canais, como WhatsApp, Telegram, terminal e painel, e continua qualquer uma delas.

## O que o app faz

- **Conversas**: lista com origem, prévia e horário. Busca, nova conversa, renomear e apagar, direto da lista.
- **Agentes**: seletor para trocar entre os perfis do Hermes. Cada agente tem suas próprias conversas.
- **Chat**: respostas em tempo real, Markdown, blocos de código, indicador de "pensando" e de ferramenta em uso.
- **Imagens**: anexar, colar print ou arrastar. O modelo enxerga a imagem.
- **Arquivos**: PDF, planilhas, texto e outros, até 25 MB. Ficam em `~/uploads` do agente, que os lê com as ferramentas de arquivo.
- **Aprovação de comandos**: quando o agente precisa de autorização para um comando perigoso, o pedido aparece no chat com os botões Permitir uma vez, Permitir nesta conversa, Permitir sempre e Negar.
- **Modo de autorização**: no botão de configurações da lista de conversas dá para escolher entre sempre perguntar, modo inteligente ou não perguntar. Vale por agente.
- **Voz**: grava pelo microfone e envia como mensagem de voz, com player para ouvir e a transcrição logo abaixo.
- **Teclado**: Enter envia, Shift+Enter quebra linha.
- **Tema** claro e escuro automáticos. Em tela larga, lista e chat ficam lado a lado.

## Instalação

```bash
hermes plugins install AstraOnlineWeb/hermes-plugins/hermes-pwa --enable
hermes gateway restart
```

Reinicie também o dashboard, ou o contêiner, para a aba aparecer.

### Pré-requisito: API server do gateway

No `.env` do Hermes ou nas variáveis do contêiner:

```
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=<gere com: openssl rand -hex 32>
```

O painel precisa estar acessível por **HTTPS**. Sem isso o navegador não oferece a instalação do app.

## Uso

1. No celular, abra `https://SEU-DOMINIO/pwa` e faça login com o usuário do painel.
2. Android, Chrome: menu ⋮, "Instalar app".
   iPhone, Safari: botão Compartilhar, "Adicionar à Tela de Início".

No computador, a aba **PWA** do painel mostra um QR code com o link. Em qualquer canal do Hermes, o
comando `/pwa` devolve o endereço.

## Opcionais

### Transcrição das mensagens de voz

No painel do Hermes, abra a aba **PWA**, vá até **Transcrição de áudio**, cole a chave do Groq e clique em
**Salvar e conferir**. O Groq tem plano gratuito; a chave é criada em https://console.groq.com/keys.

A chave é conferida na hora e a transcrição passa a valer para os próximos áudios, sem reiniciar o Hermes.

Quem preferir o terminal:

```bash
hermes config set GROQ_API_KEY <sua-chave>
hermes config set stt.provider groq
hermes config set stt.language pt
hermes config set stt.groq.model whisper-large-v3
```

Sem provedor, o áudio ainda é enviado e o agente recebe o arquivo, só não vem transcrito.

### Vários agentes

Para o seletor mostrar outros perfis além do `default`, ligue o gateway multiplexado e dê a cada perfil
a chave do API server:

```bash
hermes -p default config set gateway.multiplex_profiles true
hermes -p <perfil> config set API_SERVER_ENABLED true
hermes -p <perfil> config set API_SERVER_KEY <mesma chave do default>
hermes gateway restart
```

## Como funciona

| Rota | Função |
|---|---|
| `/pwa` | aba do painel. Acesso direto redireciona para o app; pelo menu mostra QR code e instruções |
| `/api/plugins/hermes-pwa/` | o app |
| `/api/plugins/hermes-pwa/api/*` | proxy para o API server do gateway: sessões, mensagens, chat com streaming, upload, perfis |

A chave do API server fica no servidor. O navegador usa só o cookie do dashboard.

## Limitações

- Sem notificações push. Mensagens de outros canais aparecem ao abrir o app, ou a cada 12 segundos com a conversa aberta.
- Imagens enviadas não ficam no histórico do servidor. Ao reabrir a conversa aparece o texto e um marcador.
- A transcrição usa o provedor configurado no perfil `default`.

## Segurança

- Todas as rotas passam pela autenticação do dashboard.
- O login vale 12 horas e se renova por até 30 dias com uso.
- Os nomes de arquivo enviados são sanitizados, e a rota de download só serve arquivos de `~/uploads`, sem subpastas.

## Desenvolvimento

```bash
hermes plugins validate .
python -m pytest tests -q
```

O app é JavaScript puro, sem etapa de build. Os arquivos ficam em `dashboard/pwa/`.

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
