"""Subcomando ``hermes codex-oauth`` (login, status, set-model, models, cancel)."""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import flow

_SUBCOMMANDS = (
    ("login", "Faz o login OAuth (device code) e aguarda a aprovação"),
    ("status", "Mostra o estado da conexão Codex e o modelo configurado"),
    ("set-model", "Define openai-codex como provedor padrão e escolhe o modelo"),
    ("models", "Lista os modelos Codex sugeridos"),
    ("cancel", "Cancela um login pendente"),
    ("claude-login", "Login OAuth na conta Claude Pro/Max (mostra a URL e pede o código)"),
    ("claude-status", "Estado da conexão Claude (Anthropic)"),
    ("claude-set-model", "Define anthropic como provedor padrão e escolhe o modelo Claude"),
)


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="codex_oauth_command")
    p = {name: subs.add_parser(name, help=help_) for name, help_ in _SUBCOMMANDS}
    p["login"].add_argument("--model", default=None, help="Modelo a definir como padrão após aprovar (padrão: configuração do plugin / gpt-5.5)")
    p["login"].add_argument("--no-set-model", action="store_true", help="Não altera model.provider/model.default")
    p["login"].add_argument("--force", action="store_true", help="Gera um código novo mesmo com sessão pendente")
    p["login"].add_argument("--json", action="store_true", help="Imprime link/código em JSON (uma linha) e depois o resultado final em JSON; o processo aguarda a aprovação")
    p["status"].add_argument("--json", action="store_true")
    p["set-model"].add_argument("model", nargs="?", default=None, help="Id do modelo (ex.: gpt-5.5)")
    p["claude-login"].add_argument("--model", default=None, help="Modelo Claude a definir como padrão após o login")
    p["claude-login"].add_argument("--no-set-model", action="store_true")
    p["claude-set-model"].add_argument("model", nargs="?", default=None, help="Id do modelo (ex.: claude-sonnet-4-6)")
    subparser.set_defaults(func=command)


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _cmd_login(args) -> int:
    ov = flow.overview()
    if ov["ready"] and not args.force:
        print("Já conectado ao Codex. Use --force para refazer o login.")
        return 0
    try:
        sess = flow.start(force=bool(args.force))
    except Exception as exc:
        print(f"✗ Não foi possível iniciar o login: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(sess, ensure_ascii=False), flush=True)
    else:
        print("Para continuar:\n")
        print(f"  1. Abra no navegador:  {sess['verification_url']}")
        print(f"  2. Digite o código:    {sess['user_code']}\n")
        print("Aguardando aprovação... (Ctrl+C cancela)", flush=True)
    try:
        while True:
            time.sleep(3)
            s = flow.get_session(sess["session_id"])
            if s is None or s["status"] != "pending":
                break
    except KeyboardInterrupt:
        flow.cancel(sess["session_id"])
        print("\nLogin cancelado.")
        return 130
    final = flow.public(s)
    if final["status"] != "approved":
        if args.json:
            print(json.dumps(final, ensure_ascii=False), flush=True)
        else:
            print(f"✗ Login não concluído: {final['status']} {final.get('error', '')}".strip(), file=sys.stderr)
        return 1
    model_cfg = None
    if not args.no_set_model:
        model_cfg = flow.set_model(args.model)
    if args.json:
        print(json.dumps({**final, "model": model_cfg}, ensure_ascii=False), flush=True)
    else:
        print("✓ Codex conectado e tokens salvos em auth.json")
        if model_cfg:
            print(f"✓ model.provider={model_cfg['provider']}  model.default={model_cfg['default']}")
    return 0


def _cmd_status(args) -> int:
    ov = flow.overview()
    if getattr(args, "json", False):
        _print(ov)
        return 0
    print("Codex OAuth:", "conectado ✓" if ov["logged_in"] else "não conectado ✗")
    print(f"Provedor: {ov['model']['provider'] or '-'}   Modelo: {ov['model']['default'] or '-'}")
    if ov["pending_session"]:
        p = ov["pending_session"]
        print(f"Login pendente: {p['user_code']} em {p['verification_url']} ({p['expires_in_seconds']}s)")
    return 0


def _cmd_set_model(args) -> int:
    if not flow.auth_status().get("logged_in"):
        print("✗ Codex não conectado. Rode `hermes codex-oauth login` primeiro.", file=sys.stderr)
        return 1
    r = flow.set_model(args.model)
    print(f"✓ model.provider={r['provider']}  model.default={r['default']}")
    return 0


def _cmd_models(args) -> int:
    for m in flow.suggested_models():
        print(m)
    return 0


def _cmd_cancel(args) -> int:
    out = flow.cancel(None)
    print("Sessão cancelada." if out else "Nenhuma sessão pendente.")
    return 0


def _cmd_claude_login(args) -> int:
    try:
        sess = flow.anthropic_start(force=True)
    except Exception as exc:
        print(f"✗ Não foi possível iniciar: {exc}", file=sys.stderr)
        return 1
    print("Autorize o Hermes na sua conta Claude Pro/Max:\n")
    print(f"  1. Abra no navegador:  {sess['auth_url']}")
    print("  2. Autorize e copie o código exibido.\n")
    try:
        code = input("Cole o código aqui: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        return 130
    try:
        flow.anthropic_submit(code, sess["session_id"])
    except Exception as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print("✓ Claude conectado e tokens salvos no pool de credenciais")
    if not args.no_set_model:
        r = flow.anthropic_set_model(args.model)
        print(f"✓ model.provider={r['provider']}  model.default={r['default']}")
    return 0


def _cmd_claude_status(args) -> int:
    ov = flow.anthropic_overview()
    print("Claude OAuth:", "conectado ✓" if ov["logged_in"] else "não conectado ✗")
    print(f"Provedor: {ov['model']['provider'] or '-'}   Modelo: {ov['model']['default'] or '-'}")
    return 0


def _cmd_claude_set_model(args) -> int:
    if not flow.anthropic_status().get("logged_in"):
        print("✗ Claude não conectado. Rode `hermes codex-oauth claude-login` primeiro.", file=sys.stderr)
        return 1
    r = flow.anthropic_set_model(args.model)
    print(f"✓ model.provider={r['provider']}  model.default={r['default']}")
    return 0


_DISPATCH = {
    "claude-login": _cmd_claude_login, "claude-status": _cmd_claude_status, "claude-set-model": _cmd_claude_set_model,
    "login": _cmd_login, "status": _cmd_status, "set-model": _cmd_set_model,
    "models": _cmd_models, "cancel": _cmd_cancel,
}


def command(args) -> int:
    name = getattr(args, "codex_oauth_command", None) or "status"
    return _DISPATCH[name](args)
