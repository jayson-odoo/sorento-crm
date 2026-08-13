"""S13f: the run suggests the level to set back in AutoCount, and never sets it itself.

> "the third suggestion is I should suggest the reorder level"

What is pinned here: the suggestion is written for the PLAN's pairs only, it leans the
way the trajectory leans (rising rounds up, dying rounds down), and the buyer's stored
level - hand-set or uploaded - is never touched by any of it.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import level_suggestion_service as svc
from app.services.scm import reorder_engine as eng
from tests.scm.conftest import requires_pg, seed_user
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZTLSG"
AS_OF = date(2026, 8, 10)


def _u() -> str:
    return str(uuid.uuid4())


def _world(db, *, rising: bool):
    """One project-side product with consumption + a run naming it + a hand-set level.

    Consumption (scm.consumption_v <- orders): 12/month over the study window.
    Trajectory (sales_orders): rising or falling around the 12-month project window.
    """
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    # A from-zero database has no global `scm.reorder_policy` row at all (bootstrap seeds
    # `scm.priority_policy`, a different table). Tests further down UPDATE this row's
    # `level_cover_months` - a no-op against an empty table - and silently fall back to
    # the code default instead of the value they think they set. Seed it here, same as
    # `test_reorder_level_run.py`'s `eng.ensure_reorder_policy_defaults(db)`.
    eng.ensure_reorder_policy_defaults(db)

    cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                          category_name=f"{MARKER} cat")
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                      category_id=cat.id, base_uom_id=uom.id, list_price=0,
                      is_active=True, is_discontinued=False,
                      # AutoCount's own reorder quantity, so the payload test can pin
                      # that the master figure travels beside the engine's.
                      reorder_quantity=18)
    db.add(product)
    db.flush()
    pid = str(product.id)

    wid = _u()
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available, segment) VALUES (:id, :c, :c, true, true, 'project')"),
        {"id": wid, "c": unique_code("W")[:20]})

    # Consumption: one 12-unit order per month across the 3-month study window
    # (June, July 2026 + May) -> avg 12/month.
    for day in (date(2026, 5, 10), date(2026, 6, 10), date(2026, 7, 10)):
        oid = _u()
        # kpi_warning/subtotal_amount/discount_amount/tax_amount/total_amount/
        # synced_to_excel are NOT NULL with only a Python-side ORM default (no
        # server_default) - a raw INSERT that omits them violates the constraint on a
        # from-zero database.
        db.execute(text(
            "INSERT INTO orders (id, order_number, order_date, is_cancelled, kpi_warning, "
            "subtotal_amount, discount_amount, tax_amount, total_amount, synced_to_excel, "
            "created_at, updated_at) "
            "VALUES (:id, :n, :d, false, false, 0, 0, 0, 0, false, now(), now())"),
            {"id": oid, "n": f"{MARKER}-{oid[:8]}", "d": day})
        db.execute(text(
            "INSERT INTO order_lines (id, line_sequence, order_id, product_id, warehouse_id, "
            "quantity, created_at, updated_at) VALUES (:id, 1, :o, :p, :w, 12, now(), now())"),
            {"id": _u(), "o": oid, "p": pid, "w": wid})

    # Trajectory: the project window is 12 months. Rising = orders in the recent year and
    # none the year before; falling = the reverse.
    so_days = ([date(2026, 6, 5), date(2026, 3, 5)] if rising
               else [date(2024, 10, 5), date(2024, 9, 5)])
    cust = _u()
    db.execute(text(
        "INSERT INTO customers (id, customer_code, customer_name, is_active) "
        "VALUES (:id, :c, :n, true)"),
        {"id": cust, "c": unique_code("C")[:20], "n": f"{MARKER} cust"})
    for day in so_days:
        soid = _u()
        db.execute(text(
            "INSERT INTO sales_orders (id, so_number, status, order_date, customer_id) "
            "VALUES (:id, :n, 'closed', :d, :cu)"),
            {"id": soid, "n": f"{MARKER}-{soid[:8]}", "d": day, "cu": cust})
        db.execute(text(
            "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
            "qty_ordered, qty_delivered, line_status) "
            "VALUES (:id, :so, :p, :w, 50, 0, 'open')"),
            {"id": _u(), "so": soid, "p": pid, "w": wid})

    # The level the buyer owns. It must survive every refresh untouched.
    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
        "created_at) VALUES (:id, :p, :w, 20, 'manual', now())"),
        {"id": _u(), "p": pid, "w": wid})

    run_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
        "VALUES (:id, 'completed', false, now())"), {"id": run_id})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status) "
        "VALUES (:id, :r, :p, :w, 'buy', 10, 'proposed')"),
        {"id": _u(), "r": run_id, "p": pid, "w": wid})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "warehouse_id": wid}


def _level_row(db, pid, wid) -> dict:
    return dict(db.execute(text(
        "SELECT level, source, suggested_level, suggestion_basis FROM scm.reorder_level "
        "WHERE product_id::text = :p AND warehouse_id::text = :w"),
        {"p": pid, "w": wid}).mappings().first())


def test_a_rising_book_rounds_the_suggested_level_up_and_leaves_the_level_alone():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=True)

        written = svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        row = _level_row(db, w["product_id"], w["warehouse_id"])

        assert written == 1
        # avg 12/month x 2 cover months = 24; rising rounds up, and 24 is already whole.
        assert float(row["suggested_level"]) == 24.0
        assert row["suggestion_basis"]["trend"] == "rising"
        # The buyer's number is exactly where they left it.
        assert float(row["level"]) == 20.0
        assert row["source"] == "manual"


def test_a_dying_book_rounds_down_instead():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=False)
        # 2.5 cover months -> raw 30; drop one June order to 10 so raw = avg 11.333 x 2.5
        # is fractional and the rounding direction is observable.
        db.execute(text(
            "UPDATE order_lines SET quantity = 10 WHERE product_id::text = :p "
            "AND order_id IN (SELECT id FROM orders WHERE order_date = :d)"),
            {"p": w["product_id"], "d": date(2026, 6, 10)})
        db.execute(text(
            "UPDATE scm.reorder_policy SET level_cover_months = 2.5 "
            "WHERE scope_type = 'global'"))

        svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        row = _level_row(db, w["product_id"], w["warehouse_id"])

        # avg (12+10+12)/3 = 11.3333 x 2.5 = 28.3333 -> quiet/falling floors to 28.
        assert float(row["suggested_level"]) == 28.0
        assert row["suggestion_basis"]["trend"] in ("falling", "quiet")


def test_the_run_report_carries_the_current_level_beside_the_suggestion():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=True)
        svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)

        out = svc.suggestions_for_run(db, w["run_id"])
        key = f"{w['product_id']}:{w['warehouse_id']}"

        assert out["count"] == 1
        entry = out["suggestions"][key]
        assert entry["suggested_level"] == 24.0
        assert entry["current_level"] == 20.0
        assert entry["current_source"] == "manual"
        assert entry["basis"]["avg_monthly"] == 12.0
        assert entry["product_code"], "the export names the product by code, not UUID"
        # The lot to order when the level fires, beside AutoCount's own figure. One cover
        # of demand (avg 12 x 2 = 24, already whole) rounded to a purchasable lot.
        assert entry["suggested_quantity"] == 24.0
        assert entry["master_reorder_quantity"] == 18.0


def test_a_suggestion_stored_before_quantities_existed_reads_none_not_zero():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=True)
        svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        # Strip the key the way an old row genuinely lacks it.
        db.execute(text(
            "UPDATE scm.reorder_level "
            "SET suggestion_basis = suggestion_basis - 'suggested_quantity' "
            "WHERE product_id::text = :p"), {"p": w["product_id"]})

        out = svc.suggestions_for_run(db, w["run_id"])
        entry = out["suggestions"][f"{w['product_id']}:{w['warehouse_id']}"]
        assert entry["suggested_quantity"] is None


def test_the_endpoint_serves_the_list_and_rbac_holds(scm_app):
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    company_id = next(iter(scope))
    w = _world_for_route(db, company_id)
    svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)

    with TestClient(app) as c:
        r = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/level-suggestions")
        assert r.status_code == 200, r.text
        body = r.json()
    assert body["count"] == 1
    entry = next(iter(body["suggestions"].values()))
    assert entry["suggested_level"] == 24.0

    # A user with no grants is refused, not shown an empty list.
    from app.dependencies import get_current_user, get_current_user_or_api_key
    nobody = seed_user(db, None)
    for dep in (gcu, gcuk):
        app.dependency_overrides[dep] = lambda: {"id": nobody, "email": "x@y", "roles": []}
    with TestClient(app) as c:
        denied = c.get(f"/api/v1/scm/reorder-runs/{w['run_id']}/level-suggestions")
    assert denied.status_code == 403


def _world_for_route(db, company_id: str) -> dict:
    """The service world, with every raw insert stamped into the ACTIVE company."""
    from tests._pg_fixture import unique_code

    pid, wid, cat_id, uom_id = (_u() for _ in range(4))
    db.execute(text(
        "INSERT INTO product_categories (id, category_code, category_name) "
        "VALUES (:id, :c, :c)"), {"id": cat_id, "c": unique_code(MARKER)})
    db.execute(text(
        "INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:id, :c, :c)"),
        {"id": uom_id, "c": f"U{uuid.uuid4().hex[:8]}"})
    db.execute(text(
        "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
        "list_price, is_active, is_discontinued, company_id) "
        "VALUES (:id, :c, :c, :cat, :uom, 0, true, false, :co)"),
        {"id": pid, "c": unique_code("P"), "cat": cat_id, "uom": uom_id, "co": company_id})
    db.execute(text(
        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
        "counts_as_available, segment, company_id) "
        "VALUES (:id, :c, :c, true, true, 'project', :co)"),
        {"id": wid, "c": unique_code("W")[:20], "co": company_id})

    for day in (date(2026, 5, 10), date(2026, 6, 10), date(2026, 7, 10)):
        oid = _u()
        # See _u()-marked orders INSERT above: kpi_warning/subtotal_amount/
        # discount_amount/tax_amount/total_amount/synced_to_excel are NOT NULL with
        # only a Python-side ORM default.
        db.execute(text(
            "INSERT INTO orders (id, order_number, order_date, is_cancelled, kpi_warning, "
            "subtotal_amount, discount_amount, tax_amount, total_amount, synced_to_excel, "
            "company_id, created_at, updated_at) "
            "VALUES (:id, :n, :d, false, false, 0, 0, 0, 0, false, :co, now(), now())"),
            {"id": oid, "n": f"{MARKER}-{oid[:8]}", "d": day, "co": company_id})
        db.execute(text(
            "INSERT INTO order_lines (id, line_sequence, order_id, product_id, warehouse_id, "
            "quantity, created_at, updated_at) VALUES (:id, 1, :o, :p, :w, 12, now(), now())"),
            {"id": _u(), "o": oid, "p": pid, "w": wid})

    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
        "company_id, created_at) VALUES (:id, :p, :w, 20, 'manual', :co, now())"),
        {"id": _u(), "p": pid, "w": wid, "co": company_id})

    run_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (:id, 'completed', false, :co, now())"), {"id": run_id, "co": company_id})
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation "
        "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status, company_id) "
        "VALUES (:id, :r, :p, :w, 'buy', 10, 'proposed', :co)"),
        {"id": _u(), "r": run_id, "p": pid, "w": wid, "co": company_id})
    db.flush()
    return {"run_id": run_id, "product_id": pid, "warehouse_id": wid}


# --------------------------------------------------------------------------- #
# S14: the buyer can amend the suggestion, and the engine's number stays visible
# --------------------------------------------------------------------------- #

def test_an_amendment_sits_beside_the_suggestion_and_touches_nothing_else():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=True)
        svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)

        out = svc.amend_suggestion(db, product_id=w["product_id"],
                                   warehouse_id=w["warehouse_id"],
                                   amended_level=30, amended_by="user-1")

        assert out["amended_level"] == 30.0
        row = db.execute(text(
            "SELECT level, source, suggested_level, amended_level, amended_by "
            "FROM scm.reorder_level WHERE product_id::text = :p AND warehouse_id::text = :w"),
            {"p": w["product_id"], "w": w["warehouse_id"]}).mappings().first()
        assert float(row["suggested_level"]) == 24.0  # the engine's number survives
        assert float(row["amended_level"]) == 30.0
        assert row["amended_by"] == "user-1"
        assert float(row["level"]) == 20.0            # the stored level is never touched
        assert row["source"] == "manual"


def test_amending_to_none_clears_it_back_to_the_engines_number():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=True)
        svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        svc.amend_suggestion(db, product_id=w["product_id"], warehouse_id=w["warehouse_id"],
                             amended_level=30, amended_by="user-1")

        out = svc.amend_suggestion(db, product_id=w["product_id"],
                                   warehouse_id=w["warehouse_id"],
                                   amended_level=None, amended_by="user-1")

        assert out["amended_level"] is None


def test_there_is_nothing_to_amend_before_a_suggestion_exists():
    from app.services.error_handler import AppException
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=True)  # no refresh: no suggestion yet

        with pytest.raises(AppException):
            svc.amend_suggestion(db, product_id=w["product_id"],
                                 warehouse_id=w["warehouse_id"],
                                 amended_level=30, amended_by="user-1")


def test_a_fresh_engine_run_clears_the_amendment_because_it_judged_an_old_number():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=True)
        svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        svc.amend_suggestion(db, product_id=w["product_id"], warehouse_id=w["warehouse_id"],
                             amended_level=30, amended_by="user-1")

        svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)

        row = db.execute(text(
            "SELECT amended_level FROM scm.reorder_level "
            "WHERE product_id::text = :p AND warehouse_id::text = :w"),
            {"p": w["product_id"], "w": w["warehouse_id"]}).mappings().first()
        assert row["amended_level"] is None


def test_the_run_report_carries_the_amendment_beside_the_engines_number():
    from tests._pg_fixture import pg_session
    with pg_session() as db:
        w = _world(db, rising=True)
        svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)
        svc.amend_suggestion(db, product_id=w["product_id"], warehouse_id=w["warehouse_id"],
                             amended_level=30, amended_by="user-1")

        out = svc.suggestions_for_run(db, w["run_id"])
        entry = out["suggestions"][f"{w['product_id']}:{w['warehouse_id']}"]

        assert entry["suggested_level"] == 24.0
        assert entry["amended_level"] == 30.0


def test_the_amend_endpoint_writes_and_rbac_holds(scm_app):
    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk)
    company_id = next(iter(scope))
    w = _world_for_route(db, company_id)
    svc.refresh_for_run(db, w["run_id"], as_of=AS_OF)

    with TestClient(app) as c:
        r = c.post("/api/v1/scm/reorder-levels/amend-suggestion", json={
            "product_id": w["product_id"], "warehouse_id": w["warehouse_id"],
            "amended_level": 30,
        })
        assert r.status_code == 200, r.text
        assert r.json()["amended_level"] == 30.0
        assert r.json()["suggested_level"] == 24.0

        # Validation: an item with no suggestion has nothing to amend.
        bad = c.post("/api/v1/scm/reorder-levels/amend-suggestion", json={
            "product_id": str(uuid.uuid4()), "amended_level": 10,
        })
        assert bad.status_code == 422

    from app.dependencies import get_current_user, get_current_user_or_api_key
    nobody = seed_user(db, None)
    for dep in (gcu, gcuk):
        app.dependency_overrides[dep] = lambda: {"id": nobody, "email": "x@y", "roles": []}
    with TestClient(app) as c:
        denied = c.post("/api/v1/scm/reorder-levels/amend-suggestion", json={
            "product_id": w["product_id"], "amended_level": 30,
        })
    assert denied.status_code == 403
