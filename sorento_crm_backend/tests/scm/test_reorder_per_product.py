"""Reorder planning per PRODUCT: one level, one net, order up to the level.

`PLAN-scm-reorder-per-product.md` / `scm-reorder-per-product-acceptance-criteria.md`
(captain, 27 Aug): "our reorder is per product, so it doesn't matter your location, just
take the total across all locations", and "with our net, we need to reorder up to the
reorder level".

The `reorder_level` basis used to plan PER LOCATION, with the AutoCount master level
copied onto every bin. SRTWT7408 held 1,296 at BRW and nothing at nine group bins, so
every empty bin read "500 - 0 = 500" and the plan proposed 4,507 units of a product the
company is long on. B2155-NL-BLUE had 12,000 typed into ONE bin's level box and bought
11,430 against a net of 570 at that bin while a sibling held 10,860.

So the whole product is one sizing group here: one level (the buyer's product-wide
override, else the AutoCount master), one net across every location, and the buy is the
gap up to the level. Disposition still runs per location - "this stock has not moved" is
a statement about a place.

Everything is seeded under the ZZTRPP marker inside the `scm_app` savepoint; nothing is
borrowed off an existing row.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm import reorder_level_service as rl
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_channel_read_model import _confirmed_leg, _core_line_for_run
from tests.scm.test_m3_run import (
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)
from tests.scm.test_reorder_level_run import _use_level_basis

pytestmark = requires_pg

MARKER = "ZZTRPP"


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:6]}".upper()


def _wh(db, stem: str) -> tuple[str, str]:
    """(id, code) - the run is scoped by CODE, so both are kept."""
    code = _code(stem)
    return _mk_warehouse(db, code), code


def _product(db, *, master_level: float | None = None) -> tuple[str, str]:
    """(id, code). The master level is `products.reorder_level` - AutoCount's own number.

    Always STATED, never left to the column, because `products.reorder_level` still carries
    a legacy server default of 10: a product built without one would arrive holding a level
    nobody set, and "no master level" is exactly the case AC-R7 is about.
    """
    code = _code("P")
    pid = _mk_product(db, code)
    db.execute(text("UPDATE products SET reorder_level = :l WHERE id = :p"),
               {"l": master_level, "p": pid})
    return pid, code


def _set_level(db, pid: str, wid: str | None, level: float) -> None:
    """A stored level, at the product (``wid=None``) or at one location."""
    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
        "created_at) VALUES (:id, :p, :w, :l, 'manual', now())"
    ), {"id": str(uuid.uuid4()), "p": pid, "w": wid, "l": level})
    db.flush()


def _open_po(db, pid: str, wid: str, qty: float) -> str:
    """An ordered-not-received purchase line, which is what `scm.po_ordered_v` counts.
    Returns the LINE id so a caller can link an order-inquiry row to it."""
    poid = str(uuid.uuid4())
    line_id = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, issue_date, status, created_at, "
        "updated_at) VALUES (:id, :n, CURRENT_DATE - 2, 'active', now(), now())"
    ), {"id": poid, "n": f"{MARKER}PO-{poid[:8]}"})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_received, unit_cost, line_status, created_at, updated_at) "
        "VALUES (:id, :po, :p, :w, :q, 0, 10, 'open', now(), now())"
    ), {"id": line_id, "po": poid, "p": pid, "w": wid, "q": qty})
    db.flush()
    return line_id


def _link_row_to_po(db, row_id: str, po_line_id: str, qty: float) -> None:
    """Part of an order-inquiry row's quantity, already placed on a purchase line."""
    from tests.scm.conftest import SORENTO_COMPANY_ID

    db.execute(text(
        "INSERT INTO projects.order_inquiry_links (id, row_id, po_line_id, qty, document, "
        "company_id, linked_at, created_at) "
        "VALUES (:id, :row, :pol, :q, :doc, :co, now(), now())"
    ), {"id": str(uuid.uuid4()), "row": row_id, "pol": po_line_id, "q": qty,
        "doc": f"{MARKER}-PO", "co": SORENTO_COMPANY_ID})
    db.flush()


def _run(db, warehouse_codes: list[str], product_code: str) -> str:
    """Plan exactly what this test seeded. A run with no scope plans the whole catalogue,
    which on the local prod-copy database is 11,000 products of somebody else's data."""
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


def _buys(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["rec_type"] == "buy"]


