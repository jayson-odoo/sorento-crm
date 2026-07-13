"""System-health watchdog + digest + recipient resolution (WS3).

Service-level tests over an sqlite fixture for
app/services/system_health_alert_service.py:

- Condition evaluators (_eval_n8n_liveness / _eval_failed_integrations /
  _eval_scheduled_tasks).
- run_health_watchdog de-dup state machine (fire once, suppress within cooldown,
  recover on good) with _notify_admins mocked.
- run_health_daily_digest (builds lines + notifies once; digest_enabled=False
  short-circuits).
- _resolve_recipient_user_ids (configured roles vs superadmin/admin fallback;
  active/non-trashed only).
"""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON

from app.database import Base
from app.models.health_alert_state import HealthAlertState
from app.models.integration import IntegrationLog
from app.models.lookup import LookupBinding
from app.models.scheduled_task import ScheduledTask
from app.models.user import (
    SystemSetting,
    User,
    UserRole,
    UserRoleAssignment,
    UserStatus,
)
from app.services import system_health_alert_service as svc
from app.services.n8n_liveness_service import HEALTHCHECK_CHANNEL


def _prep(*models):
    for model in models:
        for col in model.__table__.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                col.type = JSON()
                col.server_default = None


_MODELS = [
    HealthAlertState,
    IntegrationLog,
    ScheduledTask,
    SystemSetting,
    User,
    UserRole,
    UserRoleAssignment,
    LookupBinding,
]


@pytest.fixture
def db():
    _prep(*_MODELS)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _MODELS])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


NOW = datetime(2026, 7, 1, 12, 0, 0)


def _integ_log(db, *, channel, status, created_at=NOW, error_code=None):
    log = IntegrationLog(
        id=str(uuid.uuid4()),
        integration_channel=channel,
        business_table="attachments",
        business_id=str(uuid.uuid4()),
        direction="outbound",
        endpoint="https://example.invalid/webhook",
        http_method="POST",
        status=status,
        error_code=error_code,
        created_at=created_at,
    )
    db.add(log)
    db.commit()
    return log


def _task(db, *, key, enabled=True, last_status=None, next_run_at=None):
    t = ScheduledTask(
        id=str(uuid.uuid4()),
        key=key,
        name=key,
        enabled=enabled,
        interval_unit="minutes",
        interval_value=10,
        last_status=last_status,
        next_run_at=next_run_at,
    )
    db.add(t)
    db.commit()
    return t


# --------------------------------------------------------------------------- #
# _eval_n8n_liveness                                                          #
# --------------------------------------------------------------------------- #
def test_liveness_no_probe_not_bad(db):
    bad, detail = svc._eval_n8n_liveness(db, NOW)
    assert bad is False


def test_liveness_latest_failed_is_bad(db):
    _integ_log(db, channel=HEALTHCHECK_CHANNEL, status="failed", error_code="X")
    bad, detail = svc._eval_n8n_liveness(db, NOW)
    assert bad is True
    assert "FAILED" in detail


def test_liveness_latest_success_not_bad(db):
    _integ_log(db, channel=HEALTHCHECK_CHANNEL, status="success")
    bad, _ = svc._eval_n8n_liveness(db, NOW)
    assert bad is False


def test_liveness_stuck_sent_past_stale_is_bad(db):
    stale_at = NOW - svc.LIVENESS_STALE - timedelta(minutes=1)
    _integ_log(db, channel=HEALTHCHECK_CHANNEL, status="sent", created_at=stale_at)
    bad, detail = svc._eval_n8n_liveness(db, NOW)
    assert bad is True
    assert "stuck" in detail


def test_liveness_recent_sent_not_bad(db):
    _integ_log(
        db,
        channel=HEALTHCHECK_CHANNEL,
        status="sent",
        created_at=NOW - timedelta(minutes=5),
    )
    bad, _ = svc._eval_n8n_liveness(db, NOW)
    assert bad is False


def test_liveness_uses_latest_probe_only(db):
    # An old failure followed by a recent success => healthy.
    _integ_log(
        db,
        channel=HEALTHCHECK_CHANNEL,
        status="failed",
        created_at=NOW - timedelta(hours=5),
    )
    _integ_log(
        db,
        channel=HEALTHCHECK_CHANNEL,
        status="success",
        created_at=NOW - timedelta(minutes=1),
    )
    bad, _ = svc._eval_n8n_liveness(db, NOW)
    assert bad is False


# --------------------------------------------------------------------------- #
# _eval_failed_integrations                                                   #
# --------------------------------------------------------------------------- #
def test_failed_integrations_below_threshold_not_bad(db):
    for _ in range(3):
        _integ_log(db, channel="respond_io", status="failed")
    bad, _ = svc._eval_failed_integrations(db, NOW, threshold=5)
    assert bad is False


