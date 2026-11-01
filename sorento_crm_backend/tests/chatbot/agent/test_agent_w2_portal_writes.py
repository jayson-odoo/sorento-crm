"""AGENTIC-WA-W2 slice 1: dealer writes on WhatsApp through the portal's own service (UAC AC-1 .. AC-19).

Red tests, written before `agent/portal_writes.py` exists. A contact principal (Agent switch on, no linked
active user) may list its own requests, add / remove a note on one, and send / withdraw a stock inquiry. Each
write is a proposal first and runs on the contact's next-turn "yes". The portal's gates are the permission
check (form switch, own row, required fields). Postgres only, blank schema; every test seeds its own chain.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user

LIST = "crm_my_requests_list"
NOTE_ADD = "crm_my_request_note_add"
NOTE_REMOVE = "crm_my_request_note_remove"
SI_CREATE = "crm_stock_inquiry_create"
SI_WITHDRAW = "crm_stock_inquiry_withdraw"
ALL_TOOLS = {LIST, NOTE_ADD, NOTE_REMOVE, SI_CREATE, SI_WITHDRAW}
SRT = "00000000-0000-0000-0000-000000000001"
SPACE = "zzt-space"


@pytest.fixture()
def db(monkeypatch):
    from app.services.chatbot.head import access as head_access

    # Every agent context of these tests lives in one space, as the portal rows they make.
    monkeypatch.setattr(head_access, "default_space_id", lambda _db: SPACE)
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _listeners():
    """Startup registers these in the app; a test registers them itself (idempotent)."""
    from app.audit_context import clear_actor
    from app.services.audit_service import register_audit_listeners
    from app.services.company_scope import register_company_scope_listeners

    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture(autouse=True)
def _no_outside_calls(monkeypatch):
    """Submits notify teams; nothing may leave the process in a test (no Respond, no email)."""
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)


def _dealer(db, **kw) -> dict:
    """A contact principal in SRT's scope. Returns {"pk", "respond_id"}."""
    contact = seed_contact(db, **kw)
    db.execute(
        text("INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) VALUES (:i, :c, :co)"),
        {"i": str(uuid.uuid4()), "c": contact["pk"], "co": SRT},
    )
    db.flush()
    return contact


def _product(db, code: str | None = None) -> str:
    from app.models.base import company_scope
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    code = code or unique_code("SRT")
    with company_scope(db, frozenset({SRT})):
        cat = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("C"), category_name="ZZT cat", search_synonyms=[])
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("U"), uom_name="ZZT uom")
        db.add_all([cat, uom])
        db.flush()
        db.add(Product(id=str(uuid.uuid4()), product_code=code, product_name=f"ZZT {code}", category_id=cat.id,
                       base_uom_id=uom.id, list_price=1, company_id=SRT))
        db.flush()
    return code


def _ctx(db, contact):
    from app.services.chatbot.agent.access import build_context

    return build_context(db, contact["respond_id"])


def _hide_form(db, contact_pk: str, kind: str = "stock_inquiry") -> None:
    from app.models.price_tag import ContactPortalFormOverride

    db.add(ContactPortalFormOverride(id=str(uuid.uuid4()), contact_id=contact_pk, form_type=kind, is_enabled=False))
    db.flush()


def _submitted_si(db, contact_pk: str, *, minutes_ago: int = 1, status: str = "pending_project_sales",
                  history: int = 1, **cols) -> str:
    """A submitted stock inquiry of the contact, with `history` revision rows, submitted `minutes_ago`."""
    from app.models.portal import PortalFormRevision
    from app.models.procurement import StockInquiry

    rid = str(uuid.uuid4())
    db.add(StockInquiry(
        id=rid, inquiry_number=unique_code("SI"), status=status, contact_id=contact_pk, space_id=SPACE,
        salesperson_contact_id=contact_pk, product_code="ZZT-CODE", quantity="4", **cols,
    ))
    db.flush()
    stamp = datetime.utcnow() - timedelta(minutes=minutes_ago)
    for n in range(1, history + 1):
        db.add(PortalFormRevision(
            id=str(uuid.uuid4()), source_entity_type="stock_inquiry", source_entity_id=rid, version_no=n,
            revision_no=0, kind="original" if n == 1 else "resubmission", created_at=stamp, submitted_at=stamp,
        ))
    db.flush()
    return rid


