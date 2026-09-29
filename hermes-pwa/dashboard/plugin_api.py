"""Backend do hermes-pwa, montado em /api/plugins/hermes-pwa/.

Duas responsabilidades:
  1. Servir o app (index.html, app.js, app.css, manifest, service worker, ícones, QR).
  2. Fazer proxy autenticado para o API server do gateway (porta 8642) — listar sessões,
     ler mensagens, criar/renomear/apagar sessões e conversar com streaming (SSE) — usando a
     API_SERVER_KEY do ambiente. O navegador nunca vê a chave; ele só precisa do cookie do
     dashboard, que a própria gate do Hermes já exige para tudo em /api/plugins/*.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

_log = logging.getLogger(__name__)
router = APIRouter()

_HERE = Path(__file__).resolve().parent
_PWA = _HERE / "pwa"
_STATIC = {
    "app.js": ("application/javascript; charset=utf-8", _PWA / "app.js"),
    "app.css": ("text/css; charset=utf-8", _PWA / "app.css"),
    "sw.js": ("application/javascript; charset=utf-8", _PWA / "sw.js"),
    "icon.svg": ("image/svg+xml", _PWA / "icon.svg"),
    "icon-192.png": ("image/png", _PWA / "icon-192.png"),
    "icon-512.png": ("image/png", _PWA / "icon-512.png"),
}


# ── gateway API server ───────────────────────────────────────────────────────────

def _api_base() -> str:
    host = (os.environ.get("HERMES_PWA_API_HOST") or "127.0.0.1").strip()
    port = (os.environ.get("API_SERVER_PORT") or "8642").strip()
    return f"http://{host}:{port}"


def _api_key() -> str:
    key = (os.environ.get("API_SERVER_KEY") or "").strip()
    if not key:
        try:  # .env do HERMES_HOME (instalações sem Docker)
            from hermes_cli.config import get_env_path
            for line in Path(get_env_path()).read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("API_SERVER_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'\"")
                    break
        except Exception:
            pass
    if not key:
        raise HTTPException(status_code=503, detail=(
            "API_SERVER_KEY não configurada. O PWA usa o API server do gateway; defina "
            "API_SERVER_ENABLED=true, API_SERVER_HOST=0.0.0.0 e API_SERVER_KEY no .env/ambiente e reinicie."))
    return key


def _client():
    import httpx
    return httpx.AsyncClient(base_url=_api_base(), headers={"Authorization": f"Bearer {_api_key()}"},
                             timeout=httpx.Timeout(30.0, read=300.0))


async def _proxy_json(method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
                      body: Optional[Dict[str, Any]] = None) -> Any:
    try:
        async with _client() as c:
            r = await c.request(method, path, params=params, json=body)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gateway API indisponível ({_api_base()}): {exc}")
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:300]
        raise HTTPException(status_code=r.status_code, detail=detail)
    if not r.content:
        return {"ok": True}
    try:
        return r.json()
    except Exception:
        return {"ok": True, "raw": r.text[:300]}


# ── app estático ─────────────────────────────────────────────────────────────────

_NO_STORE = {"Cache-Control": "no-store"}


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def index(request: Request):
    # Sem barra final o escopo relativo do manifest/SW quebra: normaliza.
    if not request.url.path.endswith("/"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=request.url.path + "/", status_code=307)
    return HTMLResponse((_PWA / "index.html").read_text(encoding="utf-8"), headers=_NO_STORE)


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest(request: Request):
    base = request.url.path.rsplit("/manifest.webmanifest", 1)[0] + "/"
    data = {
        "name": "Hermes", "short_name": "Hermes", "description": "Chat com o Hermes Agent",
        "id": base, "start_url": base, "scope": base, "display": "standalone",
        "orientation": "portrait", "background_color": "#0b1416", "theme_color": "#0f2f31",
        "lang": "pt-BR",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return Response(json.dumps(data), media_type="application/manifest+json", headers=_NO_STORE)


@router.get("/qr.svg", include_in_schema=False)
def qr(request: Request, target: str = ""):
    """QR code (SVG) para o link do app; usado na aba PWA do painel."""
    url = target or (str(request.base_url).rstrip("/") + "/pwa")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="target inválido")
    try:
        import qrcode
        import qrcode.image.svg as qsvg
        img = qrcode.make(url, image_factory=qsvg.SvgPathImage, box_size=10, border=2)
        import io
        buf = io.BytesIO()
        img.save(buf)
        return Response(buf.getvalue(), media_type="image/svg+xml", headers=_NO_STORE)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não foi possível gerar o QR: {exc}")


# ── perfis (agentes) ─────────────────────────────────────────────────────────────
import re as _re
_PROFILE_RE = _re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


def _pfx(profile: Optional[str]) -> str:
    """Prefixo da API do gateway para um perfil secundário (gateway.multiplex_profiles)."""
    prof = (profile or "").strip().lower()
    if not prof or prof == "default":
        return ""
    if not _PROFILE_RE.match(prof):
        raise HTTPException(status_code=400, detail="perfil inválido")
    return f"/p/{prof}"


@router.get("/api/profiles")
def profiles() -> Dict[str, Any]:
    """Lista os agentes (perfis) disponíveis, com modelo e descrição."""
    out = []
    try:
        from hermes_cli.profiles import list_profiles
        for prof in list_profiles():
            desc = ""
            try:
                import yaml
                meta = Path(prof.path) / "profile.yaml"
                if meta.exists():
                    desc = str((yaml.safe_load(meta.read_text(encoding="utf-8")) or {}).get("description") or "")
            except Exception:
                pass
            out.append({"name": prof.name, "is_default": bool(prof.is_default), "model": prof.model or "",
                        "provider": prof.provider or "", "description": desc})
    except Exception as exc:
        _log.warning("hermes-pwa: list_profiles falhou: %s", exc)
        out = [{"name": "default", "is_default": True, "model": "", "provider": "", "description": ""}]
    multiplex = False
    try:
        from hermes_cli.config import load_config_readonly
        multiplex = bool(((load_config_readonly() or {}).get("gateway") or {}).get("multiplex_profiles"))
    except Exception:
        pass
    return {"profiles": out, "multiplex": multiplex}


# ── API usada pelo app ───────────────────────────────────────────────────────────

class NewSession(BaseModel):
    title: Optional[str] = None


class PatchSession(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None


class ChatBody(BaseModel):
    message: Any  # str ou lista de partes OpenAI (text / image_url com data:image/...)


class UploadBody(BaseModel):
    name: str
    data_url: str
    kind: Optional[str] = None  # "audio" | "file"


@router.get("/api/me")
def me(request: Request) -> Dict[str, Any]:
    model: Dict[str, Any] = {}
    try:
        from hermes_cli.config import load_config_readonly
        m = (load_config_readonly() or {}).get("model") or {}
        model = {"provider": m.get("provider") or "", "default": m.get("default") or m.get("model") or ""}
    except Exception:
        pass
    user = getattr(getattr(request, "state", None), "user_id", None) or "admin"
    return {"user": str(user), "model": model, "api_base": _api_base()}


@router.get("/api/sessions")
async def list_sessions(limit: int = 60, offset: int = 0, source: Optional[str] = None, profile: Optional[str] = None) -> Any:
    params: Dict[str, Any] = {"limit": max(1, min(limit, 200)), "offset": max(0, offset)}
    if source:
        params["source"] = source
    return await _proxy_json("GET", _pfx(profile) + "/api/sessions", params=params)


@router.post("/api/sessions")
async def create_session(body: NewSession, profile: Optional[str] = None) -> Any:
    payload: Dict[str, Any] = {"source": "api_server"}
    if body.title:
        payload["title"] = body.title.strip()[:120]
    return await _proxy_json("POST", _pfx(profile) + "/api/sessions", body=payload)


@router.patch("/api/sessions/{session_id}")
async def patch_session(session_id: str, body: PatchSession, profile: Optional[str] = None) -> Any:
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="nada para alterar")
    return await _proxy_json("PATCH", f"{_pfx(profile)}/api/sessions/{session_id}", body=payload)


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, profile: Optional[str] = None) -> Any:
    return await _proxy_json("DELETE", f"{_pfx(profile)}/api/sessions/{session_id}")


@router.get("/api/sessions/{session_id}/messages")
async def messages(session_id: str, limit: Optional[int] = None, offset: int = 0, profile: Optional[str] = None) -> Any:
    params: Dict[str, Any] = {"offset": max(0, offset)}
    if limit is not None:
        params["limit"] = max(1, min(limit, 500))
    return await _proxy_json("GET", f"{_pfx(profile)}/api/sessions/{session_id}/messages", params=params)


_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _uploads_dir() -> Path:
    from hermes_constants import get_hermes_home
    d = get_hermes_home() / "home" / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/api/upload")
def upload(body: UploadBody) -> Dict[str, Any]:
    """Salva um arquivo enviado pelo app em ~/uploads do agente e devolve o caminho, para que a
    mensagem possa referenciá-lo e o agente o leia com as ferramentas de arquivo."""
    import base64
    import re
    import time
    import uuid

    data_url = (body.data_url or "").strip()
    if not data_url.startswith("data:") or "," not in data_url:
        raise HTTPException(status_code=400, detail="data_url inválida")
    header, encoded = data_url.split(",", 1)
    mime = header[5:].split(";", 1)[0] or "application/octet-stream"
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="base64 inválido")
    if not raw:
        raise HTTPException(status_code=400, detail="arquivo vazio")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="arquivo maior que 25 MB")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (body.name or "arquivo").strip())[:80].strip("._") or "arquivo"
    dest = _uploads_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}_{safe}"
    dest.write_bytes(raw)
    return {"ok": True, "path": str(dest), "name": safe, "size": len(raw), "mime": mime, "kind": body.kind or "file"}


@router.get("/api/uploads/{name}")
def serve_upload(name: str):
    """Serve um arquivo de ~/uploads (áudios de voz, para o player do app). Sem subpastas."""
    import re
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", name) or name.startswith("."):
        raise HTTPException(status_code=404, detail="Not found")
    path = _uploads_dir() / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    import mimetypes
    media = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if name.endswith(".webm"):
        media = "audio/webm"
    return FileResponse(str(path), media_type=media, headers={"Cache-Control": "private, max-age=86400"})


@router.post("/api/sessions/{session_id}/chat/stream")
async def chat_stream(session_id: str, body: ChatBody, profile: Optional[str] = None):
    pfx = _pfx(profile)
    """Repassa o SSE do gateway tal qual (eventos run.started, assistant.delta, tool.progress,
    assistant.completed, run.completed, error, done)."""
    import httpx

    msg = body.message
    if isinstance(msg, str):
        msg = msg.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="mensagem vazia")
    if isinstance(msg, list):
        for part in msg:
            if not isinstance(part, dict) or part.get("type") not in ("text", "image_url"):
                raise HTTPException(status_code=400, detail="partes aceitas: text e image_url")
    key = _api_key()

    async def gen():
        try:
            async with httpx.AsyncClient(base_url=_api_base(), timeout=httpx.Timeout(30.0, read=600.0)) as c:
                async with c.stream("POST", f"{pfx}/api/sessions/{session_id}/chat/stream",
                                    headers={"Authorization": f"Bearer {key}", "Accept": "text/event-stream"},
                                    json={"message": msg}) as r:
                    if r.status_code >= 400:
                        detail = (await r.aread()).decode("utf-8", "replace")[:400]
                        yield f"event: error\ndata: {json.dumps({'message': detail, 'status': r.status_code})}\n\n".encode()
                        return
                    async for chunk in r.aiter_bytes():
                        yield chunk
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n".encode()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── aprovação de comandos ─────────────────────────────────────────────────────────
# O gateway pausa comandos perigosos e emite "approval.request" no stream do chat. O app mostra
# o pedido com botões e responde por aqui (POST /v1/runs/{run_id}/approval no gateway).

_RUN_ID_RE = _re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_APPROVAL_CHOICES = {"once", "session", "always", "deny"}


class ApprovalBody(BaseModel):
    choice: str
    request_id: Optional[str] = None


@router.post("/api/runs/{run_id}/approval")
async def run_approval(run_id: str, body: ApprovalBody, profile: Optional[str] = None) -> Any:
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="execução inválida")
    choice = (body.choice or "").strip().lower()
    if choice not in _APPROVAL_CHOICES:
        raise HTTPException(status_code=400, detail="escolha inválida")
    payload: Dict[str, Any] = {"choice": choice}
    request_id = (body.request_id or "").strip()
    if request_id:
        if not _RUN_ID_RE.match(request_id):
            raise HTTPException(status_code=400, detail="pedido inválido")
        payload["request_id"] = request_id
    return await _proxy_json("POST", f"{_pfx(profile)}/v1/runs/{run_id}/approval", body=payload)


# ── transcrição de áudio (STT) ────────────────────────────────────────────────────
# Configuração feita pela aba do plugin, sem terminal. Grava o mesmo que:
#   hermes config set GROQ_API_KEY ... ; hermes config set stt.provider groq ; ...
# O Hermes resolve chave e config a cada transcrição: vale na hora, sem reiniciar.

_STT_KEY_ENV = "GROQ_API_KEY"
_STT_MODEL = "whisper-large-v3"
_STT_LANGS = {"pt", "en", "es"}


class SttBody(BaseModel):
    key: Optional[str] = None       # vazio = mantém a chave já salva
    language: str = "pt"


def _stt_key() -> str:
    try:
        from hermes_cli.config import get_env_value
        return (get_env_value(_STT_KEY_ENV) or "").strip()
    except Exception:
        return (os.environ.get(_STT_KEY_ENV) or "").strip()


def _stt_status() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    try:
        from hermes_cli.config import load_config
        cfg = load_config().get("stt") or {}
    except Exception:
        pass
    key = _stt_key()
    provider = str(cfg.get("provider") or "")
    return {
        "has_key": bool(key),
        "key_preview": (key[:4] + "…" + key[-4:]) if len(key) >= 12 else "",
        "provider": provider,
        "language": str(cfg.get("language") or ""),
        "model": str((cfg.get("groq") or {}).get("model") or ""),
        "active": bool(key) and provider == "groq",
    }


async def _stt_check_key(key: str) -> Optional[str]:
    """Confere a chave no Groq. Devolve None se estiver válida, ou a mensagem de erro."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get("https://api.groq.com/openai/v1/models",
                                 headers={"Authorization": f"Bearer {key}"})
    except Exception as exc:
        return f"Não foi possível falar com o Groq: {exc}"
    if r.status_code == 200:
        return None
    if r.status_code in (401, 403):
        return "O Groq recusou a chave. Confira se copiou a chave inteira."
    return f"O Groq respondeu com erro {r.status_code}."


