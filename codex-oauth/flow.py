"""Fluxo OAuth device-code do OpenAI Codex, executado em segundo plano com consulta de status.

Reutiliza as funções internas do Hermes (``hermes_cli.auth_codex``) para pedir o código,
trocar o authorization_code por tokens e gravar no ``auth.json``. A única parte reescrita é o
loop de polling, para que ele rode em uma thread e o chamador (ferramenta, comando de barra ou
CLI) consiga devolver o link e o código ao usuário antes da aprovação — exatamente como o
dashboard faz na aba Accounts.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ISSUER = "https://auth.openai.com"
VERIFICATION_URL = f"{ISSUER}/codex/device"
EXPIRES_IN = 15 * 60  # OpenAI expira o device code em 15 minutos
PROVIDER_ID = "openai-codex"
FALLBACK_MODELS = ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex"]
DEFAULT_MODEL = "gpt-5.5"

_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


# ── helpers internos ─────────────────────────────────────────────────────────────

def _client_id() -> str:
    from hermes_cli.auth_constants import CODEX_OAUTH_CLIENT_ID
    return CODEX_OAUTH_CLIENT_ID


def _gc() -> None:
    """Remove sessões encerradas há mais de 1 h."""
    now = time.time()
    with _lock:
        stale = [sid for sid, s in _sessions.items()
                 if s["status"] != "pending" and s.get("finished_at", s["expires_at"]) + 3600 < now]
        for sid in stale:
            _sessions.pop(sid, None)


def public(sess: Dict[str, Any]) -> Dict[str, Any]:
    """Visão segura da sessão (sem device_auth_id)."""
    remaining = max(0, int(sess["expires_at"] - time.time())) if sess["status"] == "pending" else 0
    out = {
        "session_id": sess["id"],
        "status": sess["status"],
        "verification_url": sess["verification_url"],
        "user_code": sess["user_code"],
        "expires_in_seconds": remaining,
    }
    if sess.get("error"):
        out["error"] = sess["error"]
    return out


def get_session(session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Sessão pelo id, ou a mais recente quando ``session_id`` é vazio."""
    with _lock:
        if session_id:
            return _sessions.get(session_id)
        if not _sessions:
            return None
        return max(_sessions.values(), key=lambda s: s["started_at"])


def pending_session() -> Optional[Dict[str, Any]]:
    with _lock:
        live = [s for s in _sessions.values() if s["status"] == "pending" and s["expires_at"] > time.time()]
    return max(live, key=lambda s: s["started_at"]) if live else None


# ── fluxo ────────────────────────────────────────────────────────────────────────

def start(force: bool = False) -> Dict[str, Any]:
    """Pede um device code à OpenAI e inicia o polling em background.

    Reaproveita uma sessão pendente (o usuário pode ter pedido duas vezes) a menos que
    ``force`` seja True. Levanta ``AuthError``/``RuntimeError`` se a OpenAI recusar.
    """
    _gc()
    if not force:
        live = pending_session()
        if live is not None:
            return public(live)

    from hermes_cli.auth_codex import _codex_request_device_code

    device = _codex_request_device_code(ISSUER, _client_id())
    sid = uuid.uuid4().hex[:12]
    sess: Dict[str, Any] = {
        "id": sid,
        "status": "pending",
        "user_code": device["user_code"],
        "device_auth_id": device["device_auth_id"],
        "interval": int(device.get("interval", 5)),
        "verification_url": VERIFICATION_URL,
        "started_at": time.time(),
        "expires_at": time.time() + EXPIRES_IN,
        "cancelled": False,
        "error": "",
    }
    with _lock:
        _sessions[sid] = sess
    threading.Thread(target=_worker, args=(sid,), name=f"codex-oauth-{sid}", daemon=True).start()
    logger.info("codex-oauth: sessão %s iniciada (código %s)", sid, sess["user_code"])
    return public(sess)


