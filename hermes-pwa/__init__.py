"""hermes-pwa — registra o comando /pwa (devolve o link do app móvel).

A parte principal do plugin é a extensão de dashboard em ``dashboard/`` (aba PWA + API que
serve o app e faz proxy para o API server do gateway).
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress

logger = logging.getLogger(__name__)


def pwa_url() -> str:
    base = (os.environ.get("HERMES_DASHBOARD_PUBLIC_URL") or "").strip().rstrip("/")
    if not base:
        try:
            from hermes_cli.config import load_config_readonly
            base = str(((load_config_readonly() or {}).get("dashboard") or {}).get("public_url") or "").rstrip("/")
        except Exception:
            base = ""
    return f"{base}/pwa" if base else "/pwa"


def cmd_pwa(raw_args: str = "") -> str:
    return (
        "📱 App móvel do Hermes (PWA)\n"
        f"Abra no celular: {pwa_url()}\n"
        "Faça login, toque em \"Abrir app\" e depois em \"Adicionar à tela inicial\"."
    )


def register(ctx) -> None:
    with suppress(Exception):
        ctx.register_command("pwa", handler=cmd_pwa, description="Mostra o link do app móvel (PWA) do Hermes")
    logger.info("hermes-pwa: comando /pwa registrado")
