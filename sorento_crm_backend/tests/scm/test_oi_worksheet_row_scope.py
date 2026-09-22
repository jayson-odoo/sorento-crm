"""Lane C, PLAN-order-sheet-oi-reports-22sep.md (AC-C2/AC-C4/AC-C4a): the OI worksheet's
row set is `app.services.scm.demand.run_scope_oi_rows`.

**Contract as of the Lane A review (captain ruling, landing on `fix/order-sheet-cells` and
reaching this branch on its next merge):** `run_scope_oi_rows` reads the ENGINE's own
predicate, not "state <> cancelled / ack <> rejected" - `verb IN ('ORDER', 'ORDER_BACK')`,
`state IN ('raised', 'partly_linked')`, `ack_state IN ('acknowledged', 'changed')`,
`redirected_to_pool = FALSE`, and owed (`qty - linked`) `> 0`. The returned `qty` is the
OWED figure (`qty - linked`), not the row's raw `qty`. Product comes off the CORE sales
order line (`sol.product_id`, via `psl.core_sales_order_line_id`), not the project line.

Every case below is written to THIS contract, regardless of what `run_scope_oi_rows` does
in this worktree today - some are red only because Lane A's merge has not reached this
branch yet, not because Lane C has anything left to build; see the report for which.

Seeding is its own helper (`_engine_row`), not Lane A's `_scope_row` (that helper builds no
CORE `sales_order_lines` row at all, so it cannot express "product from the core line" or
"owed via `order_inquiry_links`") - `chain`/`db` fixtures are still reused from
`tests.scm.test_summary_order_service`.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.services.scm.demand import run_scope_oi_rows
from tests.scm.conftest import requires_pg
from tests.scm.test_summary_order_service import chain, db  # noqa: F401

pytestmark = requires_pg

MARKER = "ZZTOIWSROWS"


def _u() -> str:
    return str(uuid.uuid4())


def _ids(rows: list[dict]) -> set[str]:
    return {r["row_id"] for r in rows}


def _by_id(rows: list[dict], row_id: str) -> dict | None:
    return next((r for r in rows if r["row_id"] == row_id), None)


def _engine_row(
    db, *, product, wh, qty, delivery=None, verb="ORDER", state="raised",
    ack_state="acknowledged", so_number=None, redirected=False, linked_qty=None,
    core_product=None,
):
    """A seeded Order Inquiry row shaped for the ENGINE predicate above: a REAL core
    `sales_order_lines` row (`sol.product_id` is what the new contract reads product off -
    `core_product` lets a case put a DIFFERENT product on the core line than on the
    project line, to prove which one wins), a project line pointing at it via
    `core_sales_order_line_id`, and the inquiry row itself. `linked_qty`, when given,
    writes one real `projects.order_inquiry_links` row (a real PO line, the only target
    the CHECK constraint accepts without an SPO allocation) so owed = qty - linked_qty.
    """
    from app.models.project_so import OrderInquiry, OrderInquiryLink, OrderInquiryRow, ProjectSalesOrder, ProjectSalesOrderLine  # noqa: PLC0415

    cust = Customer(id=_u(), customer_code=f"{MARKER}-{_u()[:8]}", customer_name="Scope customer")
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), so_number=so_number or f"{MARKER}-SO-{_u()[:8]}", customer_id=cust.id,
        status="open",
    )
    db.add(so)
    db.flush()
    core_line = SalesOrderLine(
        id=_u(), sales_order_id=so.id, product_id=(core_product or product).id,
        warehouse_id=wh.id, qty_ordered=qty, qty_delivered=0, required_date=delivery,
        line_status="open",
    )
    db.add(core_line)
    db.flush()
    pso = ProjectSalesOrder(id=_u(), provisional_ref=f"{MARKER}-{_u()[:8]}", so_id=so.id)
    db.add(pso)
    db.flush()
    psl = ProjectSalesOrderLine(
        id=_u(), project_sales_order_id=pso.id, line_no=1, product_id=product.id, qty=qty,
        core_sales_order_line_id=core_line.id,
    )
    db.add(psl)
    db.flush()
    inquiry = OrderInquiry(id=_u(), project_sales_order_id=pso.id)
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_u(), order_inquiry_id=inquiry.id, so_line_id=psl.id, qty=qty,
        verb=verb, state=state, ack_state=ack_state, delivery_date=delivery,
        supply_decision_id=None, redirected_to_pool=redirected,
    )
    db.add(row)
    db.flush()

    if linked_qty:
        sup = Supplier(id=_u(), supplier_code=f"{MARKER}-{_u()[:8]}", supplier_name="Link supplier")
        db.add(sup)
        db.flush()
        po = PurchaseOrder(id=_u(), po_number=f"{MARKER}-PO-{_u()[:8]}", supplier_id=sup.id,
                           status="active", issue_date=date(2026, 1, 1))
        db.add(po)
        db.flush()
        po_line = PurchaseOrderLine(
            id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
            qty_ordered=qty, qty_received=0, line_status="open",
        )
        db.add(po_line)
        db.flush()
        db.add(OrderInquiryLink(id=_u(), row_id=row.id, po_line_id=po_line.id, qty=linked_qty))
        db.flush()

    return {"so": so, "row": row, "core_line": core_line, "psl": psl, "customer": cust}


# --------------------------------------------------------------------------------- #
# The engine predicate itself
# --------------------------------------------------------------------------------- #

def test_c2_a_raised_acknowledged_unlinked_row_is_present_with_its_full_qty_owed(db, chain):
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=7, delivery=date(2026, 10, 1))
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    matched = _by_id(rows, leg["row"].id)
    assert matched is not None, rows
    assert matched["qty"] == 7.0, matched


def test_c2_a_placed_row_is_absent(db, chain):
    """`state='placed'` is outside `('raised', 'partly_linked')` - already fully instructed,
    nothing left to print on a worksheet purchasing has already acted on."""
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=5, delivery=date(2026, 10, 1),
                      state="placed")
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id not in _ids(rows), rows


def test_c2_an_actioned_row_is_absent(db, chain):
    """`state='actioned'` - purchasing has already bought it."""
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=6, delivery=date(2026, 10, 1),
                      state="actioned")
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id not in _ids(rows), rows


def test_c2_an_awaiting_ack_row_is_absent(db, chain):
    """`ack_state='awaiting'` - purchasing has not read the instruction yet; buying against
    it is buying against something that may still be amended or refused."""
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=4, delivery=date(2026, 10, 1),
                      ack_state="awaiting")
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id not in _ids(rows), rows


def test_c2_a_redirected_row_is_absent(db, chain):
    """`redirected_to_pool = TRUE` - the document it still shows as history has already
    shipped to somebody else's order; it must not net a line's demand a second time."""
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=8, delivery=date(2026, 10, 1),
                      redirected=True)
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id not in _ids(rows), rows


def test_c2_a_changed_ack_row_is_present(db, chain):
    """`ack_state='changed'` (amended after acknowledgement) counts the same as
    'acknowledged' - the ONE other state `PLANNED_ACK_STATES` names."""
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=9, delivery=date(2026, 10, 1),
                      ack_state="changed")
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id in _ids(rows), rows


def test_c2_a_half_linked_row_prints_its_owed_half_as_qty(db, chain):
    """qty 10, one `order_inquiry_links` row of 4 - owed = 10 - 4 = 6, and the row is
    `partly_linked`, still in the counted state set."""
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=10, delivery=date(2026, 10, 1),
                      state="partly_linked", linked_qty=4)
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    matched = _by_id(rows, leg["row"].id)
    assert matched is not None, rows
    assert matched["qty"] == 6.0, matched


def test_c2_product_comes_from_the_core_line_not_the_project_line(db, chain):
    """`sol.product_id` (the core line) is what the worksheet groups by - a project line
    naming a DIFFERENT product than its own core line must surface under the CORE
    product, matching what the sales order itself was actually placed for."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    f = chain
    other_cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-CATX-{_u()[:8]}", category_name=f"{MARKER} catx",
    )
    other_uom = UnitOfMeasure(
        id=_u(), uom_name=f"{MARKER}-uomx-{_u()[:8]}", uom_code=f"UX{_u()[:6]}",
    )
    db.add_all([other_cat, other_uom])
    db.flush()
    core_product = Product(
        id=_u(), product_code=f"{MARKER}-COREPROD-{_u()[:8]}", product_name="core product",
        category_id=other_cat.id, base_uom_id=other_uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(core_product)
    db.flush()
    # project line names `f["product"]`; the core line names `core_product`.
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=5, delivery=date(2026, 10, 1),
                      core_product=core_product)
    db.flush()

    rows = run_scope_oi_rows(db, [core_product.id])

    matched = _by_id(rows, leg["row"].id)
    assert matched is not None, (
        f"row must surface under the CORE line's product ({core_product.id}), not the "
        f"project line's: {rows}"
    )
    assert matched["product_id"] == str(core_product.id), matched


