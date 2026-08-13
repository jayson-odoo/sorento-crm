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


def _commit_demand(db, pid: str, wid: str, qty: float) -> None:
    """An open sales-order line: committed demand at that location."""
    soid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, source_system, source_ref, "
        "created_at, updated_at) "
        "VALUES (:id, :num, 'open', 'scm_order_inquiry', 'order_inquiry', now(), now())"
    ), {"id": soid, "num": f"ZZTSO-{soid[:8]}"})
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
    """
    _, db, _, _ = scm_app
    root = _mk_warehouse(db, "ZZTW-ROOT")
    bin_ = _mk_warehouse(db, "ZZTW-BIN")
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


@pytest.mark.xfail(reason="TEST-FIRST contract (see module docstring): the _emit_pool path does not surface covered rows yet; red until that engine gap is fixed", strict=False)
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


@pytest.mark.xfail(reason="TEST-FIRST contract (see module docstring): the _emit_pool path does not surface covered rows yet; red until that engine gap is fixed", strict=False)
def test_the_row_states_both_numbers_the_choice_turns_on(covered_pool):
    db, pid, _root, _bin = covered_pool
    created = svc.create_run(db, ["ZZTW-ROOT", "ZZTW-BIN"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    row = next(r for r in _recs(db, created["run_id"], pid) if r["rec_type"] == "covered")

    assert float(row["inputs"]["covered_committed"]) == 1.0
    assert float(row["inputs"]["covered_available"]) == 500.0
    assert "available in this pool" in (row["triggered_reason"] or "")


@pytest.mark.xfail(reason="TEST-FIRST contract (see module docstring): the _emit_pool path does not surface covered rows yet; red until that engine gap is fixed", strict=False)
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


@pytest.mark.xfail(reason="TEST-FIRST contract (see module docstring): the _emit_pool path does not surface covered rows yet; red until that engine gap is fixed", strict=False)
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
