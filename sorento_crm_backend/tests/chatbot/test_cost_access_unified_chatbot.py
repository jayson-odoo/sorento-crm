"""COST-ACCESS-UNIFIED, the chatbot half: AC-3 (WhatsApp lane), AC-4 (dealer), AC-5 (agent).

UAC `documentation/plans/procurement/cost-access-unified-11nov-acceptance-criteria.md`.
A contact sees cost iff its linked user is ACTIVE and holds `products.cost.view`; a stored
`purchase_orders.cost` reveal row decides nothing. The attributes the lane and the dealer swap read
come from the REAL `head.access._granted_field_reveal_keys` here (not a hand-written list), so the
tests drive the same seam production does. No LLM call: the parser is stubbed, the MCP is canned.

The service-level ACs (AC-1, AC-2, AC-6, AC-9) are in `tests/test_cost_access_unified.py`; they sit
there and this file sits here because only tests under `tests/chatbot/` may import the chatbot package.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.models.access import ContactFieldReveal
from app.services.chatbot import engine as engine_mod
from tests._cost_viewer_seed import COST_PERM, cost_viewer, link_user
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_contact, seed_user
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_parser  # noqa: F401
from tests.chatbot.test_last_cost_gate import TOOL, _cost_parser_output, _granted_cost_row, _turn_row, _wire

COST = "purchase_orders.cost"
OTHER_PERM = "inventory.stock.view"


# ---------------------------------------------------------------- shared seams


@pytest.fixture
def real_access(monkeypatch):
    """`check_access` with the contact's REAL granted keys as `attributes` (what production reports)."""
    from app.services.chatbot.head.access import _granted_field_reveal_keys

    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True,
            "decision": "allow",
            "agent_name": "General Enquiries",
            "attributes": _granted_field_reveal_keys(db, contact_id=str(contact_id), space_id=space_id),
            "all_attributes_allowed": None,
            "hidden_spec_keys": [],
        },
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")


def _pk(db) -> str:
    return db.execute(text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}).scalar()


def _stored(db, pk: str, granted: bool = True) -> None:
    db.add(ContactFieldReveal(respond_contact_id=pk, field_key=COST, granted=granted))
    db.commit()


def _link(db, pk: str, **kw) -> None:
    link_user(db, pk, **kw)
    db.commit()


def _run(session_factory, monkeypatch):
    """One cost turn through the real `run_turn`; returns (result, mcp calls)."""
    calls: list[tuple[str, dict]] = []

    def mcp_call(name: str, args: dict) -> str:
        calls.append((name, dict(args)))
        return json.dumps(_granted_cost_row())

    _wire(session_factory, monkeypatch, mcp_call=mcp_call)
    return engine_mod.run_turn(_envelope(), session_factory=session_factory), calls


def _denied_text() -> str:
    from app.services.chatbot_reply_copy import CHATBOT_REPLY_ACCESS_DENIED

    return CHATBOT_REPLY_ACCESS_DENIED.replace("{{team}}", "purchase cost")


# ---------------------------------------------------------------- AC-3: the WhatsApp business lane


def test_ac3_a_cost_viewer_linked_user_is_answered_with_no_stored_row(
    session_factory, seeded, stub_parser, real_access, monkeypatch
):
    stub_parser(_cost_parser_output())
    _link(seeded, _pk(seeded), slugs=(COST_PERM,))
    result, calls = _run(session_factory, monkeypatch)
    assert result.status == "done", result.error
    assert [c[0] for c in calls] == [TOOL], calls
    assert "Cost / unit" in (result.reply.get("text") or ""), result.reply


def test_ac3_an_admin_role_linked_user_is_answered(session_factory, seeded, stub_parser, real_access, monkeypatch):
    stub_parser(_cost_parser_output())
    _link(seeded, _pk(seeded), role_slug="admin")
    result, calls = _run(session_factory, monkeypatch)
    assert [c[0] for c in calls] == [TOOL], calls
    assert "Cost / unit" in (result.reply.get("text") or ""), result.reply


