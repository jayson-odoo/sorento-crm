"""S9 second half - "Create SPO" (`app/services/scm/spo_conversion_service.py`,
`PLAN-scm-proforma-to-spo.md`'s Amendment, second decision).

Traces to the module docstring's own contract:
  * `suggest` - packed qty, netted by an open PO to the SAME supplier (product match, or
    PINNED by a po_ref carried through the PI provenance link), then by on-hand + incoming
    SPO, floored at 0. Covered and no-supplier lines stay visible with a reason.
  * `create` - one CRM `purchase_orders` header per supplier represented on the shipment,
    `source_system='crm_spo'`, its own `CRM-SPO-` number series, `shipment_line_spo_link`
    rows for both the matched and the skipped lines. A second attempt is refused (409),
    naming the SPOs already made.
  * Visibility - the new lines count as ORDERED (`scm.po_ordered_v`, no source predicate)
    immediately, and are deliberately absent from `scm.on_order_v` (spo_allocations only)
    until someone allocates them - same split pinned by `test_reorder_nets_po_ordered.py`.

Postgres only, marker-prefixed, every test seeds its own chain (CI's database is empty).
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoiceShipmentLink, ShipmentLineSpoLink
from app.services.error_handler import AppException
from app.services.scm import spo_conversion_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZSPOC"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _u() -> str:
    return str(uuid.uuid4())


class World:
    """Same shape as `test_allocation_suggestion.World` - one shared cat/uom, products and
    warehouses created lazily and cached by key, everything marker-prefixed."""

    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:8].upper()
        self.tag = tag
        cat = ProductCategory(
            id=_u(), category_code=f"{MARKER}-C-{tag}", category_name=f"{MARKER} cat"
        )
        uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs")
        db.add_all([cat, uom])
        db.flush()
        self.cat, self.uom = cat, uom
        self.products: dict[str, Product] = {}
        self.warehouses: dict[str, Warehouse] = {}
        self.suppliers: dict[str, Supplier] = {}

    def supplier(self, key: str = "S") -> Supplier:
        if key not in self.suppliers:
            s = Supplier(
                id=_u(), supplier_code=f"{MARKER}-{key}-{self.tag}",
                supplier_name=f"{MARKER} {key} supplier", is_active=True,
            )
            self.db.add(s)
            self.db.flush()
            self.suppliers[key] = s
        return self.suppliers[key]

    def product(self, key: str) -> Product:
        if key not in self.products:
            p = Product(
                id=_u(), product_code=f"{MARKER}-{key}-{self.tag}", product_name=key,
                category_id=self.cat.id, base_uom_id=self.uom.id, list_price=0,
                is_active=True, is_discontinued=False,
            )
            self.db.add(p)
            self.db.flush()
            self.products[key] = p
        return self.products[key]

    def warehouse(self, key: str = "WH") -> Warehouse:
        if key not in self.warehouses:
            w = Warehouse(
                id=_u(), warehouse_code=f"{MARKER}-{key}-{self.tag}"[:50],
                warehouse_name=key, is_active=True,
            )
            self.db.add(w)
            self.db.flush()
            self.warehouses[key] = w
        return self.warehouses[key]

    def po(self, suffix: str, supplier: Supplier, lines, *, issue_date=date(2026, 1, 1), status="active"):
        po = PurchaseOrder(
            id=_u(), po_number=f"{MARKER}-PO{suffix}-{self.tag}",
            supplier_id=supplier.id, issue_date=issue_date, status=status,
        )
        self.db.add(po)
        self.db.flush()
        for key, qty_ordered, qty_received in lines:
            self.db.add(PurchaseOrderLine(
                id=_u(), purchase_order_id=po.id, product_id=self.product(key).id,
                qty_ordered=qty_ordered, qty_received=qty_received, line_status="open",
            ))
        self.db.flush()
        return po

    def shipment(self, lines, *, supplier: Supplier | None = None, status="in_transit"):
        """`lines` is `[(key, qty, supplier_or_None)]` - per-line supplier, mirroring how a
        real container carries several factories."""
        s = InboundShipment(
            id=_u(), shipment_number=f"{MARKER}-SH-{self.tag}-{uuid.uuid4().hex[:6]}",
            supplier_id=supplier.id if supplier else None,
            shipment_date=date(2026, 8, 1), shipment_status=status,
        )
        self.db.add(s)
        self.db.flush()
        made = []
        for key, qty, line_supplier in lines:
            ln = InboundShipmentLine(
                id=_u(), shipment_id=s.id, product_id=self.product(key).id,
                supplier_id=line_supplier.id if line_supplier else None,
                quantity_shipped=qty, unit_cost=10, currency="USD",
            )
            self.db.add(ln)
            made.append(ln)
        self.db.flush()
        return s, made

    def stock(self, key: str, wh: Warehouse, qty: int) -> None:
        self.db.execute(text(
            "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
            "synced_to_excel, created_at, updated_at) "
            "VALUES (:id, :p, :w, :q, false, now(), now())"
        ), {"id": _u(), "p": self.product(key).id, "w": wh.id, "q": qty})

    def spo_allocation(self, key: str, shipment: InboundShipment, wh: Warehouse, qty: int) -> None:
        self.db.add(SPOAllocation(
            id=_u(), inbound_shipment_id=shipment.id, warehouse_id=wh.id,
            product_id=self.product(key).id, allocated_quantity=qty,
            receipt_status="pending", quantity_received=0,
        ))
        self.db.flush()

    def pi_po_ref(self, shipment_line: InboundShipmentLine, po_ref: str) -> None:
        """The PI provenance link `_po_refs_for_line` reads: a PI line naming `po_ref`,
        linked to this shipment line via `ProformaInvoiceShipmentLink` (migration 405)."""
        supplier_id = shipment_line.supplier_id
        pi = ProformaInvoice(
            id=_u(), supplier_id=supplier_id, pi_number=f"{MARKER}-PI-{uuid.uuid4().hex[:6]}",
            currency="USD",
        )
        self.db.add(pi)
        self.db.flush()
        pi_line = ProformaInvoiceLine(
            id=_u(), invoice_id=pi.id, line_no=1, item_code=f"{MARKER}-ITEM",
            qty=shipment_line.quantity_shipped, po_ref=po_ref,
            product_id=shipment_line.product_id,
        )
        self.db.add(pi_line)
        self.db.flush()
        self.db.add(ProformaInvoiceShipmentLink(
            id=_u(), proforma_invoice_id=pi.id, proforma_invoice_line_id=pi_line.id,
            inbound_shipment_id=shipment_line.shipment_id,
            inbound_shipment_line_id=shipment_line.id,
        ))
        self.db.flush()


def _line(out: dict, shipment_line_id: str) -> dict:
    for ln in out["lines"]:
        if ln["shipment_line_id"] == shipment_line_id:
            return ln
    raise AssertionError(f"no line {shipment_line_id} in suggestion output")


# --------------------------------------------------------------------------- #
# suggest
# --------------------------------------------------------------------------- #


def test_suggest_with_no_open_po_at_all_cannot_convert_and_names_why():
    """DOCTRINE CORRECTION (captain, 21 Aug): "when there is PO, then we only can do SPO...
    it is when we got PO, then we only can pull from the PO to form SPO." A packed line with
    NO open PO behind it has nothing to pull from, so it cannot become an SPO line at all -
    the opposite of the pre-correction behaviour, where an absent PO meant "ask for the full
    packed qty". `packed_qty` still reports the PACKED figure (`quantity_shipped`, never the
    PI's invoiced one - the Amendment's own correction, still true), just no PO exists here to
    seed anything to pull."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        shipment, lines = w.shipment([("A", 120, supplier)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["packed_qty"] == 120
        assert line["po_covered_qty"] == 0
        assert line["suggested_qty"] == 0
        assert line["no_po_qty"] == 120
        assert line["cannot_convert"] is True
        assert line["reason"] == svc._REASON_NO_PO