# --------------------------------------------------------------------------------- #
# SO / horizon / product scope (unaffected by the predicate change)
# --------------------------------------------------------------------------------- #

def test_c2a_a_row_on_a_picked_so_inside_the_window_is_present(db, chain):
    f = chain
    picked = f"{MARKER}-SO-PICKED-C2A"
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=7, delivery=date(2026, 10, 1),
                      so_number=picked)
    db.flush()

    rows = run_scope_oi_rows(
        db, [f["product"].id], so_numbers=[picked],
        horizon_start=date(2026, 9, 1), horizon=date(2026, 11, 30),
    )

    assert leg["row"].id in _ids(rows), rows


def test_c2b_a_row_on_an_unpicked_so_is_absent(db, chain):
    f = chain
    picked = f"{MARKER}-SO-PICKED-C2B"
    other = f"{MARKER}-SO-OTHER-C2B"
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=7, delivery=date(2026, 10, 1),
                      so_number=other)
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id], so_numbers=[picked])

    assert leg["row"].id not in _ids(rows), rows


def test_c2c_a_row_dated_after_the_plan_horizon_is_absent(db, chain):
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=5, delivery=date(2027, 3, 1))
    db.flush()

    rows = run_scope_oi_rows(
        db, [f["product"].id],
        horizon_start=date(2026, 1, 1), horizon=date(2026, 12, 31),
    )

    assert leg["row"].id not in _ids(rows), rows


