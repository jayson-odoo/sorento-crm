"""AGENTIC-P3 slice 2 (PLAN-agentic-p3-writes-30oct.md, "Build contract, slices 2 and 3"): W2 sales
opportunities through the proposal path.

Red tests, written before the tools exist. Service level (`writes.propose_step`,
`actions.store_proposal`, `actions.confirm`) with the real route functions, plus one turn-level test.
Postgres only (blank schema). Every test seeds its own chain: a user linked to the agent contact, the
sales agent that user is, customers on that agent and on another agent, the opportunity status graph
and lost reasons (`sales_seed_service`), and opportunities made through the real service.

Assumed argument names (they mirror `SalesOpportunityCreate` / `SalesOpportunityUpdate`):
create `title`, `customer_id`, `expected_close_date` (ISO text); update `opportunity_id`, `status_id`,
`lost_reason`, `customer_id`.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.company import UserCompany
from app.models.lookup import LookupOption, LookupSet
from app.models.sales import SalesOpportunity
from app.models.status import Status
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from app.services.sales import opportunity_service, sales_seed_service
from tests._ask_todo_seed import SORENTO
from tests._ask_todo_seed import agent as seed_sales_agent
from tests._ask_todo_seed import contact as seed_plain_contact
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user
from tests.chatbot.agent.test_agent_writes import (  # noqa: F401 - helpers, not tests
    PROPOSAL_HEAD,
    answer_,
    round_of,
    run_turn,
    tc,
    tool_names,
)

LIST = "crm_opportunities_list"
META = "crm_opportunity_meta"
CREATE = "crm_opportunity_create"
UPDATE = "crm_opportunity_update"
ADD_SLUG = "sales.opportunities.add"
EDIT_SLUG = "sales.opportunities.edit"
VIEW_SLUG = "sales.opportunities.view"
OWN_SLUG = "sales.opportunities.view_own"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
FULL = (VIEW_SLUG, ADD_SLUG, EDIT_SLUG)
OWN_ONLY = (OWN_SLUG, ADD_SLUG, EDIT_SLUG)
CLOSE = "2026-12-01"


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


@dataclass
class OppWorld:
    contact: dict
    user_id: str
    me: object
    other: object
    mine: object  # a customer of the user's agent
    theirs: object  # a customer of another agent

    @property
    def respond_id(self) -> str:
        return self.contact["respond_id"]


def make_world(db, *, slugs=FULL) -> OppWorld:
    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"], slugs=slugs)
    db.add(UserCompany(user_id=user_id, company_id=SORENTO))
    db.flush()
    with company_scope(db, frozenset({SORENTO})):
        sales_seed_service.run(db)
    me = seed_sales_agent(db, contact["pk"], "ME")
    other = seed_sales_agent(db, seed_plain_contact(db, "Other agent"), "OT")
    w = OppWorld(
        contact=contact, user_id=user_id, me=me, other=other,
        mine=seed_customer(db, unique_code("Mine"), me),
        theirs=seed_customer(db, unique_code("Theirs"), other),
    )
    db.commit()
    return w


def make_opp(db, w: OppWorld, *, customer=None, agent=None, title=None) -> SalesOpportunity:
    with company_scope(db, frozenset({SORENTO})):
        opp = opportunity_service.create_opportunity(
            db,
            company_id=SORENTO,
            payload={
                "title": title or unique_code("Opp"),
                "expected_close_date": date(2026, 12, 1),
                "customer_id": (customer or w.mine).id,
            },
            sales_agent_id=(agent or w.me).id,
            source="crm",
            created_by_user_id=w.user_id,
        )
    db.commit()
    return opp


def opp_now(db, opp_id: str) -> SalesOpportunity:
    db.expire_all()
    with company_scope(db, None):
        return db.query(SalesOpportunity).filter(SalesOpportunity.id == str(opp_id)).one()


def stage(db, key: str) -> Status:
    with company_scope(db, None):
        return (
            db.query(Status)
            .filter(Status.entity_type == "sales_opportunity", Status.key == key, Status.scope_id.is_(None))
            .one()
        )


def a_lost_reason(db) -> str:
    with company_scope(db, None):
        return (
            db.query(LookupOption)
            .join(LookupSet, LookupSet.id == LookupOption.set_id)
            .filter(LookupSet.set_key == "sales_opportunity_lost_reasons", LookupOption.is_active.is_(True))
            .order_by(LookupOption.sort_order)
            .first()
            .value
        )


def ctx_of(db, w):
    from app.services.chatbot.agent.access import build_context

    return build_context(db, w.respond_id)


def propose_and_store(db, w, calls, seen):
    """propose_step for each (name, args), then one stored proposal. Returns (steps, action row)."""
    from app.services.chatbot.agent import actions, writes

    ctx = ctx_of(db, w)
    steps = []
    for name, args in calls:
        res, step = writes.propose_step(db, ctx, name, args, seen_ids={s.lower() for s in seen})
        assert res.status == "proposed", f"{name}: {res.status} {res.message}"
        steps.append(step)
    row = actions.store_proposal(
        db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=steps
    )
    return steps, row


def audit_rows(db, entity_id: str) -> list:
    return db.query(AuditLog).filter(AuditLog.entity_id == str(entity_id)).order_by(AuditLog.changed_at).all()


# ------------------------------------------------------------------ registry and exposure


def test_the_registry_holds_the_two_opportunity_writes_and_the_two_reads():
    from app.services.chatbot.agent import writes

    assert {CREATE, UPDATE} <= set(writes.WRITES)
    assert {LIST, META} <= set(writes.USER_READS)
    assert writes.WRITES[CREATE].user_permission == ADD_SLUG and writes.WRITES[CREATE].record_key == ""
    assert writes.WRITES[UPDATE].user_permission == EDIT_SLUG and writes.WRITES[UPDATE].record_key == "opportunity_id"


def test_a_user_without_the_add_slug_is_not_offered_create_but_is_offered_update(db):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=(VIEW_SLUG, EDIT_SLUG))

    names = {d.name for d in writes.permitted_writes(db, ctx_of(db, w))}

    assert UPDATE in names and CREATE not in names


# ------------------------------------------------------------------ create


def test_create_is_proposed_without_writing_then_confirmed_with_the_agent_stamped_and_audited(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    title = unique_code("Showroom")
    steps, row = propose_and_store(
        db, w,
        [(CREATE, {"title": title, "customer_id": w.mine.id, "expected_close_date": CLOSE})],
        seen={w.mine.id},
    )

    assert steps[0]["summary"] == f'Create opportunity "{title}" for {w.mine.customer_code}, close {CLOSE}'
    assert not UUID_RE.search(steps[0]["summary"])
    assert steps[0]["before"] == {}
    with company_scope(db, None):
        assert db.query(SalesOpportunity).filter(SalesOpportunity.title == title).count() == 0

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "executed"
    assert [s["status"] for s in outcome.steps] == ["done"]
    created = action_result_id(db, row.id)
    opp = opp_now(db, created)
    assert opp.title == title
    assert str(opp.customer_id) == w.mine.id
    assert str(opp.sales_agent_id) == w.me.id  # stamped from the customer
    assert str(opp.created_by_user_id) == w.user_id
    mine = [a for a in audit_rows(db, created) if a.auth_method == "agent"]
    assert mine, "the create left no audit row with auth_method agent"
    assert all(str(a.user_id) == w.user_id and a.actor_type == "user" for a in mine)


def action_result_id(db, action_id) -> str:
    from tests.chatbot.agent.test_agent_writes import action_row

    return action_row(db, action_id).steps[0]["result_id"]


def test_create_for_a_prospect_names_the_prospect_in_the_summary(db):
    w = make_world(db)
    title = unique_code("Prospect")
    steps, _ = propose_and_store(
        db, w,
        [(CREATE, {"title": title, "prospect_name": "Fake Showroom Sdn Bhd", "expected_close_date": CLOSE})],
        seen=set(),
    )

    assert steps[0]["summary"] == f'Create opportunity "{title}" for Fake Showroom Sdn Bhd, close {CLOSE}'


def test_a_create_with_an_unseen_customer_id_is_invalid(db):
    from app.services.chatbot.agent import writes

    w = make_world(db)

    res, step = writes.propose_step(
        db, ctx_of(db, w), CREATE,
        {"title": unique_code("X"), "customer_id": w.mine.id, "expected_close_date": CLOSE},
        seen_ids=set(),
    )

    assert res.status == "invalid" and step is None


# ------------------------------------------------------------------ update


def test_update_names_the_stage_in_the_summary_and_moves_it_on_confirm(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    opp = make_opp(db, w)
    new, qualified = stage(db, "new"), stage(db, "qualified")
    steps, row = propose_and_store(
        db, w, [(UPDATE, {"opportunity_id": opp.id, "status_id": qualified.id})], seen={opp.id, qualified.id}
    )

    summary = steps[0]["summary"]
    assert f'Opportunity "{opp.title}":' in summary
    assert f"{new.label} -> {qualified.label}" in summary
    assert not UUID_RE.search(summary)
    assert str(opp_now(db, opp.id).status_id) == new.id  # the proposal wrote nothing

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "executed"
    after = opp_now(db, opp.id)
    assert str(after.status_id) == qualified.id and after.outcome == "open"
    assert any(a.auth_method == "agent" and str(a.user_id) == w.user_id for a in audit_rows(db, opp.id))


def test_lost_with_a_configured_reason_is_accepted(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    opp = make_opp(db, w)
    lost = stage(db, "lost")
    _, row = propose_and_store(
        db, w,
        [(UPDATE, {"opportunity_id": opp.id, "status_id": lost.id, "lost_reason": a_lost_reason(db)})],
        seen={opp.id, lost.id},
    )

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "executed"
    after = opp_now(db, opp.id)
    assert after.outcome == "lost" and after.lost_reason == a_lost_reason(db)


def test_lost_without_a_reason_fails_the_step_with_the_routes_message_and_changes_nothing(db):
    """AC11: the CRM's own rule refuses it and the reply says so."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    opp = make_opp(db, w)
    new, lost = stage(db, "new"), stage(db, "lost")
    _, row = propose_and_store(
        db, w, [(UPDATE, {"opportunity_id": opp.id, "status_id": lost.id})], seen={opp.id, lost.id}
    )

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "partial"
    assert [s["status"] for s in outcome.steps] == ["failed"]
    assert "A reason is required to mark this opportunity Lost." in (outcome.steps[0]["error"] or "")
    assert "A reason is required to mark this opportunity Lost." in outcome.reply_text
    after = opp_now(db, opp.id)
    assert str(after.status_id) == new.id and after.outcome == "open" and after.lost_reason is None