def cancel(session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    sess = get_session(session_id)
    if sess is None:
        return None
    with _lock:
        if sess["status"] == "pending":
            sess["cancelled"] = True
            sess["status"] = "cancelled"
            sess["finished_at"] = time.time()
    return public(sess)


def _finish(sess: Dict[str, Any], status: str, error: str = "") -> None:
    with _lock:
        if sess["status"] == "pending":
            sess["status"] = status
            sess["error"] = error
            sess["finished_at"] = time.time()


def _worker(sid: str) -> None:
    sess = _sessions[sid]
    try:
        import httpx
        from hermes_cli.auth_codex import _codex_http_client

        payload = {"device_auth_id": sess["device_auth_id"], "user_code": sess["user_code"]}
        code_resp: Optional[Dict[str, Any]] = None
        with _codex_http_client(timeout=httpx.Timeout(15.0)) as client:
            while time.time() < sess["expires_at"]:
                time.sleep(sess["interval"])
                if sess["cancelled"]:
                    return
                resp = client.post(f"{ISSUER}/api/accounts/deviceauth/token", json=payload,
                                   headers={"Content-Type": "application/json"})
                if resp.status_code == 200:
                    code_resp = resp.json()
                    break
                if resp.status_code in (403, 404):
                    continue  # usuário ainda não aprovou
                raise RuntimeError(f"polling do device code retornou HTTP {resp.status_code}")
        if code_resp is None:
            _finish(sess, "expired", "O código expirou antes da aprovação. Inicie um novo login.")
            return

        from hermes_cli.auth_codex import _codex_exchange_authorization_code, _save_codex_tokens

        tokens = _codex_exchange_authorization_code(ISSUER, _client_id(), code_resp)
        if sess["cancelled"]:
            return
        _save_codex_tokens({
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
        })
        _finish(sess, "approved")
        logger.info("codex-oauth: sessão %s aprovada e tokens salvos", sid)
        refresh_setup_record()

        if _auto_set_model_enabled():
            try:
                set_model(_configured_default_model())
            except Exception as exc:  # não derruba o login por falha de config
                logger.warning("codex-oauth: login ok, mas falhou ao definir modelo padrão: %s", exc)
    except Exception as exc:
        logger.warning("codex-oauth: sessão %s falhou: %s", sid, exc)
        _finish(sess, "error", str(exc))


# ── status / modelo ──────────────────────────────────────────────────────────────

def auth_status() -> Dict[str, Any]:
    """Snapshot do login Codex, igual ao que o dashboard exibe."""
    from hermes_cli.auth import get_codex_auth_status
    try:
        return dict(get_codex_auth_status() or {})
    except Exception as exc:
        return {"logged_in": False, "error": str(exc)}


def current_model() -> Dict[str, Any]:
    from hermes_cli.config import load_config_readonly
    m = (load_config_readonly() or {}).get("model") or {}
    if not isinstance(m, dict):
        m = {}
    return {"provider": m.get("provider") or "", "default": m.get("default") or m.get("model") or ""}


def suggested_models() -> List[str]:
    try:
        from hermes_cli.codex_models import DEFAULT_CODEX_MODELS
        return list(DEFAULT_CODEX_MODELS)
    except Exception:
        return list(FALLBACK_MODELS)


def set_model(model: Optional[str] = None) -> Dict[str, Any]:
    """Grava ``model.provider: openai-codex`` e ``model.default: <model>`` no config.yaml."""
    from hermes_cli.config import load_config, save_config

    model = (model or "").strip() or _configured_default_model()
    cfg = load_config() or {}
    section = cfg.get("model")
    if not isinstance(section, dict):
        section = {}
    section["provider"] = PROVIDER_ID
    section["default"] = model
    section.pop("model", None)  # chave legada; o canônico é model.default
    cfg["model"] = section
    save_config(cfg, merge_existing=True)
    refresh_setup_record()
    return {"provider": PROVIDER_ID, "default": model}


def _plugin_setting(key: str, default: Any) -> Any:
    """Lê plugins.entries.codex-oauth.settings.<key> sem depender do ctx."""
    try:
        from hermes_cli.config import load_config_readonly
        entries = ((load_config_readonly() or {}).get("plugins") or {}).get("entries") or {}
        entry = entries.get("codex-oauth") or {}
        return (entry.get("settings") or {}).get(key, default)
    except Exception:
        return default


def _configured_default_model() -> str:
    return str(_plugin_setting("default_model", DEFAULT_MODEL) or DEFAULT_MODEL)


def _auto_set_model_enabled() -> bool:
    return bool(_plugin_setting("auto_set_model", True))


def refresh_setup_record() -> bool:
    """Reavalia o registro "provider configured" que o dashboard calcula no boot.

    O chat embutido do dashboard consulta ``free_tier_bootstrap`` (cacheado no boot) para decidir
    se mostra "Setup Required". Sem isto, conectar o Codex só teria efeito após reiniciar o
    serviço. Só age no processo em que o bootstrap já rodou (o dashboard); no gateway/CLI é no-op,
    evitando disparar a criação de identidade Nous fora de hora. Nunca levanta exceção.
    """
    try:
        from hermes_cli import free_tier_bootstrap as ftb
        if ftb.current_record() is None:
            return False
        ftb.reset_for_tests()
        rec = ftb.run_bootstrap(announce=True)
        logger.info("codex-oauth: registro de setup reavaliado (provider_configured=%s)", rec.provider_configured)
        return bool(rec.provider_configured)
    except Exception as exc:
        logger.debug("codex-oauth: não foi possível reavaliar o registro de setup: %s", exc)
        return False


def overview() -> Dict[str, Any]:
    """Resumo único usado por status: login + modelo + sessão pendente."""
    status = auth_status()
    model = current_model()
    pend = pending_session()
    logged = bool(status.get("logged_in"))
    return {
        "logged_in": logged,
        "token_preview": status.get("token_preview") or "",
        "expires_at": status.get("expires_at"),
        "has_refresh_token": bool(status.get("has_refresh_token")),
        "model": model,
        "ready": logged and model["provider"] == PROVIDER_ID,
        "pending_session": public(pend) if pend else None,
        "suggested_models": suggested_models(),
    }


# ═════════════════════════════════════════════════════════════════════════════════
# Anthropic (Claude Pro/Max) — OAuth PKCE
#
# Reutiliza as constantes e a troca de token de ``agent.anthropic_credentials`` (o mesmo código
# do ``hermes auth add anthropic --type oauth``). Diferença: o fluxo é dividido em start (gera a
# URL) e submit (recebe o código colado), para funcionar no painel e no chat.
# ═════════════════════════════════════════════════════════════════════════════════

ANTHROPIC_PROVIDER_ID = "anthropic"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_MODELS = [
    "claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-4-8", "claude-sonnet-5", "claude-opus-5",
]
ANTHROPIC_EXPIRES_IN = 10 * 60

_asessions: Dict[str, Dict[str, Any]] = {}


def _anthropic_mod():
    from agent import anthropic_credentials as m
    return m


def anthropic_public(sess: Dict[str, Any]) -> Dict[str, Any]:
    remaining = max(0, int(sess["expires_at"] - time.time())) if sess["status"] == "pending" else 0
    out = {"session_id": sess["id"], "status": sess["status"], "auth_url": sess["auth_url"],
           "expires_in_seconds": remaining}
    if sess.get("error"):
        out["error"] = sess["error"]
    return out


def anthropic_get_session(session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with _lock:
        if session_id:
            return _asessions.get(session_id)
        return max(_asessions.values(), key=lambda s: s["started_at"]) if _asessions else None


def anthropic_pending_session() -> Optional[Dict[str, Any]]:
    with _lock:
        live = [s for s in _asessions.values() if s["status"] == "pending" and s["expires_at"] > time.time()]
    return max(live, key=lambda s: s["started_at"]) if live else None


def anthropic_start(force: bool = False) -> Dict[str, Any]:
    """Gera a URL de autorização (PKCE + state). O usuário abre, autoriza e recebe um código."""
    import secrets
    from urllib.parse import urlencode

    if not force:
        live = anthropic_pending_session()
        if live is not None:
            return anthropic_public(live)
    m = _anthropic_mod()
    verifier, challenge = m._generate_pkce()
    state = secrets.token_urlsafe(32)
    params = {
        "code": "true", "client_id": m._OAUTH_CLIENT_ID, "response_type": "code",
        "redirect_uri": m._OAUTH_REDIRECT_URI, "scope": m._OAUTH_SCOPES,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
    }
    sid = uuid.uuid4().hex[:12]
    sess = {"id": sid, "status": "pending", "verifier": verifier, "state": state,
            "auth_url": f"https://claude.ai/oauth/authorize?{urlencode(params)}",
            "started_at": time.time(), "expires_at": time.time() + ANTHROPIC_EXPIRES_IN, "error": ""}
    with _lock:
        _asessions[sid] = sess
    return anthropic_public(sess)


def anthropic_submit(code: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Troca o código colado (``code#state``) por tokens e grava no pool de credenciais."""
    import json as _json

    sess = anthropic_get_session(session_id)
    if sess is None or sess["status"] != "pending":
        raise RuntimeError("Nenhum login Claude pendente. Inicie de novo.")
    if sess["expires_at"] < time.time():
        sess["status"] = "expired"
        raise RuntimeError("A autorização expirou. Inicie de novo.")
    raw = (code or "").strip()
    if not raw:
        raise RuntimeError("Cole o código mostrado pela Anthropic.")
    parts = raw.split("#")
    auth_code, received_state = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
    if received_state and received_state != sess["state"]:
        raise RuntimeError("O código não corresponde a esta sessão (state diferente). Inicie de novo e cole o código completo.")
    m = _anthropic_mod()
    payload = _json.dumps({
        "grant_type": "authorization_code", "client_id": m._OAUTH_CLIENT_ID, "code": auth_code,
        "state": received_state or sess["state"], "redirect_uri": m._OAUTH_REDIRECT_URI,
        "code_verifier": sess["verifier"],
    }).encode()
    try:
        result = m._post_oauth_token(payload, content_type="application/json", timeout=15, what="exchange")
    except Exception as exc:
        raise RuntimeError(f"A Anthropic recusou o código: {exc}")
    if not result.get("access_token"):
        raise RuntimeError("A Anthropic não devolveu access_token.")
    creds = m._oauth_token_state(result)
    _anthropic_save_pool_entry(creds)
    sess["status"] = "approved"
    sess["finished_at"] = time.time()
    refresh_setup_record()
    logger.info("codex-oauth: login Anthropic aprovado (sessão %s)", sess["id"])
    return {**anthropic_public(sess), "auth": anthropic_status()}


def _anthropic_save_pool_entry(creds: Dict[str, Any]) -> None:
    """Mesma gravação do ``hermes auth add anthropic --type oauth`` (entrada própria no pool)."""
    from agent.credential_pool import AUTH_TYPE_OAUTH, SOURCE_MANUAL, PooledCredential, label_from_token, load_pool
    from hermes_cli.auth import PROVIDER_REGISTRY

    pool = load_pool(ANTHROPIC_PROVIDER_ID)
    token = creds["access_token"]
    pconfig = PROVIDER_REGISTRY.get(ANTHROPIC_PROVIDER_ID)
    entry = PooledCredential(
        provider=ANTHROPIC_PROVIDER_ID, id=uuid.uuid4().hex[:6],
        label=label_from_token(token, f"anthropic-oauth-{len(pool.entries()) + 1}"),
        auth_type=AUTH_TYPE_OAUTH, priority=0, source=f"{SOURCE_MANUAL}:hermes_pkce",
        access_token=token, refresh_token=creds.get("refresh_token"),
        expires_at_ms=creds.get("expires_at_ms"),
        base_url=(pconfig.inference_base_url if pconfig else "https://api.anthropic.com"),
    )
    pool.add_entry(entry)


def anthropic_status() -> Dict[str, Any]:
    out: Dict[str, Any] = {"logged_in": False, "token_preview": "", "entries": 0}
    try:
        from agent.credential_pool import load_pool
        entries = load_pool(ANTHROPIC_PROVIDER_ID).entries()
        out["entries"] = len(entries)
    except Exception:
        pass
    try:
        token = _anthropic_mod().resolve_anthropic_token()
        if token:
            out["logged_in"] = True
            out["token_preview"] = token[-4:]
            out["kind"] = "oauth" if _anthropic_mod()._is_oauth_token(token) else "api_key"
    except Exception as exc:
        out["error"] = str(exc)
    return out


def anthropic_set_model(model: Optional[str] = None) -> Dict[str, Any]:
    from hermes_cli.config import load_config, save_config

    model = (model or "").strip() or ANTHROPIC_DEFAULT_MODEL
    cfg = load_config() or {}
    section = cfg.get("model")
    if not isinstance(section, dict):
        section = {}
    section["provider"] = ANTHROPIC_PROVIDER_ID
    section["default"] = model
    # chaves que o Codex deixa e que não valem para a Anthropic
    for k in ("model", "base_url", "api_mode"):
        section.pop(k, None)
    cfg["model"] = section
    save_config(cfg, merge_existing=True)
    refresh_setup_record()
    return {"provider": ANTHROPIC_PROVIDER_ID, "default": model}


def anthropic_disconnect() -> bool:
    cleared = False
    try:
        from hermes_cli.auth import clear_provider_auth
        cleared = bool(clear_provider_auth(ANTHROPIC_PROVIDER_ID))
    except Exception as exc:
        logger.warning("codex-oauth: clear_provider_auth(anthropic) falhou: %s", exc)
    try:
        f = _anthropic_mod()._get_hermes_oauth_file()
        if f.exists():
            f.unlink()
            cleared = True
    except Exception:
        pass
    refresh_setup_record()
    return cleared


def anthropic_overview() -> Dict[str, Any]:
    st = anthropic_status()
    model = current_model()
    pend = anthropic_pending_session()
    return {
        "logged_in": bool(st.get("logged_in")), "token_preview": st.get("token_preview", ""),
        "kind": st.get("kind"), "entries": st.get("entries", 0), "model": model,
        "ready": bool(st.get("logged_in")) and model["provider"] == ANTHROPIC_PROVIDER_ID,
        "pending_session": anthropic_public(pend) if pend else None,
        "suggested_models": list(ANTHROPIC_MODELS),
    }
