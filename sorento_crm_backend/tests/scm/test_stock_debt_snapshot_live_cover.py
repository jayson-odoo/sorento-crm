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


# --------------------------------------------------------------------------- Change PO (part 2)

from tests.scm.test_stock_debt_po_link import _po_line  # noqa: E402


def _covered_world(scm_app, fake_ss):
    """The `_world` line (120) covered by its PO line (500, linked whole), plus a second open
    PO line of 200 on another PO, unlinked."""
    w = _world(scm_app, fake_ss)
    db = w["db"]
    w["po_line"].qty_ordered = Decimal("120")
    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    new_po, new_line = _po_line(db, w["product"], w["hq"], qty=200, doc_key=12100, dtl_key=12101)
    db.flush()
    return {**w, "new_po": new_po, "new_line": new_line}


def _change(w, po_line_id=None):
    return w["c"].post(_url(w, "/change"), json={"changes": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": po_line_id or w["new_line"].id},
    ]})


def _link_done(w):
    def answer(_request):
        return 200, {
            "operationId": "op-ch", "actionId": None, "outcome": "done", "errorCode": None,
            "message": "", "warnings": [], "docKey": 12100, "docNo": w["new_po"].po_number,
            "replacedLines": [],
            "document": {"DocKey": 12100, "DocNo": w["new_po"].po_number, "Details": [
                {"DtlKey": 12101, "ItemCode": "X", "Location": w["hq"].warehouse_code, "Qty": 80,
                 "FromSODtlKey": None},
                {"DtlKey": 12180, "ItemCode": "X", "Location": w["hq"].warehouse_code, "Qty": 120,
                 "FromSODtlKey": 11990},
            ]},
        }
    return answer


def _unlink_done(w):
    return 200, {
        "operationId": "op-un", "actionId": None, "outcome": "done", "errorCode": None, "message": "",
        "warnings": [], "docKey": 12008, "docNo": w["po"].po_number, "replacedLines": [],
        "document": {"DocKey": 12008, "DocNo": w["po"].po_number, "Details": [
            {"DtlKey": 12009, "ItemCode": "X", "Location": w["hq"].warehouse_code, "Qty": 120,
             "FromSODtlKey": 0},
        ]},
    }


def _refuse_link_while_covered(w):
    """AutoCount's own rule (AC-E2E-DB3, db3, 11 Nov): a link is QTY_ABOVE_OUTSTANDING while
    the old PO row still covers the SO row; once the unlink went through it is done."""
    def answer(request):
        if not fake_ss_unlinked(w):
            return 409, {"operationId": None, "outcome": "refused", "errorCode": "QTY_ABOVE_OUTSTANDING",
                         "message": "quantity above the SO row outstanding"}
        return _link_done(w)(request)
    return answer


def fake_ss_unlinked(w) -> bool:
    return any(r.url.path == "/api/v1/autocount/po-links/unlink" for r in w["fake"].calls)


def test_change_unlinks_the_old_po_line_then_links_the_new_one(scm_app, fake_ss):
    from app.models.procurement import PurchaseOrderLine

    w = {**_covered_world(scm_app, fake_ss), "fake": fake_ss}
    fake_ss.answers["/api/v1/autocount/po-links"] = _refuse_link_while_covered(w)
    fake_ss.answers["/api/v1/autocount/po-links/unlink"] = _unlink_done(w)
    resp = _change(w)
    assert resp.status_code == 200, resp.text
    unlink, link = resp.json()["results"]
    assert (unlink["action"], unlink["outcome"]) == ("unlink", "done")
    assert (link["action"], link["outcome"], link["qty"]) == ("link", "done", 120)
    assert link["unlinked_po"] is None

    (unbody,) = fake_ss.bodies("/api/v1/autocount/po-links/unlink")
    assert (unbody["poDocKey"], unbody["poDtlKey"]) == (12008, 12009)
    (body,) = fake_ss.bodies("/api/v1/autocount/po-links")
    assert (body["poDocKey"], body["poDtlKey"], body["qty"]) == (12100, 12101, 120)
    assert (body["soDocKey"], body["soDtlKey"]) == (11988, 11990)
    paths = [r.url.path for r in fake_ss.calls if "po-links" in r.url.path]
    assert paths == ["/api/v1/autocount/po-links/unlink", "/api/v1/autocount/po-links"]

    db = w["db"]
    db.expire_all()
    old = db.get(PurchaseOrderLine, w["po_line"].id)
    # The old PO line stays open as free supply, qty untouched.
    assert old.from_so_line_ref is None and old.line_status == "open"
    assert old.qty_ordered == Decimal("120")
    # The drill reads the new cover at once (part 1).
    line = _drill(w)[w["so_line"].id]
    assert [po["po_number"] for po in line["now"]["po_links"]] == [w["new_po"].po_number]
    assert line["status"] == "pinned"


