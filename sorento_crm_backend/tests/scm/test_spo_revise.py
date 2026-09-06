"""R24 (AC-K1..AC-K5) - an SPO already created is edited through the planner.

TEST-FIRST: `spo_conversion_service.planner_state` and `.revise` do not exist at the time
this file is written, so every test here is expected to be red until they land.

Two moves, mirroring `suggest` / `create`:

  * `planner_state` - a pure read. One SPO's own lines, each carrying BOTH the suggestion
    shape (so the planner's PO-takes and SO-covered lightboxes work unchanged) and the state
    it was persisted with: `spo_qty`, `location_splits`, `po_take_ids`, `so_takes`,
    `received_qty`. THIS SPO's own claims are taken back OUT of the candidate lists - its PO
    pulls read open again, its ticked demand outstanding again - because a state that reads
    as taken by somebody else cannot be re-ticked.
  * `revise` - the write. Same payload `create` posts, same guards, plus one of its own: a
    quantity below what an allocation has RECEIVED is refused (422) naming the product and
    the warehouse, and NOTHING is written - not even a valid change on another line of the
    same body (AC-K3). The SPO number and its header row are never touched (AC-K2); a line
    dropped from the payload, or sent `include: False`, is unwound for that line alone
    (AC-K4).

Postgres only, marker-prefixed, every test seeds its own chain (CI's database is empty).
The `World` builder and the project/retail demand chains are reused from the two suites
that already own them rather than copied - this is the same service, and a second world
would be a second set of assumptions about what a shipment looks like.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.procurement import (
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.project_so import OrderInquiryLink
from app.models.scm import OrderLinkClaim, ShipmentLineSpoLink
from app.services.error_handler import AppException
from app.services.scm import spo_conversion_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_spo_conversion import World, _u
from tests.scm.test_spo_planner_selection import _confirm, _project_chain, _retail_demand

pytestmark = requires_pg


def _state_line(state: dict, shipment_line_id: str) -> dict:
    for ln in state["lines"]:
        if ln["shipment_line_id"] == shipment_line_id:
            return ln
    raise AssertionError(f"no line {shipment_line_id} in planner state")


def _allocations(db, po_id: str) -> list[SPOAllocation]:
    """This SPO's own allocation rows. The chain is `spo_allocations.po_line_id` ->
    `purchase_order_lines.purchase_order_id` - the SPO's OWN line, which is what
    `create` writes there (never the source PO line it pulled from)."""
    return (
        db.query(SPOAllocation)
        .join(PurchaseOrderLine, PurchaseOrderLine.id == SPOAllocation.po_line_id)
        .filter(PurchaseOrderLine.purchase_order_id == po_id)
        .all()
    )


def _po_lines(db, po_id: str) -> list[PurchaseOrderLine]:
    return (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.purchase_order_id == po_id)
        .all()
    )


# --------------------------------------------------------------------------- #
# AC-K1 - planner_state: what the planner re-opens the SPO with
# --------------------------------------------------------------------------- #


def test_planner_state_returns_the_persisted_qty_splits_takes_and_ticks():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh_a, wh_b = w.warehouse("A"), w.warehouse("B")
        source_po = w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        retail, _so = _retail_demand(db, w, "A", wh_b, qty=30, required=date(2026, 9, 20))

        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 70,
                location_splits=[
                    {"warehouse_id": str(wh_a.id), "qty": 40},
                    {"warehouse_id": str(wh_b.id), "qty": 30},
                ],
                po_take_ids=[str(source_po.lines[0].id)],
                so_takes=[
                    {"key": f"project:{row.id}", "qty": 40},
                    {"key": f"retail:{retail.id}", "qty": 30},
                ],
            )],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        state = svc.planner_state(db, str(shipment.id), po_id)

        assert state["purchase_order_id"] == str(po_id)
        assert state["po_number"] == created["created_spos"][0]["po_number"]
        # Only this SPO's own line, never the whole shipment.
        assert len(state["lines"]) == 1
        ln = _state_line(state, str(lines[0].id))
        assert ln["spo_qty"] == 70
        assert sorted(
            (s["warehouse_id"], s["qty"]) for s in ln["location_splits"]
        ) == sorted([(str(wh_a.id), 40.0), (str(wh_b.id), 30.0)])
        assert {s["warehouse_code"] for s in ln["location_splits"]} == {
            wh_a.warehouse_code, wh_b.warehouse_code
        }
        assert ln["po_take_ids"] == [str(source_po.lines[0].id)]
        assert sorted((t["key"], t["qty"]) for t in ln["so_takes"]) == sorted([
            (f"project:{row.id}", 40.0), (f"retail:{retail.id}", 30.0)
        ])
        assert ln["received_qty"] == 0


def test_planner_state_hands_this_spos_own_claims_back_so_they_can_be_re_ticked():
    """The one thing a re-read of `suggest` cannot answer. `create` advanced the source PO
    line and netted the demand it was pointed at, so a straight `suggest` reads this SPO's
    own pull as taken and its own ticked demand as spent - the state on screen would be
    un-editable. `planner_state` subtracts THIS SPO's share back out."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        source_po = w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 20))

        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 100,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 100}],
                so_takes=[
                    {"key": f"project:{row.id}", "qty": 40},
                    {"key": f"retail:{retail.id}", "qty": 30},
                ],
            )],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        # What a plain `suggest` says now: nothing left, and every row taken.
        after = svc.suggest(db, str(shipment.id))
        spent = next(l for l in after["lines"] if l["shipment_line_id"] == str(lines[0].id))
        assert spent["remaining_qty"] == 0

        state = svc.planner_state(db, str(shipment.id), po_id)
        ln = _state_line(state, str(lines[0].id))

        # The whole 100 is editable again - this SPO's own 100 is not somebody else's claim.
        assert ln["remaining_qty"] == 100
        # The source PO line reads open again, and IS in the take list at its own id.
        take = next(t for t in ln["po_takes"] if t["po_line_id"] == str(source_po.lines[0].id))
        assert take["open_qty"] == 100
        assert take["taken_qty"] == 0
        # Both pieces of demand are offered at their FULL outstanding, and neither names
        # this SPO as having taken them.
        project = next(c for c in ln["so_coverage"] if c["key"] == f"project:{row.id}")
        assert project["qty"] == 40 and project["taken_by"] == []
        book = next(c for c in ln["so_coverage"] if c["key"] == f"retail:{retail.id}")
        assert book["qty"] == 30 and book["taken_by"] == []


