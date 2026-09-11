"""PLAN-reorder-one-formula.md, S3 - one scope, stored: `scm.reorder_recommendation`
gains a `hidden_by_default BOOLEAN NOT NULL DEFAULT false` column, backfilled by the SQL
twin of `app.services.scm.plan_scope.hidden_by_default` (the Python rule stays the only
RUNTIME source; the migration's SQL is a one-off backfill). `reorder_run_service` stamps
the column at write time; `run_log.recommendation_count`, `decision_service._refresh_run_
counts`' planned figure, the recommendations serializer and `list_plan_row_decisions`'s
total all read the column instead of recomputing the rule (three independent
re-derivations is exactly what drifted apart per the owner's 10 Sep measurement: list 415,
tile "0 of 950", sheet 950).

Both tests are red today because the column does not exist anywhere yet - a bare `SELECT
hidden_by_default FROM scm.reorder_recommendation` is an `UndefinedColumn`, not a
false-positive pass.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.services.scm import plan_scope
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_channel_read_model import _core_line_for_run
from tests.scm.test_m3_run import _link, _mk_demand, _mk_product, _mk_stock, _mk_supplier, _mk_warehouse
from tests.scm.test_reorder_level_run import _use_level_basis
from tests.scm.test_reorder_one_formula import _code, _product, _run, _wh
from tests.scm.test_reorder_per_product import _set_level

pytestmark = requires_pg

MARKER = "ZZTHIDCOL"

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load_migration():
    """The 512 migration module, loaded off disk the way `test_demand_class_backfill_
    migration.py` loads 425 - alembic revisions are not an importable package."""
    spec = importlib.util.spec_from_file_location(
        "512_hidden_by_default_col", _VERSIONS / "512_hidden_by_default_col.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- AC-11: the column exists, is backfilled, and matches the Python rule -------------

def test_backfill_matches_python_rule(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)

    # A covered-above-level product: hidden by the Python rule.
    hid_wid, hid_code = _wh(db, "HID")
    hid_pid, hid_pcode = _product(db)
    _set_level(db, hid_pid, None, 100)
    _mk_stock(db, hid_pid, hid_wid, 200)
    _mk_demand(db, hid_pid, hid_wid, 0.0)
    _link(db, hid_pid, _mk_supplier(db, f"{MARKER} hid"), moq=None, mult=None)

    # A buy: never hidden (rec_type != 'covered').
    buy_wid, buy_code = _wh(db, "BUY")
    buy_pid, buy_pcode = _product(db)
    _set_level(db, buy_pid, None, 100)
    _mk_stock(db, buy_pid, buy_wid, 10)
    _mk_demand(db, buy_pid, buy_wid, 0.0)
    _link(db, buy_pid, _mk_supplier(db, f"{MARKER} buy"), moq=None, mult=None)
    db.flush()

    run_id = _run(db, [hid_code], hid_pcode)
    run_id2 = _run(db, [buy_code], buy_pcode)

    # This is the red assertion: the column must exist before anything else here can be
    # checked at all. A from-zero database (no migration yet) fails this with
    # `UndefinedColumn`, which is the right reason - not a fixture bug.
    try:
        rows = db.execute(text(
            "SELECT id, rec_type, hidden_by_default, net_position, inputs "
            "FROM scm.reorder_recommendation WHERE run_id IN (:r1, :r2)"
        ), {"r1": run_id, "r2": run_id2}).mappings().all()
    except ProgrammingError as exc:
        raise AssertionError(
            "scm.reorder_recommendation.hidden_by_default does not exist yet - "
            f"add the S3 migration: {exc}"
        ) from exc

    assert rows, "the two runs above must have produced at least one recommendation each"
    for row in rows:
        inputs = row["inputs"] or {}
        expected = plan_scope.hidden_by_default(
            rec_type=row["rec_type"],
            policy_type=inputs.get("policy_type"),
            reorder_level=inputs.get("reorder_level"),
            master_reorder_level=inputs.get("master_reorder_level"),
            net_position=(
                float(row["net_position"]) if row["net_position"] is not None else None
            ),
        )
        assert row["hidden_by_default"] is expected, (
            f"row {row['id']} ({row['rec_type']}): stored {row['hidden_by_default']!r}, "
            f"the Python rule says {expected!r}"
        )

    # NOT NULL DEFAULT false: the information_schema contract the migration must add.
    col = db.execute(text(
        "SELECT is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = 'scm' AND table_name = 'reorder_recommendation' "
        "AND column_name = 'hidden_by_default'"
    )).mappings().first()
    assert col is not None
    assert col["is_nullable"] == "NO"
    assert col["column_default"] is not None and "false" in col["column_default"].lower()


# --- AC-12: the three counters read the column, not three re-derivations --------------

def test_run_counts_read_the_column(scm_app):
    """3 products: 2 buys (never hidden - `rec_type != 'covered'`) and 1 covered row
    whose stock sits well above its level (hidden). Every counter must agree: 2.

    A `covered` row is only ever emitted when there is committed demand to weigh against
    the stock (`_covered_rec` returns `None` on a product with none at all - "genuinely
    nothing to say", not a decision withheld) - so the hidden row carries a small
    committed line precisely so it exists to test against; its own net still clears the
    level by a wide margin, which is what makes it hidden.
    """
    app, db, gcu, gcuak = scm_app
    _use_level_basis(db)

    buy_wid, buy_code = _wh(db, "BUYC")
    buy_pid, buy_pcode = _product(db)
    _set_level(db, buy_pid, None, 100)
    _mk_stock(db, buy_pid, buy_wid, 10)
    _mk_demand(db, buy_pid, buy_wid, 0.0)
    _link(db, buy_pid, _mk_supplier(db, f"{MARKER} buyc"), moq=None, mult=None)

    hid_wid, hid_code = _wh(db, "HIDC")
    hid_pid, hid_pcode = _product(db)
    _set_level(db, hid_pid, None, 100)
    _mk_stock(db, hid_pid, hid_wid, 200)
    _mk_demand(db, hid_pid, hid_wid, 0.0)
    _link(db, hid_pid, _mk_supplier(db, f"{MARKER} hidc"), moq=None, mult=None)
    _core_line_for_run(db, hid_pid, hid_wid, qty=10, demand_class="retail")

    shown_wid, shown_code = _wh(db, "SHOWNC")
    shown_pid, shown_pcode = _product(db)
    _set_level(db, shown_pid, None, 50)
    _mk_stock(db, shown_pid, shown_wid, 5)
    _mk_demand(db, shown_pid, shown_wid, 0.0)
    _link(db, shown_pid, _mk_supplier(db, f"{MARKER} shownc"), moq=None, mult=None)
    db.flush()

    r1 = _run(db, [buy_code], buy_pcode)
    r2 = _run(db, [hid_code], hid_pcode)
    r3 = _run(db, [shown_code], shown_pcode)

    def _one_rec(run_id):
        return db.execute(text(
            "SELECT rec_type FROM scm.reorder_recommendation WHERE run_id = :r"
        ), {"r": run_id}).mappings().one()

    assert _one_rec(r1)["rec_type"] == "buy"
    assert _one_rec(r2)["rec_type"] == "covered"
    assert _one_rec(r3)["rec_type"] == "buy"

    # Fold the three runs' recs onto ONE run row so a single run_log/planned_count/
    # decisions total can be asked about all three at once, mirroring how the real
    # engine writes every product of one run under one run_id.
    folded = r1
    db.execute(text(
        "UPDATE scm.reorder_recommendation SET run_id = :folded "
        "WHERE run_id IN (:r2, :r3)"
    ), {"folded": folded, "r2": r2, "r3": r3})
    # A 4th row, on its own product, that no decision can ever be recorded on. It is a
    # LINE of the plan (`recommendation_count` counts it) but not a decidable product
    # (`planned_count` must not). Written straight in: how an exception comes to exist is
    # `_emit_product`'s business, and this test is about the migration's own SQL.
    exc_pid, _exc_pcode = _product(db)
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, status, inputs, created_at) "
        "VALUES (gen_random_uuid(), :run, :pid, NULL, 'exception', 'proposed', "
        "        '{}'::jsonb, now())"
    ), {"run": folded, "pid": exc_pid})
    db.flush()

    from app.models.scm import ReorderRecommendation
    recs = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.run_id == folded)
        .all()
    )
    assert len(recs) == 3

    from app.services.scm import reorder_run_service as svc
    counts = svc._summarise(recs)
    # This is the red assertion (today `_summarise` counts every rec, hidden or not).
    assert counts["recommendation_count"] == 2, (
        f"1 buy + 1 shown covered = 2; the hidden covered row must not inflate the "
        f"count: {counts}"
    )

    from app.services.scm import decision_service as dsvc
    dsvc._refresh_run_counts(db, folded)
    planned = db.execute(text(
        "SELECT planned_count FROM scm.reorder_run WHERE id = :r"
    ), {"r": folded}).scalar()
    assert planned == 2, f"_refresh_run_counts must also exclude the hidden row: {planned}"

    total = dsvc.list_plan_row_decisions(db, folded)["total_count"]
    assert total == 2, f"list_plan_row_decisions must count the same 2: {total}"

    uid = seed_user(db, "purchasing")
    as_user(app, gcu, gcuak, uid)
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/scm/reorder-runs/{folded}/recommendations?limit=50")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_pid = {r["product_id"]: r for r in body["data"]}
    assert by_pid[hid_pid]["hidden_by_default"] is True
    assert by_pid[buy_pid]["hidden_by_default"] is False
    assert by_pid[shown_pid]["hidden_by_default"] is False


# --- AC-14 gap: a run that already existed when 512 first ran kept its unscoped counts -

def test_backfill_recomputes_run_counts(scm_app):
    """The column landed on the recs, but a run's own `planned_count` / `run_log.
    recommendation_count` are stamped once, at write time (`reorder_run_service`) - a run
    written BEFORE this migration first shipped never had that write happen against the
    column, so it kept reading its old, unscoped numbers forever (826 on the owner's own
    11 Sep 07:30 run). This pins the migration's OWN backfill of those two counters,
    run directly rather than re-derived by `_refresh_run_counts` (which only a decision
    triggers) or `_summarise` (which only a fresh run's own write path calls).

    4 recs on one run: a buy, a covered row sitting well above its level (hidden), a shown
    covered row, and an `exception`. The two counters count DIFFERENT populations and the
    migration has to spell both - `planned_count` is a decision denominator, so it counts
    only the rec types a decision can be recorded on (`decision_service.
    _PLAN_ROW_DECIDABLE_TYPES`, which excludes `exception`), while
    `run_log.recommendation_count` is "lines on this plan" and counts an exception like any
    other (`_summarise`). Both counters are stamped "the old way" first (what a
    pre-migration run's stored numbers actually looked like), so the assertions are red
    until the migration's backfill runs.
    """
    _, db, _, _ = scm_app
    _use_level_basis(db)

    buy_wid, buy_code = _wh(db, "BUFBC")
    buy_pid, buy_pcode = _product(db)
    _set_level(db, buy_pid, None, 100)
    _mk_stock(db, buy_pid, buy_wid, 10)
    _mk_demand(db, buy_pid, buy_wid, 0.0)
    _link(db, buy_pid, _mk_supplier(db, f"{MARKER} bufbc"), moq=None, mult=None)

    hid_wid, hid_code = _wh(db, "HIFBC")
    hid_pid, hid_pcode = _product(db)
    _set_level(db, hid_pid, None, 100)
    _mk_stock(db, hid_pid, hid_wid, 200)
    _mk_demand(db, hid_pid, hid_wid, 0.0)
    _link(db, hid_pid, _mk_supplier(db, f"{MARKER} hifbc"), moq=None, mult=None)
    _core_line_for_run(db, hid_pid, hid_wid, qty=10, demand_class="retail")

    shown_wid, shown_code = _wh(db, "SHFBC")
    shown_pid, shown_pcode = _product(db)
    _set_level(db, shown_pid, None, 50)
    _mk_stock(db, shown_pid, shown_wid, 5)
    _mk_demand(db, shown_pid, shown_wid, 0.0)
    _link(db, shown_pid, _mk_supplier(db, f"{MARKER} shfbc"), moq=None, mult=None)
    db.flush()

    r1 = _run(db, [buy_code], buy_pcode)
    r2 = _run(db, [hid_code], hid_pcode)
    r3 = _run(db, [shown_code], shown_pcode)

    folded = r1
    db.execute(text(
        "UPDATE scm.reorder_recommendation SET run_id = :folded "
        "WHERE run_id IN (:r2, :r3)"
    ), {"folded": folded, "r2": r2, "r3": r3})
    # A 4th row, on its own product, that no decision can ever be recorded on. It is a
    # LINE of the plan (`recommendation_count` counts it) but not a decidable product
    # (`planned_count` must not). Written straight in: how an exception comes to exist is
    # `_emit_product`'s business, and this test is about the migration's own SQL.
    exc_pid, _exc_pcode = _product(db)
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, status, inputs, created_at) "
        "VALUES (gen_random_uuid(), :run, :pid, NULL, 'exception', 'proposed', "
        "        '{}'::jsonb, now())"
    ), {"run": folded, "pid": exc_pid})
    # Stamp the run "completed" with the OLD, unscoped numbers - what a run written before
    # this migration first ran actually has stored today.
    db.execute(text(
        "UPDATE scm.reorder_run "
        "SET status = 'completed', planned_count = 4, "
        "    run_log = jsonb_set(COALESCE(run_log, '{}'::jsonb), '{recommendation_count}', '4'::jsonb) "
        "WHERE id = :r"
    ), {"r": folded})
    db.flush()

    conn = db.connection()
    ops = Operations(MigrationContext.configure(conn))
    import alembic.op as op_module
    op_module._proxy = ops
    _load_migration()._backfill_run_counts()

    row = db.execute(text(
        "SELECT planned_count, run_log ->> 'recommendation_count' AS rec_count "
        "FROM scm.reorder_run WHERE id = :r"
    ), {"r": folded}).mappings().one()
    assert row["planned_count"] == 2, (
        f"1 buy + 1 shown covered = 2; neither the hidden covered row nor the exception "
        f"(no quantity anybody can decide) may inflate the already-existing run's "
        f"planned_count: {row}"
    )
    assert row["rec_count"] == "3", (
        f"recommendation_count is LINES, not decidable products - the exception counts, "
        f"only the hidden covered row drops out: {row}"
    )

    # Idempotent: running it again gives the same result, never a second decrement.
    _load_migration()._backfill_run_counts()
    row2 = db.execute(text(
        "SELECT planned_count, run_log ->> 'recommendation_count' AS rec_count "
        "FROM scm.reorder_run WHERE id = :r"
    ), {"r": folded}).mappings().one()
    assert row2["planned_count"] == 2
    assert row2["rec_count"] == "3"
