"""Demand the pool's own stock covers is a suggestion, never a silent omission.

> "even if BRW holds 5 on hand, it also requires buying, that's the gist, we can recommend
>  to use stock, but it needs to appear in the reorder planning as a suggestion, cause maybe
>  CS overlook, we can suggest this, but never help the user to decide that oh this use
>  stock, so i don't include this in reorder planning, this is no no"

An order-inquiry line has already been through CS: they looked at what the branch holds and
decided this quantity needs buying. The engine finding stock in the pool is worth SAYING,
and is not the engine's decision to take. `_emit_pool` used to write nothing at all when the
trigger did not fire, so a covered line vanished and the system had quietly chosen "use
stock" on the planner's behalf.

MWC7624-RL-S10 is the real case: 1 unit committed at BRW-IB, 5 sitting at BRW-BB in the same
BRW pool, no row in the plan.

The same sentence has to be said with pooled netting OFF, which is how every live policy is
configured. With netting off each bin is planned on its own, so the bin short by 1 correctly
gets a Buy row - and the 5 units standing in its sibling go unmentioned, which is the half
of the quote ("we can suggest this") the plan still owed. The quantity does not change: the
row names the stock so the planner can decide, exactly as the covered row does.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


def _pool(db, member_id: str, root_id: str) -> None:
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :root WHERE id = :id"),
               {"root": root_id, "id": member_id})


def _commit_demand(db, pid: str, wid: str, qty: float, *, demand_class=None) -> None:
    """An open sales-order line: committed demand at that location.

    ``demand_class`` decides what the engine may DO with it, which is why the sibling cases
    below pass one. Unclassified demand is carried and shown and never sized (AC-E06), so a
    bin holding only unclassified demand never triggers a buy however short it is; retail
    demand is netted and sized, which is the ordinary shortage a plan acts on.
    """
    soid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, demand_class, source_system, "
        "source_ref, created_at, updated_at) "
        "VALUES (:id, :num, 'open', :cls, 'scm_order_inquiry', 'order_inquiry', now(), now())"
    ), {"id": soid, "num": f"ZZTSO-{soid[:8]}", "cls": demand_class})
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_required, qty_delivered, line_status, purchasing_status, "
        "created_at, updated_at) "
        "VALUES (:id, :so, :p, :w, :q, :q, 0, 'open', 'needs_purchase', now(), now())"
    ), {"id": str(uuid.uuid4()), "so": soid, "p": pid, "w": wid, "q": qty})


def _recs(db, run_id: str, pid: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(
        "SELECT rec_type, warehouse_id, recommended_qty, rounded_qty, unit_cost, "
        "       cash_impact, triggered_reason, inputs "
        "FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
    ), {"r": run_id, "p": pid}).mappings().all()]


@pytest.fixture
def covered_pool(scm_app):
    """A pool holding more than the demand committed against one of its members.

    Shaped after the real case: the shortage is in the branch bin, the stock is in a sibling
    bin of the same pool, so pooled netting covers it and no purchase is triggered.

    Two details are production's, not decoration. The root points at ITSELF, the way all
    sixteen real pool roots do, so the fixture cannot pass on a COALESCE the live data never
    exercises. And `pool_netting` is switched ON: it is off by default (buying less on the
    strength of a transfer nobody agreed to under-buys), and with it off each bin is its own
    singleton pool, so "available in this pool" would be the bin's own nothing and the case
    below would be testing a shape that does not exist. The netting-OFF behaviour is a
    separate contract, pinned further down.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    root = _mk_warehouse(db, "ZZTW-ROOT")
    bin_ = _mk_warehouse(db, "ZZTW-BIN")
    _pool(db, root, root)
    _pool(db, bin_, root)
    pid = _mk_product(db, f"ZZTP-COV-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, root, 500)          # plenty in the pool root
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _commit_demand(db, pid, bin_, 1)       # CS says: buy 1
    _link(db, pid, _mk_supplier(db, "ZZT Covered Supplier"), moq=None, mult=None, cost=40)
    db.flush()
    return db, pid, root, bin_


def test_a_covered_line_still_appears_in_the_plan(covered_pool):
    db, pid, root, _bin = covered_pool
    created = svc.create_run(db, ["ZZTW-ROOT", "ZZTW-BIN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rows = _recs(db, created["run_id"], pid)
    covered = [r for r in rows if r["rec_type"] == "covered"]

    assert covered, "a line the pool covers must still be shown, not silently dropped"
    assert not [r for r in rows if r["rec_type"] == "buy"], (
        "the pool genuinely covers it, so it is a suggestion and not a purchase"
    )


def test_the_row_states_both_numbers_the_choice_turns_on(covered_pool):
    db, pid, _root, _bin = covered_pool
    created = svc.create_run(db, ["ZZTW-ROOT", "ZZTW-BIN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    row = next(r for r in _recs(db, created["run_id"], pid) if r["rec_type"] == "covered")

    assert float(row["inputs"]["covered_committed"]) == 1.0
    assert float(row["inputs"]["covered_available"]) == 500.0
    assert "available in this pool" in (row["triggered_reason"] or "")


def test_buying_anyway_has_a_quantity_and_a_price(covered_pool):
    # Without both, the planner is asked to choose between using stock and buying while
    # only one side of the comparison is on screen.
    db, pid, _root, _bin = covered_pool
    created = svc.create_run(db, ["ZZTW-ROOT", "ZZTW-BIN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    row = next(r for r in _recs(db, created["run_id"], pid) if r["rec_type"] == "covered")

    assert float(row["rounded_qty"]) == 1.0, "buy anyway means buy what was committed"
    assert float(row["unit_cost"]) == 40.0
    assert float(row["cash_impact"]) == 40.0


def test_a_covered_row_is_not_a_purchase_in_any_tally(covered_pool):
    # It is a decision nobody has taken. Counting it as a buy would report money as
    # committed that no one agreed to spend.
    db, pid, _root, _bin = covered_pool
    created = svc.create_run(db, ["ZZTW-ROOT", "ZZTW-BIN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    log = db.execute(text("SELECT run_log FROM scm.reorder_run WHERE id = :r"),
                     {"r": created["run_id"]}).scalar()
    rows = _recs(db, created["run_id"], pid)

    assert log["covered"] >= 1, "counted on its own"
    assert log["buy"] == 0, "and never inside the Buy count"
    assert float(log["total_cash_impact"]) == 0.0, "nor inside the cash total"
    assert all(r["rec_type"] != "buy" for r in rows)


def test_no_committed_demand_means_nothing_to_say(scm_app):
    # Stock sitting idle with nobody asking for it is not a withheld decision. Emitting a
    # covered row per untouched SKU would bury the ones that need a choice.
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-QUIET")
    pid = _mk_product(db, f"ZZTP-QUIET-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 90)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, "ZZT Quiet Supplier"))
    db.flush()

    created = svc.create_run(db, ["ZZTW-QUIET"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    assert not [r for r in _recs(db, created["run_id"], pid) if r["rec_type"] == "covered"]


def test_a_real_shortage_is_still_a_buy_not_a_suggestion(scm_app):
    # The change must not turn purchases into suggestions: when the pool cannot cover the
    # demand, the plan still says buy.
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTW-SHORT")
    pid = _mk_product(db, f"ZZTP-SHORT-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 2)
    _mk_demand(db, pid, wid, 11.0)
    _commit_demand(db, pid, wid, 40)
    _link(db, pid, _mk_supplier(db, "ZZT Short Supplier"))
    db.flush()

    created = svc.create_run(db, ["ZZTW-SHORT"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rows = _recs(db, created["run_id"], pid)
    assert [r for r in rows if r["rec_type"] == "buy"]
    assert not [r for r in rows if r["rec_type"] == "covered"]


# =========================================================================== #
# netting OFF - the live configuration
# =========================================================================== #


@pytest.fixture
def sibling_stock_netting_off(scm_app):
    """The same shape as ``covered_pool``, planned the way every live policy plans.

    `pool_netting` is off, so the bin is sized on itself and genuinely needs its 1 unit
    bought. The 5 units in its sibling are not netted and must not be: nobody has agreed to
    move them. They are the thing the row has to SAY.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    root = _mk_warehouse(db, "ZZTW-SIBROOT")
    bin_ = _mk_warehouse(db, "ZZTW-SIBBIN")
    _pool(db, root, root)
    _pool(db, bin_, root)
    pid = _mk_product(db, f"ZZTP-SIB-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, root, 5)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _commit_demand(db, pid, bin_, 1, demand_class="retail")
    _link(db, pid, _mk_supplier(db, "ZZT Sibling Supplier"), moq=None, mult=None, cost=40)
    db.flush()
    return db, pid, root, bin_


def _row_at(rows: list[dict], wid: str) -> dict:
    return next(r for r in rows if str(r["warehouse_id"]) == wid)


def test_a_buy_under_netting_off_still_names_what_the_pool_holds(sibling_stock_netting_off):
    """"BRW holds 5, it still requires buying, that's the gist" - both halves, one row.

    Netting is off, so the engine is right to buy the 1: a transfer nobody has agreed to is
    not supply. But a planner reading "Buy 1" with no mention of the 5 standing one bin away
    has been given half the picture, and the choice the quote asks for (use the stock, or
    buy anyway) cannot be made off this screen. The quantity is untouched; what is added is
    the sentence.
    """
    db, pid, root, bin_ = sibling_stock_netting_off
    created = svc.create_run(db, ["ZZTW-SIBROOT", "ZZTW-SIBBIN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rows = _recs(db, created["run_id"], pid)
    buy = _row_at([r for r in rows if r["rec_type"] == "buy"], bin_)

    assert float(buy["rounded_qty"]) == 1.0, "the hint changes no quantity"
    assert float(buy["inputs"]["sibling_available"]) == 5.0
    assert buy["inputs"]["sibling_pool_code"] == "ZZTW-SIBROOT"
    assert "5 available at ZZTW-SIBROOT" in (buy["triggered_reason"] or "")


def test_the_bin_holding_the_stock_is_not_told_about_itself(sibling_stock_netting_off):
    """GUARD: the sibling total is what OTHER bins hold, never the row's own stock.

    Counting a bin's own on-hand as sibling cover would put the hint on every row in the
    plan, and a hint that fires everywhere is read nowhere.
    """
    db, pid, root, _bin = sibling_stock_netting_off
    created = svc.create_run(db, ["ZZTW-SIBROOT", "ZZTW-SIBBIN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    for row in _recs(db, created["run_id"], pid):
        if str(row["warehouse_id"]) == root:
            assert row["inputs"].get("sibling_available") is None
            assert "available at" not in (row["triggered_reason"] or "")


def test_a_shortage_no_sibling_can_cover_says_nothing_extra(scm_app):
    """GUARD: the hint fires only when the pool could actually answer the shortage.

    A bin short 40 beside a sibling holding 2 is still short 38 after any transfer, so
    naming the 2 would add a line of noise to a row whose decision it cannot change.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = false"))
    root = _mk_warehouse(db, "ZZTW-THINROOT")
    bin_ = _mk_warehouse(db, "ZZTW-THINBIN")
    _pool(db, root, root)
    _pool(db, bin_, root)
    pid = _mk_product(db, f"ZZTP-THIN-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, root, 2)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _commit_demand(db, pid, bin_, 40, demand_class="retail")
    _link(db, pid, _mk_supplier(db, "ZZT Thin Supplier"), moq=None, mult=None, cost=40)
    db.flush()

    created = svc.create_run(db, ["ZZTW-THINROOT", "ZZTW-THINBIN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    buy = _row_at([r for r in _recs(db, created["run_id"], pid) if r["rec_type"] == "buy"],
                  bin_)
    assert float(buy["rounded_qty"]) == 40.0
    assert buy["inputs"].get("sibling_available") is None
    assert "available at" not in (buy["triggered_reason"] or "")


def test_a_long_trigger_reason_gives_way_rather_than_cutting_the_note_in_half():
    """``triggered_reason`` is 100 characters wide, and half a sentence says nothing.

    Pure function, no run needed: the budget is the point. The trigger's wording is also
    carried whole in ``inputs.reason_label``, while the sibling figures exist nowhere else
    on the row, so it is the trigger that gives way.
    """
    cell = {
        "reason_label": "periodic_review: net -1 < order-up-to 0 on review cadence "
                        "for a location whose code is long",
        "sibling_available": 5.0,
        "sibling_pool_code": "ZZTW-SIBROOT",
    }

    label = svc._with_sibling_note(cell)

    assert len(label) <= 100
    assert label.endswith("5 available at ZZTW-SIBROOT (netting off)")
    assert label.startswith("periodic_review: net -1")
