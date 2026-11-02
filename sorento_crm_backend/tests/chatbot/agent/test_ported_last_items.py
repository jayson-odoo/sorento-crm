"""AGENTIC-UNIFY PR 4: the reviewers' last items (non-panel equals main, the verifier, the 403 log, the brand set).

Real role rows on the blank Postgres schema; the only fakes are the route's answer and the Jev call.
"""
from __future__ import annotations

import json
import logging
import uuid

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.user import User
from app.services.chatbot import principal as staff_principal
from app.services.chatbot import router
from app.services.chatbot.agent import loop as agent_loop
from app.services.chatbot.agent import tools as agent_tools
from app.services.company_scope import register_company_scope_listeners
from tests.chatbot.agent._ported_reads_support import AC1, catalog, panel_ctx, panel_turn, slugs_for
from tests.chatbot.agent._seed import all_agent_slugs, seed_agent_contact, seed_user
from tests.chatbot.agent.test_agent_writes import answer_, round_of, tc
from tests.chatbot.agent.test_agent_writes_round1 import Prov
from tests.chatbot.agent.test_router import (  # noqa: F401  (fixtures by name)
    _fresh_prompt_cache,
    db,
    jev,
    route,
    set_jev_key,
)
from tests.chatbot.agent.test_router_tool_labels import publish_criteria  # noqa: F401


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


# ------------------------------------------------------------------ 5: a console turn never runs the ported part


def _spy_reveal(monkeypatch, *, boom: bool):
    from app.services import contact_field_reveal_service as svc

    calls: list = []

    def spy(db, user_id):
        calls.append(user_id)
        if boom:
            raise RuntimeError("reveal lookup failed")
        return []

    monkeypatch.setattr(svc, "staff_reveal_keys", spy)
    return calls


def test_off_the_panel_agent_tool_labels_does_not_call_staff_reveal_keys(db, monkeypatch):
    user_id = seed_user(db, contact_pk=None, slugs=all_agent_slugs())
    calls = _spy_reveal(monkeypatch, boom=False)
    labels = router.agent_tool_labels(db, db.get(User, user_id))
    assert calls == [], "the staff reveal lookup ran on a turn that is not a panel turn"
    assert labels, "the old labels are still sent"


def test_a_failure_in_the_ported_part_cannot_fail_a_console_turn(db, jev, monkeypatch):
    contact = seed_agent_contact(db, slugs=all_agent_slugs())
    set_jev_key(db)
    publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
    _spy_reveal(monkeypatch, boom=True)
    router.agent_tool_labels(db, db.get(User, contact["user_id"]))
    decision = route(db, contact["respond_id"])
    assert decision.side == "agent", (decision.side, decision.reason)
    assert len(jev.calls) == 1


# ------------------------------------------------------------------ 6: the verifier and the plain empty reads


def _entry(name, status, args):
    return {"f1": {"name": name, "status": status, "args": args, "data": None}}


def _claim(what="closed complaints"):
    return {"text": "None.", "not_found": [{"what": what, "call_id": "f1"}]}


PLAIN_READS = [
    ("crm_complaints_list", {"status": "closed"}),
    ("crm_complaint_analytics", {"group_by": "status"}),
    ("crm_projects_list", {"status_key": "lost"}),
    ("crm_order_analytics", {"metric": "count"}),
    ("crm_sla_conversation_tracking_list", {"status": "breached"}),
]


@pytest.mark.parametrize("name,args", PLAIN_READS, ids=[r[0] for r in PLAIN_READS])
def test_an_empty_plain_read_with_no_ids_backs_a_not_found_claim(name, args):
    _, bad = agent_loop.verify_answer(_claim(), _entry(name, "empty", args), "any closed complaints")
    assert bad == [], f"an empty {name} did not back the claim: {bad}"


@pytest.mark.parametrize("name,args", PLAIN_READS, ids=[r[0] for r in PLAIN_READS])
def test_an_ok_result_or_a_call_never_made_does_not_back_a_not_found_claim(name, args):
    _, ok_bad = agent_loop.verify_answer(_claim(), _entry(name, "ok", args), "any")
    assert ok_bad == ["closed complaints"]
    _, none_bad = agent_loop.verify_answer(
        {"text": "None.", "not_found": [{"what": "closed complaints", "call_id": "never"}]}, {}, "any"
    )
    assert none_bad == ["closed complaints"]


