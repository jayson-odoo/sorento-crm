"""SCM M2 - analytics TRIGGERS (plan §3): scheduled full run + on-GR hook.

Covers the two Phase-2 trigger deliverables:
  * the scheduled ``scm_analytics`` handler runs ``run_analytics`` and leaves a
    ``scm.scm_analytics_run`` log row (completed on success, failed on exception);
  * the on-GR hook ``on_goods_receipt_posted`` refreshes ONLY the affected
    supplier×product's ``supplier_performance`` (others untouched) and swallows
    scoring errors so it can never block the GR commit that triggered it.

The scoped-refresh maths itself is blessed in ``test_m2_supplier_perf.py``; here we
assert the TRIGGER wiring around it.
"""
from __future__ import annotations

import json
import os
import types
from datetime import date

from sqlalchemy import text

from app.scheduler.task_scheduler import _handler_scm_analytics
from app.services.scm import analytics_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m2_supplier_perf import (
    AS_OF,
    _build_fixture,
    _row,
    _set_scoring_policy,
)

pytestmark = requires_pg

_GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "golden_m2.json")))
_AS_OF = date.fromisoformat(_GOLDEN["as_of"])


def _pid(db, code):
    return db.execute(text("SELECT id FROM products WHERE product_code = :c"), {"c": code}).scalar()


def _fake_task(metadata: dict | None):
    """Minimal stand-in for a ScheduledTask row - only ``metadata_`` is read."""
    return types.SimpleNamespace(metadata_=metadata)


# ---------------------------------------------------------------------------
# 1. Scheduled full run - scm_analytics handler
# ---------------------------------------------------------------------------

def test_scheduled_handler_runs_analytics_and_logs_success(scm_app):
    """The scm_analytics scheduled callable runs run_analytics and leaves a
    completed scm_analytics_run row. Scope/config are read from task metadata."""
    _, db, _, _ = scm_app
    pid = _pid(db, _GOLDEN["demand"][0]["product_code"])
    task = _fake_task({"scope": {"product_ids": [str(pid)]},
                       "config": {"as_of": _AS_OF.isoformat()}})

    result = _handler_scm_analytics(db, task)

    assert result["status"] == "completed"
    row = db.execute(text(
        "SELECT status, error_text FROM scm.scm_analytics_run WHERE id = :id"
    ), {"id": result["run_id"]}).fetchone()
    assert row is not None
    assert row.status == "completed"
    assert row.error_text is None


def test_scheduled_handler_defaults_to_full_run_when_no_metadata(scm_app):
    """No metadata => full-catalog run as of today (nightly default) still logs a row."""
    _, db, _, _ = scm_app
    result = _handler_scm_analytics(db, _fake_task(None))
    assert result["status"] == "completed"
    status = db.execute(text(
        "SELECT status FROM scm.scm_analytics_run WHERE id = :id"
    ), {"id": result["run_id"]}).scalar()
    assert status == "completed"


def test_scheduled_handler_writes_failed_row_on_exception(scm_app, monkeypatch):
    """A failure during the run stamps scm_analytics_run.status='failed' + error_text
    and re-raises (heartbeat catches -> scheduler stays alive)."""
    _, db, _, _ = scm_app

    def _boom(_db):
        raise RuntimeError("boom: injected analytics failure")

    # ensure_policy_defaults runs inside run_analytics' try block, AFTER the run-log
    # row is opened -> the failure path stamps that row 'failed'.
    monkeypatch.setattr(svc, "ensure_policy_defaults", _boom)

    raised = False
    try:
        _handler_scm_analytics(db, _fake_task({"config": {"as_of": _AS_OF.isoformat()}}))
    except RuntimeError:
        raised = True
    assert raised, "handler must re-raise so the scheduled-task run is marked failed"

    row = db.execute(text(
        "SELECT status, error_text FROM scm.scm_analytics_run "
        "WHERE status = 'failed' ORDER BY started_at DESC LIMIT 1"
    )).fetchone()
    assert row is not None
    assert row.status == "failed"
    assert row.error_text and "boom" in row.error_text


# ---------------------------------------------------------------------------
# 2. On-GR hook - on_goods_receipt_posted
# ---------------------------------------------------------------------------

def test_on_gr_hook_refreshes_only_affected_pair(scm_app):
    """AC-M2.11 via the trigger wrapper: posting a GR refreshes only that
    supplier×product, leaving other suppliers' rows untouched."""
    _, db, _, _ = scm_app
    f = _build_fixture(db)
    _set_scoring_policy(db)

    # nothing computed yet
    assert _row(db, f["s2"], f["p3"]) is None
    assert _row(db, f["s1"], f["p1"]) is None

    written = svc.on_goods_receipt_posted(db, f["s2"], f["p3"], config={"as_of": AS_OF})
    assert written >= 1

    # only S2×P3 was recomputed
    assert _row(db, f["s2"], f["p3"]) is not None
    assert _row(db, f["s1"], f["p1"]) is None


def test_on_gr_hook_swallows_scoring_errors(scm_app, monkeypatch):
    """A scoring failure must never propagate out of the GR-post trigger."""
    _, db, _, _ = scm_app

    def _boom(*_a, **_k):
        raise RuntimeError("scoring exploded")

    monkeypatch.setattr(svc, "refresh_supplier_performance", _boom)

    # must NOT raise and must report zero rows written
    written = svc.on_goods_receipt_posted(db, "00000000-0000-0000-0000-000000000000", None)
    assert written == 0