def _sizing_row(rows: list[dict]) -> dict:
    """The product's ONE planning row - whatever kind the run ended up emitting."""
    planning = [r for r in rows if r["rec_type"] != "disposition"]
    assert len(planning) == 1, (
        f"one product is one sizing decision, got {[r['rec_type'] for r in planning]}"
    )
    return planning[0]


# --- AC-R1: one net per product ---------------------------------------------------------

def test_one_net_across_every_location_leaves_an_overstocked_product_alone(scm_app):
    """AC-R1, SRTWT7408 as it stood on the walk.

    1,296 at the pool root, nothing at nine group bins, master level 500, 7 retail
    outstanding. The net is the product's own 1,289, comfortably above the level, so
    nothing is bought - and no row reads "level 500, on hand 0" for a bin.
    """
    _, db, _, _ = scm_app
    _use_level_basis(db)
    root, root_code = _wh(db, "R")
    bins = [_wh(db, f"B{i}") for i in range(9)]
    pid, code = _product(db, master_level=500)
    _mk_stock(db, pid, root, 1296)
    _mk_demand(db, pid, root, 0.0)
    for wid, _ in bins:
        _mk_stock(db, pid, wid, 0)
        _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R1"), moq=None, mult=None)
    _core_line_for_run(db, pid, root, qty=7, demand_class="retail")
    db.flush()

    rows = _recs(db, _run(db, [root_code] + [c for _, c in bins], code), pid)

    assert not _buys(rows), "1,289 against a level of 500 is not a shortage"
    row = _sizing_row(rows)
    assert float(row["inputs"]["net"]) == 1289.0
    assert float(row["inputs"]["on_hand"]) == 1296.0, "on hand is the product's, not a bin's"
    assert float(row["inputs"]["reorder_level"]) == 500.0
    assert not [r for r in rows
                if float((r["inputs"] or {}).get("reorder_level") or 0) == 500.0
                and float((r["inputs"] or {}).get("on_hand") or 0) == 0.0], (
        "an empty bin must never be sized against the product's level"
    )


# --- AC-R2: order up to the level -------------------------------------------------------

def test_the_buy_is_the_gap_from_the_net_up_to_the_level(scm_app):
    """AC-R2, B2155-NL-BLUE's own figures: 10,860 + 860 on order - 150 project - 290
    retail = 11,280 against a level of 12,000, so the buy is 720."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    (a, a_code), (b, b_code), (c, c_code) = (_wh(db, s) for s in ("A", "B", "C"))
    pid, code = _product(db)
    _set_level(db, pid, None, 12000)
    _mk_stock(db, pid, a, 10860)
    _mk_stock(db, pid, b, 0)
    _mk_stock(db, pid, c, 0)
    for wid in (a, b, c):
        _mk_demand(db, pid, wid, 0.0)
    _open_po(db, pid, a, 860)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R2"), moq=None, mult=None)
    _core_line_for_run(db, pid, a, qty=290, demand_class="retail")
    _confirmed_leg(db, product_id=pid, warehouse_id=a, buy_qty=150)
    db.flush()

    rows = _recs(db, _run(db, [a_code, b_code, c_code], code), pid)

    buys = _buys(rows)
    assert len(buys) == 1, "one product is one buy line"
    assert float(buys[0]["inputs"]["net"]) == 11280.0
    assert float(buys[0]["recommended_qty"]) == 720.0
    assert float(buys[0]["rounded_qty"]) == 720.0


# --- AC-R3: a per-location level is ignored ---------------------------------------------

def test_a_location_level_is_ignored_and_the_autocount_master_decides(scm_app):
    """AC-R3: a level typed against ONE bin cannot size the product. With no product-wide
    override the plan reads the AutoCount master level, and the row says so."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    root, root_code = _wh(db, "MR")
    bin_, bin_code = _wh(db, "MB")
    pid, code = _product(db, master_level=500)
    _set_level(db, pid, bin_, 12000)
    _mk_stock(db, pid, root, 100)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R3"), moq=None, mult=None)
    db.flush()

    rows = _recs(db, _run(db, [root_code, bin_code], code), pid)

    buys = _buys(rows)
    assert len(buys) == 1
    assert float(buys[0]["inputs"]["reorder_level"]) == 500.0, "the bin's 12,000 is ignored"
    assert buys[0]["inputs"]["reorder_level_source"] == "autocount_master"
    assert float(buys[0]["rounded_qty"]) == 400.0