def test_an_own_scope_user_cannot_move_an_opportunity_onto_another_agents_customer(db):
    """The route's `_assert_still_theirs` stays authoritative; its message becomes the step error."""
    from app.services.chatbot.agent import actions

    w = make_world(db, slugs=OWN_ONLY)
    opp = make_opp(db, w)
    _, row = propose_and_store(
        db, w, [(UPDATE, {"opportunity_id": opp.id, "customer_id": w.theirs.id})], seen={opp.id, w.theirs.id}
    )

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "partial"
    assert outcome.steps[0]["status"] == "failed"
    assert "Pick one of your own customers or sales agents." in (outcome.steps[0]["error"] or "")
    assert str(opp_now(db, opp.id).customer_id) == w.mine.id


def test_an_own_scope_user_cannot_even_propose_a_change_to_another_agents_opportunity(db):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=OWN_ONLY)
    foreign = make_opp(db, w, customer=w.theirs, agent=w.other)
    own = make_opp(db, w)
    qualified = stage(db, "qualified")
    seen = {foreign.id, own.id, qualified.id}

    control, _ = writes.propose_step(
        db, ctx_of(db, w), UPDATE, {"opportunity_id": own.id, "status_id": qualified.id}, seen_ids=seen
    )
    res, step = writes.propose_step(
        db, ctx_of(db, w), UPDATE, {"opportunity_id": foreign.id, "status_id": qualified.id}, seen_ids=seen
    )

    assert control.status == "proposed"
    assert res.status == "denied" and step is None


