"""UAC E3 / E4 - the plan counts PRODUCTS, and Confirm covers the rows nobody touched.

R14: "Confirm (N), Save (N), 'N of Total made' count distinct products, not locations."
The verified bug (plan fact F2) is that `list_plan_row_decisions` counted RECOMMENDATIONS:
a product-grain row fans one decision out to every location it summed, so a product held
in three bins read as three decisions out of three rows when the buyer had made one.

R3: "Confirm covers untouched rows as the engine suggestion; skipped rows are left out."
Before this, Confirm drafted only what had been decided, so a buyer who agreed with the
whole plan had to touch every row to buy any of it.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.services.scm import decision_service as dsvc
from tests._pg_fixture import pg_session
from tests.scm._revamp_fixtures import (
    category_and_uom,
    product,
    recommendation,
    run,
    supplier,
    warehouse,
)
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg

pytestmark = requires_pg

ACTOR = str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        with company_scope(s, frozenset({SORENTO_COMPANY_ID})):
            yield s


def _lines_for_product(db, product_id):
    return db.execute(text(
        "SELECT qty_ordered, warehouse_id::text AS warehouse_id "
        "FROM purchase_order_lines "
        "WHERE product_id = :p AND source_system = 'scm_order_summary_row'"
    ), {"p": product_id}).mappings().all()


# ===========================================================================
# E4 - decided / total by DISTINCT product
# ===========================================================================

def test_one_product_in_three_bins_decided_once_reads_one_of_one(db):
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    sup = supplier(db, "count supplier")
    plan = run(db)
    recs = [recommendation(db, plan, prod, warehouse(db), sup=sup) for _ in range(3)]

    # The fan-out the grid performs: the SAME decision on every member of the group.
    for rec in recs:
        dsvc.record_plan_row_decision(db, rec.id, "buy", 40, [], None, [], None, ACTOR)

    out = dsvc.list_plan_row_decisions(db, plan.id)
    assert out["decided_count"] == 1, "one product decided once, not three locations"
    assert out["total_count"] == 1, "three bins of one product are one product to decide"
    # The rows themselves are still per recommendation - the pill reads off each member.
    assert len(out["data"]) == 3


def test_two_products_one_decided_reads_one_of_two(db):
    cat, uom = category_and_uom(db)
    sup = supplier(db, "count supplier b")
    plan = run(db)
    a, b = product(db, cat, uom), product(db, cat, uom)
    rec_a = recommendation(db, plan, a, warehouse(db), sup=sup)
    recommendation(db, plan, b, warehouse(db), sup=sup)

    dsvc.record_plan_row_decision(db, rec_a.id, "buy", 10, [], None, [], None, ACTOR)

    out = dsvc.list_plan_row_decisions(db, plan.id)
    assert (out["decided_count"], out["total_count"]) == (1, 2)


# ===========================================================================
# E3 - Confirm: amended, untouched, skipped
# ===========================================================================

def test_confirm_drafts_the_untouched_product_as_the_suggestion_and_skips_the_skipped(db):
    cat, uom = category_and_uom(db)
    sup = supplier(db, "confirm supplier")
    plan = run(db)
    wh = warehouse(db)

    amended = product(db, cat, uom)
    untouched = product(db, cat, uom)
    skipped = product(db, cat, uom)
    rec_amended = recommendation(db, plan, amended, wh, qty=50, sup=sup)
    recommendation(db, plan, untouched, wh, qty=70, sup=sup)
    rec_skipped = recommendation(db, plan, skipped, wh, qty=30, sup=sup)

    dsvc.record_plan_row_decision(db, rec_amended.id, "buy", 45, [], None, [], None, ACTOR)
    dsvc.record_plan_row_decision(db, rec_skipped.id, "skip", None, [], None, [], None, ACTOR)

    out = dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    assert out["confirmed_count"] == 2, "the amended and the untouched product, never the skip"

    amended_line = _lines_for_product(db, amended.id)
    assert len(amended_line) == 1
    assert float(amended_line[0]["qty_ordered"]) == 45

    # R3: nobody touched it, so it is bought at exactly what the engine sized.
    untouched_line = _lines_for_product(db, untouched.id)
    assert len(untouched_line) == 1
    assert float(untouched_line[0]["qty_ordered"]) == 70

    assert _lines_for_product(db, skipped.id) == [], "a skipped product is not bought"


def test_an_untouched_product_with_nothing_to_buy_drafts_nothing(db):
    """`rounded_qty` of zero is the engine saying "do not buy this", not an absent
    decision - drafting a zero line would put an empty row in a purchase order."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "confirm supplier zero")
    plan = run(db)
    nothing = product(db, cat, uom)
    recommendation(db, plan, nothing, warehouse(db), qty=0, sup=sup)

    out = dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    assert out["confirmed_count"] == 0
    assert _lines_for_product(db, nothing.id) == []


def test_reconfirming_an_untouched_product_reconciles_its_line(db):
    cat, uom = category_and_uom(db)
    sup = supplier(db, "confirm supplier twice")
    plan = run(db)
    prod = product(db, cat, uom)
    recommendation(db, plan, prod, warehouse(db), qty=70, sup=sup)

    dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    assert len(_lines_for_product(db, prod.id)) == 1, "re-confirm reconciles, never duplicates"


def test_a_covered_row_is_not_bought_just_because_nobody_touched_it(db):
    """Only a BUY the engine sized is confirmed untouched. A covered row is the engine
    saying the stock is already there, and R3 does not turn that into a purchase."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "confirm supplier covered")
    plan = run(db)
    prod = product(db, cat, uom)
    recommendation(db, plan, prod, warehouse(db), qty=25, sup=sup, rec_type="covered")

    out = dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    assert out["confirmed_count"] == 0
    assert _lines_for_product(db, prod.id) == []