@router.get("/api/stt")
def stt_get() -> Dict[str, Any]:
    return _stt_status()


@router.post("/api/stt")
async def stt_save(body: SttBody) -> Dict[str, Any]:
    key = (body.key or "").strip()
    language = (body.language or "pt").strip().lower()
    if language not in _STT_LANGS:
        raise HTTPException(status_code=400, detail="Idioma não suportado.")
    if key and not _re.fullmatch(r"gsk_[A-Za-z0-9]{20,}", key):
        raise HTTPException(status_code=400, detail="Chave inválida. A chave do Groq começa com gsk_.")
    effective = key or _stt_key()
    if not effective:
        raise HTTPException(status_code=400, detail="Informe a chave do Groq.")
    error = await _stt_check_key(effective)
    if error:
        raise HTTPException(status_code=400, detail=error)
    try:
        from hermes_cli.config import load_config, save_config, save_env_value
        if key:
            save_env_value(_STT_KEY_ENV, key)
        cfg = load_config()
        stt = dict(cfg.get("stt") or {})
        stt["provider"] = "groq"
        stt["language"] = language
        groq = dict(stt.get("groq") or {})
        groq["model"] = _STT_MODEL
        groq["language"] = language
        stt["groq"] = groq
        cfg["stt"] = stt
        save_config(cfg)
    except Exception as exc:
        _log.exception("hermes-pwa: falha ao salvar a configuração de transcrição")
        raise HTTPException(status_code=500, detail=f"Não foi possível salvar: {exc}")
    return _stt_status()


@router.delete("/api/stt")
def stt_delete() -> Dict[str, Any]:
    try:
        from hermes_cli.config import remove_env_value
        remove_env_value(_STT_KEY_ENV)
        os.environ.pop(_STT_KEY_ENV, None)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não foi possível remover: {exc}")
    return _stt_status()


# Catch-all estático: DEVE ficar por último para não engolir /qr.svg e /api/*.
@router.get("/{name}", include_in_schema=False)
def static(name: str):
    entry = _STATIC.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail="Not found")
    media, path = entry
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    headers = dict(_NO_STORE)
    if name == "sw.js":
        headers["Service-Worker-Allowed"] = "./"
    return FileResponse(str(path), media_type=media, headers=headers)