def test_planner_state_reports_what_each_line_has_already_received():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        created = svc.create(
            db, str(shipment.id),
            [_confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}])],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]
        allocation = _allocations(db, po_id)[0]
        allocation.quantity_received = 50
        db.flush()

        state = svc.planner_state(db, str(shipment.id), po_id)

        assert _state_line(state, str(lines[0].id))["received_qty"] == 50


def test_planner_state_refuses_a_purchase_order_this_shipment_never_made():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        other = w.po("Z", supplier, [("A", 10, 0)])
        shipment, _lines = w.shipment([("A", 100, supplier)])

        with pytest.raises(AppException) as exc:
            svc.planner_state(db, str(shipment.id), str(other.id))
        assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# AC-K2 - Save updates rows in place, and the number never moves
# --------------------------------------------------------------------------- #


def test_revise_changes_qty_moves_a_split_adds_a_retail_take_and_drops_a_project_one():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh_a, wh_b = w.warehouse("A"), w.warehouse("B")
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        retail, _so = _retail_demand(db, w, "A", wh_b, qty=30, required=date(2026, 9, 20))

        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 70,
                location_splits=[
                    {"warehouse_id": str(wh_a.id), "qty": 40},
                    {"warehouse_id": str(wh_b.id), "qty": 30},
                ],
                so_takes=[{"key": f"project:{row.id}", "qty": 40}],
            )],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]
        po_number = created["created_spos"][0]["po_number"]

        svc.revise(
            db, str(shipment.id), po_id,
            [_confirm(
                lines[0], 90,
                # The wh_a slice moves to wh_b entirely: one row updated, one deleted.
                location_splits=[{"warehouse_id": str(wh_b.id), "qty": 90}],
                # The project tick goes; a retail one arrives.
                so_takes=[{"key": f"retail:{retail.id}", "qty": 30}],
            )],
        )
        db.flush()

        # The header row is UNTOUCHED: same id, same number.
        po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
        assert po.po_number == po_number

        # One SPO line, now at 90.
        po_lines = _po_lines(db, po_id)
        assert len(po_lines) == 1
        assert float(po_lines[0].qty_ordered) == 90

        # One allocation, at wh_b, holding the whole 90.
        allocations = _allocations(db, po_id)
        assert len(allocations) == 1
        assert str(allocations[0].warehouse_id) == str(wh_b.id)
        assert allocations[0].allocated_quantity == 90

        # The project link is gone; the retail claim exists at the new take.
        assert db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).count() == 0
        claim = (
            db.query(OrderLinkClaim)
            .filter(
                OrderLinkClaim.so_line_id == str(retail.id),
                OrderLinkClaim.source == "planner",
            )
            .one()
        )
        assert float(claim.qty) == 30

        # The shipment line's own allocated total follows.
        shipment_line = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.id == lines[0].id)
            .one()
        )
        assert shipment_line.spo_allocated_quantity == 90