def test_an_open_po_line_to_the_same_supplier_forms_the_suggested_qty():
    """Product-match candidate: no po_ref anywhere, so the open PO to the SAME supplier for
    the SAME product is what the SPO PULLS - the doctrine correction's own arithmetic
    (`suggested_qty = po_covered_qty`, never a deduction). Packed (100) exceeds what the PO
    can back (40), so the line stays selectable at 40 and the uncovered 60 is named, not
    hidden."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["po_covered_qty"] == 40
        assert line["matched_by"] == "product"
        assert line["suggested_qty"] == 40
        assert line["no_po_qty"] == 60
        assert line["cannot_convert"] is False
        assert "no PO to pull from" in line["reason"]


def test_a_po_ref_from_pi_provenance_pins_the_match_over_a_product_only_candidate():
    """The plan's own rule: "a stated po_ref outranks inference". PO-PIN carries the po_ref
    the PI line stated (small, 15 open); PO-BIG is a product-only candidate that would win on
    quantity/earliest-issued alone (90 open) if the pin were not honoured. The suggestion must
    pull against PO-PIN ONLY - 15, not 90, and must NOT sum the two."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        pinned = w.po("PIN", supplier, [("A", 15, 0)], issue_date=date(2025, 1, 1))
        w.po("BIG", supplier, [("A", 90, 0)], issue_date=date(2024, 1, 1))
        shipment, lines = w.shipment([("A", 100, supplier)])
        w.pi_po_ref(lines[0], pinned.po_number)

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["matched_by"] == "po_ref"
        assert line["matched_po_number"] == pinned.po_number
        assert line["po_covered_qty"] == 15, "must be the PINNED PO's own quantity, not summed with the bigger candidate"
        assert line["suggested_qty"] == 15
        assert line["no_po_qty"] == 85


