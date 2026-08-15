"""Every plan-screen reader answers for ONE run, and only that run.

These pin the behaviour that the index fix must not change. Rewriting
``run_id::text = :run_id`` into ``run_id = CAST(:run_id AS uuid)`` swaps the comparison's
type on both sides, and the way that goes wrong is silent: a predicate that matches too
much (the second run's rows leak in) or too little (an empty payload that reads as "this
product has no history"). So each reader is asked the same question against a world
holding TWO runs, and has to come back with its own run's rows only.

Two runs, two products, deliberately: with a single run in the world a predicate that had
been dropped entirely would still pass every assertion.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests._pg_fixture import pg_session

MARKER = "ZZTPLANIDX"


def _u() -> str:
    return str(uuid.uuid4())


def _world(db) -> dict:
    """Two completed runs. Run A plans product A, run B plans product B.

    Each product carries one costed buy recommendation with a supplier, one purchase-order
    line and one sales-order line, which is the minimum every reader under test needs to
    return a non-empty answer for its own run.
    """
    # `pg_session` leaves the company scope UNSET, which is fail-closed: the route-level
    # readers (cover-sources calls `assert_run_visible`) would then 404 their own run. A
    # request resolves this from the caller's token; the fixture has to supply it.
    from app.models.base import set_company_scope

    set_company_scope(db, None)

    cat, uom = _reference(db)
    sup_a, sup_b = _supplier(db, "A"), _supplier(db, "B")
    wh = _warehouse(db)
    out = {"warehouse_id": wh}

    for tag, supplier in (("A", sup_a), ("B", sup_b)):
        pid = _product(db, tag, cat, uom)
        run_id = _u()
        db.execute(
            text(
                "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
                "VALUES (:id, 'completed', false, now())"
            ),
            {"id": run_id},
        )
        db.execute(
            text(
                "INSERT INTO scm.reorder_recommendation "
                "(id, run_id, product_id, warehouse_id, supplier_id, rec_type, rounded_qty, "
                " unit_cost, currency, status, inputs) "
                "VALUES (:id, :r, :p, :w, :s, 'buy', 10, 25.50, 'MYR', 'proposed', "
                "        '{\"committed\": 5, \"on_hand\": 2}'::jsonb)"
            ),
            {"id": _u(), "r": run_id, "p": pid, "w": wh, "s": supplier},
        )
        _purchase(db, tag, pid, supplier)
        _sale(db, tag, pid, wh)
        _stock(db, pid, wh)
        out[tag] = {"run_id": run_id, "product_id": pid, "supplier_id": supplier}

    db.flush()
    return out


def _reference(db) -> tuple[str, str]:
    cat = _u()
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name) "
            "VALUES (:id, :c, :c)"
        ),
        {"id": cat, "c": f"{MARKER}-CAT"},
    )
    uom = _u()
    db.execute(
        text("INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:id, :c, :c)"),
        {"id": uom, "c": f"{MARKER}-UOM"},
    )
    return cat, uom


def _product(db, tag: str, cat: str, uom: str) -> str:
    pid = _u()
    db.execute(
        text(
            "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
            "list_price) VALUES (:id, :c, :c, :cat, :uom, 100)"
        ),
        {"id": pid, "c": f"{MARKER}-P{tag}", "cat": cat, "uom": uom},
    )
    return pid


def _supplier(db, tag: str) -> str:
    sid = _u()
    db.execute(
        text(
            "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active) "
            "VALUES (:id, :c, :c, true)"
        ),
        {"id": sid, "c": f"{MARKER}-S{tag}"},
    )
    return sid


def _warehouse(db) -> str:
    wid = _u()
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available, segment) VALUES (:id, :c, :c, true, true, 'project')"
        ),
        {"id": wid, "c": f"{MARKER}-WH"},
    )
    return wid


def _purchase(db, tag: str, pid: str, supplier: str) -> None:
    poid = _u()
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, supplier_id, status, issue_date, "
            "currency) VALUES (:id, :n, :s, 'issued', :d, 'MYR')"
        ),
        {"id": poid, "n": f"{MARKER}-PO{tag}", "s": supplier, "d": date.today() - timedelta(days=30)},
    )
    db.execute(
        text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "qty_ordered, qty_received, line_status, unit_cost, currency) "
            "VALUES (:id, :po, :p, 100, 0, 'open', 20.00, 'MYR')"
        ),
        {"id": _u(), "po": poid, "p": pid},
    )


def _sale(db, tag: str, pid: str, wh: str) -> None:
    soid = _u()
    db.execute(
        text(
            "INSERT INTO sales_orders (id, so_number, status, order_date) "
            "VALUES (:id, :n, 'open', :d)"
        ),
        {"id": soid, "n": f"{MARKER}-SO{tag}", "d": date.today() - timedelta(days=15)},
    )
    db.execute(
        text(
            "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
            "qty_ordered, qty_delivered, line_status) "
            "VALUES (:id, :so, :p, :w, 40, 0, 'open')"
        ),
        {"id": _u(), "so": soid, "p": pid, "w": wh},
    )


def _stock(db, pid: str, wh: str) -> None:
    db.execute(
        text(
            # `quantity_available` is a generated column - never write it.
            "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
            "synced_to_excel) VALUES (:id, :p, :w, 500, false)"
        ),
        {"id": _u(), "p": pid, "w": wh},
    )


# --------------------------------------------------------------------------- #
# one run's answer never carries the other run's rows
# --------------------------------------------------------------------------- #

def test_the_costed_buy_count_counts_only_its_own_run():
    from app.api.v1.scm.reorder_runs import _costed_buy_counts

    with pg_session() as db:
        w = _world(db)

        counts = _costed_buy_counts(db, [w["A"]["run_id"]])

        assert counts == {w["A"]["run_id"]: 1}, "run B's costed buy leaked into run A's count"


def test_the_costed_buy_count_answers_for_several_runs_at_once():
    """The run-history panel asks for a whole page of runs in one call."""
    from app.api.v1.scm.reorder_runs import _costed_buy_counts

    with pg_session() as db:
        w = _world(db)

        counts = _costed_buy_counts(db, [w["A"]["run_id"], w["B"]["run_id"]])

        assert counts == {w["A"]["run_id"]: 1, w["B"]["run_id"]: 1}


def test_price_history_carries_only_the_runs_own_product_supplier_pair():
    from app.services.scm.price_history_service import price_history_for_run

    with pg_session() as db:
        w = _world(db)

        history = price_history_for_run(db, w["A"]["run_id"])

        assert list(history) == [f"{w['A']['product_id']}:{MARKER}-SA"]
        assert history[f"{w['A']['product_id']}:{MARKER}-SA"].last.unit_cost == 20.0


def test_the_price_history_header_does_not_depend_on_which_entry_comes_first():
    """The route echoes the thresholds off ``next(iter(history.values()))``.

    That is only safe while every entry carries the same pair, and it is the one place on
    the plan screen where the ORDER of a keyed payload could have changed an answer. It
    matters here because using the index changes the order rows arrive in: a parallel
    sequential scan and a bitmap index scan hand back the same rows in different sequences,
    so the payload's key order moved even though its content did not. The FE reads both
    payloads by key (``prices[key]``, ``products[product_id]``) and never by position, and
    this keeps the one positional read honest.
    """
    from app.services.scm.price_history_service import price_history_for_run

    with pg_session() as db:
        w = _world(db)
        # Both runs' pairs, so the map holds more than one entry to be first.
        both = dict(price_history_for_run(db, w["A"]["run_id"]))
        both.update(price_history_for_run(db, w["B"]["run_id"]))

        assert len(both) == 2
        assert len({a.stale_after_days for a in both.values()}) == 1
        assert len({a.movement_threshold_pct for a in both.values()}) == 1


def test_the_trajectory_covers_only_the_runs_own_products():
    from app.services.scm.trajectory_service import trajectory_for_run

    with pg_session() as db:
        w = _world(db)

        series = trajectory_for_run(db, w["A"]["run_id"])["series"]

        assert [k.split(":")[0] for k in series] == [w["A"]["product_id"]]


def test_the_purchase_trend_covers_only_the_runs_own_products():
    from app.services.scm.purchase_trend_service import purchase_trend_for_run

    with pg_session() as db:
        w = _world(db)

        products = purchase_trend_for_run(db, w["A"]["run_id"])["products"]

        assert list(products) == [w["A"]["product_id"]]


def test_free_stock_reads_the_runs_own_plan_demand():
    """`free = on hand - the demand THIS run placed on the location`.

    Asked for run A's product, the netting has to use run A's committed figure. Reading the
    plan demand off the wrong run would hand the buyer stock another plan already spent.
    """
    from app.services.scm.cover_service import free_stock_by_product

    with pg_session() as db:
        w = _world(db)
        pid = w["A"]["product_id"]

        free = free_stock_by_product(db, w["A"]["run_id"], [pid])

        assert [s.qty for s in free[pid]] == [495.0], "500 on hand less the run's 5 committed"


def test_free_stock_ignores_a_product_the_caller_did_not_ask_about():
    from app.services.scm.cover_service import free_stock_by_product

    with pg_session() as db:
        w = _world(db)

        free = free_stock_by_product(db, w["A"]["run_id"], [w["A"]["product_id"]])

        assert w["B"]["product_id"] not in free


def test_cover_sources_lists_the_products_this_run_plans():
    """The route derives the product scope from the run's own buy / needs_level rows."""
    from app.api.v1.scm.reorder_runs import list_cover_sources

    with pg_session() as db:
        w = _world(db)

        payload = list_cover_sources(w["A"]["run_id"], db, {})

        assert list(payload["sources"]) == [w["A"]["product_id"]]


