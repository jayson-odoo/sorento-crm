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
