"""S1 of PLAN-excel-preview-26sep.md, the email's link (UAC AC-19..AC-22; owner rulings 26 Sep,
Q1 and Q5).

The daily low stock email is the automation engine's: an admin's rule, run by the
`automation_runner` scheduled task, with its own template and its own `recipient_config`. What
the engine could not do is name the run. These tests pin the trigger that lets it:
`low_stock_report_ready`, dispatched once when the daily reorder run is funded, carrying
`report.link` to the in-system low stock report page.

Written before the implementation (tests red first). Postgres only, rolled back.
"""
from __future__ import annotations

import uuid

from app.models.automation import Automation
from app.models.email_template import EmailTemplate
from app.models.notification import Notification
from tests.scm.conftest import requires_pg, seed_user
from tests.scm.test_low_stock_report import _product, _run, _summary_row
from tests.scm.test_product_grain_summary import db  # noqa: F401

pytestmark = requires_pg

TRIGGER = "low_stock_report_ready"


def _seed_run_with_rows(db):
    run = _run(db)
    _summary_row(db, run, _product(db, stem="RDYLOW"), pool_on_hand=5, reorder_level=50)
    _summary_row(db, run, _product(db, stem="RDYOK"), pool_on_hand=90, reorder_level=50)
    db.flush()
    return str(run.id)


def _stub_the_run(monkeypatch, run_id):
    """The handler plans and funds a whole network run; the trigger only needs the run it
    produced, so the planning calls are stubbed to hand back the seeded run."""
    from app.services.scm import reorder_run_service as reorder_svc

    monkeypatch.setattr(reorder_svc, "create_run", lambda db, **kw: {"run_id": run_id})
    monkeypatch.setattr(reorder_svc, "run_reorder", lambda rid, db=None: None)
    monkeypatch.setattr(
        reorder_svc, "apply_run_budget", lambda db, rid, budget, full=False: {"funded": 2},
    )


class _Task:
    metadata_ = {}


def test_trigger_is_listed():
    from app.services import automation_triggers

    specs = {s.type: s for s in automation_triggers.list_specs()}
    assert TRIGGER in specs
    assert specs[TRIGGER].label == "Low stock report ready"
    # Event-driven: a scheduled evaluation finds nothing on its own.
    assert automation_triggers.fire(None, TRIGGER, {}, "Asia/Kuala_Lumpur") == []


def test_daily_run_dispatches_low_stock_report_ready(db, monkeypatch):
    from app.scheduler import task_scheduler
    from app.services import automation_service

    run_id = _seed_run_with_rows(db)
    _stub_the_run(monkeypatch, run_id)
    calls: list = []
    monkeypatch.setattr(
        automation_service.AutomationService, "dispatch_event",
        lambda self, trigger_type, **kw: calls.append((trigger_type, kw)) or {"fired": 0},
    )

    result = task_scheduler._handler_scm_reorder_run(db, _Task())

    assert result["run_id"] == run_id
    assert len(calls) == 1, calls
    trigger_type, kw = calls[0]
    assert trigger_type == TRIGGER
    assert kw["source_kind"] == "reorder_run"
    assert kw["source_id"] == run_id
    report = kw["context"]["report"]
    assert report["link"].endswith(f"/scm/low-stock-report/{run_id}")
    assert report["low"] == 1
    assert report["rows"] == 2
    assert report["as_of"] == "2026-09-10"
    assert report["date_label"] == "10 Sep 2026"


def _fail_the_run(monkeypatch, db, run_id):
    """What the real `run_reorder` does on a failure: it never raises, it marks the run
    `failed` and returns `{"status": "failed"}` (`reorder_run_service._execute_run`)."""
    from app.models.scm import ReorderRun
    from app.services.scm import reorder_run_service as reorder_svc

    def _failed(rid, db=None):
        run = db.query(ReorderRun).filter(ReorderRun.id == rid).one()
        run.status = "failed"
        run.error_text = "planning blew up"
        db.flush()
        return {"run_id": rid, "status": "failed", "error": "planning blew up"}

    monkeypatch.setattr(reorder_svc, "run_reorder", _failed)


def _record_dispatches(monkeypatch) -> list:
    from app.services import automation_service

    calls: list = []
    monkeypatch.setattr(
        automation_service.AutomationService, "dispatch_event",
        lambda self, trigger_type, **kw: calls.append((trigger_type, kw)) or {"fired": 0},
    )
    return calls


def test_failed_run_does_not_dispatch(db, monkeypatch):
    """Review B1: a failed daily run must never send the low stock email. Before the fix the
    handler ignored `run_reorder`'s `failed` status and dispatched a "0 low" all-clear
    linking to an empty page."""
    from app.scheduler import task_scheduler

    run_id = _seed_run_with_rows(db)
    _stub_the_run(monkeypatch, run_id)
    _fail_the_run(monkeypatch, db, run_id)
    calls = _record_dispatches(monkeypatch)

    result = task_scheduler._handler_scm_reorder_run(db, _Task())

    assert result["run_id"] == run_id
    assert calls == []