def test_change_refuses_when_the_new_po_line_has_too_little_free(scm_app, fake_ss):
    w = _covered_world(scm_app, fake_ss)
    w["new_line"].qty_received = Decimal("150")  # 50 free, 120 needed
    w["db"].flush()
    resp = _change(w)
    assert resp.status_code == 422
    assert resp.json()["message"] == f"PO {w['new_po'].po_number} has only 50 free."
    assert not [r for r in fake_ss.calls if "po-links" in r.url.path], "nothing is sent"


def test_change_refuses_a_line_not_covered_by_exactly_one_po_line(scm_app, fake_ss):
    w = _covered_world(scm_app, fake_ss)
    w["po_line"].from_so_line_ref = None  # not covered at all
    w["db"].flush()
    resp = _change(w)
    assert resp.status_code == 422
    assert "not covered by exactly one PO line" in resp.json()["message"]

    w["po_line"].from_so_line_ref = w["so_line"].source_ref
    _po_line(w["db"], w["product"], w["hq"], qty=10, so_ref=w["so_line"].source_ref,
             po=w["po"], dtl_key=12020)
    w["db"].flush()
    resp = _change(w)
    assert resp.status_code == 422
    assert "not covered by exactly one PO line" in resp.json()["message"]
    assert not [r for r in fake_ss.calls if "po-links" in r.url.path]


def test_change_to_the_same_po_line_is_refused(scm_app, fake_ss):
    w = _covered_world(scm_app, fake_ss)
    resp = _change(w, po_line_id=w["po_line"].id)
    assert resp.status_code == 422


def test_a_refused_unlink_sends_no_link_and_leaves_the_old_po_line_linked(scm_app, fake_ss):
    from app.models.procurement import PurchaseOrderLine

    w = _covered_world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links/unlink"] = (409, {
        "operationId": None, "outcome": "refused", "errorCode": "DOC_STALE", "message": "",
    })
    resp = _change(w)
    assert resp.status_code == 200, resp.text
    (unlink,) = resp.json()["results"]
    assert (unlink["action"], unlink["outcome"]) == ("unlink", "refused")
    assert not fake_ss.bodies("/api/v1/autocount/po-links"), "no link after a refused unlink"
    w["db"].expire_all()
    assert w["db"].get(PurchaseOrderLine, w["po_line"].id).from_so_line_ref == w["so_line"].source_ref


def test_a_refused_link_after_the_unlink_names_the_po_unlinked(scm_app, fake_ss):
    w = _covered_world(scm_app, fake_ss)
    fake_ss.answers["/api/v1/autocount/po-links/unlink"] = _unlink_done(w)
    fake_ss.answers["/api/v1/autocount/po-links"] = (409, {
        "operationId": None, "outcome": "refused", "errorCode": "DOC_STALE", "message": "",
    })
    unlink, link = _change(w).json()["results"]
    assert unlink["outcome"] == "done"
    assert (link["outcome"], link["unlinked_po"]) == ("refused", w["po"].po_number)


def test_change_needs_the_switch_on(scm_app, fake_ss):
    from tests.scm.test_stock_debt_po_link import _switch

    w = _covered_world(scm_app, fake_ss)
    _switch(w["db"], False)
    assert _change(w).status_code == 403


# --------------------------------------------------------------------------- review round 1

def _snap(w, **filters):
    c = w["c"]
    resp = c.post(SNAP, json={"name": "filtered", "filters": {"query": w["marker"], "only_debt": False, **filters}})
    assert resp.status_code == 201, resp.text
    sid = resp.json()["id"]
    row_id = next(r["row_id"] for r in c.get(f"{SNAP}/{sid}/rows", params={"limit": 200}).json()["data"]
                  if r["product_code"] == f"{w['marker']}-A")
    return sid, row_id


def test_live_cover_walks_under_the_snapshots_date_from(scm_app, fake_ss):
    """A line due before `date_from` is out of the snapshot; today's walk must leave it out too,
    or it takes the stock first and the snapshot's line reads less covered than it is."""
    from datetime import date as _date

    from tests.scm.test_stock_debt_routes import _stock

    w = _world(scm_app, fake_ss)
    db = w["db"]
    _stock(db, w["product"], w["mwh"], 120)
    _demand(db, w["product"], w["mwh"], qty=100, required_date=_date.today(), so_number=f"{w['marker']}-EARLY")
    db.flush()
    sid, row_id = _snap(w, date_from=w["so_line"].required_date.isoformat())
    assert _drill(w, sid, row_id)[w["so_line"].id]["assigned_qty"] == 120
    # Without the filter the early line takes 100 of the 120 first.
    sid_all, row_all = _snap(w)
    assert _drill(w, sid_all, row_all)[w["so_line"].id]["assigned_qty"] == 20


