"""Contract snapshot for the reflected tool surface (see docs/ADAPTER_API_CONTRACT.md).

``PlannerAPIAdapter``'s public methods are reflected into model-facing tools by both
the LLM agent (``llms.llm_handler._build_tools``) and the MCP server
(``tm_bot.mcp_server.tools.register_adapter_tools``). That makes method names,
parameter names/defaults, first-line docstrings, and the exposed set a *published
API*: changing any of them silently moves what Claude/ChatGPT see.

This test snapshots that surface and fails on any drift, so the blast radius of an
adapter edit shows up in review. The surface is derived by **statically parsing**
``planner_api_adapter.py`` (no runtime deps / no DB), plus the exclusion sets from
``llms.tool_exposure``.

To accept an intentional change, regenerate the snapshot:

    UPDATE_TOOL_CONTRACT=1 pytest tm_bot/tests/test_adapter_tool_contract.py

and commit the updated ``adapter_tool_contract.snapshot.json`` in the same PR.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Dict, List

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADAPTER_SRC = _REPO_ROOT / "tm_bot" / "services" / "planner_api_adapter.py"
_SNAPSHOT_PATH = Path(__file__).resolve().parent / "adapter_tool_contract.snapshot.json"

# Stripped from model-facing signatures by llms/tool_wrappers._wrap_tool.
_HIDDEN_PARAMS = {"self", "user_id"}


def _first_doc_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node, clean=True) or ""
    return doc.splitlines()[0].strip() if doc else ""


def _method_signature(node) -> Dict[str, List[str]]:
    """Model-facing params and required params for one adapter method (mirrors _wrap_tool)."""
    a = node.args
    positional = list(a.posonlyargs) + list(a.args)
    # defaults align to the tail of `positional`
    num_defaults = len(a.defaults)
    defaulted = set(p.arg for p in positional[len(positional) - num_defaults:]) if num_defaults else set()

    params: List[str] = []
    required: List[str] = []
    for p in positional:
        if p.arg in _HIDDEN_PARAMS:
            continue
        params.append(p.arg)
        if p.arg not in defaulted:
            required.append(p.arg)
    for p, d in zip(a.kwonlyargs, a.kw_defaults):
        if p.arg in _HIDDEN_PARAMS:
            continue
        params.append(p.arg)
        if d is None:  # kwonly with no default is required
            required.append(p.arg)
    return {"params": params, "required": required}


def _adapter_methods() -> Dict[str, Dict]:
    """Public callable surface of PlannerAPIAdapter, as the reflectors' ``dir()`` sees it.

    Captures both ``def`` methods and class-level assignment aliases
    (e.g. ``add_action = log_completed_activity``) — the latter are callable
    attributes that runtime reflection exposes, so they are part of the contract.
    """
    tree = ast.parse(_ADAPTER_SRC.read_text(encoding="utf-8"))
    cls = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PlannerAPIAdapter"),
        None,
    )
    assert cls is not None, "PlannerAPIAdapter class not found"

    out: Dict[str, Dict] = {}
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            sig = _method_signature(node)
            out[node.name] = {
                "params": sig["params"],
                "required": sig["required"],
                "doc": _first_doc_line(node),
            }

    # Resolve class-level aliases `name = other_name` to the target's signature/doc.
    for node in cls.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Name):
            continue
        target_name = node.value.id
        if target_name not in out:
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and not tgt.id.startswith("_") and tgt.id not in out:
                out[tgt.id] = {**out[target_name], "alias_of": target_name}
    return out


def _compute_snapshot() -> Dict:
    from llms.tool_exposure import LLM_EXCLUDED_TOOLS, MCP_EXCLUDED_TOOLS

    methods = _adapter_methods()
    names = set(methods)
    return {
        "adapter_methods": methods,
        "llm_exposed": sorted(names - set(LLM_EXCLUDED_TOOLS)),
        "mcp_exposed": sorted(names - set(MCP_EXCLUDED_TOOLS)),
    }


def test_adapter_tool_contract_matches_snapshot():
    current = _compute_snapshot()

    if os.environ.get("UPDATE_TOOL_CONTRACT") == "1" or not _SNAPSHOT_PATH.exists():
        _SNAPSHOT_PATH.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if os.environ.get("UPDATE_TOOL_CONTRACT") != "1":
            pytest.skip(f"Bootstrapped tool-contract snapshot at {_SNAPSHOT_PATH.name}; commit it.")
        return

    saved = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert current == saved, (
        "The reflected tool surface (PlannerAPIAdapter public methods / exposure) changed.\n"
        "This moves what the LLM agent AND the MCP server expose — see docs/ADAPTER_API_CONTRACT.md.\n"
        "If intentional, regenerate with:\n"
        "    UPDATE_TOOL_CONTRACT=1 pytest tm_bot/tests/test_adapter_tool_contract.py\n"
        "and commit the updated snapshot in the same PR."
    )


def test_no_excluded_tool_is_advertised_and_descriptions_exist():
    """Defense-in-depth: exposed tools must have a description, and exclusions must be real methods."""
    snap = _compute_snapshot()
    methods = snap["adapter_methods"]

    # Every exposed tool should carry a non-empty first-line docstring (its model description).
    missing_doc = [n for n in snap["mcp_exposed"] if not methods.get(n, {}).get("doc")]
    assert not missing_doc, f"MCP-exposed tools missing a docstring/description: {missing_doc}"

    # Exclusion lists should not reference methods that no longer exist (stale denylist entries).
    from llms.tool_exposure import LLM_EXCLUDED_TOOLS, MCP_EXCLUDED_TOOLS
    known = set(methods)
    stale_llm = sorted(set(LLM_EXCLUDED_TOOLS) - known)
    stale_mcp = sorted(set(MCP_EXCLUDED_TOOLS) - known)
    assert not stale_llm, f"LLM_EXCLUDED_TOOLS names no longer on the adapter: {stale_llm}"
    assert not stale_mcp, f"MCP_EXCLUDED_TOOLS names no longer on the adapter: {stale_mcp}"
