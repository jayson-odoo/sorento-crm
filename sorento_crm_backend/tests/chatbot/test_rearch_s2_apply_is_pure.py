"""S2 - `apply()` is pure: one function, no text, no I/O, no imports from the old
seams (AC-1520, PLAN-chatbot-turn-rearch.md "APPLY contract" + "Testing seams").

`app/services/chatbot/turn/` does not exist yet - EVERY test in this file is RED with
`ModuleNotFoundError: No module named 'app.services.chatbot.turn'` (or, for the two
source-scan tests, an explicit `pytest.fail` when the package directory itself is
missing, so an empty glob can never read as a vacuous pass).
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from tests.chatbot._turn_helpers import build_policy, verdict

TURN_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot" / "turn"
)

FORBIDDEN_IMPORT_ROOTS = {"head", "dialogue", "tail", "engine"}


def _turn_files() -> list[pathlib.Path]:
    if not TURN_DIR.is_dir():
        pytest.fail(f"app/services/chatbot/turn/ does not exist yet: {TURN_DIR}", pytrace=False)
    files = sorted(TURN_DIR.glob("*.py"))
    if not files:
        pytest.fail(f"app/services/chatbot/turn/ has no .py files yet: {TURN_DIR}", pytrace=False)
    return files


def test_apply_function_exists_with_the_contract_signature():
    from app.services.chatbot.turn.apply import apply

    sig = inspect.signature(apply)
    params = list(sig.parameters)
    assert params[:3] == ["state", "verdict", "policy"], params
    assert "resolved" in sig.parameters, params
    assert sig.parameters["resolved"].default is None


@pytest.mark.parametrize("forbidden_root", sorted(FORBIDDEN_IMPORT_ROOTS))
def test_turn_package_imports_nothing_from_the_old_seams(forbidden_root):
    for path in _turn_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                module_root = node.module.split(".")[0]
                # `app.services.chatbot.head` etc - check the first segment AFTER
                # `app.services.chatbot`, not the bare top-level `app`.
                parts = node.module.split(".")
                if "chatbot" in parts:
                    idx = parts.index("chatbot")
                    if len(parts) > idx + 1 and parts[idx + 1] == forbidden_root:
                        pytest.fail(f"{path.name} imports from chatbot.{forbidden_root}: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if "chatbot" in parts:
                        idx = parts.index("chatbot")
                        if len(parts) > idx + 1 and parts[idx + 1] == forbidden_root:
                            pytest.fail(f"{path.name} imports chatbot.{forbidden_root}: {alias.name}")


def test_turn_package_never_calls_re_dot_or_reads_dot_text():
    """Grep guard, not an AST scan - `re.` and `.text` are source-level tells (a
    regex call, a raw-text read) the PLAN forbids inside `apply`'s pure core."""
    hits = []
    for path in _turn_files():
        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "re." in line or ".text" in line or "message.text" in line or "message[" in line:
                hits.append(f"{path.name}:{lineno}: {stripped}")
    assert not hits, hits


def test_apply_is_pure_equal_inputs_give_equal_outputs():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(entities=[{"raw": "SRTWC8517", "hint": "product"}])
    policy = build_policy()

    state1, plan1 = apply(state, v, policy)
    state2, plan2 = apply(state, v, policy)

    assert state1 == state2
    assert plan1 == plan2