def test_a_run_with_no_recommendations_answers_empty_rather_than_everything():
    """The failure mode a dropped predicate produces: every row in the table comes back."""
    from app.services.scm.price_history_service import price_history_for_run
    from app.services.scm.purchase_trend_service import purchase_trend_for_run

    with pg_session() as db:
        _world(db)
        missing = _u()
        db.execute(
            text(
                "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
                "VALUES (:id, 'completed', false, now())"
            ),
            {"id": missing},
        )
        db.flush()

        assert price_history_for_run(db, missing) == {}
        assert purchase_trend_for_run(db, missing)["products"] == {}


# --------------------------------------------------------------------------- #
# the same question of the readers whose product predicates were rewritten
#
# These carry a list of product ids rather than a run id, so the failure mode is the
# mirror image: an id list that no longer matches (empty answers everywhere) or one that
# matches too much (another product's stock and orders folded into this one's figures).
# --------------------------------------------------------------------------- #

def test_product_economics_answers_for_the_runs_own_products_only():
    from app.services.scm.product_economics_service import economics_for_run

    with pg_session() as db:
        w = _world(db)

        products = economics_for_run(db, w["A"]["run_id"])["products"]

        assert list(products) == [w["A"]["product_id"]]
        # 500 on hand was seeded for this product at the one warehouse.
        assert products[w["A"]["product_id"]]["on_hand"] == 500.0