def _propose(db, ctx, name, args, seen=(), *, is_test=False):
    from app.services.chatbot.agent import writes

    return writes.propose_step(db, ctx, name, args, seen_ids=set(seen), loop_args={"_is_test": is_test})


def _store_and_confirm(db, ctx, step, *, operator: str | None = None):
    """Live: the dealer's own next turn. With `operator`: the console's Confirm button."""
    from app.services.chatbot.agent import actions

    action = actions.store_proposal(db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])
    if operator:
        return actions.confirm(db, ctx.contact_respond_id, str(action.id), via="console", operator_user_id=operator)
    return actions.confirm(db, ctx.contact_respond_id, str(action.id), via="chat", turn_id=str(uuid.uuid4()))


# ================================================================ AC-1 .. AC-5 exposure


def test_ac1_a_contact_is_offered_the_five_dealer_tools_and_still_no_staff_write(db):
    from app.services.chatbot.agent import portal_writes, writes

    ctx = _ctx(db, _dealer(db))

    assert ctx.principal == "contact"
    assert set(portal_writes.offered(db, ctx)) == ALL_TOOLS
    assert writes.permitted_writes(db, ctx) == []
    assert writes.permitted_user_reads(db, ctx) == []


def test_ac2_a_hidden_stock_inquiry_form_drops_the_two_stock_inquiry_tools(db):
    from app.services.chatbot.agent import portal_writes

    contact = _dealer(db)
    _hide_form(db, contact["pk"])

    assert set(portal_writes.offered(db, _ctx(db, contact))) == {LIST, NOTE_ADD, NOTE_REMOVE}


def test_ac2_the_gate_asks_no_user_permission(db, monkeypatch):
    from app.services.chatbot.agent import portal_writes, writes

    def boom(*a, **k):
        raise AssertionError("a contact's dealer tools must not consult a user slug")

    ctx = _ctx(db, _dealer(db))
    monkeypatch.setattr(writes, "_permitted", boom)
    assert set(portal_writes.offered(db, ctx)) == ALL_TOOLS


def test_ac3_an_ambiguous_contact_is_offered_no_dealer_tool(db):
    from app.services.chatbot.agent import portal_writes

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    db.execute(
        text("INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, chatbot_allowed, "
             "chatbot_agent_enabled) VALUES (:id, :cid, '+60019999', '{}'::jsonb, true, true)"),
        {"id": str(uuid.uuid4()), "cid": contact["respond_id"]},
    )
    db.flush()

    assert portal_writes.offered(db, ctx) == []


def test_ac4_a_linked_staff_contact_is_offered_no_dealer_tool_in_slice_1(db):
    from app.services.chatbot.agent import portal_writes

    contact = _dealer(db)
    seed_user(db, contact_pk=contact["pk"], slugs=())
    ctx = _ctx(db, contact)

    assert ctx.principal == "user"
    assert portal_writes.offered(db, ctx) == []


def test_ac5_the_router_labels_follow_what_the_contact_is_offered(db):
    from app.services.chatbot.agent.tools import TOOL_LABELS
    from app.services.chatbot.router import agent_tool_labels

    contact = _dealer(db)
    labels = agent_tool_labels(db, None, contact_respond_id=contact["respond_id"])
    assert TOOL_LABELS[SI_CREATE] in labels and TOOL_LABELS[NOTE_ADD] in labels

    _hide_form(db, contact["pk"])
    labels = agent_tool_labels(db, None, contact_respond_id=contact["respond_id"])
    assert TOOL_LABELS[SI_CREATE] not in labels
    assert TOOL_LABELS[NOTE_ADD] in labels


def test_ac5_every_dealer_tool_has_a_label():
    from app.services.chatbot.agent.tools import TOOL_LABELS

    assert ALL_TOOLS <= set(TOOL_LABELS)


# ================================================================ AC-6 .. AC-8 proposing