def test_revise_re_deals_the_pull_on_the_source_purchase_order_line():
    """`create` advances the source line's `qty_received` by what it pulled; a revision has
    to un-advance the old pull and advance the new one, or the source PO stays short by a
    quantity no SPO claims any more."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        source_po = w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])

        created = svc.create(
            db, str(shipment.id),
            [_confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}])],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]
        source_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.id == source_po.lines[0].id
        ).one()
        assert float(source_line.qty_received) == 70

        svc.revise(
            db, str(shipment.id), po_id,
            [_confirm(lines[0], 30, location_splits=[{"warehouse_id": str(wh.id), "qty": 30}])],
        )
        db.flush()
        db.refresh(source_line)

        assert float(source_line.qty_received) == 30
        po_line = _po_lines(db, po_id)[0]
        assert [q for _id, q in svc.parse_source_ref(po_line.source_ref)["pulls"]] == [30.0]


def test_a_planner_state_round_trip_saved_unchanged_writes_no_row_difference():
    """The safety net under every edit: opening an SPO and pressing Save without touching
    anything leaves the database exactly where it was."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh_a, wh_b = w.warehouse("A"), w.warehouse("B")
        source_po = w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        retail, _so = _retail_demand(db, w, "A", wh_b, qty=30, required=date(2026, 9, 20))

        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 70,
                location_splits=[
                    {"warehouse_id": str(wh_a.id), "qty": 40},
                    {"warehouse_id": str(wh_b.id), "qty": 30},
                ],
                so_takes=[
                    {"key": f"project:{row.id}", "qty": 40},
                    {"key": f"retail:{retail.id}", "qty": 30},
                ],
            )],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        def snapshot():
            return {
                "po_lines": sorted(
                    (float(pl.qty_ordered), svc.parse_source_ref(pl.source_ref)["pulls"])
                    for pl in _po_lines(db, po_id)
                ),
                "allocations": sorted(
                    (str(a.warehouse_id), a.allocated_quantity) for a in _allocations(db, po_id)
                ),
                "links": sorted(
                    (str(l.row_id), float(l.qty))
                    for l in db.query(OrderInquiryLink)
                    .filter(OrderInquiryLink.row_id == row.id)
                    .all()
                ),
                "claims": sorted(
                    (str(c.so_line_id), float(c.qty or 0))
                    for c in db.query(OrderLinkClaim)
                    .filter(OrderLinkClaim.source == "planner")
                    .all()
                ),
                "source_received": float(
                    db.query(PurchaseOrderLine)
                    .filter(PurchaseOrderLine.id == source_po.lines[0].id)
                    .one()
                    .qty_received
                ),
            }

        before = snapshot()

        state = svc.planner_state(db, str(shipment.id), po_id)
        ln = _state_line(state, str(lines[0].id))
        svc.revise(
            db, str(shipment.id), po_id,
            [{
                "shipment_line_id": ln["shipment_line_id"],
                "qty": ln["spo_qty"],
                "include": True,
                "location_splits": [
                    {"warehouse_id": s["warehouse_id"], "qty": s["qty"]}
                    for s in ln["location_splits"]
                ],
                "po_take_ids": ln["po_take_ids"],
                "so_takes": ln["so_takes"],
            }],
        )
        db.flush()
        db.expire_all()

        assert snapshot() == before