def test_a_po_ref_pin_still_matches_when_the_book_supplier_is_spelled_differently():
    """DB evidence, live case (captain, 21 Aug): PI line SRTWT7443 states po_ref
    202605-S0060, an open PO with 1,880 open - booked under the importer's own name-squashed
    KAILU identity, while the shipment line itself carries the PI's own 400-J006 supplier
    code. `_pinned_po_candidates` must trust the STATED document regardless of supplier
    spelling - the module's own rule, "a stated po_ref outranks inference". An ample PO fully
    backs the packed qty, so the whole 100 is pulled (not zero - the doctrine correction means
    ample PO backing ENABLES the full ask, it does not zero it out)."""
    with pg_session() as db:
        w = World(db)
        book_supplier = w.supplier("KAILU")
        shipment_supplier = w.supplier("J006")
        pinned = w.po("PIN", book_supplier, [("A", 1880, 0)])
        shipment, lines = w.shipment([("A", 100, shipment_supplier)])
        w.pi_po_ref(lines[0], pinned.po_number)

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["matched_by"] == "po_ref"
        assert line["matched_po_number"] == pinned.po_number
        assert line["po_covered_qty"] == 100, "capped at packed, not the PO's full 1,880"
        assert line["suggested_qty"] == 100
        assert line["no_po_qty"] == 0
        assert line["cannot_convert"] is False


