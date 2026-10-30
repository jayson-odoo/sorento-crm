"""AGENTIC-W3 (PLAN-agentic-w3-pr-decide-30oct.md): approve / reject a purchase request or a sponsorship form
through the agent's proposal path.

Service level (`writes.propose_step`, `actions.store_proposal`, `actions.confirm`) over the real route function
`decide_purchase_request_approval`, so the route's own checks, the form-action ledger and the grace window are
the screen's. Postgres only (blank schema); every test seeds its own rows. The outward sends (requester
notification, dealer WhatsApp, approval automation) are replaced by recorders: the tests assert they ran once,
or not at all.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.audit import AuditLog
from app.models.procurement import PurchaseRequestHeader
from app.models.sla import SlaFormAction
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user

LIST = "crm_purchase_requests_list"
DECIDE = "crm_purchase_request_decide"
APPROVE = "procurement.purchase_requests.approve"
PR_VIEW = "procurement.purchase_requests.view"
PR_VIEW_OWN = "procurement.purchase_requests.view_own"
SF_VIEW = "procurement.sponsorship_forms.view"
APPROVER = (PR_VIEW, SF_VIEW, APPROVE)

_SENDS = (
    "_notify_requester_on_approved",
    "_notify_requester_on_rejected",
    "_notify_contact_on_approval_approved",
    "_notify_contact_on_approval_rejected",
    "_dispatch_approval_automation",
)


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


@pytest.fixture()
def sends(monkeypatch):
    """Every outward send of a decision, recorded instead of sent: [(method name, request id)]."""
    from app.services.procurement_service import PurchaseRequestService

    calls: list[tuple[str, str]] = []
    for name in _SENDS:
        monkeypatch.setattr(
            PurchaseRequestService, name, lambda self, header, _n=name: calls.append((_n, str(header.id)))
        )
    return calls


@dataclass
class World:
    contact: dict
    user_id: str
    sender_id: str
    rows: list = field(default_factory=list)

    @property
    def respond_id(self) -> str:
        return self.contact["respond_id"]


def make_world(db, *, slugs=APPROVER) -> World:
    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"], slugs=slugs)
    sender_id = seed_user(db, contact_pk=None, slugs=())
    db.commit()
    return World(contact=contact, user_id=user_id, sender_id=sender_id)


def make_request(
    db, w: World, *, kind="purchase_request", approval_status="pending", status="submitted", submitted_by=None,
    title=None,
) -> PurchaseRequestHeader:
    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=kind,
        request_number=unique_code("PR"),
        customer_name="ZZT Example Trading",
        project_title=title or "Showroom display",
        total_project_value=12500,
        status=status,
        approval_status=approval_status,
        source="crm",
        contact_id=submitted_by,
        requested_approval_by_user_id=w.sender_id,
    )
    db.add(row)
    db.commit()
    w.rows.append(row)
    return row


def row_now(db, rid: str) -> PurchaseRequestHeader:
    db.expire_all()
    return db.query(PurchaseRequestHeader).filter(PurchaseRequestHeader.id == str(rid)).one()


def ctx_of(db, w):
    from app.services.chatbot.agent.access import build_context

    return build_context(db, w.respond_id)


def propose(db, w, args, seen=None):
    from app.services.chatbot.agent import writes

    ids = {str(args.get("request_id", "")).lower()} if seen is None else seen
    return writes.propose_step(db, ctx_of(db, w), DECIDE, args, seen_ids=ids)


def propose_and_store(db, w, args):
    from app.services.chatbot.agent import actions

    res, step = propose(db, w, args)
    assert res.status == "proposed", f"{res.status} {res.message}"
    ctx = ctx_of(db, w)
    row = actions.store_proposal(db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])
    return step, row


def confirm(db, w, action_row):
    from app.services.chatbot.agent import actions

    return actions.confirm(db, w.respond_id, str(action_row.id), via="console")


def no_grace(monkeypatch):
    monkeypatch.setattr("app.services.form_action_grace.grace_seconds_for", lambda *a, **k: 0)


# ------------------------------------------------------------------ registry and exposure


def test_the_registry_holds_the_decide_write_and_the_list_read():
    from app.services.chatbot.agent import writes
    from app.services.chatbot.agent.tools import TOOL_LABELS

    assert DECIDE in writes.WRITES and LIST in writes.USER_READS
    assert writes.WRITES[DECIDE].user_permission == APPROVE
    assert writes.WRITES[DECIDE].record_key == "request_id"
    assert DECIDE in TOOL_LABELS and LIST in TOOL_LABELS


def test_a_user_without_the_approve_slug_is_not_offered_the_decision(db):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=(PR_VIEW,))

    names = {d.name for d in writes.permitted_writes(db, ctx_of(db, w))}
    reads = {r.name for r in writes.permitted_user_reads(db, ctx_of(db, w))}

    assert DECIDE not in names
    assert LIST in reads


def test_a_user_with_no_request_slug_is_not_offered_the_list(db):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=("sales.customer_asks.view",))

    assert LIST not in {r.name for r in writes.permitted_user_reads(db, ctx_of(db, w))}


# ------------------------------------------------------------------ the list read


def test_the_list_shows_pending_requests_with_their_id_and_number(db):
    from app.services.chatbot.agent import writes

    w = make_world(db)
    pending = make_request(db, w)
    make_request(db, w, approval_status="approved", status="approved")
    seen: set[str] = set()

    res = writes.run_user_read(db, ctx_of(db, w), LIST, {}, seen)

    assert res.status == "ok", res.message
    ids = [r["request_id"] for r in res.data["requests"]]
    assert ids == [pending.id] or (pending.id in ids and all(
        r["approval_status"] == "pending" for r in res.data["requests"]
    ))
    row = next(r for r in res.data["requests"] if r["request_id"] == pending.id)
    assert row["number"] == pending.request_number
    assert row["kind"] == "purchase_request"
    assert row["customer"] == "ZZT Example Trading"
    assert pending.id.lower() in seen


def test_the_list_filters_by_status_and_kind(db):
    from app.services.chatbot.agent import writes

    w = make_world(db)
    make_request(db, w)
    sf = make_request(db, w, kind="sponsorship_form", approval_status="approved", status="approved")

    res = writes.run_user_read(
        db, ctx_of(db, w), LIST, {"status": "approved", "kind": "sponsorship_form"}, set()
    )

    assert res.status == "ok", res.message
    assert sf.id in [r["request_id"] for r in res.data["requests"]]
    assert all(r["kind"] == "sponsorship_form" and r["approval_status"] == "approved" for r in res.data["requests"])


def test_a_limited_user_lists_only_requests_their_contact_submitted(db):
    from app.services.chatbot.agent import writes

    w = make_world(db, slugs=(PR_VIEW_OWN, APPROVE))
    mine = make_request(db, w, submitted_by=w.contact["pk"])
    theirs = make_request(db, w, submitted_by=seed_contact(db)["pk"])

    res = writes.run_user_read(db, ctx_of(db, w), LIST, {}, set())

    ids = [r["request_id"] for r in res.data["requests"]]
    assert mine.id in ids and theirs.id not in ids


def test_the_list_refuses_unknown_arguments(db):
    from app.services.chatbot.agent import writes

    w = make_world(db)

    res = writes.run_user_read(db, ctx_of(db, w), LIST, {"approver": "me"}, set())

    assert res.status == "invalid"


# ------------------------------------------------------------------ proposing


def test_proposing_an_approval_writes_nothing_and_names_the_request(db, sends):
    w = make_world(db)
    pr = make_request(db, w)

    res, step = propose(db, w, {"request_id": pr.id, "decision": "approve"})

    assert res.status == "proposed", res.message
    summary = step["summary"]
    assert summary.startswith("Approve purchase request ")
    assert pr.request_number in summary and "ZZT Example Trading" in summary and "Showroom display" in summary
    assert "will be told" in summary
    assert step["before"]["approval_status"] == "pending"
    assert row_now(db, pr.id).approval_status == "pending"
    assert sends == []


def test_a_sponsorship_form_is_named_as_one(db):
    w = make_world(db)
    sf = make_request(db, w, kind="sponsorship_form")

    res, step = propose(db, w, {"request_id": sf.id, "decision": "approve"})

    assert res.status == "proposed", res.message
    assert step["summary"].startswith("Approve sponsorship form ")


def test_a_rejection_quotes_the_reason(db):
    w = make_world(db)
    pr = make_request(db, w)

    res, step = propose(db, w, {"request_id": pr.id, "decision": "reject", "reason": "Budget not approved"})

    assert res.status == "proposed", res.message
    assert step["summary"].startswith("Reject purchase request ")
    assert '"Budget not approved"' in step["summary"]


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_a_rejection_without_a_reason_is_refused(db, reason):
    w = make_world(db)
    pr = make_request(db, w)
    args = {"request_id": pr.id, "decision": "reject"}
    if reason is not None:
        args["reason"] = reason

    res, step = propose(db, w, args)

    assert res.status == "invalid" and step is None
    assert res.message == "Rejection reason is required."


@pytest.mark.parametrize("state", ["approved", "rejected"])
def test_an_already_decided_request_is_refused_in_the_services_words(db, state):
    w = make_world(db)
    pr = make_request(db, w, approval_status=state, status=state)

    res, step = propose(db, w, {"request_id": pr.id, "decision": "approve"})

    assert step is None and res.status == "invalid"
    assert f"already been {state}" in res.message


def test_a_request_not_sent_for_approval_is_refused(db):
    w = make_world(db)
    pr = make_request(db, w, approval_status=None)

    res, step = propose(db, w, {"request_id": pr.id, "decision": "approve"})

    assert step is None and res.status == "invalid"
    assert "not pending approval" in res.message


def test_a_voided_request_is_refused(db):
    w = make_world(db)
    pr = make_request(db, w, status="voided", approval_status="voided")

    res, step = propose(db, w, {"request_id": pr.id, "decision": "approve"})

    assert step is None and res.status in ("invalid", "denied")


def test_a_limited_user_is_refused_the_decision_like_the_route(db):
    """The router's own-scope guard refuses every write to a `view_own`-only user; a direct call skips the
    router, so the tool runs the same check."""
    w = make_world(db, slugs=(PR_VIEW_OWN, APPROVE))
    pr = make_request(db, w, submitted_by=w.contact["pk"])

    res, step = propose(db, w, {"request_id": pr.id, "decision": "approve"})

    assert step is None and res.status == "denied"


def test_the_handling_lock_refuses_at_proposal(db, monkeypatch):
    from app.services.error_handler import AppException

    def held(db_, rid, actor, **kw):
        raise AppException(status_code=403, message="This form is being handled by someone else.", code="FORBIDDEN")

    monkeypatch.setattr("app.services.handling_lock_service.assert_can_act_on_form", held)
    w = make_world(db)
    pr = make_request(db, w)

    res, step = propose(db, w, {"request_id": pr.id, "decision": "approve"})

    assert step is None and res.status == "denied"
    assert "handled by" in res.message


def test_another_decision_waiting_in_its_grace_window_refuses_at_proposal(db):
    w = make_world(db)
    pr = make_request(db, w)
    db.add(SlaFormAction(
        action_key="pr.approval_decision", source_entity_type="purchase_request", source_entity_id=pr.id,
        event_name="approved", payload_json={"request_id": pr.id, "action": "approved"}, prior_state_json={},
        requested_by_id=w.sender_id, channel="ui", status="pending",
    ))
    db.commit()

    res, step = propose(db, w, {"request_id": pr.id, "decision": "approve"})

    assert step is None and res.status == "invalid"
    assert "still pending" in res.message


def test_an_unseen_request_id_is_refused(db):
    w = make_world(db)
    pr = make_request(db, w)

    res, step = propose(db, w, {"request_id": pr.id, "decision": "approve"}, seen=set())

    assert step is None and res.status == "invalid"


# ------------------------------------------------------------------ confirming


def test_confirming_an_approval_decides_it_as_the_linked_user(db, sends, monkeypatch):
    no_grace(monkeypatch)
    w = make_world(db)
    pr = make_request(db, w)
    _, action = propose_and_store(db, w, {"request_id": pr.id, "decision": "approve"})

    out = confirm(db, w, action)

    assert out.status == "executed", out.steps
    now = row_now(db, pr.id)
    assert (now.approval_status, now.status) == ("approved", "approved")
    assert now.approved_by == "ZZT Agent User"
    assert ("_notify_contact_on_approval_approved", pr.id) in sends
    assert ("_notify_requester_on_approved", pr.id) in sends
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == pr.id, AuditLog.action == "UPDATE")
        .order_by(AuditLog.changed_at.desc())
        .first()
    )
    assert audit is not None and str(audit.user_id) == w.user_id and audit.auth_method == "agent"
    ledger = db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == pr.id).one()
    assert (ledger.status, str(ledger.requested_by_id)) == ("committed", w.user_id)


def test_confirming_a_rejection_stores_the_reason_and_the_rejecter(db, sends, monkeypatch):
    no_grace(monkeypatch)
    w = make_world(db)
    pr = make_request(db, w, kind="sponsorship_form")
    _, action = propose_and_store(db, w, {"request_id": pr.id, "decision": "reject", "reason": "Budget not approved"})

    out = confirm(db, w, action)

    assert out.status == "executed", out.steps
    now = row_now(db, pr.id)
    assert (now.approval_status, now.approval_comments) == ("rejected", "Budget not approved")
    assert str(now.rejected_by_id) == w.user_id
    assert ("_notify_contact_on_approval_rejected", pr.id) in sends
    assert out.steps[0]["changes"] and out.steps[0]["changes"][0]["after"] == "Rejected"


def test_a_decision_made_on_screen_after_the_proposal_rejects_the_action(db, sends, monkeypatch):
    no_grace(monkeypatch)
    w = make_world(db)
    pr = make_request(db, w)
    _, action = propose_and_store(db, w, {"request_id": pr.id, "decision": "approve"})
    row = row_now(db, pr.id)
    row.approval_status, row.status, row.approval_comments = "rejected", "rejected", "On screen"
    db.commit()

    out = confirm(db, w, action)

    assert out.status == "rejected"
    assert row_now(db, pr.id).approval_status == "rejected"
    assert sends == []


def test_with_a_grace_window_the_decision_is_parked_not_applied(db, sends, monkeypatch):
    monkeypatch.setattr("app.services.form_action_grace.grace_seconds_for", lambda *a, **k: 30)
    w = make_world(db)
    pr = make_request(db, w)
    _, action = propose_and_store(db, w, {"request_id": pr.id, "decision": "approve"})

    out = confirm(db, w, action)

    assert out.status == "executed", out.steps
    assert row_now(db, pr.id).approval_status == "pending"
    assert sends == []
    parked = db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == pr.id).one()
    assert (parked.status, str(parked.requested_by_id)) == ("pending", w.user_id)
    assert parked.commit_at is not None
    db.expire_all()
    from app.models.chatbot_agent import AgentAction

    step = db.get(AgentAction, str(action.id)).steps[0]
    assert step["after"]["deferred"] is True and step["after"]["commit_at"]
    assert "applies in 30 seconds" in out.reply_text


def test_the_slug_removed_before_confirm_rejects_the_action(db, sends, monkeypatch):
    from tests.chatbot.agent.test_agent_writes import revoke

    no_grace(monkeypatch)
    w = make_world(db)
    pr = make_request(db, w)
    _, action = propose_and_store(db, w, {"request_id": pr.id, "decision": "approve"})
    revoke(db, w.user_id, APPROVE)

    out = confirm(db, w, action)

    assert out.status == "rejected"
    assert row_now(db, pr.id).approval_status == "pending"
    assert sends == []


# ------------------------------------------------------------------ one turn


def test_a_turn_lists_then_proposes_an_approval_and_writes_nothing(db, sends):
    from tests.chatbot.agent.test_agent_writes import PROPOSAL_HEAD, answer_, round_of, run_turn, tc, tool_names

    w = make_world(db)
    pr = make_request(db, w)
    script = [
        round_of(tc(LIST, {}, "l1")),
        round_of(tc(DECIDE, {"request_id": pr.id, "decision": "approve"}, "d1")),
        answer_("I have prepared the approval."),
    ]

    result, provider = run_turn(db, w, script, text_="approve the pending showroom request")

    assert {LIST, DECIDE} <= tool_names(provider)
    assert result.pending_action is not None
    assert PROPOSAL_HEAD in result.reply_text
    assert f"Approve purchase request {pr.request_number}" in result.reply_text
    assert row_now(db, pr.id).approval_status == "pending"
    assert sends == []