# --------------------------------------------------------------------------- #
# AC-K3 - a received row cannot be dropped below what arrived, and a refusal
#         writes NOTHING
# --------------------------------------------------------------------------- #


def test_a_qty_below_what_was_received_is_refused_naming_the_product_and_warehouse():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        created = svc.create(
            db, str(shipment.id),
            [_confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}])],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]
        _allocations(db, po_id)[0].quantity_received = 50
        db.flush()

        with pytest.raises(AppException) as exc:
            svc.revise(
                db, str(shipment.id), po_id,
                [_confirm(lines[0], 20, location_splits=[{"warehouse_id": str(wh.id), "qty": 20}])],
            )

        assert exc.value.status_code == 422
        said = str(exc.value.detail)
        assert w.product("A").product_code in said
        assert wh.warehouse_code in said


def test_a_refused_revision_writes_nothing_not_even_the_valid_line_beside_it():
    """Two lines in one body: one drops below what it received, the other is a perfectly
    good change. The refusal is for the whole save, so the good line must be untouched
    too - a half-applied SPO is worse than a refused one."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        w.po("B", supplier, [("B", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier), ("B", 100, supplier)])
        created = svc.create(
            db, str(shipment.id),
            [
                _confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}]),
                _confirm(lines[1], 60, location_splits=[{"warehouse_id": str(wh.id), "qty": 60}]),
            ],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]
        received_on = next(
            a for a in _allocations(db, po_id) if str(a.product_id) == str(w.product("A").id)
        )
        received_on.quantity_received = 50
        db.flush()

        with pytest.raises(AppException) as exc:
            svc.revise(
                db, str(shipment.id), po_id,
                [
                    # The refusal.
                    _confirm(lines[0], 20, location_splits=[{"warehouse_id": str(wh.id), "qty": 20}]),
                    # A change that would otherwise have landed.
                    _confirm(lines[1], 90, location_splits=[{"warehouse_id": str(wh.id), "qty": 90}]),
                ],
            )
        assert exc.value.status_code == 422
        db.expire_all()

        by_product = {str(pl.product_id): float(pl.qty_ordered) for pl in _po_lines(db, po_id)}
        assert by_product[str(w.product("A").id)] == 70
        assert by_product[str(w.product("B").id)] == 60
        allocated = {
            str(a.product_id): a.allocated_quantity for a in _allocations(db, po_id)
        }
        assert allocated[str(w.product("B").id)] == 60


def test_dropping_a_received_line_entirely_is_refused_too():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        created = svc.create(
            db, str(shipment.id),
            [_confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}])],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]
        _allocations(db, po_id)[0].quantity_received = 10
        db.flush()

        with pytest.raises(AppException) as exc:
            svc.revise(db, str(shipment.id), po_id, [])
        assert exc.value.status_code == 422
        assert len(_po_lines(db, po_id)) == 1


# --------------------------------------------------------------------------- #
# AC-K4 - a line removed is unwound for that line only
# --------------------------------------------------------------------------- #


def test_removing_one_line_unwinds_only_its_own_rows_and_links():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        source_a = w.po("A", supplier, [("A", 100, 0)])
        w.po("B", supplier, [("B", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier), ("B", 100, supplier)])
        row_a, _pso_a = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        row_b, _pso_b = _project_chain(db, w, "B", qty=25, delivery=date(2026, 9, 12))

        created = svc.create(
            db, str(shipment.id),
            [
                _confirm(
                    lines[0], 70,
                    location_splits=[{"warehouse_id": str(wh.id), "qty": 70}],
                    so_takes=[{"key": f"project:{row_a.id}", "qty": 40}],
                ),
                _confirm(
                    lines[1], 60,
                    location_splits=[{"warehouse_id": str(wh.id), "qty": 60}],
                    so_takes=[{"key": f"project:{row_b.id}", "qty": 25}],
                ),
            ],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        out = svc.revise(
            db, str(shipment.id), po_id,
            [
                # Line A goes.
                {"shipment_line_id": str(lines[0].id), "qty": 0, "include": False},
                _confirm(
                    lines[1], 60,
                    location_splits=[{"warehouse_id": str(wh.id), "qty": 60}],
                    so_takes=[{"key": f"project:{row_b.id}", "qty": 25}],
                ),
            ],
        )
        db.flush()
        db.expire_all()

        assert out["removed_line_count"] == 1

        # Only B's line survives, with its allocation and its link.
        po_lines = _po_lines(db, po_id)
        assert [str(pl.product_id) for pl in po_lines] == [str(w.product("B").id)]
        assert [str(a.product_id) for a in _allocations(db, po_id)] == [str(w.product("B").id)]
        assert db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_a.id).count() == 0
        assert db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_b.id).count() == 1

        # A's own matched link row is gone, B's is not.
        matched = (
            db.query(ShipmentLineSpoLink)
            .filter(
                ShipmentLineSpoLink.purchase_order_id == po_id,
                ShipmentLineSpoLink.inbound_shipment_line_id.in_(
                    [str(lines[0].id), str(lines[1].id)]
                ),
            )
            .all()
        )
        assert [str(l.inbound_shipment_line_id) for l in matched] == [str(lines[1].id)]

        # A's pull is handed back to the source purchase order.
        source_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.id == source_a.lines[0].id
        ).one()
        assert float(source_line.qty_received) == 0

        # And the shipment line reads unconverted again, so the planner offers it afresh.
        after = svc.suggest(db, str(shipment.id))
        freed = next(l for l in after["lines"] if l["shipment_line_id"] == str(lines[0].id))
        assert freed["remaining_qty"] == 100


def test_an_empty_revision_that_would_leave_no_line_at_all_is_refused():
    """Deleting the SPO is Delete's job, and it mints no new number to replace this one -
    an SPO header with no lines is a document that says nothing."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        created = svc.create(
            db, str(shipment.id),
            [_confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}])],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        with pytest.raises(AppException) as exc:
            svc.revise(
                db, str(shipment.id), po_id,
                [{"shipment_line_id": str(lines[0].id), "qty": 0, "include": False}],
            )
        assert exc.value.status_code == 422
        assert len(_po_lines(db, po_id)) == 1