def test_failed_integrations_at_threshold_is_bad(db):
    for _ in range(5):
        _integ_log(db, channel="respond_io", status="failed")
    bad, detail = svc._eval_failed_integrations(db, NOW, threshold=5)
    assert bad is True
    assert "respond_io" in detail


def test_failed_integrations_ignores_healthcheck_channel(db):
    for _ in range(10):
        _integ_log(db, channel=HEALTHCHECK_CHANNEL, status="failed")
    bad, _ = svc._eval_failed_integrations(db, NOW, threshold=5)
    assert bad is False


def test_failed_integrations_ignores_old_failures(db):
    for _ in range(6):
        _integ_log(
            db,
            channel="respond_io",
            status="failed",
            created_at=NOW - timedelta(hours=48),
        )
    bad, _ = svc._eval_failed_integrations(db, NOW, threshold=5)
    assert bad is False


# --------------------------------------------------------------------------- #
# _eval_scheduled_tasks                                                       #
# --------------------------------------------------------------------------- #
def test_scheduled_tasks_last_failed_is_bad(db):
    _task(db, key="respond_sync", last_status="failed", next_run_at=NOW + timedelta(minutes=5))
    bad, detail = svc._eval_scheduled_tasks(db, NOW)
    assert bad is True
    assert "respond_sync" in detail


def test_scheduled_tasks_overdue_is_bad(db):
    _task(db, key="import_job", last_status="success", next_run_at=NOW - timedelta(minutes=1))
    bad, detail = svc._eval_scheduled_tasks(db, NOW)
    assert bad is True
    assert "overdue" in detail


def test_scheduled_tasks_healthy_not_bad(db):
    _task(db, key="ok_task", last_status="success", next_run_at=NOW + timedelta(minutes=5))
    bad, _ = svc._eval_scheduled_tasks(db, NOW)
    assert bad is False


def test_scheduled_tasks_null_next_run_not_overdue(db):
    _task(db, key="just_seeded", last_status="success", next_run_at=None)
    bad, _ = svc._eval_scheduled_tasks(db, NOW)
    assert bad is False


def test_scheduled_tasks_disabled_ignored(db):
    _task(db, key="off", enabled=False, last_status="failed", next_run_at=NOW - timedelta(hours=1))
    bad, _ = svc._eval_scheduled_tasks(db, NOW)
    assert bad is False


# --------------------------------------------------------------------------- #
# run_health_watchdog — de-dup state machine                                  #
# --------------------------------------------------------------------------- #
@pytest.fixture
def notify_spy(monkeypatch):
    calls = []
    monkeypatch.setattr(
        svc,
        "_notify_admins",
        lambda db, settings, *, subject, lines, is_alert, task=None: calls.append(
            {"subject": subject, "lines": lines, "is_alert": is_alert}
        ),
    )
    return calls


def test_watchdog_fires_once_then_suppresses_within_cooldown(db, notify_spy, monkeypatch):
    # Freeze "now" so the second run is inside the cooldown window.
    monkeypatch.setattr(svc, "_utcnow_naive", lambda: NOW)
    _integ_log(db, channel=HEALTHCHECK_CHANNEL, status="failed", error_code="E")

    out1 = svc.run_health_watchdog(db)
    assert out1["fired"] == ["n8n_liveness"]
    assert len([c for c in notify_spy if c["is_alert"]]) == 1
    row = db.query(HealthAlertState).filter(HealthAlertState.alert_key == "n8n_liveness").one()
    assert row.state == "alerting"
    assert row.last_alerted_at == NOW

    # Second immediate run: still bad, within cooldown => no new alert.
    out2 = svc.run_health_watchdog(db)
    assert out2["fired"] == []
    assert len([c for c in notify_spy if c["is_alert"]]) == 1


def test_watchdog_refires_after_cooldown(db, notify_spy, monkeypatch):
    monkeypatch.setattr(svc, "_utcnow_naive", lambda: NOW)
    _integ_log(db, channel=HEALTHCHECK_CHANNEL, status="failed", error_code="E")

    svc.run_health_watchdog(db)
    # Push the last alert back beyond the cooldown window.
    row = db.query(HealthAlertState).filter(HealthAlertState.alert_key == "n8n_liveness").one()
    row.last_alerted_at = NOW - svc.ALERT_COOLDOWN - timedelta(minutes=1)
    db.commit()

    out = svc.run_health_watchdog(db)
    assert out["fired"] == ["n8n_liveness"]
    assert len([c for c in notify_spy if c["is_alert"]]) == 2