def test_ac6_an_unknown_product_code_is_refused_and_nothing_is_written(db):
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    out, step = _propose(db, _ctx(db, contact), SI_CREATE, {"product_code": "ZZT-NOPE", "quantity": "40"})

    assert step is None and out.status in ("invalid", "error", "denied")
    assert db.query(StockInquiry).filter(StockInquiry.contact_id == contact["pk"]).count() == 0


def test_ac6_quantity_is_required(db):
    contact = _dealer(db)
    out, step = _propose(db, _ctx(db, contact), SI_CREATE, {"product_code": _product(db)})

    assert step is None and out.status == "invalid"


def test_ac6_a_hidden_form_refuses_the_proposal(db):
    contact = _dealer(db)
    code = _product(db)
    _hide_form(db, contact["pk"])
    out, step = _propose(db, _ctx(db, contact), SI_CREATE, {"product_code": code, "quantity": "4"})

    assert step is None and out.status in ("denied", "error")


def test_ac7_a_valid_proposal_reads_in_words_and_writes_nothing(db):
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    code = _product(db)
    ctx = _ctx(db, contact)
    out, step = _propose(db, ctx, SI_CREATE, {
        "product_code": code.lower(), "quantity": "40", "delivery_date": "2026-12-15", "project_name": "ZZT Tower",
    })

    assert out.status == "proposed", out.message
    assert step["summary"] == (
        f"Send a stock inquiry to the project sales team: {code} (ZZT {code}), 40 pcs, needed by 15 Dec 2026, "
        "project ZZT Tower, requested by you."
    )
    assert db.query(StockInquiry).filter(StockInquiry.contact_id == contact["pk"]).count() == 0


def test_ac7_the_stored_action_has_no_user(db):
    from app.services.chatbot.agent import actions

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    _out, step = _propose(db, ctx, SI_CREATE, {"product_code": _product(db), "quantity": "4"})
    action = actions.store_proposal(db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])

    assert action.user_id == ""
    assert actions.pending_action(db, contact["respond_id"], user_id="").id == action.id


def test_ac8_a_note_on_another_contacts_request_is_refused(db):
    mine, theirs = _dealer(db), _dealer(db)
    rid = _submitted_si(db, theirs["pk"])

    out, step = _propose(db, _ctx(db, mine), NOTE_ADD, {"kind": "stock_inquiry", "submission_id": rid, "text": "hi"}, [rid])

    assert step is None and out.status != "proposed"


def test_ac8_a_note_on_a_draft_is_refused(db):
    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"], status="draft", portal_draft_at=datetime.utcnow())

    out, step = _propose(db, _ctx(db, contact), NOTE_ADD, {"kind": "stock_inquiry", "submission_id": rid, "text": "x"}, [rid])

    assert step is None and out.status != "proposed"


def test_ac8_a_note_needs_an_id_seen_this_turn(db):
    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])

    out, step = _propose(db, _ctx(db, contact), NOTE_ADD, {"kind": "stock_inquiry", "submission_id": rid, "text": "x"})

    assert step is None and out.status == "invalid"


def test_ac8_a_note_on_an_own_request_proposes_in_words(db):
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])
    number = db.get(StockInquiry, rid).inquiry_number

    out, step = _propose(db, _ctx(db, contact), NOTE_ADD,
                         {"kind": "stock_inquiry", "submission_id": rid, "text": "Customer only home Tuesday"}, [rid])

    assert out.status == "proposed", out.message
    assert step["summary"] == f'Add this note to your stock inquiry {number}: "Customer only home Tuesday"'


# ================================================================ AC-9 .. AC-13 confirming


def test_ac9_a_confirm_submits_the_inquiry_as_the_contact(db):
    from app.models.portal import PortalFormRevision
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    code = _product(db)
    ctx = _ctx(db, contact)
    _out, step = _propose(db, ctx, SI_CREATE, {"product_code": code, "quantity": "40", "delivery_date": "2026-12-15"})

    outcome = _store_and_confirm(db, ctx, step)

    assert outcome.status == "executed", outcome.reply_text
    row = db.query(StockInquiry).filter(StockInquiry.contact_id == contact["pk"]).one()
    assert (row.salesperson_contact_id, row.space_id, row.status) == (contact["pk"], SPACE, "pending_project_sales")
    assert row.product_code == code and str(row.quantity) == "40"
    assert row.inquiry_number and row.portal_draft_at is None
    assert db.query(PortalFormRevision).filter(PortalFormRevision.source_entity_id == row.id).count() == 1
    note = f"Stock inquiry {row.inquiry_number} is with the project sales team. Reply undo within 10 minutes to withdraw it."
    assert note in outcome.notes
    assert note in outcome.reply_text


