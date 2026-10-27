"""AC-REMOVED-KEEP-CANCELLED follow-up: the lines the sweep now KEEPS instead of deleting
count in no total; every other cancelled line counts exactly as before.

Owner via crew (27 Oct 2026): "keep today's numbers unchanged". Before #1905 the sweep
deleted an AutoCount line a push no longer carried when nothing pointed at it; such a row
now stays cancelled with `removed_unreferenced = True`, and the aggregates skip it.

Postgres only, scratch schemas. No real customer names.
"""
from __future__ import annotations

from sqlalchemy import text

from app.services.order_service import OrderService

from .test_ac_removed_lines_ingest import (
    _oi_row_on,
    _push_po,
    _push_so,
    _remove_so_line_x,
    _repush_without_a,
)
from .test_ingest_documents import INGEST_PO, env  # noqa: F401 - pytest fixture
from .test_order_by_product_so_outstanding import _so_line, db, scenario  # noqa: F401

__all__ = ["env", "db", "scenario"]


def _flag(env, table, line_id):
    env.db.expire_all()
    return env.db.execute(
        text(f"SELECT line_status, removed_unreferenced FROM {table} WHERE id = :i"),
        {"i": line_id},
    ).one()


# ------------------------------------------------------------------ the sweep marks it
def test_an_unreferenced_removed_po_line_is_kept_and_marked(env):
    w = _push_po(env)
    assert _flag(env, "purchase_order_lines", w.line_a) == ("open", False)

    _repush_without_a(env, w)

    assert _flag(env, "purchase_order_lines", w.line_a) == ("cancelled", True)
    assert _flag(env, "purchase_order_lines", w.line_b) == ("open", False)


def test_a_referenced_removed_line_is_not_marked_until_the_old_sweep_would_delete_it(env):
    """Push 1: something points at it, so it was kept before too (and counted): no mark.
    The release then frees it; push 2 is where the old sweep deleted it: marked."""
    w = _push_po(env)
    _oi_row_on(env, w)

    _repush_without_a(env, w)
    assert _flag(env, "purchase_order_lines", w.line_a) == ("cancelled", False)

    _repush_without_a(env, w)
    assert _flag(env, "purchase_order_lines", w.line_a) == ("cancelled", True)


def test_the_mark_clears_when_autocount_sends_the_line_again(env):
    w = _push_po(env)
    _repush_without_a(env, w)
    assert _flag(env, "purchase_order_lines", w.line_a)[1] is True

    res = env.post(INGEST_PO, [w.record])
    assert res.status_code == 200, res.text

    status, flag = _flag(env, "purchase_order_lines", w.line_a)
    assert flag is False and status != "cancelled"


def test_a_removed_so_line_gets_the_same_mark_rule(env):
    record, header, line_x, y = _push_so(env)
    _remove_so_line_x(env, record, y)
    _remove_so_line_x(env, record, y)

    status, flag = _flag(env, "sales_order_lines", line_x["id"])
    assert status == "cancelled"
    # Marked exactly when nothing points at it (an SO line may carry a project mirror).
    from app.models.project_so import ProjectSalesOrderLine

    referenced = (
        env.db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.core_sales_order_line_id == str(line_x["id"]))
        .count()
        > 0
    )
    assert flag is (not referenced)


# --------------------------------------------------- stamp_so_outstanding_rows (D3)
def _totals(db, prod):
    s = OrderService(db).list_orders_by_product(
        product_ids=[prod.id], include_summary=True, include_pipeline=True
    )["summary"]
    p = s["products"][0]
    return p["so_count"], p["so_ordered_qty"], p["so_transferred_qty"]


def test_so_totals_skip_a_marked_line_and_still_count_other_cancelled_lines(db, scenario):
    from app.models.order import SalesOrderLine

    cust, prod, _ = scenario
    assert _totals(db, prod) == (1, 9, 2)  # the scenario's one open SO line

    kept = _so_line(db, customer_id=cust.id, product_id=prod.id, ordered=50, delivered=5,
                    status="cancelled")
    db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id == kept.id).update(
        {"removed_unreferenced": True}
    )
    db.commit()
    assert _totals(db, prod) == (1, 9, 2), "a marked line must not move any figure"

    _so_line(db, customer_id=cust.id, product_id=prod.id, ordered=4, delivered=1,
             status="cancelled")
    db.commit()
    assert _totals(db, prod) == (2, 13, 3), "an unmarked cancelled line counts as today"


# ------------------------------------------------- SCM PO detail: figures vs line list
def test_po_detail_figures_skip_a_marked_line_but_the_line_still_shows(env):
    from app.services.scm.purchase_order_service import PurchaseOrderService

    w = _push_po(env)
    env.db.expire_all()
    before = PurchaseOrderService(env.db).get_one(w.header_id)
    assert before["line_count"] == 2

    _repush_without_a(env, w)

    env.db.expire_all()
    after = PurchaseOrderService(env.db).get_one(w.header_id)
    shown = {str(line["id"]): line for line in after["lines"]}
    assert w.line_a in shown, "the removed line stays visible, as Cancelled"
    assert after["line_count"] == 1
    assert float(after["total_qty"]) == float(before["total_qty"]) / 2