def test_the_inference_path_still_refuses_a_cross_supplier_po_with_no_stated_ref():
    """No po_ref at all - the UN-pinned (product-match) path must still refuse a PO booked
    under a different supplier, or the pin fix above would silently widen inference too. With
    nothing pullable at all, the line is `cannot_convert` (doctrine correction) rather than
    offered at the full packed qty."""
    with pg_session() as db:
        w = World(db)
        book_supplier = w.supplier("KAILU")
        shipment_supplier = w.supplier("J006")
        w.po("OTHER", book_supplier, [("A", 500, 0)])
        shipment, lines = w.shipment([("A", 100, shipment_supplier)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["matched_by"] is None
        assert line["po_covered_qty"] == 0
        assert line["suggested_qty"] == 0
        assert line["cannot_convert"] is True


def test_on_hand_and_incoming_spo_are_context_only_and_do_not_net_the_suggested_qty():
    """DOCTRINE CORRECTION: stock/incoming netting DISAPPEARS from the SPO arithmetic - kept
    on the response as context (cheap), never subtracted. An open PO backs 60 of the 100
    packed; on_hand (20) and incoming_spo (15) are reported unchanged but do NOT reduce the
    60 pulled from the PO (the pre-correction formula would have read 100-60-20-15=5)."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("1", supplier, [("A", 60, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        w.stock("A", wh, 20)
        w.spo_allocation("A", shipment, wh, 15)

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["on_hand"] == 20
        assert line["incoming_spo"] == 15
        assert line["po_covered_qty"] == 60
        assert line["suggested_qty"] == 60, "on_hand/incoming_spo must not reduce this"


def test_an_ample_po_caps_the_suggested_qty_at_packed_not_beyond_it():
    """An open PO far bigger than the packed quantity (500 available, 100 packed) does not
    push `po_covered_qty` past what shipped - the cascade's own `need = packed` cap, verified
    directly rather than assumed. Fully selectable, nothing uncovered."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 500, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["po_covered_qty"] == 100
        assert line["suggested_qty"] == 100
        assert line["no_po_qty"] == 0
        assert line["cannot_convert"] is False
        assert line["reason"] is None


def test_a_line_with_no_supplier_cannot_convert_and_carries_its_reason():
    """The n8n PDF path: a container line with an unattributed factory."""
    with pg_session() as db:
        w = World(db)
        shipment, lines = w.shipment([("A", 50, None)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["cannot_convert"] is True
        assert line["supplier_id"] is None
        assert "no supplier" in line["reason"].lower()
        assert line["suggested_qty"] == 0


def test_suggest_on_an_unknown_shipment_is_a_404():
    with pg_session() as db:
        with pytest.raises(AppException) as exc:
            svc.suggest(db, str(uuid.uuid4()))
        assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #


def _confirm_all(shipment_lines, *, include_ids: set[str] | None = None) -> list[dict]:
    """Every line accounted for, per the route's own contract - `include_ids=None` means
    include every line at its full packed qty."""
    out = []
    for ln in shipment_lines:
        include = include_ids is None or str(ln.id) in include_ids
        out.append({
            "shipment_line_id": str(ln.id),
            "qty": float(ln.quantity_shipped) if include else 0,
            "include": include,
        })
    return out


def test_create_writes_one_spo_header_per_supplier_on_a_multi_supplier_shipment():
    """DOCTRINE CORRECTION: `create` now only writes an SPO line for a product it can pull
    from an open PO, so both suppliers need one seeded (previously this test needed no PO at
    all - an absent PO used to mean "ask for the full packed qty")."""
    with pg_session() as db:
        w = World(db)
        jiangmen = w.supplier("JIANGMEN")
        kailu = w.supplier("KAILU")
        w.po("A", jiangmen, [("A", 50, 0)])
        w.po("B", kailu, [("B", 30, 0)])
        shipment, lines = w.shipment([
            ("A", 50, jiangmen),
            ("B", 30, kailu),
        ])

        out = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        assert len(out["created_spos"]) == 2
        supplier_ids = {s["supplier_id"] for s in out["created_spos"]}
        assert supplier_ids == {str(jiangmen.id), str(kailu.id)}
        assert not out["skipped"]


def test_create_marks_source_system_crm_spo_and_records_the_pull():
    """DOCTRINE CORRECTION: needs a seeded open PO (see the test above). Also locks down the
    "honest" recording decision the plan asked to settle: the pull ADVANCES the source PO
    line's own `qty_received` (mirroring `allocation_suggestion_service.approve`'s identical
    write) rather than only linking, and the new CRM SPO line's `source_ref` carries WHICH
    source PO line(s) it pulled from, as JSON - see the module docstring's fifth amendment."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        source_po = w.po("1", supplier, [("A", 40, 0)])
        source_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == source_po.id
        ).one()
        shipment, lines = w.shipment([("A", 40, supplier)])

        out = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        po_id = out["created_spos"][0]["purchase_order_id"]
        po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one()
        assert po.source_system == svc.SOURCE_SYSTEM == "crm_spo"
        assert po.status == "active"
        assert po.po_number.startswith("CRM-SPO-"), po.po_number
        po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po.id
        ).one()
        assert po_line.source_system == "crm_spo"
        assert po_line.line_status == "open"
        assert float(po_line.qty_ordered) == 40

        pulls = json.loads(po_line.source_ref)
        assert pulls == [{"po_line_id": str(source_line.id), "qty": 40.0}]
        db.refresh(source_line)
        assert float(source_line.qty_received) == 40, "the source PO line's own accounting must advance"


def test_create_writes_shipment_line_spo_link_rows_for_matched_and_skipped_lines():
    """DOCTRINE CORRECTION: line A now needs a seeded PO to be pullable at all - it is the
    INCLUDED line here, so without one this create would produce nothing to match."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        # A: included, backed by an open PO. B: deliberately left unticked, so the "every
        # line accounted for" contract is exercised on both outcomes in one create. C: ALSO
        # ticked (doctrine correction, new outcome) but backed by no PO at all - re-checked
        # at write time, never trusted off `suggest`'s earlier read.
        shipment, lines = w.shipment([("A", 40, supplier), ("B", 10, supplier), ("C", 5, supplier)])
        include_ids = {str(lines[0].id), str(lines[2].id)}

        svc.create(db, str(shipment.id), _confirm_all(lines, include_ids=include_ids), actor="tester")

        links = {
            str(l.inbound_shipment_line_id): l
            for l in db.query(ShipmentLineSpoLink).filter(
                ShipmentLineSpoLink.inbound_shipment_id == shipment.id
            ).all()
        }
        assert len(links) == 3
        matched = links[str(lines[0].id)]
        assert matched.purchase_order_line_id is not None
        assert matched.unmatched_reason is None
        not_selected = links[str(lines[1].id)]
        assert not_selected.purchase_order_line_id is None
        assert not_selected.unmatched_reason == svc._REASON_NOT_SELECTED
        no_po = links[str(lines[2].id)]
        assert no_po.purchase_order_line_id is None
        assert no_po.unmatched_reason == svc._REASON_NO_PO


def test_create_refuses_when_nothing_ticked_has_a_po_behind_it():
    """DOCTRINE CORRECTION, new outcome: a ticked line with no open PO behind it is skipped
    at write time too (never trusted off `suggest`'s earlier read) - same shape as the
    no-supplier skip, which already made a shipment with nothing groupable a 422 rather than
    an empty success (`test_route_create_spo_all_unconvertible_no_supplier_is_422`)."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        shipment, lines = w.shipment([("A", 40, supplier)])

        with pytest.raises(AppException) as exc:
            svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        assert exc.value.status_code == 422
        assert exc.value.detail["detail"] == "nothing_selected"


def test_a_second_create_is_refused_409_naming_the_existing_spo():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 40, supplier)])

        first = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
        first_number = first["created_spos"][0]["po_number"]

        with pytest.raises(AppException) as exc:
            svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        assert exc.value.status_code == 409
        assert first_number in str(exc.value.message if hasattr(exc.value, "message") else exc.value.detail or exc.value)
        # suggest() must also report it as already converted, not re-offer a confirm screen.
        again = svc.suggest(db, str(shipment.id))
        assert again["already_converted"] is True
        assert again["existing_spos"][0]["po_number"] == first_number


def test_draft_shipment_converts_too():
    """A container never packing-listed for real, drafted from a PI, still runs through
    Create SPO on its own packed figures - pulled from an open PO (doctrine correction, so a
    PO is seeded here where the pre-correction version needed none)."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 25, 0)])
        shipment, lines = w.shipment([("A", 25, supplier)], status="draft")

        suggestion = svc.suggest(db, str(shipment.id))
        assert suggestion["shipment_status"] == "draft"
        assert suggestion["lines"][0]["suggested_qty"] == 25

        out = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
        assert len(out["created_spos"]) == 1


# --------------------------------------------------------------------------- #
# visibility - po_ordered_v vs on_order_v (test_reorder_nets_po_ordered.py's split)
# --------------------------------------------------------------------------- #


def test_created_spo_lines_appear_in_po_ordered_v_immediately():
    """`scm.po_ordered_v` reads `purchase_order_lines` by status/line_status only - no
    `source_system` predicate - so a freshly created CRM SPO counts as ordered at once.

    DOCTRINE CORRECTION: `create` now needs an open PO to pull from (seeded here, sized to
    exactly the packed qty), and the pull ADVANCES that source line's own accounting - so the
    total across BOTH lines (source, now fully advanced; new CRM SPO line, freshly ordered)
    stays 40, byte-identical to what a bare new line alone used to read pre-correction. The
    conversion re-attributes an existing order to its shipment; it does not conjure a second."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 40, supplier)])
        product_id = str(lines[0].product_id)

        svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        row = db.execute(text(
            "SELECT ordered FROM scm.po_ordered_v WHERE product_id = :p"
        ), {"p": product_id}).mappings().first()
        assert row is not None, "the new SPO line must be visible in po_ordered_v"
        assert float(row["ordered"]) == 40


def test_created_spo_lines_are_absent_from_on_order_v_until_allocated():
    """`scm.on_order_v` reads `spo_allocations` exclusively - a CRM SPO with no allocation
    yet must NOT count as incoming, even though it is already ORDERED (previous test).

    DOCTRINE CORRECTION: needs a seeded open PO to pull from (see the previous test)."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 40, supplier)])
        product_id = str(lines[0].product_id)

        svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        row = db.execute(text(
            "SELECT on_order FROM scm.on_order_v WHERE product_id = :p"
        ), {"p": product_id}).mappings().first()
        assert row is None, "on_order_v must stay silent about a CRM SPO with no allocation"


# --------------------------------------------------------------------------- #
# unwind (delete) + self-heal - third amendment, captain live case 21 Aug
# --------------------------------------------------------------------------- #


def test_unwind_deletes_po_lines_headers_links_and_allocations_then_suggest_recovers():
    """DOCTRINE CORRECTION: needs a seeded open PO to pull from, and `unwind` must REVERSE
    the `qty_received` advance `create` made on it - the fifth amendment's own reversibility
    half, verified directly - or the source line stays permanently short with nothing left to
    explain where its 40 went."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        source_po = w.po("1", supplier, [("A", 40, 0)])
        source_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == source_po.id
        ).one()
        shipment, lines = w.shipment([("A", 40, supplier)])

        created = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
        po_id = created["created_spos"][0]["purchase_order_id"]
        po_number = created["created_spos"][0]["po_number"]
        po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po_id
        ).one()
        db.refresh(source_line)
        assert float(source_line.qty_received) == 40, "sanity: the pull must have advanced it"
        # An allocation hanging off the created PO line - the state `unwind` must clean up
        # itself (the FK there is SET NULL, not CASCADE), not just leave orphaned once the
        # PO line under it is gone.
        db.add(SPOAllocation(
            id=_u(), inbound_shipment_id=shipment.id, warehouse_id=wh.id,
            product_id=lines[0].product_id, allocated_quantity=40,
            receipt_status="pending", quantity_received=0, po_line_id=po_line.id,
        ))
        db.flush()

        out = svc.unwind(db, str(shipment.id))

        assert out["deleted_spo_count"] == 1
        assert out["deleted_po_numbers"] == [po_number]
        assert out["deleted_allocation_count"] == 1
        assert out["restored_po_line_count"] == 1
        assert db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one_or_none() is None
        assert db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po_id
        ).count() == 0
        assert db.query(ShipmentLineSpoLink).filter(
            ShipmentLineSpoLink.inbound_shipment_id == shipment.id
        ).count() == 0
        assert db.query(SPOAllocation).filter(SPOAllocation.po_line_id == po_line.id).count() == 0
        db.refresh(source_line)
        assert float(source_line.qty_received) == 0, "the source PO line's advance must be reversed"

        again = svc.suggest(db, str(shipment.id))
        assert again["already_converted"] is False
        assert again["lines"][0]["suggested_qty"] == 40


def test_unwind_refuses_a_non_crm_spo_header_409_and_leaves_it_untouched():
    """A defensive guard: `unwind` must never delete a PO it did not itself create, however
    it ended up linked - simulate an AutoCount-imported PO wired to this shipment by some
    other path."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        shipment, lines = w.shipment([("A", 40, supplier)])
        po = w.po("AC", supplier, [("A", 40, 0)])  # source_system left None - not crm_spo
        po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po.id
        ).one()
        db.add(ShipmentLineSpoLink(
            id=_u(), inbound_shipment_id=shipment.id, inbound_shipment_line_id=lines[0].id,
            purchase_order_id=po.id, purchase_order_line_id=po_line.id,
        ))
        db.flush()

        with pytest.raises(AppException) as exc:
            svc.unwind(db, str(shipment.id))

        assert exc.value.status_code == 409
        assert po.po_number in str(exc.value.detail)
        assert db.query(PurchaseOrder).filter(PurchaseOrder.id == po.id).one_or_none() is not None
        assert db.query(ShipmentLineSpoLink).filter(
            ShipmentLineSpoLink.inbound_shipment_id == shipment.id
        ).count() == 1


def test_unwind_only_touches_this_shipments_spo_not_anothers():
    """DOCTRINE CORRECTION: each shipment needs its own open PO to pull from."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("A", supplier, [("A", 40, 0)])
        w.po("B", supplier, [("B", 25, 0)])
        shipment_a, lines_a = w.shipment([("A", 40, supplier)])
        shipment_b, lines_b = w.shipment([("B", 25, supplier)])
        svc.create(db, str(shipment_a.id), _confirm_all(lines_a), actor="tester")
        created_b = svc.create(db, str(shipment_b.id), _confirm_all(lines_b), actor="tester")
        po_b_id = created_b["created_spos"][0]["purchase_order_id"]

        svc.unwind(db, str(shipment_a.id))

        assert db.query(PurchaseOrder).filter(PurchaseOrder.id == po_b_id).one_or_none() is not None
        again_a = svc.suggest(db, str(shipment_a.id))
        assert again_a["already_converted"] is False
        again_b = svc.suggest(db, str(shipment_b.id))
        assert again_b["already_converted"] is True


def test_unwind_on_a_never_converted_shipment_is_404():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        shipment, _lines = w.shipment([("A", 40, supplier)])

        with pytest.raises(AppException) as exc:
            svc.unwind(db, str(shipment.id))
        assert exc.value.status_code == 404


def test_heal_stale_link_cleans_up_a_link_pointing_at_a_deleted_po_and_suggest_answers_honestly():
    """Simulate a CRM SPO removed by some path OTHER than `unwind` - delete the PO line then
    the header directly (Postgres's own `ON DELETE SET NULL`, migration 406, then clears the
    link's ids, the exact signature `_heal_stale_links` must catch).

    DOCTRINE CORRECTION: needs a seeded open PO to pull from. This bypass-`unwind` delete does
    NOT reverse the `qty_received` advance `create` made on the source line (only `unwind`
    does that, per its own docstring) - self-heal clears the ORPHANED link so the planner is
    never stuck, but the source PO's balance stays spent, exactly the documented limitation.
    So the line comes back `cannot_convert` (nothing left to pull), not restored to 40 - the
    honest answer here, not the pre-correction expectation."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 40, supplier)])
        created = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
        po_id = created["created_spos"][0]["purchase_order_id"]

        db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po_id
        ).delete(synchronize_session=False)
        db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).delete(synchronize_session=False)
        db.flush()
        assert db.query(ShipmentLineSpoLink).filter(
            ShipmentLineSpoLink.inbound_shipment_id == shipment.id
        ).count() == 1

        out = svc.suggest(db, str(shipment.id))

        assert out["already_converted"] is False
        assert out["self_heal_note"] is not None
        assert out["lines"][0]["cannot_convert"] is True
        assert out["lines"][0]["suggested_qty"] == 0
        assert db.query(ShipmentLineSpoLink).filter(
            ShipmentLineSpoLink.inbound_shipment_id == shipment.id
        ).count() == 0


def test_heal_partial_alive_conversion_shows_the_alive_spo_and_notes_the_cleared_one():
    """DOCTRINE CORRECTION: each supplier needs its own open PO to pull from for `create` to
    produce anything at all."""
    with pg_session() as db:
        w = World(db)
        jiangmen = w.supplier("JIANGMEN")
        kailu = w.supplier("KAILU")
        w.po("A", jiangmen, [("A", 50, 0)])
        w.po("B", kailu, [("B", 30, 0)])
        shipment, lines = w.shipment([
            ("A", 50, jiangmen),
            ("B", 30, kailu),
        ])
        created = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
        dead = next(s for s in created["created_spos"] if s["supplier_id"] == str(jiangmen.id))
        alive = next(s for s in created["created_spos"] if s["supplier_id"] == str(kailu.id))

        db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == dead["purchase_order_id"]
        ).delete(synchronize_session=False)
        db.query(PurchaseOrder).filter(
            PurchaseOrder.id == dead["purchase_order_id"]
        ).delete(synchronize_session=False)
        db.flush()

        out = svc.suggest(db, str(shipment.id))

        assert out["already_converted"] is True
        assert out["self_heal_note"] is not None
        remaining_ids = {s["purchase_order_id"] for s in out["existing_spos"]}
        assert remaining_ids == {alive["purchase_order_id"]}


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #

_BASE = "/api/v1/scm/inbound-shipments"


def _seed_route_shipment(db, *, status="in_transit"):
    """One supplier, one product, one shipment line - built with ORM models like the
    fulfilment route suite's own `_seed`, company-scoped via `as_company_user`.

    DOCTRINE CORRECTION: also seeds an OPEN PO for the same product/supplier, sized to
    exactly the shipment line's packed qty (15), so every route test below that exercises
    the happy path has something to pull from - without it every one of them would read
    `cannot_convert` and every `create` would 422 "nothing selected"."""
    cat = ProductCategory(
        id=_u(), category_code=f"{MARKER}R-C-{uuid.uuid4().hex[:6]}", category_name=f"{MARKER} cat"
    )
    uom = UnitOfMeasure(
        id=_u(), uom_code=f"{MARKER[:4]}R{uuid.uuid4().hex[:5]}", uom_name=f"{MARKER} unit"
    )
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_u(), product_code=f"{MARKER}R-ITEM-{uuid.uuid4().hex[:6]}".upper(),
        product_name="Route test item", category_id=cat.id, base_uom_id=uom.id,
        list_price=0, is_active=True, is_discontinued=False,
    )
    supplier = Supplier(
        id=_u(), supplier_code=f"{MARKER}R-{uuid.uuid4().hex[:6]}".upper(),
        supplier_name=f"{MARKER} route supplier", is_active=True,
    )
    db.add_all([product, supplier])
    db.flush()
    po = PurchaseOrder(
        id=_u(), po_number=f"{MARKER}R-PO-{uuid.uuid4().hex[:6]}",
        supplier_id=supplier.id, issue_date=date(2026, 1, 1), status="active",
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id,
        qty_ordered=15, qty_received=0, line_status="open",
    ))
    shipment = InboundShipment(
        id=_u(), shipment_number=f"{MARKER}R-SH-{uuid.uuid4().hex[:6]}",
        supplier_id=supplier.id, shipment_date=date(2026, 8, 1), shipment_status=status,
    )
    db.add(shipment)
    db.flush()
    line = InboundShipmentLine(
        id=_u(), shipment_id=shipment.id, product_id=product.id, supplier_id=supplier.id,
        quantity_shipped=15, unit_cost=5, currency="USD",
    )
    db.add(line)
    db.flush()
    return shipment, line


