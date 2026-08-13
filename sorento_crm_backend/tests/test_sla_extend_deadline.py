"""SLA "Extend resolution deadline" feature tests (PLAN-sla-extend-deadline).

Covers the 25 UACs from docs/plans/PLAN-sla-extend-deadline.md.

Mix of:
- Real-sqlite service tests (compute_extension, extend_tracking, warnings, event log,
  counters, reminders, escalation-due re-keying, user pref round-trip).
- Mock-based unit tests for the route coroutine gating (403/422) and the
  best-effort next-tier notify path (no-next-tier skip, raise -> still succeed).

Run:
    venv/bin/pytest tests/test_sla_extend_deadline.py -q
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.calendar import PublicHoliday
from app.models.notification import (
    Notification,
    NotificationDelivery,
)
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.services.error_handler import AppException
from app.services.notification_service import NotificationService
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    with blank_session() as s:
        yield s


ASSIGNEE_ID = "6dc131a2-52a4-5183-ac51-f99a2adc2bf8"
def _seed_policy(db, **policy_over) -> str:
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code="NORMAL", name="Normal", **policy_over))
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
    db.commit()
    return pid


def _seed_user(db, uid=ASSIGNEE_ID, **over):
    db.add(User(id=uid, email=f"{uid}@example.com", name=uid, **over))
    db.commit()


def _seed_tracking(
    db,
    policy_id,
    *,
    assigned_to_id=ASSIGNEE_ID,
    is_resolved=False,
    due_res=datetime(2026, 7, 1, 9, 0, 0),  # Wed 2026-07-01 (a working day)
    current_tier=1,
    source_entity_type=None,
    is_responded=True,
    extension_count=0,
    extension_days_total=0,
) -> str:
    tid = str(uuid.uuid4())
    db.add(
        ConversationSLATracking(
            id=tid,
            policy_id=policy_id,
            current_tier=current_tier,
            assigned_to_id=assigned_to_id,
            initiated_at=datetime(2026, 6, 30, 9, 0, 0),
            current_tier_started_at=datetime(2026, 6, 30, 9, 0, 0),
            due_at=datetime(2026, 6, 30, 13, 0, 0),
            due_at_resolution=due_res,
            is_responded=is_responded,
            is_resolved=is_resolved,
            source_entity_type=source_entity_type,
            source_entity_id=str(uuid.uuid4()) if source_entity_type else None,
            extension_count=extension_count,
            extension_days_total=extension_days_total,
        )
    )
    db.commit()
    return tid


def _svc(db):
    return ConversationSLATrackingService(db)


# ---------------------------------------------------------------------------
# UAC-8 / UAC-18 / UAC-21: extend happy path, days mode
# ---------------------------------------------------------------------------
def test_extend_days_mode_skips_weekends_preserves_time_and_bumps_counters(db):
    """UAC-8: +N working days skipping weekends; time-of-day preserved.
    UAC-18: persisted to due_at_resolution. UAC-21: counters bump."""
    _seed_user(db)
    pid = _seed_policy(db)
    # Wed 2026-07-01 09:00 + 3 working days = Mon 2026-07-06 09:00 (skips Sat/Sun).
    tid = _seed_tracking(db, pid, due_res=datetime(2026, 7, 1, 9, 0, 0))

    tracking = _svc(db).extend_tracking(
        tid, ASSIGNEE_ID, days=3, reason="Waiting on supplier"
    )

    assert tracking.due_at_resolution == datetime(2026, 7, 6, 9, 0, 0)
    assert tracking.due_at_resolution.time() == datetime(2026, 7, 1, 9, 0, 0).time()
    assert int(tracking.extension_count) == 1
    assert float(tracking.extension_days_total) == 3.0


def test_extend_days_mode_skips_public_holiday(db):
    """UAC-8: KL public holidays are skipped, not just weekends."""
    _seed_user(db)
    pid = _seed_policy(db)
    # Thu 2026-07-02 is a holiday; base Wed 2026-07-01 09:00 + 2 wd should land
    # Mon 2026-07-06 (skip Thu holiday, Sat, Sun): Wed->Fri(1)->Mon(2).
    db.add(PublicHoliday(date=date(2026, 7, 2), name="Test Holiday"))
    db.commit()
    tid = _seed_tracking(db, pid, due_res=datetime(2026, 7, 1, 9, 0, 0))

    tracking = _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=2, reason="hol")
    assert tracking.due_at_resolution == datetime(2026, 7, 6, 9, 0, 0)


# ---------------------------------------------------------------------------
# UAC-11 / UAC-18: target_date mode
# ---------------------------------------------------------------------------
def test_extend_target_date_mode_derives_working_days(db):
    """UAC-11: date strictly after current due -> derived working-day count,
    current-due time-of-day applied. UAC-18: authoritatively recomputed."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, due_res=datetime(2026, 7, 1, 9, 0, 0))

    # Target Mon 2026-07-06 -> 3 working days from Wed 2026-07-01 (Thu,Fri,Mon).
    new_due, working_days = _svc(db).compute_extension(
        _svc(db).get_tracking(tid, load_event_logs=False), target_date="2026-07-06"
    )
    assert working_days == 3
    assert new_due == datetime(2026, 7, 6, 9, 0, 0)

    tracking = _svc(db).extend_tracking(
        tid, ASSIGNEE_ID, target_date="2026-07-06", reason="date mode"
    )
    assert tracking.due_at_resolution == datetime(2026, 7, 6, 9, 0, 0)
    assert float(tracking.extension_days_total) == 3.0


