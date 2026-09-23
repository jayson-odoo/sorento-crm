"""RED tests, written before the coder's Phase 2, for Lane E of
`PLAN-order-sheet-oi-reports-22sep.md` (AC-E1..E7 in
`order-sheet-oi-reports-22sep-acceptance-criteria.md`).

Lane E: `_planning_rows`' admission WHERE (`reorder_run_service.py` ~873) hard-excludes
`p.is_discontinued = false` for every run kind, so a discontinued product with confirmed
project OI demand inside a run's own scope never enters the plan at all - the owner's
measured case (SRTWC193, OI-2609-0228, 8 units due 31/10/2026, `cv_all`'s own
`project_confirmed_committed = 8` for it, plan of 23/09 10:25 shows no line). The fix:
`p.is_discontinued = false` becomes `(p.is_discontinued = false OR EXISTS (SELECT 1 FROM
cv_all c WHERE c.product_id = p.id AND c.project_confirmed_committed > 0))` -
`is_active`/`exclude_from_planning` stay hard, and leg 2 (below level, moved in 180 d)
never admits a discontinued product on its own (it is not evidence of project demand). A
product admitted this way sizes PROJECT-ONLY on every run kind that can admit it at all
(the `_project_only_cell`/`project_only` branches #1122 built) - no retail reorder-point or
level top-up, even when the product sits below its level. A Dealer run has no project leg
at all (`demand_class='retail'` keeps only the book leg of `cv_all`'s UNION -
`demand.horizon_committed_select_sql`'s own docstring), so `project_confirmed_committed` is
always 0 there regardless of any OI row - a discontinued product can never be admitted on a
Dealer run.

Every test below seeds a SINGLE dealer location BELOW its reorder level (the leg-2 shape,
so a leg-2 admission bug would be visible) with a recent movement (leg 2's own "not dead"
half) - `_seed_single_below_level`/`_discontinued_below_level`, copied from
`tests/scm/test_reorder_plan_project_only.py`, then flips `products.is_discontinued` to
true by hand (`_mk_product` hard-codes `is_discontinued = false`, and no seeding helper
here takes it as a parameter). The product is DISCONTINUED, ACTIVE, and NOT excluded from
planning unless a specific test says otherwise (AC-E6).

Harness copied from `tests/scm/test_reorder_plan_project_only.py` (`_seed_single_below_
level`, `_recs_for`/`_buy_rows`, `MARKER`/`_code`/`_u` conventions) and
`tests/test_reorder_plan_demand_scope.py` (`_project_so_with_lines`, the confirmed-leg
ORDER-row builder: project + PSO + inquiry + one ACTIVE decision + row). Postgres only, via
`tests/scm/conftest.py::scm_app` - a live TestClient over a rolled-back SAVEPOINT. CI's
database starts empty: every test seeds its own full chain, nothing borrowed off the shared
local database.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.models.project_so import ACK_ACKNOWLEDGED, ACK_AWAITING
from app.services.scm import demand
from app.services.scm import reorder_run_service as svc
from app.services.scm import summary_order_service as sos
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401
from tests.scm.test_reorder_plan_project_only import _seed_single_below_level
from tests.test_reorder_plan_demand_scope import _project_so_with_lines

pytestmark = requires_pg

MARKER = "ZZTADC"


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


def _discontinued_below_level(db, *, level=150, demand_add=0.0, lead=30, moq=1, mult=1):
    """A single dealer location below its reorder level (leg 2's own shape), flipped
    discontinued after `_mk_product` seeds it (that helper hard-codes `is_discontinued =
    false`, and neither it nor `_seed_single_below_level` above it takes the flag)."""
    u = _seed_single_below_level(db, level=level, lead=lead, moq=moq, mult=mult,
                                  demand_add=demand_add)
    db.execute(text("UPDATE products SET is_discontinued = true WHERE id = :id"),
               {"id": u["pid"]})
    db.flush()
    return u


def _oi_row(db, *, pid, wid, qty=8, delivery=date(2026, 10, 1), ack_state=ACK_ACKNOWLEDGED):
    return _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": qty,
         "delivery_date": delivery, "ack_state": ack_state},
    ])


# =============================================================================
# AC-E1 - Project run, picked SO, discontinued product with a confirmed OI row inside
# the run's scope -> a recommendation whose project need equals the owed qty.
# =============================================================================

def test_ac_e1_project_run_admits_discontinued_product_with_confirmed_oi_row_in_scope(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    so = _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, (
        "expected a discontinued product with confirmed OI demand inside scope to enter "
        f"the plan, got {_recs_for(db, created['run_id'], u['pid'])}"
    )
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 8.0, f"expected the owed qty alone (8), got {total}"


# =============================================================================
# AC-E1b - same on an All run, both with the SO picked and with nothing picked.
# =============================================================================

def test_ac_e1b_all_run_with_picked_so_admits_discontinued_product(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    so = _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, (
        f"expected an All run to admit the discontinued product too, "
        f"got {_recs_for(db, created['run_id'], u['pid'])}"
    )
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 8.0, f"expected the owed qty alone (8), got {total}"


def test_ac_e1b_all_run_with_nothing_picked_admits_discontinued_product(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, (
        "expected an All run with nothing picked to still admit the discontinued "
        f"product (project rows are unscoped when so_numbers is empty/None), got "
        f"{_recs_for(db, created['run_id'], u['pid'])}"
    )
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 8.0, f"expected the owed qty alone (8), got {total}"


# =============================================================================
# AC-E2 - three negatives: outside the window, on an un-picked SO, awaiting ack.
# =============================================================================

def test_ac_e2_row_outside_the_window_admits_nothing(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    so = _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8, delivery=date(2027, 3, 1))

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"a row delivering after the window must not admit the product, got {recs}"


def test_ac_e2_row_on_an_unpicked_so_admits_nothing(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)
    other_so_number = _code("OTHER-SO")

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[other_so_number],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"a row on an un-picked SO must not admit the product, got {recs}"


def test_ac_e2_row_awaiting_ack_admits_nothing(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    so = _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8, ack_state=ACK_AWAITING)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"a row still awaiting acknowledgement must not admit the product, got {recs}"


# =============================================================================
# AC-E3 - below level, no OI row anywhere -> leg 2 never admits a discontinued product,
# on an All run or a Dealer run.
# =============================================================================

def test_ac_e3_below_level_no_oi_row_admits_nothing_on_all_run(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)

    created = svc.create_run(db, [], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"leg 2 must never admit a discontinued product, got {recs}"


def test_ac_e3_below_level_no_oi_row_admits_nothing_on_dealer_run(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)

    created = svc.create_run(db, [], enqueue=False, demand_class="retail")
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"leg 2 must never admit a discontinued product, got {recs}"


# =============================================================================
# AC-E4 - an All run: the admitted product's Suggested qty is the project need ONLY,
# even below its level - no retail top-up.
# =============================================================================

def test_ac_e4_all_run_suggested_equals_oi_owed_qty_no_retail_topup(scm_app):
    _, db, _, _ = scm_app
    # demand_add/lead sized so the RETAIL path would answer far more than 8 (the
    # project_only twin's own math: rop/oup on demand_add=5.0, lead=30 answers well over
    # 300) - a coder who drops the project-only sizing swap and lets this fall through to
    # the plain reorder-point trigger would size the level top-up instead of the row.
    u = _discontinued_below_level(db, demand_add=5.0, lead=30)
    so = _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, f"expected a buy, got {_recs_for(db, created['run_id'], u['pid'])}"
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 8.0, (
        f"expected the OI owed qty alone (8), no retail top-up despite sitting below "
        f"level, got {total}"
    )


# =============================================================================
# AC-E5 - a Dealer run never admits a discontinued product, even with the OI row present.
# =============================================================================

def test_ac_e5_dealer_run_never_admits_discontinued_product_even_with_oi_row(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)

    created = svc.create_run(db, [], enqueue=False, demand_class="retail")
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], (
        f"a Dealer run has no project leg at all - it must never admit a discontinued "
        f"product, got {recs}"
    )


# =============================================================================
# AC-E6 - is_active = false or exclude_from_planning = true keep a product out even with
# a confirmed OI row.
# =============================================================================

def test_ac_e6_inactive_product_stays_out_despite_confirmed_oi_row(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    db.execute(text("UPDATE products SET is_active = false WHERE id = :id"), {"id": u["pid"]})
    db.flush()
    so = _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"is_active=false must stay hard, got {recs}"


def test_ac_e6_excluded_from_planning_product_stays_out_despite_confirmed_oi_row(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    db.execute(text("UPDATE products SET exclude_from_planning = true WHERE id = :id"),
               {"id": u["pid"]})
    db.flush()
    so = _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"exclude_from_planning=true must stay hard, got {recs}"


# =============================================================================
# AC-E7 - the sheet (write_rows -> project_customers) and the OI worksheet
# (demand.run_scope_oi_rows) both carry the admitted product's line.
# =============================================================================

def test_ac_e7_write_rows_freezes_project_customers_and_worksheet_scope_returns_the_row(scm_app):
    _, db, _, _ = scm_app
    u = _discontinued_below_level(db)
    so = _oi_row(db, pid=u["pid"], wid=u["wid"], qty=8)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert sos.write_rows(db, created["run_id"]) >= 1

    product_code = db.execute(
        text("SELECT product_code FROM products WHERE id = :id"), {"id": u["pid"]},
    ).scalar()
    report = sos.report(db, run_id=created["run_id"])
    row = next((r for r in report["rows"] if r["product_code"] == product_code), None)
    assert row is not None, (
        f"expected the discontinued product's frozen row on the sheet, got "
        f"{[r['product_code'] for r in report['rows']]}"
    )
    customers = row["project_customers"]
    assert sum(c["qty"] for c in customers) == 8.0, customers

    scope_rows = demand.run_scope_oi_rows(
        db, [u["pid"]], so_numbers=[so["so_number"]],
        horizon_start=date(2026, 1, 1), horizon=date(2026, 12, 31),
    )
    assert any(float(r["qty"]) == 8.0 for r in scope_rows), (
        f"expected the OI worksheet's own row scope to carry the discontinued product's "
        f"line too, got {scope_rows}"
    )
