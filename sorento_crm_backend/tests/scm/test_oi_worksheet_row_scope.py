"""Lane C, PLAN-order-sheet-oi-reports-22sep.md (AC-C2/AC-C4/AC-C4a): the OI worksheet's
row set is `app.services.scm.demand.run_scope_oi_rows` - the SAME helper A3 (Lane A,
already merged onto this branch) uses to build Project qty / Delivery / Project-customer,
so the sheet and the worksheet can never list a different row set for the same run
(AC-C4a: "the workbook's rows are exactly the rows Project qty counted").

Most of the predicate (verb, state, ack_state, qty > 0, so_numbers, horizon bounds, undated
rows) is Lane A's own contract and already implemented - the cases below re-pin it at the
CALL SHAPE Lane C's route/task will use, so a regression in either lane is caught here too.
The ONE genuinely new behaviour for Lane C is `product_ids=None` meaning "no product
filter" (a Dealer/All run's OWN scope is never narrowed by product): today's
`run_scope_oi_rows` opens with `if not product_ids: return []`, which is falsy for `None`
as well as `[]`, so that case is RED for the right reason (an empty list, not the rows) until
the coder tells the two apart.

Seeding reused wholesale from Lane A's own new helper: `tests.scm.test_order_summary_sheet.
_scope_row` (a project SO line + a Buy-verb `OrderInquiryRow`, no supply decision at all -
the SRTWB248 shape) and its `chain`/`db` fixtures.
"""
from __future__ import annotations

from datetime import date

from app.services.scm.demand import run_scope_oi_rows
from tests.scm.conftest import requires_pg
from tests.scm.test_order_summary_sheet import MARKER, _scope_row
from tests.scm.test_summary_order_service import chain, db  # noqa: F401

pytestmark = requires_pg


def _ids(rows: list[dict]) -> set[str]:
    return {r["row_id"] for r in rows}


# --------------------------------------------------------------------------------- #
# (a) / (b): SO scope
# --------------------------------------------------------------------------------- #

def test_c2a_a_row_on_a_picked_so_inside_the_window_is_present(db, chain):
    f = chain
    picked = f"{MARKER}-SO-PICKED-C2A"
    leg = _scope_row(db, product=f["product"], qty=7, delivery=date(2026, 10, 1),
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
    leg = _scope_row(db, product=f["product"], qty=7, delivery=date(2026, 10, 1),
                     so_number=other)
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id], so_numbers=[picked])

    assert leg["row"].id not in _ids(rows), rows


# --------------------------------------------------------------------------------- #
# (c): horizon
# --------------------------------------------------------------------------------- #

def test_c2c_a_row_dated_after_the_plan_horizon_is_absent(db, chain):
    f = chain
    leg = _scope_row(db, product=f["product"], qty=5, delivery=date(2027, 3, 1))
    db.flush()

    rows = run_scope_oi_rows(
        db, [f["product"].id],
        horizon_start=date(2026, 1, 1), horizon=date(2026, 12, 31),
    )

    assert leg["row"].id not in _ids(rows), rows


# --------------------------------------------------------------------------------- #
# (d): undated rows are always in scope
# --------------------------------------------------------------------------------- #

def test_c2d_an_undated_row_is_present_regardless_of_the_window(db, chain):
    f = chain
    leg = _scope_row(db, product=f["product"], qty=3, delivery=None)
    db.flush()

    rows = run_scope_oi_rows(
        db, [f["product"].id],
        horizon_start=date(2026, 1, 1), horizon=date(2026, 12, 31),
    )

    matched = next((r for r in rows if r["row_id"] == leg["row"].id), None)
    assert matched is not None, rows
    assert matched["delivery_date"] is None, matched


# --------------------------------------------------------------------------------- #
# (e): product_ids scoping
# --------------------------------------------------------------------------------- #

