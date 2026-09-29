"""Testes básicos: manifesto coerente com as ferramentas e fluxo sem rede."""

import sys
import time
import types
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.name.replace("-", "_")


def _load():
    """Importa o plugin como pacote a partir da pasta (o Hermes faz o mesmo via pacote sintético)."""
    import importlib.util
    if PKG in sys.modules:
        return sys.modules[PKG]
    spec = importlib.util.spec_from_file_location(PKG, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)
    return mod


def test_manifest_matches_tools():
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    mod = _load()
    names = {t[0] for t in mod._tools.TOOLS}
    assert set(manifest["provides_tools"]) == names
    for f in ("name", "version", "description"):
        assert manifest[f]


def test_register_records_every_tool():
    mod = _load()
    seen = {"tools": [], "commands": [], "cli": [], "prompt": [], "skill": []}

    class Ctx:
        def register_tool(self, name, toolset, schema, handler, **kw):
            assert schema["name"] == name and callable(handler)
            seen["tools"].append(name)
        def register_command(self, name, handler, **kw): seen["commands"].append(name)
        def register_cli_command(self, name, **kw): seen["cli"].append(name)
        def register_system_prompt_section(self, id, content, **kw): seen["prompt"].append(id)
        def register_skill(self, name, path, **kw): seen["skill"].append(name)

    mod.register(Ctx())
    assert len(seen["tools"]) == 9
    assert seen["commands"] == ["codex-login", "codex-status", "codex-model", "claude-login", "claude-code", "claude-status", "claude-model"]
    assert seen["cli"] == ["codex-oauth"] and seen["prompt"] == ["codex-oauth.guide"]


def test_public_view_hides_device_auth_id():
    mod = _load()
    sess = {"id": "abc", "status": "pending", "user_code": "AAAA-BBBB", "device_auth_id": "secret",
            "verification_url": mod.flow.VERIFICATION_URL, "expires_at": time.time() + 60, "error": ""}
    out = mod.flow.public(sess)
    assert "device_auth_id" not in out and out["user_code"] == "AAAA-BBBB" and out["expires_in_seconds"] > 0
