"""AGENTIC-P3 slice 1 (PLAN-agentic-p3-writes-30oct.md): the write foundation plus W1 customer asks.

Red tests, written before any implementation exists. They import the plan's "Build contract,
slice 1" names (`agent.writes`, `agent.actions`, `models.chatbot_agent.AgentAction`) lazily inside
helpers and tests, so a missing module fails each test on its own instead of the whole file at
collection.

Postgres only, through the blank schema. Every test seeds its own chain: a sales agent linked to
the agent contact's user, a customer assigned to that agent, a dealer contact and the asks. No
live model and no MCP: a scripted provider returns `ChatResult` objects (an item may also be a
callable that reads the messages sent so far).

Test numbers in the docstrings are the plan's test list (item numbers 1 to 16).
"""
from __future__ import annotations

import copy
import dataclasses
import json
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor, get_actor
from app.models.audit import AuditLog
from app.models.base import company_scope, get_company_scope
from app.models.company import UserCompany
from app.models.stock_ask import StockAsk
from app.models.user import SystemSetting, UserPermission, UserRoleAssignment, UserRolePermission
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from app.services.llm_provider import ChatResult
from app.services.user_service import invalidate_rbac_cache
from tests._ask_todo_seed import NOW as SEED_NOW
from tests._ask_todo_seed import SORENTO
from tests._ask_todo_seed import agent as seed_sales_agent
from tests._ask_todo_seed import ask as seed_ask
from tests._ask_todo_seed import contact as seed_plain_contact
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user

VIEW = "sales.customer_asks.view"
EDIT = "sales.customer_asks.edit"
UPDATE = "crm_customer_ask_update"
LIST = "crm_customer_asks_list"
CONFIRM_ACTION = "confirm_action"
CANCEL_ACTION = "cancel_action"
NOTE = "Called the customer"
PROPOSAL_HEAD = "I will make these changes when you confirm:"
PROPOSAL_TAIL = "Reply yes to go ahead, or tell me what to change."
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


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


# ------------------------------------------------------------------ seeding


@dataclass
class World:
    contact: dict
    user_id: str
    asks: list
    customer: object

    @property
    def respond_id(self) -> str:
        return self.contact["respond_id"]


def make_world(db, *, slugs=(VIEW, EDIT), n_asks=1, mine=True, grant_company=True) -> World:
    """A switched-on agent contact, its linked active user holding `slugs`, the sales agent that
    user is, one customer and `n_asks` open asks. `mine=False` hangs the customer on ANOTHER
    sales agent, so the asks are out of the user's scope. The user holds a Sorento company grant,
    the contact holds none: the user's company scope sees the asks, the contact's does not."""
    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"], slugs=slugs)
    if grant_company:
        db.add(UserCompany(user_id=user_id, company_id=SORENTO))
        db.flush()
    me = seed_sales_agent(db, contact["pk"], "ME")
    other = seed_sales_agent(db, seed_plain_contact(db, "Other agent"), "OT")
    cust = seed_customer(db, unique_code("Cust"), me if mine else other)
    dealer = seed_plain_contact(db, "Dealer")
    rows = [
        seed_ask(db, cust, dealer, unique_code("SRT"), created_at=SEED_NOW - timedelta(hours=i + 1))
        for i in range(n_asks)
    ]
    db.commit()
    return World(contact=contact, user_id=user_id, asks=rows, customer=cust)


def ask_now(db, ask_id: str) -> StockAsk:
    db.expire_all()
    with company_scope(db, None):
        return db.query(StockAsk).filter(StockAsk.id == str(ask_id)).one()


def action_rows(db, respond_id: str) -> list:
    from app.models.chatbot_agent import AgentAction

    db.expire_all()
    return (
        db.query(AgentAction)
        .filter(AgentAction.contact_respond_id == respond_id)
        .order_by(AgentAction.created_at, AgentAction.id)
        .all()
    )


def action_row(db, action_id: str):
    from app.models.chatbot_agent import AgentAction

    db.expire_all()
    return db.get(AgentAction, str(action_id))