def test_a_line_that_is_not_on_this_spo_cannot_be_added_through_a_revision():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        w.po("B", supplier, [("B", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier), ("B", 100, supplier)])
        created = svc.create(
            db, str(shipment.id),
            [
                _confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}]),
                {"shipment_line_id": str(lines[1].id), "qty": 0, "include": False},
            ],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        with pytest.raises(AppException) as exc:
            svc.revise(
                db, str(shipment.id), po_id,
                [
                    _confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}]),
                    _confirm(lines[1], 50, location_splits=[{"warehouse_id": str(wh.id), "qty": 50}]),
                ],
            )
        assert exc.value.status_code == 422


def test_revise_refuses_a_purchase_order_create_spo_did_not_mint():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        created = svc.create(
            db, str(shipment.id),
            [_confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}])],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]
        db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one().source_system = "scm_upload"
        db.flush()

        with pytest.raises(AppException) as exc:
            svc.revise(
                db, str(shipment.id), po_id,
                [_confirm(lines[0], 50, location_splits=[{"warehouse_id": str(wh.id), "qty": 50}])],
            )
        assert exc.value.status_code == 409


# --------------------------------------------------------------------------- #
# the guards `create` already applies still apply
# --------------------------------------------------------------------------- #


def test_a_split_that_does_not_add_up_is_refused_the_same_way_create_refuses_it():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        created = svc.create(
            db, str(shipment.id),
            [_confirm(lines[0], 70, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}])],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        with pytest.raises(AppException) as exc:
            svc.revise(
                db, str(shipment.id), po_id,
                [_confirm(lines[0], 80, location_splits=[{"warehouse_id": str(wh.id), "qty": 70}])],
            )
        assert exc.value.status_code == 422


def test_a_take_above_the_rows_own_outstanding_is_still_refused_on_a_revision():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))
        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 70,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 70}],
                so_takes=[{"key": f"retail:{retail.id}", "qty": 30}],
            )],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        with pytest.raises(AppException) as exc:
            svc.revise(
                db, str(shipment.id), po_id,
                [_confirm(
                    lines[0], 70,
                    location_splits=[{"warehouse_id": str(wh.id), "qty": 70}],
                    # 999 against a row that only ever needed 30 - even counting this SPO's
                    # own 30 back in.
                    so_takes=[{"key": f"retail:{retail.id}", "qty": 999}],
                )],
            )
        assert exc.value.status_code == 422