@pytest.mark.parametrize(
    "linked",
    [
        pytest.param(None, id="no_user"),
        pytest.param({"slugs": (OTHER_PERM,)}, id="user_without_permission"),
        pytest.param({"slugs": (COST_PERM,), "status": "INACTIVE"}, id="inactive_user"),
    ],
)
def test_ac3_a_stored_granted_row_without_a_cost_viewer_is_refused_in_the_existing_words(
    session_factory, seeded, stub_parser, real_access, monkeypatch, linked
):
    stub_parser(_cost_parser_output())
    pk = _pk(seeded)
    _stored(seeded, pk, True)
    if linked is not None:
        _link(seeded, pk, **linked)
    result, calls = _run(session_factory, monkeypatch)
    assert result.status == "done", result.error
    assert calls == [], f"the tool must not be called for a stored row alone: {calls!r}"
    assert (result.reply.get("text") or "") == _denied_text()
    trace = _turn_row(session_factory, result.turn_id).trace or []
    assert any(
        isinstance(e, dict) and e.get("skipped") == "not_granted" and e.get("needs") == COST for e in trace
    ), trace


def test_ac3_the_real_access_attributes_carry_cost_for_a_viewer_and_not_for_a_stored_row(session_factory, seeded):
    from app.services.chatbot.head.access import _granted_field_reveal_keys

    pk = _pk(seeded)
    assert COST not in _granted_field_reveal_keys(seeded, contact_id=str(CONTACT_ID), space_id="364817")
    _stored(seeded, pk, True)
    assert COST not in _granted_field_reveal_keys(seeded, contact_id=str(CONTACT_ID), space_id="364817")
    _link(seeded, pk, slugs=(COST_PERM,))
    assert COST in _granted_field_reveal_keys(session_factory(), contact_id=str(CONTACT_ID), space_id="364817")


# ---------------------------------------------------------------- AC-4: the dealer path (`_dealer_cost_as_promotion`)


class _Trace:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def add(self, name: str, payload: Any = None) -> None:
        self.events.append((name, payload))


def _dealer_tag(db, pk: str) -> None:
    import uuid

    tid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO contact_tags (id, name, is_active, settings) VALUES (:i, :n, true, CAST(:s AS jsonb))"),
        {"i": tid, "n": f"ZZT dealer {tid[:8]}", "s": json.dumps({"chatbot": {"tier": "dealer"}})},
    )
    db.execute(text("INSERT INTO respond_contact_tags (contact_id, tag_id) VALUES (:c, :t)"), {"c": pk, "t": tid})
    db.flush()


def _cost_verdict() -> dict[str, Any]:
    return {"domain_hint": "purchase_cost", "intent_hint": "check_po_cost", "asks": []}


def _swap(db, pk: str) -> dict[str, Any]:
    """The dealer swap fed the contact's REAL granted keys, as the engine feeds it."""
    from app.services.contact_field_reveal_service import granted_keys

    access = {"allowed": True, "attributes": granted_keys(db, pk)}
    return engine_mod._dealer_cost_as_promotion(db, _cost_verdict(), access, pk, _Trace())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def test_ac4_a_dealer_with_a_stored_cost_row_and_no_user_still_gets_promotions(db):
    pk = seed_contact(db)["pk"]
    _dealer_tag(db, pk)
    db.add(ContactFieldReveal(respond_contact_id=pk, field_key=COST, granted=True))
    db.flush()
    out = _swap(db, pk)
    assert out["domain_hint"] == "promotion" and out["intent_hint"] == "check_promotion", out


def test_ac4_a_dealer_with_a_stored_row_and_a_user_lacking_the_permission_gets_promotions(db):
    pk = seed_contact(db)["pk"]
    _dealer_tag(db, pk)
    db.add(ContactFieldReveal(respond_contact_id=pk, field_key=COST, granted=True))
    link_user(db, pk, slugs=(OTHER_PERM,))
    db.flush()
    out = _swap(db, pk)
    assert out["domain_hint"] == "promotion", out


def test_ac4_a_dealer_with_an_inactive_cost_user_gets_promotions(db):
    pk = seed_contact(db)["pk"]
    _dealer_tag(db, pk)
    link_user(db, pk, slugs=(COST_PERM,), status="INACTIVE")
    out = _swap(db, pk)
    assert out["domain_hint"] == "promotion", out


def test_ac4_a_dealer_with_no_row_and_no_user_gets_promotions(db):
    pk = seed_contact(db)["pk"]
    _dealer_tag(db, pk)
    out = _swap(db, pk)
    assert out["domain_hint"] == "promotion", out