# ---------------------------------------------------------------------------
# UAC-10: overdue base = the CURRENT due (NOT now). New due = current due + N
# working days, which may itself still be in the past; only strictly-after the
# current due is guaranteed.
# ---------------------------------------------------------------------------
def test_extend_overdue_base_is_current_due_not_now(db):
    """UAC-10 (revised): an overdue row extends relative to its CURRENT due, not now.
    new due = current_due advanced by N working days (skipping weekends/holidays),
    preserving the current due's time-of-day, strictly after the current due."""
    from app.services.calendar_service import CalendarService

    _seed_user(db)
    pid = _seed_policy(db)
    # Fixed overdue date with a known time-of-day (Wed 2024-05-15 09:00 — long past).
    current_due = datetime(2024, 5, 15, 9, 0, 0)
    tid = _seed_tracking(db, pid, due_res=current_due)

    tracking = _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=1, reason="overdue")

    # Expected: current_due advanced by 1 working day, current due's time-of-day kept
    # (mirrors product: add_working_days(base, N) then re-combine with current.time()).
    advanced = CalendarService(db).add_working_days(current_due, 1)
    expected = datetime.combine(advanced.date(), current_due.time())
    assert tracking.due_at_resolution == expected
    # Strictly after the current due — but NOT anchored to today (still in the past).
    assert tracking.due_at_resolution > current_due
    assert tracking.due_at_resolution < datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# UAC-9: days < 1 / 0 / negative rejected
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [0, -1, -5])
def test_extend_days_below_one_rejected(db, bad):
    """UAC-9: 0 / negative days rejected (cannot reduce / no-op).
    The whole extend/preview contract returns 422 for all validation."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid)
    with pytest.raises(AppException) as ei:
        _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=bad, reason="x")
    assert ei.value.status_code == 422


def test_extend_both_days_and_target_date_rejected(db):
    """Both inputs -> rejected (422; single validation status across the contract)."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid)
    with pytest.raises(AppException) as ei:
        _svc(db).extend_tracking(
            tid, ASSIGNEE_ID, days=2, target_date="2026-07-06", reason="x"
        )
    assert ei.value.status_code == 422


def test_extend_neither_days_nor_target_date_rejected(db):
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid)
    with pytest.raises(AppException) as ei:
        _svc(db).extend_tracking(tid, ASSIGNEE_ID, reason="x")
    assert ei.value.status_code == 422


# ---------------------------------------------------------------------------
# UAC-12: target_date on/before current due rejected
# ---------------------------------------------------------------------------
def test_extend_target_date_on_or_before_current_due_rejected(db):
    """UAC-12: a date on/before the current due is rejected (can only extend)."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, due_res=datetime(2026, 7, 10, 9, 0, 0))
    svc = _svc(db)
    tr = svc.get_tracking(tid, load_event_logs=False)
    # Same date as current due. (422; single validation status across the contract)
    with pytest.raises(AppException) as ei:
        svc.compute_extension(tr, target_date="2026-07-10")
    assert ei.value.status_code == 422
    # Earlier date.
    with pytest.raises(AppException) as ei2:
        svc.compute_extension(tr, target_date="2026-07-08")
    assert ei2.value.status_code == 422


# ---------------------------------------------------------------------------
# UAC-17: empty reason rejected (server)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("reason", ["", "   ", None])
def test_extend_empty_reason_rejected(db, reason):
    """UAC-17: reason required (server side)."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid)
    with pytest.raises(AppException) as ei:
        _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=2, reason=reason)
    assert ei.value.status_code == 422


# ---------------------------------------------------------------------------
# UAC-2 / UAC-3 / UAC-4: gating (service-level _assert_can_extend)
# ---------------------------------------------------------------------------
def test_extend_non_assignee_403(db):
    """UAC-2: non-assignee -> 403."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, assigned_to_id=ASSIGNEE_ID)
    with pytest.raises(AppException) as ei:
        _svc(db).extend_tracking(tid, "someone-else", days=2, reason="x")
    assert ei.value.status_code == 403


def test_extend_resolved_422(db):
    """UAC-3: resolved row -> 422."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, is_resolved=True)
    with pytest.raises(AppException) as ei:
        _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=2, reason="x")
    assert ei.value.status_code == 422


def test_extend_no_resolution_due_422(db):
    """UAC-4 (backend): no due_at_resolution -> 422."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, due_res=None)
    with pytest.raises(AppException) as ei:
        _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=2, reason="x")
    assert ei.value.status_code == 422


# ---------------------------------------------------------------------------
# UAC-6: extend allowed at any tier (no tier<3 cap like escalate)
# ---------------------------------------------------------------------------
def test_extend_allowed_at_top_tier(db):
    """UAC-6: extend works at tier 3 (escalate would refuse)."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, current_tier=3, due_res=datetime(2026, 7, 1, 9, 0, 0))
    tracking = _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=1, reason="tier3")
    assert int(tracking.extension_count) == 1


# ---------------------------------------------------------------------------
# UAC-7: extend works for both conversation + form SLA rows
# ---------------------------------------------------------------------------
def test_extend_works_for_form_sla_row(db):
    """UAC-7: form SLA row (source_entity_type='complaint') can be extended."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, source_entity_type="complaint", due_res=datetime(2026, 7, 1, 9, 0, 0))
    tracking = _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=1, reason="form")
    assert int(tracking.extension_count) == 1


# ---------------------------------------------------------------------------
# Form-SLA extend is ASSIGNEE-ONLY too — consistent with conversation (F-block).
# ---------------------------------------------------------------------------
def test_form_extend_non_assignee_403(db):
    """A non-assignee cannot extend a form SLA (assignee-only, same as conversation)."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, source_entity_type="complaint")
    with pytest.raises(AppException) as ei:
        _svc(db).extend_tracking(tid, "someone-else", days=1, reason="nope")
    assert ei.value.status_code == 403


# ---------------------------------------------------------------------------
# UAC-20: exactly one 'extend' event log, correct fields, no -8h shift
# ---------------------------------------------------------------------------
def test_extend_writes_single_extend_event_log_no_tz_shift(db):
    """UAC-20: one event_type='extend' row; from_time=old due, due_at=new due,
    duration=working days added, reason, trigger='manual', triggered_by_id=actor,
    from_tier==to_tier==current tier; from_time/due_at NOT shifted -8h."""
    _seed_user(db)
    pid = _seed_policy(db)
    old_due = datetime(2026, 7, 1, 9, 0, 0)
    tid = _seed_tracking(db, pid, due_res=old_due, current_tier=2)

    _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=3, reason="Need more time")

    logs = (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == tid,
            ConversationSLAEventLog.event_type == "extend",
        )
        .all()
    )
    assert len(logs) == 1
    log = logs[0]
    # from_time = old due (no -8h shift: create_event_log treats naive as +8, but
    # extend_tracking wraps with _to_aware_utc, so it must equal the UTC instant).
    assert log.from_time == old_due
    # due_at = new due (Mon 2026-07-06 09:00).
    assert log.due_at == datetime(2026, 7, 6, 9, 0, 0)
    assert float(log.duration) == 3.0
    assert log.reason == "Need more time"
    assert log.trigger == "manual"
    assert str(log.triggered_by_id) == ASSIGNEE_ID
    assert log.from_tier == 2
    assert log.to_tier == 2