def test_watchdog_recovers_and_emits_recovery(db, notify_spy, monkeypatch):
    monkeypatch.setattr(svc, "_utcnow_naive", lambda: NOW)
    failed = _integ_log(db, channel=HEALTHCHECK_CHANNEL, status="failed", error_code="E")
    svc.run_health_watchdog(db)
    assert len([c for c in notify_spy if c["is_alert"]]) == 1

    # Flip healthy: the latest probe now succeeds.
    _integ_log(
        db,
        channel=HEALTHCHECK_CHANNEL,
        status="success",
        created_at=NOW + timedelta(minutes=1),
    )
    out = svc.run_health_watchdog(db)
    assert out["recovered"] == ["n8n_liveness"]
    recoveries = [c for c in notify_spy if not c["is_alert"]]
    assert len(recoveries) == 1
    assert "recovered" in recoveries[0]["subject"].lower()
    row = db.query(HealthAlertState).filter(HealthAlertState.alert_key == "n8n_liveness").one()
    assert row.state == "ok"
    assert row.last_detail is None


def test_watchdog_skips_when_alerts_disabled(db, notify_spy):
    db.add(SystemSetting(id=str(uuid.uuid4()), name="Co", health_alerts_enabled=False))
    db.commit()
    _integ_log(db, channel=HEALTHCHECK_CHANNEL, status="failed", error_code="E")
    out = svc.run_health_watchdog(db)
    assert out == {"skipped": "alerts_disabled"}
    assert notify_spy == []


# --------------------------------------------------------------------------- #
# run_health_daily_digest                                                     #
# --------------------------------------------------------------------------- #
def _stub_digest_blocks(monkeypatch):
    from app.api.v1.system import health as health_mod

    monkeypatch.setattr(health_mod, "_email_outbox_health", lambda db, cutoff: None)
    monkeypatch.setattr(health_mod, "_imports_health", lambda db, cutoff: None)
    monkeypatch.setattr(health_mod, "_scheduled_tasks_health", lambda db, now: None)
    monkeypatch.setattr(health_mod, "_integrations_health", lambda db, cutoff: None)
    monkeypatch.setattr(health_mod, "_audit_activity_health", lambda db, cutoff, now: None)


def test_digest_builds_lines_and_notifies_once(db, notify_spy, monkeypatch):
    _stub_digest_blocks(monkeypatch)
    out = svc.run_health_daily_digest(db)
    assert out["sent"] is True
    assert len(notify_spy) == 1
    call = notify_spy[0]
    assert call["is_alert"] is False
    assert any("digest" in l.lower() for l in call["lines"])
    assert any("n8n liveness" in l.lower() for l in call["lines"])


def test_digest_skips_when_disabled(db, notify_spy, monkeypatch):
    _stub_digest_blocks(monkeypatch)
    db.add(SystemSetting(id=str(uuid.uuid4()), name="Co", health_digest_enabled=False))
    db.commit()
    out = svc.run_health_daily_digest(db)
    assert out == {"skipped": "digest_disabled"}
    assert notify_spy == []


# --------------------------------------------------------------------------- #
# _resolve_recipient_user_ids                                                 #
# --------------------------------------------------------------------------- #
def _user(db, *, status=UserStatus.ACTIVE.value, is_trashed=False):
    u = User(
        id=str(uuid.uuid4()),
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        status=status,
        is_trashed=is_trashed,
    )
    db.add(u)
    db.commit()
    return u


def _role(db, slug):
    r = UserRole(id=str(uuid.uuid4()), slug=slug, name=slug)
    db.add(r)
    db.commit()
    return r


def _assign(db, user, role):
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
    db.commit()


def test_recipients_configured_roles(db):
    ops = _role(db, "ops")
    admin = _role(db, "admin")
    u_ops = _user(db)
    u_admin = _user(db)
    _assign(db, u_ops, ops)
    _assign(db, u_admin, admin)

    settings = SystemSetting(id=str(uuid.uuid4()), name="Co", health_notify_role_ids=[ops.id])
    out = svc._resolve_recipient_user_ids(db, settings)
    assert out == [u_ops.id]


def test_recipients_fallback_to_superadmin_admin(db):
    superadmin = _role(db, "superadmin")
    admin = _role(db, "admin")
    other = _role(db, "viewer")
    u_super = _user(db)
    u_admin = _user(db)
    u_other = _user(db)
    _assign(db, u_super, superadmin)
    _assign(db, u_admin, admin)
    _assign(db, u_other, other)

    settings = SystemSetting(id=str(uuid.uuid4()), name="Co", health_notify_role_ids=None)
    out = set(svc._resolve_recipient_user_ids(db, settings))
    assert out == {u_super.id, u_admin.id}


def test_recipients_exclude_inactive_and_trashed(db):
    admin = _role(db, "admin")
    active = _user(db)
    inactive = _user(db, status=UserStatus.INACTIVE.value)
    trashed = _user(db, is_trashed=True)
    for u in (active, inactive, trashed):
        _assign(db, u, admin)

    settings = SystemSetting(id=str(uuid.uuid4()), name="Co", health_notify_role_ids=None)
    out = svc._resolve_recipient_user_ids(db, settings)
    assert out == [active.id]
