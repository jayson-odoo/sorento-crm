"""S7 (PLAN-reorder-feedback-9sep.md, G1 ruling 9 Sep 2026) - the AutoCount level reads
retail deliveries only.

"Retail deliveries = delivery-order lines shipped from a `dealer`-segment warehouse. A
line shipped from a `project` bin (BRW-IB, BRW-BB, ...) is a project delivery." Applies to
the LEVEL suggestion (ADU) only - health (`movement_class`) stays on all deliveries
(unchanged, out of scope here).

Harness adapted from `tests/scm/test_reorder_level_formula.py`'s `_world`/`_do` (the
delivery-order fixture that already exercises `scm.consumption_v`), split across a
`dealer` bin and a `project` bin instead of two `project` bins, so a `retail_only` read
has something real to disagree with an unfiltered one about.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.services.scm import level_suggestion_service as lsvc
from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_level_service as rl
from tests._pg_fixture import pg_session, unique_code
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

MARKER = "ZZTRETADU"
AS_OF = date(2026, 8, 10)


def _u() -> str:
    return str(uuid.uuid4())


def _do(db, pid, wid, *, day: date, qty: float) -> None:
    oid = _u()
    db.execute(text(
        "INSERT INTO orders (id, order_number, order_date, is_cancelled, kpi_warning, "
        "subtotal_amount, discount_amount, tax_amount, total_amount, synced_to_excel, "
        "created_at, updated_at) "
        "VALUES (:id, :n, :d, false, false, 0, 0, 0, 0, false, now(), now())"),
        {"id": oid, "n": f"{MARKER}-{oid[:8]}", "d": day})
    db.execute(text(
        "INSERT INTO order_lines (id, line_sequence, order_id, product_id, warehouse_id, "
        "quantity, created_at, updated_at) VALUES (:id, 1, :o, :p, :w, :q, now(), now())"),
        {"id": _u(), "o": oid, "p": pid, "w": wid, "q": qty})


def _world(db):
    """One product, one `project`-bin (100 shipped) and one `dealer`-bin (10 shipped) in
    the 90-day window - AC-S7.3's own numbers."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    eng.ensure_reorder_policy_defaults(db)

    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    from app.models.product import Product as _P
    product = _P(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                category_id=cat.id, base_uom_id=uom.id, list_price=0,
                is_active=True, is_discontinued=False)
    db.add(product)
    db.flush()
    pid = str(product.id)

    project_wid = _u()
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available, segment) VALUES (:id, :c, :c, true, true, 'project')"),
        {"id": project_wid, "c": unique_code("W")[:20]})
    dealer_wid = _u()
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available, segment) VALUES (:id, :c, :c, true, true, 'dealer')"),
        {"id": dealer_wid, "c": unique_code("W")[:20]})

    _do(db, pid, project_wid, day=date(2026, 7, 1), qty=100)
    _do(db, pid, dealer_wid, day=date(2026, 7, 1), qty=10)

    run_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
        "VALUES (:id, 'completed', false, now())"), {"id": run_id})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status) "
        "VALUES (:id, :r, :p, :w, 'needs_level', 0, 'proposed')"),
        {"id": _u(), "r": run_id, "p": pid, "w": dealer_wid})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "project_wid": project_wid,
            "dealer_wid": dealer_wid}


# --- AC-S7.1: the arithmetic reads dealer-segment deliveries only -------------------

def test_average_daily_usage_retail_only_reads_the_dealer_bin_alone():
    with pg_session() as db:
        w = _world(db)

        usage = rl.average_daily_usage(
            db, [w["product_id"]], as_of=AS_OF, retail_only=True,
        )

        assert usage[w["product_id"]]["window_qty"] == 10.0, (
            "the 100 shipped from the project bin must not lift the retail-only ADU"
        )
        assert usage[w["product_id"]]["adu"] == 10.0 / rl.LEVEL_WINDOW_DAYS


def test_average_daily_usage_unfiltered_still_reads_both_bins():
    """The unfiltered read (health, `movement_class`) is UNCHANGED - only the level's own
    call opts into `retail_only`."""
    with pg_session() as db:
        w = _world(db)

        usage = rl.average_daily_usage(db, [w["product_id"]], as_of=AS_OF)

        assert usage[w["product_id"]]["window_qty"] == 110.0


def test_monthly_movement_retail_only_excludes_the_project_bin():
    with pg_session() as db:
        w = _world(db)

        movement = rl.monthly_movement(
            db, [w["product_id"]], None, as_of=AS_OF, retail_only=True,
        )

        total = sum(m["qty"] for m in movement.get(w["product_id"], []))
        assert total == 10.0


# --- AC-S7.2: the run stamps basis.retail_only and uses the retail-only ADU ---------

def test_refresh_for_run_stamps_retail_only_and_sizes_off_the_dealer_bin_alone():
    with pg_session() as db:
        w = _world(db)

        written = lsvc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        assert written == 1

        row = db.execute(text(
            "SELECT suggested_level, suggestion_basis FROM scm.reorder_level "
            "WHERE product_id = :p AND warehouse_id = :w"
        ), {"p": w["product_id"], "w": w["dealer_wid"]}).mappings().first()
        assert row is not None

        basis = row["suggestion_basis"] or {}
        assert basis.get("retail_only") is True, (
            "the level's basis must state it was sized off retail deliveries only"
        )
        # ADU 10/90 x lead(30, unknown->fallback) + 10/90 x 14, rounded up - the level
        # must NOT be sized off the 110-unit unfiltered total.
        unfiltered_usage = rl.average_daily_usage(db, [w["product_id"]], as_of=AS_OF)
        unfiltered_level = rl.suggest_level_from_usage(
            adu=unfiltered_usage[w["product_id"]]["adu"], lead_time_days=None,
        )["level"]
        assert float(row["suggested_level"]) != unfiltered_level


# --- Phase 3 fix round, S7: ONE level rule everywhere -------------------------------

def test_refresh_suggestions_also_reads_retail_only():
    """`reorder_level_service.refresh_suggestions` (the admin "recompute levels" path) is
    a SECOND caller of the same ADU formula `level_suggestion_service.refresh_for_run`
    uses per run - both must size off the dealer bin alone, or the two screens disagree
    about the very number this slice exists to fix."""
    with pg_session() as db:
        w = _world(db)

        written = rl.refresh_suggestions(db, [w["product_id"]], [w["dealer_wid"]],
                                         as_of=AS_OF)
        assert written == 1

        row = db.execute(text(
            "SELECT suggested_level, suggestion_basis FROM scm.reorder_level "
            "WHERE product_id = :p AND warehouse_id = :w"
        ), {"p": w["product_id"], "w": w["dealer_wid"]}).mappings().first()
        assert row is not None
        assert (row["suggestion_basis"] or {}).get("retail_only") is True

        unfiltered_usage = rl.average_daily_usage(db, [w["product_id"]], as_of=AS_OF)
        unfiltered_level = rl.suggest_level_from_usage(
            adu=unfiltered_usage[w["product_id"]]["adu"], lead_time_days=None,
        )["level"]
        assert float(row["suggested_level"]) != unfiltered_level


# --- AC-S7.3: the view migration is additive (append-only column) ------------------

def test_consumption_v_carries_a_warehouse_segment_column():
    with pg_session() as db:
        cols = db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'scm' AND table_name = 'consumption_v'"
        )).scalars().all()
        assert "warehouse_segment" in cols
