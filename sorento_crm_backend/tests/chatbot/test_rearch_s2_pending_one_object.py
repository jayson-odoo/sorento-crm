"""S2 - `Pending` is one object, one constructor (`pending.ask`), one resolver (inside
`apply`) (AC-1521, PLAN-chatbot-turn-rearch.md).

RIGHT NOW every test is RED. The AST-scan tests (arm/resolve site counts) fail with an
explicit `pytest.fail` when `app/services/chatbot/turn/` does not exist - never a
vacuous pass over zero files - and every other test fails with
`ModuleNotFoundError: No module named 'app.services.chatbot.turn'`.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

CHATBOT_DIR = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
TURN_DIR = CHATBOT_DIR / "turn"


def _all_chatbot_py_files() -> list[pathlib.Path]:
    return sorted(CHATBOT_DIR.rglob("*.py"))


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == name)
            or (isinstance(node.func, ast.Attribute) and node.func.attr == name)
        )
    ]


def test_pending_dot_ask_is_the_only_constructor_of_a_pending():
    """Every `Pending(` call site in `app/services/chatbot/` lives in `turn/pending.py`."""
    if not TURN_DIR.is_dir():
        pytest.fail("app/services/chatbot/turn/ does not exist yet", pytrace=False)
    sites = []
    for path in _all_chatbot_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in _calls_named(tree, "Pending"):
            sites.append(f"{path.relative_to(CHATBOT_DIR.parent.parent.parent)}:{call.lineno}")
    outside = [s for s in sites if "turn/pending.py" not in s]
    assert not outside, outside


def test_apply_is_the_only_pending_resolver():
    """No site outside `turn/apply.py` calls `resolve_pending(` or `.resolve(` on a
    Pending-shaped value."""
    if not TURN_DIR.is_dir():
        pytest.fail("app/services/chatbot/turn/ does not exist yet", pytrace=False)
    sites = []
    for path in _all_chatbot_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in ("resolve_pending", "resolve"):
            for call in _calls_named(tree, name):
                sites.append(f"{path.relative_to(CHATBOT_DIR.parent.parent.parent)}:{call.lineno}")
    outside = [s for s in sites if "turn/apply.py" not in s]
    assert not outside, outside


def test_pending_has_the_contract_fields():
    from app.services.chatbot.turn.pending import Pending

    fields = set(getattr(Pending, "__dataclass_fields__", {})) or set(
        getattr(Pending, "model_fields", {})
    )
    assert fields == {
        "kind",
        "expects",
        "options",
        "team",
        "payload",
        "asked_at_turn",
    }, fields


def test_pending_ask_constructs_from_kind_and_options():
    from app.services.chatbot.turn.pending import ask

    options = [
        {"position": 1, "label": "A", "uuid": "u1", "uuids": ["u1"], "entity_type": "product", "payload": {}},
    ]
    result = ask("member_offer", options, team="warehouse", asked_at_turn=7)
    assert result.kind == "member_offer"
    assert result.options == options
    assert result.asked_at_turn == 7


@pytest.mark.parametrize("kind", [
    "escalation_offer", "member_offer", "team_clarify", "outstanding_scope",
    "outstanding_detail", "tier_ask", "company_clarify", "disambiguation", "kind_pick",
])
def test_pending_kind_accepts_every_named_kind(kind):
    from app.services.chatbot.turn.pending import ask

    result = ask(kind, [], team=None, asked_at_turn=1)
    assert result.kind == kind


def test_asked_at_turn_is_set_from_state():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    from tests.chatbot._turn_helpers import build_policy, entity, verdict

    state = State(focus=Focus(), pending=None, profile=Profile(), turn_no=42)
    v = verdict(
        domain_hint="incoming",
        entities=[entity("wc286", hint="product", confident=True)],
    )
    _state2, plan = apply(state, v, build_policy())
    assert plan.ask is not None
    assert plan.ask.asked_at_turn == 42
