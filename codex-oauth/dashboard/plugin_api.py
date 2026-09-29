"""Backend da aba "Codex" do dashboard, montado em /api/plugins/codex-oauth/.

Reaproveita o módulo ``flow.py`` do plugin (mesmo código das ferramentas e da CLI). Como o
dashboard importa este arquivo isoladamente, ``flow.py`` é carregado pelo caminho; ele não tem
imports relativos, então funciona fora do pacote.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_log = logging.getLogger(__name__)
router = APIRouter()

_FLOW_MODULE = "hermes_codex_oauth_dashboard_flow"


def _flow():
    mod = sys.modules.get(_FLOW_MODULE)
    if mod is not None:
        return mod
    path = Path(__file__).resolve().parent.parent / "flow.py"
    spec = importlib.util.spec_from_file_location(_FLOW_MODULE, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"flow.py não encontrado em {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_FLOW_MODULE] = mod
    spec.loader.exec_module(mod)
    return mod


class StartBody(BaseModel):
    force: bool = False


class SetModelBody(BaseModel):
    model: Optional[str] = None


class SessionBody(BaseModel):
    session_id: Optional[str] = None


@router.get("/status")
def status() -> Dict[str, Any]:
    return _flow().overview()


@router.post("/start")
def start(body: StartBody) -> Dict[str, Any]:
    f = _flow()
    ov = f.overview()
    if ov["ready"] and not body.force:
        return {"already_connected": True, **ov}
    try:
        sess = f.start(force=body.force)
    except Exception as exc:
        _log.warning("codex-oauth dashboard: start falhou: %s", exc)
        raise HTTPException(status_code=502, detail=f"Não foi possível iniciar o login: {exc}")
    return sess


@router.get("/check")
def check(session_id: Optional[str] = None) -> Dict[str, Any]:
    f = _flow()
    sess = f.get_session(session_id or None)
    if sess is None:
        raise HTTPException(status_code=404, detail="Nenhuma sessão de login encontrada.")
    out = f.public(sess)
    if out["status"] == "approved":
        out["auth"] = f.auth_status()
        out["model"] = f.current_model()
    return out


@router.post("/set-model")
def set_model(body: SetModelBody) -> Dict[str, Any]:
    f = _flow()
    if not f.auth_status().get("logged_in"):
        raise HTTPException(status_code=409, detail="Codex ainda não conectado.")
    try:
        return f.set_model(body.model)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao gravar config.yaml: {exc}")


@router.post("/cancel")
def cancel(body: SessionBody) -> Dict[str, Any]:
    out = _flow().cancel(body.session_id or None)
    if out is None:
        raise HTTPException(status_code=404, detail="Nenhuma sessão para cancelar.")
    return out


@router.post("/disconnect")
def disconnect() -> Dict[str, Any]:
    """Remove os tokens do Codex (mesmo efeito de `hermes auth logout openai-codex`)."""
    try:
        from hermes_cli.auth import clear_provider_auth
        cleared = bool(clear_provider_auth("openai-codex"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao desconectar: {exc}")
    f = _flow()
    f.refresh_setup_record()
    return {"ok": cleared, "status": f.overview()}


# ── Anthropic (Claude Pro/Max) via OAuth PKCE ────────────────────────────────────

class SubmitBody(BaseModel):
    code: str
    session_id: Optional[str] = None


@router.get("/anthropic/status")
def anthropic_status() -> Dict[str, Any]:
    return _flow().anthropic_overview()


@router.post("/anthropic/start")
def anthropic_start(body: StartBody) -> Dict[str, Any]:
    try:
        return _flow().anthropic_start(force=body.force)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Não foi possível iniciar o login Claude: {exc}")


@router.post("/anthropic/submit")
def anthropic_submit(body: SubmitBody) -> Dict[str, Any]:
    try:
        return _flow().anthropic_submit(body.code, body.session_id or None)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha inesperada: {exc}")


@router.post("/anthropic/set-model")
def anthropic_set_model(body: SetModelBody) -> Dict[str, Any]:
    f = _flow()
    if not f.anthropic_status().get("logged_in"):
        raise HTTPException(status_code=409, detail="Claude ainda não conectado.")
    try:
        return f.anthropic_set_model(body.model)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao gravar config.yaml: {exc}")


@router.post("/anthropic/disconnect")
def anthropic_disconnect() -> Dict[str, Any]:
    f = _flow()
    return {"ok": f.anthropic_disconnect(), "status": f.anthropic_overview()}
