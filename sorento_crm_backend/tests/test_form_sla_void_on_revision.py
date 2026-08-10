"""Void-and-restart: what a contact revision does to the SLA side.

Covers UAC F1/F2/F4/F4a/F4b/F5/F6/F6a/FT1 - the tracker bookkeeping, the exclusions
that keep a voided stage out of every "open" query and every dashboard number, and
the notification to whoever was mid-work.

Run: pytest tests/test_form_sla_void_on_revision.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models.notification import Notification
from app.models.sla import ConversationSLAEventLog, ConversationSLATracking
from app.services.form_sla_service import FormSLAOrchestrator
from app.services.portal_revision_service import PortalRevisionService
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    seed_agent,
    seed_config,
    seed_contact,
    seed_entity,
    seed_policy,
    seed_stage_config,
    seed_system_settings,
    seed_token,
    seed_tracker,
    seed_user,
)

KIND = "stock_inquiry"


@pytest.fixture(autouse=True)
def no_queue():
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _setup(db, *, assigned_to_id=None, handled_by_id=None, tracker_kwargs=None):
    seed_system_settings(db, cap=3)
    seed_config(db, KIND)
    contact = seed_contact(db)
    row = seed_entity(db, KIND, contact)
    policy_id = seed_policy(db)
    tracker = seed_tracker(
        db,
        KIND,
        str(row.id),
        policy_id,
        assigned_to_id=assigned_to_id,
        handled_by_id=handled_by_id,
        **(tracker_kwargs or {}),
    )
    return contact, seed_token(contact), row, tracker


def _revise(db, token, row, reason="Quantity was wrong on the original"):
    return PortalRevisionService(db).revise(
        token, KIND, str(row.id), {"quantity": "12"}, reason, row.revision_no
    )


# ------------------------------------------------------------------- the void


def test_revision_voids_the_open_stage(db):
    _c, token, row, tracker = _setup(db)
    _revise(db, token, row)

    db.expire_all()
    fresh = db.query(ConversationSLATracking).filter_by(id=tracker.id).one()
    assert fresh.voided_at is not None
    assert fresh.void_reason == "revised_by_contact"
    # NOT resolved: a voided stage was never completed, and saying otherwise would
    # count it as a finished stage in every duration and KPI aggregate.
    assert fresh.is_resolved is False


def test_void_releases_the_handling_lock(db):
    handler = seed_user(db, name="Locked Larry")
    _c, token, row, tracker = _setup(db, handled_by_id=handler.id)
    _revise(db, token, row)

    db.expire_all()
    fresh = db.query(ConversationSLATracking).filter_by(id=tracker.id).one()
    assert fresh.handled_by_id is None
    assert fresh.handled_at is None


def test_void_writes_one_event_log_per_tracker(db):
    _c, token, row, tracker = _setup(db)
    _revise(db, token, row, reason="Wrong product code")

    logs = (
        db.query(ConversationSLAEventLog)
        .filter(ConversationSLAEventLog.sla_tracking_id == tracker.id)
        .all()
    )
    assert [log.event_type for log in logs] == ["void"]
    assert "Wrong product code" in (logs[0].reason or "")


def test_void_event_log_timestamps_are_not_shifted_back_eight_hours(db):
    """create_event_log reads a NAIVE datetime as Malaysia time. The tracker columns
    are naive UTC, so anything not wrapped in _to_aware_utc lands 8h early."""
    _c, token, row, tracker = _setup(db)
    tracker_due = tracker.due_at
    before = datetime.utcnow() - timedelta(minutes=1)

    _revise(db, token, row)

    log = (
        db.query(ConversationSLAEventLog)
        .filter(ConversationSLAEventLog.sla_tracking_id == tracker.id)
        .one()
    )
    assert _naive_utc(log.due_at) == _naive_utc(tracker_due)
    assert _naive_utc(log.event_at) >= before


def test_conversation_sla_is_never_touched(db):
    """UAC F4b. The two systems share this table and are told apart only by
    source_entity_type - a revision must not reach across."""
    _c, token, row, _tracker = _setup(db)
    policy_id = seed_policy(db)
    conversation = seed_tracker(
        db,
        None,  # conversation rows carry no source entity type
        str(row.id),
        policy_id,
        team_set_code=None,
    )

    _revise(db, token, row)

    db.expire_all()
    fresh = db.query(ConversationSLATracking).filter_by(id=conversation.id).one()
    assert fresh.voided_at is None
    assert fresh.void_reason is None


def test_void_active_for_source_refuses_a_non_form_type(db):
    orchestrator = FormSLAOrchestrator(db)
    assert orchestrator.void_active_for_source("not_a_form", str(uuid.uuid4()), reason="x") == []


def test_the_identify_query_and_the_void_query_ask_the_same_question(db):
    """UAC F4b, on the OTHER query.

    ``revise()`` IDENTIFIES the stage it is about to void with
    ``active_trackers_for_source`` and voids with ``void_active_for_source``. The
    void query pins the type to FORM_SLA_TYPES and negates the conversation scope;
    the identify query filtered on neither, so the two could disagree about the same
    rows. That discriminator is the ONLY thing telling the two SLA systems apart
    inside this table, and a form row has already once falsely matched a
    conversation-keyed query here.
    """
    _c, _token, row, tracker = _setup(db)
    orchestrator = FormSLAOrchestrator(db)

    # A form type: both queries see the open stage.
    assert [t.id for t in orchestrator.active_trackers_for_source(KIND, str(row.id))] == [
        tracker.id
    ]

    # A conversation-side row on the same entity id. Neither query may see it.
    policy_id = seed_policy(db)
    conversation = seed_tracker(
        db, "conversation", str(row.id), policy_id, team_set_code=None
    )
    assert orchestrator.active_trackers_for_source("conversation", str(row.id)) == []
    assert orchestrator.void_active_for_source("conversation", str(row.id), reason="x") == []
    db.expire_all()
    assert (
        db.query(ConversationSLATracking).filter_by(id=conversation.id).one().voided_at
        is None
    )


def test_the_identify_query_refuses_a_non_form_type(db):
    """The same early return the void query makes, so "what would be voided" and
    "what was voided" cannot answer differently. Seeded with a real open row under
    the non-form type, so an empty result is the guard and not an empty table."""
    entity_id = str(uuid.uuid4())
    policy_id = seed_policy(db)
    seed_tracker(db, "not_a_form", entity_id, policy_id, team_set_code=None)

    orchestrator = FormSLAOrchestrator(db)
    assert orchestrator.active_trackers_for_source("not_a_form", entity_id) == []
    assert orchestrator.void_active_for_source("not_a_form", entity_id, reason="x") == []


def test_an_already_resolved_stage_is_left_alone(db):
    _c, token, row, _tracker = _setup(db)
    policy_id = seed_policy(db)
    done = seed_tracker(
        db, KIND, str(row.id), policy_id, team_set_code="project_sales", is_resolved=True
    )

    _revise(db, token, row)

    db.expire_all()
    assert db.query(ConversationSLATracking).filter_by(id=done.id).one().voided_at is None


# --------------------------------------------------------------- the exclusions


def test_a_voided_stage_is_not_an_active_tracker(db):
    """UAC F4. This is also what lets the restart spawn a fresh stage 1 - without it
    the chain would find the stage it just voided and skip."""
    _c, token, row, tracker = _setup(db)
    policy_id = seed_policy(db)
    config = seed_stage_config(
        db,
        KIND,
        policy_id,
        stage_code="purchasing",
        team_set_code="purchasing",
    )
    orchestrator = FormSLAOrchestrator(db)
    assert orchestrator._active_tracker(config, str(row.id)) is not None

    orchestrator.void_active_for_source(KIND, str(row.id), reason="revised")
    db.commit()

    assert orchestrator._active_tracker(config, str(row.id)) is None
    assert orchestrator.active_trackers_for_source(KIND, str(row.id)) == []
    # Still readable as history.
    assert len(orchestrator.trackers_for_source(KIND, str(row.id))) == 1


def test_a_voided_stage_is_never_escalated(db):
    _c, _token, row, tracker = _setup(db)
    tracker.due_at = datetime.utcnow() - timedelta(days=2)
    tracker.due_at_resolution = datetime.utcnow() - timedelta(days=2)
    db.commit()

    orchestrator = FormSLAOrchestrator(db)
    assert orchestrator.scan_overdue_and_escalate()["scanned"] == 1

    orchestrator.void_active_for_source(KIND, str(row.id), reason="revised")
    db.commit()
    assert orchestrator.scan_overdue_and_escalate()["scanned"] == 0


def test_voided_stages_are_out_of_the_dashboard_numbers(db):
    """UAC F4a: leaving them in inflates the breach count on every revision."""
    from app.services import sla_kpi_service

    _c, _token, row, tracker = _setup(db)
    # An overdue, never-responded stage is a breach on the response clock.
    tracker.due_at = datetime.utcnow() - timedelta(days=2)
    tracker.due_at_resolution = datetime.utcnow() - timedelta(days=2)
    db.commit()

    before = sla_kpi_service.kpi_summary(db, scope="form")
    assert before["opened"] == 1
    assert before["response_breach"] == 1

    FormSLAOrchestrator(db).void_active_for_source(KIND, str(row.id), reason="revised")
    db.commit()

    after = sla_kpi_service.kpi_summary(db, scope="form")
    assert after["opened"] == 0
    assert after["response_breach"] == 0
    assert sla_kpi_service.kpi_tasks(db, scope="form")["total"] == 0
    assert sla_kpi_service.kpi_leaderboard(db, scope="form") == []
    # The reason code is what makes the exclusion explainable rather than invisible.
    db.expire_all()
    assert (
        db.query(ConversationSLATracking).filter_by(id=tracker.id).one().void_reason
        == "revised_by_contact"
    )


def test_a_pending_takeover_on_a_voided_stage_is_voided(db):
    """UAC F2, mirroring the escalation path."""
    from app.services.sla_takeover_service import SlaTakeoverService

    _c, token, row, tracker = _setup(db)
    with patch.object(SlaTakeoverService, "void_for_tracking") as void_spy:
        _revise(db, token, row)
    void_spy.assert_called_once_with(str(tracker.id), "revised_by_contact")


# ------------------------------------------------------------------ the restart


def test_the_chain_restarts_at_stage_one(db):
    """UAC F3: the revision emits the chain's own submit event, so stage 1 spawns
    through the normal assignment path rather than a bespoke one."""
    _c, token, row, _tracker = _setup(db)
    policy_id = seed_policy(db)
    seed_stage_config(
        db,
        KIND,
        policy_id,
        stage_code="project_sales",
        team_set_code="project_sales",
        start_event="submit",
    )
    with patch("app.services.form_sla_service.emit_form_event") as emit:
        _revise(db, token, row)
    emit.assert_called_once()
    assert emit.call_args.args[1:4] == (KIND, str(row.id), "submit")


def test_the_restart_stage_can_be_overridden_by_config(db):
    seed_system_settings(db, cap=3)
    seed_config(db, KIND, restart_stage_code="purchasing")
    contact = seed_contact(db)
    row = seed_entity(db, KIND, contact)
    policy_id = seed_policy(db)
    seed_stage_config(
        db, KIND, policy_id, stage_code="project_sales", team_set_code="project_sales"
    )
    seed_stage_config(
        db,
        KIND,
        policy_id,
        stage_code="purchasing",
        team_set_code="purchasing",
        start_event="project_sales_approve",
    )

    with patch("app.services.form_sla_service.emit_form_event") as emit:
        _revise(db, seed_token(contact), row)

    assert emit.call_args.args[3] == "project_sales_approve"
    db.expire_all()
    from app.models.procurement import StockInquiry

    assert db.query(StockInquiry).filter_by(id=row.id).one().status == "pending_purchasing"


# ------------------------------------------------------- what history records
# A revision voids EVERY open stage and tells EVERY handler, so the revision row
# has to name every one of them. Naming only the newest under-reports a
# cancellation two people were just told about.


def _two_open_stages(db):
    """One entity with two stages open at once, newest = purchasing.

    A purchase request really can sit with project sales and approval open
    together, which is the case the single-stage record loses.
    """
    seed_system_settings(db, cap=3)
    seed_config(db, KIND)
    contact = seed_contact(db)
    row = seed_entity(db, KIND, contact)
    policy_id = seed_policy(db)
    older_user = seed_user(db, name="Project Sales Priya")
    newer_user = seed_user(db, name="Purchasing Pat")

    older = seed_tracker(
        db,
        KIND,
        str(row.id),
        policy_id,
        team_set_code="project_sales",
        assigned_to_id=older_user.id,
    )
    newer = seed_tracker(
        db,
        KIND,
        str(row.id),
        policy_id,
        team_set_code="purchasing",
        assigned_to_id=newer_user.id,
    )
    # seed_tracker stamps every row with the same initiated_at, so pin the order
    # the "newest stage" assertions depend on.
    older.initiated_at = datetime.utcnow() - timedelta(hours=6)
    newer.initiated_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()

    # The stage code lives on the config, keyed by (type, team_set_code).
    seed_stage_config(
        db, KIND, policy_id, stage_code="project_sales", team_set_code="project_sales"
    )
    seed_stage_config(
        db,
        KIND,
        policy_id,
        stage_code="purchasing",
        team_set_code="purchasing",
        start_event="project_sales_approve",
    )
    return contact, seed_token(contact), row, (older, older_user), (newer, newer_user)


def test_every_voided_stage_is_recorded_on_the_revision_row(db):
    """The revision row must account for both cancellations, not just one."""
    from app.models.portal import PortalFormRevision

    _c, token, row, (_older, older_user), (_newer, newer_user) = _two_open_stages(db)

    _revise(db, token, row, reason="Both quantities were wrong")

    revision = (
        db.query(PortalFormRevision)
        .filter(
            PortalFormRevision.source_entity_id == str(row.id),
            PortalFormRevision.kind == "revision",
        )
        .one()
    )
    # Newest first, matching the order the stages were voided in.
    assert revision.voided_stages_json == [
        {"stage_code": "purchasing", "assignee_user_id": str(newer_user.id)},
        {"stage_code": "project_sales", "assignee_user_id": str(older_user.id)},
    ]
    # The scalar columns keep the newest stage, so every existing reader of the
    # common single-stage case is unchanged.
    assert revision.voided_stage_code == "purchasing"
    assert revision.voided_assignee_user_id == str(newer_user.id)


def test_a_single_open_stage_still_records_the_scalar_columns(db):
    """The common case: one stage, and the list is a list of one."""
    from app.models.portal import PortalFormRevision

    handler = seed_user(db, name="Solo Sam")
    _c, token, row, _tracker = _setup(db, assigned_to_id=handler.id)
    _revise(db, token, row)

    revision = (
        db.query(PortalFormRevision)
        .filter(
            PortalFormRevision.source_entity_id == str(row.id),
            PortalFormRevision.kind == "revision",
        )
        .one()
    )
    assert revision.voided_stage_code == "purchasing"
    assert revision.voided_assignee_user_id == str(handler.id)
    assert revision.voided_stages_json == [
        {"stage_code": "purchasing", "assignee_user_id": str(handler.id)}
    ]


def test_a_revision_with_no_open_stage_records_nothing_to_void(db):
    from app.models.portal import PortalFormRevision

    seed_system_settings(db, cap=3)
    seed_config(db, KIND)
    contact = seed_contact(db)
    row = seed_entity(db, KIND, contact)

    _revise(db, seed_token(contact), row)

    revision = (
        db.query(PortalFormRevision)
        .filter(
            PortalFormRevision.source_entity_id == str(row.id),
            PortalFormRevision.kind == "revision",
        )
        .one()
    )
    assert revision.voided_stage_code is None
    assert revision.voided_assignee_user_id is None
    assert revision.voided_stages_json is None


def test_history_reads_back_every_voided_stage_with_its_handler(db):
    """UAC H3: the office Revisions tab shows which stage was voided and who was
    working it - for each stage, since more than one can stop at once."""
    _c, token, row, (_older, older_user), (_newer, newer_user) = _two_open_stages(db)
    _revise(db, token, row)

    entries = PortalRevisionService(db).list_revisions(KIND, str(row.id))
    revision = [e for e in entries if e["kind"] == "revision"][0]

    assert revision["voided_stages"] == [
        {"stage_code": "purchasing", "assignee_name": newer_user.name},
        {"stage_code": "project_sales", "assignee_name": older_user.name},
    ]
    # The scalar fields the timeline already renders keep their meaning.
    assert revision["voided_stage_code"] == "purchasing"
    assert revision["voided_assignee_name"] == newer_user.name


def test_both_handlers_are_told_and_both_stages_are_voided(db):
    """The record and the notification fan-out have to agree about the same set."""
    _c, token, row, (older, older_user), (newer, newer_user) = _two_open_stages(db)
    _revise(db, token, row)

    db.expire_all()
    for tracker in (older, newer):
        assert (
            db.query(ConversationSLATracking).filter_by(id=tracker.id).one().voided_at
            is not None
        )
    told = {
        n.user_id
        for n in db.query(Notification).filter(Notification.type == "form_revised").all()
    }
    assert told == {older_user.id, newer_user.id}


# ------------------------------------------------------------- the notification


def test_the_voided_assignee_is_told_why_their_work_stopped(db):
    """UAC F6/F6a: revision-specific copy, never recycled assignment copy."""
    handler = seed_user(db, name="Purchasing Pat")
    _c, token, row, tracker = _setup(db, assigned_to_id=handler.id)
    _revise(db, token, row, reason="Customer changed the quantity")

    notification = (
        db.query(Notification)
        .filter(Notification.user_id == handler.id, Notification.type == "form_revised")
        .one()
    )
    assert "Revision 1" in notification.title
    # The document number carries the revision wherever it appears (UAC N1).
    assert f"{row.inquiry_number}-R1" in notification.body
    assert "Customer changed the quantity" in notification.body
    assert "stop work" in notification.body.lower()
    # UAC F7: the in-system detail page, never the public ?token= view.
    assert notification.data["link"] == f"/procurement-management/stock-inquiries/{row.id}"
    assert "token=" not in notification.body


def test_the_handling_lock_holder_is_told_too(db):
    assignee = seed_user(db, name="Assigned Alice")
    holder = seed_user(db, name="Holding Hank")
    _c, token, row, _tracker = _setup(
        db, assigned_to_id=assignee.id, handled_by_id=holder.id
    )
    _revise(db, token, row)

    told = {
        n.user_id
        for n in db.query(Notification).filter(Notification.type == "form_revised").all()
    }
    assert told == {assignee.id, holder.id}


def test_an_unassigned_stage_falls_back_to_the_stage_team(db):
    """UAC FT1: a revision must never fail silently into nobody's inbox."""
    member = seed_user(db, name="Team Member")
    agent = seed_agent(db, code="marker_agent")
    _c, token, row, _tracker = _setup(
        db, tracker_kwargs={"agent_id": agent.id, "team_set_code": "purchasing"}
    )

    with patch(
        "app.services.user_service.AccessAgentService.resolve_team_with_tier_fallback",
        return_value=("team-1", 1),
    ), patch.object(
        PortalRevisionService, "_stage_team_members", return_value=[member.id]
    ) as team_spy:
        _revise(db, token, row)

    team_spy.assert_called_once()
    assert (
        db.query(Notification)
        .filter(Notification.user_id == member.id, Notification.type == "form_revised")
        .count()
        == 1
    )


def test_a_raising_notifier_does_not_undo_a_committed_revision(db):
    """UAC F5: post-commit side effects are best-effort. A notify failure must never
    turn a revision that actually committed into a 500."""
    handler = seed_user(db)
    _c, token, row, tracker = _setup(db, assigned_to_id=handler.id)

    from app.services.notification_service import NotificationService

    with patch.object(
        NotificationService, "create_with_channel_preferences", side_effect=RuntimeError("smtp down")
    ):
        result = _revise(db, token, row)

    assert result["revision_no"] == 1
    db.expire_all()
    from app.models.procurement import StockInquiry

    assert db.query(StockInquiry).filter_by(id=row.id).one().revision_no == 1
    assert db.query(ConversationSLATracking).filter_by(id=tracker.id).one().voided_at is not None


def test_a_failing_restart_does_not_undo_a_committed_revision(db):
    _c, token, row, _tracker = _setup(db)
    with patch(
        "app.services.form_sla_service.emit_form_event", side_effect=RuntimeError("boom")
    ):
        result = _revise(db, token, row)
    assert result["revision_no"] == 1