# ---------------------------------------------------------------------------
# UAC-13 / UAC-14 / UAC-15: soft warnings (never block)
# ---------------------------------------------------------------------------
def test_warning_per_request_cap(db):
    """UAC-13: per-request cap breached -> warning, but extend still applies."""
    _seed_user(db)
    pid = _seed_policy(db, max_extension_days_per_request=2)
    tid = _seed_tracking(db, pid, due_res=datetime(2026, 7, 1, 9, 0, 0))
    svc = _svc(db)
    tr = svc.get_tracking(tid, load_event_logs=False)
    warnings = svc.evaluate_extension_warnings(tr, tr.policy, added_days=5)
    assert warnings and any("per-request" in w for w in warnings)
    # Still applies on extend.
    tracking = svc.extend_tracking(tid, ASSIGNEE_ID, days=5, reason="big ask")
    assert int(tracking.extension_count) == 1


def test_warning_count_cap(db):
    """UAC-14: max_extension_count breached -> warning."""
    _seed_user(db)
    pid = _seed_policy(db, max_extension_count=1)
    tid = _seed_tracking(db, pid, extension_count=1, due_res=datetime(2026, 7, 1, 9, 0, 0))
    svc = _svc(db)
    tr = svc.get_tracking(tid, load_event_logs=False)
    warnings = svc.evaluate_extension_warnings(tr, tr.policy, added_days=1)
    assert warnings and any("extension #" in w for w in warnings)


def test_warning_total_days_cap(db):
    """UAC-14: max_extension_days_total breached -> warning."""
    _seed_user(db)
    pid = _seed_policy(db, max_extension_days_total=3)
    tid = _seed_tracking(db, pid, extension_days_total=2, due_res=datetime(2026, 7, 1, 9, 0, 0))
    svc = _svc(db)
    tr = svc.get_tracking(tid, load_event_logs=False)
    warnings = svc.evaluate_extension_warnings(tr, tr.policy, added_days=2)  # 2+2=4 > 3
    assert warnings and any("Cumulative" in w for w in warnings)


def test_no_warning_when_all_caps_null(db):
    """UAC-15: all-null caps -> no warning ever."""
    _seed_user(db)
    pid = _seed_policy(db)  # all caps null
    tid = _seed_tracking(db, pid)
    svc = _svc(db)
    tr = svc.get_tracking(tid, load_event_logs=False)
    assert svc.evaluate_extension_warnings(tr, tr.policy, added_days=999) == []


def test_warning_never_blocks_mutation(db):
    """UAC-13: a warned extension still mutates the row (warning is non-blocking)."""
    _seed_user(db)
    pid = _seed_policy(db, max_extension_days_per_request=1, max_extension_count=1,
                       max_extension_days_total=1)
    old_due = datetime(2026, 7, 1, 9, 0, 0)
    tid = _seed_tracking(db, pid, due_res=old_due)
    tracking = _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=10, reason="way over")
    assert tracking.due_at_resolution > old_due
    assert int(tracking.extension_count) == 1


# ---------------------------------------------------------------------------
# UAC-22: reminders reset + escalation-due re-keys off new due
# ---------------------------------------------------------------------------
def test_extend_re_keys_escalation_due_off_new_due(db):
    """UAC-22: after extend, the auto-escalation breach query no longer flags the
    row (new due_at_resolution is in the future)."""
    _seed_user(db)
    pid = _seed_policy(db)
    # Overdue + responded -> would be flagged by list_due_escalations before extend.
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    tid = _seed_tracking(db, pid, due_res=past, is_responded=True, current_tier=1)
    svc = _svc(db)

    before = svc.list_due_escalations()
    assert any(item["tracking_id"] == tid for item in before), "row should be overdue pre-extend"

    svc.extend_tracking(tid, ASSIGNEE_ID, days=2, reason="more time")

    after = svc.list_due_escalations()
    assert not any(item["tracking_id"] == tid for item in after), (
        "row must no longer be flagged once due moved into the future"
    )


# ---------------------------------------------------------------------------
# UAC-18 (preview): preview endpoint returns 4 fields, no mutation
# ---------------------------------------------------------------------------
def test_preview_returns_fields_and_does_not_mutate(db):
    """UAC-18 (preview): compute_extension + evaluate_extension_warnings produce the
    new due + working-days + warnings without changing the row."""
    _seed_user(db)
    pid = _seed_policy(db, max_extension_days_per_request=1)
    old_due = datetime(2026, 7, 1, 9, 0, 0)
    tid = _seed_tracking(db, pid, due_res=old_due, extension_count=0)
    svc = _svc(db)
    tr = svc.get_tracking(tid, load_event_logs=False)

    new_due, working_days = svc.compute_extension(tr, days=3)
    warnings = svc.evaluate_extension_warnings(tr, tr.policy, working_days)
    assert new_due == datetime(2026, 7, 6, 9, 0, 0)
    assert working_days == 3
    assert warnings  # 3 > per-request cap of 1

    # No mutation occurred.
    fresh = svc.get_tracking(tid, load_event_logs=False)
    assert fresh.due_at_resolution == old_due
    assert int(fresh.extension_count) == 0


# ---------------------------------------------------------------------------
# UAC-23 (prefs): user toggles round-trip via UserResponse builders + UserUpdate
# ---------------------------------------------------------------------------
def test_user_deadline_extended_prefs_surface_in_get_me_and_get_user(db):
    """UAC-23: notify_email/whatsapp_on_deadline_extended surface through the manual
    UserResponse(**dict) builders in get_me / get_user."""
    _seed_user(db, "u-prefs", notify_email_on_deadline_extended=False,
               notify_whatsapp_on_deadline_extended=True)

    user = db.query(User).filter(User.id == "u-prefs").first()

    # The get_user / get_me builders read these columns via getattr (mirrors
    # users.py lines 366/466/759); confirm the saved values are what they will read.
    assert user.notify_email_on_deadline_extended is False
    assert user.notify_whatsapp_on_deadline_extended is True
    # Confirm UserUpdate accepts these fields (round-trip via schema).
    from app.schemas.user import UserUpdate

    upd = UserUpdate(notify_email_on_deadline_extended=True,
                     notify_whatsapp_on_deadline_extended=False)
    dumped = upd.model_dump(exclude_unset=True)
    assert dumped["notify_email_on_deadline_extended"] is True
    assert dumped["notify_whatsapp_on_deadline_extended"] is False