def test_ac10_a_note_confirm_writes_one_comment_by_the_contact(db):
    from app.models.entity_conversation import EntityConversationMessage

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])
    ctx = _ctx(db, contact)
    _out, step = _propose(db, ctx, NOTE_ADD, {"kind": "stock_inquiry", "submission_id": rid, "text": "Tuesday only"}, [rid])

    outcome = _store_and_confirm(db, ctx, step)

    assert outcome.status == "executed", outcome.reply_text
    rows = db.query(EntityConversationMessage).filter(EntityConversationMessage.entity_id == rid).all()
    assert len(rows) == 1
    assert rows[0].author_contact_id == contact["pk"] and rows[0].author_user_id is None
    assert "Tuesday only" in rows[0].body_html


def test_ac11_the_audit_rows_name_the_contact_and_the_agent(db):
    from app.models.audit import AuditLog
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    _out, step = _propose(db, ctx, SI_CREATE, {"product_code": _product(db), "quantity": "4"})
    _store_and_confirm(db, ctx, step)

    row = db.query(StockInquiry).filter(StockInquiry.contact_id == contact["pk"]).one()
    audits = db.query(AuditLog).filter(AuditLog.entity_id == str(row.id)).all()
    assert audits
    assert all(a.contact_id == contact["pk"] and a.auth_method == "agent" for a in audits)
    assert all(a.actor_type == "contact" for a in audits)


def test_ac12_the_router_keeps_a_contacts_own_proposal_on_the_agent(db):
    from app.services.chatbot.agent import actions
    from app.services.chatbot.router import decide_route

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    _out, step = _propose(db, ctx, SI_CREATE, {"product_code": _product(db), "quantity": "4"})
    actions.store_proposal(db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])

    decision = decide_route(db, contact_respond_id=contact["respond_id"], text="yes", session_vars=None, has_media=False)

    assert (decision.side, decision.reason) == ("agent", "pending_action")


def _scripted(*results):
    class Provider:
        def __init__(self):
            self.calls = []

        def chat(self, messages, *, tools=None, **kw):
            self.calls.append({"messages": [dict(m) for m in messages], "tools": [t["function"]["name"] for t in tools or []]})
            return results[min(len(self.calls), len(results)) - 1]

    return Provider()


def _asks(*calls):
    from app.services.llm_provider import ChatResult

    return ChatResult(content="", prompt_tokens=10, completion_tokens=1, total_tokens=11, tool_calls=list(calls))


def _says(text_):
    return _asks({"id": "ans", "name": "answer", "arguments": {"text": text_, "figures": [], "not_found": [], "not_checked": []}})


def _forbidden(name, args):
    raise AssertionError(f"the MCP must not be reached for {name}")


def test_ac13_a_contact_with_no_own_proposal_naming_confirm_is_denied(db):
    from app.services.chatbot.agent.loop import run_agent_turn

    contact = _dealer(db)
    provider = _scripted(_asks({"id": "c1", "name": "confirm_action", "arguments": {"action_id": str(uuid.uuid4())}}),
                         _says("Done."))

    result = run_agent_turn(db, contact_respond_id=contact["respond_id"], text="yes", provider=provider,
                            mcp_call=_forbidden, catalog={}, is_test=False)

    assert {c["name"]: c["status"] for c in result.tool_calls}.get("confirm_action") == "denied"


