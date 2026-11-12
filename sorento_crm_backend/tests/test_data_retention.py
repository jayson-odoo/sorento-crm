"""DB-RETENTION: plan exceptions, superseded reorder runs, settings, seeds and handlers.

Plan: documentation/plans/infra/PLAN-db-retention-12nov.md (section 2 rules, section 7
contract). UAC: documentation/plans/infra/db-retention-acceptance-criteria.md.

Rule tests run on the blank Postgres schema (``blank_session``), so every table starts
empty and the counts a rule returns are exactly the rows this test seeded. The session is
put under scope ``None`` (all companies), which is what the scheduler gives a task run
(``scheduled_task_service``), so a scoped query inside the rule sees every company.

The migration test runs the new migration's upgrade() on the blank schema (see its
docstring for why not the shared database).

The service module is imported inside each test, not at module top, so a missing module
fails each test on its own rather than turning the whole file into a collection error.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import (
    PlanException,
    PlanExceptionBatch,
    OrderSummaryRow,
    PlanRowDecision,
    RecommendationOverride,
    ReorderRecommendation,
    ReorderRun,
)
from tests._pg_fixture import blank_session

MARKER = "ZZTDBR"


def _svc():
    from app.services import data_retention_service

    return data_retention_service


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _ago(*, days: float = 0, hours: float = 0) -> datetime:
    return datetime.utcnow() - timedelta(days=days, hours=hours)


def _pk(obj) -> str:
    """The primary key without touching an expired attribute: reading ``obj.id`` after a
    rule deleted the row raises ObjectDeletedError, which is not the assertion's point."""
    return str(sa_inspect(obj).identity[0])


def _counts(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in ("dry_run", "finished")}


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        yield s


