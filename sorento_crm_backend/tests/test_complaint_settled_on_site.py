"""Complaint adapter for the skip engine - "Settled on site" (UAC group B).

The technician fixed the issue during the site visit, so the complaint is terminal
with NO customer-service stage and NO replacement delivery order. This is the third
technical-team outcome beside Approve (needs replacement -> CS) and Reject (not a
product issue).

Two tests here are load-bearing:
  * B3 - the `main` tracker resolves AND no `customer_service` tracker is created.
    That is the entire point of the feature.
  * B6 - the DO auto-linker must ignore a settled complaint. `settled_on_site` is
    absent from LINKABLE_STATUSES, so a DO naming it never links and the reconciler
    never reverts it into `processed_by_cs` - the stage we deliberately skipped.
"""
from __future__ import annotations

import uuid
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.complaints import Complaint


MARKER = "CMPSOS"


@pytest.fixture(autouse=True)
def _clean_state():
    """Delete only this test's own rows - the dev DB is a copy of production."""
    for _ in range(2):
        with engine.connect() as conn:
            try:
                conn.execute(
                    text(
                        "DELETE FROM conversation_sla_tracking WHERE source_entity_id IN "
                        "(SELECT id FROM complaints WHERE complaint_number LIKE :p)"
                    ),
                    {"p": f"{MARKER}-%"},
                )
                conn.execute(
                    text("DELETE FROM complaints WHERE complaint_number LIKE :p"),
                    {"p": f"{MARKER}-%"},
                )
                conn.commit()
            except Exception:
                conn.rollback()
        yield
        return


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _seed(db: Session, status: str = "responded", *, with_tracker: bool = True) -> Complaint:
    """A complaint plus, by default, an ACTIVE `main` stage tracker.

    The tracker matters: a skip is a way of CLOSING a live stage, so without one the
    engine correctly refuses. `team_set_code='complaint'` is what binds the tracker to
    the `main` config - a form-SLA stage is identified by
    (source_entity_type, team_set_code).
    """
    from datetime import datetime, timedelta

    from app.models.sla import ConversationSLATracking

    c = Complaint(
        id=str(uuid.uuid4()),
        complaint_number=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        status=status,
        customer_name="ACME",
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    if with_tracker:
        policy_id = db.execute(
            text(
                "SELECT policy_id FROM form_sla_configs "
                "WHERE source_entity_type='complaint' AND stage_code='main'"
            )
        ).scalar()
        db.add(
            ConversationSLATracking(
                id=str(uuid.uuid4()),
                policy_id=policy_id,
                current_tier=1,
                due_at=datetime.utcnow() + timedelta(days=1),
                is_resolved=False,
                source_entity_type="complaint",
                source_entity_id=str(c.id),
                team_set_code="complaint",
            )
        )
        db.commit()
    return c


def _skip(db: Session, complaint_id: str, **kw):
    """Exercise the skip with the permission gate bypassed.

    The gate is real and runs FIRST - it gets its own test below. Every other test
    here targets a different guard, so seeding a role graph for each would test the
    permission system over and over instead of the thing under test.
    """
    from app.services.form_skip_service import FormSkipService

    kw.setdefault("check_permission", False)
    return FormSkipService(db).skip("complaint", complaint_id, **kw)


def test_a5_permission_denied_before_any_write(db: Session) -> None:
    """403 before the status moves - a denied caller must not mutate anything."""
    from app.services.error_handler import AppException
    from app.services.form_skip_service import FormSkipService

    c = _seed(db, "responded")
    with pytest.raises(AppException) as exc:
        FormSkipService(db).skip("complaint", c.id, actor_user_id="nobody-has-this-id")
    assert exc.value.status_code == 403
    db.rollback()
    refetched = db.query(Complaint).filter(Complaint.id == c.id).first()
    assert refetched.status == "responded"


def test_a5_anonymous_caller_denied(db: Session) -> None:
    from app.services.error_handler import AppException
    from app.services.form_skip_service import FormSkipService

    c = _seed(db, "responded")
    with pytest.raises(AppException) as exc:
        FormSkipService(db).skip("complaint", c.id, actor_user_id=None)
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------- #
# B1 / B2 - status transition and its guard
# --------------------------------------------------------------------------- #

def test_b1_responded_complaint_becomes_settled_on_site(db: Session) -> None:
    c = _seed(db, "responded")
    with patch("app.services.form_skip_service.FormSkipService._run_side_effects"), \
         patch("app.services.form_sla_service.emit_form_event"):
        out = _skip(db, c.id, actor_user_id="u-tech")
    db.refresh(c)
    assert c.status == "settled_on_site"
    assert c.resolved_at is not None
    assert c.resolved_by == "u-tech"
    assert out["status"] == "settled_on_site"


def test_b2_wrong_source_status_refused(db: Session) -> None:
    """Only a `responded` complaint can be settled - mirrors _DECIDE_ALLOWED_FROM_STATUSES."""
    from app.services.error_handler import AppException

    c = _seed(db, "approved")
    with pytest.raises(AppException) as exc:
        _skip(db, c.id, actor_user_id="u-tech")
    # Matches decide_complaint's guard code exactly (handle_validation_error -> 400).
    assert exc.value.status_code == 400
    db.rollback()
    refetched = db.query(Complaint).filter(Complaint.id == c.id).first()
    assert refetched.status == "approved", "a refused skip must not move the status"


def test_b2_already_settled_is_refused(db: Session) -> None:
    from app.services.error_handler import AppException

    c = _seed(db, "settled_on_site")
    with pytest.raises(AppException) as exc:
        _skip(db, c.id, actor_user_id="u-tech")
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# B3 - THE core assertion: main resolves, customer service never spawns
# --------------------------------------------------------------------------- #

def test_b3_emits_skip_event_not_approved(db: Session) -> None:
    """The skip must emit `settled_on_site`, never `approved`.

    `complaint.main` has advance_on_event='approved', so emitting 'approved' here
    would resolve the stage AND spawn customer service - the exact bug this feature
    exists to avoid. The CS config's own start_event='approved' would fire too.
    """
    c = _seed(db, "responded")
    with patch("app.services.form_skip_service.emit_form_event") as emit, \
         patch("app.services.form_skip_service.FormSkipService._notify_and_automate"):
        _skip(db, c.id, actor_user_id="u-tech")
    assert emit.called
    event_name = emit.call_args[0][3] if len(emit.call_args[0]) > 3 else emit.call_args.kwargs.get("event_name")
    assert event_name == "settled_on_site"
    assert event_name != "approved"


def test_b3_no_customer_service_tracker_after_skip(db: Session) -> None:
    """End-to-end through the real orchestrator: no CS stage row is created."""
    from app.models.sla import ConversationSLATracking

    c = _seed(db, "responded")
    with patch("app.services.form_skip_service.FormSkipService._notify_and_automate"):
        _skip(db, c.id, actor_user_id="u-tech")
    db.commit()

    cs_rows = (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == "complaint",
            ConversationSLATracking.source_entity_id == str(c.id),
            ConversationSLATracking.team_set_code == "customer_service",
        )
        .all()
    )
    assert cs_rows == [], "customer service must never be assigned on a settled complaint"


