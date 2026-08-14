"""The reorder_level basis, end to end through a real planning run.

The pure-function coverage lives in `test_reorder_level_basis.py`. What is pinned here is the
part that only a run can prove: that the buyer's stored number reaches the engine, that it
alone decides the quantity, that an item without one is named rather than guessed at, and
that switching a policy row is the whole of turning the basis on.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.services.scm import reorder_level_service as rl
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


def _use_level_basis(db) -> None:
    """Point the GLOBAL policy at the level basis - the same one-row change an admin makes."""
    svc.eng.ensure_reorder_policy_defaults(db)
    # Every scope, not only global: the seeded product_class rows carry a higher priority
    # and would otherwise win the resolution and keep the forecast basis in play. An admin
    # switching the whole install does the same thing through the policies screen.
    db.execute(text("UPDATE scm.reorder_policy SET policy_type = 'reorder_level'"))
    db.flush()


def _set_level(db, pid: str, wid: str | None, level: float | None) -> None:
    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
        "created_at) VALUES (:id, :p, :w, :l, 'manual', now())"
    ), {"id": str(uuid.uuid4()), "p": pid, "w": wid, "l": level})
    db.flush()


def _recs(db, run_id: str, pid: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(
        "SELECT rec_type, rounded_qty, recommended_qty, triggered_reason, inputs "
        "FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
    ), {"r": run_id, "p": pid}).mappings().all()]


def _plan(db, code: str, *, on_hand: float, level: float | None,
          demand_rate: float = 0.0, moq=None, mult=None) -> list[dict]:
    wid = _mk_warehouse(db, code)
    pid = _mk_product(db, f"ZZTP-LVL-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, on_hand)
    _mk_demand(db, pid, wid, demand_rate)
    _link(db, pid, _mk_supplier(db, f"ZZT Lvl Supplier {code}"), moq=moq, mult=mult)
    if level is not None:
        _set_level(db, pid, wid, level)
    db.flush()
    created = svc.create_run(db, [code], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    return _recs(db, created["run_id"], pid)


def test_the_buy_is_the_gap_to_the_level_and_nothing_else(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)
    rows = _plan(db, "ZZTW-LVL-GAP", on_hand=8, level=20)
    buys = [r for r in rows if r["rec_type"] == "buy"]
    assert buys, "8 on hand against a level of 20 is a shortage"
    assert float(buys[0]["rounded_qty"]) == 12.0
    assert "reorder_level" in (buys[0]["triggered_reason"] or "")


def test_a_high_forecast_cannot_inflate_the_quantity(scm_app):
    # The whole reason this basis exists. Under reorder_point a demand rate of 5/day over a
    # 51-day cover window would ask for hundreds; the level says 20, so the answer is 12.
    _, db, _, _ = scm_app
    _use_level_basis(db)
    rows = _plan(db, "ZZTW-LVL-FCAST", on_hand=8, level=20, demand_rate=5.0)
    buys = [r for r in rows if r["rec_type"] == "buy"]
    assert buys
    assert float(buys[0]["rounded_qty"]) == 12.0


def test_above_the_level_nothing_is_bought(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)
    rows = _plan(db, "ZZTW-LVL-OVER", on_hand=50, level=20, demand_rate=5.0)
    assert not [r for r in rows if r["rec_type"] == "buy"]


def test_an_item_with_no_level_is_named_not_guessed_at(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)
    rows = _plan(db, "ZZTW-LVL-UNSET", on_hand=0, level=None, demand_rate=5.0)
    kinds = {r["rec_type"] for r in rows}
    assert "needs_level" in kinds, "an unset item must appear, not vanish"
    assert "buy" not in kinds, "an unset level must never be planned as 0"
    row = next(r for r in rows if r["rec_type"] == "needs_level")
    assert "no reorder level set" in (row["triggered_reason"] or "")
    assert row["rounded_qty"] is None


def test_the_moq_still_shapes_the_order(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)
    rows = _plan(db, "ZZTW-LVL-MOQ", on_hand=18, level=20, moq=10, mult=4)
    buys = [r for r in rows if r["rec_type"] == "buy"]
    assert buys
    assert float(buys[0]["recommended_qty"]) == 2.0     # the honest gap
    assert float(buys[0]["rounded_qty"]) == 12.0        # max(2, moq 10) -> next multiple of 4


def test_the_row_carries_the_weekly_checklist(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)
    rows = _plan(db, "ZZTW-LVL-CHECK", on_hand=8, level=20)
    inp = next(r for r in rows if r["rec_type"] == "buy")["inputs"]
    for key in ("on_hand", "on_order", "po_ordered", "committed", "moq",
                "reorder_level", "segment"):
        assert key in inp, f"the buyer checks {key} by hand; it must be on the row"
    assert float(inp["on_hand"]) == 8.0
    assert float(inp["reorder_level"]) == 20.0


def test_the_forecast_basis_is_untouched_by_any_of_this(scm_app):
    # No policy change at all, so the seeded policies still resolve to a FORECAST basis
    # (which one depends on the product's class - reorder_point globally, periodic_review
    # for the seeded SRT-BA class). A stored level must not interfere either way, because
    # turning the basis on is a policy row and nothing else.
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    rows = _plan(db, "ZZTW-LVL-FWD", on_hand=0, level=20, demand_rate=5.0)
    buys = [r for r in rows if r["rec_type"] == "buy"]
    assert buys, "under the forecast basis a 5/day item with nothing on hand buys"
    # 51 days of cover at 5/day is far more than the level of 20 - proof the level is
    # sitting there unused rather than quietly capping the forecast basis.
    assert float(buys[0]["rounded_qty"]) > 100
    reason = buys[0]["triggered_reason"] or ""
    assert reason.startswith(("reorder_point", "periodic_review")), reason
    assert "reorder_level" not in reason


def test_a_suggestion_is_never_planned_as_a_level(scm_app):
    # A suggestion exists but nobody accepted it. The plan must still ask rather than buy.
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid = _mk_warehouse(db, "ZZTW-LVL-SUGG")
    pid = _mk_product(db, f"ZZTP-SUGG-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 1.0)
    _link(db, pid, _mk_supplier(db, "ZZT Sugg Supplier"), moq=None, mult=None)
    rl.store_suggestion(db, product_id=pid, warehouse_id=wid, suggested_level=99.0,
                        basis={"avg_monthly": 49.5, "cover_months": 2, "months_studied": 3})
    db.flush()

    created = svc.create_run(db, ["ZZTW-LVL-SUGG"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rows = _recs(db, created["run_id"], pid)
    assert {r["rec_type"] for r in rows} == {"needs_level"}
    assert float(rows[0]["inputs"]["suggested_level"]) == 99.0


# --- last purchase, split by segment where the destination is known ----------------------

def _po_line(db, pid: str, wid: str | None, cost: float, days_ago: int = 3) -> None:
    """A recent purchase. Dated relative to today on purpose: an old one makes the item
    read as dead stock, and a disposition row replaces the buy this test is about."""
    poid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, issue_date, status, created_at, "
        "updated_at) VALUES (:id, :n, CURRENT_DATE - :ago, 'closed', now(), now())"
    ), {"id": poid, "n": f"ZZTPO-{poid[:8]}", "ago": days_ago})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_received, unit_cost, line_status, created_at, updated_at) "
        "VALUES (:id, :po, :p, :w, 1, 0, :c, 'closed', now(), now())"
    ), {"id": str(uuid.uuid4()), "po": poid, "p": pid, "w": wid, "c": cost})
    db.flush()


def test_a_dealer_row_reads_a_dealer_purchase(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid = _mk_warehouse(db, "ZZTW-SEG-D")
    db.execute(text("UPDATE warehouses SET segment = 'dealer' WHERE id = :w"), {"w": wid})
    pid = _mk_product(db, f"ZZTP-SEGD-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 8)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, "ZZT Seg D"), moq=None, mult=None)
    _set_level(db, pid, wid, 20)
    _po_line(db, pid, wid, 33.0)
    db.flush()

    created = svc.create_run(db, ["ZZTW-SEG-D"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    inp = next(r for r in _recs(db, created["run_id"], pid)
               if r["rec_type"] == "buy")["inputs"]
    assert float(inp["last_purchase"]["cost"]) == 33.0
    assert inp["last_purchase_basis"] == "own_segment"


def test_a_project_row_is_not_shown_the_dealer_price(scm_app):
    # The whole reason the split exists. A purchase into the dealer bin must not be
    # presented as what a project order costs.
    _, db, _, _ = scm_app
    _use_level_basis(db)
    dealer = _mk_warehouse(db, "ZZTW-SEG-DD")
    project = _mk_warehouse(db, "ZZTW-SEG-PP")
    db.execute(text("UPDATE warehouses SET segment = 'dealer' WHERE id = :w"), {"w": dealer})
    db.execute(text("UPDATE warehouses SET segment = 'project' WHERE id = :w"), {"w": project})
    pid = _mk_product(db, f"ZZTP-SEGP-{uuid.uuid4().hex[:6]}")
    for w in (dealer, project):
        _mk_stock(db, pid, w, 8)
        _mk_demand(db, pid, w, 0.0)
        _set_level(db, pid, w, 20)
    _link(db, pid, _mk_supplier(db, "ZZT Seg P"), moq=None, mult=None)
    _po_line(db, pid, dealer, 33.0)
    db.flush()

    created = svc.create_run(db, ["ZZTW-SEG-DD", "ZZTW-SEG-PP"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rows = [r for r in _recs(db, created["run_id"], pid) if r["rec_type"] == "buy"]
    by_segment = {r["inputs"]["segment"]: r["inputs"] for r in rows}
    assert by_segment["dealer"]["last_purchase_basis"] == "own_segment"
    # The project row has no purchase of its own, so it falls back and SAYS it fell back.
    assert by_segment["project"]["last_purchase_basis"] == "unattributed"


def test_a_purchase_with_no_destination_is_never_relabelled(scm_app):
    # 12,928 of the customer's 12,940 purchase lines are like this. Calling one of them
    # "the dealer cost" would invent the attribution the buyer asked us to make.
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid = _mk_warehouse(db, "ZZTW-SEG-U")
    db.execute(text("UPDATE warehouses SET segment = 'dealer' WHERE id = :w"), {"w": wid})
    pid = _mk_product(db, f"ZZTP-SEGU-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 8)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, "ZZT Seg U"), moq=None, mult=None)
    _set_level(db, pid, wid, 20)
    _po_line(db, pid, None, 21.0)
    db.flush()

    created = svc.create_run(db, ["ZZTW-SEG-U"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    inp = next(r for r in _recs(db, created["run_id"], pid)
               if r["rec_type"] == "buy")["inputs"]
    assert float(inp["last_purchase"]["cost"]) == 21.0
    assert inp["last_purchase_basis"] == "unattributed"


def test_never_purchased_says_so_rather_than_showing_nothing(scm_app):
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid = _mk_warehouse(db, "ZZTW-SEG-N")
    pid = _mk_product(db, f"ZZTP-SEGN-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, wid, 8)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, "ZZT Seg N"), moq=None, mult=None)
    _set_level(db, pid, wid, 20)
    db.flush()

    created = svc.create_run(db, ["ZZTW-SEG-N"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    inp = next(r for r in _recs(db, created["run_id"], pid)
               if r["rec_type"] == "buy")["inputs"]
    assert inp["last_purchase"] is None
    assert inp["last_purchase_basis"] == "never_purchased"


def test_a_pooled_buy_row_still_carries_the_checklist(scm_app):
    """A pool sizes the buy; the row still has to describe the PLACE it lands in.

    Found in the browser: pooled rows were built from the aggregate cell, which has no
    on-hand, no level and no last price, so the checklist was blank on exactly the rows a
    pool produces - and a pool produces most of them.
    """
    _, db, _, _ = scm_app
    _use_level_basis(db)
    root = _mk_warehouse(db, "ZZTW-POOL-R")
    bin_ = _mk_warehouse(db, "ZZTW-POOL-B")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id = :b"),
               {"r": root, "b": bin_})
    pid = _mk_product(db, f"ZZTP-POOL-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, root, 4)
    _mk_stock(db, pid, bin_, 6)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _set_level(db, pid, root, 50)
    _set_level(db, pid, bin_, 50)
    _link(db, pid, _mk_supplier(db, "ZZT Pool Supplier"), moq=None, mult=None)
    _po_line(db, pid, bin_, 7.5)
    db.flush()

    created = svc.create_run(db, ["ZZTW-POOL-R", "ZZTW-POOL-B"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    buys = [r for r in _recs(db, created["run_id"], pid) if r["rec_type"] == "buy"]
    assert buys, "10 across the pool against a level of 100 is a shortage"
    for b in buys:
        inp = b["inputs"]
        assert inp.get("on_hand") is not None, "a pooled row must still say what is on hand"
        assert inp.get("reorder_level") is not None, "and which level it was measured against"
        assert inp.get("last_purchase_basis") is not None


def test_a_pool_where_nobody_set_a_level_buys_nothing(scm_app):
    """Found in the browser: summing the levels that exist gave a pool with NONE a target
    of 0, and 0 is a real target that any deficit trips - so it bought its whole shortage
    (52,872 units on the live data) against a number nobody chose."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    root = _mk_warehouse(db, "ZZTW-POOL-NL-R")
    bin_ = _mk_warehouse(db, "ZZTW-POOL-NL-B")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id = :b"),
               {"r": root, "b": bin_})
    pid = _mk_product(db, f"ZZTP-POOLNL-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, root, 0)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 3.0)
    _mk_demand(db, pid, bin_, 3.0)
    _link(db, pid, _mk_supplier(db, "ZZT PoolNL Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, ["ZZTW-POOL-NL-R", "ZZTW-POOL-NL-B"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rows = _recs(db, created["run_id"], pid)
    kinds = {r["rec_type"] for r in rows}
    assert "buy" not in kinds, "a pool with no level anywhere must not buy on a target of 0"
    assert "needs_level" in kinds, "and each unset member must still be named"


# --- pooled netting is opt-in ------------------------------------------------------------

def _pool_pair(db, code_root: str, root_stock: float, bin_stock: float,
               demand: float = 2.0):
    """A two-bin pool: the root holds surplus, the bin is short."""
    root = _mk_warehouse(db, f"{code_root}-R")
    bin_ = _mk_warehouse(db, f"{code_root}-B")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id = :b"),
               {"r": root, "b": bin_})
    pid = _mk_product(db, f"ZZTP-{code_root}-{uuid.uuid4().hex[:6]}")
    _mk_stock(db, pid, root, root_stock)
    _mk_stock(db, pid, bin_, bin_stock)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, demand)
    _link(db, pid, _mk_supplier(db, f"ZZT {code_root} Supplier"), moq=None, mult=None)
    db.flush()
    created = svc.create_run(db, [f"{code_root}-R", f"{code_root}-B"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    return _recs(db, created["run_id"], pid)


def test_by_default_a_bin_buys_its_own_shortage(scm_app):
    """A sibling's surplus does NOT cover a shortage unless somebody says it may.

    > "the pool, is at CS level, for them to do stock allocation, what it has to do with
    >  this leh"

    Stock moves between bins on CS's decision, taken before purchasing sees the
    requirement, and this phase does not propose transfers. Buying less on the strength of
    a move nobody agreed to under-buys, and an under-buy is invisible until it runs out.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    rows = _pool_pair(db, "ZZTW-NOPOOL", root_stock=5000, bin_stock=0)
    buys = [r for r in rows if r["rec_type"] == "buy"]
    assert buys, "the short bin must still buy, however much the sibling is sitting on"


def test_turning_pooled_netting_on_lets_the_sibling_cover(scm_app):
    """The other behaviour is a policy row away, not a deploy away."""
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    db.flush()
    rows = _pool_pair(db, "ZZTW-POOLON", root_stock=5000, bin_stock=0)
    assert not [r for r in rows if r["rec_type"] == "buy"], \
        "5,000 on the shared root covers the shortage, so nothing is bought"
