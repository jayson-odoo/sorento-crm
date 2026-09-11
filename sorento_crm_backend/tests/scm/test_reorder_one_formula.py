"""PLAN-reorder-one-formula.md - the one formula, S4.

    level  = reorder_level, or 0 when the product has none ("no level = 0")
    need   = project + retail + level - SPO arriving
    buy    = need - on hand - PO open              (= level - net; clipped at 0)

Worked example (the owner's own measured figures, run de3a0cf7, 11 Sep 2026),
product B2155-NL-BLUE: on hand 128, SPO 0, PO 339, project 493, retail 170, no
buyer level anywhere. need = 493 + 170 + 0 - 0 = 663. buy = 663 - 128 - 339 = 196.

Harness copied from `test_reorder_per_product.py` (`_wh`/`_product`/`_set_level`/`_open_po`/
`_run`/`_recs`/`_buys`/`_sizing_row`) and `test_channel_read_model.py`'s `_confirmed_leg`
(the firm, confirmed-unplaced Project Buy leg) + `_core_line_for_run` (a plain committed
retail SO line) - the same seeding shapes the rest of the reorder suite already uses so a
real Postgres constraint (a supplier link, a category/uom pair) is never invented.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_channel_read_model import _confirmed_leg, _core_line_for_run
from tests.scm.test_m3_run import _link, _mk_demand, _mk_product, _mk_stock, _mk_supplier, _mk_warehouse
from tests.scm.test_reorder_level_run import _use_level_basis
from tests.scm.test_reorder_per_product import _open_po, _set_level

pytestmark = requires_pg

MARKER = "ZZTONE"


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:6]}".upper()


def _wh(db, stem: str) -> tuple[str, str]:
    code = _code(stem)
    return _mk_warehouse(db, code), code


def _product(db, *, master_level: float | None = None) -> tuple[str, str]:
    code = _code("P")
    pid = _mk_product(db, code)
    db.execute(text("UPDATE products SET reorder_level = :l WHERE id = :p"),
               {"l": master_level, "p": pid})
    return pid, code


def _run(db, warehouse_codes: list[str], product_code: str) -> str:
    created = svc.create_run(db, warehouse_codes, enqueue=False,
                             product_codes=[product_code])
    svc.run_reorder(created["run_id"], db=db)
    return created["run_id"]


def _recs(db, run_id: str, pid: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(
        "SELECT rec_type, warehouse_id::text AS warehouse_id, recommended_qty, "
        "       rounded_qty, triggered_reason, inputs "
        "FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
    ), {"r": run_id, "p": pid}).mappings().all()]


def _sizing_row(rows: list[dict]) -> dict:
    planning = [r for r in rows if r["rec_type"] != "disposition"]
    assert len(planning) == 1, (
        f"one product is one sizing decision, got {[r['rec_type'] for r in planning]}"
    )
    return planning[0]


# --- AC-1: a no-level product-grain row plans level 0, never a project-buy bypass ------

def test_no_level_product_row_buys_level_zero_gap(scm_app):
    """B2155's own figures. `need = project 493 + retail 170 + level 0 - SPO 0 = 663`;
    `buy = 663 - on_hand 128 - PO 339 = 196`. Today's engine instead bypasses the trigger
    on the confirmed Project Buy alone (issue #794) and buys 493 - the row this pins is
    RED against 196, not merely against a different number by chance."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "B2155")
    pid, code = _product(db)  # no master level, no override anywhere
    _mk_stock(db, pid, wid, 128)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} supplier"), moq=None, mult=None)
    _open_po(db, pid, wid, 339)
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=493)
    _core_line_for_run(db, pid, wid, qty=170, demand_class="retail")
    db.flush()

    run_id = _run(db, [wh_code], code)
    row = _sizing_row(_recs(db, run_id, pid))

    assert row["rec_type"] == "buy", row
    assert float(row["recommended_qty"]) == 196.0, row
    assert float(row["rounded_qty"]) == 196.0, row
    assert row["inputs"]["reorder_level"] is None
    assert row["inputs"].get("needs_level") is True
    reason = (row["triggered_reason"] or "").lower()
    assert "project buy" not in reason, (
        f"the level-0 breach must name itself, not the retired project-buy bypass: {reason}"
    )


