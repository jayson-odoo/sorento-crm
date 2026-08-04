"""Generic skip-the-next-stage engine (UAC-form-sla-skip-stage.md, group A).

A form-SLA stage may declare itself skippable via `skip_event`. Taking the skip
resolves the current stage, prevents `next_config_id` from spawning, and writes the
entity's terminal status through a per-entity adapter.

The engine needs no changes to `_resolve_for_active` to achieve the "don't advance"
half - a skip event that is in `resolve_event` but NOT in `advance_on_event` already
resolves without advancing. These tests pin the plumbing around that fact.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.sla import FormSLAConfig


SKIP_MARKER = "ZZTSKIP"


@pytest.fixture(autouse=True)
def _clean_state():
    """Scope every delete to this test's own marker rows - the dev DB holds real data."""
    with engine.connect() as conn:
        try:
            _sweep(conn)
            conn.commit()
        except Exception:
            conn.rollback()
    yield
    with engine.connect() as conn:
        try:
            _sweep(conn)
            conn.commit()
        except Exception:
            conn.rollback()


def _sweep(conn) -> None:
    """Remove this file's own rows, children first. Scoped to the marker: the dev DB
    is a copy of production and an unscoped DELETE here would destroy real data."""
    conn.execute(
        text(
            "DELETE FROM conversation_sla_tracking WHERE team_set_code LIKE :p "
            "OR source_entity_id IN (SELECT id FROM complaints WHERE complaint_number LIKE :p)"
        ),
        {"p": f"{SKIP_MARKER}%"},
    )
    conn.execute(text("DELETE FROM complaints WHERE complaint_number LIKE :p"), {"p": f"{SKIP_MARKER}%"})
    conn.execute(text("DELETE FROM form_sla_configs WHERE stage_code LIKE :p"), {"p": f"{SKIP_MARKER}%"})
    conn.execute(text("DELETE FROM sla_policies WHERE code LIKE :p"), {"p": f"{SKIP_MARKER}%"})


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _policy_id(db: Session) -> str:
    """Create this test's own SLA policy and return its id.

    Never borrow an arbitrary existing row: CI runs against a freshly migrated
    database with NO seed data, so `SELECT id FROM sla_policies LIMIT 1` is None
    there and every dependent insert dies on the NOT NULL policy_id.
    """
    from app.models.sla import SLAPolicy

    code = f"{SKIP_MARKER}-{uuid.uuid4().hex[:8]}"
    policy = SLAPolicy(id=str(uuid.uuid4()), code=code, name="Skip test policy", is_active=True)
    db.add(policy)
    db.commit()
    return str(policy.id)


# --------------------------------------------------------------------------- #
# A1 - config declares a skip
# --------------------------------------------------------------------------- #

def test_a1_config_carries_skip_columns(db: Session) -> None:
    """The three skip columns exist and round-trip."""
    policy_id = _policy_id(db)
    cfg = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type="complaint",
        stage_code=f"{SKIP_MARKER}-main",
        policy_id=policy_id,
        agent_code="complaint",
        start_event="submit",
        resolve_event="approved,rejected,settled_on_site",
        advance_on_event="approved",
        skip_event="settled_on_site",
        skip_terminal_status="settled_on_site",
        skip_action_label="Settled on site",
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    assert cfg.skip_event == "settled_on_site"
    assert cfg.skip_terminal_status == "settled_on_site"
    assert cfg.skip_action_label == "Settled on site"


def test_a1_skip_columns_default_null(db: Session) -> None:
    """A stage that declares no skip is unskippable and behaves exactly as today."""
    policy_id = _policy_id(db)
    cfg = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type="complaint",
        stage_code=f"{SKIP_MARKER}-cs",
        policy_id=policy_id,
        agent_code="complaint",
        start_event="approved",
        resolve_event="resolved",
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    assert cfg.skip_event is None
    assert cfg.skip_terminal_status is None
    assert cfg.skip_action_label is None


# --------------------------------------------------------------------------- #
# A2 - adapter registry
# --------------------------------------------------------------------------- #

def test_a2_complaint_adapter_registered() -> None:
    from app.services.form_skip_registry import get_skip_adapter

    adapter = get_skip_adapter("complaint")
    assert adapter is not None
    assert adapter.permission_slug == "complaint_management.complaints.settle_on_site"
    assert "responded" in adapter.allowed_source_statuses
    # Consequence copy is domain truth and lives in the adapter, never in config.
    assert adapter.consequence_copy
    assert adapter.automation_event == "complaint_settled_on_site"