def test_ac13_a_whole_whatsapp_exchange_proposes_then_confirms(db):
    from app.models.procurement import StockInquiry
    from app.services.chatbot.agent.loop import run_agent_turn

    contact = _dealer(db)
    code = _product(db)
    first = _scripted(
        _asks({"id": "p1", "name": SI_CREATE, "arguments": {"product_code": code, "quantity": "40"}}),
        _says("I will send this when you confirm."),
    )
    turn1 = run_agent_turn(db, contact_respond_id=contact["respond_id"], text=f"can get 40 pcs {code}?",
                           provider=first, mcp_call=_forbidden, catalog={}, is_test=False)
    assert SI_CREATE in first.calls[0]["tools"]
    assert turn1.pending_action is not None
    assert db.query(StockInquiry).filter(StockInquiry.contact_id == contact["pk"]).count() == 0

    second = _scripted(
        _asks({"id": "c1", "name": "confirm_action", "arguments": {"action_id": turn1.pending_action["id"]}}),
        _says("Sent."),
    )
    turn2 = run_agent_turn(db, contact_respond_id=contact["respond_id"], text="yes", provider=second,
                           mcp_call=_forbidden, catalog={}, is_test=False)

    assert "confirm_action" in second.calls[0]["tools"]
    row = db.query(StockInquiry).filter(StockInquiry.contact_id == contact["pk"]).one()
    assert row.inquiry_number in turn2.reply_text


# ================================================================ AC-14 .. AC-16 undo


def _note(db, rid: str, *, contact_pk: str | None = None, user_id: str | None = None) -> str:
    from app.models.entity_conversation import EntityConversationMessage
    from app.services.form_comment_service import FORM_COMMENT_SCOPE

    cid = str(uuid.uuid4())
    db.add(EntityConversationMessage(
        id=cid, entity_type="stock_inquiry", entity_id=rid, scope=FORM_COMMENT_SCOPE, body_html="<p>x</p>",
        author_contact_id=contact_pk, author_user_id=user_id,
    ))
    db.flush()
    return cid


def test_ac14_removing_an_own_note_deletes_it(db):
    from app.models.entity_conversation import EntityConversationMessage

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])
    cid = _note(db, rid, contact_pk=contact["pk"])
    ctx = _ctx(db, contact)
    out, step = _propose(db, ctx, NOTE_REMOVE, {"kind": "stock_inquiry", "submission_id": rid, "comment_id": cid}, [rid, cid])
    assert out.status == "proposed", out.message

    outcome = _store_and_confirm(db, ctx, step)

    assert outcome.status == "executed", outcome.reply_text
    assert db.get(EntityConversationMessage, cid) is None


def test_ac14_a_staff_note_is_refused(db):
    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])
    cid = _note(db, rid, user_id=seed_user(db, contact_pk=None, slugs=()))

    out, step = _propose(db, _ctx(db, contact), NOTE_REMOVE,
                         {"kind": "stock_inquiry", "submission_id": rid, "comment_id": cid}, [rid, cid])

    assert step is None and out.status != "proposed"


def test_ac15_a_fresh_untouched_inquiry_is_withdrawn_with_its_children(db):
    from app.models.notification import Notification
    from app.models.portal import PortalFormRevision
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"], minutes_ago=3)
    staff = seed_user(db, contact_pk=None, slugs=())
    db.add(Notification(id=str(uuid.uuid4()), user_id=staff, type="stock_inquiry", title="New Stock Inquiry created",
                        source_entity_type="stock_inquiry", source_entity_id=rid))
    db.flush()
    ctx = _ctx(db, contact)
    out, step = _propose(db, ctx, SI_WITHDRAW, {"submission_id": rid}, [rid])
    assert out.status == "proposed", out.message

    outcome = _store_and_confirm(db, ctx, step)

    assert outcome.status == "executed", outcome.reply_text
    assert db.get(StockInquiry, rid) is None
    assert db.query(PortalFormRevision).filter(PortalFormRevision.source_entity_id == rid).count() == 0
    assert db.query(Notification).filter(Notification.source_entity_id == rid).count() == 0


REFUSED = "It is with the team now, so I can't withdraw it. I can add a note to it instead."