def test_the_product_wide_override_beats_the_autocount_master(scm_app):
    """AC-R3's other half: the buyer's own number wins, and the row names it as theirs."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "OV")
    pid, code = _product(db, master_level=500)
    _set_level(db, pid, None, 900)
    _mk_stock(db, pid, wid, 100)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R3B"), moq=None, mult=None)
    db.flush()

    buys = _buys(_recs(db, _run(db, [wh_code], code), pid))
    assert len(buys) == 1
    assert float(buys[0]["inputs"]["reorder_level"]) == 900.0
    assert buys[0]["inputs"]["reorder_level_source"] == "manual"
    assert float(buys[0]["rounded_qty"]) == 800.0


# --- AC-R4 / AC-R5: which project demand counts -----------------------------------------

def test_an_awaiting_order_inquiry_row_is_not_demand(scm_app):
    """AC-R4 (`PLAN-scm-oi-handshake.md` section 3): a plan may only buy against an
    instruction purchasing has taken on. 100 awaiting + 20 acknowledged is 20 of demand."""
    from app.models.project_so import ACK_AWAITING

    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "AK")
    pid, code = _product(db)
    _set_level(db, pid, None, 200)
    _mk_stock(db, pid, wid, 100)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R4"), moq=None, mult=None)
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=100,
                   ack_state=ACK_AWAITING)
    _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=20)
    db.flush()

    buys = _buys(_recs(db, _run(db, [wh_code], code), pid))
    assert len(buys) == 1
    assert float(buys[0]["inputs"]["project_committed"]) == 20.0
    assert float(buys[0]["inputs"]["net"]) == 80.0, "100 on hand less the acknowledged 20"
    assert float(buys[0]["rounded_qty"]) == 120.0


def test_only_the_unlinked_remainder_counts_and_the_po_counts_once(scm_app):
    """AC-R5: an acknowledged row of 50 with 30 already placed on a purchase order is 20
    of demand, and that purchase order's 30 is incoming supply - counted once."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "LK")
    pid, code = _product(db)
    _set_level(db, pid, None, 100)
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R5"), moq=None, mult=None)
    made = _confirmed_leg(db, product_id=pid, warehouse_id=wid, buy_qty=50)
    po_line = _open_po(db, pid, wid, 30)
    _link_row_to_po(db, str(made["inquiry_row"].id), po_line, 30)
    db.flush()

    buys = _buys(_recs(db, _run(db, [wh_code], code), pid))
    assert len(buys) == 1
    inputs = buys[0]["inputs"]
    assert float(inputs["project_committed"]) == 20.0, "the un-linked remainder"
    assert float(inputs["po_ordered"]) == 30.0
    assert float(inputs["net"]) == 10.0, "0 on hand + 30 on order - 20 still owed"
    assert float(buys[0]["rounded_qty"]) == 90.0


# --- AC-R6: the supplier's terms --------------------------------------------------------

def test_the_moq_and_the_multiple_shape_the_order(scm_app):
    """AC-R6: a gap of 720 under a MoQ of 1,000 buys 1,000."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "MQ")
    pid, code = _product(db)
    _set_level(db, pid, None, 12000)
    _mk_stock(db, pid, wid, 11280)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R6"), moq=1000, mult=100)
    db.flush()

    buys = _buys(_recs(db, _run(db, [wh_code], code), pid))
    assert len(buys) == 1
    assert float(buys[0]["recommended_qty"]) == 720.0, "the honest gap"
    assert float(buys[0]["rounded_qty"]) == 1000.0


def test_no_gap_buys_nothing_whatever_the_moq(scm_app):
    """AC-R6's second half: a net AT the level has nothing to top up, and a MoQ is not a
    reason to buy - it is a shape the order takes once there IS one."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "MQ0")
    pid, code = _product(db)
    _set_level(db, pid, None, 11280)
    _mk_stock(db, pid, wid, 11280)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R6B"), moq=1000, mult=100)
    db.flush()

    rows = _recs(db, _run(db, [wh_code], code), pid)
    assert not [r for r in _buys(rows) if float(r["rounded_qty"] or 0) > 0]


# --- AC-R7: no level, no guess ----------------------------------------------------------