# --------------------------------------------------------------------------- #
# B5 - automation event
# --------------------------------------------------------------------------- #

def test_b5_dispatches_settled_automation_with_correct_status(db: Session) -> None:
    """A new event, not a reuse of complaint_approved.

    Reusing it would emit "status": "approved" for a complaint that is not approved,
    poisoning a field n8n/email automations branch on.
    """
    c = _seed(db, "responded")
    with patch("app.services.form_skip_service.emit_form_event"), \
         patch("app.services.automation_service.AutomationService.dispatch_event") as disp:
        _skip(db, c.id, actor_user_id="u-tech")
    assert disp.called
    assert disp.call_args[0][0] == "complaint_settled_on_site"
    ctx = disp.call_args.kwargs["context"]
    assert ctx["complaint"]["status"] == "settled_on_site"


def test_b5_automation_trigger_is_registered() -> None:
    from app.services import automation_triggers

    types = {spec.type for spec in automation_triggers.list_specs()} \
        if hasattr(automation_triggers, "list_specs") else set()
    if not types:
        # Fall back to the module-level registry mapping.
        types = set(getattr(automation_triggers, "_REGISTRY", {}).keys())
    assert "complaint_settled_on_site" in types


# --------------------------------------------------------------------------- #
# B6 - the DO auto-linker must ignore a settled complaint (regression guard)
# --------------------------------------------------------------------------- #

def test_b6_settled_status_is_not_linkable() -> None:
    from app.services.complaint_fulfilment_service import LINKABLE_STATUSES

    assert "settled_on_site" not in LINKABLE_STATUSES
    # The two genuinely CS-driven states stay linkable.
    assert "processed_by_cs" in LINKABLE_STATUSES
    assert "fulfilled" in LINKABLE_STATUSES