def test_user_prefs_in_userresponse_dict_builders(db):
    """UAC-23: the keys are literally present in the get_user / get_me dict builders
    so the toggle surfaces to the FE (not silently dropped)."""
    import inspect
    from app.api.v1.user_management import users as users_mod

    src = inspect.getsource(users_mod)
    # Both keys appear at least twice (get_user + get_me builders).
    assert src.count('"notify_email_on_deadline_extended"') >= 2
    assert src.count('"notify_whatsapp_on_deadline_extended"') >= 2


# ===========================================================================
# Route-coroutine gating + notify best-effort (mock-based)
# ===========================================================================
from app.api.v1.sla import sla_tracking as route_mod  # noqa: E402
from app.api.v1.sla.sla_tracking import (  # noqa: E402
    preview_extend_sla_tracking,
    extend_sla_tracking,
    _ExtendPreviewRequest,
    _ExtendRequest,
)


def _run(coro):
    return asyncio.run(coro)


def test_route_preview_both_days_and_date_422():
    """Preview route: exactly-one guard -> 422."""
    with pytest.raises(HTTPException) as ei:
        _run(
            preview_extend_sla_tracking(
                tracking_id=uuid.uuid4(),
                payload=_ExtendPreviewRequest(days=2, target_date="2026-07-06"),
                current_user={"id": "me"},
                db=MagicMock(),
            )
        )
    assert ei.value.status_code == 422


def test_route_preview_non_assignee_403():
    """UAC-2 (preview): non-assignee -> 403 from _assert_extend_assignee."""
    svc = MagicMock()
    svc.get_tracking.return_value = SimpleNamespace(
        assigned_to_id="owner", due_at_resolution=datetime(2026, 7, 1, 9, 0, 0)
    )
    with patch.object(route_mod, "ConversationSLATrackingService", return_value=svc):
        with pytest.raises(HTTPException) as ei:
            _run(
                preview_extend_sla_tracking(
                    tracking_id=uuid.uuid4(),
                    payload=_ExtendPreviewRequest(days=2),
                    current_user={"id": "not-owner"},
                    db=MagicMock(),
                )
            )
    assert ei.value.status_code == 403


def test_route_preview_no_resolution_due_422():
    """UAC-4 (preview): no resolution deadline -> 422."""
    svc = MagicMock()
    svc.get_tracking.return_value = SimpleNamespace(
        assigned_to_id="me", due_at_resolution=None
    )
    with patch.object(route_mod, "ConversationSLATrackingService", return_value=svc):
        with pytest.raises(HTTPException) as ei:
            _run(
                preview_extend_sla_tracking(
                    tracking_id=uuid.uuid4(),
                    payload=_ExtendPreviewRequest(days=2),
                    current_user={"id": "me"},
                    db=MagicMock(),
                )
            )
    assert ei.value.status_code == 422


def test_route_preview_happy_path_returns_four_fields():
    """UAC-18 (preview): returns current_due_at, new_due_at, working_days, warnings[]."""
    svc = MagicMock()
    current = datetime(2026, 7, 1, 9, 0, 0)
    new = datetime(2026, 7, 6, 9, 0, 0)
    svc.get_tracking.return_value = SimpleNamespace(
        assigned_to_id="me", due_at_resolution=current, policy=None
    )
    svc.compute_extension.return_value = (new, 3)
    svc.evaluate_extension_warnings.return_value = ["warn!"]
    with patch.object(route_mod, "ConversationSLATrackingService", return_value=svc):
        result = _run(
            preview_extend_sla_tracking(
                tracking_id=uuid.uuid4(),
                payload=_ExtendPreviewRequest(days=3),
                current_user={"id": "me"},
                db=MagicMock(),
            )
        )
    assert result["current_due_at"] == current.isoformat()
    assert result["new_due_at"] == new.isoformat()
    assert result["working_days"] == 3
    assert result["warnings"] == ["warn!"]


def test_route_extend_both_inputs_422():
    with pytest.raises(HTTPException) as ei:
        _run(
            extend_sla_tracking(
                tracking_id=uuid.uuid4(),
                payload=_ExtendRequest(days=2, target_date="2026-07-06", reason="x"),
                current_user={"id": "me"},
                db=MagicMock(),
            )
        )
    assert ei.value.status_code == 422


# ---------------------------------------------------------------------------
# UAC-23 / UAC-24 / UAC-25: next-tier notify behaviour
# ---------------------------------------------------------------------------
def _svc_for_notify():
    """A ConversationSLATrackingService instance with a mocked db, for unit-testing
    _notify_next_tier_deadline_extended in isolation."""
    svc = ConversationSLATrackingService.__new__(ConversationSLATrackingService)
    svc.db = MagicMock()
    return svc


def _tier_map(mapping):
    """side_effect for get_tier_team_and_notify: {tier: (team_id, notify) or None}."""
    def _fn(agent_id, tier, team_set_code=None, *, company_id=None):
        return mapping.get(tier)
    return _fn


def _peek_map(mapping):
    """side_effect for _peek_next_assignee: {team_id: next_user_id}."""
    def _fn(agent_id, team_id):
        return (None, mapping.get(team_id))
    return _fn