def test_a2_unknown_type_has_no_adapter() -> None:
    from app.services.form_skip_registry import get_skip_adapter

    assert get_skip_adapter("purchase_request") is None
    assert get_skip_adapter("not_a_real_type") is None


# --------------------------------------------------------------------------- #
# A4 - guards refuse before any write
# --------------------------------------------------------------------------- #

def test_a4_unknown_entity_type_raises_422(db: Session) -> None:
    from app.services.error_handler import AppException
    from app.services.form_skip_service import FormSkipService

    with pytest.raises(AppException) as exc:
        FormSkipService(db).skip(
            "not_a_real_type", str(uuid.uuid4()), actor_user_id="u1", check_permission=False
        )
    # 400 via handle_validation_error - same code decide_complaint returns for its
    # wrong-status guard, so both actions on the page fail alike. The ROUTE returns 422
    # for an unknown entity type before the service is ever reached.
    assert exc.value.status_code == 400


def test_a4_no_active_tracker_raises_422(db: Session) -> None:
    """A complaint with no active form-SLA stage cannot be skipped."""
    from app.services.error_handler import AppException
    from app.services.form_skip_service import FormSkipService

    svc = FormSkipService(db)
    with patch.object(svc, "_active_skippable_stage", return_value=(None, None)):
        with pytest.raises(AppException) as exc:
            svc.skip(
                "complaint", str(uuid.uuid4()), actor_user_id="u1", check_permission=False
            )
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# A7 - post-commit side effects are best-effort
# --------------------------------------------------------------------------- #

def test_a7_notify_failure_does_not_raise() -> None:
    """A side effect that runs AFTER the status commits must catch and warn.

    Raising here would 500 an operation that already succeeded, and the caller's
    retry takes the wrong-status guard - which never backfills the missed effect.
    """
    from app.services.form_skip_service import FormSkipService

    svc = FormSkipService(MagicMock())
    entity = SimpleNamespace(id="c1", status="settled_on_site")
    adapter = SimpleNamespace(
        source_entity_type="complaint",
        notify=MagicMock(side_effect=RuntimeError("respond.io down")),
        automation_event=None,
        build_automation_context=None,
    )
    # Must not propagate.
    svc._run_side_effects(adapter, entity, note=None, skip_event="settled_on_site",
                          actor_user_id="u1")


def test_a7_automation_failure_does_not_raise() -> None:
    from app.services.form_skip_service import FormSkipService

    svc = FormSkipService(MagicMock())
    entity = SimpleNamespace(id="c1", status="settled_on_site")
    adapter = SimpleNamespace(
        source_entity_type="complaint",
        notify=None,
        automation_event="complaint_settled_on_site",
        build_automation_context=MagicMock(side_effect=RuntimeError("boom")),
    )
    svc._run_side_effects(adapter, entity, note=None, skip_event="settled_on_site",
                          actor_user_id="u1")


# --------------------------------------------------------------------------- #
# A8 - tracker payload exposes the skip fields
# --------------------------------------------------------------------------- #

def test_a8_serializer_carries_skip_fields(db: Session) -> None:
    """The FE reads skip capability off the tracker query it already runs.

    The stage config is resolved by (source_entity_type, team_set_code) - the pair
    that uniquely identifies a form-SLA stage.
    """
    from app.api.v1.sla.form_sla_tracking import _serialize

    policy_id = _policy_id(db)
    cfg = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type="complaint",
        stage_code=f"{SKIP_MARKER}-stage",
        policy_id=policy_id,
        agent_code="complaint",
        team_set_code=f"{SKIP_MARKER}-team",
        start_event="submit",
        resolve_event="approved,rejected,settled_on_site",
        advance_on_event="approved",
        skip_event="settled_on_site",
        skip_terminal_status="settled_on_site",
        skip_action_label="Settled on site",
    )
    db.add(cfg)
    db.commit()

    tracker = SimpleNamespace(
        id=uuid.uuid4(),
        current_tier=1,
        due_at=None,
        due_at_resolution=None,
        is_resolved=False,
        assigned_to_id=None,
        source_entity_type="complaint",
        source_entity_id=str(uuid.uuid4()),
        team_set_code=f"{SKIP_MARKER}-team",
        escalation_reason=None,
        escalated_at=None,
        handled_by_id=None,
        handled_at=None,
    )
    out = _serialize(db, tracker, viewer_user_id=None, flag_enabled=False, viewer_is_admin=False)
    assert out["skip_event"] == "settled_on_site"
    assert out["skip_action_label"] == "Settled on site"
    # No viewer -> cannot skip. Permission is per-entity and resolved server-side.
    assert out["can_skip"] is False