def audit_updates(db, ask_id: str) -> list:
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == str(ask_id), AuditLog.action == "UPDATE")
        .order_by(AuditLog.changed_at, AuditLog.id)
        .all()
    )


def revoke(db, user_id: str, slug: str) -> None:
    perm = db.query(UserPermission).filter(UserPermission.slug == slug).one()
    roles = [a.role_id for a in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id)]
    db.query(UserRolePermission).filter(
        UserRolePermission.role_id.in_(roles), UserRolePermission.permission_id == perm.id
    ).delete(synchronize_session=False)
    db.commit()
    invalidate_rbac_cache(user_id)


# ------------------------------------------------------------------ scripted model


def tc(name, args, cid):
    return {"id": cid, "name": name, "arguments": args}


def round_of(*calls):
    return ChatResult(
        content="", prompt_tokens=100, completion_tokens=10, total_tokens=110, cached_tokens=0,
        tool_calls=list(calls),
    )


def answer_(text_, cid="ans-1"):
    return round_of(
        tc("answer", {"text": text_, "figures": [], "not_found": [], "not_checked": []}, cid)
    )


class Provider:
    """Returns scripted `ChatResult`s; an item that is callable receives the messages of this call."""

    def __init__(self, script):
        self.script = list(script)
        self.seen: list[dict] = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        self.seen.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        item = self.script.pop(0)
        return item(self.seen[-1]["messages"]) if callable(item) else item


def _no_mcp(name, args):
    raise AssertionError(f"the write tests never reach the MCP server (called {name})")


def tool_names(provider: Provider, call_index: int = 0) -> set[str]:
    return {t["function"]["name"] for t in (provider.seen[call_index]["tools"] or [])}


def run_turn(db, world: World, script, text_="please update my customer asks"):
    from app.services.chatbot.agent.loop import run_agent_turn

    provider = Provider(script)
    result = run_agent_turn(
        db, contact_respond_id=world.respond_id, text=text_, provider=provider, mcp_call=_no_mcp, catalog={}
    )
    return result, provider


def update_call(ask, cid, *, state="done", note=NOTE):
    return tc(UPDATE, {"ask_id": str(ask.id), "state": state, "note": note}, cid)


def proposal_script(asks, *, state="done", note=NOTE, final="I have prepared the changes."):
    """List the user's asks (so the ids are seen), then update each ask (4 calls per round, the
    loop's per-round cap), then answer."""
    script = [round_of(tc(LIST, {}, "list-1"))]
    for start in range(0, len(asks), 4):
        group = asks[start:start + 4]
        script.append(round_of(*[update_call(a, f"u{start + i}", state=state, note=note) for i, a in enumerate(group)]))
    script.append(answer_(final))
    return script


def propose(db, world: World, asks=None, **kw):
    """Run one proposing turn. Returns (turn result, the stored agent_actions row)."""
    result, _ = run_turn(db, world, proposal_script(asks if asks is not None else world.asks, **kw))
    assert result.pending_action is not None, f"no pending_action; reply was {result.reply_text!r}"
    row = action_row(db, result.pending_action["id"])
    assert row is not None
    return result, row


def set_budgets(db, **cols):
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    for k, v in cols.items():
        setattr(row, k, v)
    db.flush()


