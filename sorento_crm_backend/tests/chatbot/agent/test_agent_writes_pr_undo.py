"""AGENTIC-W3 Q1(a) (PLAN-agentic-w3-pr-decide-30oct.md): taking a purchase-request action back.

Two ways, both the system's own:
- the console's Withdraw on a parked step (`actions.withdraw`): the form-action cancel, as the linked user who
  started it, while the grace window runs; nothing ran, nobody is told;
- the write `crm_purchase_request_action_undo`, proposed and confirmed like any write: inside the window it
  withdraws the user's own waiting action; after commit it is the system's post-grace undo (its slug, its
  mandatory reason, its guardrail and its refusal words).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.sla import SlaFormAction
from tests.chatbot.agent.test_agent_writes_purchase_request import (  # noqa: F401 - fixtures and helpers
    APPROVER,
    DECIDE,
    _listeners,
    confirm,
    ctx_of,
    db,
    make_request,
    make_world,
    no_grace,
    propose_and_store,
    row_now,
    sends,
)

UNDO = "crm_purchase_request_action_undo"
UNDO_SLUG = "sla_management.form_sla.undo_action"


def grace(monkeypatch, seconds=30):
    monkeypatch.setattr("app.services.form_action_grace.grace_seconds_for", lambda *a, **k: seconds)


def decided(db, w, monkeypatch, *, parked: bool, kind="purchase_request"):
    """A pending request the user approved through the agent: parked in its grace window, or applied."""
    grace(monkeypatch, 30 if parked else 0)
    pr = make_request(db, w, kind=kind)
    _, action = propose_and_store(db, w, {"request_id": pr.id, "decision": "approve"})
    out = confirm(db, w, action)
    assert out.status == "executed", out.steps
    return pr, action


def propose_undo(db, w, args):
    from app.services.chatbot.agent import writes

    return writes.propose_step(db, ctx_of(db, w), UNDO, args, seen_ids={str(args["request_id"]).lower()})


def store(db, w, step):
    from app.services.chatbot.agent import actions

    return actions.store_proposal(
        db, ctx_of(db, w), conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step]
    )


def form_actions(db, rid):
    db.expire_all()
    return db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == str(rid)).order_by(SlaFormAction.created_at).all()


# ------------------------------------------------------------------ the undo write


def test_the_undo_write_is_registered_and_offered_to_a_user_who_sees_requests(db):
    from app.services.chatbot.agent import writes
    from app.services.chatbot.agent.tools import TOOL_LABELS

    assert UNDO in writes.WRITES and writes.WRITES[UNDO].record_key == "request_id"
    assert UNDO in TOOL_LABELS
    w = make_world(db)
    assert UNDO in {d.name for d in writes.permitted_writes(db, ctx_of(db, w))}


def test_inside_the_window_the_undo_withdraws_the_users_own_waiting_decision(db, sends, monkeypatch):
    w = make_world(db)
    pr, _ = decided(db, w, monkeypatch, parked=True)

    res, step = propose_undo(db, w, {"request_id": pr.id})

    assert res.status == "proposed", res.message
    assert step["summary"].startswith("Withdraw the waiting approval on purchase request ")
    assert pr.request_number in step["summary"]
    from app.services.chatbot.agent import actions

    out = actions.confirm(db, w.respond_id, str(store(db, w, step).id), via="console")

    assert out.status == "executed", out.steps
    assert [a.status for a in form_actions(db, pr.id)] == ["cancelled"]
    assert row_now(db, pr.id).approval_status == "pending"
    assert sends == []


def test_someone_elses_waiting_decision_cannot_be_withdrawn(db, monkeypatch):
    w = make_world(db)
    pr = make_request(db, w)
    db.add(SlaFormAction(
        action_key="pr.approval_decision", source_entity_type="purchase_request", source_entity_id=pr.id,
        event_name="approved", payload_json={"request_id": pr.id, "action": "approved"}, prior_state_json={},
        requested_by_id=w.sender_id, channel="ui", status="pending",
        created_at=datetime.utcnow(), commit_at=datetime.utcnow() + timedelta(seconds=60),
    ))
    db.commit()

    res, step = propose_undo(db, w, {"request_id": pr.id})

    assert step is None and res.status == "invalid"
    assert res.message == "Only the person who started this action can undo it."


def test_after_commit_the_undo_needs_the_systems_reason(db, sends, monkeypatch):
    w = make_world(db, slugs=(*APPROVER, UNDO_SLUG))
    pr, _ = decided(db, w, monkeypatch, parked=False)

    res, step = propose_undo(db, w, {"request_id": pr.id})

    assert step is None and res.status == "invalid"
    assert res.message == "A reason is required to undo an action."


def test_after_commit_the_undo_needs_the_systems_undo_slug(db, sends, monkeypatch):
    w = make_world(db)
    pr, _ = decided(db, w, monkeypatch, parked=False)

    res, step = propose_undo(db, w, {"request_id": pr.id, "reason": "Approved the wrong one"})

    assert step is None
    assert res.message == "You do not have permission to undo actions on this form."


def test_after_commit_the_undo_reverses_the_decision_through_the_system(db, sends, monkeypatch):
    from app.services.chatbot.agent import actions

    w = make_world(db, slugs=(*APPROVER, UNDO_SLUG))
    pr, _ = decided(db, w, monkeypatch, parked=False)
    assert row_now(db, pr.id).approval_status == "approved"

    res, step = propose_undo(db, w, {"request_id": pr.id, "reason": "Approved the wrong one"})
    assert res.status == "proposed", res.message
    assert step["summary"].startswith("Undo the approval on purchase request ")
    assert '"Approved the wrong one"' in step["summary"]
    out = actions.confirm(db, w.respond_id, str(store(db, w, step).id), via="console")

    assert out.status == "executed", out.steps
    assert row_now(db, pr.id).approval_status == "pending"
    undone = form_actions(db, pr.id)[-1]
    assert (undone.status, str(undone.undone_by_id), undone.undo_reason) == ("undone", w.user_id, "Approved the wrong one")


def test_the_undo_names_the_last_action_on_the_form_as_the_systems_undo_does(db, sends, monkeypatch):
    """The system's Undo reverses only the LAST committed action; the proposal says which one it is."""
    from app.services.form_action_registry import get_action

    w = make_world(db, slugs=(*APPROVER, UNDO_SLUG))
    pr, _ = decided(db, w, monkeypatch, parked=False)
    first = form_actions(db, pr.id)[0]
    db.add(SlaFormAction(
        action_key="pr.finalize", source_entity_type="purchase_request", source_entity_id=pr.id,
        event_name="resolved", payload_json={"request_id": pr.id}, prior_state_json={},
        requested_by_id=w.sender_id, channel="ui", status="committed",
        created_at=datetime.utcnow(), committed_at=first.committed_at + timedelta(seconds=5),
    ))
    db.commit()

    res, step = propose_undo(db, w, {"request_id": pr.id, "reason": "Processed by mistake"})

    assert res.status == "proposed", res.message
    label = get_action("pr.finalize").label.lower()
    assert step["summary"].startswith(f"Undo the {label} on purchase request ")


