"""Regression (SI26-0123): a form SLA tracker must still resolve after its stage's
SLA policy is changed *after* the tracker was created.

Bug: `_active_tracker` matched the live tracker on `policy_id == config.policy_id`.
`policy_id` is a snapshot the tracker stored at create time, so editing the stage's
policy afterward orphaned the live tracker — the resolve event (e.g.
`project_sales_approve`, fired when status goes pending_project_sales ->
pending_purchasing) could no longer find it, and it stuck at Escalated.

Fix: stage identity is (source_entity_type, team_set_code) — NOT policy_id. Drop the
policy_id predicate so the running tracker resolves regardless of a later policy edit.

Run: pytest tests/test_form_sla_policy_change_midway_resolve.py -v
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.models.access import AccessAgent, RespondContact
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.services.form_sla_service import FormSLAOrchestrator, _utc_naive_now
from tests._pg_fixture import blank_session

SOURCE_TYPE = "stock_inquiry"
STAGE = "project_sales"
RESOLVE_EVENT = "project_sales_approve"


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _policy(db, code: str) -> str:
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code=code, name=code.title()))
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=pid,
            tier_level=1,
            tier_name="Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    return pid


def _seed(db, *, tracker_policy_id: str, config_policy_id: str) -> str:
    """One live, escalated project_sales tracker created under `tracker_policy_id`;
    its stage config now points at `config_policy_id` (the mid-way policy change)."""
    source_id = str(uuid.uuid4())
    now = _utc_naive_now()
    db.add(
        ConversationSLATracking(
            id=str(uuid.uuid4()),
            policy_id=tracker_policy_id,
            current_tier=3,
            initiated_at=now - timedelta(days=3),
            current_tier_started_at=now - timedelta(days=1),
            due_at=now - timedelta(days=1),
            due_at_resolution=now - timedelta(days=1),
            escalated_at=now - timedelta(days=1),
            is_responded=False,
            is_resolved=False,
            source_entity_type=SOURCE_TYPE,
            source_entity_id=source_id,
            team_set_code=STAGE,
        )
    )
    db.add(
        FormSLAConfig(
            id=str(uuid.uuid4()),
            source_entity_type=SOURCE_TYPE,
            stage_code=STAGE,
            policy_id=config_policy_id,  # <-- changed after the tracker was created
            agent_code="lead_time_enquiries",
            team_set_code=STAGE,
            start_event="submit",
            resolve_event=RESOLVE_EVENT,
            is_active=True,
        )
    )
    db.commit()
    return source_id


def _resolve(db, source_id: str):
    orch = FormSLAOrchestrator(db)
    # Resolve enqueues a Respond.io conversation close on the worker; stub it out.
    with patch("app.services.queue_service.enqueue_job"):
        orch.emit_event(SOURCE_TYPE, source_id, RESOLVE_EVENT)
    db.expire_all()
    return (
        db.query(ConversationSLATracking)
        .filter(ConversationSLATracking.source_entity_id == source_id)
        .one()
    )


def test_resolves_after_policy_changed_midway(db):
    """The exact SI26-0123 scenario: tracker made under NORMAL, stage repointed to
    STOCK_INQUIRIES, then resolved -> tracker MUST be captured as resolved."""
    normal = _policy(db, "NORMAL")
    stock = _policy(db, "STOCK_INQUIRIES")
    source_id = _seed(db, tracker_policy_id=normal, config_policy_id=stock)

    tracker = _resolve(db, source_id)

    assert tracker.is_resolved is True, "policy changed mid-way orphaned the tracker"
    assert tracker.is_responded is True  # resolve implies responded
    assert tracker.resolved_at is not None


def test_resolves_when_policy_unchanged(db):
    """Control: same policy on tracker and config still resolves (no regression)."""
    normal = _policy(db, "NORMAL")
    source_id = _seed(db, tracker_policy_id=normal, config_policy_id=normal)

    tracker = _resolve(db, source_id)

    assert tracker.is_resolved is True
