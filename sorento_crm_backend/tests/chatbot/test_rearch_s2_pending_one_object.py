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


def _pending_resolver_calls(tree: ast.AST, *, label: str) -> list[str]:
    """Sites that resolve a PENDING, narrowed (captain ruling, 16 Sep 2026, item 2) to:

    * a bare call to `resolve_pending(` or `answer_pending(`;
    * an attribute call `<receiver>.resolve(` whose receiver's own name CONTAINS
      "pending" (`pending.resolve(...)`, `state.pending.resolve(...)`, a variable named
      `pending_obj`, ...).

    Deliberately does NOT match every `.resolve(` in the package: `copy_mod.resolve(db)`
    / `reply_copy.resolve(db)` (canned-copy TEMPLATE resolution, `app/services/chatbot/
    copy.py` and `chatbot_reply_copy.py`) are a different `resolve` entirely, and matching
    on the method name alone made this guard fail on the merged tree for a reason that
    has nothing to do with Pending.
    """
    sites: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in ("resolve_pending", "answer_pending"):
            sites.append(f"{label}:{node.lineno}")
        elif isinstance(func, ast.Attribute) and func.attr == "resolve":
            receiver = func.value
            receiver_name = (
                receiver.id if isinstance(receiver, ast.Name)
                else getattr(receiver, "attr", "")
            )
            if "pending" in receiver_name.lower():
                sites.append(f"{label}:{node.lineno}")
    return sites


def test_apply_is_the_only_pending_resolver():
    """No site outside `turn/apply.py` resolves a Pending (see `_pending_resolver_calls`
    for exactly what counts)."""
    if not TURN_DIR.is_dir():
        pytest.fail("app/services/chatbot/turn/ does not exist yet", pytrace=False)
    sites = []
    for path in _all_chatbot_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        label = str(path.relative_to(CHATBOT_DIR.parent.parent.parent))
        sites.extend(_pending_resolver_calls(tree, label=label))
    outside = [s for s in sites if "turn/apply.py" not in s]
    assert not outside, outside


def test_the_guard_would_catch_a_pending_resolve_call_outside_apply():
    """Proves `_pending_resolver_calls` is not vacuously green: fed a small inline
    source string standing in for a violation in `engine.py`, it must be caught -
    a bare `answer_pending(` call and a `pending.resolve(...)` attribute call - while
    the canned-copy `copy_mod.resolve(db)` / `reply_copy.resolve(db)` shape it is
    deliberately narrowed away from stays silent."""
    violation_source = (
        "def _close_turn(pending, db):\n"
        "    answer_pending(pending, 2)\n"
        "    pending.resolve(2)\n"
        "    copy_mod.resolve(db)\n"
        "    reply_copy.resolve(db)\n"
    )
    tree = ast.parse(violation_source, filename="engine.py")
    sites = _pending_resolver_calls(tree, label="app/services/chatbot/engine.py")

    assert "app/services/chatbot/engine.py:2" in sites  # answer_pending(
    assert "app/services/chatbot/engine.py:3" in sites  # pending.resolve(
    assert not any(":4" in s for s in sites)  # copy_mod.resolve( excluded
    assert not any(":5" in s for s in sites)  # reply_copy.resolve( excluded


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
    "product_pick", "customer_pick", "tier_pick", "team_pick", "company_pick",
    "member_offer", "outstanding_scope", "outstanding_detail", "kind_pick",
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
    # Stale pin, re-pinned by tester 36 (review round, 20 Sep 2026): AC-1690
    # (`0c4864a4d`, already shipped BEFORE this round started) retired `turn/
    # narrow.py`'s own product roster entirely - `kind == "product"` now settles
    # through as entities unconditionally for every domain, so this test's own
    # `wc286`/`wc287` product fixture no longer arms `plan.ask` at all regardless
    # of candidate count (a require-specific product roster is minted later, by
    # `gate.py`, off the real resolver's candidates - a layer this function-level
    # `apply()` call never reaches). This test's own purpose is `Pending.
    # asked_at_turn`'s wiring, not which kind rosters, so it is re-pointed at a
    # kind `apply()` still rosters directly: `customer` under "order"
    # (must_narrow_one, `test_rearch_s2_narrower.py::
    # test_order_customer_with_three_candidate_families_asks_customer_pick`'s own
    # already-green shape), two candidates (AC-1691's own floor).
    v = verdict(
        domain_hint="order",
        entities=[
            entity("chin", hint="customer", confident=True),
            entity("chun", hint="customer", confident=True),
        ],
    )
    _state2, plan = apply(state, v, build_policy())
    assert plan.ask is not None
    assert plan.ask.kind == "customer_pick"
    assert plan.ask.asked_at_turn == 42