def test_a_product_with_no_level_anywhere_is_named_not_guessed_at(scm_app):
    """AC-R7: no override and no master level is `needs_level`, carrying the suggestion,
    and nothing is bought. The row names the PRODUCT, so accepting the suggestion writes
    the product-wide level the next plan will read."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    a, a_code = _wh(db, "NLA")
    b, b_code = _wh(db, "NLB")
    pid, code = _product(db)
    for wid in (a, b):
        _mk_stock(db, pid, wid, 0)
        _mk_demand(db, pid, wid, 3.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R7"), moq=None, mult=None)
    rl.store_suggestion(db, product_id=pid, warehouse_id=None, suggested_level=99.0,
                        basis={"avg_monthly": 49.5, "cover_months": 2, "months_studied": 3})
    db.flush()

    rows = _recs(db, _run(db, [a_code, b_code], code), pid)

    assert not _buys(rows), "an unset level must never be planned as 0"
    row = _sizing_row(rows)
    assert row["rec_type"] == "needs_level"
    assert row["warehouse_id"] is None, "the level to set is the product's, not a bin's"
    assert float(row["inputs"]["suggested_level"]) == 99.0
    assert row["rounded_qty"] is None


def test_a_master_level_of_zero_is_not_a_level(scm_app):
    """AC-R7: 0 is a real target that any deficit trips, so it would buy the whole
    shortage on a number nobody chose."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "NL0")
    pid, code = _product(db, master_level=0)
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 3.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R7B"), moq=None, mult=None)
    _core_line_for_run(db, pid, wid, qty=40, demand_class="retail")
    db.flush()

    rows = _recs(db, _run(db, [wh_code], code), pid)
    assert not _buys(rows)
    assert _sizing_row(rows)["rec_type"] == "needs_level"


# --- AC-R9: Set level writes the product row --------------------------------------------

def test_set_level_writes_the_product_wide_row(scm_app):
    """AC-R9: the level the plan reads is the product's, so setting one from the plan
    writes THAT row - a per-location row would be a save that changes nothing."""
    app, db, gcu, gcuak = scm_app
    as_user(app, gcu, gcuak, seed_user(db, "purchasing"))
    wid, _ = _wh(db, "SL")
    pid, _code_unused = _product(db)
    db.flush()

    with TestClient(app) as client:
        res = client.put("/api/v1/scm/reorder-levels",
                         json={"product_id": pid, "warehouse_id": wid, "level": 12000})
    assert res.status_code == 200, res.text

    rows = [dict(r) for r in db.execute(text(
        "SELECT warehouse_id::text AS warehouse_id, level, source "
        "FROM scm.reorder_level WHERE product_id = :p"
    ), {"p": pid}).mappings().all()]
    assert len(rows) == 1
    assert rows[0]["warehouse_id"] is None
    assert float(rows[0]["level"]) == 12000.0
    assert rows[0]["source"] == "manual"


# --- AC-R10: disposition is still about a place -----------------------------------------