def test_notify_next_tier_conversation_row():
    """Conversation row -> notifies the next-tier user resolved by PEEKING the
    round-robin cursor (agent by code -> tier team via get_tier_team_and_notify ->
    _peek_next_assignee), never advancing it."""
    svc = _svc_for_notify()
    tracking = SimpleNamespace(
        id="t1", current_tier=1, source_entity_type=None, assigned_to_id="me",
        agent_id=None, team_set_code=None, due_at_resolution=datetime(2026, 7, 6, 9, 0),
    )
    agent_svc = MagicMock()
    agent_svc.get_agent_id_by_code.return_value = "agent-conv"
    agent_svc.get_tier_team_and_notify.side_effect = _tier_map({2: ("team-2", True)})
    agent_svc._peek_next_assignee.side_effect = _peek_map({"team-2": "next-tier-user"})
    captured = {}

    def fake_notify(tr, *, recipient_user_id, reason):
        captured["recipient"] = recipient_user_id
        captured["reason"] = reason

    svc._notify_user_deadline_extended = fake_notify  # type: ignore[assignment]
    with patch("app.services.user_service.AccessAgentService", return_value=agent_svc):
        svc._notify_next_tier_deadline_extended(tracking, reason="more time")

    assert captured["recipient"] == "next-tier-user"
    assert captured["reason"] == "more time"
    agent_svc._peek_next_assignee.assert_called_once_with("agent-conv", "team-2")
    # Notify-only: must PEEK, never advance the round-robin.
    agent_svc.get_next_assignee.assert_not_called()


def test_notify_next_tier_form_row():
    """Form row -> resolves the tier team via get_tier_team_and_notify then PEEKS the
    cursor for the recipient (no cursor advance)."""
    svc = _svc_for_notify()
    tracking = SimpleNamespace(
        id="t1", current_tier=1, source_entity_type="complaint", assigned_to_id="me",
        agent_id="agent-1", team_set_code="cs_team", due_at_resolution=datetime(2026, 7, 6, 9, 0),
    )
    agent_svc = MagicMock()
    agent_svc.get_tier_team_and_notify.side_effect = _tier_map({2: ("team-2", True)})
    agent_svc._peek_next_assignee.side_effect = _peek_map({"team-2": "form-next-user"})
    captured = {}
    svc._notify_user_deadline_extended = lambda tr, *, recipient_user_id, reason: captured.update(
        recipient=recipient_user_id
    )
    with patch("app.services.user_service.AccessAgentService", return_value=agent_svc):
        svc._notify_next_tier_deadline_extended(tracking, reason="r")
    assert captured["recipient"] == "form-next-user"
    agent_svc._peek_next_assignee.assert_called_once_with("agent-1", "team-2")
    agent_svc.get_next_assignee.assert_not_called()


def test_notify_fans_up_to_grandparent(db=None):
    """N2: tier-1 extend with tier2 + tier3 both opted-in -> BOTH notified."""
    svc = _svc_for_notify()
    tracking = SimpleNamespace(
        id="t1", current_tier=1, source_entity_type="complaint", assigned_to_id="me",
        agent_id="agent-1", team_set_code="cs", due_at_resolution=datetime(2026, 7, 6, 9, 0),
    )
    agent_svc = MagicMock()
    agent_svc.get_tier_team_and_notify.side_effect = _tier_map(
        {2: ("team-2", True), 3: ("team-3", True)}
    )
    agent_svc._peek_next_assignee.side_effect = _peek_map(
        {"team-2": "mgr-user", "team-3": "director-user"}
    )
    recipients = []
    svc._notify_user_deadline_extended = lambda tr, *, recipient_user_id, reason: recipients.append(
        recipient_user_id
    )
    with patch("app.services.user_service.AccessAgentService", return_value=agent_svc):
        svc._notify_next_tier_deadline_extended(tracking, reason="r")
    assert recipients == ["mgr-user", "director-user"]  # parent + grandparent


def test_notify_per_tier_optout():
    """N3: tier3 notify_on_extension=false -> only tier2 notified, not tier3."""
    svc = _svc_for_notify()
    tracking = SimpleNamespace(
        id="t1", current_tier=1, source_entity_type="complaint", assigned_to_id="me",
        agent_id="agent-1", team_set_code="cs", due_at_resolution=datetime(2026, 7, 6, 9, 0),
    )
    agent_svc = MagicMock()
    agent_svc.get_tier_team_and_notify.side_effect = _tier_map(
        {2: ("team-2", True), 3: ("team-3", False)}  # tier3 opted out
    )
    agent_svc._peek_next_assignee.side_effect = _peek_map(
        {"team-2": "mgr-user", "team-3": "director-user"}
    )
    recipients = []
    svc._notify_user_deadline_extended = lambda tr, *, recipient_user_id, reason: recipients.append(
        recipient_user_id
    )
    with patch("app.services.user_service.AccessAgentService", return_value=agent_svc):
        svc._notify_next_tier_deadline_extended(tracking, reason="r")
    assert recipients == ["mgr-user"]


def test_notify_dedups_shared_member():
    """N6: same user is next-in-line for tier2 and tier3 -> notified once."""
    svc = _svc_for_notify()
    tracking = SimpleNamespace(
        id="t1", current_tier=1, source_entity_type="complaint", assigned_to_id="me",
        agent_id="agent-1", team_set_code="cs", due_at_resolution=datetime(2026, 7, 6, 9, 0),
    )
    agent_svc = MagicMock()
    agent_svc.get_tier_team_and_notify.side_effect = _tier_map(
        {2: ("team-2", True), 3: ("team-3", True)}
    )
    agent_svc._peek_next_assignee.side_effect = _peek_map(
        {"team-2": "same-user", "team-3": "same-user"}
    )
    recipients = []
    svc._notify_user_deadline_extended = lambda tr, *, recipient_user_id, reason: recipients.append(
        recipient_user_id
    )
    with patch("app.services.user_service.AccessAgentService", return_value=agent_svc):
        svc._notify_next_tier_deadline_extended(tracking, reason="r")
    assert recipients == ["same-user"]  # deduped, not twice


def test_notify_skipped_at_top_tier():
    """UAC-24: top tier (no next tier) -> no notification, no raise."""
    svc = _svc_for_notify()
    tracking = SimpleNamespace(
        id="t1", current_tier=3, source_entity_type=None, assigned_to_id="me",
        agent_id=None, team_set_code=None, due_at_resolution=datetime(2026, 7, 6, 9, 0),
    )
    called = {"n": 0}
    svc._notify_user_deadline_extended = lambda *a, **k: called.__setitem__("n", called["n"] + 1)
    agent_svc = MagicMock()
    with patch("app.services.user_service.AccessAgentService", return_value=agent_svc):
        svc._notify_next_tier_deadline_extended(tracking, reason="r")
    assert called["n"] == 0
    # Top tier returns before any team/peek resolution.
    agent_svc._peek_next_assignee.assert_not_called()