@pytest.mark.parametrize(
    "setup",
    [
        {"minutes_ago": 11},
        {"history": 2},
        {"status": "responded"},
        {"purchasing_response": "ETA 3 weeks"},
        {"staff_note": True},
    ],
    ids=["after-10-minutes", "a-resubmission", "moved-on", "answered", "staff-commented"],
)
def test_ac16_a_touched_or_old_inquiry_is_refused_with_the_team_line(db, setup):
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    setup = dict(setup)
    staff_note = setup.pop("staff_note", False)
    rid = _submitted_si(db, contact["pk"], **setup)
    if staff_note:
        _note(db, rid, user_id=seed_user(db, contact_pk=None, slugs=()))

    out, step = _propose(db, _ctx(db, contact), SI_WITHDRAW, {"submission_id": rid}, [rid])

    assert step is None
    assert REFUSED in (out.message or "")
    assert db.get(StockInquiry, rid) is not None


def test_ac16_another_contacts_inquiry_is_not_found(db):
    mine, theirs = _dealer(db), _dealer(db)
    rid = _submitted_si(db, theirs["pk"])

    out, step = _propose(db, _ctx(db, mine), SI_WITHDRAW, {"submission_id": rid}, [rid])

    assert step is None and REFUSED not in (out.message or "")


def test_ac16_the_withdraw_rechecks_at_confirm(db):
    """A staff reply between the proposal and the "yes" stops the withdraw."""
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"], minutes_ago=2)
    ctx = _ctx(db, contact)
    _out, step = _propose(db, ctx, SI_WITHDRAW, {"submission_id": rid}, [rid])
    db.get(StockInquiry, rid).purchasing_response = "ETA 3 weeks"
    db.flush()

    outcome = _store_and_confirm(db, ctx, step)

    assert outcome.status != "executed"
    assert db.get(StockInquiry, rid) is not None


# ================================================================ AC-17 console = test


def test_ac17_a_console_confirm_writes_nothing(db):
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    out, step = _propose(db, ctx, SI_CREATE, {"product_code": _product(db), "quantity": "4"}, is_test=True)
    assert out.status == "proposed"

    outcome = _store_and_confirm(db, ctx, step, operator=seed_user(db, contact_pk=None, slugs=()))

    assert db.query(StockInquiry).filter(StockInquiry.contact_id == contact["pk"]).count() == 0
    assert "Test turn: nothing was sent." in outcome.reply_text


def test_ac17_a_console_withdraw_deletes_nothing(db):
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])
    ctx = _ctx(db, contact)
    _out, step = _propose(db, ctx, SI_WITHDRAW, {"submission_id": rid}, [rid], is_test=True)

    _store_and_confirm(db, ctx, step, operator=seed_user(db, contact_pk=None, slugs=()))

    assert db.get(StockInquiry, rid) is not None


def test_ac17_a_console_turn_marks_the_step_as_a_test(db):
    """The loop, not the model, decides test or live."""
    from app.services.chatbot.agent.loop import run_agent_turn

    contact = _dealer(db)
    code = _product(db)
    provider = _scripted(
        _asks({"id": "p1", "name": SI_CREATE, "arguments": {"product_code": code, "quantity": "4", "_is_test": False}}),
        _says("ok"),
    )
    run_agent_turn(db, contact_respond_id=contact["respond_id"], text="4 pcs", provider=provider,
                   mcp_call=_forbidden, catalog={}, is_test=True)
    # A model-supplied loop key is refused, so nothing is proposed from it.
    from app.services.chatbot.agent import actions

    assert actions.pending_action(db, contact["respond_id"], user_id="") is None


# ================================================================ AC-18 read


def test_ac18_the_list_holds_only_own_submitted_rows_with_own_notes(db):
    from app.services.chatbot.agent import portal_writes

    contact, other = _dealer(db), _dealer(db)
    mine = _submitted_si(db, contact["pk"])
    _submitted_si(db, contact["pk"], status="draft", portal_draft_at=datetime.utcnow())
    _submitted_si(db, other["pk"])
    note = _note(db, mine, contact_pk=contact["pk"])
    _note(db, mine, user_id=seed_user(db, contact_pk=None, slugs=()))
    seen: set[str] = set()

    out = portal_writes.run_read(db, _ctx(db, contact), LIST, {}, seen)

    assert out.status == "ok", out.message
    rows = out.data["requests"]
    assert [r["id"] for r in rows] == [mine]
    assert rows[0]["kind"] == "stock_inquiry"
    assert [n["id"] for n in rows[0]["my_notes"]] == [note]
    assert {mine, note} <= seen


