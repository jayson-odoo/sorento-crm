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


def test_untouched_product_across_three_bins_confirms_once_then_is_idempotent(db):
    """PLAN section 9, the B2 deviation: an untouched product confirmed under R3 gets a
    `PlanRowDecision` PER MEMBER with `buy_qty` set to the PRODUCT's whole quantity, not
    that member's share - so a product held in THREE bins drafts its total once on the
    first confirm, and a second confirm reads that decision back through the grid path
    (`_confirm_product_grain`'s own precedence) rather than re-summing three untouched
    recommendations into triple the quantity. E4/R14: decided/total still read 1/1 - one
    product, however many locations it sums."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "three bin supplier")
    plan = run(db)
    prod = product(db, cat, uom)
    bins = [warehouse(db) for _ in range(3)]
    for wh in bins:
        recommendation(db, plan, prod, wh, qty=20, sup=sup)

    first = dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    assert first["confirmed_count"] == 1, "one product, however many bins it sums"

    lines = _lines_for_product(db, prod.id)
    assert len(lines) == 3, "the product total is split back across its three real warehouses"
    assert sum(float(l["qty_ordered"]) for l in lines) == 60

    listed = dsvc.list_plan_row_decisions(db, plan.id)
    assert (listed["decided_count"], listed["total_count"]) == (1, 1)

    second = dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    assert second["confirmed_count"] == 1, "the second confirm still counts the product decided"

    lines_again = _lines_for_product(db, prod.id)
    assert len(lines_again) == 3, "no new lines appear on a re-confirm"
    assert sum(float(l["qty_ordered"]) for l in lines_again) == 60, "the total is unchanged"

    listed_again = dsvc.list_plan_row_decisions(db, plan.id)
    assert (listed_again["decided_count"], listed_again["total_count"]) == (1, 1)


# ===========================================================================
# The LOCATION-grain half of the same rulings.
# `list_plan_row_decisions` (E4/R14) reads `PlanRowDecision` joined to
# `ReorderRecommendation` with no branch on `decision_grain` at all, so it counts by
# product identically on either grain. `confirm_decisions` DOES branch
# (`decision_grain_of(run) == PRODUCT_GRAIN` picks `_confirm_product_grain`, else
# `_confirm_location_grain`), and R3's untouched-as-suggestion fallback now lives in BOTH
# halves - it used to be product-grain only, so a location run silently left every
# untouched row out of the purchase orders Confirm raised.
# ===========================================================================

def test_list_plan_row_decisions_counts_by_product_on_a_location_grain_run_too(db):
    cat, uom = category_and_uom(db)
    sup = supplier(db, "location grain count supplier")
    plan = run(db, grain="location")
    a, b = product(db, cat, uom), product(db, cat, uom)
    rec_a = recommendation(db, plan, a, warehouse(db), sup=sup)
    recommendation(db, plan, b, warehouse(db), sup=sup)

    dsvc.record_plan_row_decision(db, rec_a.id, "buy", 10, [], None, [], None, ACTOR)

    out = dsvc.list_plan_row_decisions(db, plan.id)
    assert (out["decided_count"], out["total_count"]) == (1, 2)


def test_skip_excludes_on_a_location_grain_confirm(db):
    """A skipped rec IS a decision (it counts as decided) but drafts nothing, on the
    location grain exactly as the product-grain test above pins it."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "location grain skip supplier")
    plan = run(db, grain="location")
    wh = warehouse(db)
    skipped = product(db, cat, uom)
    rec_skipped = recommendation(db, plan, skipped, wh, qty=30, sup=sup)

    dsvc.record_plan_row_decision(db, rec_skipped.id, "skip", None, [], None, [], None, ACTOR)

    listed = dsvc.list_plan_row_decisions(db, plan.id)
    assert listed["decided_count"] == 1, "a skip is still a decision, not an undecided row"

    out = dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    assert out["confirmed_count"] == 0, "a skip never drafts a purchase"

    lines = db.execute(text(
        "SELECT 1 FROM purchase_order_lines WHERE source_ref = :rid"
    ), {"rid": rec_skipped.id}).fetchall()
    assert lines == []