def test_extend_still_succeeds_at_top_tier_no_notify(db):
    """UAC-24 (end-to-end): tier 3 extend succeeds even though no next tier."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, current_tier=3, due_res=datetime(2026, 7, 1, 9, 0, 0))
    tracking = _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=1, reason="top tier")
    assert tracking.due_at_resolution == datetime(2026, 7, 2, 9, 0, 0)
    assert int(tracking.extension_count) == 1


def test_notify_failure_does_not_raise():
    """UAC-25: a raising notify helper is swallowed (best-effort, never 500s)."""
    svc = _svc_for_notify()
    tracking = SimpleNamespace(
        id="t1", current_tier=1, source_entity_type=None, assigned_to_id="me",
        agent_id=None, team_set_code=None, due_at_resolution=datetime(2026, 7, 6, 9, 0),
    )
    agent_svc = MagicMock()
    agent_svc.get_agent_id_by_code.return_value = "agent-conv"
    agent_svc.get_team_id_by_tier.return_value = "team-2"
    agent_svc._peek_next_assignee.return_value = (None, "next-tier-user")

    def boom(*a, **k):
        raise RuntimeError("notification backend down")

    svc._notify_user_deadline_extended = boom  # type: ignore[assignment]
    # Must NOT raise.
    with patch("app.services.user_service.AccessAgentService", return_value=agent_svc):
        svc._notify_next_tier_deadline_extended(tracking, reason="r")


def test_extend_succeeds_when_notify_raises(db):
    """UAC-25 (end-to-end): extend returns success even if the notify path raises.

    Drives the real _notify_next_tier_deadline_extended to a resolved recipient
    (via mocked AccessAgentService) then makes the inner _notify_user_deadline_extended
    raise — the method's own try/except must swallow it so extend still commits."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(db, pid, due_res=datetime(2026, 7, 1, 9, 0, 0))
    svc = _svc(db)

    def boom(*a, **k):
        raise RuntimeError("notify exploded")

    agent_svc = MagicMock()
    agent_svc.get_agent_id_by_code.return_value = "agent-conv"
    agent_svc.get_team_id_by_tier.return_value = "team-2"
    agent_svc._peek_next_assignee.return_value = (None, "next-user")

    with patch.object(svc, "_notify_user_deadline_extended", side_effect=boom), patch(
        "app.services.user_service.AccessAgentService", return_value=agent_svc
    ):
        tracking = svc.extend_tracking(tid, ASSIGNEE_ID, days=1, reason="resilient")
    assert int(tracking.extension_count) == 1
    assert tracking.due_at_resolution == datetime(2026, 7, 2, 9, 0, 0)


# ---------------------------------------------------------------------------
# Notify-only must NOT advance the round-robin cursor (reviewer guard against the
# cursor-advance bug — extend is notify-only, PLAN decision 11).
# ---------------------------------------------------------------------------
def test_extend_does_not_advance_round_robin_cursor(db):
    """An extend whose notify resolves a next tier must PEEK the round-robin cursor,
    never advance it: the cursor's last_assigned_user_id is unchanged afterward."""
    # Two RR-eligible members so a cursor advance would be observable.
    _seed_user(db)  # the actor / current assignee
    _seed_user(db, "74dcc05f-9de1-56c8-b66c-5d81b3672c79")
    _seed_user(db, "00aa4179-2642-5755-b3a3-72dab04cac0a")

    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="complaint", name="Complaint Agent"))
    team2_id = str(uuid.uuid4())
    db.add(Team(id=team2_id, name="Tier 2 Team"))
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team2_id, user_id="74dcc05f-9de1-56c8-b66c-5d81b3672c79", sort_order=1))
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team2_id, user_id="00aa4179-2642-5755-b3a3-72dab04cac0a", sort_order=2))
    # Agent team set 'cs' at tier 2 -> team2.
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=agent_id, code="cs", team_id=team2_id, tier=2))
    # Flush parents first -- Postgres enforces the cursor's team/agent FKs, and the
    # ORM insert order is not guaranteed without relationships between these mappers.
    db.flush()
    # Cursor currently points at next-1 (so next-in-line would be next-2).
    db.add(
        AgentTeamRoundRobinCursor(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            team_id=team2_id,
            last_assigned_user_id="74dcc05f-9de1-56c8-b66c-5d81b3672c79",
        )
    )
    db.commit()

    pid = _seed_policy(db)
    # Form SLA row at tier 1 (agent_id + team_set_code 'cs') -> notify resolves tier 2.
    tid = _seed_tracking(
        db,
        pid,
        source_entity_type="complaint",
        current_tier=1,
        due_res=datetime(2026, 7, 1, 9, 0, 0),
    )
    tracking = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    tracking.agent_id = agent_id
    tracking.team_set_code = "cs"
    db.commit()

    _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=1, reason="cursor guard")

    db.expire_all()
    cursor = (
        db.query(AgentTeamRoundRobinCursor)
        .filter(
            AgentTeamRoundRobinCursor.agent_id == agent_id,
            AgentTeamRoundRobinCursor.team_id == team2_id,
        )
        .first()
    )
    # The notify PEEKED (next-in-line = next-2) but must NOT have advanced the cursor.
    assert cursor is not None
    assert cursor.last_assigned_user_id == "74dcc05f-9de1-56c8-b66c-5d81b3672c79"


# ---------------------------------------------------------------------------
# UAC-8: overdue days-mode advances relative to the CURRENT due (not today) and
# preserves the current-due time-of-day.
# ---------------------------------------------------------------------------
def test_extend_overdue_days_mode_advances_from_current_due_keeps_time(db):
    """UAC-8: an overdue row extended by N working days lands on current_due.date()
    advanced by N working days (relative to the CURRENT due, NOT today), preserving
    the current due's time-of-day (09:00). The result may still be in the past."""
    from app.services.calendar_service import CalendarService

    _seed_user(db)
    pid = _seed_policy(db)
    # Current due 09:00, long in the past -> overdue.
    current_due = datetime(2024, 5, 15, 9, 0, 0)
    tid = _seed_tracking(db, pid, due_res=current_due)

    tracking = _svc(db).extend_tracking(tid, ASSIGNEE_ID, days=2, reason="overdue tod")

    new_due = tracking.due_at_resolution
    # Expected date = current_due advanced by 2 working days (tracks weekends/holidays),
    # with the current due's time-of-day re-applied — relative to current due, not now.
    advanced = CalendarService(db).add_working_days(current_due, 2)
    expected = datetime.combine(advanced.date(), current_due.time())
    assert new_due == expected
    assert new_due.date() == advanced.date()
    # Time-of-day equals the current due's 09:00.
    assert (new_due.hour, new_due.minute, new_due.second, new_due.microsecond) == (9, 0, 0, 0)
    # Strictly after current due; NOT anchored to today (still in the past).
    assert new_due > current_due


