"""S2 - the reorder run universe is committed demand only, admitted at PRODUCT grain.

`PLAN-scm-reorder-oi-feedback-1sep.md` S2, `scm-reorder-oi-feedback-1sep-acceptance-
criteria.md` AC-2.1 through AC-2.5, reworked by the captain-intent ruling of 2 Sep
(PENDING CAPTAIN CONFIRM): G1 gates which PRODUCTS enter a run, not which rows. A
product with committed demand > 0 ANYWHERE among its own locations (inside the horizon)
admits ALL of its rows, so an aggregate basis (pooled netting, a network-scope buy, the
product-wide `reorder_level` basis) keeps every location's on-hand/on-order in its net.
WHICH locations get their OWN recommendation row is the separate LOCATION question, and
a location-grain basis (the default, per-warehouse policy) answers it per row at
EMISSION time (`reorder_run_service._emit_cell` and the per-member loops in `_emit_pool`
/ `_plan_network`): a location carrying none of the committed demand emits nothing of
its own there.

B1's regression, pinned here (AC-2.3): the FIRST cut of this slice gated admission per
ROW instead of per product, which stripped an uncommitted location's on-hand/on-order
from every aggregate basis reading it - on the dev-DB full-network run, 76,098 on-hand +
14,475 on-order units lost from 298 in-plan products' aggregates, flipping 55 `covered`
rows to `buy` and inflating 37 buys by 2,032 units net. Exactly the SRTWT7408 shape
("1,296 at the pool root, nothing at nine group bins", `test_reorder_per_product.py`)
ADR-0011's pooled netting exists to solve - a customer's SO names the BIN, never the
pool ROOT, so the root is almost always zero-committed itself.

Postgres only, marker-prefixed, every test seeds its own chain inside the `scm_app`
savepoint.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _link,
    _mk_committed,
    _mk_demand,
    _mk_movement,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)
from tests.scm.test_reorder_level_run import _no_master_level, _use_level_basis

pytestmark = requires_pg


def _recs(db, run_id: str, pid: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(
        "SELECT rec_type, warehouse_id::text AS warehouse_id, recommended_qty, "
        "       rounded_qty, inputs "
        "FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
    ), {"r": run_id, "p": pid}).mappings().all()]


# --------------------------------------------------------------------------- AC-2.1

def test_stock_movement_and_a_level_alone_earn_no_row_with_no_committed_demand(scm_app):
    """AC-2.1: a product with on-hand, movement, and an AutoCount master level - but zero
    committed demand anywhere - produces NO row of any kind on the unscoped daily run."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTAC1-WH")
    pid = _mk_product(db, "ZZTAC1-P")
    _mk_stock(db, pid, wid, 500)
    _mk_demand(db, pid, wid, 5.0)
    _mk_movement(db, pid, wid, 10, days_ago=5)
    db.execute(text("UPDATE products SET reorder_level = 100 WHERE id = :p"), {"p": pid})
    db.flush()

    created = svc.create_run(db, ["ZZTAC1-WH"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    assert _recs(db, created["run_id"], pid) == [], (
        "no committed demand anywhere must produce zero rows, of any rec_type"
    )


# --------------------------------------------------------------------------- AC-2.2

def test_a_named_product_with_no_committed_demand_still_enters_and_is_evaluated(scm_app):
    """AC-2.2 (G10): explicit `product_codes` at Start Plan enters that product REGARDLESS
    of committed demand, and it is fully evaluated - a buy still triggers off stock/
    forecast alone, the same treatment the SKU got before G1 existed. Admission-only
    would leave the row present but silent; that is not what a buyer who typed a SKU in
    asked for."""
    _, db, _, _ = scm_app
    wid = _mk_warehouse(db, "ZZTAC2-WH")
    pid = _mk_product(db, "ZZTAC2-P")
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, "ZZTAC2 Supplier"))
    db.flush()

    created = svc.create_run(db, ["ZZTAC2-WH"], "warehouse",
                             product_codes=["ZZTAC2-P"], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs(db, created["run_id"], pid)
    assert recs and recs[0]["rec_type"] == "buy", (
        "a named product with zero committed demand must still be planned, not merely admitted"
    )


# --------------------------------------------------------------------------- AC-2.3 / B1

def test_an_uncommitted_locations_surplus_still_covers_the_products_aggregate_net(scm_app):
    """B1 regression, covered verdict: product-wide `reorder_level` basis, two locations -
    A holds surplus with NO committed demand of its own, B carries the product's only
    committed demand and none of the stock. A's 1,000 on hand must still land in the
    product's aggregate net, so a level of 200 reads as comfortably covered rather than
    a manufactured shortage.

    Row-grain admission (rejected) excluded A entirely (committed=0 there), so agg_net
    read -50 (B alone) against the level of 200 and flipped this to a `buy` of 250 - one
    of the 55 covered->buy flips B1 names.
    """
    _, db, _, _ = scm_app
    _use_level_basis(db)
    a = _mk_warehouse(db, "ZZTAC3-A")
    b = _mk_warehouse(db, "ZZTAC3-B")
    pid = _mk_product(db, "ZZTAC3-P")
    _mk_stock(db, pid, a, 1000)     # surplus, uncommitted
    _mk_stock(db, pid, b, 0)
    _mk_demand(db, pid, a, 0.0)
    _mk_demand(db, pid, b, 0.0)
    _mk_committed(db, pid, b, qty=50)   # the product's ONLY committed demand
    _link(db, pid, _mk_supplier(db, "ZZTAC3 Supplier"), moq=None, mult=None)
    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
        "created_at) VALUES (:id, :p, NULL, 200, 'manual', now())"
    ), {"id": str(uuid.uuid4()), "p": pid})
    db.flush()

    created = svc.create_run(db, ["ZZTAC3-A", "ZZTAC3-B"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs(db, created["run_id"], pid)
    types = {r["rec_type"] for r in recs}
    assert "buy" not in types, (
        f"A's 1,000 on hand must keep this covered, not a fabricated shortage: {types}"
    )
    covered = next(r for r in recs if r["rec_type"] == "covered")
    assert float(covered["inputs"]["covered_committed"]) == 50.0


def test_an_uncommitted_locations_surplus_shrinks_the_products_buy_qty(scm_app):
    """B1 regression, buy qty: same shape as above but a real shortage remains even with
    A's surplus counted, so a buy still fires - sized against the product's TRUE
    aggregate net (which includes A's 30 on hand), not against B's shortage alone.

    Row-grain admission (rejected) excluded A, sizing the buy at 200 - (0 - 100) = 300;
    product-grain admission counts A's 30, sizing it at 200 - (30 - 100) = 270 - one of
    the 37 buys B1 names as inflated by the row-grain mistake.
    """
    _, db, _, _ = scm_app
    _use_level_basis(db)
    a = _mk_warehouse(db, "ZZTAC4-A")
    b = _mk_warehouse(db, "ZZTAC4-B")
    pid = _mk_product(db, "ZZTAC4-P")
    _mk_stock(db, pid, a, 30)        # some stock, uncommitted
    _mk_stock(db, pid, b, 0)
    _mk_demand(db, pid, a, 0.0)
    _mk_demand(db, pid, b, 0.0)
    _mk_committed(db, pid, b, qty=100)
    _link(db, pid, _mk_supplier(db, "ZZTAC4 Supplier"), moq=None, mult=None)
    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
        "created_at) VALUES (:id, :p, NULL, 200, 'manual', now())"
    ), {"id": str(uuid.uuid4()), "p": pid})
    db.flush()

    created = svc.create_run(db, ["ZZTAC4-A", "ZZTAC4-B"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs(db, created["run_id"], pid)
    buys = [r for r in recs if r["rec_type"] == "buy"]
    assert buys, "100 committed against 30 on hand across the product is still a real shortage"
    assert float(buys[0]["rounded_qty"]) == 270.0, (
        f"expected A's 30 on hand to shrink the buy to 270, got {buys[0]['rounded_qty']}"
    )


# --------------------------------------------------------------------------- AC-2.4

def _seed_cell(db, product_id: str, warehouse_id: str, abc: str, xyz: str) -> None:
    """Per-LOCATION classification, so a policy scoped to the resulting abc/xyz cell
    resolves per bin - `scm.reorder_policy` carries no warehouse scope of its own
    (sku > abc_xyz_cell > product_class > global), so this is the only lever that makes
    two bins of one product resolve two different bases."""
    db.execute(text(
        "INSERT INTO scm.item_classification "
        "(id, product_id, warehouse_id, abc_class, xyz_class, source_system, source_ref, "
        " created_at) VALUES (:id, :p, :w, :a, :x, 'test', 'test', now())"
    ), {"id": str(uuid.uuid4()), "p": product_id, "w": warehouse_id, "a": abc, "x": xyz})


def test_needs_level_names_only_the_committed_pool_member(scm_app):
    """AC-2.4 goldens: a pool with two members, neither carrying a level - only the
    member with committed demand of its own gets a `needs_level` row (location-grain
    EMISSION gate, `_emit_pool`'s `unset` loop). The uncommitted root stays in the
    pool's net (it is why the pool exists at all) but does not get its own "you have no
    level" row - it has nothing to plan for on its own account.

    Both bins are classified into the SAME abc/xyz cell (so both resolve `reorder_level`
    identically) while the PRODUCT-wide resolution (no warehouse) finds no classification
    at all and stays on the untouched global default (`reorder_point`, `pool_netting`
    turned on) - the same divergence a real abc/xyz-scoped policy override produces, and
    the only way to reach `_emit_pool`'s `unset` loop rather than `_emit_product`'s.
    """
    _, db, _, _ = scm_app
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true "
                    "WHERE scope_type = 'global'"))
    root = _mk_warehouse(db, "ZZTAC5-ROOT")
    bin_ = _mk_warehouse(db, "ZZTAC5-BIN")
    db.execute(text("UPDATE warehouses SET pool_warehouse_id = :r WHERE id = :b"),
              {"r": root, "b": bin_})
    pid = _mk_product(db, "ZZTAC5-P")
    _no_master_level(db, pid)   # products.reorder_level has a legacy default of 10
    _mk_stock(db, pid, root, 50)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 2.0)
    _mk_committed(db, pid, bin_, qty=5)
    _link(db, pid, _mk_supplier(db, "ZZTAC5 Supplier"), moq=None, mult=None)
    _seed_cell(db, pid, root, "A", "X")
    _seed_cell(db, pid, bin_, "A", "X")
    db.execute(text(
        "INSERT INTO scm.reorder_policy (id, scope_type, scope_ref, policy_type, "
        " is_active, priority, created_at) "
        "VALUES (:id, 'abc_xyz_cell', 'A-X', 'reorder_level', true, 10, now())"
    ), {"id": str(uuid.uuid4())})
    db.flush()

    created = svc.create_run(db, ["ZZTAC5-ROOT", "ZZTAC5-BIN"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs(db, created["run_id"], pid)
    needs_level = [r for r in recs if r["rec_type"] == "needs_level"]
    assert len(needs_level) == 1, (
        f"only the committed member should be named, got {len(needs_level)}: {recs}"
    )
    assert needs_level[0]["warehouse_id"] == bin_


# --------------------------------------------------------------------------- AC-2.1 / _emit_cell

def test_a_second_uncommitted_location_emits_nothing_but_stays_in_the_run(scm_app):
    """`_emit_cell`'s location-grain gate on the DEFAULT (`reorder_point`, non-pooled,
    non-product-wide) basis - the ordinary case, no classification override needed. A
    second location of a committed product, carrying none of the commitment itself:

    (a) emits NO row of its own - it does not answer for demand that is not its own.
    (b) still counts IN SIZING: product-grain admission (2 Sep) keeps it in
        `_planning_rows` with its real on-hand, rather than dropping it from the run's
        own math the way row-grain admission (rejected) did. This is what makes a
        pooled or product-wide basis for the SAME product able to net against it, had
        the buyer configured either - the location's stock was never invisible, only
        its OWN recommendation row is withheld.
    """
    _, db, _, _ = scm_app
    committed_wh = _mk_warehouse(db, "ZZTAC6-COMMITTED")
    quiet_wh = _mk_warehouse(db, "ZZTAC6-QUIET")
    pid = _mk_product(db, "ZZTAC6-P")
    _mk_stock(db, pid, committed_wh, 5)     # low net -> triggers a buy
    _mk_stock(db, pid, quiet_wh, 40)        # real stock, zero committed
    _mk_demand(db, pid, committed_wh, 10.0)
    _mk_demand(db, pid, quiet_wh, 0.0)
    _mk_committed(db, pid, committed_wh, qty=3)
    _link(db, pid, _mk_supplier(db, "ZZTAC6 Supplier"))
    db.flush()

    created = svc.create_run(db, ["ZZTAC6-COMMITTED", "ZZTAC6-QUIET"], "warehouse",
                             enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs(db, created["run_id"], pid)
    assert not [r for r in recs if r["warehouse_id"] == quiet_wh], (
        "(a) the uncommitted location must emit no row of its own"
    )
    assert [r for r in recs
            if r["warehouse_id"] == committed_wh and r["rec_type"] == "buy"], (
        "the committed location's own buy must be unaffected"
    )

    # (b) still visible to the run's own math, not dropped from it.
    rows = svc._planning_rows(db, [committed_wh, quiet_wh])
    quiet_row = next(r for r in rows if str(r["warehouse_id"]) == quiet_wh)
    assert float(quiet_row["quantity_on_hand"]) == 40.0


# =========================================================================== #
# S1 (PLAN-low-stock-report.md, low-stock-report-acceptance-criteria.md
# AC-10..AC-16, issue #889): admission grows a SECOND leg - the dead guard
#
# Measured on the 0907 prod copy (the plan's table): the committed-demand leg
# admits 950 of 14,789 plannable products, while 7,778 sit below their level and
# only 582 of those reached the last run - 7,196 products a low stock report
# bounded by a run cannot see, CB100-BL-DIY (87 on hand, level 100, no open SO)
# among them. Admitting every non-discontinued product instead costs ~60 s a run
# and ~7,000 buy rows for SKUs nobody sells, so the owner's ruling of 14 Sep is:
#
#     admitted = committed demand > 0   OR   (below level AND not dead)
#
# "Below level" reads the SAME level the engine will plan against (a person's
# product-wide `scm.reorder_level` row, else `products.reorder_level`, 0 is not a
# level) against the SAME site-pool on-hand figure the Low sheet filters on.
# "Dead" reuses the dashboard's rule: last outbound movement in `scm.consumption_v`
# older than the GLOBAL `scm.reorder_policy.dead_stock_days` (else 180), and a
# product with no movement at all is dead (AC-15: no second definition of dead).
#
# WRITTEN BEFORE THE IMPLEMENTATION EXISTS. Every test below seeds a LIVE,
# below-level CONTROL product beside its subject, and asserts the control earns a
# row. That control is what makes a "stays out" test fail today for the right
# reason - the second leg is missing, so nothing is admitted at all - instead of
# passing vacuously because the run is empty. The two exceptions are called out
# in their own docstrings.
#
# The run is put on the LEVEL basis (`_use_level_basis`), which is the basis the
# new leg's own arithmetic is stated in and the one that makes `inputs.policy_type`
# readable as `reorder_level`.
# =========================================================================== #

def _dead_days(db, days) -> None:
    """Set the GLOBAL dead-stock window - the only scope the admission leg reads.

    `dashboard_service._dead_days_for` also honours sku / product_class scoped rows;
    the admission leg deliberately does not (plan S1: there is not one such row on the
    prod copy, and the trigger for adding the lookup is the first one). `days=None`
    leaves the window UNSET, which is how `reorder_policy.resolve_global_dead_stock_days`
    reports "no policy row said anything" - the case that must fall back to 180.
    """
    svc.eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET dead_stock_days = :d "
                    "WHERE scope_type = 'global'"), {"d": days})
    db.flush()


def _master_level(db, pid: str, level) -> None:
    """The AutoCount master level (`products.reorder_level`) - set explicitly because the
    column carries a legacy server default of 10, so a product built without one arrives
    holding a level nobody set."""
    db.execute(text("UPDATE products SET reorder_level = :l WHERE id = :p"),
               {"l": level, "p": pid})
    db.flush()


def _buyer_level(db, pid: str, level: float, source: str = "manual") -> None:
    """The buyer's own PRODUCT-WIDE override (`scm.reorder_level`, `warehouse_id IS
    NULL`). Only a person's row is an override (`reorder_level_service.VALID_SOURCES`),
    which is exactly the rule `_product_level` applies when it plans - so the admission
    leg has to apply it too, or the run admits a product on a level it will not plan
    against."""
    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
        "created_at) VALUES (:id, :p, NULL, :l, :s, now())"
    ), {"id": str(uuid.uuid4()), "p": pid, "l": level, "s": source})
    db.flush()