def test_live_cover_walks_under_the_snapshots_location(scm_app, fake_ss):
    """Narrowed to MWH, an HQ line is outside the span: today's walk must not let it take
    the stock first."""
    from datetime import date as _date

    from tests.scm.test_stock_debt_routes import _stock

    w = _world(scm_app, fake_ss)
    db = w["db"]
    _stock(db, w["product"], w["mwh"], 120)
    _demand(db, w["product"], w["hq"], qty=100, required_date=_date.today(), so_number=f"{w['marker']}-HQ")
    db.flush()
    sid, row_id = _snap(w, location=[w["mwh"].id])
    narrowed = _drill(w, sid, row_id)[w["so_line"].id]["assigned_qty"]
    sid_all, row_all = _snap(w)
    unfiltered = _drill(w, sid_all, row_all)[w["so_line"].id]["assigned_qty"]
    assert (narrowed, unfiltered) == (120, 20)


def test_two_changes_onto_one_po_line_share_its_free(scm_app, fake_ss):
    """Owner card 3a over a whole request: two lines of 120 onto a PO line with 200 free."""
    w = _covered_world(scm_app, fake_ss)
    db = w["db"]
    _o2, line2 = _demand(db, w["product"], w["mwh"], qty=120, required_date=_months_ahead(1),
                         so_number=f"{w['marker']}-SO2")
    _o2.source_system = "autocount"
    _o2.source_ref = f"{DB}:11999"
    line2.source_system = "autocount"
    line2.source_ref = f"{DB}:11999:12001"
    _po_line(db, w["product"], w["hq"], qty=120, so_ref=line2.source_ref, doc_key=12200, dtl_key=12201)
    db.flush()
    sid, row_id = _snap(w)
    resp = w["c"].post(f"{SNAP}/{sid}/rows/{row_id}/po-link/change", json={"changes": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["new_line"].id},
        {"sales_order_line_id": line2.id, "po_line_id": w["new_line"].id},
    ]})
    assert resp.status_code == 422
    assert resp.json()["message"] == f"PO {w['new_po'].po_number} has only 200 free."
    assert not [r for r in fake_ss.calls if "po-links" in r.url.path], "nothing is sent"


def test_change_moves_the_linked_qty_less_what_was_cancelled(scm_app, fake_ss):
    w = _covered_world(scm_app, fake_ss)
    w["po_line"].qty_cancelled = Decimal("20")
    w["db"].flush()
    fake_ss.answers["/api/v1/autocount/po-links"] = _link_done(w)
    fake_ss.answers["/api/v1/autocount/po-links/unlink"] = _unlink_done(w)
    assert _change(w).status_code == 200
    (body,) = fake_ss.bodies("/api/v1/autocount/po-links")
    assert body["qty"] == 100


def test_change_refuses_the_same_sales_order_line_twice(scm_app, fake_ss):
    w = _covered_world(scm_app, fake_ss)
    resp = w["c"].post(_url(w, "/change"), json={"changes": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["new_line"].id},
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["new_line"].id},
    ]})
    assert resp.status_code == 422
    assert resp.json()["message"] == "Name each sales order line once."
    assert not [r for r in fake_ss.calls if "po-links" in r.url.path]


def test_change_checks_the_old_po_line_before_anything_is_sent(scm_app, fake_ss):
    """An old PO line AutoCount cannot address (no keys) is refused up front, never after the
    new link already went out."""
    w = _covered_world(scm_app, fake_ss)
    w["po_line"].source_ref = None
    w["db"].flush()
    resp = _change(w)
    assert resp.status_code == 422
    assert not [r for r in fake_ss.calls if "po-links" in r.url.path]


def test_unlinking_one_row_again_after_a_relink_is_a_new_key(scm_app, fake_ss):
    """The unlink body names no sales order; its key carries the link it removes, so the same
    row unlinked from another SO line later is a new intent, not a replay."""
    from app.services.scm.stock_debt_po_link_service import StockDebtPoLinkService

    w = _world(scm_app, fake_ss)
    body = {"companyCode": "X", "poDocKey": 12008, "poDtlKey": 12009}
    w["po_line"].from_so_line_ref = f"{DB}:11988:11990"
    first = StockDebtPoLinkService._intent_key("po-links/unlink", body, w["po_line"])
    w["po_line"].from_so_line_ref = f"{DB}:11999:12001"
    second = StockDebtPoLinkService._intent_key("po-links/unlink", body, w["po_line"])
    assert first != second
    # The link path's key is unchanged by the PO line's own link.
    link_body = {**body, "soDocKey": 1, "soDtlKey": 2, "qty": 5}
    assert StockDebtPoLinkService._intent_key("po-links", link_body, w["po_line"]) == (
        StockDebtPoLinkService._intent_key("po-links", link_body, w["po_line"])
    )


def test_change_needs_the_link_permission(scm_app, fake_ss):
    from tests.scm.test_stock_debt_po_link import _client as _po_client
    from tests.scm.test_stock_debt_routes import VIEW

    w = _covered_world(scm_app, fake_ss)
    c, _db = _po_client(scm_app, permissions=(VIEW,))
    resp = c.post(_url(w, "/change"), json={"changes": [
        {"sales_order_line_id": w["so_line"].id, "po_line_id": w["new_line"].id},
    ]})
    assert resp.status_code == 403