# --- AC-2: a level-set product-grain row nets the open PO exactly once -----------------

def test_level_row_nets_po_once(scm_app):
    """CBMC5570's own figures: level 100, retail 2, PO 1 -> 101. The engine's OWN net
    already includes the PO book (`net = net_position + po_ordered`, one line per SKU),
    so this pins that the product-grain aggregate does not net it a second time - the
    sheet/grid re-netting bug (S4's second half) lives downstream of this figure, never
    inside it."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "CBMC")
    pid, code = _product(db)
    _set_level(db, pid, None, 100)
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} cbmc"), moq=None, mult=None)
    _open_po(db, pid, wid, 1)
    _core_line_for_run(db, pid, wid, qty=2, demand_class="retail")
    db.flush()

    run_id = _run(db, [wh_code], code)
    row = _sizing_row(_recs(db, run_id, pid))

    assert row["rec_type"] == "buy", row
    assert float(row["recommended_qty"]) == 101.0, row
    assert float(row["rounded_qty"]) == 101.0, row


# --- AC-3: project demand is inside the net, never added a second time -----------------

def test_location_row_project_inside_net(scm_app):
    """A location-grain row (the default forecast/reorder_point basis - a `reorder_level`
    product is ALWAYS planned product-grain, `_is_product_level_basis`, so this is the
    other basis a single-location product actually reaches `_emit_cell` under) with ample
    stock against a modest confirmed Project Buy must read COVERED, not a buy for the
    project amount.

    Today's `_compute_cell` (~2215, `PLAN-reorder-one-formula.md`'s own line reference)
    nets Retail alone against the position, and then bolts the WHOLE confirmed Project Buy
    back on top unconditionally the moment Retail alone does not trigger - so a location
    holding 10,000 against a mere 200 of confirmed project demand still buys 200 today,
    even though the position is many times over both channels combined. The one formula
    folds project into net once: nothing is bought at all.

    Tester's note for the coder/captain: AC-3's own wording ("recommended_qty = level -
    net, level 0 when none") describes the `reorder_level` basis, which this codebase
    routes to `_emit_product` (product grain) UNCONDITIONALLY, with no location-grain
    entry point reachable through the public run pipeline today. This test instead pins
    the identical PRINCIPLE - project is inside net, never added back on top of the
    retail-only netting - on the basis that single-location rows actually reach
    (`_emit_cell`, reorder_point/periodic_review). If the coder's fix keeps the two
    channels split by design at this basis, escalate rather than silently reinterpreting
    this test.
    """
    _, db, _, _ = scm_app
    from app.services.scm import reorder_engine as eng
    eng.ensure_reorder_policy_defaults(db)
    # `_mk_product`'s borrowed category resolves to a product-class `reorder_level`
    # override on this database (the same trap `test_reorder_level_run.py::_use_level_basis`
    # documents), which would route this straight to `_emit_product` and test AC-1's own
    # code path a second time. Forced to `reorder_point` everywhere, matching the idiom
    # `test_pool_netting_parity.py::_plan` already uses for the same reason, so this row
    # actually reaches `_emit_cell` (location grain).
    db.execute(text("UPDATE scm.reorder_policy SET policy_type = 'reorder_point'"))
    db.flush()

    wid, wh_code = _wh(db, "LOCG")
    pid, code = _product(db)
    _mk_stock(db, pid, wid, 10_000)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} locg"), moq=None, mult=None)
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=200)
    db.flush()

    run_id = _run(db, [wh_code], code)
    row = _sizing_row(_recs(db, run_id, pid))

    assert row["rec_type"] == "covered", (
        f"10,000 on hand against 200 of confirmed project demand must read covered, "
        f"not a bolted-on project buy: {row}"
    )
    assert float(row["rounded_qty"] or 0) == 0.0, row