def _sellable(db, wid: str, code_stem: str, *, on_hand: float, moved_days_ago,
              master_level=100) -> str:
    """One product at one site-pool location: stock, an optional outbound movement, a
    linked supplier, a master level - and NO committed demand anywhere, which is the
    whole point (the first admission leg must not be what lets it in).

    A supplier is linked on every product, the ones expected to stay OUT included: a
    product with no supplier emits an `exception` row rather than a `buy`, so leaving it
    off would make "no row" ambiguous between "not admitted" and "admitted, unsourceable".
    """
    pid = _mk_product(db, code_stem)
    _mk_stock(db, pid, wid, on_hand)
    if moved_days_ago is not None:
        _mk_movement(db, pid, wid, 3, days_ago=moved_days_ago)
    _link(db, pid, _mk_supplier(db, f"{code_stem} Supplier"))
    _master_level(db, pid, master_level)
    return pid


class TestDeadGuardAdmission:
    """AC-10..AC-15: the second admission leg, and the four things it must NOT admit."""

    # ----------------------------------------------------------------- AC-10

    def test_below_level_live_product_with_no_committed_demand_enters_as_a_level_buy(
            self, scm_app):
        """AC-10: 40 on hand against a level of 100, an outbound movement 5 days ago, and
        not one open sales order line anywhere - CB100-BL-DIY's exact shape. The run must
        plan it, and plan it the SAME way a committed-demand product on the level basis is
        planned: one `buy` row, `policy_type = reorder_level`, sized `L - net` (100 - 40 =
        60) then floored at the supplier's MOQ of 100 and ceiled to its multiple of 50.

        RED today for the right reason: nothing admits this product, so the run plans
        zero products and writes zero rows.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        _dead_days(db, 180)
        wid = _mk_warehouse(db, "ZZTDG1-WH", segment="dealer")
        pid = _sellable(db, wid, "ZZTDG1-P", on_hand=40, moved_days_ago=5)
        db.flush()

        created = svc.create_run(db, ["ZZTDG1-WH"], "warehouse", enqueue=False)
        svc.run_reorder(created["run_id"], db=db)

        recs = _recs(db, created["run_id"], pid)
        assert len(recs) == 1, f"one decision for the product, got {recs}"
        assert recs[0]["rec_type"] == "buy"
        assert recs[0]["inputs"]["policy_type"] == "reorder_level", (
            "admitted on the level leg, planned on the level basis - one reading of "
            "the level, not two"
        )
        assert float(recs[0]["recommended_qty"]) == 60.0, "L - net = 100 - 40"
        assert float(recs[0]["rounded_qty"]) == 100.0, (
            "60 floored at MOQ 100, already on the multiple of 50"
        )

    def test_buyer_level_outranks_master_level_in_admission(self, scm_app):
        """AC-10: the leg resolves the level the way `_product_level` does - a person's
        product-wide `scm.reorder_level` row FIRST, the AutoCount master second - so
        admission and planning can never disagree about whether the product is below
        level.

        Both directions, in one run:
          * OVERRIDE: master 10 (40 on hand is comfortably above it) but the buyer typed
            100 -> below level -> admitted.
          * REVERSE: master 100 (40 would be below it) but the buyer typed 10 -> the
            buyer's number is the one that counts -> NOT admitted.

        RED today on the OVERRIDE half.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        _dead_days(db, 180)
        wid = _mk_warehouse(db, "ZZTDG2-WH", segment="dealer")

        override = _sellable(db, wid, "ZZTDG2-OVERRIDE", on_hand=40, moved_days_ago=5,
                             master_level=10)
        _buyer_level(db, override, 100)
        reverse = _sellable(db, wid, "ZZTDG2-REVERSE", on_hand=40, moved_days_ago=5,
                            master_level=100)
        _buyer_level(db, reverse, 10)
        db.flush()

        created = svc.create_run(db, ["ZZTDG2-WH"], "warehouse", enqueue=False)
        svc.run_reorder(created["run_id"], db=db)

        assert [r["rec_type"] for r in _recs(db, created["run_id"], override)] == ["buy"], (
            "the buyer's level of 100 is the level, so 40 on hand is below it"
        )
        assert _recs(db, created["run_id"], reverse) == [], (
            "the buyer's level of 10 outranks the master's 100; 40 on hand is above it"
        )

    # ----------------------------------------------------------------- AC-11

    def test_below_level_dead_product_stays_out(self, scm_app):
        """AC-11: below level is not enough. A product whose last outbound movement is
        older than `dead_stock_days` is a SKU nobody sells, and buying more of it is the
        ~7,000 dead buy rows the owner rejected. The LIVE control beside it - identical
        but for the movement date - is what proves the run was planning at all.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        _dead_days(db, 180)
        wid = _mk_warehouse(db, "ZZTDG3-WH", segment="dealer")
        live = _sellable(db, wid, "ZZTDG3-LIVE", on_hand=40, moved_days_ago=5)
        dead = _sellable(db, wid, "ZZTDG3-DEAD", on_hand=40, moved_days_ago=200)
        db.flush()

        created = svc.create_run(db, ["ZZTDG3-WH"], "warehouse", enqueue=False)
        svc.run_reorder(created["run_id"], db=db)

        assert [r["rec_type"] for r in _recs(db, created["run_id"], live)] == ["buy"]
        assert _recs(db, created["run_id"], dead) == [], (
            "200 days without an outbound movement is dead at the 180-day window"
        )

    def test_below_level_product_that_never_moved_stays_out(self, scm_app):
        """AC-11/AC-15: a product with NO `scm.consumption_v` row at all is dead, not
        merely unmeasured - the same reading `_compute_status` takes (`last_movement is
        None -> dead`). Below level and never sold is the clearest case of stock nobody
        should be topping up.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        _dead_days(db, 180)
        wid = _mk_warehouse(db, "ZZTDG4-WH", segment="dealer")
        live = _sellable(db, wid, "ZZTDG4-LIVE", on_hand=40, moved_days_ago=5)
        never = _sellable(db, wid, "ZZTDG4-NEVER", on_hand=40, moved_days_ago=None)
        db.flush()

        created = svc.create_run(db, ["ZZTDG4-WH"], "warehouse", enqueue=False)
        svc.run_reorder(created["run_id"], db=db)

        assert [r["rec_type"] for r in _recs(db, created["run_id"], live)] == ["buy"]
        assert _recs(db, created["run_id"], never) == [], (
            "no movement row at all is dead, not 'moved an unknown time ago'"
        )

    # ----------------------------------------------------------------- AC-12

    def test_above_level_product_with_no_committed_demand_stays_out(self, scm_app):
        """AC-12: the committed-demand leg is unchanged. A comfortably covered product
        (500 on hand against a level of 100) that moved yesterday still earns nothing,
        because the new leg admits BELOW-level products only - it is not "every product
        that still moves".

        The sibling of the module-level test at the top of this file
        (`test_stock_movement_and_a_level_alone_earn_no_row_with_no_committed_demand`),
        on the LEVEL basis and beside a live control, so the assertion cannot pass
        merely because the run planned nothing.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        _dead_days(db, 180)
        wid = _mk_warehouse(db, "ZZTDG5-WH", segment="dealer")
        live = _sellable(db, wid, "ZZTDG5-LIVE", on_hand=40, moved_days_ago=5)
        covered = _sellable(db, wid, "ZZTDG5-COVERED", on_hand=500, moved_days_ago=1)
        db.flush()

        created = svc.create_run(db, ["ZZTDG5-WH"], "warehouse", enqueue=False)
        svc.run_reorder(created["run_id"], db=db)

        assert [r["rec_type"] for r in _recs(db, created["run_id"], live)] == ["buy"]
        assert _recs(db, created["run_id"], covered) == [], (
            "500 on hand against a level of 100 is not below level, so nothing admits it"
        )

    # ----------------------------------------------------------------- AC-13

    def test_no_level_no_demand_stays_out(self, scm_app):
        """AC-13: a `needs_level` row still needs a demand signal, as today. A product
        with no level ANYWHERE - no buyer row, and `products.reorder_level` NULL - cannot
        be below level, so the new leg has nothing to test it against and must not admit
        it. Admitting it would put a "you have no level" row in front of the buyer for
        every unloved SKU in the catalogue.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        _dead_days(db, 180)
        wid = _mk_warehouse(db, "ZZTDG6-WH", segment="dealer")
        live = _sellable(db, wid, "ZZTDG6-LIVE", on_hand=40, moved_days_ago=5)
        unset = _sellable(db, wid, "ZZTDG6-UNSET", on_hand=0, moved_days_ago=1)
        _no_master_level(db, unset)
        db.flush()

        created = svc.create_run(db, ["ZZTDG6-WH"], "warehouse", enqueue=False)
        svc.run_reorder(created["run_id"], db=db)

        assert [r["rec_type"] for r in _recs(db, created["run_id"], live)] == ["buy"]
        assert _recs(db, created["run_id"], unset) == [], (
            "no resolvable level means the level leg cannot admit it - not even as "
            "needs_level"
        )

    # ----------------------------------------------------------------- AC-14

    def test_named_dead_product_still_enters(self, scm_app):
        """AC-14 (G10, unchanged): a buyer who TYPES a SKU into Start Plan gets it
        planned - demand, level and movement notwithstanding. This one is expected to be
        GREEN before the slice as well as after: it is the pin that stops the new leg
        from being written as a filter that also narrows the named-product path.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        _dead_days(db, 180)
        wid = _mk_warehouse(db, "ZZTDG7-WH", segment="dealer")
        pid = _sellable(db, wid, "ZZTDG7-DEAD", on_hand=40, moved_days_ago=400)
        db.flush()

        created = svc.create_run(db, ["ZZTDG7-WH"], "warehouse",
                                 product_codes=["ZZTDG7-DEAD"], enqueue=False)
        svc.run_reorder(created["run_id"], db=db)

        assert _recs(db, created["run_id"], pid), (
            "a named product enters regardless of movement, level or demand (G10)"
        )

    # ----------------------------------------------------------------- AC-15

    def test_admission_dead_days_follow_the_global_policy(self, scm_app):
        """AC-15: the window is whatever the admin set on the global
        `scm.reorder_policy` row - no second definition of dead, and no constant baked
        into the admission SQL. The SAME product, moved 45 days ago, is out at a 30-day
        window and in at a 60-day one; only the policy row changes between the two runs.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        wid = _mk_warehouse(db, "ZZTDG8-WH", segment="dealer")
        live = _sellable(db, wid, "ZZTDG8-LIVE", on_hand=40, moved_days_ago=5)
        subject = _sellable(db, wid, "ZZTDG8-45D", on_hand=40, moved_days_ago=45)
        db.flush()

        _dead_days(db, 30)
        tight = svc.create_run(db, ["ZZTDG8-WH"], "warehouse", enqueue=False)
        svc.run_reorder(tight["run_id"], db=db)
        assert [r["rec_type"] for r in _recs(db, tight["run_id"], live)] == ["buy"]
        assert _recs(db, tight["run_id"], subject) == [], (
            "45 days without a movement is dead at a 30-day window"
        )

        _dead_days(db, 60)
        wide = svc.create_run(db, ["ZZTDG8-WH"], "warehouse", enqueue=False)
        svc.run_reorder(wide["run_id"], db=db)
        assert [r["rec_type"] for r in _recs(db, wide["run_id"], subject)] == ["buy"], (
            "the same product is alive at a 60-day window - the policy row decides"
        )

    def test_admission_dead_days_default_180_without_a_global_row(self, scm_app):
        """AC-15: with nothing set, the window is `reorder_policy.DEFAULT_DEAD_STOCK_DAYS`
        (180) - the same fallback `dashboard_service._dead_days_for` lands on.

        The global row is left in place with `dead_stock_days` NULL rather than deleted:
        NULL is precisely what `resolve_global_dead_stock_days` reports as "unset" (it
        returns None either way), and the row itself still carries the level basis the
        rest of the seed depends on. One run, two products either side of the default.
        """
        _, db, _, _ = scm_app
        _use_level_basis(db)
        _dead_days(db, None)
        wid = _mk_warehouse(db, "ZZTDG9-WH", segment="dealer")
        inside = _sellable(db, wid, "ZZTDG9-170D", on_hand=40, moved_days_ago=170)
        outside = _sellable(db, wid, "ZZTDG9-190D", on_hand=40, moved_days_ago=190)
        db.flush()

        created = svc.create_run(db, ["ZZTDG9-WH"], "warehouse", enqueue=False)
        svc.run_reorder(created["run_id"], db=db)

        assert [r["rec_type"] for r in _recs(db, created["run_id"], inside)] == ["buy"], (
            "170 days is inside the 180-day default"
        )
        assert _recs(db, created["run_id"], outside) == [], (
            "190 days is outside it"
        )