def test_a_non_ported_tool_is_verified_exactly_as_before():
    """An empty stock read with no ids backs nothing; one whose ids came from a found match still does."""
    _, bad = agent_loop.verify_answer(
        _claim("stock"), _entry("crm_inventory_stock_balance_list", "empty", {"query": "x"}), "stock"
    )
    assert bad == ["stock"]
    pid = str(uuid.uuid4())
    ledger = {
        "r1": {"name": agent_tools.RESOLVE, "status": "ok", "args": {}, "data": {
            "results": [{"term": "SKU1", "status": "found", "matches": [{"id": pid}]}]}},
        "f1": {"name": "crm_inventory_stock_balance_list", "status": "empty", "args": {"product_ids": [pid]}, "data": None},
    }
    _, bad2 = agent_loop.verify_answer(_claim("stock for SKU1"), ledger, "stock")
    assert bad2 == []


# ------------------------------------------------------------------ 7: a console prompt equals main's, with literals


MAIN_LEFT_OUT = (
    "sales and outstanding figures; stock on hand; incoming stock; incoming shipments; goods received; "
    "last purchase cost; purchase orders placed; last receipt; orders by product; finding names and codes; "
    "finding products; searching company documents; reading the CRM user guides; your customer asks; "
    "recent changes; your sales opportunities; opportunity stages; finding dealer contacts; "
    "purchase requests and sponsorship forms; your ideas; change a customer ask; create an opportunity; "
    "change an opportunity; change a dealer contact; approve or reject a purchase request; "
    "take back a purchase request action; record a suggestion or wish for what the system should have or do, "
    "an idea or a feature request; change one of your ideas"
)


def test_a_non_panel_prompt_names_exactly_main_s_labels_written_out(db):
    text = agent_loop._system_prompt(db, "ZZT User", tool_names=())
    assert (
        f"Outside this user's or this contact's access: {MAIN_LEFT_OUT}. When asked about these" in text
    ), "the outside-access line is not what main sends"


# ------------------------------------------------------------------ 8: what the model is told after a confirm


def test_a_non_panel_idea_confirm_says_exactly_what_main_says(db, monkeypatch):
    from app.services.chatbot.agent import actions

    outcome = actions.ActionOutcome(
        action_id=str(uuid.uuid4()), status="executed", reply_text="Done. IDEA-0184 /ideas/x",
        steps=[{"summary": "Capture the idea", "status": "done", "error": None, "changes": [], "waiting": None}],
        notes=["IDEA-0184 /ideas/x"],
    )
    monkeypatch.setattr(actions, "confirm", lambda *a, **k: outcome)
    ctx = type("C", (), {"contact_respond_id": "ZZT-R", "operator_user_id": None})()
    action_id = str(uuid.uuid4())
    waiting = type("W", (), {"id": action_id})()
    out = agent_loop._decide(db, ctx, agent_loop.CONFIRM_ACTION, {"action_id": action_id}, "t1", [], waiting=waiting)
    assert out.message == "The idea's number and link are added to your reply automatically. Do not write them.", (
        out.message
    )


# ------------------------------------------------------------------ 9: a route 403 is logged with its detail, not told


DETAIL = "ZZT-route-detail requires complaint_management.complaints.view"


def _refusing(shape):
    def call(name, args):
        if shape == "body":
            return {"status_code": 403, "detail": DETAIL}
        raise RuntimeError(f"{name} returned HTTP 403: {json.dumps({'detail': DETAIL})}")

    return call


@pytest.mark.parametrize("shape", ["body", "raised"])
def test_a_403_on_the_panel_is_logged_with_tool_user_and_detail_but_the_model_hears_none_of_them(
    db, caplog, shape
):
    name = "crm_complaints_list"
    slug = next(r[1] for r in AC1 if r[0] == name)
    user_id = seed_user(db, contact_pk=None, slugs=slugs_for(name, slug))
    ctx = panel_ctx(db, user_id)
    with caplog.at_level(logging.DEBUG):
        with panel_turn(user_id):
            out = agent_tools.dispatch(db, ctx, name, {}, call=_refusing(shape), catalog=catalog(), timeout=5.0)
    assert out.status == "denied", (out.status, out.message)
    lines = [r.getMessage() for r in caplog.records]
    assert any(name in m and user_id in m and "ZZT-route-detail" in m for m in lines), lines
    for token in (name, user_id, "ZZT-route-detail", "complaint_management"):
        assert token not in out.message, f"the model was told {token!r}: {out.message!r}"


# ------------------------------------------------------------------ 10: the brand set


def test_the_tools_denied_when_scoped_is_the_forecast_alone():
    from app.services import contact_brand_scope

    assert contact_brand_scope._TOOLS_DENIED_WHEN_SCOPED == frozenset({"crm_project_forecast"})


# ------------------------------------------------------------------ invisible characters are refused


