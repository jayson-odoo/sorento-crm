"""AC-R11 - the suggested reorder level, the industry way.

    level = ADU x lead_time + ADU x 14
    ADU   = delivery-order line quantity over the last 90 days / 90

The delivery-order book is the CRM's own `orders` / `order_lines` (what
`scm.consumption_v` reads): every warehouse, cancelled orders excluded. Sales-order
lines play no part - they are demand, not what left the building.

What is pinned here: the arithmetic itself, the 90-day window (an older order outside
it contributes nothing), the cancelled exclusion, the 30-day lead-time fallback, and
that a run writes the whole basis (ADU, lead, safety) onto `scm.reorder_level` so the
popover can name the three terms.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.services.scm import level_suggestion_service as lsvc
from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_level_service as rl
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

MARKER = "ZZTLVLF"
AS_OF = date(2026, 8, 10)


def _u() -> str:
    return str(uuid.uuid4())


def _do(db, pid, wid, *, day: date, qty: float, cancelled: bool = False) -> None:
    """One delivery-order line. `orders` carries several NOT NULL columns whose only
    default is Python-side, so a raw INSERT has to name them (see the note in
    `test_level_suggestion_run.py`)."""
    oid = _u()
    db.execute(text(
        "INSERT INTO orders (id, order_number, order_date, is_cancelled, kpi_warning, "
        "subtotal_amount, discount_amount, tax_amount, total_amount, synced_to_excel, "
        "created_at, updated_at) "
        "VALUES (:id, :n, :d, :c, false, 0, 0, 0, 0, false, now(), now())"),
        {"id": oid, "n": f"{MARKER}-{oid[:8]}", "d": day, "c": cancelled})
    db.execute(text(
        "INSERT INTO order_lines (id, line_sequence, order_id, product_id, warehouse_id, "
        "quantity, created_at, updated_at) VALUES (:id, 1, :o, :p, :w, :q, now(), now())"),
        {"id": _u(), "o": oid, "p": pid, "w": wid, "q": qty})


def _world(db, *, lead_days: int | None = 30):
    """One product, TWO warehouses, 900 units delivered inside the 90-day window.

    900 / 90 = an ADU of exactly 10, which makes every downstream number checkable by
    hand: safety 10 x 14 = 140, level 10 x 30 + 140 = 440.
    """
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    eng.ensure_reorder_policy_defaults(db)

    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False)
    db.add(product)
    db.flush()
    pid = str(product.id)

    wids = []
    for _ in range(2):
        wid = _u()
        db.execute(text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available, segment) VALUES (:id, :c, :c, true, true, 'project')"),
            {"id": wid, "c": unique_code("W")[:20]})
        wids.append(wid)

    # 900 delivered inside the window, split across BOTH warehouses - the level is a
    # product fact, so where it left from must not matter.
    _do(db, pid, wids[0], day=date(2026, 6, 1), qty=400)
    _do(db, pid, wids[1], day=date(2026, 7, 1), qty=300)
    _do(db, pid, wids[0], day=date(2026, 8, 1), qty=200)
    # Cancelled inside the window: never counted.
    _do(db, pid, wids[0], day=date(2026, 7, 15), qty=100, cancelled=True)
    # Delivered, but before the window opens: also not counted.
    _do(db, pid, wids[0], day=date(2026, 1, 10), qty=500)

    # A sales order for the same product: demand, never ADU.
    cust = _u()
    db.execute(text(
        "INSERT INTO customers (id, customer_code, customer_name, is_active) "
        "VALUES (:id, :c, :n, true)"),
        {"id": cust, "c": unique_code("C")[:20], "n": f"{MARKER} cust"})
    soid = _u()
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, order_date, customer_id) "
        "VALUES (:id, :n, 'open', :d, :cu)"),
        {"id": soid, "n": f"{MARKER}-{soid[:8]}", "d": date(2026, 7, 20), "cu": cust})
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_delivered, line_status) "
        "VALUES (:id, :so, :p, :w, 5000, 0, 'open')"),
        {"id": _u(), "so": soid, "p": pid, "w": wids[0]})

    if lead_days is not None:
        sid = _u()
        db.execute(text(
            "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active) "
            "VALUES (:id, :c, :n, true)"),
            {"id": sid, "c": unique_code("S")[:20], "n": f"{MARKER} supplier"})
        db.execute(text(
            "INSERT INTO product_suppliers (id, product_id, supplier_id, "
            "standard_lead_time_days, unit_cost, currency, is_primary_supplier, created_at) "
            "VALUES (:id, :p, :s, :lead, 12, 'MYR', true, now())"),
            {"id": _u(), "p": pid, "s": sid, "lead": lead_days})

    run_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
        "VALUES (:id, 'completed', false, now())"), {"id": run_id})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status) "
        "VALUES (:id, :r, :p, :w, 'needs_level', 0, 'proposed')"),
        {"id": _u(), "r": run_id, "p": pid, "w": wids[0]})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "warehouse_ids": wids}


# --- the arithmetic ----------------------------------------------------------------

def test_adu_is_delivery_order_quantity_over_ninety_days():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db)

        usage = rl.average_daily_usage(db, [w["product_id"]], as_of=AS_OF)

        assert usage[w["product_id"]]["window_qty"] == 900.0
        assert usage[w["product_id"]]["adu"] == 10.0
        assert usage[w["product_id"]]["window_days"] == 90


def test_the_level_is_lead_time_demand_plus_fourteen_days_of_safety():
    out = rl.suggest_level_from_usage(adu=10.0, lead_time_days=30)

    assert out["level"] == 440.0
    basis = out["basis"]
    assert basis["adu"] == 10.0
    assert basis["lead_time_days"] == 30.0
    assert basis["safety_days"] == 14.0
    assert basis["safety_stock"] == 140.0
    assert basis["window_days"] == 90


def test_the_level_rounds_up_to_a_whole_unit():
    # 0.4 x 20 = 8 plus 0.4 x 14 = 5.6 -> 13.6, and half a unit is not a thing to hold.
    out = rl.suggest_level_from_usage(adu=0.4, lead_time_days=20)
    assert out["level"] == 14.0
    assert out["basis"]["raw_level"] == 13.6


def test_an_unknown_lead_time_falls_back_to_thirty_days():
    out = rl.suggest_level_from_usage(adu=1.0, lead_time_days=None)
    assert out["basis"]["lead_time_days"] == 30.0
    assert out["level"] == 44.0


def test_nothing_delivered_suggests_zero_and_says_so():
    out = rl.suggest_level_from_usage(adu=0.0, lead_time_days=30)
    assert out["level"] == 0.0
    assert out["basis"]["no_movement"] is True


# --- the run writes it -------------------------------------------------------------

def test_the_run_stores_the_level_and_the_three_terms_behind_it():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db)

        written = lsvc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        row = db.execute(text(
            "SELECT suggested_level, suggestion_basis FROM scm.reorder_level "
            "WHERE product_id::text = :p"), {"p": w["product_id"]}).mappings().first()

        assert written == 1
        assert float(row["suggested_level"]) == 440.0
        basis = row["suggestion_basis"]
        assert basis["adu"] == 10.0
        assert basis["lead_time_days"] == 30.0
        assert basis["safety_days"] == 14.0
        assert basis["safety_stock"] == 140.0
        assert basis["window_days"] == 90


def test_a_product_with_no_supplier_lead_time_is_planned_at_thirty_days():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, lead_days=None)

        lsvc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        row = db.execute(text(
            "SELECT suggested_level, suggestion_basis FROM scm.reorder_level "
            "WHERE product_id::text = :p"), {"p": w["product_id"]}).mappings().first()

        assert row["suggestion_basis"]["lead_time_days"] == 30.0
        assert float(row["suggested_level"]) == 440.0


def test_a_longer_lead_time_raises_the_level_by_its_own_days_of_demand():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, lead_days=60)

        lsvc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        row = db.execute(text(
            "SELECT suggested_level FROM scm.reorder_level "
            "WHERE product_id::text = :p"), {"p": w["product_id"]}).mappings().first()

        # 10 x 60 + 140
        assert float(row["suggested_level"]) == 740.0


def test_the_payload_carries_the_basis_for_the_popover():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db)
        lsvc.refresh_for_run(db, w["run_id"], as_of=AS_OF)

        out = lsvc.suggestions_for_run(db, w["run_id"])
        entry = next(iter(out["suggestions"].values()))

        assert entry["suggested_level"] == 440.0
        assert entry["basis"]["adu"] == 10.0
        assert entry["basis"]["lead_time_days"] == 30.0
        assert entry["basis"]["safety_stock"] == 140.0