# ---------------------------------------------------------------------------
# UAC-1 (backend visibility data): list_my_pending emits due_at_resolution so the
# FE can gate the Extend button.
# ---------------------------------------------------------------------------
def test_list_my_pending_emits_due_at_resolution(db):
    """UAC-1: the widget query exposes due_at_resolution for client-side gating."""
    _seed_user(db)
    pid = _seed_policy(db)
    _seed_tracking(db, pid, due_res=datetime(2026, 7, 1, 9, 0, 0))
    out = _svc(db).list_my_pending(ASSIGNEE_ID)
    assert len(out) == 1
    assert out[0]["due_at_resolution"] == "2026-07-01T09:00:00"


# ===========================================================================
# CHANGE 1: per-occurrence re-notify (event_type="deadline_extended:{count}")
# ===========================================================================
def _seed_next_tier_chain(db, *, source_entity_type="complaint"):
    """Seed an agent + tier-2 team + cursor so an extend's next-tier notify resolves
    a concrete recipient ('74dcc05f-9de1-56c8-b66c-5d81b3672c79'). Returns (agent_id, team2_id, recipient_id)."""
    _seed_user(db)  # actor / current assignee (ASSIGNEE_ID)
    _seed_user(db, "74dcc05f-9de1-56c8-b66c-5d81b3672c79")
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="complaint", name="Complaint Agent"))
    team2_id = str(uuid.uuid4())
    db.add(Team(id=team2_id, name="Tier 2 Team"))
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team2_id, user_id="74dcc05f-9de1-56c8-b66c-5d81b3672c79", sort_order=1))
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=agent_id, code="cs", team_id=team2_id, tier=2))
    db.commit()
    return agent_id, team2_id, "74dcc05f-9de1-56c8-b66c-5d81b3672c79"


def _attach_agent(db, tid, agent_id):
    tr = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    tr.agent_id = agent_id
    tr.team_set_code = "cs"
    db.commit()


def test_two_extends_create_two_distinct_notifications(db):
    """CHANGE 1: TWO extends on the SAME tracking (same next-tier recipient) create
    TWO distinct Notification rows ('deadline_extended:1' and ':2'). Pre-fix the 2nd
    deduped to the 1st and sent nothing."""
    agent_id, _team, recipient = _seed_next_tier_chain(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(
        db, pid, source_entity_type="complaint", current_tier=1,
        due_res=datetime(2026, 7, 1, 9, 0, 0),
    )
    _attach_agent(db, tid, agent_id)

    svc = _svc(db)
    svc.extend_tracking(tid, ASSIGNEE_ID, days=1, reason="first")   # extension_count -> 1
    svc.extend_tracking(tid, ASSIGNEE_ID, days=1, reason="second")  # extension_count -> 2

    notes = (
        db.query(Notification)
        .filter(
            Notification.user_id == recipient,
            Notification.source_entity_type == "form_sla_tracking",
            Notification.source_entity_id == tid,
        )
        .order_by(Notification.event_type.asc())
        .all()
    )
    event_types = sorted(n.event_type for n in notes)
    assert event_types == ["deadline_extended:1", "deadline_extended:2"], event_types
    # Each notification has its own deliveries (in_app + a pending email at minimum).
    for n in notes:
        ds = db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_id == n.id
        ).all()
        channels = {d.channel for d in ds}
        assert "in_app" in channels
        assert "email" in channels  # recipient defaults notify_email_on_deadline_extended=True