from tests.chatbot.agent.test_ported_writes import (  # noqa: E402,F401  (fixtures by name, then helpers)
    CANCEL,
    CLOSE,
    CLOSE_SLUG,
    ORDERS_VIEW,
    TICKET,
    TICKET_SLUG,
    confirm_ticket,
    ctx_of as panel_ctx_of,
    grace,
    make_complaint,
    make_order,
    make_world as make_writes_world,
    no_llm,
    panel,
    propose,
    propose_and_store,
    respond_sends,
)

ZERO_WIDTH = "​"
TAG_CHAR = "\U000e0041"
INVISIBLE = [pytest.param(ZERO_WIDTH, id="zero_width_space"), pytest.param(TAG_CHAR, id="tag_character")]
ORDINARY = "Café 你好 \U0001F600 thanks"


def _refused(res, step):
    assert step is None and res.status == "invalid", (res.status, res.message)
    assert res.message.strip()


def _proposal(db, field):
    """(world, tool, args builder) for each of the four free-text fields."""
    if field == "note":
        w = make_writes_world(db, CLOSE_SLUG)
        row = make_complaint(db)
        w.seen = {row.id}
        return w, CLOSE, lambda text: {"complaint_id": row.id, "note": text}
    if field == "reason":
        w = make_writes_world(db, ORDERS_VIEW)
        row = make_order(db)
        return w, CANCEL, lambda text: {"order_number": row.order_number, "reason": text}
    w = make_writes_world(db, TICKET_SLUG)
    if field == "title":
        return w, TICKET, lambda text: {"title": text}
    return w, TICKET, lambda text: {"title": "ZZT screen", "description": text}


FIELDS_UNDER_TEST = ["note", "reason", "title", "description"]


@pytest.mark.parametrize("char", INVISIBLE)
@pytest.mark.parametrize("field", FIELDS_UNDER_TEST)
def test_a_format_character_in_free_text_is_refused_at_proposal(db, field, char):
    w, tool, build = _proposal(db, field)
    res, step = propose(db, w, tool, build(f"Please{char}close it"))
    _refused(res, step)


@pytest.mark.parametrize("field", FIELDS_UNDER_TEST)
def test_ordinary_text_with_accents_chinese_and_an_emoji_is_not_refused(db, field):
    w, tool, build = _proposal(db, field)
    res, step = propose(db, w, tool, build(ORDINARY))
    assert res.status == "proposed", (res.status, res.message)
    assert ORDINARY in step["summary"], step["summary"]


# ------------------------------------------------------------------ the line the model is told after a confirm


TICKET_LINE = "The ticket link is added to your reply automatically. Do not write it."
IDEA_LINE = "The idea's number and link are added to your reply automatically. Do not write them."


def _decide_on_panel(db, w, action, notes):
    with panel(db, w):
        return agent_loop._decide(
            db, panel_ctx_of(db, w), agent_loop.CONFIRM_ACTION, {"action_id": str(action.id)}, str(uuid.uuid4()), notes,
            waiting=action,
        )


def test_a_ticket_confirm_says_the_ticket_line_in_words(db, no_llm):
    w = make_writes_world(db, TICKET_SLUG)
    _, action = propose_and_store(db, w, TICKET, {"title": f"ZZT ticket {uuid.uuid4().hex[:8]}"})
    notes: list[str] = []
    out = _decide_on_panel(db, w, action, notes)
    assert notes, "the draft link is still put in the reply by code"
    assert out.message == TICKET_LINE, out.message


def test_a_ticket_plus_a_parked_complaint_close_says_the_ticket_line_not_the_idea_line(
    db, no_llm, grace, respond_sends
):
    from app.services.chatbot.agent import actions, writes

    grace(30)
    w = make_writes_world(db, TICKET_SLUG, CLOSE_SLUG)
    row = make_complaint(db)
    w.seen = {row.id}
    ctx = panel_ctx_of(db, w)
    steps = []
    with panel(db, w):
        for name, args in (
            (TICKET, {"title": f"ZZT ticket {uuid.uuid4().hex[:8]}"}),
            (CLOSE, {"complaint_id": row.id}),
        ):
            res, step = writes.propose_step(db, ctx, name, args, seen_ids={row.id.lower()})
            assert res.status == "proposed", (name, res.status, res.message)
            steps.append(step)
    action = actions.store_proposal(
        db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=steps
    )
    notes: list[str] = []
    out = _decide_on_panel(db, w, action, notes)
    assert out.data["status"] == "executed", out.data
    assert out.message == TICKET_LINE, out.message
    assert "idea" not in out.message.lower()