def test_ac4_a_dealer_whose_linked_user_is_a_cost_viewer_keeps_the_cost_ask(db):
    pk = seed_contact(db)["pk"]
    _dealer_tag(db, pk)
    cost_viewer(db, pk)  # no stored row at all
    out = _swap(db, pk)
    assert out["domain_hint"] == "purchase_cost" and out["intent_hint"] == "check_po_cost", out


def test_ac4_a_non_dealer_is_never_swapped(db):
    pk = seed_contact(db)["pk"]
    out = _swap(db, pk)
    assert out["domain_hint"] == "purchase_cost", out


# ---------------------------------------------------------------- AC-5: the agent


@pytest.fixture
def agent_db():
    with blank_session() as session:
        yield session


LAST_COST = "crm_procurement_po_last_cost_list"


def test_ac5_a_contact_principal_with_a_stored_row_never_gets_the_last_cost_tool(agent_db):
    from app.services.chatbot.agent.access import build_context

    contact = seed_contact(agent_db)
    agent_db.add(ContactFieldReveal(respond_contact_id=contact["pk"], field_key=COST, granted=True))
    agent_db.flush()
    ctx = build_context(agent_db, contact["respond_id"])
    assert ctx.principal == "contact"
    assert LAST_COST not in ctx.tool_names
    assert COST not in ctx.grants


def test_ac5_a_contact_whose_linked_user_is_inactive_is_a_contact_principal_without_the_tool(agent_db):
    from app.services.chatbot.agent.access import build_context

    contact = seed_contact(agent_db)
    agent_db.add(ContactFieldReveal(respond_contact_id=contact["pk"], field_key=COST, granted=True))
    seed_user(agent_db, contact_pk=contact["pk"], slugs=(COST_PERM,), status="INACTIVE")
    agent_db.flush()
    ctx = build_context(agent_db, contact["respond_id"])
    assert ctx.principal == "contact"
    assert LAST_COST not in ctx.tool_names


def test_ac5_a_user_principal_holding_the_permission_gets_the_tool_with_no_stored_row(agent_db):
    from app.services.chatbot.agent.access import build_context

    contact = seed_contact(agent_db)
    seed_user(agent_db, contact_pk=contact["pk"], slugs=(COST_PERM,))
    ctx = build_context(agent_db, contact["respond_id"])
    assert ctx.principal == "user"
    assert LAST_COST in ctx.tool_names
    assert COST in ctx.grants


def test_ac5_a_user_principal_with_a_stored_row_but_no_permission_gets_nothing(agent_db):
    from app.services.chatbot.agent.access import build_context

    contact = seed_contact(agent_db)
    agent_db.add(ContactFieldReveal(respond_contact_id=contact["pk"], field_key=COST, granted=True))
    seed_user(agent_db, contact_pk=contact["pk"], slugs=(OTHER_PERM,))
    agent_db.flush()
    ctx = build_context(agent_db, contact["respond_id"])
    assert ctx.principal == "user"
    assert LAST_COST not in ctx.tool_names
    assert COST not in ctx.grants


def test_ac5_an_admin_role_user_principal_gets_the_tool(agent_db):
    from app.services.chatbot.agent.access import build_context

    contact = seed_contact(agent_db)
    link_user(agent_db, contact["pk"], role_slug="admin")
    ctx = build_context(agent_db, contact["respond_id"])
    assert LAST_COST in ctx.tool_names


def test_ac5_the_grants_hash_moves_when_the_permission_is_the_only_change(agent_db):
    """A lost or gained cost permission must start a new conversation (the hash covers grants and tools)."""
    from app.services.chatbot.agent.access import build_context, grants_hash

    plain = seed_contact(agent_db)
    seed_user(agent_db, contact_pk=plain["pk"], slugs=(OTHER_PERM,))
    viewer = seed_contact(agent_db)
    seed_user(agent_db, contact_pk=viewer["pk"], slugs=(OTHER_PERM, COST_PERM))
    assert grants_hash(build_context(agent_db, plain["respond_id"])) != grants_hash(
        build_context(agent_db, viewer["respond_id"])
    )


def test_ac9_the_staff_panel_principal_still_reveals_cost_from_the_permission(agent_db):
    """AC-9: `staff_reveal_keys` is untouched, so the panel's staff principal keeps its cost reveal."""
    from app.services.contact_field_reveal_service import staff_reveal_keys

    contact = seed_contact(agent_db)
    holder = seed_user(agent_db, contact_pk=contact["pk"], slugs=(COST_PERM,))
    assert COST in staff_reveal_keys(agent_db, holder)
