"""STOCKDEBT-LIVE-ACTIONS: a snapshot freezes the sales order lines and their quantities; the
cover (Assigned, Covered by, Status, Short as far as it depends on cover) is read live.

Owner ruling, 11 Nov 2026: "in stock debt, what should be frozen is the things like quantity,
orders, at the moment, the linkage, request to reserve all those should be updated".
Plan: documentation/plans/scm/PLAN-stockdebt-live-actions-11nov.md.

Red first: before the change the drill served the cover frozen at save time, so a PO link made
from Decide never showed in Assigned / Covered by / Status, even after a reload.
"""
from __future__ import annotations

from decimal import Decimal

from tests.scm.conftest import requires_pg
from tests.scm.test_stock_debt_po_link import (
    DB,
    SNAP,
    _done_split,
    _url,
    _world,
    fake_ss,  # noqa: F401  (pytest fixture)
    refusal_store,  # noqa: F401  (autouse fixture)
)
from tests.scm.test_stock_debt_routes import _demand, _months_ahead

pytestmark = requires_pg

#: The fields of a drill line that follow today's cover, not the snapshot.
LIVE_COVER = {"assigned_qty", "assigned_source", "assigned_from", "status", "short_qty", "lent_qty"}
#: The fields that stay as frozen, whatever happens to the book afterwards.
FROZEN = {"so_number", "line_no", "warehouse_code", "required_date", "open_qty", "qty_ordered",
          "qty_delivered", "bucket", "sales_order_line_id"}


def _drill(w, sid=None, row_id=None):
    resp = w["c"].get(f"{SNAP}/{sid or w['sid']}/rows/{row_id or w['row_id']}/lines")
    assert resp.status_code == 200, resp.text
    return {l["sales_order_line_id"]: l for l in resp.json()["data"]}


def _covered_by(line) -> str:
    return " ".join(str(entry.get("ref") or "") for entry in line.get("assigned_from") or [])


def test_a_link_after_the_snapshot_shows_in_assigned_covered_by_and_status(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    before = _drill(w)[w["so_line"].id]
    assert before["status"] != "pinned"

    fake_ss.answers["/api/v1/autocount/po-links"] = _done_split
    resp = w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 120},
    ]})
    assert resp.json()["results"][0]["outcome"] == "done", resp.text

    after = _drill(w)[w["so_line"].id]
    assert after["status"] == "pinned"
    assert after["assigned_qty"] == 120
    assert after["short_qty"] == 0
    assert w["po"].po_number in _covered_by(after)
    # The sales order line itself stays as frozen.
    assert {k: after[k] for k in FROZEN} == {k: before[k] for k in FROZEN}


def test_an_unlink_after_the_snapshot_drops_the_pin(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    w["db"].flush()
    # A fresh snapshot, taken while the PO line is linked: it freezes the line Pinned.
    c = w["c"]
    sid = c.post(SNAP, json={"name": "linked", "filters": {"query": w["marker"], "only_debt": False}}).json()["id"]
    row_id = next(r["row_id"] for r in c.get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
                  if r["product_code"] == f"{w['marker']}-A")
    assert _drill(w, sid, row_id)[w["so_line"].id]["status"] == "pinned"

    fake_ss.answers["/api/v1/autocount/po-links/unlink"] = (200, {
        "operationId": "op-live", "actionId": None, "outcome": "done", "errorCode": None, "message": "",
        "warnings": [], "docKey": 12008, "docNo": "202609-S0029", "replacedLines": [],
        "document": {"DocKey": 12008, "DocNo": "202609-S0029", "Details": [
            {"DtlKey": 12009, "ItemCode": "X", "Location": w["hq"].warehouse_code, "Qty": 500, "FromSODtlKey": 0},
        ]},
    })
    resp = c.post(f"{SNAP}/{sid}/rows/{row_id}/po-link/unlink", json={"po_line_ids": [w["po_line"].id]})
    assert resp.json()["results"][0]["outcome"] == "done", resp.text

    after = _drill(w, sid, row_id)[w["so_line"].id]
    assert after["status"] != "pinned"
    assert after["now"]["po_links"] == []


def test_a_move_after_the_snapshot_pins_the_other_line_instead(scm_app, fake_ss):
    w = _world(scm_app, fake_ss)
    db = w["db"]
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    other_so, other = _demand(db, w["product"], w["mwh"], qty=30, required_date=_months_ahead(1),
                              so_number=f"{w['marker']}-SO2")
    # A PO line's S/O resolves at document level (`book_sales_orders_by_ref`).
    other_so.source_system = "autocount"
    other_so.source_ref = f"{DB}:11999"
    other.source_system = "autocount"
    other.source_ref = f"{DB}:11999:12001"
    db.flush()
    c = w["c"]
    sid = c.post(SNAP, json={"name": "two", "filters": {"query": w["marker"], "only_debt": False}}).json()["id"]
    row_id = next(r["row_id"] for r in c.get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
                  if r["product_code"] == f"{w['marker']}-A")
    frozen = _drill(w, sid, row_id)
    assert frozen[w["so_line"].id]["status"] == "pinned"
    assert frozen[other.id]["status"] != "pinned"

    # What a done move leaves in the book: the PO line now names the other sales order line.
    w["po_line"].from_so_line_ref = other.source_ref
    db.flush()

    live = _drill(w, sid, row_id)
    assert live[other.id]["status"] == "pinned"
    assert live[w["so_line"].id]["status"] != "pinned"
    assert {k: live[other.id][k] for k in FROZEN} == {k: frozen[other.id][k] for k in FROZEN}


def test_quantities_stay_frozen_and_short_is_frozen_outstanding_less_live_cover(scm_app, fake_ss):
    """A delivery after the snapshot does not move Ordered / Delivered / Outstanding; the line's
    Short is its frozen outstanding less what covers it today."""
    w = _world(scm_app, fake_ss)
    before = _drill(w)[w["so_line"].id]
    assert before["open_qty"] == 120

    w["so_line"].qty_delivered = Decimal("20")
    w["db"].flush()
    # The fake AutoCount answers with a 120 row linked to the line (`_done_split`).
    fake_ss.answers["/api/v1/autocount/po-links"] = _done_split
    w["c"].post(_url(w, "/link"), json={"lines": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["po_line"].id, "qty": 100},
    ]})

    after = _drill(w)[w["so_line"].id]
    # Frozen: the line's quantities as saved.
    assert after["open_qty"] == 120 and after["qty_delivered"] == before["qty_delivered"]
    # Live: today's outstanding (Now), and the cover the walk gives today's 100.
    assert after["now"]["open_qty"] == 100
    assert after["status"] == "pinned" and after["assigned_qty"] == 100
    # Mixed: frozen outstanding 120 less the 100 that covers it in time today.
    assert after["short_qty"] == 20


def test_a_line_gone_from_the_book_keeps_its_frozen_cover(scm_app, fake_ss):
    """A line no longer in today's walk (cancelled, delivered) has no live cover to read: it
    keeps what was frozen, and Now says why (SO cancelled / Open 0)."""
    w = _world(scm_app, fake_ss)
    before = _drill(w)[w["so_line"].id]
    w["so"].status = "cancelled"
    w["db"].flush()
    after = _drill(w)[w["so_line"].id]
    assert {k: after[k] for k in LIVE_COVER} == {k: before[k] for k in LIVE_COVER}
    assert after["now"]["so_status"] == "cancelled"