def test_ac18_a_hidden_kind_is_left_out_of_the_list(db):
    from app.services.chatbot.agent import portal_writes

    contact = _dealer(db)
    _submitted_si(db, contact["pk"])
    _hide_form(db, contact["pk"])

    out = portal_writes.run_read(db, _ctx(db, contact), LIST, {}, set())

    assert out.status == "ok"
    assert all(r["kind"] != "stock_inquiry" for r in out.data["requests"])


def test_ac18_the_list_refuses_a_kind_the_contact_cannot_see(db):
    from app.services.chatbot.agent import portal_writes

    contact = _dealer(db)
    _hide_form(db, contact["pk"])

    out = portal_writes.run_read(db, _ctx(db, contact), LIST, {"kind": "stock_inquiry"}, set())

    assert out.status in ("denied", "invalid")


# AC-19 (router unchanged for open bot questions) stays pinned by tests/chatbot/agent/test_router_bot_asked.py.


def test_ac15_an_inquiry_sent_through_the_agent_can_be_withdrawn_at_once(db):
    """End to end on the real submit: nothing the submit itself creates blocks its own undo."""
    from app.models.notification import Notification
    from app.models.portal import PortalFormRevision
    from app.models.procurement import StockInquiry

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    _out, step = _propose(db, ctx, SI_CREATE, {"product_code": _product(db), "quantity": "4"})
    assert _store_and_confirm(db, ctx, step).status == "executed"
    rid = str(db.query(StockInquiry.id).filter(StockInquiry.contact_id == contact["pk"]).scalar())

    out, step = _propose(db, ctx, SI_WITHDRAW, {"submission_id": rid}, [rid])
    assert out.status == "proposed", out.message
    assert _store_and_confirm(db, ctx, step).status == "executed"

    assert db.get(StockInquiry, rid) is None
    assert db.query(PortalFormRevision).filter(PortalFormRevision.source_entity_id == rid).count() == 0
    assert db.query(Notification).filter(Notification.source_entity_id == rid).count() == 0


def test_ac15_an_untouched_sla_stage_the_submit_opened_goes_with_the_inquiry(db):
    from app.models.sla import ConversationSLATracking
    from app.models.procurement import StockInquiry
    from tests._void_harness import new_policy, new_tracker

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])
    tid = new_tracker(db, source_entity_type="stock_inquiry", source_entity_id=rid, policy_id=new_policy(db))
    ctx = _ctx(db, contact)
    out, step = _propose(db, ctx, SI_WITHDRAW, {"submission_id": rid}, [rid])
    assert out.status == "proposed", out.message

    assert _store_and_confirm(db, ctx, step).status == "executed"
    assert db.get(StockInquiry, rid) is None
    assert db.get(ConversationSLATracking, tid) is None


@pytest.mark.parametrize("touch", ["handled", "resolved", "form_action"])
def test_ac16_a_stage_someone_acted_on_refuses_the_withdraw(db, touch):
    from app.models.sla import SlaFormAction
    from tests._void_harness import new_policy, new_tracker

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])
    staff = seed_user(db, contact_pk=None, slugs=())
    if touch == "form_action":
        db.add(SlaFormAction(id=str(uuid.uuid4()), action_key="si.respond", source_entity_type="stock_inquiry",
                             source_entity_id=rid, payload_json={}, prior_state_json={}))
        db.flush()
    else:
        new_tracker(db, source_entity_type="stock_inquiry", source_entity_id=rid, policy_id=new_policy(db),
                    handled_by_id=staff if touch == "handled" else None, is_resolved=touch == "resolved")

    out, step = _propose(db, _ctx(db, contact), SI_WITHDRAW, {"submission_id": rid}, [rid])

    assert step is None and REFUSED in (out.message or "")


# ================================================================ security round 1 (B1, S1, S2)


def _live_action(db, ctx, name, args, seen=()):
    from app.services.chatbot.agent import actions

    _out, step = _propose(db, ctx, name, args, seen)
    assert step is not None, _out.message
    return actions.store_proposal(db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])