def test_an_idea_confirm_through_the_real_path_says_main_s_exact_text(db, monkeypatch):
    from tests.chatbot.agent import test_agent_writes_ideas as ideas

    fake = _ideas_fake(monkeypatch, ideas)
    w = ideas.make_world(db)
    _, row = ideas.store(db, w, [(ideas.CREATE, ideas.FIELDS)])
    notes: list[str] = []
    out = agent_loop._decide(
        db, ideas.ctx_of(db, w), agent_loop.CONFIRM_ACTION, {"action_id": str(row.id)}, str(uuid.uuid4()), notes,
        waiting=row,
    )
    assert fake is not None
    assert notes, "the idea's number and link are put in the reply by code"
    assert out.message == IDEA_LINE, out.message


def _ideas_fake(monkeypatch, ideas):
    """The ideas suite's own ideation fake, installed the way its `ss` fixture does."""
    import httpx

    from app.config import settings
    from tests.chatbot.agent.test_agent_writes_ideas import CRM, configure_embed_settings

    configure_embed_settings(monkeypatch)
    monkeypatch.setattr(settings, "frontend_base_url", CRM)
    fake = ideas.FakeSS().install(monkeypatch)
    ids = iter(str(uuid.uuid4()) for _ in range(20))
    numbers = iter(f"IDEA-{n:04d}" for n in range(184, 300))
    fake.route("POST", ideas.SIMILAR_PATH, json_body={"matches": []})
    fake.routes[("POST", ideas.CREATE_PATH)] = lambda request: httpx.Response(
        200,
        json={"idea_id": next(ids), "idea_number": next(numbers), "status": "captured", "title": "x"},
        request=request,
    )
    fake.route("GET", "/embed/ideas", json_body=[])
    return fake


# ------------------------------------------------------------------ not_found only for an unfiltered empty read


def _ledger_with_found_id(name, args, pid):
    return {
        "r1": {"name": agent_tools.RESOLVE, "status": "ok", "args": {}, "data": {
            "results": [{"term": "ACME", "status": "found", "matches": [{"id": pid}]}]}},
        "f1": {"name": name, "status": "empty", "args": args, "data": None},
    }


@pytest.mark.parametrize("name,args", PLAIN_READS[:3], ids=[r[0] for r in PLAIN_READS[:3]])
def test_an_empty_read_with_an_id_argument_does_not_back_a_not_found_claim(name, args):
    pid = str(uuid.uuid4())
    # An id this turn resolved cleanly: the empty read is a real "none" for it.
    ledger = _ledger_with_found_id(name, {**args, "customer_ids": [pid]}, pid)
    _, bad = agent_loop.verify_answer(_claim("complaints for Acme"), ledger, "complaints for Acme")
    assert bad == [], "an empty read for an id resolved cleanly is a real none"
    # An id the turn never resolved (or only found ambiguous) backs nothing.
    other = str(uuid.uuid4())
    ledger = _ledger_with_found_id(name, {**args, "customer_ids": [other]}, pid)
    _, bad = agent_loop.verify_answer(_claim("complaints for Acme"), ledger, "complaints for Acme")
    assert bad == ["complaints for Acme"], "an empty read narrowed by an id the turn did not resolve backs nothing"
    ambiguous = {
        "r1": {"name": agent_tools.RESOLVE, "status": "ok", "args": {}, "data": {
            "results": [{"term": "ACME", "status": "ambiguous", "matches": [{"id": pid}, {"id": other}]}]}},
        "f1": {"name": name, "status": "empty", "args": {**args, "customer_ids": [pid]}, "data": None},
    }
    _, bad = agent_loop.verify_answer(_claim("complaints for Acme"), ambiguous, "complaints for Acme")
    assert bad == ["complaints for Acme"], "an ambiguous resolve must stay unbacked"


@pytest.mark.parametrize("name,args", PLAIN_READS[:3], ids=[r[0] for r in PLAIN_READS[:3]])
def test_an_empty_read_with_assigned_to_set_does_not_back_a_not_found_claim(name, args):
    ledger = _entry(name, "empty", {**args, "assigned_to": "someone"})
    _, bad = agent_loop.verify_answer(_claim("complaints for someone"), ledger, "complaints for someone")
    assert bad == ["complaints for someone"]


@pytest.mark.parametrize("name,args", PLAIN_READS[:3], ids=[r[0] for r in PLAIN_READS[:3]])
def test_an_empty_read_with_neither_still_backs_it(name, args):
    _, bad = agent_loop.verify_answer(_claim(), _entry(name, "empty", args), "any closed complaints")
    assert bad == []