def test_an_opportunity_changed_since_the_proposal_is_rejected_and_nothing_is_written(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    opp = make_opp(db, w)
    qualified, won = stage(db, "qualified"), stage(db, "won")
    _, row = propose_and_store(
        db, w, [(UPDATE, {"opportunity_id": opp.id, "status_id": won.id})], seen={opp.id, won.id}
    )
    with company_scope(db, None):
        live = db.query(SalesOpportunity).filter(SalesOpportunity.id == opp.id).one()
        live.status_id = qualified.id
        db.commit()

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "rejected"
    assert "changed" in (outcome.steps[0]["error"] or "").lower()
    assert str(opp_now(db, opp.id).status_id) == qualified.id


# ------------------------------------------------------------------ reads


def test_the_list_read_under_own_scope_shows_only_the_users_own_opportunities(db):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=OWN_ONLY)
    mine = make_opp(db, w)
    foreign = make_opp(db, w, customer=w.theirs, agent=w.other)
    seen: set[str] = set()

    out = writes.run_user_read(db, ctx_of(db, w), LIST, {}, seen)

    assert out.status == "ok"
    body = json.dumps(out.data, default=str)
    assert mine.title in body and foreign.title not in body
    assert mine.id.lower() in seen and foreign.id.lower() not in seen


def test_the_list_read_for_a_full_view_user_shows_both_and_the_meta_read_adds_the_stage_ids(db):
    from app.services.chatbot.agent import writes

    w = make_world(db)
    mine = make_opp(db, w)
    foreign = make_opp(db, w, customer=w.theirs, agent=w.other)
    seen: set[str] = set()

    listed = writes.run_user_read(db, ctx_of(db, w), LIST, {}, seen)
    meta = writes.run_user_read(db, ctx_of(db, w), META, {}, seen)

    body = json.dumps(listed.data, default=str)
    assert mine.title in body and foreign.title in body
    assert meta.status == "ok"
    assert stage(db, "qualified").id.lower() in seen
    assert "Qualified" in json.dumps(meta.data, default=str) or stage(db, "qualified").label in json.dumps(meta.data, default=str)


# ------------------------------------------------------------------ one turn


def test_a_turn_reads_then_proposes_a_stage_move_and_writes_nothing(db):
    w = make_world(db)
    opp = make_opp(db, w)
    qualified = stage(db, "qualified")
    script = [
        round_of(tc(LIST, {}, "l1"), tc(META, {}, "m1")),
        round_of(tc(UPDATE, {"opportunity_id": opp.id, "status_id": qualified.id}, "u1")),
        answer_("I have prepared the stage change."),
    ]

    result, provider = run_turn(db, w, script, text_="move my opportunity to qualified")

    assert {LIST, META, UPDATE, CREATE} <= tool_names(provider)
    assert result.pending_action is not None
    assert PROPOSAL_HEAD in result.reply_text
    assert f"{stage(db, 'new').label} -> {qualified.label}" in result.reply_text
    assert str(opp_now(db, opp.id).status_id) == stage(db, "new").id