def test_dispatch_ready_refuses_a_run_that_is_not_completed(db, monkeypatch):
    """The guard sits on `dispatch_ready` itself, off the run row, so no caller can mail a
    report for a failed or still-running plan."""
    from app.models.scm import ReorderRun
    from app.services.scm import low_stock_report_service as lsr

    run_id = _seed_run_with_rows(db)
    calls = _record_dispatches(monkeypatch)
    run = db.query(ReorderRun).filter(ReorderRun.id == run_id).one()

    for status in ("failed", "running"):
        run.status = status
        db.flush()
        assert lsr.dispatch_ready(db, run_id)["fired"] == 0
    assert calls == []

    run.status = "completed"
    db.flush()
    lsr.dispatch_ready(db, run_id)
    assert len(calls) == 1


def test_trigger_context_link_is_internal_page(db, monkeypatch):
    from app.config import settings
    from app.services.scm import low_stock_report_service as lsr

    run_id = _seed_run_with_rows(db)

    monkeypatch.setattr(settings, "frontend_base_url", "https://crm.example/")
    assert lsr.ready_context(db, run_id)["report"]["link"] == (
        f"https://crm.example/scm/low-stock-report/{run_id}"
    )
    monkeypatch.setattr(settings, "frontend_base_url", "")
    assert lsr.ready_context(db, run_id)["report"]["link"] == (
        f"/scm/low-stock-report/{run_id}"
    )


def test_dispatch_failure_does_not_fail_run(db, monkeypatch):
    from app.scheduler import task_scheduler
    from app.services import automation_service

    run_id = _seed_run_with_rows(db)
    _stub_the_run(monkeypatch, run_id)

    def _boom(self, trigger_type, **kw):
        raise RuntimeError("mail server on fire")

    monkeypatch.setattr(automation_service.AutomationService, "dispatch_event", _boom)

    result = task_scheduler._handler_scm_reorder_run(db, _Task())

    assert result["run_id"] == run_id
    assert result["funded"] == 2


def test_dispatch_sql_error_leaves_the_scheduler_session_usable(db, monkeypatch):
    """Review S1: a DATABASE error inside dispatch (a statement timeout in the report read,
    say) aborts the transaction. Swallowing it without a rollback left the session unusable,
    so the scheduler's own `finish_run` bookkeeping failed with InFailedSqlTransaction right
    after - failing a run AC-22 says dispatch never fails."""
    from sqlalchemy import text

    from app.scheduler import task_scheduler
    from app.services.scm import low_stock_report_service as lsr

    run_id = _seed_run_with_rows(db)
    _stub_the_run(monkeypatch, run_id)
    _record_dispatches(monkeypatch)

    def _bad_sql(db, rid):
        db.execute(text("SELECT no_such_column FROM scm.reorder_run"))

    monkeypatch.setattr(lsr, "ready_context", _bad_sql)

    result = task_scheduler._handler_scm_reorder_run(db, _Task())

    assert result["run_id"] == run_id
    assert result["funded"] == 2
    # What the scheduler does next on this same session.
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_automation_on_the_trigger_emails_its_own_recipients_the_link(db, monkeypatch):
    """End to end through the engine: an enabled rule on the trigger renders its template
    with the run's link and queues it to the rule's own recipient (Q5: recipients live on
    the automation)."""
    from app.services.scm import low_stock_report_service as lsr

    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    run_id = _seed_run_with_rows(db)
    # The engine authors the queued email as the rule's creator; a fresh CI database has
    # no users at all, so the rule names one.
    author_id = seed_user(db, "purchasing")
    template = EmailTemplate(
        id=str(uuid.uuid4()), code=f"tpl-lsrdy-{uuid.uuid4().hex[:6]}",
        name="Daily low stock", is_active=True, body_text=None,
        subject="Low stock report {{ report.date_label }}: {{ report.low }} low",
        body_html="<p><a href='{{ report.link }}'>Open the low stock report</a></p>",
    )
    db.add(template)
    db.flush()
    rule = Automation(
        id=str(uuid.uuid4()), name="Daily low stock email", enabled=True,
        trigger_type=TRIGGER, trigger_config={}, action_type="send_email",
        email_template_id=str(template.id),
        recipient_config={"user_ids": [], "role_ids": [], "extra_emails": ["buyer@test.local"]},
        schedule_type="manual", run_time=None, timezone="Asia/Kuala_Lumpur",
        created_by_user_id=author_id,
    )
    db.add(rule)
    db.flush()

    lsr.dispatch_ready(db, run_id)

    sent = (
        db.query(Notification)
        .filter(Notification.type == "automation_email")
        .filter(Notification.title == "Low stock report 10 Sep 2026: 1 low")
        .all()
    )
    assert len(sent) == 1, [n.title for n in sent]
    assert f"/scm/low-stock-report/{run_id}" in (sent[0].body or "")