@pytest.fixture
def product(db):
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    p = Product(
        id=_u(), product_code=_code("P"), product_name=f"{MARKER} product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(p)
    db.flush()
    return p


# --------------------------------------------------------------------------- #
# R1 plan exceptions
# --------------------------------------------------------------------------- #

def _run(db, *, days_ago: float = 0, superseded_by: str | None = None) -> ReorderRun:
    run = ReorderRun(
        id=_u(), status="completed", created_at=_ago(days=days_ago),
        superseded_by_run_id=superseded_by,
    )
    db.add(run)
    db.flush()
    return run


def _batch(db, *, run_id, days: float = 0, hours: float = 0) -> PlanExceptionBatch:
    at = _ago(days=days, hours=hours)
    b = PlanExceptionBatch(
        id=_u(), run_id=run_id, as_of=at.date(), generated_at=at, created_at=at, delta_count=0,
    )
    db.add(b)
    db.flush()
    return b


def _exc(db, batch, product, *, status="open", decided_at=None) -> PlanException:
    e = PlanException(
        id=_u(), batch_id=batch.id, product_id=product.id,
        exception_type="shortfall_earlier", quantity=1,
        status=status, decided_at=decided_at,
    )
    db.add(e)
    db.flush()
    return e


def _exc_ids(db, batch) -> set[str]:
    return {
        str(i) for (i,) in db.query(PlanException.id).filter(PlanException.batch_id == _pk(batch))
    }


def _batch_exists(db, batch) -> bool:
    return db.query(PlanExceptionBatch.id).filter(PlanExceptionBatch.id == _pk(batch)).count() == 1


def test_older_batch_loses_undecided_rows_and_empty_batch_is_removed(db, product):
    """UAC 5: the newest batch of a run keeps every row; an older batch's undecided rows go,
    and the batch they emptied goes with them."""
    run = _run(db)
    newest = _batch(db, run_id=run.id, days=10)
    older = _batch(db, run_id=run.id, days=20)
    keep = {_exc(db, newest, product).id, _exc(db, newest, product).id}
    _exc(db, older, product)
    _exc(db, older, product)
    db.commit()

    result = _svc().prune_plan_exceptions(db, grace_days=1)

    assert result["rows_deleted"] == 2
    assert result["batches_deleted"] == 1
    assert result["dry_run"] is False and result["finished"] is True
    assert _exc_ids(db, newest) == {str(i) for i in keep}
    assert not _batch_exists(db, older)


def test_newest_batch_of_each_run_is_kept_even_when_old(db, product):
    """A run's only (so newest) batch is what the screen reads for that run, however old."""
    run = _run(db, days_ago=400)
    only = _batch(db, run_id=run.id, days=400)
    _exc(db, only, product)
    db.commit()

    result = _svc().prune_plan_exceptions(db, grace_days=1)

    assert result["rows_deleted"] == 0 and result["batches_deleted"] == 0
    assert len(_exc_ids(db, only)) == 1


def test_batches_with_no_run_form_one_group_whose_newest_is_kept(db, product):
    """Batches with run_id NULL are one group: its newest is kept even when a batch of some
    run is newer overall, and the older NULL-run batch is pruned."""
    run = _run(db)
    run_batch = _batch(db, run_id=run.id, days=1)
    null_newest = _batch(db, run_id=None, days=5)
    null_older = _batch(db, run_id=None, days=15)
    _exc(db, run_batch, product)
    kept = _exc(db, null_newest, product)
    _exc(db, null_older, product)
    db.commit()

    result = _svc().prune_plan_exceptions(db, grace_days=1)

    assert result["rows_deleted"] == 1 and result["batches_deleted"] == 1
    assert _exc_ids(db, null_newest) == {str(kept.id)}
    assert len(_exc_ids(db, run_batch)) == 1
    assert not _batch_exists(db, null_older)


def test_decided_plan_exception_rows_are_never_deleted(db, product):
    """UAC 5: a row with a decision (status not open, OR a decision time) is NEVER deleted,
    and its batch stays even though it is an older batch."""
    run = _run(db)
    _exc(db, _batch(db, run_id=run.id, days=5), product)
    older = _batch(db, run_id=run.id, days=30)
    _exc(db, older, product)  # open, undecided: the only row that goes
    decided = {
        _exc(db, older, product, status="approved", decided_at=_ago(days=29)).id,
        _exc(db, older, product, status="rejected").id,
        _exc(db, older, product, status="open", decided_at=_ago(days=28)).id,
    }
    db.commit()

    result = _svc().prune_plan_exceptions(db, grace_days=1)

    assert result["rows_deleted"] == 1
    assert result["batches_deleted"] == 0
    assert _batch_exists(db, older)
    assert _exc_ids(db, older) == {str(i) for i in decided}


def test_old_batch_with_one_decided_row_keeps_that_row_and_the_batch(db, product):
    """Crew ruling: an OLD batch holding one decided row keeps that row AND the batch row;
    its undecided siblings may go."""
    run = _run(db, days_ago=400)
    _exc(db, _batch(db, run_id=run.id, days=300), product)
    old = _batch(db, run_id=run.id, days=400)
    decided = _exc(db, old, product, status="approved", decided_at=_ago(days=399))
    _exc(db, old, product)
    _exc(db, old, product)
    db.commit()

    result = _svc().prune_plan_exceptions(db)

    assert result["rows_deleted"] == 2 and result["batches_deleted"] == 0
    assert _batch_exists(db, old)
    assert _exc_ids(db, old) == {str(decided.id)}


def test_grace_days_keeps_a_batch_superseded_within_the_grace(db, product):
    """An older batch generated inside the grace is kept; outside it, pruned."""
    run = _run(db)
    _exc(db, _batch(db, run_id=run.id, hours=1), product)
    recent_older = _batch(db, run_id=run.id, hours=12)
    _exc(db, recent_older, product)
    db.commit()

    kept = _svc().prune_plan_exceptions(db, grace_days=1)
    assert kept["rows_deleted"] == 0 and kept["batches_deleted"] == 0
    assert _batch_exists(db, recent_older)

    pruned = _svc().prune_plan_exceptions(db, grace_days=0)
    assert pruned["rows_deleted"] == 1 and pruned["batches_deleted"] == 1
    assert not _batch_exists(db, recent_older)


def test_plan_exception_dry_run_counts_match_live_run_and_change_nothing(db, product):
    """UAC 2 + 3: dry-run reports what the live run then does, and writes nothing."""
    run = _run(db)
    _exc(db, _batch(db, run_id=run.id, days=1), product)
    older = _batch(db, run_id=run.id, days=10)
    _exc(db, older, product)
    _exc(db, older, product)
    half = _batch(db, run_id=run.id, days=20)
    _exc(db, half, product)
    _exc(db, half, product, status="approved", decided_at=_ago(days=19))
    db.commit()
    rows_before = db.query(PlanException).count()
    batches_before = db.query(PlanExceptionBatch).count()

    dry = _svc().prune_plan_exceptions(db, grace_days=1, dry_run=True)

    assert dry["dry_run"] is True and dry["finished"] is True
    assert db.query(PlanException).count() == rows_before
    assert db.query(PlanExceptionBatch).count() == batches_before

    live = _svc().prune_plan_exceptions(db, grace_days=1, dry_run=False)

    assert live["dry_run"] is False
    assert _counts(dry) == _counts(live)
    assert live["rows_deleted"] == 3 and live["batches_deleted"] == 1


def test_plan_exception_small_batch_size_still_finishes(db, product):
    run = _run(db)
    _exc(db, _batch(db, run_id=run.id, days=1), product)
    a = _batch(db, run_id=run.id, days=10)
    b = _batch(db, run_id=run.id, days=20)
    for batch in (a, a, b):
        _exc(db, batch, product)
    db.commit()

    result = _svc().prune_plan_exceptions(db, grace_days=1, batch_size=1)

    assert result["finished"] is True
    assert result["rows_deleted"] == 3 and result["batches_deleted"] == 2
    assert not _batch_exists(db, a) and not _batch_exists(db, b)


def test_plan_exception_time_budget_stops_after_one_batch_and_next_run_continues(db, product):
    """UAC 4: the budget is checked between batches, so max_seconds=0 does exactly one
    batch, reports finished False, and the next run carries on with nothing lost."""
    run = _run(db)
    _exc(db, _batch(db, run_id=run.id, days=1), product)
    older = _batch(db, run_id=run.id, days=10)
    for _ in range(3):
        _exc(db, older, product)
    db.commit()

    first = _svc().prune_plan_exceptions(db, grace_days=1, batch_size=1, max_seconds=0)

    assert first["finished"] is False
    assert first["rows_deleted"] == 1
    assert len(_exc_ids(db, older)) == 2
    assert _batch_exists(db, older)

    second = _svc().prune_plan_exceptions(db, grace_days=1, batch_size=1)

    assert second["finished"] is True
    assert second["rows_deleted"] == 2 and second["batches_deleted"] == 1
    assert not _batch_exists(db, older)


# --------------------------------------------------------------------------- #
# R3c superseded reorder runs
# --------------------------------------------------------------------------- #

def _rec(db, run, product) -> ReorderRecommendation:
    r = ReorderRecommendation(id=_u(), run_id=run.id, product_id=product.id, rec_type="buy")
    db.add(r)
    db.flush()
    return r


def _run_exists(db, run) -> bool:
    return db.query(ReorderRun.id).filter(ReorderRun.id == _pk(run)).count() == 1


def test_superseded_old_run_is_deleted_with_its_recommendations(db, product):
    """UAC 9: the superseded run past the window goes, and its recommendations with it."""
    current = _run(db, days_ago=400)  # current (not superseded) and old: never deleted
    old = _run(db, days_ago=120, superseded_by=current.id)
    _rec(db, old, product)
    _rec(db, old, product)
    _rec(db, current, product)
    db.add(OrderSummaryRow(
        id=_u(), run_id=old.id, product_id=product.id,
        as_of=_ago(days=120).date(), computed_at=_ago(days=120),
    ))
    db.commit()

    result = _svc().prune_reorder_runs(db, retention_days=90)

    assert result["runs_deleted"] == 1
    assert db.query(OrderSummaryRow).filter(OrderSummaryRow.run_id == _pk(old)).count() == 0
    assert result["dry_run"] is False and result["finished"] is True
    assert not _run_exists(db, old)
    assert db.query(ReorderRecommendation).filter(ReorderRecommendation.run_id == _pk(old)).count() == 0
    assert _run_exists(db, current)
    assert db.query(ReorderRecommendation).filter(ReorderRecommendation.run_id == current.id).count() == 1


def test_current_run_is_never_deleted_even_when_old(db):
    current = _run(db, days_ago=1000)
    db.commit()

    result = _svc().prune_reorder_runs(db, retention_days=90)

    assert result["runs_deleted"] == 0
    assert _run_exists(db, current)


def test_superseded_run_inside_the_window_is_kept(db):
    current = _run(db)
    recent = _run(db, days_ago=10, superseded_by=current.id)
    db.commit()

    result = _svc().prune_reorder_runs(db, retention_days=90)

    assert result["runs_deleted"] == 0
    assert _run_exists(db, recent)


def test_superseded_old_run_with_an_override_is_kept(db, product):
    """UAC 9: a person overrode something on it, so it stays."""
    current = _run(db)
    old = _run(db, days_ago=200, superseded_by=current.id)
    rec = _rec(db, old, product)
    db.add(RecommendationOverride(id=_u(), recommendation_id=rec.id, original_qty=5, override_qty=3))
    db.commit()

    result = _svc().prune_reorder_runs(db, retention_days=90)

    assert result["runs_deleted"] == 0
    assert _run_exists(db, old)


def test_superseded_old_run_with_a_plan_row_decision_is_kept(db, product):
    """UAC 9: a person decided a row on it, so it stays."""
    current = _run(db)
    old = _run(db, days_ago=200, superseded_by=current.id)
    rec = _rec(db, old, product)
    db.add(PlanRowDecision(id=_u(), recommendation_id=rec.id, kind="buy", buy_qty=2))
    db.commit()

    result = _svc().prune_reorder_runs(db, retention_days=90)

    assert result["runs_deleted"] == 0
    assert _run_exists(db, old)


def _three_superseded_old_runs(db, product) -> list[ReorderRun]:
    current = _run(db)
    runs = []
    for days in (100, 200, 300):
        run = _run(db, days_ago=days, superseded_by=current.id)
        _rec(db, run, product)
        runs.append(run)
    db.commit()
    return runs


def test_reorder_run_dry_run_counts_match_live_run_and_change_nothing(db, product):
    runs = _three_superseded_old_runs(db, product)
    recs_before = db.query(ReorderRecommendation).count()

    dry = _svc().prune_reorder_runs(db, retention_days=90, dry_run=True)

    assert dry["dry_run"] is True and dry["finished"] is True
    assert all(_run_exists(db, r) for r in runs)
    assert db.query(ReorderRecommendation).count() == recs_before

    live = _svc().prune_reorder_runs(db, retention_days=90)

    assert _counts(dry) == _counts(live)
    assert live["runs_deleted"] == 3


def test_reorder_run_small_batch_size_still_finishes(db, product):
    runs = _three_superseded_old_runs(db, product)

    result = _svc().prune_reorder_runs(db, retention_days=90, batch_size=1)

    assert result["finished"] is True and result["runs_deleted"] == 3
    assert not any(_run_exists(db, r) for r in runs)


def test_reorder_run_time_budget_stops_inside_a_run_and_next_run_finishes_it(db, product):
    """Crew ruling: a run's children (recommendations, order summary rows) are deleted in
    keyset batches of batch_size, one commit each, then the run row - no single long
    transaction. With batch_size=1 and max_seconds=0 a run with 3 recommendations stops
    after one batch, finished False; a later call finishes it."""
    current = _run(db)
    old = _run(db, days_ago=200, superseded_by=current.id)
    for _ in range(3):
        _rec(db, old, product)
    db.commit()

    def recs_left() -> int:
        return db.query(ReorderRecommendation).filter(ReorderRecommendation.run_id == _pk(old)).count()

    first = _svc().prune_reorder_runs(db, retention_days=90, batch_size=1, max_seconds=0)

    assert first["finished"] is False
    assert first["runs_deleted"] == 0
    assert _run_exists(db, old)
    assert recs_left() == 2

    second = _svc().prune_reorder_runs(db, retention_days=90, batch_size=1)

    assert second["finished"] is True and second["runs_deleted"] == 1
    assert not _run_exists(db, old)
    assert recs_left() == 0
    assert _run_exists(db, current)


# --------------------------------------------------------------------------- #
# Settings (UAC 13), seeds (UAC 1), handlers
# --------------------------------------------------------------------------- #

SETTING_DEFAULTS = {
    "integration_log_payload_retention_days": 30,
    "integration_log_row_retention_days": 180,
    "chatbot_turn_trace_retention_days": 90,
    "scheduled_task_run_retention_days": 90,
    "reorder_run_retention_days": 90,
    "embedding_superseded_retention_days": 90,
    "plan_exception_superseded_grace_days": 1,
    "data_retention_dry_run": False,  # crew ruling: live by default
    "data_retention_batch_size": 5000,
    "data_retention_batch_sleep_ms": 200,
    "data_retention_max_run_minutes": 30,
}

NEW_TASK_KEYS = [
    "plan_exception_prune",
    "integration_log_prune",
    "chatbot_turn_trace_prune",
    "scheduled_task_runs_prune",
    "reorder_run_prune",
    "embedding_superseded_prune",
]
SEEDED_TASK_KEYS = NEW_TASK_KEYS + ["import_job_rows_prune"]


def test_system_settings_model_carries_every_retention_setting_with_its_default(db):
    from app.models.user import SystemSetting

    missing = [name for name in SETTING_DEFAULTS if not hasattr(SystemSetting, name)]
    assert missing == [], f"SystemSetting lacks {missing}"

    row = SystemSetting()
    db.add(row)
    db.flush()
    db.refresh(row)
    assert {name: getattr(row, name) for name in SETTING_DEFAULTS} == SETTING_DEFAULTS


VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _retention_migration():
    """The one new migration (plan section 7), found by what it seeds rather than by a file
    name the tester cannot know before the coder writes it."""
    files = [
        p for p in VERSIONS.glob("*.py")
        if "plan_exception_prune" in p.read_text(encoding="utf-8")
    ]
    assert len(files) == 1, f"expected one migration seeding plan_exception_prune, found {files}"
    spec = importlib.util.spec_from_file_location("_db_retention_migration", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_adds_settings_columns_and_seeds_every_retention_task(db):
    """UAC 1 + 13, against the migration itself rather than the ORM.

    Run on the blank schema, NOT the shared database: a CI database is built by
    ``create_all`` and stamped at head (scripts/bootstrap_env.py), so a migration's seed
    rows are never in it and asserting them there would fail for a reason unrelated to
    this lane. The blank schema already carries the model's columns, so they are dropped
    first to stand in for a database at the previous head (all rolled back afterwards).
    """
    m = _retention_migration()
    assert len(m.revision) <= 32
    for name in SETTING_DEFAULTS:
        db.execute(text(f"ALTER TABLE system_settings DROP COLUMN IF EXISTS {name}"))
    db.execute(text("DELETE FROM scheduled_tasks"))

    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        m.upgrade()

    cols = {
        name: (default, nullable)
        for name, default, nullable in db.execute(text(
            "SELECT column_name, column_default, is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'system_settings'"
        ))
    }
    missing = [name for name in SETTING_DEFAULTS if name not in cols]
    assert missing == [], f"migration does not add {missing}"
    for name, value in SETTING_DEFAULTS.items():
        default, nullable = cols[name]
        assert nullable == "NO", name
        expected = str(value).lower()
        assert default is not None and expected in str(default).lower(), (name, default)

    rows = {
        key: (unit, value)
        for key, unit, value in db.execute(text(
            "SELECT key, interval_unit, interval_value FROM scheduled_tasks"
        ))
    }
    missing = [k for k in SEEDED_TASK_KEYS if k not in rows]
    assert missing == [], f"migration does not seed {missing}"
    for key in SEEDED_TASK_KEYS:
        assert rows[key] == ("days", 1), (key, rows[key])


@pytest.mark.parametrize("key", SEEDED_TASK_KEYS)
def test_every_retention_task_has_a_handler(key):
    from app.scheduler import task_scheduler

    assert callable(getattr(task_scheduler, f"_handler_{key}", None)), f"_handler_{key} missing"


def test_new_retention_handlers_are_registered_off_the_heartbeat_thread():
    """A long prune must never block the 10 s heartbeat: background=True."""
    from app.scheduler.task_scheduler import register_task_handlers
    from app.services import scheduled_task_service as sts

    register_task_handlers()
    for key in SEEDED_TASK_KEYS:
        assert key in sts.TASK_HANDLERS, key
    not_background = [k for k in NEW_TASK_KEYS if k not in sts.BACKGROUND_TASK_KEYS]
    assert not_background == [], f"not background: {not_background}"


def test_handler_honours_the_dry_run_setting(db):
    """UAC 2/3/13: the handler reads data_retention_dry_run from settings."""
    from app.models.integration import IntegrationLog
    from app.models.user import SystemSetting
    from app.scheduler.task_scheduler import _handler_integration_log_prune

    settings = SystemSetting(data_retention_dry_run=True)
    db.add(settings)
    old = IntegrationLog(
        integration_channel="zzt", business_table="zzt", business_id=_u(),
        direction="outbound", endpoint="/zzt", http_method="POST", status="success",
        request_payload="body", created_at=_ago(days=400),
    )
    db.add(old)
    db.commit()

    dry = _handler_integration_log_prune(db, None)
    assert dry["dry_run"] is True and dry["rows_deleted"] == 1
    assert db.query(IntegrationLog).filter(IntegrationLog.id == _pk(old)).count() == 1

    settings.data_retention_dry_run = False
    db.commit()
    live = _handler_integration_log_prune(db, None)
    assert live["dry_run"] is False and live["rows_deleted"] == 1
    assert db.query(IntegrationLog).filter(IntegrationLog.id == _pk(old)).count() == 0
