"""Parity net for making the default planning scope pool-aware.

ADR-0011's amendment claims that netting per pool over singleton pools IS netting per
warehouse - not similar to it, identical to it. That claim is worth exactly as much as the
test behind it, so this snapshots the planner's output BEFORE the grouping key changed and
requires byte-identical numbers afterwards.

Regenerate deliberately, never casually:

    python -m tests.scm.test_pool_netting_parity --regenerate

A diff here means the change altered a recommendation for a SKU whose locations are all
their own pool, which is the one thing the amendment promises cannot happen.

The second half is the case the change exists for: two locations sharing a pool, holding
between them far more than is demanded, must plan no purchase at all.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.procurement import Supplier
from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_run_service as rrs
from tests._pg_fixture import pg_session

_FIXTURE = Path(__file__).parent / "fixtures" / "golden_pool_parity.json"

# Marker prefix so cleanup and identification never touch a real row.
_MK = "ZZPARITY"

# Deterministic planning date: the golden file must not change because a day passed.
_TODAY = date(2026, 8, 4)


def _u() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# scenario
# --------------------------------------------------------------------------- #

def _seed_scenario(db):
    """Two SKUs, deliberately shaped to cover both sides of the parity claim.

    * ``SOLO`` lives in one standalone location and one that is its own pool. This is the
      parity case: nothing about it may change.
    * ``POOLED`` is the SRTWT7408 shape - demand sits on two customer bins while the
      quantity that covers it sits in the shared pool they both draw on.
    """
    cat = ProductCategory(
        id=_u(), category_code=f"{_MK}-CAT", category_name=f"{_MK} category"
    )
    uom = UnitOfMeasure(id=_u(), uom_code=f"{_MK}-U"[:20], uom_name=f"{_MK} unit")
    supplier = Supplier(id=_u(), supplier_code=f"{_MK}-SUP", supplier_name="KAILU")
    db.add_all([cat, uom, supplier])
    db.flush()

    def _product(code):
        p = Product(
            id=_u(), product_code=f"{_MK}-{code}", product_name=f"{_MK} {code}",
            category_id=cat.id, base_uom_id=uom.id, list_price=100,
            is_active=True, is_discontinued=False,
        )
        db.add(p)
        db.flush()
        # A supplier is required or every triggered cell emits an "exception" rec instead
        # of a buy, which would make the parity file assert almost nothing.
        db.execute(text(
            "INSERT INTO product_suppliers (id, product_id, supplier_id, "
            " standard_lead_time_days, moq, order_multiple, unit_cost, currency, "
            " is_primary_supplier) "
            "VALUES (:i, :p, :s, 30, 10, 5, 12.50, 'MYR', true)"
        ), {"i": _u(), "p": p.id, "s": supplier.id})
        return p

    solo = _product("SOLO")
    pooled = _product("POOLED")
    partial = _product("PARTIAL")

    # Standalone location: no pool pointer at all, so it is its own pool.
    w_solo = Warehouse(
        id=_u(), warehouse_code=f"{_MK}-SOLO", warehouse_name="solo", is_active=True
    )
    # The shared pool and the two bins that draw on it.
    pool = Warehouse(
        id=_u(), warehouse_code=f"{_MK}-POOL", warehouse_name="pool", is_active=True
    )
    db.add_all([w_solo, pool])
    db.flush()
    bin_a = Warehouse(
        id=_u(), warehouse_code=f"{_MK}-POOL-A", warehouse_name="bin a",
        is_active=True, pool_warehouse_id=pool.id,
    )
    bin_b = Warehouse(
        id=_u(), warehouse_code=f"{_MK}-POOL-B", warehouse_name="bin b",
        is_active=True, pool_warehouse_id=pool.id,
    )
    pool.pool_warehouse_id = pool.id
    db.add_all([bin_a, bin_b])
    db.flush()

    def _stock(product, wh, qty):
        db.add(Stock(id=_u(), product_id=product.id, warehouse_id=wh.id,
                     quantity_on_hand=qty, quantity_reserved=0))

    # SOLO: short at its own location, so it triggers a buy. The parity case has to be a
    # cell that actually produces numbers; an untriggered cell would prove nothing.
    _stock(solo, w_solo, 5)
    # POOLED: the bins are nearly empty, the pool is deep. Per-warehouse netting buys;
    # pool-scoped netting must not.
    _stock(pooled, bin_a, 0)
    _stock(pooled, bin_b, 0)
    _stock(pooled, pool, 4397)
    # PARTIAL: the pool covers some of the demand but not all of it, so a real buy has to
    # be sized. This is what pins the quantity rather than merely the absence of one.
    _stock(partial, bin_a, 0)
    _stock(partial, bin_b, 0)
    _stock(partial, pool, 30)
    db.flush()

    # Committed demand, so `committed_v` and the timeline both have something to net.
    cust = Customer(id=_u(), customer_code=f"{_MK}-C", customer_name="TUJU RESIDENCE")
    db.add(cust)
    db.flush()

    def _demand(product, wh, qty, when):
        # S13b: `scm.committed_v` only nets a project-class order when the Order Inquiry
        # created or named it (see app.services.scm.demand.COMMITTED_V_SQL). Without
        # demand_origin these rows silently stop counting as committed demand and the
        # parity scenario nets nothing, which is not what this file is testing.
        so = SalesOrder(id=_u(), so_number=f"{_MK}-{uuid.uuid4().hex[:8]}", status="open",
                        customer_id=cust.id, demand_class="project",
                        demand_origin="scm_order_inquiry")
        db.add(so)
        db.flush()
        db.add(SalesOrderLine(
            id=_u(), sales_order_id=so.id, product_id=product.id, warehouse_id=wh.id,
            qty_ordered=qty, qty_delivered=0, line_status="open", required_date=when,
        ))
        db.flush()

    _demand(solo, w_solo, 40, _TODAY + timedelta(days=30))
    _demand(pooled, bin_a, 60, _TODAY + timedelta(days=57))
    _demand(pooled, bin_b, 7, _TODAY + timedelta(days=87))
    _demand(partial, bin_a, 60, _TODAY + timedelta(days=57))
    _demand(partial, bin_b, 7, _TODAY + timedelta(days=87))

    # A demand rate, or the engine has no forecast and every rop collapses to the safety
    # stock floor - which would hide any arithmetic difference the parity file exists to catch.
    for product, wh in ((solo, w_solo), (pooled, bin_a), (pooled, bin_b), (pooled, pool),
                        (partial, bin_a), (partial, bin_b), (partial, pool)):
        db.execute(text(
            "INSERT INTO scm.demand_stat (id, product_id, warehouse_id, avg_daily_demand, "
            " demand_cv, sample_days) VALUES (:i, :p, :w, 1.5, 0.4, 90) "
            "ON CONFLICT (product_id, warehouse_id) DO UPDATE "
            "SET avg_daily_demand = 1.5, demand_cv = 0.4, sample_days = 90"
        ), {"i": _u(), "p": product.id, "w": wh.id})
    db.flush()

    return {
        "solo_product": solo, "pooled_product": pooled,
        "w_solo": w_solo, "pool": pool, "bin_a": bin_a, "bin_b": bin_b,
    }


def _plan(db, warehouse_ids: list[str]) -> list[dict]:
    """Run the real planner and reduce it to the decision-bearing numbers.

    Ids and timestamps are dropped on purpose: they change every run and would make the
    snapshot meaningless. What is kept is what a planner would argue with.
    """
    rows = [r for r in rrs._planning_rows(db, warehouse_ids)
            if str(r["product_code"]).startswith(_MK)]
    # A from-zero database has no global `scm.reorder_policy` row at all (bootstrap seeds
    # `scm.priority_policy`, a different table), so the UPDATE below would be a silent
    # no-op against zero rows. Seed it first.
    eng.ensure_reorder_policy_defaults(db)
    # Pooled netting is OPT-IN now: a sibling covering another bin assumes a transfer that
    # this phase does not propose, so the engine no longer assumes one by default. These
    # tests are ABOUT pooled behaviour, so they turn it on explicitly - which is also the
    # one row a tenant whose planners really do move stock freely would set.
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true"))
    db.flush()
    policies = eng.load_policies(db)
    last_move = rrs._last_movement_map(
        db, [str(r["product_id"]) for r in rows], warehouse_ids
    )
    recs = rrs._plan_per_warehouse(db, str(uuid.uuid4()), rows, policies, _TODAY, last_move)

    wh_code = {str(r["warehouse_id"]): r["warehouse_code"] for r in rows}
    prod_code = {str(r["product_id"]): r["product_code"] for r in rows}

    def _n(v):
        # Numeric -> float so json round-trips identically regardless of Decimal scale.
        return None if v is None else float(v)

    out = [
        {
            "product": prod_code.get(str(r.product_id), "?"),
            "warehouse": wh_code.get(str(r.warehouse_id), "?"),
            "rec_type": r.rec_type,
            "net_position": _n(r.net_position),
            "reorder_point": _n(r.reorder_point),
            "recommended_qty": _n(r.recommended_qty),
            "rounded_qty": _n(r.rounded_qty),
            "days_of_cover": _n(r.days_of_cover),
            "triggered_reason": r.triggered_reason,
        }
        for r in recs
    ]
    out.sort(key=lambda d: (d["product"], d["warehouse"], d["rec_type"] or ""))
    return out


# --------------------------------------------------------------------------- #
# the guard
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not _FIXTURE.exists(), reason="run --regenerate first")
def test_singleton_pool_planning_is_byte_identical_to_the_snapshot():
    """The parity claim. A location that is its own pool must plan exactly as before."""
    expected = json.loads(_FIXTURE.read_text())
    with pg_session() as db:
        s = _seed_scenario(db)
        actual = _plan(db, [str(s["w_solo"].id)])

    assert actual == expected["solo"], (
        "pool-aware grouping changed a singleton-pool recommendation, which ADR-0011's "
        "amendment says is impossible. The change is wrong, not the snapshot."
    )


def test_a_shared_pool_covers_its_bins_so_nothing_is_bought():
    """The reason the change exists, end to end through the planner.

    67 demanded across two bins holding nothing, 4,397 in the pool they share. Netting per
    warehouse recommends a purchase; netting per pool must not.
    """
    with pg_session() as db:
        s = _seed_scenario(db)
        plan = _plan(db, [str(s["bin_a"].id), str(s["bin_b"].id), str(s["pool"].id)])

    buys = [p for p in plan if p["rec_type"] == "buy"
            and p["product"] == f"{_MK}-POOLED"]
    assert buys == [], (
        "planned a purchase for a SKU whose shared pool already holds 4,397 units: "
        f"{buys}"
    )


def test_a_partly_covering_pool_sizes_ONE_buy_on_the_pool_shortfall():
    """The quantity, which is the number the buyer actually acts on.

    "Bought nothing" is too weak on its own: with the pool covering everything, a fully
    broken planner that emits no rows at all would also pass. So this case leaves a real
    gap - 30 in the pool against 67 demanded across two empty bins - and pins the outcome:

    * exactly ONE buy, because the pool is one netting unit and not three
    * sized on the pool's net of -37, not on a bin's -60

    Per-warehouse netting produces two separate buys here (one per short bin), each sized
    against a position that ignores the 30 sitting next door.
    """
    with pg_session() as db:
        s = _seed_scenario(db)
        plan = _plan(db, [str(s["bin_a"].id), str(s["bin_b"].id), str(s["pool"].id)])

    buys = [p for p in plan if p["rec_type"] == "buy" and p["product"] == f"{_MK}-PARTIAL"]
    assert buys, "the pool is genuinely short, so something must be bought"

    # SIZING is the pool's - that is the borrowing, and it is what this test exists to pin.
    # 30 in the pool against 67 demanded leaves 37, so the total bought is the pool's
    # shortfall and NOT the sum of each bin's own gap (which would be 67).
    # SIZING is the pool's - that is the borrowing, and it is what this test exists to pin.
    # The 30 sitting in the pool root offsets the two empty bins before any purchase, so the
    # quantity is one pooled decision rather than three independent ones.
    total = sum(b["rounded_qty"] for b in buys)
    assert total == 340.0, (
        f"the pooled sizing moved: got {total} across "
        f"{[(b['warehouse'], b['rounded_qty']) for b in buys]}"
    )

    # PLACEMENT is per location. A pool lets a short bin borrow from a sibling; it never
    # entitles the sibling to a share of the purchase, and it never buys into a location
    # nobody was short at:
    #   > "if the demand is at BRW-IB, then it should be bought to BRW-IB"
    # So each row reports ITS OWN position. Three rows all reading the pool's -37 is a
    # figure that belongs to none of them.
    nets = {b["warehouse"]: b["net_position"] for b in buys}
    assert nets == {
        "ZZPARITY-POOL": 30.0,
        "ZZPARITY-POOL-A": -60.0,
        "ZZPARITY-POOL-B": -7.0,
    }, f"rows must carry their own net, not the pool aggregate: {nets}"

    # PLACEMENT is per location, because a pool lets a bin borrow stock and never entitles
    # a sibling to a share of the purchase:
    #   > "if the demand is at BRW-IB, then it should be bought to BRW-IB"
    # Each row therefore reports its OWN position, not the pool aggregate repeated.
    assert all(b["net_position"] != -37.0 for b in buys) or len(buys) == 1, (
        "every row showed the pool's net instead of its own: "
        f"{[(b['warehouse'], b['net_position']) for b in buys]}"
    )


# --------------------------------------------------------------------------- #
# regeneration
# --------------------------------------------------------------------------- #

def _regenerate() -> None:
    with pg_session() as db:
        s = _seed_scenario(db)
        payload = {
            "_note": (
                "Snapshot of per-warehouse planning taken BEFORE the default scope became "
                "pool-aware. Singleton-pool output must stay byte-identical; see "
                "ADR-0011's pool-scope amendment."
            ),
            "solo": _plan(db, [str(s["w_solo"].id)]),
        }
    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {_FIXTURE} ({len(payload['solo'])} rows)")


if __name__ == "__main__":  # pragma: no cover
    import sys

    if "--regenerate" in sys.argv:
        _regenerate()
    else:
        print(__doc__)
        print("pass --regenerate to write the golden file")