def test_c2e_a_row_for_a_product_outside_product_ids_is_absent(db, chain):
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    import uuid

    f = chain
    other_cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=f"{MARKER}-CAT2-{uuid.uuid4().hex[:8]}",
        category_name=f"{MARKER} cat2",
    )
    other_uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_name=f"{MARKER}-uom2-{uuid.uuid4().hex[:8]}",
        uom_code=f"U2{uuid.uuid4().hex[:6]}",
    )
    db.add_all([other_cat, other_uom])
    db.flush()
    other_product = Product(
        id=str(uuid.uuid4()), product_code=f"{MARKER}-OTHER-{uuid.uuid4().hex[:8]}",
        product_name="other product", category_id=other_cat.id, base_uom_id=other_uom.id,
        list_price=0, is_active=True, is_discontinued=False,
    )
    db.add(other_product)
    db.flush()
    leg = _scope_row(db, product=other_product, qty=4, delivery=date(2026, 10, 1))
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id not in _ids(rows), rows


# --------------------------------------------------------------------------------- #
# (f): so_numbers None/empty (Dealer/All run) admits every product's rows
# --------------------------------------------------------------------------------- #

def test_c2f_so_numbers_none_admits_every_in_window_row_of_every_scoped_product(db, chain):
    f = chain
    leg_a = _scope_row(db, product=f["product"], qty=6, delivery=date(2026, 10, 1),
                       so_number=f"{MARKER}-SO-A-C2F")
    leg_b = _scope_row(db, product=f["product"], qty=9, delivery=date(2026, 10, 1),
                       so_number=f"{MARKER}-SO-B-C2F")
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id], so_numbers=None)

    ids = _ids(rows)
    assert leg_a["row"].id in ids, rows
    assert leg_b["row"].id in ids, rows


# --------------------------------------------------------------------------------- #
# (g): a product the engine bought nothing for is still present (AC-C4: input, not
# output) - `run_scope_oi_rows` never joins `scm.order_summary_row` at all, so a
# product with NO frozen row for this run still surfaces its in-scope OI rows.
# --------------------------------------------------------------------------------- #

def test_c2g_a_product_with_no_order_summary_row_for_the_run_is_still_present(db, chain):
    f = chain
    # Deliberately no `scm.order_summary_row` write for this product/run at all - the
    # engine never bought it, but its OI row is still in the run's own scope.
    leg = _scope_row(db, product=f["product"], qty=11, delivery=date(2026, 10, 1))
    db.flush()

    rows = run_scope_oi_rows(db, [f["product"].id])

    assert leg["row"].id in _ids(rows), rows


# --------------------------------------------------------------------------------- #
# (h) NEW for Lane C: `product_ids=None` must mean NO product filter at all - a Dealer
# or All run's own scope is never narrowed by product. Today's guard clause
# (`if not product_ids: return []`) treats `None` exactly like an empty list, so this is
# RED for the wrong-shaped reason (an empty list) rather than the rows, until the coder
# tells "asked for nothing" (`[]`) apart from "asked for no filter" (`None`) - the SAME
# split `ReorderRun.product_ids`'s own column comment already draws.
# --------------------------------------------------------------------------------- #

def test_c2h_product_ids_none_means_no_product_filter_at_all(db, chain):
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    import uuid

    f = chain
    other_cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=f"{MARKER}-CAT3-{uuid.uuid4().hex[:8]}",
        category_name=f"{MARKER} cat3",
    )
    other_uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_name=f"{MARKER}-uom3-{uuid.uuid4().hex[:8]}",
        uom_code=f"U3{uuid.uuid4().hex[:6]}",
    )
    db.add_all([other_cat, other_uom])
    db.flush()
    other_product = Product(
        id=str(uuid.uuid4()), product_code=f"{MARKER}-OTHER2-{uuid.uuid4().hex[:8]}",
        product_name="other product 2", category_id=other_cat.id, base_uom_id=other_uom.id,
        list_price=0, is_active=True, is_discontinued=False,
    )
    db.add(other_product)
    db.flush()
    leg_this = _scope_row(db, product=f["product"], qty=2, delivery=date(2026, 10, 1))
    leg_other = _scope_row(db, product=other_product, qty=3, delivery=date(2026, 10, 1))
    db.flush()

    rows = run_scope_oi_rows(db, None)

    ids = _ids(rows)
    assert leg_this["row"].id in ids, (
        "product_ids=None must not drop every row - it must apply NO product filter "
        f"at all: {rows}"
    )
    assert leg_other["row"].id in ids, rows
