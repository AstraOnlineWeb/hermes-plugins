"""Ferramentas (function calling) e comandos de barra do plugin codex-oauth."""

from __future__ import annotations

import json
from typing import Any, Dict

from . import flow


def _schema(name: str, description: str, properties: Dict[str, Any], required=None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        params["required"] = required
    return {"name": name, "description": description, "parameters": params}


def _dump(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _instructions(sess: Dict[str, Any]) -> str:
    return (
        f"1) Abra {sess['verification_url']} no navegador. "
        f"2) Faça login na conta ChatGPT/Codex. "
        f"3) Digite o código {sess['user_code']}. "
        f"O código vale por {max(1, sess['expires_in_seconds'] // 60)} minuto(s). "
        "Depois use codex_oauth_check para confirmar a aprovação."
    )


# ── schemas ──────────────────────────────────────────────────────────────────────

STATUS_SCHEMA = _schema(
    "codex_oauth_status",
    "Mostra se o Hermes está conectado à assinatura ChatGPT/Codex (OAuth), qual provedor e modelo "
    "padrão estão configurados, se há um login pendente e quais modelos Codex são sugeridos. "
    "Use antes de iniciar um login para não pedir de novo o que já está conectado.",
    {},
)

START_SCHEMA = _schema(
    "codex_oauth_start",
    "Inicia o login OAuth (device code) na conta ChatGPT/Codex do usuário. Retorna a URL de "
    "verificação e o código que o usuário deve digitar no navegador. O Hermes fica aguardando a "
    "aprovação em segundo plano; confirme com codex_oauth_check. Se já houver um login pendente "
    "válido, devolve o mesmo código em vez de gerar outro (a menos que force=true).",
    {"force": {"type": "boolean", "description": "Gera um código novo mesmo com sessão pendente.", "default": False}},
)

CHECK_SCHEMA = _schema(
    "codex_oauth_check",
    "Consulta o andamento de um login iniciado com codex_oauth_start: pending, approved, expired, "
    "cancelled ou error. Quando aprovado, os tokens já foram salvos e o modelo padrão já foi "
    "ajustado (se auto_set_model estiver ligado). Chame a cada ~10 s enquanto estiver pendente, "
    "ou quando o usuário disser que aprovou.",
    {"session_id": {"type": "string", "description": "Id retornado por codex_oauth_start. Se omitido, usa a sessão mais recente."}},
)

SET_MODEL_SCHEMA = _schema(
    "codex_oauth_set_model",
    "Define o provedor openai-codex como padrão do Hermes e escolhe o modelo (ex.: gpt-5.5, "
    "gpt-5.4-mini, gpt-5.3-codex). Só faz sentido depois do login aprovado. A mudança vale para "
    "novas sessões; o gateway pode precisar de reinício.",
    {"model": {"type": "string", "description": "Id do modelo Codex. Se omitido usa o configurado no plugin (padrão gpt-5.5)."}},
)

CANCEL_SCHEMA = _schema(
    "codex_oauth_cancel",
    "Cancela um login pendente (o código deixa de ser aceito pelo Hermes).",
    {"session_id": {"type": "string", "description": "Id da sessão. Se omitido, cancela a mais recente."}},
)


# ── handlers das ferramentas ─────────────────────────────────────────────────────

def handle_status(args: Dict[str, Any], **_kw) -> str:
    return _dump(flow.overview())


def handle_start(args: Dict[str, Any], **_kw) -> str:
    ov = flow.overview()
    if ov["ready"] and not args.get("force"):
        return _dump({"already_connected": True, "hint": "Já conectado ao Codex. Use force=true para refazer o login.", **ov})
    try:
        sess = flow.start(force=bool(args.get("force")))
    except Exception as exc:
        return _dump({"error": f"Não foi possível iniciar o login: {exc}"})
    return _dump({**sess, "instructions": _instructions(sess)})


def handle_check(args: Dict[str, Any], **_kw) -> str:
    sess = flow.get_session((args.get("session_id") or "").strip() or None)
    if sess is None:
        return _dump({"error": "Nenhuma sessão de login encontrada. Inicie com codex_oauth_start."})
    out = flow.public(sess)
    if out["status"] == "approved":
        out.update({"auth": flow.auth_status(), "model": flow.current_model()})
    return _dump(out)


def handle_set_model(args: Dict[str, Any], **_kw) -> str:
    if not flow.auth_status().get("logged_in"):
        return _dump({"error": "Codex ainda não está conectado. Faça o login antes de definir o modelo."})
    try:
        result = flow.set_model(args.get("model"))
    except Exception as exc:
        return _dump({"error": f"Falha ao gravar config.yaml: {exc}"})
    return _dump({**result, "note": "Reinicie o gateway (ou inicie uma nova sessão) para aplicar."})


def handle_cancel(args: Dict[str, Any], **_kw) -> str:
    out = flow.cancel((args.get("session_id") or "").strip() or None)
    return _dump(out or {"error": "Nenhuma sessão para cancelar."})


TOOLS = (
    ("codex_oauth_status",    STATUS_SCHEMA,    handle_status,    "🔎"),
    ("codex_oauth_start",     START_SCHEMA,     handle_start,     "🔐"),
    ("codex_oauth_check",     CHECK_SCHEMA,     handle_check,     "⏳"),
    ("codex_oauth_set_model", SET_MODEL_SCHEMA, handle_set_model, "🧠"),
    ("codex_oauth_cancel",    CANCEL_SCHEMA,    handle_cancel,    "✖️"),
)


# ── comandos de barra (/codex-login, /codex-status, /codex-model) ────────────────

def _fmt_status() -> str:
    ov = flow.overview()
    lines = ["☤ Codex OAuth"]
    if ov["logged_in"]:
        lines.append(f"Conectado ✅ (token …{ov['token_preview']})" if ov["token_preview"] else "Conectado ✅")
    else:
        lines.append("Não conectado ❌")
    m = ov["model"]
    lines.append(f"Provedor: {m['provider'] or '(não definido)'}  |  Modelo: {m['default'] or '(não definido)'}")
    if ov["pending_session"]:
        p = ov["pending_session"]
        lines.append(f"Login pendente: código {p['user_code']} em {p['verification_url']} ({p['expires_in_seconds']} s restantes)")
    if not ov["ready"]:
        lines.append("Use /codex-login para conectar." if not ov["logged_in"] else "Use /codex-model <modelo> para ativar o Codex como padrão.")
    return "\n".join(lines)


def cmd_codex_login(raw_args: str = "") -> str:
    force = "--force" in (raw_args or "")
    try:
        sess = flow.start(force=force)
    except Exception as exc:
        return f"Não foi possível iniciar o login Codex: {exc}"
    return (
        "☤ Login Codex iniciado\n"
        f"1. Abra: {sess['verification_url']}\n"
        f"2. Digite o código: {sess['user_code']}\n"
        f"Válido por {sess['expires_in_seconds'] // 60} min. Depois envie /codex-status para confirmar."
    )


def cmd_codex_status(raw_args: str = "") -> str:
    return _fmt_status()


def cmd_codex_model(raw_args: str = "") -> str:
    model = (raw_args or "").strip()
    if model in ("", "list", "ls"):
        return "Modelos Codex sugeridos:\n- " + "\n- ".join(flow.suggested_models()) + "\n\nUse /codex-model <modelo>."
    if not flow.auth_status().get("logged_in"):
        return "Codex ainda não conectado. Rode /codex-login primeiro."
    try:
        r = flow.set_model(model)
    except Exception as exc:
        return f"Falha ao gravar config: {exc}"
    return f"Padrão definido: provider={r['provider']}, model={r['default']}. Reinicie o gateway para aplicar."


COMMANDS = (
    ("codex-login",  cmd_codex_login,  "Inicia o login OAuth na assinatura ChatGPT/Codex e mostra link + código", "[--force]"),
    ("codex-status", cmd_codex_status, "Mostra se o Codex está conectado e qual modelo está ativo", ""),
    ("codex-model",  cmd_codex_model,  "Define o modelo Codex padrão (ou lista os sugeridos)", "<modelo>"),
)


# ── Claude (Anthropic) via OAuth PKCE ────────────────────────────────────────────

CLAUDE_STATUS_SCHEMA = _schema(
    "claude_oauth_status",
    "Mostra se o Hermes está conectado a uma conta Claude (Anthropic) via OAuth ou chave, qual provedor "
    "e modelo padrão estão ativos e se há um login pendente. Exige plano Claude Max com créditos extras.",
    {},
)
CLAUDE_START_SCHEMA = _schema(
    "claude_oauth_start",
    "Inicia o login OAuth na conta Claude Pro/Max. Retorna auth_url: o usuário abre, autoriza e a "
    "Anthropic mostra um código, que deve ser enviado com claude_oauth_submit. Válido por 10 minutos.",
    {"force": {"type": "boolean", "description": "Gera uma URL nova mesmo com sessão pendente.", "default": False}},
)
CLAUDE_SUBMIT_SCHEMA = _schema(
    "claude_oauth_submit",
    "Conclui o login Claude com o código que a Anthropic exibiu após a autorização (formato code#state). "
    "Salva os tokens no pool de credenciais.",
    {"code": {"type": "string", "description": "Código completo colado pelo usuário."},
     "session_id": {"type": "string", "description": "Opcional; usa a sessão mais recente se omitido."}},
    required=["code"],
)
CLAUDE_SET_MODEL_SCHEMA = _schema(
    "claude_oauth_set_model",
    "Define anthropic como provedor padrão e escolhe o modelo Claude (ex.: claude-sonnet-4-6, claude-opus-4-6).",
    {"model": {"type": "string", "description": "Id do modelo. Padrão: claude-sonnet-4-6."}},
)


def handle_claude_status(args, **_kw) -> str:
    return _dump(flow.anthropic_overview())


def handle_claude_start(args, **_kw) -> str:
    try:
        sess = flow.anthropic_start(force=bool(args.get("force")))
    except Exception as exc:
        return _dump({"error": f"Não foi possível iniciar: {exc}"})
    return _dump({**sess, "instructions": (
        "1) Abra auth_url no navegador e faça login na conta Claude (Max). 2) Autorize o Hermes. "
        "3) A Anthropic mostra um código: peça ao usuário para colá-lo e chame claude_oauth_submit.")})


def handle_claude_submit(args, **_kw) -> str:
    try:
        return _dump(flow.anthropic_submit(args.get("code", ""), (args.get("session_id") or "").strip() or None))
    except Exception as exc:
        return _dump({"error": str(exc)})


def handle_claude_set_model(args, **_kw) -> str:
    if not flow.anthropic_status().get("logged_in"):
        return _dump({"error": "Claude ainda não conectado."})
    try:
        return _dump({**flow.anthropic_set_model(args.get("model")), "note": "Abra uma sessão nova (/new) para aplicar."})
    except Exception as exc:
        return _dump({"error": f"Falha ao gravar config.yaml: {exc}"})


def cmd_claude_login(raw_args: str = "") -> str:
    try:
        sess = flow.anthropic_start(force="--force" in (raw_args or ""))
    except Exception as exc:
        return f"Não foi possível iniciar o login Claude: {exc}"
    return ("☤ Login Claude (Anthropic) iniciado\n"
            f"1. Abra: {sess['auth_url']}\n"
            "2. Autorize o Hermes na sua conta Claude Max.\n"
            "3. Copie o código exibido e envie: /claude-code <código>\n"
            f"Válido por {sess['expires_in_seconds'] // 60} min.")


def cmd_claude_code(raw_args: str = "") -> str:
    try:
        r = flow.anthropic_submit(raw_args or "")
    except Exception as exc:
        return f"Falha: {exc}"
    return "✓ Claude conectado. Use /claude-model <modelo> para torná-lo padrão (ex.: claude-sonnet-4-6)."


def cmd_claude_status(raw_args: str = "") -> str:
    ov = flow.anthropic_overview()
    lines = ["☤ Claude (Anthropic)", "Conectado ✅" if ov["logged_in"] else "Não conectado ❌",
             f"Provedor: {ov['model']['provider'] or '-'}  |  Modelo: {ov['model']['default'] or '-'}"]
    if ov["pending_session"]:
        lines.append("Login pendente: envie /claude-code <código> ou /claude-login para uma URL nova.")
    return "\n".join(lines)


def cmd_claude_model(raw_args: str = "") -> str:
    model = (raw_args or "").strip()
    if model in ("", "list", "ls"):
        return "Modelos Claude sugeridos:\n- " + "\n- ".join(flow.ANTHROPIC_MODELS) + "\n\nUse /claude-model <modelo>."
    if not flow.anthropic_status().get("logged_in"):
        return "Claude ainda não conectado. Rode /claude-login primeiro."
    try:
        r = flow.anthropic_set_model(model)
    except Exception as exc:
        return f"Falha ao gravar config: {exc}"
    return f"Padrão definido: provider={r['provider']}, model={r['default']}. Abra uma sessão nova (/new)."


TOOLS = TOOLS + (
    ("claude_oauth_status",    CLAUDE_STATUS_SCHEMA,    handle_claude_status,    "🔎"),
    ("claude_oauth_start",     CLAUDE_START_SCHEMA,     handle_claude_start,     "🔐"),
    ("claude_oauth_submit",    CLAUDE_SUBMIT_SCHEMA,    handle_claude_submit,    "✅"),
    ("claude_oauth_set_model", CLAUDE_SET_MODEL_SCHEMA, handle_claude_set_model, "🧠"),
)

COMMANDS = COMMANDS + (
    ("claude-login",  cmd_claude_login,  "Inicia o login OAuth na conta Claude Pro/Max e mostra a URL", "[--force]"),
    ("claude-code",   cmd_claude_code,   "Conclui o login Claude com o código exibido pela Anthropic", "<código>"),
    ("claude-status", cmd_claude_status, "Mostra se o Claude está conectado e qual modelo está ativo", ""),
    ("claude-model",  cmd_claude_model,  "Define o modelo Claude padrão (ou lista os sugeridos)", "<modelo>"),
)
