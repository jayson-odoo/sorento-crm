"""UAC E3 / E4 - the plan counts PRODUCTS, and Confirm covers exactly what was decided.

R14: "Confirm (N), Save (N), 'N of Total made' count distinct products, not locations."
The verified bug (plan fact F2) is that `list_plan_row_decisions` counted RECOMMENDATIONS:
a product-grain row fans one decision out to every location it summed, so a product held
in three bins read as three decisions out of three rows when the buyer had made one.

G5 (S6, `reorder-feedback-9sep.md`, 9 Sep 2026 - "Confirm never sweeps"): REVERSES R3
("Confirm covers untouched rows as the engine suggestion; skipped rows are left out").
Under R3, Confirm drafted an untouched row at the engine's own suggestion so a buyer who
agreed with the whole plan did not have to touch every row to buy any of it; under G5 an
untouched row is left exactly as undecided as it was - what the buyer decided is what is
bought, exactly. Every test below that used to pin the R3 sweep is RE-PINNED to G5 rather
than deleted, so the reversal itself stays a regression pin.
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

def test_confirm_drafts_only_the_amended_row_never_the_untouched_or_skipped(db):
    """G5 (S6, 9 Sep 2026 - "Confirm never sweeps"): re-pinned from the R3-era
    `test_confirm_drafts_the_untouched_product_as_the_suggestion_and_skips_the_skipped`.
    The untouched product used to be bought at the engine's own suggestion; now it is
    left exactly as undecided as it was, same as the skip."""
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

    assert out["confirmed_count"] == 1, "only the amended row - G5, Confirm never sweeps"

    amended_line = _lines_for_product(db, amended.id)
    assert len(amended_line) == 1
    assert float(amended_line[0]["qty_ordered"]) == 45

    # G5: nobody touched it, so Confirm leaves it exactly as undecided as it was.
    assert _lines_for_product(db, untouched.id) == [], "an untouched row is never swept in"

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
    """G5: re-pinned - an untouched product drafts nothing, and a second confirm still
    drafts nothing (there is no line to "reconcile" any more)."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "confirm supplier twice")
    plan = run(db)
    prod = product(db, cat, uom)
    recommendation(db, plan, prod, warehouse(db), qty=70, sup=sup)

    first = dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    second = dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    assert first["confirmed_count"] == 0
    assert second["confirmed_count"] == 0
    assert _lines_for_product(db, prod.id) == []


def test_untouched_product_across_three_bins_confirms_once_then_is_idempotent(db):
    """G5: re-pinned from the R3-era test of the same name. An untouched product across
    THREE bins is not swept in by Confirm, however many locations it sums - decided/total
    stays 0/1 on the first pass and the second pass changes nothing either."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "three bin supplier")
    plan = run(db)
    prod = product(db, cat, uom)
    bins = [warehouse(db) for _ in range(3)]
    for wh in bins:
        recommendation(db, plan, prod, wh, qty=20, sup=sup)

    first = dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    assert first["confirmed_count"] == 0, "nobody decided this product"
    assert _lines_for_product(db, prod.id) == []

    listed = dsvc.list_plan_row_decisions(db, plan.id)
    assert (listed["decided_count"], listed["total_count"]) == (0, 1)

    second = dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    assert second["confirmed_count"] == 0, "still nothing to confirm"
    assert _lines_for_product(db, prod.id) == []

    listed_again = dsvc.list_plan_row_decisions(db, plan.id)
    assert (listed_again["decided_count"], listed_again["total_count"]) == (0, 1)


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
    """`ids` narrows `_confirm_location_grain`'s recs query to just the named ones (plan
    section 5.6) - unaffected by G5's removal of the untouched sweep. Re-pinned on two
    DECIDED recs rather than two untouched ones: a confirm naming only ONE drafts only
    that one, and recording a decision is separate from confirming it - both still read
    decided either way."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "narrowed ids supplier")
    plan = run(db, grain="location")
    wh = warehouse(db)
    named, other = product(db, cat, uom), product(db, cat, uom)
    rec_named = recommendation(db, plan, named, wh, qty=40, sup=sup)
    rec_other = recommendation(db, plan, other, wh, qty=25, sup=sup)
    dsvc.record_plan_row_decision(db, rec_named.id, "buy", 40, [], None, [], None, ACTOR)
    dsvc.record_plan_row_decision(db, rec_other.id, "buy", 25, [], None, [], None, ACTOR)

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
    assert other_lines == [], "a decided rec outside `ids` is not drafted this round"

    listed = dsvc.list_plan_row_decisions(db, plan.id)
    assert (listed["decided_count"], listed["total_count"]) == (2, 2), (
        "recording a decision is separate from confirming it - both rows read decided"
    )


def test_untouched_confirms_nothing_on_a_location_grain_run_too(db):
    """G5's own wording carries no grain qualifier ("Confirm never sweeps") - re-pinned
    from the R3-era test of the same shape: a location run's untouched row is left
    exactly as undecided as a product run's is."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "location grain untouched supplier")
    plan = run(db, grain="location")
    untouched = product(db, cat, uom)
    recommendation(db, plan, untouched, warehouse(db), qty=70, sup=sup)

    out = dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    assert out["confirmed_count"] == 0, "nobody decided this row"
    lines = db.execute(text(
        "SELECT qty_ordered FROM purchase_order_lines WHERE product_id = :p"
    ), {"p": untouched.id}).mappings().all()
    assert lines == []


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


def test_confirming_leaves_undecided_rows_with_no_decision_at_all(db):
    """G5 (re-pinned from `test_confirming_untouched_rows_records_the_decision_they_were_
    bought_at`): Confirm never manufactures a decision for a row nobody touched. Before
    this, an untouched row Confirm bought got a `PlanRowDecision` written FOR it (R3's own
    bookkeeping); now a row with no decision stays exactly that way after Confirm runs -
    the pill stays Suggested and "N of Total made" stays unchanged.
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
    assert out["decided_count"] == 0, "confirm must not itself write a decision"
    assert out["total_count"] == 2
    assert out["data"] == []