def test_location_grain_confirm_narrowed_by_ids_only_drafts_the_named_recs(db):
    """`ids` is the same optional narrowing both `_confirm_location_grain`'s recs query
    and its own untouched-as-suggestion loop filter on (plan section 5.6/R3). A confirm
    naming only ONE of two untouched recs must draft (and record a decision for) only
    that one - the other stays exactly as undecided as it was before Confirm ran."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "narrowed ids supplier")
    plan = run(db, grain="location")
    wh = warehouse(db)
    named, other = product(db, cat, uom), product(db, cat, uom)
    rec_named = recommendation(db, plan, named, wh, qty=40, sup=sup)
    recommendation(db, plan, other, wh, qty=25, sup=sup)

    out = dsvc.confirm_decisions(db, plan.id, [rec_named.id], ACTOR)

    assert out["confirmed_count"] == 1, "only the named rec is confirmed"

    named_lines = db.execute(text(
        "SELECT qty_ordered FROM purchase_order_lines "
        "WHERE product_id = :p AND source_system = 'scm_recommendation'"
    ), {"p": named.id}).mappings().all()
    assert len(named_lines) == 1
    assert float(named_lines[0]["qty_ordered"]) == 40

    other_lines = db.execute(text(
        "SELECT 1 FROM purchase_order_lines "
        "WHERE product_id = :p AND source_system = 'scm_recommendation'"
    ), {"p": other.id}).fetchall()
    assert other_lines == [], "a rec outside `ids` is never drafted"

    listed = dsvc.list_plan_row_decisions(db, plan.id)
    assert (listed["decided_count"], listed["total_count"]) == (1, 2), (
        "the named product picked up a decision; the other is still undecided"
    )
    assert {d["recommendation_id"] for d in listed["data"]} == {rec_named.id}


def test_untouched_confirms_as_the_suggestion_on_a_location_grain_run_too(db):
    """R3's own wording carries no grain qualifier ("Confirm covers untouched rows as
    the engine suggestion") - a location run's buyer who leaves a row alone expects the
    same "make this plan" behaviour a product run already gives them."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "location grain untouched supplier")
    plan = run(db, grain="location")
    untouched = product(db, cat, uom)
    recommendation(db, plan, untouched, warehouse(db), qty=70, sup=sup)

    out = dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    assert out["confirmed_count"] == 1, "the untouched product confirms at the engine's own qty"
    lines = db.execute(text(
        "SELECT qty_ordered FROM purchase_order_lines WHERE product_id = :p"
    ), {"p": untouched.id}).mappings().all()
    assert len(lines) == 1
    assert float(lines[0]["qty_ordered"]) == 70


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


# ===========================================================================
# R3's own bookkeeping: an untouched row that Confirm bought IS a decision
# ===========================================================================

def _draft_lines_on_run(db, run_id):
    return db.execute(text("""
        SELECT pol.id
          FROM purchase_order_lines pol
          JOIN purchase_orders po ON po.id = pol.purchase_order_id
          JOIN scm.reorder_recommendation rr ON rr.id::text = pol.source_ref
         WHERE rr.run_id = CAST(:r AS uuid) AND po.status = 'draft_recommendation'
    """), {"r": str(run_id)}).fetchall()


def test_confirming_untouched_rows_records_the_decision_they_were_bought_at(db):
    """The pill, the tiles and Confirm (N) all read `list_plan_row_decisions`.

    Before this, Confirm drafted the purchase order for an untouched product and wrote no
    decision at all, so the screen kept saying nobody had decided: the pill stayed
    Suggested, "N of Total made" stayed short, and Confirm stayed live over rows already
    in a draft PO.
    """
    cat, uom = category_and_uom(db)
    sup = supplier(db, "untouched decision supplier")
    plan = run(db)
    wh = warehouse(db)
    a, b = product(db, cat, uom), product(db, cat, uom)
    recommendation(db, plan, a, wh, qty=70, sup=sup)
    recommendation(db, plan, b, wh, qty=30, sup=sup)

    dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    out = dsvc.list_plan_row_decisions(db, plan.id)
    assert out["decided_count"] == out["total_count"] == 2
    assert {d["kind"] for d in out["data"]} == {"buy"}
    assert {float(d["buy_qty"]) for d in out["data"]} == {70.0, 30.0}
    # Every product reads Confirmed: the decision names the draft PO its line sits in.
    assert all(d["draft_po_number"] for d in out["data"])


def test_the_same_holds_on_a_location_grain_run(db):
    cat, uom = category_and_uom(db)
    sup = supplier(db, "untouched decision supplier loc")
    plan = run(db, grain="location")
    prod = product(db, cat, uom)
    recommendation(db, plan, prod, warehouse(db), qty=70, sup=sup)

    dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    out = dsvc.list_plan_row_decisions(db, plan.id)
    assert (out["decided_count"], out["total_count"]) == (1, 1)
    assert out["data"][0]["kind"] == "buy"
    assert float(out["data"][0]["buy_qty"]) == 70.0


def test_reconfirming_an_untouched_product_still_drafts_one_line(db):
    """The second confirm reads the decision the first one wrote, through the grid path -
    so the quantity it drafts is the product's whole quantity, not one member's share."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "untouched reconfirm supplier")
    plan = run(db)
    prod = product(db, cat, uom)
    recommendation(db, plan, prod, warehouse(db), qty=70, sup=sup)

    dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    lines = _lines_for_product(db, prod.id)
    assert len(lines) == 1
    assert float(lines[0]["qty_ordered"]) == 70


# ===========================================================================
# Reset planning clears what Confirm drafted, on BOTH stamps
# ===========================================================================

def test_reset_clears_the_product_grain_draft_lines_confirm_raised(db):
    """`reset_run_decisions` only pulled the `scm_recommendation`-stamped line, so a
    product-grain confirm's own line (`scm_order_summary_row`, same rec id) survived - and
    the plans list, which reads Confirmed off the draft purchase orders, said Confirmed
    forever after a reset."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "reset supplier")
    plan = run(db)
    prod = product(db, cat, uom)
    recommendation(db, plan, prod, warehouse(db), qty=70, sup=sup)

    dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    assert _draft_lines_on_run(db, plan.id), "confirm drafted a line to begin with"

    dsvc.reset_run_decisions(db, plan.id, ACTOR)

    assert _draft_lines_on_run(db, plan.id) == []
    assert _lines_for_product(db, prod.id) == []
    listed = dsvc.list_plan_row_decisions(db, plan.id)
    assert listed["decided_count"] == 0