def test_a8_unskippable_stage_reports_no_skip(db: Session) -> None:
    from app.api.v1.sla.form_sla_tracking import _serialize

    policy_id = _policy_id(db)
    cfg = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type="complaint",
        stage_code=f"{SKIP_MARKER}-nocs",
        policy_id=policy_id,
        agent_code="complaint",
        team_set_code=f"{SKIP_MARKER}-noteam",
        start_event="approved",
        resolve_event="resolved",
    )
    db.add(cfg)
    db.commit()

    tracker = SimpleNamespace(
        id=uuid.uuid4(),
        current_tier=1,
        due_at=None,
        due_at_resolution=None,
        is_resolved=False,
        assigned_to_id=None,
        source_entity_type="complaint",
        source_entity_id=str(uuid.uuid4()),
        team_set_code=f"{SKIP_MARKER}-noteam",
        escalation_reason=None,
        escalated_at=None,
        handled_by_id=None,
        handled_at=None,
    )
    out = _serialize(db, tracker, viewer_user_id=None, flag_enabled=False, viewer_is_admin=False)
    assert out["skip_event"] is None
    assert out["can_skip"] is False


# --------------------------------------------------------------------------- #
# A3 - the service and the tracker endpoint must agree on WHICH stage is skipped
# --------------------------------------------------------------------------- #

def test_a3_service_picks_the_same_stage_the_frontend_offered(db: Session) -> None:
    """Form SLA is multi-active, so an entity can carry several unresolved stages.

    GET /form-sla-tracking orders by `initiated_at DESC` and the frontend offers the
    skip for the first unresolved row of that list. If the service ordered differently
    it would close a DIFFERENT stage from the one whose label the user clicked - and
    silently, because both calls would return 200.
    """
    from datetime import datetime, timedelta

    from app.models.complaints import Complaint
    from app.models.sla import ConversationSLATracking
    from app.services.form_skip_service import FormSkipService

    policy_id = _policy_id(db)
    team = f"{SKIP_MARKER}-multi"
    db.add(
        FormSLAConfig(
            id=str(uuid.uuid4()),
            source_entity_type="complaint",
            stage_code=f"{SKIP_MARKER}-multi-stage",
            policy_id=policy_id,
            agent_code="complaint",
            team_set_code=team,
            start_event="submit",
            resolve_event="approved,rejected,settled_on_site",
            advance_on_event="approved",
            skip_event="settled_on_site",
            skip_terminal_status="settled_on_site",
            skip_action_label="Settled on site",
        )
    )
    complaint = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{SKIP_MARKER}-{uuid.uuid4().hex[:6]}",
        status="responded",
        customer_name="ACME",
    )
    db.add(complaint)
    db.commit()

    now = datetime.utcnow()

    def _tracker(hours_ago: int) -> ConversationSLATracking:
        return ConversationSLATracking(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            current_tier=1,
            due_at=now + timedelta(days=1),
            is_resolved=False,
            initiated_at=now - timedelta(hours=hours_ago),
            source_entity_type="complaint",
            source_entity_id=str(complaint.id),
            team_set_code=team,
        )

    older, newer = _tracker(5), _tracker(1)
    db.add_all([older, newer])
    db.commit()

    # What the frontend sees (same query + ordering as the GET route).
    offered = (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == "complaint",
            ConversationSLATracking.source_entity_id == str(complaint.id),
            ConversationSLATracking.is_resolved.is_(False),
        )
        .order_by(ConversationSLATracking.initiated_at.desc())
        .first()
    )
    chosen, config = FormSkipService(db)._active_skippable_stage("complaint", str(complaint.id))

    assert config is not None
    assert str(chosen.id) == str(offered.id) == str(newer.id)