def test_the_same_holds_on_a_location_grain_run(db):
    """G5: re-pinned - a location run's untouched row also gets no decision from Confirm."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "untouched decision supplier loc")
    plan = run(db, grain="location")
    prod = product(db, cat, uom)
    recommendation(db, plan, prod, warehouse(db), qty=70, sup=sup)

    dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    out = dsvc.list_plan_row_decisions(db, plan.id)
    assert (out["decided_count"], out["total_count"]) == (0, 1)
    assert out["data"] == []


def test_reconfirming_an_untouched_product_still_drafts_no_line(db):
    """G5: re-pinned - with no decision, a second confirm changes nothing either; it
    does not manufacture one on a later pass."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "untouched reconfirm supplier")
    plan = run(db)
    prod = product(db, cat, uom)
    recommendation(db, plan, prod, warehouse(db), qty=70, sup=sup)

    dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    dsvc.confirm_decisions(db, plan.id, None, ACTOR)

    assert _lines_for_product(db, prod.id) == []


# ===========================================================================
# Reset planning clears what Confirm drafted, on BOTH stamps
# ===========================================================================

def test_reset_clears_the_product_grain_draft_lines_confirm_raised(db):
    """`reset_run_decisions` only pulled the `scm_recommendation`-stamped line, so a
    product-grain confirm's own line (`scm_order_summary_row`, same rec id) survived - and
    the plans list, which reads Confirmed off the draft purchase orders, said Confirmed
    forever after a reset.

    G5 (re-pinned): the row now has to be DECIDED for Confirm to draft anything at all -
    an untouched row (the R3-era setup) drafts nothing for reset to clear.
    """
    cat, uom = category_and_uom(db)
    sup = supplier(db, "reset supplier")
    plan = run(db)
    wh = warehouse(db)
    prod = product(db, cat, uom)
    rec = recommendation(db, plan, prod, wh, qty=70, sup=sup)
    dsvc.record_plan_row_decision(db, rec.id, "buy", 70, [], None, [], None, ACTOR)

    dsvc.confirm_decisions(db, plan.id, None, ACTOR)
    assert _draft_lines_on_run(db, plan.id), "confirm drafted a line to begin with"

    dsvc.reset_run_decisions(db, plan.id, ACTOR)

    assert _draft_lines_on_run(db, plan.id) == []
    assert _lines_for_product(db, prod.id) == []
    listed = dsvc.list_plan_row_decisions(db, plan.id)
    assert listed["decided_count"] == 0


# ===========================================================================
# S6 (reorder-feedback-9sep.md, G5 ruling 9 Sep 2026) - Confirm never sweeps
#
# Reverses R3 above: "Confirm covers untouched rows as the engine suggestion" is
# retired. What the buyer decided is what is bought - exactly, and nothing else.
# ===========================================================================

def test_confirm_drafts_only_the_decided_row_of_three_buy_recs(db):
    """AC-S6.4(a): three buy recs, one decided - `ids=[]` (every decided row of the
    run) drafts exactly the decided product's line. The other two get NO PO line and
    NO decision row of their own - Confirm must not itself manufacture a decision for
    a row nobody touched."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "s6 three recs supplier")
    plan = run(db)
    wh = warehouse(db)
    decided = product(db, cat, uom)
    left1 = product(db, cat, uom)
    left2 = product(db, cat, uom)
    rec_decided = recommendation(db, plan, decided, wh, qty=40, sup=sup)
    recommendation(db, plan, left1, wh, qty=70, sup=sup)
    recommendation(db, plan, left2, wh, qty=30, sup=sup)

    dsvc.record_plan_row_decision(db, rec_decided.id, "buy", 40, [], None, [], None, ACTOR)

    out = dsvc.confirm_decisions(db, plan.id, [], ACTOR)

    assert out["confirmed_count"] == 1, "only the decided product is confirmed"
    decided_line = _lines_for_product(db, decided.id)
    assert len(decided_line) == 1
    assert float(decided_line[0]["qty_ordered"]) == 40
    assert _lines_for_product(db, left1.id) == [], "an undecided row gets no PO line"
    assert _lines_for_product(db, left2.id) == [], "an undecided row gets no PO line"

    listed = dsvc.list_plan_row_decisions(db, plan.id)
    assert listed["decided_count"] == 1, "confirm must not itself decide the other two"
    assert listed["total_count"] == 3


def test_confirm_with_nothing_decided_confirms_nothing(db):
    """AC-S6.4(b): a run with zero decisions answers 200 with confirmed=0 and drafts
    nothing at all - Confirm (0) really means nobody has bought anything yet."""
    cat, uom = category_and_uom(db)
    sup = supplier(db, "s6 none decided supplier")
    plan = run(db)
    wh = warehouse(db)
    a = product(db, cat, uom)
    b = product(db, cat, uom)
    recommendation(db, plan, a, wh, qty=70, sup=sup)
    recommendation(db, plan, b, wh, qty=30, sup=sup)

    out = dsvc.confirm_decisions(db, plan.id, [], ACTOR)

    assert out["confirmed_count"] == 0
    assert out["po_count"] == 0
    assert _lines_for_product(db, a.id) == []
    assert _lines_for_product(db, b.id) == []