def test_a_voided_form_is_refused_in_the_systems_words(db, sends, monkeypatch):
    w = make_world(db, slugs=(*APPROVER, UNDO_SLUG))
    pr, _ = decided(db, w, monkeypatch, parked=False)
    row = row_now(db, pr.id)
    row.status = "voided"
    db.commit()

    res, step = propose_undo(db, w, {"request_id": pr.id, "reason": "Approved the wrong one"})

    assert step is None and res.message == "This form has moved on since that action."


def test_nothing_to_take_back_is_refused_in_the_systems_words(db):
    w = make_world(db, slugs=(*APPROVER, UNDO_SLUG))
    pr = make_request(db, w)

    res, step = propose_undo(db, w, {"request_id": pr.id, "reason": "x"})

    assert step is None and res.message == "There is no completed action on this form to undo."


def test_a_withdraw_proposed_while_waiting_is_rejected_once_the_decision_applied(db, sends, monkeypatch):
    from app.services.chatbot.agent import actions
    from app.services.form_action_service import FormActionService

    w = make_world(db, slugs=(*APPROVER, UNDO_SLUG))
    pr, _ = decided(db, w, monkeypatch, parked=True)
    res, step = propose_undo(db, w, {"request_id": pr.id})
    assert res.status == "proposed", res.message
    action = store(db, w, step)
    FormActionService(db).commit_one(form_actions(db, pr.id)[0])

    out = actions.confirm(db, w.respond_id, str(action.id), via="console")

    assert out.status == "rejected"
    assert row_now(db, pr.id).approval_status == "approved"