def _find_key(node, key):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            found = _find_key(v, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_key(v, key)
            if found is not None:
                return found
    return None


def action_id_from(messages) -> str:
    """The action id a previous tool result of this turn carried (a random id when none did)."""
    for m in reversed(messages):
        if m.get("role") == "tool":
            try:
                body = json.loads(m["content"])
            except (TypeError, ValueError):
                continue
            found = _find_key(body, "action_id")
            if found:
                return str(found)
    return str(uuid.uuid4())


# ------------------------------------------------------------------ 1. exposure


def test_01_the_registry_holds_exactly_the_registered_writes_and_the_in_process_reads():
    """AC12: nothing outside the registered write tools exists."""
    from app.services.chatbot.agent import writes

    assert set(writes.WRITES) == {
        UPDATE, "crm_opportunity_create", "crm_opportunity_update", "crm_contact_access_update",
        "crm_purchase_request_decide",
    }
    assert {LIST, "crm_agent_actions_recent"} <= set(writes.USER_READS)
    definition = writes.WRITES[UPDATE]
    assert definition.name == UPDATE
    assert definition.user_permission == EDIT
    assert definition.record_key == "ask_id"


def test_01_a_write_tool_is_exposed_only_when_the_linked_user_holds_its_slug(db):
    """AC03: absent for a user without sales.customer_asks.edit, present for one with it."""
    from app.services.chatbot.agent import writes
    from app.services.chatbot.agent.access import build_context

    can = make_world(db, slugs=(VIEW, EDIT))
    cannot = make_world(db, slugs=(VIEW,))

    assert [w.name for w in writes.permitted_writes(db, build_context(db, can.respond_id))] == [UPDATE]
    assert writes.permitted_writes(db, build_context(db, cannot.respond_id)) == []

    _, with_edit = run_turn(db, can, [answer_("Hello.")])
    _, without_edit = run_turn(db, cannot, [answer_("Hello.")])
    assert UPDATE in tool_names(with_edit) and LIST in tool_names(with_edit)
    assert UPDATE not in tool_names(without_edit)


def test_01_a_direct_call_to_a_write_the_user_may_not_make_is_denied_and_proposes_nothing(db):
    """AC03: the slug is checked again at call time, so a call the model was never offered still fails."""
    w = make_world(db, slugs=(VIEW,))

    result, _ = run_turn(db, w, proposal_script(w.asks))

    calls = [c for c in result.tool_calls if c["name"] == UPDATE]
    assert [c["status"] for c in calls] == ["denied"]
    assert action_rows(db, w.respond_id) == []
    assert result.pending_action is None
    assert ask_now(db, w.asks[0].id).state == "open"


# ------------------------------------------------------------------ 2. a write call writes nothing


def test_02_a_write_call_during_a_turn_writes_nothing_and_stores_one_proposal(db):
    """AC01: the ask is unchanged, one proposed action with one step, the reply ends with the block."""
    w = make_world(db)
    ask = w.asks[0]

    result, row = propose(db, w)

    after = ask_now(db, ask.id)
    assert after.state == "open" and after.note is None
    rows = action_rows(db, w.respond_id)
    assert len(rows) == 1 and str(rows[0].id) == str(row.id)
    assert row.status == "proposed"
    assert row.user_id == w.user_id
    assert len(row.steps) == 1
    step = row.steps[0]
    assert step["tool"] == UPDATE
    assert step["args"]["ask_id"] == str(ask.id)
    assert step["args"]["state"] == "done" and step["args"]["note"] == NOTE
    summary = step["summary"]
    assert summary and not UUID_RE.search(summary)
    assert ask.product_code in summary or w.customer.customer_name in summary

    assert PROPOSAL_HEAD in result.reply_text
    assert summary in result.reply_text
    assert result.reply_text.rstrip().endswith(PROPOSAL_TAIL)
    pending = result.pending_action
    assert pending["id"] == str(row.id)
    assert len(pending["lines"]) == 1 and summary in pending["lines"][0]
    assert pending["expires_at"]


# ------------------------------------------------------------------ 3. ids rule


@pytest.mark.parametrize("real_id", [True, False], ids=["real ask never listed", "invented id"])
def test_03_an_ask_id_not_seen_in_this_turns_results_is_invalid_and_adds_no_step(db, real_id):
    w = make_world(db)
    target = str(w.asks[0].id) if real_id else str(uuid.uuid4())
    script = [
        round_of(tc(UPDATE, {"ask_id": target, "state": "done", "note": NOTE}, "u0")),
        answer_("I could not prepare that change."),
    ]

    result, _ = run_turn(db, w, script)

    assert [c["status"] for c in result.tool_calls if c["name"] == UPDATE] == ["invalid"]
    assert action_rows(db, w.respond_id) == []
    assert result.pending_action is None
    assert PROPOSAL_HEAD not in result.reply_text
    assert ask_now(db, w.asks[0].id).state == "open"


# ------------------------------------------------------------------ 4. out of scope


def test_04_an_ask_of_another_salespersons_customer_is_denied_at_read_before(db):
    """AC04: even with its id marked seen, the route's own scope 404s read_before: denied, no step."""
    from app.services.chatbot.agent import writes
    from app.services.chatbot.agent.access import build_context

    w = make_world(db, mine=False)
    ctx = build_context(db, w.respond_id)
    ask_id = str(w.asks[0].id)

    res, step = writes.propose_step(
        db, ctx, UPDATE, {"ask_id": ask_id, "state": "done", "note": NOTE}, seen_ids={ask_id}
    )

    assert res.status == "denied"
    assert step is None
    assert action_rows(db, w.respond_id) == []


def test_04_in_a_turn_the_other_agents_ask_never_becomes_a_proposal(db):
    w = make_world(db, mine=False)

    result, _ = run_turn(db, w, proposal_script(w.asks))

    assert [c["status"] for c in result.tool_calls if c["name"] == UPDATE] != ["proposed"]
    assert action_rows(db, w.respond_id) == []
    assert result.pending_action is None
    assert ask_now(db, w.asks[0].id).state == "open"


# ------------------------------------------------------------------ 5. console confirm executes


def test_05_console_confirm_executes_the_write_as_the_linked_user(db):
    """AC02: state done, note saved, action executed, step done with result_id, audit names the user."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    ask = w.asks[0]
    _, row = propose(db, w)

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.action_id == str(row.id)
    assert outcome.status == "executed"
    assert [s["status"] for s in outcome.steps] == ["done"]
    assert row.steps[0]["summary"] in outcome.reply_text

    after = ask_now(db, ask.id)
    assert after.state == "done" and after.note == NOTE
    assert str(after.done_by_user_id) == w.user_id

    stored = action_row(db, row.id)
    assert stored.status == "executed"
    assert stored.via == "console"
    assert stored.decided_at is not None and stored.finished_at is not None
    assert stored.steps[0]["status"] == "done"
    assert stored.steps[0]["result_id"] == str(ask.id)

    audits = audit_updates(db, ask.id)
    assert audits, "the update left no audit row"
    mine = [a for a in audits if a.auth_method == "agent"]
    assert mine, f"no audit row with auth_method agent: {[(a.actor_type, a.auth_method) for a in audits]}"
    row_ = mine[-1]
    assert row_.actor_type == "user"
    assert str(row_.user_id) == w.user_id and str(row_.real_user_id) == w.user_id
    assert str(row_.contact_id) == w.contact["pk"]
    assert UPDATE in (row_.description or "")
    assert not [a for a in audits if a.actor_type == "integration"]


# ------------------------------------------------------------------ 6. changed since proposal


@pytest.mark.parametrize("field", ["note", "state"])
def test_06_a_record_changed_on_screen_since_the_proposal_is_rejected_and_nothing_is_written(db, field):
    """AC05: rejected naming what changed; the on-screen edit stays and no step was applied."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    ask = w.asks[0]
    _, row = propose(db, w)
    with company_scope(db, None):
        live = db.query(StockAsk).filter(StockAsk.id == str(ask.id)).one()
        if field == "note":
            live.note = "edited on screen"
        else:
            live.state = "done"
        db.commit()

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "rejected"
    error = (outcome.steps[0].get("error") or "").lower()
    assert error and (field in error or "changed" in error)
    after = ask_now(db, ask.id)
    if field == "note":
        assert after.note == "edited on screen" and after.state == "open"
    else:
        assert after.state == "done" and after.note is None
    assert after.done_by_user_id is None
    stored = action_row(db, row.id)
    assert stored.status == "rejected"
    assert stored.steps[0]["status"] != "done"


# ------------------------------------------------------------------ 7. slug removed


def test_07_a_slug_removed_between_proposal_and_confirm_rejects_and_writes_nothing(db):
    """AC07."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    _, row = propose(db, w)
    revoke(db, w.user_id, EDIT)

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "rejected"
    assert outcome.steps[0].get("error")
    after = ask_now(db, w.asks[0].id)
    assert after.state == "open" and after.note is None
    assert action_row(db, row.id).status == "rejected"


# ------------------------------------------------------------------ 8. expiry


def test_08_a_proposal_older_than_ten_minutes_is_refused_as_expired(db):
    """AC06."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    _, row = propose(db, w)

    with pytest.raises(actions.ActionRefused) as exc:
        actions.confirm(
            db, w.respond_id, str(row.id), via="console",
            now=row.created_at + timedelta(minutes=actions.ACTION_TTL_MINUTES + 1),
        )

    assert exc.value.reason == "expired"
    assert ask_now(db, w.asks[0].id).state == "open"


def test_08_a_proposal_inside_the_window_still_confirms(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    _, row = propose(db, w)

    outcome = actions.confirm(
        db, w.respond_id, str(row.id), via="console",
        now=row.created_at + timedelta(minutes=actions.ACTION_TTL_MINUTES - 1),
    )

    assert outcome.status == "executed"
    assert ask_now(db, w.asks[0].id).state == "done"


def test_08_the_ttl_is_ten_minutes_and_the_cap_is_twenty():
    from app.services.chatbot.agent import actions

    assert actions.ACTION_TTL_MINUTES == 10
    assert actions.MAX_STEPS == 20


# ------------------------------------------------------------------ 9. not newest


def test_09_a_second_proposal_expires_the_first_and_confirming_the_first_is_refused(db):
    """AC06."""
    from app.services.chatbot.agent import actions

    w = make_world(db, n_asks=2)
    _, first = propose(db, w, asks=[w.asks[0]])
    _, second = propose(db, w, asks=[w.asks[1]])

    assert action_row(db, first.id).status == "expired"
    assert action_row(db, second.id).status == "proposed"
    assert str(actions.pending_action(db, w.respond_id).id) == str(second.id)

    with pytest.raises(actions.ActionRefused) as exc:
        actions.confirm(db, w.respond_id, str(first.id), via="console")

    assert exc.value.reason == "not_proposed"
    assert ask_now(db, w.asks[0].id).state == "open"
    assert ask_now(db, w.asks[1].id).state == "open"


# ------------------------------------------------------------------ 10. double confirm


def test_10_a_second_confirm_is_refused_and_the_write_ran_once(db):
    """AC06."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    ask = w.asks[0]
    _, row = propose(db, w)

    first = actions.confirm(db, w.respond_id, str(row.id), via="console")
    updates_after_first = len(audit_updates(db, ask.id))
    with pytest.raises(actions.ActionRefused) as exc:
        actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert first.status == "executed"
    assert exc.value.reason == "not_proposed"
    assert len(audit_updates(db, ask.id)) == updates_after_first
    assert action_row(db, row.id).status == "executed"


# ------------------------------------------------------------------ 11. cancel


def test_11_cancel_writes_nothing_and_a_later_confirm_is_refused(db):
    """AC06."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    ask = w.asks[0]
    _, row = propose(db, w)

    outcome = actions.cancel(db, w.respond_id, str(row.id))

    assert outcome.status == "cancelled"
    assert outcome.action_id == str(row.id)
    assert action_row(db, row.id).status == "cancelled"
    assert ask_now(db, ask.id).state == "open"
    with pytest.raises(actions.ActionRefused) as exc:
        actions.confirm(db, w.respond_id, str(row.id), via="console")
    assert exc.value.reason == "not_proposed"
    assert ask_now(db, ask.id).state == "open" and ask_now(db, ask.id).note is None


def test_11_pending_action_is_none_once_cancelled(db):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    _, row = propose(db, w)
    assert actions.pending_action(db, w.respond_id) is not None

    actions.cancel(db, w.respond_id, str(row.id))

    assert actions.pending_action(db, w.respond_id) is None


# ------------------------------------------------------------------ 12. switch off


def test_12_the_agent_switch_turned_off_before_confirm_refuses_with_entry_refused(db):
    """AC07."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    _, row = propose(db, w)
    db.execute(
        text("UPDATE respond_contacts SET chatbot_agent_enabled = false WHERE id = :id"),
        {"id": w.contact["pk"]},
    )
    db.commit()

    with pytest.raises(actions.ActionRefused) as exc:
        actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert exc.value.reason == "entry_refused"
    assert ask_now(db, w.asks[0].id).state == "open"
    assert action_row(db, row.id).status == "proposed"


# ------------------------------------------------------------------ 13. chat confirm


def test_13_in_a_later_turn_the_model_confirms_through_confirm_action(db):
    """AC08: "yes go ahead" in the next message. The tools are offered only while an action is pending."""
    w = make_world(db)
    ask = w.asks[0]
    first_result, row = propose(db, w)
    _, quiet = run_turn(db, w, [answer_("Hello.")])  # an unrelated later turn leaves the proposal pending
    assert action_row(db, row.id).status == "proposed"
    assert {CONFIRM_ACTION, CANCEL_ACTION} <= tool_names(quiet)  # pending now, so both are offered

    result, _ = run_turn(
        db, w,
        [round_of(tc(CONFIRM_ACTION, {"action_id": str(row.id)}, "c1")), answer_("Done, the ask is updated.")],
        text_="yes go ahead",
    )

    after = ask_now(db, ask.id)
    assert after.state == "done" and after.note == NOTE
    stored = action_row(db, row.id)
    assert stored.status == "executed"
    assert stored.via == "chat"
    assert str(stored.confirm_turn_id) == result.turn_id
    assert str(stored.turn_id) == first_result.turn_id != result.turn_id
    assert [c["status"] for c in result.tool_calls if c["name"] == CONFIRM_ACTION][0] != "invalid"


def test_13_the_confirm_and_cancel_tools_are_not_offered_when_nothing_is_pending(db):
    w = make_world(db)

    _, provider = run_turn(db, w, [answer_("Hello.")])

    assert UPDATE in tool_names(provider)  # the write tools are there; the confirm pair is not
    assert CONFIRM_ACTION not in tool_names(provider) and CANCEL_ACTION not in tool_names(provider)


def test_13_confirming_an_unstored_proposal_in_its_own_turn_writes_nothing(db):
    """AC08: the model cannot confirm in the turn it proposed."""
    w = make_world(db)
    ask = w.asks[0]
    script = [
        round_of(tc(LIST, {}, "list-1")),
        round_of(update_call(ask, "u0")),
        lambda messages: round_of(tc(CONFIRM_ACTION, {"action_id": action_id_from(messages)}, "c1")),
        answer_("I have prepared the change."),
    ]

    result, _ = run_turn(db, w, script)

    confirms = [c for c in result.tool_calls if c["name"] == CONFIRM_ACTION]
    assert confirms and confirms[0]["status"] == "invalid"
    assert ask_now(db, ask.id).state == "open"
    rows = action_rows(db, w.respond_id)
    assert len(rows) == 1 and rows[0].status == "proposed"


def test_13_the_same_turn_rule_is_enforced_by_the_server_function_too(db):
    """Contract: confirm(via="chat", turn_id == the proposing turn) raises same_turn."""
    from app.services.chatbot.agent import actions

    w = make_world(db)
    first_result, row = propose(db, w)

    with pytest.raises(actions.ActionRefused) as exc:
        actions.confirm(db, w.respond_id, str(row.id), via="chat", turn_id=first_result.turn_id)

    assert exc.value.reason == "same_turn"
    assert ask_now(db, w.asks[0].id).state == "open"


# ------------------------------------------------------------------ 14. at most 20 changes


def test_14_the_twenty_first_write_call_in_one_turn_is_invalid(db):
    """AC09: at most 20 changes per confirmation."""
    w = make_world(db, n_asks=21)
    set_budgets(db, chatbot_agent_max_rounds=20)

    result, _ = run_turn(db, w, proposal_script(w.asks))

    statuses = [c["status"] for c in result.tool_calls if c["name"] == UPDATE]
    assert len(statuses) == 21
    assert statuses[-1] == "invalid"
    assert "invalid" not in statuses[:20]
    row = action_rows(db, w.respond_id)[0]
    assert len(row.steps) == 20
    assert {s["args"]["ask_id"] for s in row.steps} == {str(a.id) for a in w.asks[:20]}
    assert len(result.pending_action["lines"]) == 20


# ------------------------------------------------------------------ 15. partial


def test_15_a_step_that_fails_stops_the_run_earlier_steps_stay_done_later_ones_are_skipped(db, monkeypatch):
    """AC09: step 2 fails inside the route; step 1 done, step 3 skipped, status partial."""
    from app.services.chatbot.agent import actions, writes
    from app.services.error_handler import AppException

    w = make_world(db, n_asks=3)
    _, row = propose(db, w)
    assert len(row.steps) == 3

    original = writes.WRITES[UPDATE]
    calls = {"n": 0}

    def flaky(db_, user, args):
        calls["n"] += 1
        if calls["n"] == 2:
            raise AppException(status_code=400, message="boom from the route", code="BOOM")
        return original.execute(db_, user, args)

    monkeypatch.setitem(writes.WRITES, UPDATE, dataclasses.replace(original, execute=flaky))

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "partial"
    assert [s["status"] for s in outcome.steps] == ["done", "failed", "skipped"]
    assert "boom from the route" in (outcome.steps[1].get("error") or "")
    assert calls["n"] == 2
    ids = [s["args"]["ask_id"] for s in row.steps]
    states = {i: ask_now(db, i).state for i in ids}
    assert [states[i] for i in ids] == ["done", "open", "open"]
    stored = action_row(db, row.id)
    assert stored.status == "partial"
    assert [s["status"] for s in stored.steps] == ["done", "failed", "skipped"]


# ------------------------------------------------------------------ 16. company scope


def test_16_the_write_runs_under_the_users_company_scope_and_actor_and_restores_both(db, monkeypatch):
    """Plan section 1: run_as_user sets the USER's scope (not the contact's) and the agent actor."""
    from app.services.chatbot.agent import actions, writes

    w = make_world(db)
    _, row = propose(db, w)  # read_before already needs the user's scope: the contact holds no company
    original = writes.WRITES[UPDATE]
    seen: dict = {}

    def recorder(db_, user, args):
        seen["scope"] = get_company_scope(db_)
        seen["user_id"] = str(user["id"])
        seen["actor"] = get_actor(db_)
        return {"id": args["ask_id"], "after": {}}

    monkeypatch.setitem(writes.WRITES, UPDATE, dataclasses.replace(original, execute=recorder))

    outcome = actions.confirm(db, w.respond_id, str(row.id), via="console")

    assert outcome.status == "executed"
    assert seen["scope"] == frozenset({SORENTO})
    assert seen["user_id"] == w.user_id
    actor = seen["actor"]
    assert actor is not None
    assert actor.actor_type == "user"
    assert str(actor.user_id) == w.user_id and str(actor.real_user_id) == w.user_id
    assert actor.auth_method == "agent"
    assert str(actor.contact_id) == w.contact["pk"]
    assert actor.tool_name == UPDATE
    assert get_company_scope(db) != frozenset({SORENTO})
    assert get_actor(db) is None


def test_16_run_as_user_restores_the_scope_and_actor_even_when_the_function_raises(db):
    from app.services.chatbot.agent import writes
    from app.services.chatbot.agent.access import build_context

    w = make_world(db)
    ctx = build_context(db, w.respond_id)
    before_scope = get_company_scope(db)

    def boom(user):
        assert get_company_scope(db) == frozenset({SORENTO})
        assert str(user["id"]) == w.user_id
        raise RuntimeError("inside")

    with pytest.raises(RuntimeError, match="inside"):
        writes.run_as_user(db, ctx, boom)

    assert get_company_scope(db) == before_scope
    assert get_actor(db) is None