def test_b6_reconciler_never_reverts_a_settled_complaint(db: Session) -> None:
    """A DO naming a settled complaint must not drag it into processed_by_cs.

    The reconciler's `fulfilled + not all_delivered -> processed_by_cs` branch is
    keyed on `fulfilled`; a settled complaint holds a different status precisely so
    that branch cannot reach it.
    """
    from app.services.complaint_fulfilment_service import ComplaintFulfilmentService

    c = _seed(db, "settled_on_site")
    svc = ComplaintFulfilmentService(db)
    order = MagicMock()
    order.id = str(uuid.uuid4())
    order.order_number = f"{MARKER}-DO"
    order.is_cancelled = False
    order.remarks_cs = c.complaint_number

    warnings, _ = svc.reconcile_links_and_status(
        [{"order": order, "old_remarks": None}], dry_run=True
    )
    db.refresh(c)
    assert c.status == "settled_on_site"
    # The complaint is named but not linkable, so the caller is told why.
    assert any(c.complaint_number in w for w in warnings)


# --------------------------------------------------------------------------- #
# B7 - recovery path stays open
# --------------------------------------------------------------------------- #

def test_b7_settled_complaint_is_still_voidable() -> None:
    """Void is the recovery when a settle turns out to be wrong.

    `fulfilled` is not void-blocked today; `settled_on_site` matches it. Adding it to
    the blocked list would leave a mis-settled complaint with no way out at all.
    """
    from app.services.complaints_service import ComplaintService

    assert "settled_on_site" not in ComplaintService._VOID_BLOCKED_STATUSES


# --------------------------------------------------------------------------- #
# B8 / B9 - the migrations that make the feature reachable
# --------------------------------------------------------------------------- #

def test_b8_permission_registered() -> None:
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    assert "complaint_management.complaints.settle_on_site" in slugs


def test_b8_permission_granted_to_every_approver_role(db: Session) -> None:
    """A permission granted to nobody is indistinguishable from a broken feature."""
    rows = db.execute(
        text(
            """
            SELECT r.id
            FROM user_role_permissions rp
            JOIN user_roles r ON r.id = rp.role_id
            JOIN user_permissions p ON p.id = rp.permission_id
            WHERE p.slug = :slug
            """
        ),
        {"slug": "complaint_management.complaints.approve"},
    ).fetchall()
    approver_roles = {r[0] for r in rows}

    rows = db.execute(
        text(
            """
            SELECT r.id
            FROM user_role_permissions rp
            JOIN user_roles r ON r.id = rp.role_id
            JOIN user_permissions p ON p.id = rp.permission_id
            WHERE p.slug = :slug
            """
        ),
        {"slug": "complaint_management.complaints.settle_on_site"},
    ).fetchall()
    settle_roles = {r[0] for r in rows}

    assert approver_roles, "no role holds .approve - fixture assumption broken"
    assert approver_roles <= settle_roles, (
        "every role that can approve must also be able to settle on site"
    )


def test_b9_complaint_main_config_accepts_the_skip_event(db: Session) -> None:
    """The live `main` stage resolves on settled_on_site but still advances only on approved."""
    row = db.execute(
        text(
            """
            SELECT resolve_event, advance_on_event, skip_event, skip_action_label
            FROM form_sla_configs
            WHERE source_entity_type = 'complaint' AND stage_code = 'main'
            """
        )
    ).fetchone()
    assert row is not None, "complaint.main stage config missing"
    resolve_event, advance_on_event, skip_event, skip_label = row
    assert "settled_on_site" in (resolve_event or ""), (
        "without this the main tracker never resolves on a skip - the complaint closes "
        "while its SLA clock keeps running and escalating"
    )
    assert (advance_on_event or "").strip() == "approved", (
        "advance_on_event must stay 'approved' - that is what stops CS spawning"
    )
    assert skip_event == "settled_on_site"
    assert skip_label == "Settled on site"


def test_b9_customer_service_stage_is_not_skippable(db: Session) -> None:
    """Only the technical stage may be skipped; CS has no skip of its own."""
    row = db.execute(
        text(
            """
            SELECT skip_event FROM form_sla_configs
            WHERE source_entity_type = 'complaint' AND stage_code = 'customer_service'
            """
        )
    ).fetchone()
    assert row is not None
    assert row[0] is None
