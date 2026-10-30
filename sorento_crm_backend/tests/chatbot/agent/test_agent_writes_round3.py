"""AGENTIC-P3 review round 3 (PLAN-agentic-p3-writes-30oct.md, "Review round 3").

R13: the route's own-customer rule (`_assert_still_theirs`) is applied for each person, so a `view_own`
console operator acting for a linked user who holds `view` cannot move an opportunity onto, create on, or
stamp a prospect to another agent's customer. R14: `crm_agent_actions_recent` is for the linked user
themself. R15: the waiting-change reference is not a user-role message.

Every test has a positive control (the same call on the operator's own customer or agent, or without the
narrowing) so it cannot pass because a tool or argument is missing. Assumed: the create tool accepts a
`sales_agent_id` argument (the plan's "the passed sales_agent_id"); today it does not, so the control of
case (c) is red until it does.
"""
from __future__ import annotations

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.base import company_scope
from app.models.sales import SalesOpportunity
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from tests._ask_todo_seed import SORENTO
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent.test_agent_writes import answer_, make_world as ask_world, proposal_script, tool_names
from tests.chatbot.agent.test_agent_writes_opportunity import (  # noqa: F401 - helpers, not tests
    ADD_SLUG,
    CREATE,
    EDIT_SLUG,
    FULL,
    OWN_ONLY,
    OWN_SLUG,
    UPDATE,
    VIEW_SLUG,
    make_opp,
    make_world as opp_world,
    opp_now,
    stage,
)
from tests.chatbot.agent.test_agent_writes_round1 import ASK_EDIT, ASK_VIEW, REFERENCE, Prov, _no_mcp, go, operator_with
from tests.chatbot.agent.test_agent_writes_round2 import (  # noqa: F401 - helpers, not tests
    console_confirm,
    grant,
    make_operator,
    propose,
    read,
    refused,
    revoke,
    store,
)

RECENT = "crm_agent_actions_recent"
CLOSE = "2026-12-01"
WIDE = (VIEW_SLUG, EDIT_SLUG, ADD_SLUG)


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def scene(db):
    """The linked user holds `view`. `narrow` is a view_own operator and `wide` a view operator, each with an
    own sales agent, customer and opportunity. `w.mine` / `w.me` are the linked user's customer and agent."""
    w = opp_world(db, slugs=FULL)
    narrow = make_operator(db, OWN_ONLY)
    wide = make_operator(db, WIDE)
    narrow_opp = make_opp(db, w, customer=narrow.customer, agent=narrow.agent)
    wide_opp = make_opp(db, w, customer=wide.customer, agent=wide.agent)
    return w, narrow, wide, narrow_opp, wide_opp


def spare_customer(db, op):
    customer = seed_customer(db, unique_code("Spare"), op.agent)
    db.commit()
    return customer


# ------------------------------------------------------------------ R13: (a) update onto another customer


def test_r13_a_view_own_operator_cannot_move_their_opportunity_onto_another_agents_customer(db):
    w, narrow, wide, narrow_opp, wide_opp = scene(db)
    own_other = spare_customer(db, narrow)

    control, step = propose(db, w, narrow.user_id, UPDATE, {"opportunity_id": narrow_opp.id, "customer_id": own_other.id}, narrow_opp.id, own_other.id)
    res, none = propose(db, w, narrow.user_id, UPDATE, {"opportunity_id": narrow_opp.id, "customer_id": w.mine.id}, narrow_opp.id, w.mine.id)
    broad, _ = propose(db, w, wide.user_id, UPDATE, {"opportunity_id": wide_opp.id, "customer_id": w.mine.id}, wide_opp.id, w.mine.id)

    assert control.status == "proposed" and step is not None  # their own other customer is fine
    assert broad.status == "proposed"  # a view operator may
    assert refused(res, none)


@pytest.mark.parametrize("narrowed, expected", [(True, "rejected"), (False, "executed")])
def test_r13_a_update_onto_another_customer_is_rechecked_after_the_operator_is_narrowed(db, narrowed, expected):
    w, narrow, wide, narrow_opp, wide_opp = scene(db)
    action = store(db, w, wide.user_id, [(UPDATE, {"opportunity_id": wide_opp.id, "customer_id": w.mine.id})], {wide_opp.id, w.mine.id})
    if narrowed:
        revoke(db, wide.user_id, VIEW_SLUG)
        grant(db, wide.user_id, OWN_SLUG)

    outcome = console_confirm(db, w, action, wide.user_id)

    assert outcome.status == expected
    assert (str(opp_now(db, wide_opp.id).customer_id) == w.mine.id) is (not narrowed)


# ------------------------------------------------------------------ R13: (b) create on another agent's customer


def create_args(customer_id, title=None):
    return {"title": title or unique_code("New"), "customer_id": customer_id, "expected_close_date": CLOSE}


def test_r13_a_view_own_operator_cannot_create_an_opportunity_on_another_agents_customer(db):
    w, narrow, wide, *_ = scene(db)

    control, step = propose(db, w, narrow.user_id, CREATE, create_args(narrow.customer.id), narrow.customer.id)
    res, none = propose(db, w, narrow.user_id, CREATE, create_args(w.mine.id), w.mine.id)
    broad, _ = propose(db, w, wide.user_id, CREATE, create_args(w.mine.id), w.mine.id)

    assert control.status == "proposed" and step is not None
    assert broad.status == "proposed"
    assert refused(res, none)