def test_product_economics_does_not_fold_in_another_products_stock():
    from app.services.scm.product_economics_service import economics_for_run

    with pg_session() as db:
        w = _world(db)

        a = economics_for_run(db, w["A"]["run_id"])["products"][w["A"]["product_id"]]
        b = economics_for_run(db, w["B"]["run_id"])["products"][w["B"]["product_id"]]

        assert a["on_hand"] == b["on_hand"] == 500.0


def test_reorder_level_movement_is_scoped_to_the_products_asked_about():
    from app.services.scm.reorder_level_service import monthly_movement

    with pg_session() as db:
        w = _world(db)

        movement = monthly_movement(db, [w["A"]["product_id"]], months=12)

        # Keyed by product id, and product B is not one of them.
        assert list(movement) == [w["A"]["product_id"]]


def test_reorder_level_lookup_returns_only_the_asked_products_level():
    from app.services.scm.reorder_level_service import get_levels, upsert_level

    with pg_session() as db:
        w = _world(db)
        upsert_level(db, product_id=w["A"]["product_id"],
                     warehouse_id=w["warehouse_id"], level=7, source="manual")
        upsert_level(db, product_id=w["B"]["product_id"],
                     warehouse_id=w["warehouse_id"], level=99, source="manual")
        db.flush()

        levels = get_levels(db, [w["A"]["product_id"]])

        assert {pid for pid, _ in levels} == {w["A"]["product_id"]}
        assert float(next(iter(levels.values()))["level"]) == 7.0


def test_supplier_constraints_are_scoped_to_the_asked_products():
    from app.services.scm.reorder_level_service import supplier_constraints

    with pg_session() as db:
        w = _world(db)
        for tag in ("A", "B"):
            db.execute(
                text(
                    "INSERT INTO product_suppliers (id, product_id, supplier_id, moq, "
                    "standard_lead_time_days, is_primary_supplier) "
                    "VALUES (:id, :p, :s, 25, 30, false)"
                ),
                {"id": _u(), "p": w[tag]["product_id"], "s": w[tag]["supplier_id"]},
            )
        db.flush()

        out = supplier_constraints(db, [w["A"]["product_id"]])

        assert list(out) == [w["A"]["product_id"]]
        assert out[w["A"]["product_id"]]["moq"] == 25.0


def test_an_empty_id_list_matches_nothing_rather_than_everything():
    """`= ANY(CAST(:pids AS uuid[]))` on an empty list.

    The old `::text` form and the new one both have to mean "no products", not "all of
    them", and an empty array must not raise on the cast either.
    """
    from app.services.scm.reorder_level_service import get_levels, supplier_constraints

    with pg_session() as db:
        _world(db)

        assert get_levels(db, []) == {}
        assert supplier_constraints(db, []) == {}