def test_route_spo_suggestion_happy_path(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)

    r = TestClient(app).get(f"{_BASE}/{shipment.id}/spo-suggestion")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["already_converted"] is False
    assert body["lines"][0]["shipment_line_id"] == str(line.id)
    assert body["lines"][0]["suggested_qty"] == 15


def test_route_create_spo_happy_path(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)

    r = TestClient(app).post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 15, "include": True}]},
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["created_spos"]) == 1
    assert body["created_spos"][0]["po_number"].startswith("CRM-SPO-")


def test_route_create_spo_requires_the_operator_permission(scm_app):
    from tests.scm.conftest import as_user, seed_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)
    # Swap to a principal with no grants at all, same company scope untouched.
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 15, "include": True}]},
    )

    assert r.status_code == 403, r.text


def test_route_spo_suggestion_unknown_shipment_is_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).get(f"{_BASE}/{uuid.uuid4()}/spo-suggestion")

    assert r.status_code == 404, r.text


def test_route_create_spo_unknown_shipment_is_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(
        f"{_BASE}/{uuid.uuid4()}/spo",
        json={"lines": []},
    )

    assert r.status_code in (404, 422), r.text


def test_route_create_spo_with_every_line_unticked_is_a_422_nothing_selected(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)

    r = TestClient(app).post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 0, "include": False}]},
    )

    assert r.status_code == 422, r.text
    assert "nothing was selected" in r.json()["detail"].lower() or "nothing_selected" in r.text.lower()