def test_the_overstocked_location_still_gets_its_disposition_row(scm_app):
    """AC-R10: netting per product does not aggregate away "this bin is sitting on a
    year of cover". Disposition is a statement about a place and stays per location."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    root, root_code = _wh(db, "DR")
    bin_, bin_code = _wh(db, "DB")
    pid, code = _product(db, master_level=500)
    _mk_stock(db, pid, root, 1296)
    _mk_stock(db, pid, bin_, 0)
    _mk_demand(db, pid, root, 0.2)
    _mk_demand(db, pid, bin_, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} R10"), moq=None, mult=None)
    db.flush()

    rows = _recs(db, _run(db, [root_code, bin_code], code), pid)

    disposition = [r for r in rows if r["rec_type"] == "disposition"]
    assert len(disposition) == 1, "the location holding the stock, and only it"
    assert disposition[0]["warehouse_id"] == root
    assert disposition[0]["inputs"]["disposition_action"] == "hold"


# --- the lane run, 27 Aug: three things the seeded tests did not catch -------------------

def _segment(db, wid: str, segment: str) -> None:
    db.execute(text("UPDATE warehouses SET segment = :s WHERE id = :w"),
               {"s": segment, "w": wid})
    db.flush()


def test_stock_at_a_group_bin_counts_toward_the_products_own_net(scm_app):
    """AC-R1 as the lane run found it: "every location" is every `stock` row.

    SRTWT7408 holds 5,498 across the warehouses, but the plan counted 1,296 - the group
    bins are `segment = 'project'`, and every other planning path deliberately drops their
    stock (captain, 20 Aug: a project bin's quantity is not freely usable). This basis asks
    a different question - how much of this item does the company have - so the bins count,
    and the row still says how much of the total is sitting in one.
    """
    _, db, _, _ = scm_app
    _use_level_basis(db)
    root, root_code = _wh(db, "GBR")
    bin_, bin_code = _wh(db, "GBB")
    _segment(db, root, "dealer")
    _segment(db, bin_, "project")
    pid, code = _product(db, master_level=500)
    _mk_stock(db, pid, root, 1296)
    _mk_stock(db, pid, bin_, 4202)
    _mk_demand(db, pid, root, 0.0)
    _mk_demand(db, pid, bin_, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} GB"), moq=None, mult=None)
    _core_line_for_run(db, pid, root, qty=7, demand_class="retail")
    db.flush()

    rows = _recs(db, _run(db, [root_code, bin_code], code), pid)

    assert not _buys(rows), "5,491 against a level of 500 is not a shortage"
    inputs = _sizing_row(rows)["inputs"]
    assert float(inputs["on_hand"]) == 5498.0, "the whole stock, both bins"
    assert float(inputs["project_on_hand"]) == 4202.0, "and how much of it sits in a bin"
    assert float(inputs["net"]) == 5491.0
    by_code = {loc["warehouse_code"]: loc for loc in inputs["plan_basis"]["locations"]}
    assert float(by_code[bin_code]["on_hand"]) == 4202.0, (
        "a bin reading 0 beside 4,202 of its own stock is what made the product look empty"
    )


def test_an_autocount_mirror_of_zero_is_not_a_buyers_level(scm_app):
    """AC-R7 / AC-R2 as the lane run found it: the level upload mirrors the AutoCount master
    into `scm.reorder_level` (`source = 'autocount'`, 7,852 of them a level of 0 on the live
    copy). Read as an override, B2155-NL-BLUE planned against a level of 0 and reported
    itself covered on a net of 3,065 - when nobody had set it a level at all."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "ACZ")
    pid, code = _product(db, master_level=0)
    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, notes, "
        "created_at) VALUES (:id, :p, NULL, 0, 'autocount', 'AutoCount upload by ZZT', now())"
    ), {"id": str(uuid.uuid4()), "p": pid})
    _mk_stock(db, pid, wid, 3065)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} ACZ"), moq=None, mult=None)
    _core_line_for_run(db, pid, wid, qty=40, demand_class="retail")
    db.flush()

    rows = _recs(db, _run(db, [wh_code], code), pid)

    assert not _buys(rows)
    row = _sizing_row(rows)
    assert row["rec_type"] == "needs_level", (
        "a mirrored master of 0 is not a level, whichever table it is read from"
    )


def test_an_autocount_mirror_with_a_level_is_the_master_not_an_override(scm_app):
    """The other half: the mirror IS the master, so a real number in it plans the product -
    and the row names it as AutoCount's rather than as somebody's own decision (AC-R3)."""
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "ACM")
    pid, code = _product(db, master_level=None)
    db.execute(text(
        "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, notes, "
        "created_at) VALUES (:id, :p, NULL, 500, 'autocount', 'AutoCount upload by ZZT', now())"
    ), {"id": str(uuid.uuid4()), "p": pid})
    _mk_stock(db, pid, wid, 100)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} ACM"), moq=None, mult=None)
    db.flush()

    buys = _buys(_recs(db, _run(db, [wh_code], code), pid))
    assert len(buys) == 1
    assert float(buys[0]["inputs"]["reorder_level"]) == 500.0
    assert buys[0]["inputs"]["reorder_level_source"] == "autocount_master"
    assert float(buys[0]["rounded_qty"]) == 400.0


def test_a_covered_row_suggests_buying_nothing(scm_app):
    """A covered row means the stock is already there, so the quantity it SUGGESTS is 0.

    `recommended_qty` carried the committed demand instead, so the plan read as a
    7,936-unit suggestion for a product holding more than it owes. What buying anyway would
    cost stays on `rounded_qty` - the Covered-by-stock view's "Buy anyway" column, and the
    quantity `decision_service` records if the buyer takes it.
    """
    _, db, _, _ = scm_app
    _use_level_basis(db)
    wid, wh_code = _wh(db, "CVD")
    pid, code = _product(db, master_level=500)
    _set_level(db, pid, None, 500)
    _mk_stock(db, pid, wid, 4000)
    _mk_demand(db, pid, wid, 0.0)
    _link(db, pid, _mk_supplier(db, f"{MARKER} CVD"), moq=None, mult=None)
    _core_line_for_run(db, pid, wid, qty=200, demand_class="retail")
    db.flush()

    row = _sizing_row(_recs(db, _run(db, [wh_code], code), pid))

    assert row["rec_type"] == "covered"
    assert float(row["recommended_qty"]) == 0.0, "nothing is being bought"
    assert float(row["rounded_qty"]) == 200.0, "what buying anyway would cost, kept"
    assert float(row["inputs"]["covered_committed"]) == 200.0