def test_b1_a_staff_console_confirm_of_a_live_dealer_proposal_is_refused(db):
    from app.models.procurement import StockInquiry
    from app.services.chatbot.agent import actions

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    action = _live_action(db, ctx, SI_CREATE, {"product_code": _product(db), "quantity": "4"})
    staff = seed_user(db, contact_pk=None, slugs=())

    with pytest.raises(actions.ActionRefused):
        actions.confirm(db, contact["respond_id"], str(action.id), via="console", operator_user_id=staff)
    with pytest.raises(actions.ActionRefused):
        actions.confirm(db, contact["respond_id"], str(action.id), via="chat", turn_id=str(uuid.uuid4()),
                        operator_user_id=staff)
    assert db.query(StockInquiry).filter(StockInquiry.contact_id == contact["pk"]).count() == 0
    db.refresh(action)
    assert action.status == "proposed"


def test_b1_a_live_withdraw_cannot_be_run_from_the_console(db):
    from app.models.procurement import StockInquiry
    from app.services.chatbot.agent import actions

    contact = _dealer(db)
    rid = _submitted_si(db, contact["pk"])
    ctx = _ctx(db, contact)
    action = _live_action(db, ctx, SI_WITHDRAW, {"submission_id": rid}, [rid])

    with pytest.raises(actions.ActionRefused):
        actions.confirm(db, contact["respond_id"], str(action.id), via="console",
                        operator_user_id=seed_user(db, contact_pk=None, slugs=()))
    assert db.get(StockInquiry, rid) is not None


def test_b1_a_console_turn_is_not_offered_the_confirm_of_a_live_proposal(db):
    from app.services.chatbot.agent import actions
    from app.services.chatbot.agent.loop import run_agent_turn

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    live = _live_action(db, ctx, SI_CREATE, {"product_code": _product(db), "quantity": "4"})
    provider = _scripted(_says("ok"))

    run_agent_turn(db, contact_respond_id=contact["respond_id"], text="yes", provider=provider, mcp_call=_forbidden,
                   catalog={}, is_test=True, operator_user_id=seed_user(db, contact_pk=None, slugs=()))

    assert "confirm_action" not in provider.calls[0]["tools"]
    db.refresh(live)
    assert live.status == "proposed"


def test_s1_a_console_operator_cannot_cancel_a_live_dealer_proposal(db):
    from app.services.chatbot.agent import actions

    contact = _dealer(db)
    action = _live_action(db, _ctx(db, contact), SI_CREATE, {"product_code": _product(db), "quantity": "4"})

    with pytest.raises(actions.ActionRefused):
        actions.cancel(db, contact["respond_id"], str(action.id), operator_user_id=seed_user(db, contact_pk=None, slugs=()))
    db.refresh(action)
    assert action.status == "proposed"


def test_s2_a_console_proposal_leaves_the_live_one_and_neither_answers_the_other(db):
    from app.services.chatbot.agent import actions
    from app.services.chatbot.router import decide_route

    contact = _dealer(db)
    ctx = _ctx(db, contact)
    code = _product(db)
    live = _live_action(db, ctx, SI_CREATE, {"product_code": code, "quantity": "4"})
    _out, step = _propose(db, ctx, SI_CREATE, {"product_code": code, "quantity": "9"}, is_test=True)
    test = actions.store_proposal(db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])

    db.refresh(live)
    assert live.status == "proposed", "a console test must not expire the dealer's live proposal"
    assert actions.pending_action(db, contact["respond_id"], user_id="", test=False).id == live.id
    assert actions.pending_action(db, contact["respond_id"], user_id="", test=True).id == test.id
    # The dealer's WhatsApp yes cannot confirm the console's test.
    with pytest.raises(actions.ActionRefused):
        actions.confirm(db, contact["respond_id"], str(test.id), via="chat", turn_id=str(uuid.uuid4()))
    # The live proposal is still the newest live one and confirms from the dealer's own turn.
    assert actions.confirm(db, contact["respond_id"], str(live.id), via="chat", turn_id=str(uuid.uuid4())).status == "executed"
    decision = decide_route(db, contact_respond_id=contact["respond_id"], text="hi", session_vars=None, has_media=False)
    assert decision.reason != "pending_action", "a console test proposal never holds the WhatsApp message"