def test_route_create_spo_all_unconvertible_no_supplier_is_422(scm_app):
    """Every line lacks a supplier -> nothing groupable, refused the same way an empty
    selection is - the reason (no supplier) is carried in the (would-be) skip, not silently
    dropped."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)
    line.supplier_id = None
    db.flush()

    r = TestClient(app).post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 15, "include": True}]},
    )

    assert r.status_code == 422, r.text


def test_route_worksheet_export_returns_xlsx_bytes_with_a_sensible_filename(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)
    client = TestClient(app)
    created = client.post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 15, "include": True}]},
    )
    assert created.status_code == 201, created.text

    r = client.get(f"{_BASE}/{shipment.id}/spo-worksheet/export")

    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == _XLSX
    disposition = r.headers.get("content-disposition", "")
    assert "spo-worksheet.xlsx" in disposition
    assert shipment.shipment_number in disposition or (shipment.shipping_container_number or "") in disposition
    assert len(r.content) > 0


def test_route_worksheet_export_before_any_create_is_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, _line = _seed_route_shipment(db)

    r = TestClient(app).get(f"{_BASE}/{shipment.id}/spo-worksheet/export")

    assert r.status_code == 404, r.text


def test_route_draft_shipment_converts_too(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db, status="draft")

    suggestion = TestClient(app).get(f"{_BASE}/{shipment.id}/spo-suggestion")
    assert suggestion.status_code == 200, suggestion.text
    assert suggestion.json()["shipment_status"] == "draft"

    r = TestClient(app).post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 15, "include": True}]},
    )
    assert r.status_code == 201, r.text


def test_route_delete_spo_happy_path(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)
    client = TestClient(app)
    created = client.post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 15, "include": True}]},
    )
    assert created.status_code == 201, created.text

    r = client.delete(f"{_BASE}/{shipment.id}/spo")

    assert r.status_code == 200, r.text
    assert r.json()["deleted_spo_count"] == 1

    again = client.get(f"{_BASE}/{shipment.id}/spo-suggestion")
    assert again.json()["already_converted"] is False


def test_route_delete_spo_requires_the_operator_permission(scm_app):
    from tests.scm.conftest import as_user, seed_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)
    client = TestClient(app)
    created = client.post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 15, "include": True}]},
    )
    assert created.status_code == 201, created.text
    # Swap to a principal with no grants at all, same company scope untouched.
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = client.delete(f"{_BASE}/{shipment.id}/spo")

    assert r.status_code == 403, r.text


def test_route_delete_spo_with_nothing_converted_is_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, _line = _seed_route_shipment(db)

    r = TestClient(app).delete(f"{_BASE}/{shipment.id}/spo")

    assert r.status_code == 404, r.text
