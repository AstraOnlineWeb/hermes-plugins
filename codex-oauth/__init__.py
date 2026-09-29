"""codex-oauth — login OAuth (device code) na assinatura ChatGPT/Codex pelo chat, dashboard ou CLI.

Registra:
  * ferramentas ``codex_oauth_*`` para o agente conduzir o login com o usuário;
  * comandos de barra ``/codex-login``, ``/codex-status`` e ``/codex-model``;
  * subcomando ``hermes codex-oauth``;
  * uma seção de system prompt que ensina o agente a usar tudo isso;
  * a skill ``codex-oauth:connect-codex`` com o passo a passo.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path

from . import cli as _cli
from . import tools as _tools

logger = logging.getLogger(__name__)

_GUIDE = (
    "Codex OAuth: quando o usuário pedir para conectar/logar a conta ChatGPT ou Codex, ou quando "
    "nenhum provedor de LLM estiver configurado, use as ferramentas codex_oauth_*: primeiro "
    "codex_oauth_status; se não estiver conectado, codex_oauth_start e mostre ao usuário a URL e "
    "o código exatamente como retornados; depois codex_oauth_check até 'approved'. Com o login "
    "aprovado, confirme o modelo com codex_oauth_set_model (sugestão: gpt-5.5). Os comandos "
    "/codex-login, /codex-status e /codex-model fazem o mesmo sem passar pelo modelo. Para a conta "
    "Claude Pro/Max (Anthropic) use claude_oauth_status, claude_oauth_start (mostre auth_url), peça ao "
    "usuário o código exibido pela Anthropic e envie em claude_oauth_submit; depois claude_oauth_set_model."
)


def register(ctx) -> None:
    for name, schema, handler, emoji in _tools.TOOLS:
        ctx.register_tool(name=name, toolset="codex_oauth", schema=schema, handler=handler,
                          emoji=emoji, description=schema["description"])

    # Os registros abaixo não são ferramentas; em sondas de validação com ctx mínimo podem não
    # existir, por isso cada um é protegido individualmente.
    for name, handler, description, hint in _tools.COMMANDS:
        with suppress(Exception):
            ctx.register_command(name, handler=handler, description=description, args_hint=hint)

    with suppress(Exception):
        ctx.register_cli_command(
            name="codex-oauth",
            help="Login OAuth na assinatura ChatGPT/Codex (login, status, set-model)",
            setup_fn=_cli.register_cli, handler_fn=_cli.command,
            description="Conecta o Hermes ao Codex via device code sem precisar do dashboard.",
        )

    with suppress(Exception):
        ctx.register_system_prompt_section(id="codex-oauth.guide", content=_GUIDE)

    skill = Path(__file__).parent / "SKILL.md"
    if skill.exists():
        with suppress(Exception):
            ctx.register_skill(name="connect-codex", path=skill,
                               description="Passo a passo para conectar a assinatura ChatGPT/Codex via OAuth")

    logger.info("codex-oauth: plugin registrado (%d ferramentas)", len(_tools.TOOLS))