def test_a_take_this_spo_already_holds_is_not_refused_as_taken_by_somebody_else():
    """The trap the "hand our own claims back" rule exists for: re-saving the SAME retail
    take must not read as asking for 30 out of a row with 0 outstanding."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))
        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 70,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 70}],
                so_takes=[{"key": f"retail:{retail.id}", "qty": 30}],
            )],
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        svc.revise(
            db, str(shipment.id), po_id,
            [_confirm(
                lines[0], 70,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 70}],
                so_takes=[{"key": f"retail:{retail.id}", "qty": 30}],
            )],
        )
        db.flush()

        claims = (
            db.query(OrderLinkClaim)
            .filter(
                OrderLinkClaim.so_line_id == str(retail.id),
                OrderLinkClaim.source == "planner",
            )
            .all()
        )
        assert len(claims) == 1
        assert float(claims[0].qty) == 30


# --------------------------------------------------------------------------- #
# the routes (AC-K1, AC-K2) - the shapes the planner actually sends and reads
# --------------------------------------------------------------------------- #


def test_the_routes_read_the_state_and_save_a_revision(scm_app):
    """`response_model` is deliberately absent on both, the same as every other route in
    this module: the dicts the service builds ARE the answer. Asserted end to end anyway,
    because a field the screen seeds a row from is a field a silent drop would empty."""
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    supplier = w.supplier()
    wh_a, wh_b = w.warehouse("A"), w.warehouse("B")
    w.po("A", supplier, [("A", 100, 0)])
    shipment, lines = w.shipment([("A", 100, supplier)])
    row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

    client = TestClient(app)
    created = client.post(
        f"/api/v1/scm/inbound-shipments/{shipment.id}/spo",
        json={
            "lines": [
                {
                    "shipment_line_id": str(lines[0].id),
                    "qty": 70,
                    "include": True,
                    "location_splits": [{"warehouse_id": str(wh_a.id), "qty": 70}],
                    "so_takes": [{"key": f"project:{row.id}", "qty": 40}],
                }
            ]
        },
    )
    assert created.status_code == 201, created.text
    po_id = created.json()["created_spos"][0]["purchase_order_id"]
    po_number = created.json()["created_spos"][0]["po_number"]

    state = client.get(
        f"/api/v1/scm/inbound-shipments/{shipment.id}/spo/{po_id}/planner-state"
    )
    assert state.status_code == 200, state.text
    body = state.json()
    assert body["po_number"] == po_number
    ln = body["lines"][0]
    assert ln["spo_qty"] == 70
    assert ln["received_qty"] == 0
    assert [s["warehouse_id"] for s in ln["location_splits"]] == [str(wh_a.id)]
    assert ln["so_takes"] == [{"key": f"project:{row.id}", "qty": 40}]
    assert ln["po_takes"] and ln["so_coverage"] and ln["location_options"]

    saved = client.put(
        f"/api/v1/scm/inbound-shipments/{shipment.id}/spo/{po_id}",
        json={
            "lines": [
                {
                    "shipment_line_id": str(lines[0].id),
                    "qty": 90,
                    "include": True,
                    "location_splits": [{"warehouse_id": str(wh_b.id), "qty": 90}],
                    "so_takes": [{"key": f"project:{row.id}", "qty": 40}],
                }
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["po_number"] == po_number
    assert saved.json()["removed_line_count"] == 0

    reopened = client.get(
        f"/api/v1/scm/inbound-shipments/{shipment.id}/spo/{po_id}/planner-state"
    ).json()["lines"][0]
    assert reopened["spo_qty"] == 90
    assert [s["warehouse_id"] for s in reopened["location_splits"]] == [str(wh_b.id)]


def test_the_planner_state_route_is_404_for_an_spo_this_shipment_never_made(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    supplier = w.supplier()
    other = w.po("Z", supplier, [("A", 10, 0)])
    shipment, _lines = w.shipment([("A", 100, supplier)])

    client = TestClient(app)
    out = client.get(
        f"/api/v1/scm/inbound-shipments/{shipment.id}/spo/{other.id}/planner-state"
    )
    assert out.status_code == 404, out.text