def test_c2d_an_undated_row_is_present_regardless_of_the_window(db, chain):
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=3, delivery=None)
    db.flush()

    rows = run_scope_oi_rows(
        db, [f["product"].id],
        horizon_start=date(2026, 1, 1), horizon=date(2026, 12, 31),
    )

    matched = _by_id(rows, leg["row"].id)
    assert matched is not None, rows
    assert matched["delivery_date"] is None, matched


def test_c2e_a_row_for_a_product_outside_product_ids_is_absent(db, chain):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    f = chain
    other_cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-CAT2-{_u()[:8]}", category_name=f"{MARKER} cat2",
    )
    other_uom = UnitOfMeasure(
        id=_u(), uom_name=f"{MARKER}-uom2-{_u()[:8]}", uom_code=f"U2{_u()[:6]}",
    )
    db.add_all([other_cat, other_uom])
    db.flush()
    other_product = Product(
        id=_u(), product_code=f"{MARKER}-OTHER-{_u()[:8]}", product_name="other product",
        category_id=other_cat.id, base_uom_id=other_uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(other_product)
    db.flush()
    leg = _engine_row(db, product=other_product, wh=f["bin"], qty=4, delivery=date(2026, 10, 1))
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id not in _ids(rows), rows


def test_c2f_so_numbers_none_admits_every_in_window_row_of_every_scoped_product(db, chain):
    f = chain
    leg_a = _engine_row(db, product=f["product"], wh=f["bin"], qty=6, delivery=date(2026, 10, 1),
                        so_number=f"{MARKER}-SO-A-C2F")
    leg_b = _engine_row(db, product=f["product"], wh=f["bin"], qty=9, delivery=date(2026, 10, 1),
                        so_number=f"{MARKER}-SO-B-C2F")
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id], so_numbers=None)

    ids = _ids(rows)
    assert leg_a["row"].id in ids, rows
    assert leg_b["row"].id in ids, rows


def test_c2g_a_product_with_no_order_summary_row_for_the_run_is_still_present(db, chain):
    """AC-C4: a product the engine bought nothing for is still present - `run_scope_oi_rows`
    never joins `scm.order_summary_row` at all."""
    f = chain
    leg = _engine_row(db, product=f["product"], wh=f["bin"], qty=11, delivery=date(2026, 10, 1))
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id in _ids(rows), rows


# --------------------------------------------------------------------------------- #
# (h) NEW for Lane C: `product_ids=None` means NO product filter at all.
# --------------------------------------------------------------------------------- #

def test_c2h_product_ids_none_means_no_product_filter_at_all(db, chain):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    f = chain
    other_cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}-CAT3-{_u()[:8]}", category_name=f"{MARKER} cat3",
    )
    other_uom = UnitOfMeasure(
        id=_u(), uom_name=f"{MARKER}-uom3-{_u()[:8]}", uom_code=f"U3{_u()[:6]}",
    )
    db.add_all([other_cat, other_uom])
    db.flush()
    other_product = Product(
        id=_u(), product_code=f"{MARKER}-OTHER2-{_u()[:8]}", product_name="other product 2",
        category_id=other_cat.id, base_uom_id=other_uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(other_product)
    db.flush()
    leg_this = _engine_row(db, product=f["product"], wh=f["bin"], qty=2, delivery=date(2026, 10, 1))
    leg_other = _engine_row(db, product=other_product, wh=f["bin"], qty=3, delivery=date(2026, 10, 1))
    db.flush()

    rows = run_scope_oi_rows(db, None)

    ids = _ids(rows)
    assert leg_this["row"].id in ids, (
        "product_ids=None must not drop every row - it must apply NO product filter "
        f"at all: {rows}"
    )
    assert leg_other["row"].id in ids, rows