def test_retrying_same_occurrence_is_idempotent(db):
    """CHANGE 1: re-notifying the SAME extension occurrence (same extension_count)
    returns the existing notification — no duplicate row."""
    agent_id, _team, recipient = _seed_next_tier_chain(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(
        db, pid, source_entity_type="complaint", current_tier=1,
        due_res=datetime(2026, 7, 1, 9, 0, 0),
    )
    _attach_agent(db, tid, agent_id)

    svc = _svc(db)
    svc.extend_tracking(tid, ASSIGNEE_ID, days=1, reason="first")  # count -> 1, notify :1
    # Re-run the notify for the SAME occurrence (count is still 1) — must dedup.
    tracking = svc.get_tracking(tid, load_event_logs=False)
    svc._notify_user_deadline_extended(tracking, recipient_user_id=recipient, reason="retry")

    notes = (
        db.query(Notification)
        .filter(
            Notification.user_id == recipient,
            Notification.source_entity_id == tid,
            Notification.event_type == "deadline_extended:1",
        )
        .all()
    )
    assert len(notes) == 1  # idempotent on the same occurrence


# ===========================================================================
# CHANGE 5: channel gating for deadline_extended
# ===========================================================================
def _seed_recipient_with_whatsapp(db, uid, *, email_pref, whatsapp_pref):
    """Seed a user with a linked RespondContact (resolvable respond_io_id) + prefs."""
    rc_id = str(uuid.uuid4())
    db.add(
        RespondContact(
            id=rc_id,
            phone_number=f"+6012{uid[-7:].zfill(7)}",
            name=uid,
            respond_io_id=f"rio-{uid}",
            session_vars={},
        )
    )
    db.add(
        User(
            id=uid,
            email=f"{uid}@example.com",
            name=uid,
            respond_contact_id=rc_id,
            notify_email_on_deadline_extended=email_pref,
            notify_whatsapp_on_deadline_extended=whatsapp_pref,
        )
    )
    db.commit()


def _channels_for(db, user_id):
    """Create a deadline_extended notification via the channel-pref API and return the
    set of delivery channels created."""
    note = NotificationService(db).create_with_channel_preferences(
        user_id=user_id,
        type="form_sla",
        title="SLA deadline extended",
        body="body",
        data={},
        source_entity_type="form_sla_tracking",
        source_entity_id=str(uuid.uuid4()),
        event_type="deadline_extended:1",
        send_in_app=True,
        send_email=True,
        send_whatsapp=True,
        email_pref_attr="notify_email_on_deadline_extended",
        whatsapp_pref_attr="notify_whatsapp_on_deadline_extended",
    )
    ds = db.query(NotificationDelivery).filter(
        NotificationDelivery.notification_id == note.id
    ).all()
    return {d.channel for d in ds}


def test_channel_gating_both_prefs_on(db):
    """CHANGE 5: both prefs on + resolvable respond_io_id -> email + whatsapp + in_app."""
    _seed_recipient_with_whatsapp(db, "rcpt-both", email_pref=True, whatsapp_pref=True)
    channels = _channels_for(db, "rcpt-both")
    assert channels == {"in_app", "email", "whatsapp"}


def test_channel_gating_email_pref_off(db):
    """CHANGE 5: email pref False -> no email delivery; whatsapp still created."""
    _seed_recipient_with_whatsapp(db, "rcpt-noemail", email_pref=False, whatsapp_pref=True)
    channels = _channels_for(db, "rcpt-noemail")
    assert "email" not in channels
    assert "whatsapp" in channels
    assert "in_app" in channels


def test_channel_gating_whatsapp_pref_off(db):
    """CHANGE 5: whatsapp pref False -> no whatsapp delivery; email still created."""
    _seed_recipient_with_whatsapp(db, "rcpt-nowa", email_pref=True, whatsapp_pref=False)
    channels = _channels_for(db, "rcpt-nowa")
    assert "whatsapp" not in channels
    assert "email" in channels
    assert "in_app" in channels


# ===========================================================================
# CHANGE 6: row deadline phase (active_due_at / due_kind) keyed on is_responded
# ===========================================================================
def test_my_pending_phase_respond_when_not_responded(db):
    """CHANGE 6: not responded -> due_kind 'respond', active_due_at = due_at."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(
        db, pid, source_entity_type="complaint", is_responded=False,
        due_res=datetime(2026, 7, 5, 9, 0, 0),
    )
    tr = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    row = next(r for r in _svc(db).list_my_pending(ASSIGNEE_ID) if r["id"] == tid)
    assert row["due_kind"] == "respond"
    assert row["active_due_at"] == tr.due_at.isoformat()


def test_my_pending_phase_resolve_when_responded(db):
    """CHANGE 6: responded -> due_kind 'resolve', active_due_at = due_at_resolution."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(
        db, pid, source_entity_type="complaint", is_responded=True,
        due_res=datetime(2026, 7, 5, 9, 0, 0),
    )
    row = next(r for r in _svc(db).list_my_pending(ASSIGNEE_ID) if r["id"] == tid)
    assert row["due_kind"] == "resolve"
    assert row["active_due_at"] == "2026-07-05T09:00:00"


def test_my_pending_phase_resolve_falls_back_to_due_at_when_resolution_null(db):
    """CHANGE 6: responded but no resolution due -> active_due_at falls back to due_at."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(
        db, pid, source_entity_type="complaint", is_responded=True, due_res=None,
    )
    tr = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    row = next(r for r in _svc(db).list_my_pending(ASSIGNEE_ID) if r["id"] == tid)
    assert row["due_kind"] == "resolve"
    assert row["active_due_at"] == tr.due_at.isoformat()


def test_my_pending_phase_conversation_row(db):
    """CHANGE 6: phase logic applies to conversation rows too (source_entity_type None)."""
    _seed_user(db)
    pid = _seed_policy(db)
    tid = _seed_tracking(
        db, pid, source_entity_type=None, is_responded=False,
        due_res=datetime(2026, 7, 5, 9, 0, 0),
    )
    tr = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    row = next(r for r in _svc(db).list_my_pending(ASSIGNEE_ID) if r["id"] == tid)
    assert row["due_kind"] == "respond"
    assert row["active_due_at"] == tr.due_at.isoformat()


# ===========================================================================
# CHANGE 8: deadline_extended prefs round-trip through the channels endpoint
# (_SLA_NOTIFY_FIELDS / _ChannelPrefsUpdate / _channel_prefs).
# ===========================================================================
def test_channel_prefs_includes_deadline_extended_fields(db):
    """CHANGE 8: _channel_prefs surfaces both deadline_extended toggles with the
    saved values (email default true, whatsapp default false)."""
    from app.api.v1.notifications.notifications import (
        _SLA_NOTIFY_FIELDS,
        _ChannelPrefsUpdate,
        _channel_prefs,
    )

    assert "notify_email_on_deadline_extended" in _SLA_NOTIFY_FIELDS
    assert "notify_whatsapp_on_deadline_extended" in _SLA_NOTIFY_FIELDS

    _seed_user(db, "u-ch", notify_email_on_deadline_extended=False,
               notify_whatsapp_on_deadline_extended=True)
    user = db.query(User).filter(User.id == "u-ch").first()
    prefs = _channel_prefs(user)
    assert prefs["notify_email_on_deadline_extended"] is False
    assert prefs["notify_whatsapp_on_deadline_extended"] is True

    # _ChannelPrefsUpdate accepts both fields.
    upd = _ChannelPrefsUpdate(
        notify_email_on_deadline_extended=True,
        notify_whatsapp_on_deadline_extended=False,
    )
    dumped = upd.model_dump(exclude_unset=True)
    assert dumped["notify_email_on_deadline_extended"] is True
    assert dumped["notify_whatsapp_on_deadline_extended"] is False


def test_channel_prefs_defaults_when_unset(db):
    """CHANGE 8: with no explicit prefs, _channel_prefs returns the column defaults
    (email-on True, whatsapp-on False)."""
    from app.api.v1.notifications.notifications import _channel_prefs

    _seed_user(db, "u-def")
    user = db.query(User).filter(User.id == "u-def").first()
    prefs = _channel_prefs(user)
    assert prefs["notify_email_on_deadline_extended"] is True
    assert prefs["notify_whatsapp_on_deadline_extended"] is False
