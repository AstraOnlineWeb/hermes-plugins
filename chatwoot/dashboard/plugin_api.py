"""API da aba Chatwoot do painel (montada em /api/plugins/chatwoot/).

Configura o canal Chatwoot sem terminal: cria o Agent Bot no Chatwoot, liga o bot às caixas de
entrada escolhidas e grava a configuração no .env do Hermes. O token de administrador informado
na configuração é usado só nessa hora e não é guardado.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_log = logging.getLogger(__name__)
router = APIRouter()

_PORT_DEFAULT = "8646"
_ROUTE_NAME = "chatwoot"
_PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
_ENV_KEYS = ("CHATWOOT_BASE_URL", "CHATWOOT_BOT_TOKEN", "CHATWOOT_WEBHOOK_SECRET", "CHATWOOT_ALLOW_ALL_USERS",
             "CHATWOOT_ACCOUNT_ID", "CHATWOOT_BOT_ID", "CHATWOOT_BOT_NAME", "CHATWOOT_INBOXES", "CHATWOOT_PUBLIC_URL")


# ── leitura e gravação da configuração ───────────────────────────────────────────

def _env(name: str) -> str:
    try:
        from hermes_cli.config import get_env_value
        return (get_env_value(name) or "").strip()
    except Exception:
        return (os.environ.get(name) or "").strip()


def _save_env(values: Dict[str, str]) -> None:
    from hermes_cli.config import save_env_value
    for key, value in values.items():
        save_env_value(key, value)


def _clear_env() -> None:
    from hermes_cli.config import remove_env_value
    for key in _ENV_KEYS:
        try:
            remove_env_value(key)
        except Exception:
            pass
        os.environ.pop(key, None)


def _clean_base_url(value: str) -> str:
    url = (value or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9._~:\-]+(?:/[A-Za-z0-9._~\-/]*)?", url):
        raise HTTPException(status_code=400, detail="Endereço do Chatwoot inválido. Exemplo: https://chat.seudominio.com.br")
    return url


def _public_base(origin: Optional[str]) -> str:
    """Endereço público do Hermes, usado para montar o webhook que o Chatwoot vai chamar."""
    for candidate in (_env("CHATWOOT_PUBLIC_URL"), _env("HERMES_DASHBOARD_PUBLIC_URL")):
        if candidate:
            return candidate.rstrip("/")
    try:
        from hermes_cli.config import load_config
        url = str((load_config().get("dashboard") or {}).get("public_url") or "").strip()
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    origin = (origin or "").strip().rstrip("/")
    if re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d+)?", origin):
        return origin
    return ""


def _webhook_url(origin: Optional[str], secret: str) -> str:
    base = _public_base(origin)
    return f"{base}/chatwoot/webhook/{secret}" if base and secret else ""


def _profiles() -> List[str]:
    names = ["default"]
    try:
        from hermes_constants import get_hermes_home
        root = Path(get_hermes_home()) / "profiles"
        if root.is_dir():
            names += sorted(p.name for p in root.iterdir() if p.is_dir() and _PROFILE_RE.match(p.name))
    except Exception:
        pass
    return names


def _routed_profile() -> str:
    try:
        from hermes_cli.config import load_config
        for route in (load_config().get("gateway") or {}).get("profile_routes") or []:
            if isinstance(route, dict) and route.get("platform") == "chatwoot" and route.get("name") == _ROUTE_NAME:
                return str(route.get("profile") or "default")
    except Exception:
        pass
    return "default"


def _set_routed_profile(profile: str) -> None:
    """Agente que atende o Chatwoot: uma rota de perfil do gateway (gateway.profile_routes)."""
    from hermes_cli.config import load_config, save_config
    cfg = load_config()
    gateway = dict(cfg.get("gateway") or {})
    routes = [r for r in (gateway.get("profile_routes") or [])
              if not (isinstance(r, dict) and r.get("platform") == "chatwoot" and r.get("name") == _ROUTE_NAME)]
    if profile and profile != "default":
        routes.append({"name": _ROUTE_NAME, "platform": "chatwoot", "profile": profile})
        gateway["multiplex_profiles"] = True
    gateway["profile_routes"] = routes
    cfg["gateway"] = gateway
    save_config(cfg)


async def _listening() -> bool:
    import httpx
    port = _env("CHATWOOT_WEBHOOK_PORT") or _PORT_DEFAULT
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"http://127.0.0.1:{port}/chatwoot/health")
        return r.status_code == 200
    except Exception:
        return False


async def _status(origin: Optional[str] = None) -> Dict[str, Any]:
    token = _env("CHATWOOT_BOT_TOKEN")
    secret = _env("CHATWOOT_WEBHOOK_SECRET")
    configured = bool(_env("CHATWOOT_BASE_URL") and token and secret)
    inboxes = [x for x in _env("CHATWOOT_INBOXES").split("|") if x]
    return {
        "configured": configured,
        "listening": (await _listening()) if configured else False,
        "base_url": _env("CHATWOOT_BASE_URL"),
        "account_id": _env("CHATWOOT_ACCOUNT_ID"),
        "bot_name": _env("CHATWOOT_BOT_NAME"),
        "bot_id": _env("CHATWOOT_BOT_ID"),
        "inboxes": inboxes,
        "token_preview": (token[:3] + "…" + token[-3:]) if len(token) >= 10 else "",
        "webhook_url": _webhook_url(origin, secret) if configured else "",
        "public_base": _public_base(origin),
        "profile": _routed_profile(),
        "profiles": _profiles(),
    }


# ── chamadas ao Chatwoot ─────────────────────────────────────────────────────────

async def _chatwoot(method: str, base: str, path: str, token: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.request(method, f"{base}{path}", json=payload,
                                     headers={"api-access-token": token, "Content-Type": "application/json"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Não foi possível falar com o Chatwoot em {base}: {exc}")
    if r.status_code in (401, 403):
        raise HTTPException(status_code=400, detail="O Chatwoot recusou o token de acesso. Use o token de um administrador da conta.")
    if r.status_code == 404:
        raise HTTPException(status_code=400, detail="Conta ou recurso não encontrado no Chatwoot. Confira o endereço e o ID da conta.")
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"O Chatwoot respondeu com erro {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except Exception:
        return {}


def _payload_list(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        data = data.get("payload", data.get("data", []))
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


class ConnectBody(BaseModel):
    base_url: str
    account_id: int
    access_token: str


class SetupBody(ConnectBody):
    inbox_ids: List[int]
    bot_name: str = "Hermes"
    profile: str = "default"
    origin: Optional[str] = None


class ManualBody(BaseModel):
    base_url: str
    bot_token: str
    profile: str = "default"
    origin: Optional[str] = None


class ProfileBody(BaseModel):
    profile: str


def _check_profile(profile: str) -> str:
    prof = (profile or "default").strip().lower()
    if prof not in _profiles():
        raise HTTPException(status_code=400, detail="Agente não encontrado.")
    return prof


# ── rotas ────────────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config(origin: Optional[str] = None) -> Dict[str, Any]:
    return await _status(origin)


@router.post("/inboxes")
async def list_inboxes(body: ConnectBody) -> Dict[str, Any]:
    base = _clean_base_url(body.base_url)
    token = body.access_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Informe o token de acesso.")
    data = await _chatwoot("GET", base, f"/api/v1/accounts/{body.account_id}/inboxes", token)
    inboxes = [{"id": i.get("id"), "name": i.get("name") or f"Caixa {i.get('id')}",
                "channel": str(i.get("channel_type") or "").replace("Channel::", "")}
               for i in _payload_list(data) if i.get("id") is not None]
    return {"inboxes": inboxes}


@router.post("/setup")
async def setup(body: SetupBody) -> Dict[str, Any]:
    base = _clean_base_url(body.base_url)
    token = body.access_token.strip()
    profile = _check_profile(body.profile)
    name = (body.bot_name or "Hermes").strip()[:60] or "Hermes"
    if not token:
        raise HTTPException(status_code=400, detail="Informe o token de acesso.")
    if not body.inbox_ids:
        raise HTTPException(status_code=400, detail="Escolha pelo menos uma caixa de entrada.")

    secret = _env("CHATWOOT_WEBHOOK_SECRET") or secrets.token_hex(24)
    webhook = _webhook_url(body.origin, secret)
    if not webhook:
        raise HTTPException(status_code=400, detail="Não foi possível descobrir o endereço público do Hermes para o webhook.")

    account = body.account_id
    available = {i.get("id"): i.get("name") for i in _payload_list(
        await _chatwoot("GET", base, f"/api/v1/accounts/{account}/inboxes", token))}
    missing = [i for i in body.inbox_ids if i not in available]
    if missing:
        raise HTTPException(status_code=400, detail=f"Caixa de entrada não encontrada: {missing}")

    # Reaproveita o bot criado antes por este plugin (mesmo id) em vez de criar outro a cada vez.
    bot_payload = {"name": name, "description": "Agente de IA do Hermes", "outgoing_url": webhook}
    bot: Dict[str, Any] = {}
    bot_id = _env("CHATWOOT_BOT_ID")
    if bot_id and _env("CHATWOOT_BASE_URL") == base and _env("CHATWOOT_ACCOUNT_ID") == str(account):
        try:
            bot = await _chatwoot("PATCH", base, f"/api/v1/accounts/{account}/agent_bots/{bot_id}", token, bot_payload)
        except HTTPException:
            bot = {}
    if not bot.get("id"):
        bot = await _chatwoot("POST", base, f"/api/v1/accounts/{account}/agent_bots", token, bot_payload)
    bot_token = str(bot.get("access_token") or "").strip() or _env("CHATWOOT_BOT_TOKEN")
    if not bot.get("id") or not bot_token:
        raise HTTPException(status_code=400, detail=(
            "O Chatwoot criou o bot mas não devolveu o token dele. Copie o token do bot em "
            "Configurações > Bots no Chatwoot e use a configuração manual."))

    for inbox_id in body.inbox_ids:
        await _chatwoot("POST", base, f"/api/v1/accounts/{account}/inboxes/{inbox_id}/set_agent_bot", token,
                        {"agent_bot": bot["id"]})

    try:
        _save_env({
            "CHATWOOT_BASE_URL": base, "CHATWOOT_BOT_TOKEN": bot_token, "CHATWOOT_WEBHOOK_SECRET": secret,
            "CHATWOOT_ALLOW_ALL_USERS": "true", "CHATWOOT_ACCOUNT_ID": str(account),
            "CHATWOOT_BOT_ID": str(bot["id"]), "CHATWOOT_BOT_NAME": name,
            "CHATWOOT_INBOXES": "|".join(str(available.get(i) or i) for i in body.inbox_ids),
        })
        _set_routed_profile(profile)
    except Exception as exc:
        _log.exception("chatwoot: falha ao salvar a configuração")
        raise HTTPException(status_code=500, detail=f"Bot criado no Chatwoot, mas não foi possível salvar no Hermes: {exc}")
    return await _status(body.origin)


@router.post("/manual")
async def manual(body: ManualBody) -> Dict[str, Any]:
    base = _clean_base_url(body.base_url)
    token = body.bot_token.strip()
    profile = _check_profile(body.profile)
    if not re.fullmatch(r"[A-Za-z0-9_\-]{10,120}", token):
        raise HTTPException(status_code=400, detail="Token do bot inválido.")
    secret = _env("CHATWOOT_WEBHOOK_SECRET") or secrets.token_hex(24)
    try:
        _save_env({"CHATWOOT_BASE_URL": base, "CHATWOOT_BOT_TOKEN": token, "CHATWOOT_WEBHOOK_SECRET": secret,
                   "CHATWOOT_ALLOW_ALL_USERS": "true"})
        _set_routed_profile(profile)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não foi possível salvar: {exc}")
    return await _status(body.origin)


@router.post("/profile")
async def set_profile(body: ProfileBody) -> Dict[str, Any]:
    profile = _check_profile(body.profile)
    try:
        _set_routed_profile(profile)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não foi possível salvar: {exc}")
    return await _status()


@router.post("/restart")
def restart_gateway() -> Dict[str, Any]:
    """Pede ao gateway um reinício gracioso (SIGUSR1): ele termina o que está fazendo, sai, e o
    gerenciador de serviço (systemd, s6) o sobe de novo já com o canal configurado."""
    import json
    import signal
    try:
        from hermes_constants import get_hermes_home
        raw = (Path(get_hermes_home()) / "gateway.pid").read_text(encoding="utf-8").strip()
        pid = int(json.loads(raw)["pid"]) if raw.startswith("{") else int(raw)
        os.kill(pid, signal.SIGUSR1)
        return {"ok": True, "method": "signal"}
    except Exception as exc:
        _log.info("chatwoot: reinício por sinal indisponível (%s); usando o reinício do painel", exc)
    try:
        from hermes_cli.web_server import _spawn_gateway_restart
        _spawn_gateway_restart(None)
        return {"ok": True, "method": "painel"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não foi possível reiniciar o gateway: {exc}")


@router.delete("/config")
async def delete_config() -> Dict[str, Any]:
    try:
        _clear_env()
        _set_routed_profile("default")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não foi possível remover: {exc}")
    return await _status()