# ------------------------------------------------------------------ the console's Withdraw


def test_a_parked_step_reports_its_waiting_window(db, sends, monkeypatch):
    w = make_world(db)
    grace(monkeypatch, 30)
    pr = make_request(db, w)
    _, action = propose_and_store(db, w, {"request_id": pr.id, "decision": "approve"})

    out = confirm(db, w, action)

    waiting = out.steps[0]["waiting"]
    assert waiting["window_seconds"] == 30 and waiting["commit_at"]


def test_withdraw_cancels_the_parked_decision_as_the_linked_user(db, sends, monkeypatch):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    pr, action = decided(db, w, monkeypatch, parked=True)

    out = actions.withdraw(db, w.respond_id, str(action.id), 0)

    assert out.steps[0]["status"] == "withdrawn" and out.steps[0]["waiting"] is None
    assert "nobody was told" in out.reply_text
    assert [a.status for a in form_actions(db, pr.id)] == ["cancelled"]
    assert row_now(db, pr.id).approval_status == "pending"
    assert sends == []


def test_withdraw_after_the_decision_applied_is_refused(db, sends, monkeypatch):
    from app.services.chatbot.agent import actions
    from app.services.form_action_service import FormActionService

    w = make_world(db)
    pr, action = decided(db, w, monkeypatch, parked=True)
    FormActionService(db).commit_one(form_actions(db, pr.id)[0])

    with pytest.raises(actions.ActionRefused) as exc:
        actions.withdraw(db, w.respond_id, str(action.id), 0)

    assert exc.value.reason == "applied"
    assert row_now(db, pr.id).approval_status == "approved"


def test_withdraw_of_a_step_that_never_waited_is_refused(db, sends, monkeypatch):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    _, action = decided(db, w, monkeypatch, parked=False)

    with pytest.raises(actions.ActionRefused) as exc:
        actions.withdraw(db, w.respond_id, str(action.id), 0)

    assert exc.value.reason == "not_waiting"


@pytest.mark.parametrize("index", [-1, 1, 99])
def test_withdraw_of_a_step_that_does_not_exist_is_refused(db, sends, monkeypatch, index):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    _, action = decided(db, w, monkeypatch, parked=True)

    with pytest.raises(actions.ActionRefused) as exc:
        actions.withdraw(db, w.respond_id, str(action.id), index)

    assert exc.value.reason == "not_found"


def test_withdraw_by_an_operator_without_the_steps_slug_is_refused(db, sends, monkeypatch):
    from app.services.chatbot.agent import actions
    from tests.chatbot.agent._seed import seed_user

    w = make_world(db)
    pr, action = decided(db, w, monkeypatch, parked=True)
    stranger = seed_user(db, contact_pk=None, slugs=("system.chat_history.view",))
    db.commit()

    with pytest.raises(actions.ActionRefused) as exc:
        actions.withdraw(db, w.respond_id, str(action.id), 0, operator_user_id=stranger)

    assert exc.value.reason == "entry_refused"
    assert [a.status for a in form_actions(db, pr.id)] == ["pending"]


def test_withdraw_of_another_contacts_action_is_not_found(db, sends, monkeypatch):
    from app.services.chatbot.agent import actions

    w = make_world(db)
    other = make_world(db)
    _, action = decided(db, w, monkeypatch, parked=True)

    with pytest.raises(actions.ActionRefused) as exc:
        actions.withdraw(db, other.respond_id, str(action.id), 0)

    assert exc.value.reason == "not_found"