@pytest.mark.parametrize("narrowed, expected", [(True, "rejected"), (False, "executed")])
def test_r13_a_create_on_another_customer_is_rechecked_after_the_operator_is_narrowed(db, narrowed, expected):
    w, narrow, wide, *_ = scene(db)
    title = unique_code("Recheck")
    action = store(db, w, wide.user_id, [(CREATE, create_args(w.mine.id, title))], {w.mine.id})
    if narrowed:
        revoke(db, wide.user_id, VIEW_SLUG)
        grant(db, wide.user_id, OWN_SLUG)

    outcome = console_confirm(db, w, action, wide.user_id)

    assert outcome.status == expected
    with company_scope(db, None):
        made = db.query(SalesOpportunity).filter(SalesOpportunity.title == title).count()
    assert made == (0 if narrowed else 1)


# ------------------------------------------------------------------ R13: (c) a prospect stamped to another agent


def prospect_args(agent_id, title=None):
    return {
        "title": title or unique_code("Prospect"), "prospect_name": unique_code("Fake Showroom"),
        "expected_close_date": CLOSE, "sales_agent_id": agent_id,
    }


def test_r13_a_view_own_operator_cannot_stamp_a_prospect_to_another_agent(db):
    w, narrow, wide, *_ = scene(db)

    control, step = propose(db, w, narrow.user_id, CREATE, prospect_args(narrow.agent.id), narrow.agent.id)
    res, none = propose(db, w, narrow.user_id, CREATE, prospect_args(w.me.id), w.me.id)
    broad, _ = propose(db, w, wide.user_id, CREATE, prospect_args(w.me.id), w.me.id)

    assert control.status == "proposed" and step is not None  # their own agent is fine
    assert broad.status == "proposed"
    assert refused(res, none)


def test_r13_a_view_own_operator_cannot_create_a_prospect_with_no_agent(db):
    """Security round 3 should-fix: the service stamps no agent on a bare prospect, so a view_own person
    would create a row they cannot see. They must name one of their own agents."""
    w, narrow, wide, *_ = scene(db)
    bare = {k: v for k, v in prospect_args(None).items() if k != "sales_agent_id"}

    control, step = propose(db, w, narrow.user_id, CREATE, prospect_args(narrow.agent.id), narrow.agent.id)
    res, none = propose(db, w, narrow.user_id, CREATE, bare)
    broad, _ = propose(db, w, wide.user_id, CREATE, dict(bare))

    assert control.status == "proposed" and step is not None
    assert broad.status == "proposed"  # a full-view person may log an unassigned prospect
    assert refused(res, none)


@pytest.mark.parametrize("narrowed, expected", [(True, "rejected"), (False, "executed")])
def test_r13_a_prospect_stamp_is_rechecked_after_the_operator_is_narrowed(db, narrowed, expected):
    w, narrow, wide, *_ = scene(db)
    title = unique_code("StampRecheck")
    action = store(db, w, wide.user_id, [(CREATE, prospect_args(w.me.id, title))], {w.me.id})
    if narrowed:
        revoke(db, wide.user_id, VIEW_SLUG)
        grant(db, wide.user_id, OWN_SLUG)

    outcome = console_confirm(db, w, action, wide.user_id)

    assert outcome.status == expected
    with company_scope(db, None):
        made = db.query(SalesOpportunity).filter(SalesOpportunity.title == title).count()
    assert made == (0 if narrowed else 1)


# ------------------------------------------------------------------ R14: recent changes for the linked user only


def test_r14_recent_actions_is_offered_to_the_linked_user_and_refused_for_another_operator(db):
    w = ask_world(db)
    holder = make_operator(db, (ASK_VIEW, ASK_EDIT))
    own, _ = read(db, w, None, RECENT, {})
    same, _ = read(db, w, w.user_id, RECENT, {})  # the operator IS the linked user
    other, seen = read(db, w, holder.user_id, RECENT, {})

    assert own.status == "ok" and same.status == "ok"  # controls
    assert other.status == "denied"
    assert not seen


def test_r14_the_tool_is_absent_from_a_turn_run_by_another_operator(db):
    w = ask_world(db)
    holder = operator_with(db, ASK_VIEW, ASK_EDIT)

    _, as_holder = go(db, w, [answer_("Hi.")], operator=holder)
    _, as_linked = go(db, w, [answer_("Hi.")], operator=w.user_id)
    _, as_chat = go(db, w, [answer_("Hi.")], operator=None)

    assert RECENT in tool_names(as_linked) and RECENT in tool_names(as_chat)  # controls
    assert RECENT not in tool_names(as_holder)


# ------------------------------------------------------------------ R15: the reference is not a user message


def test_r15_the_waiting_change_reference_is_an_assistant_message_before_the_users_text(db):
    w = ask_world(db)
    first, _ = go(db, w, proposal_script(w.asks))
    summary = first.pending_action["lines"][0]

    _, prov = go(db, w, [answer_("Something is waiting.")], text_="what is waiting?")

    messages = prov.seen[0]["messages"]
    holders = [i for i, m in enumerate(messages) if REFERENCE in str(m.get("content"))]
    carrying = [m for m in messages if m["role"] == "user" and REFERENCE in str(m.get("content"))]
    assert holders, "no message carries the reference"
    assert summary in messages[holders[0]]["content"]  # control: the reference is there
    assert not carrying, "the reference is sent with the user role"
    assert messages[holders[0]]["role"] == "assistant"
    last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
    assert messages[last_user]["content"] == "what is waiting?"
    assert holders[0] < last_user
