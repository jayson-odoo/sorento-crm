"""RED tests, written before the coder's Phase 2, for
`PLAN-reorder-plan-project-only.md` / its UAC (AC-PO-1..9; AC-PO-10 is the existing-suite
green check, run separately by the harness; AC-PO-11 is browser, skipped here).

None of S1/S2 exists yet on origin/main: `_planning_rows`'s `product_admit_join` still
UNIONs the below-reorder-level ("leg 2") admission into a `demand_class="project"` run
exactly as it does for every other run, and `_emit_pool` (and its network/product-grain
twins) still size a Project run's pool as RETAIL-policy-recommended PLUS the firm project
need on top, rather than the project need ALONE. Every test below seeds a product that is
BELOW ITS REORDER LEVEL (the leg-2 gate) and POOLED across two dealer locations (so the
pool-level buy in `_emit_pool` is computed unconditionally of any one member's own
committed demand - see the long G1 comment above `_emit_cell` in
`reorder_run_service.py`: a non-pooled, zero-committed cell emits nothing at all today,
so a single-location fixture would not exercise the leg-2 admission bug this lane fixes).

Harness copied from `tests/scm/test_m3_run.py` (`_client`, `_mk_*`) and
`tests/test_reorder_plan_demand_scope.py` (`_project_so_with_lines`, the confirmed-leg
ORDER-row builder already used to seed a real Order Inquiry chain: project + PSO +
inquiry + decision + row, one ACTIVE decision per PSO). Postgres only, via
`tests/scm/conftest.py::scm_app` - a live TestClient over a rolled-back SAVEPOINT. CI's
database starts empty: every test seeds its own full chain, nothing borrowed off the
shared local database.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import ACK_ACKNOWLEDGED, OrderInquiryLink
from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg, scm_app  # noqa: F401
from tests.scm.test_m3_run import (
    _link,
    _mk_demand,
    _mk_movement,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)
from tests.test_reorder_plan_demand_scope import _project_so_with_lines

pytestmark = requires_pg

MARKER = "ZZTPO"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _recs_for(db, run_id: str, pid: str) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT rec_type, warehouse_id::text AS warehouse_id, rounded_qty, "
            "recommended_qty, triggered_reason AS reason_label, inputs "
            "FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
        ),
        {"r": run_id, "p": pid},
    ).mappings().all()
    return [dict(r) for r in rows]


def _buy_rows(db, run_id: str, pid: str) -> list[dict]:
    return [r for r in _recs_for(db, run_id, pid) if r["rec_type"] == "buy"]


def _seed_pool_below_level(db, *, level=150, demand_add=5.0, lead=30, moq=1, mult=1):
    """Two pooled dealer locations, product-wide level `level`, on hand 0 at both, a
    recent movement (admits leg 2's "not dead" half), and a nonzero forecast demand rate
    at the root so the RETAIL policy genuinely fires - the fixture the plan's own measured
    facts describe (MPW800 level 150, on hand 0), widened to a pool so a zero-committed
    member's buy is not silently withheld by the unrelated G1 location-grain gate
    (`_emit_cell`'s `committed_here <= 0` withhold, which does not apply to a pool's own
    buy - see module docstring).
    """
    root_wid = _mk_warehouse(db, _code("ROOT"))
    child_wid = _mk_warehouse(db, _code("CHILD"), pool_warehouse_id=root_wid)
    pid = _mk_product(db, _code("P"))
    _mk_stock(db, pid, root_wid, 0)
    _mk_stock(db, pid, child_wid, 0)
    _mk_demand(db, pid, root_wid, demand_add)
    _mk_movement(db, pid, root_wid, 1, days_ago=7)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier"), lead=lead, moq=moq, mult=mult)

    eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true WHERE scope_type = 'global'"))
    db.execute(
        text(
            "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
            "company_id, created_at) VALUES (:id, :p, NULL, :lvl, 'manual', :co, now())"
        ),
        {"id": _u(), "p": pid, "lvl": level, "co": SORENTO_COMPANY_ID},
    )
    db.flush()
    return {"pid": pid, "root_wid": root_wid, "child_wid": child_wid}


def _seed_single_below_level(db, *, level=150, lead=30, moq=1, mult=1):
    """One dealer location, below its product-wide reorder level, on hand 0, a recent
    movement (leg 2's own admission gate) and NO forecast demand rate - the "with an
    ORDER row" fixtures (AC-PO-3..7, AC-PO-9): a single, non-pooled location whose only
    committed demand is the ORDER row the caller adds, so the resulting recommendation
    (or its absence) is driven by that row alone rather than by a retail forecast on top
    of it.
    """
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("P"))
    _mk_stock(db, pid, wid, 0)
    _mk_movement(db, pid, wid, 1, days_ago=7)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier"), lead=lead, moq=moq, mult=mult)

    eng.ensure_reorder_policy_defaults(db)
    db.execute(
        text(
            "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
            "company_id, created_at) VALUES (:id, :p, NULL, :lvl, 'manual', :co, now())"
        ),
        {"id": _u(), "p": pid, "lvl": level, "co": SORENTO_COMPANY_ID},
    )
    db.flush()
    return {"pid": pid, "wid": wid}


# ===========================================================================
# AC-PO-1 / AC-PO-2 - leg 2 (below reorder level) must not admit a Project run
# ===========================================================================

def test_ac_po_1_project_run_does_not_admit_a_below_level_product_with_no_project_row(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)

    created = svc.create_run(db, [], enqueue=False, demand_class="project", so_numbers=[])
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"expected no recommendation at all, got {recs}"


def test_ac_po_2_dealer_run_still_admits_and_buys_the_same_product(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)

    created = svc.create_run(db, [], enqueue=False, demand_class="retail", so_numbers=[])
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, "a Dealer run must still buy for a below-level product"
    assert float(buys[0]["rounded_qty"]) > 0


# ===========================================================================
# AC-PO-3 / AC-PO-4 - the project channel is sized ALONE, no retail top-up
# ===========================================================================

def test_ac_po_3_project_run_with_order_row_and_below_level_buys_exactly_the_order_qty(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    buys = [r for r in recs if r["rec_type"] == "buy"]
    # A pooled buy is emitted ONE ROW PER LOCATION THAT ASKED (`_emit_pool`'s own split,
    # unrelated to this lane) - the ROOT holds no project need at all here, so a
    # project-only run must land the whole 20 at the CHILD alone and write no row for the
    # root, exactly as a project buy is meant to land where the order was placed, not
    # wherever a leftover retail deficit happens to point the allocator.
    assert len(recs) == 1, f"expected exactly one line (at the child alone), got {recs}"
    assert buys, f"expected the one line to be a buy, got {recs}"
    assert float(buys[0]["rounded_qty"]) == 20.0, (
        f"expected the project need alone (20), got {buys[0]['rounded_qty']}"
    )
    assert (buys[0]["reason_label"] or "").startswith("project buy"), buys[0]["reason_label"]


def test_ac_po_4_dealer_run_with_same_seed_sizes_the_retail_top_up_not_20(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)
    _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="retail", so_numbers=[],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, "a Dealer run must still buy for the below-level product"
    assert float(buys[0]["rounded_qty"]) != 20.0, (
        "a Dealer run's figure is today's retail top-up, not the project qty"
    )


# ===========================================================================
# AC-PO-5 - so_numbers scope: a project row on an order OUTSIDE the picked list
# ===========================================================================

def test_ac_po_5_project_run_scoped_to_other_orders_emits_nothing_for_this_product(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])
    other_so_number = _code("OTHER-SO")

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[other_so_number],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], (
        f"a Project run scoped away from {so['so_number']} must not see its product, got {recs}"
    )


# ===========================================================================
# AC-PO-6 - a fully-linked ORDER row (owed 0) is not committed demand
# ===========================================================================

def test_ac_po_6_project_run_emits_nothing_for_a_fully_linked_order_row(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])
    row = so["rows"][0]
    supplier = Supplier(id=_u(), company_id=SORENTO_COMPANY_ID, supplier_code=_code("SUP"),
                        supplier_name=f"{MARKER} link supplier")
    po = PurchaseOrder(id=_u(), company_id=SORENTO_COMPANY_ID, po_number=_code("PO"),
                       supplier_id=supplier.id, status="active")
    db.add_all([supplier, po])
    db.flush()
    po_line = PurchaseOrderLine(id=_u(), company_id=SORENTO_COMPANY_ID, purchase_order_id=po.id,
                                product_id=u["pid"], warehouse_id=u["child_wid"],
                                qty_ordered=row.qty, qty_received=0, line_status="open")
    db.add(po_line)
    db.flush()
    db.add(OrderInquiryLink(id=_u(), row_id=row.id, po_line_id=po_line.id, qty=row.qty,
                            document=po.po_number))
    db.flush()

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"a fully-linked row owes nothing; expected no line, got {recs}"


# ===========================================================================
# AC-PO-7 - MOQ / order multiple still round the project-alone need
# ===========================================================================

def test_ac_po_7_moq_rounds_the_project_need_alone(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db, moq=50, mult=50)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, "expected a buy for the project need"
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 50.0, (
        f"MOQ 50 must round the project need (20) up to 50 in total, got {total} "
        f"across {buys}"
    )


# ===========================================================================
# AC-PO-8 - a pooled product's sibling on-hand does not net a firm project Buy
# ===========================================================================

def test_ac_po_8_pooled_sibling_on_hand_does_not_reduce_the_project_buy(scm_app):
    _, db, _, _ = scm_app
    root_wid = _mk_warehouse(db, _code("ROOT"))
    child_wid = _mk_warehouse(db, _code("CHILD"), pool_warehouse_id=root_wid)
    pid = _mk_product(db, _code("P"))
    # Need at the CHILD (0 on hand), 100 sitting at the ROOT the pool could otherwise net
    # a firm project Buy against.
    _mk_stock(db, pid, child_wid, 0)
    _mk_stock(db, pid, root_wid, 100)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier"), moq=1, mult=1)
    eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true WHERE scope_type = 'global'"))
    db.flush()

    so = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": child_wid, "qty": 10,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], pid)
    assert buys, "expected a buy for the firm project need"
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 10.0, (
        f"the sibling's 100 on hand must not net the firm project Buy, got {total} across {buys}"
    )


# ===========================================================================
# AC-PO-9 - the run header counts equal the sum of the emitted lines
# ===========================================================================

def test_ac_po_9_header_counts_equal_the_sum_of_the_lines_emitted(scm_app):
    """Two products in the SAME run: A has an acknowledged ORDER row (qty 20, no MOQ
    rounding) - the one line the run is entitled to; B is below its reorder level with NO
    project demand anywhere - AC-PO-1's own product, the leg-2 phantom this run must admit
    NOTHING for. The header counts must equal A's one line alone - B contributing a
    needs_level/buy/covered row of its own would be exactly the "phantom count from the
    dropped leg" AC-PO-9 exists to catch.
    """
    _, db, _, _ = scm_app
    a = _seed_single_below_level(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": a["pid"], "warehouse_id": a["wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])
    b = _seed_pool_below_level(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _recs_for(db, created["run_id"], b["pid"]) == [], (
        "product B (below level, no project demand) must contribute nothing"
    )

    run = db.execute(
        text("SELECT run_log FROM scm.reorder_run WHERE id = :id"), {"id": created["run_id"]},
    ).mappings().first()
    recs = db.execute(
        text("SELECT rec_type, rounded_qty, product_id::text AS product_id "
             "FROM scm.reorder_recommendation WHERE run_id = :id"),
        {"id": created["run_id"]},
    ).mappings().all()
    buy_count = sum(1 for r in recs if r["rec_type"] == "buy")
    assert run["run_log"]["buy"] == buy_count
    assert run["run_log"]["recommendation_count"] == len(recs)
    # A's own seed drives this: exactly one buy line, product A alone, sized 20 - no
    # phantom leg-2 recommendation riding along beside it.
    assert buy_count == 1, f"expected exactly one buy line, run_log={run['run_log']!r}"
    assert recs[0]["product_id"] == a["pid"]
    assert float(recs[0]["rounded_qty"]) == 20.0
