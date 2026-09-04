"""S9 second half - "Create SPO" (`app/services/scm/spo_conversion_service.py`,
`PLAN-scm-proforma-to-spo.md`'s Amendment, second decision).

Traces to the module docstring's own contract:
  * `suggest` - packed qty, netted by an open PO to the SAME supplier (product match, or
    PINNED by a po_ref carried through the PI provenance link), then by on-hand + incoming
    SPO, floored at 0. Covered and no-supplier lines stay visible with a reason.
  * `create` - one CRM `purchase_orders` header per supplier represented on the shipment,
    `source_system='crm_spo'`, its own `S-SPO-yyyy/mm-nnnn` number series
    (`numbering_defaults.CRM_SPO_DOC_TYPE`), `shipment_line_spo_link` rows for both the
    matched and the skipped lines. A second attempt is refused (409), naming the SPOs
    already made.
  * Visibility - the new lines count as ORDERED (`scm.po_ordered_v`, no source predicate)
    immediately, and are deliberately absent from `scm.on_order_v` (spo_allocations only)
    until someone allocates them - same split pinned by `test_reorder_nets_po_ordered.py`.

Postgres only, marker-prefixed, every test seeds its own chain (CI's database is empty).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_RAISED,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SO_STATUS_DRAFT,
)
from app.models.projects import Project
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

    def warehouse(
        self, key: str = "WH", *, segment: str | None = None, is_active: bool = True
    ) -> Warehouse:
        """A location. `segment='project'` is a GROUP bin (stock there is spoken for) and
        `is_active=False` is a CLOSED location - eleven of those exist on the live book.
        Neither is a site pool, so neither belongs in the planner's context figures."""
        if key not in self.warehouses:
            w = Warehouse(
                id=_u(), warehouse_code=f"{MARKER}-{key}-{self.tag}"[:50],
                warehouse_name=key, is_active=is_active, segment=segment,
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


def test_suggest_with_no_open_po_at_all_is_still_convertible_and_names_why():
    """CAPTAIN'S RULING (3 Sep, sixth amendment): the PO cap is removed. A packed line with NO
    open PO behind it is still convertible - `cannot_convert` is now true ONLY for a line with
    no supplier at all - the reason it has nothing to pull from is kept as INFORMATION
    (`reason == _REASON_NO_PO`), not a block. `packed_qty` still reports the PACKED figure
    (`quantity_shipped`, never the PI's invoiced one - the Amendment's own correction, still
    true). Location options and SO coverage are computed for this line too, since it can
    still be confirmed (previously both were skipped for a `cannot_convert` line).

    A warehouse is seeded so `_location_options`'s own fallback (`_default_warehouse`, "the
    one counts-as-available warehouse") has something to find - CI's database starts empty,
    unlike the local dev DB, which is a prod copy already carrying real warehouses."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.warehouse()
        shipment, lines = w.shipment([("A", 120, supplier)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["packed_qty"] == 120
        assert line["po_covered_qty"] == 0
        assert line["suggested_qty"] == 0
        assert line["no_po_qty"] == 120
        assert line["cannot_convert"] is False
        assert line["reason"] == svc._REASON_NO_PO
        assert line["location_options"], "still convertible, so a destination is offered"
        assert line["so_coverage"] is not None


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


def test_a_pin_to_an_exhausted_po_falls_back_to_the_product_match():
    """F1 (review round, BLOCKER): PO-PIN is the STATED po_ref but has nothing open left
    (100 ordered, 100 already received) - S5 stopped `_open_line_rows` dropping
    `available == 0` lines, so `_candidate_lines_for_line` now RESOLVES the pin (it names a
    real line) even though the cascade can take nothing from it. Before this fix
    `matched_by` was set to `po_ref` whenever the pin resolved AT ALL, so the product-match
    fallback below never ran and the line read `cannot_convert` with PO-OTHER (80 open, same
    supplier and product) sitting right there.

    NOTE: this test creates a PI row (`pi_po_ref`) the same way the pin tests above do, and
    fails LOCALLY the same way they do on `UndefinedColumn: container_size_id` (the shared
    dev DB's `create_all` convergence lags a migration - see `sorento_crm_backend/CLAUDE.md`).
    It runs green on CI, which migrates to head.
    `test_a_pin_to_an_exhausted_po_falls_back_to_the_product_match_without_a_pi_row` below
    covers the identical fix without a PI row, so the fix itself is proven either way."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        pinned = w.po("PIN", supplier, [("A", 100, 100)])  # fully received, nothing open
        w.po("OTHER", supplier, [("A", 80, 0)])
        shipment, lines = w.shipment([("A", 80, supplier)])
        w.pi_po_ref(lines[0], pinned.po_number)

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["matched_by"] == "product"
        assert line["po_covered_qty"] == 80
        assert line["cannot_convert"] is False


def test_a_pin_to_an_exhausted_po_falls_back_to_the_product_match_without_a_pi_row(monkeypatch):
    """F1, direct: the same fix, with no `ProformaInvoice` row at all - avoids the
    `container_size_id` dev-DB drift `test_a_pin_to_an_exhausted_po_falls_back_to_the_
    product_match` above hits locally. `_po_refs_for_line` and `_pinned_po_candidates` are
    monkeypatched to stand in for PI provenance and hand back the exhausted PO-PIN line
    directly; PO-OTHER is a REAL open line to the same supplier/product so the fallback
    cascade has something real to take from."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        pinned = w.po("PIN", supplier, [("A", 100, 100)])
        w.po("OTHER", supplier, [("A", 80, 0)])
        shipment, lines = w.shipment([("A", 80, supplier)])
        ln = lines[0]

        monkeypatch.setattr(
            svc, "_po_refs_for_line", lambda db, shipment_line_id: {pinned.po_number}
        )
        monkeypatch.setattr(
            svc,
            "_pinned_po_candidates",
            lambda db, po_number, supplier_id, product_id: [(pinned.lines[0], pinned, 0.0)],
        )

        matched_by, takes = svc._match_takes_for_line(db, ln, 80)

        assert matched_by == "product"
        assert sum(t[2] for t in takes) == 80


def test_the_inference_path_still_refuses_a_cross_supplier_po_with_no_stated_ref():
    """No po_ref at all - the UN-pinned (product-match) path must still refuse a PO booked
    under a different supplier, or the pin fix above would silently widen inference too. With
    nothing pullable at all, `po_covered_qty` stays 0 (doctrine correction). Sixth amendment
    (captain's ruling, 3 Sep): a supplier is still on the line, so it is NOT `cannot_convert` -
    only a missing supplier blocks conversion now."""
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
        assert line["cannot_convert"] is False
        assert line["no_po_qty"] == 100


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


def test_context_figures_count_active_site_pools_only():
    """AC-G3, sum = cell. Both context cells open a dialog that lists ACTIVE POOL rows only
    (`location_stock_service.location_stock_for_product` for On hand, `container_request_
    drill`'s own `w.is_active AND _POOL` for Incoming SPO), so a cell counting a closed
    location or a project bin sends the reader to a total that does not match what she
    clicked. 50 at the pool is the whole of both figures; the 30 in a project bin and the 40
    in a closed location are not in either."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        pool = w.warehouse("POOL")
        bin_ = w.warehouse("BIN", segment="project")
        closed = w.warehouse("CLOSED", is_active=False)
        shipment, lines = w.shipment([("A", 100, supplier)])
        w.stock("A", pool, 50)
        w.stock("A", bin_, 30)
        w.stock("A", closed, 40)
        w.spo_allocation("A", shipment, pool, 50)
        w.spo_allocation("A", shipment, bin_, 30)
        w.spo_allocation("A", shipment, closed, 40)

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["on_hand"] == 50
        assert line["incoming_spo"] == 50


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
        assert re.match(r"^S-SPO-\d{4}/\d{2}-\d{4}$", po.po_number), po.po_number
        po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po.id
        ).one()
        assert po_line.source_system == "crm_spo"
        assert po_line.line_status == "open"
        assert float(po_line.qty_ordered) == 40

        # `source_ref` carries the pull AND what the SPO line was ticked to cover; the
        # older bare-list encoding still reads, which is what `parse_source_ref` is for.
        recorded = json.loads(po_line.source_ref)
        assert recorded["pulls"] == [{"po_line_id": str(source_line.id), "qty": 40.0}]
        assert svc.parse_source_ref(po_line.source_ref)["pulls"] == [
            (str(source_line.id), 40.0)
        ]
        db.refresh(source_line)
        assert float(source_line.qty_received) == 40, "the source PO line's own accounting must advance"


def test_create_writes_the_full_line_qty_when_the_po_only_covers_part_of_it():
    """AC-I4 (captain's ruling, 3 Sep, sixth amendment): an open PO for 409 to the same
    supplier, a shipment line packed 500, confirmed at 500. The SPO line is written at 500 (not
    capped at what the PO covers); `source_ref.pulls` totals only the 409 the PO actually gave
    up; the source PO line advances by exactly 409, never the full 500; `no_po_qty` on
    `source_ref` records the uncovered 91."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        source_po = w.po("1", supplier, [("A", 409, 0)])
        source_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == source_po.id
        ).one()
        shipment, lines = w.shipment([("A", 500, supplier)])

        out = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        po_id = out["created_spos"][0]["purchase_order_id"]
        po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po_id
        ).one()
        assert float(po_line.qty_ordered) == 500

        recorded = json.loads(po_line.source_ref)
        assert recorded["pulls"] == [{"po_line_id": str(source_line.id), "qty": 409.0}]
        assert recorded["no_po_qty"] == 91.0
        assert svc.parse_source_ref(po_line.source_ref)["pulls"] == [
            (str(source_line.id), 409.0)
        ]

        db.refresh(source_line)
        assert float(source_line.qty_received) == 409, "advances by only what it actually pulled"


def test_create_writes_shipment_line_spo_link_rows_for_matched_selected_and_unpo_backed_lines():
    """CAPTAIN'S RULING (3 Sep, sixth amendment): line C, ticked but backed by no open PO at
    all, is NO LONGER a skip - it gets its own SPO line, matched (a link row with a
    `purchase_order_line_id`, not an `unmatched_reason`), same as PO-backed line A. Only B
    (deliberately left unticked) is skipped, and only for `_REASON_NOT_SELECTED` - the
    "every line accounted for" contract is exercised on all three outcomes in one create."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        # A: included, backed by an open PO. B: deliberately left unticked, so the "every
        # line accounted for" contract is exercised on both outcomes in one create. C: ALSO
        # ticked, backed by no PO at all - convertible since the sixth amendment, re-checked
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
        assert no_po.purchase_order_line_id is not None
        assert no_po.unmatched_reason is None
        no_po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.id == no_po.purchase_order_line_id
        ).one()
        assert float(no_po_line.qty_ordered) == 5
        assert svc.parse_source_ref(no_po_line.source_ref)["pulls"] == []


def test_f7_two_runs_leave_exactly_one_skip_row_per_still_skipped_line():
    """F7 (review round): a skip-reason `shipment_line_spo_link` row (`purchase_order_id IS
    NULL`) carries no PO to scope by, unlike a matched row, and used to be written fresh on
    EVERY `create` run with no disposal of the old one - so a line skipped twice in a row
    accumulated TWO skip rows, growing without bound on every re-run. B is deliberately left
    unticked on BOTH runs; only ONE skip row for it must survive the second run. A, ticked a
    little more each run, still gets a NEW matched row per run (R1's own "one row per run"
    contract for matched rows, migration 469 - untouched by this fix)."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier), ("B", 10, supplier)])
        a_id, b_id = str(lines[0].id), str(lines[1].id)

        svc.create(
            db, str(shipment.id),
            [
                {"shipment_line_id": a_id, "qty": 10, "include": True},
                {"shipment_line_id": b_id, "qty": 0, "include": False},
            ],
            actor="tester",
        )
        svc.create(
            db, str(shipment.id),
            [
                {"shipment_line_id": a_id, "qty": 20, "include": True},
                {"shipment_line_id": b_id, "qty": 0, "include": False},
            ],
            actor="tester",
        )

        links = db.query(ShipmentLineSpoLink).filter(
            ShipmentLineSpoLink.inbound_shipment_id == shipment.id
        ).all()
        a_links = [l for l in links if str(l.inbound_shipment_line_id) == a_id]
        b_links = [l for l in links if str(l.inbound_shipment_line_id) == b_id]

        assert len(a_links) == 2, "matched rows still accumulate one per run (R1)"
        assert all(l.purchase_order_line_id is not None for l in a_links)

        assert len(b_links) == 1, "the stale skip row from the first run must be gone"
        assert b_links[0].unmatched_reason == svc._REASON_NOT_SELECTED


def test_create_succeeds_with_no_po_behind_the_ticked_line():
    """CAPTAIN'S RULING (3 Sep, sixth amendment, AC-I5): a ticked line with a supplier but no
    open PO behind it is convertible - `create` writes it at `need` (the full packed qty, here)
    with no pull. Was a 422 refusal pre-ruling (see the docs); the shape of that guard
    (`test_route_create_spo_all_unconvertible_no_supplier_is_422`) is still true for the
    no-supplier case, which this test does not touch."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        shipment, lines = w.shipment([("A", 40, supplier)])

        out = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        assert len(out["created_spos"]) == 1
        assert not out["skipped"]
        po_id = out["created_spos"][0]["purchase_order_id"]
        po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po_id
        ).one()
        assert float(po_line.qty_ordered) == 40
        assert svc.parse_source_ref(po_line.source_ref)["pulls"] == []


def test_a_second_create_after_full_conversion_is_422_nothing_left_not_409():
    """R1 supersedes the old blanket-refusal contract: a fully converted shipment no longer
    blocks `suggest` (which keeps reporting `already_converted: false` and lists the SPO in
    `existing_spos`) and a second `create` with nothing left on any line is 422 `nothing_left`,
    never a 409."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 40, supplier)])

        first = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
        first_number = first["created_spos"][0]["po_number"]

        with pytest.raises(AppException) as exc:
            svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        assert exc.value.status_code == 422
        assert exc.value.detail["detail"] == "nothing_left"
        # suggest() must keep reporting `already_converted: false` (R1: it never flips any
        # more) and still list the SPO already made.
        again = svc.suggest(db, str(shipment.id))
        assert again["already_converted"] is False
        assert again["existing_spos"][0]["po_number"] == first_number
        assert _line(again, str(lines[0].id))["remaining_qty"] == 0


# --------------------------------------------------------------------------- #
# R1 - many SPOs per container (AC-H1..H5)
# --------------------------------------------------------------------------- #


def test_suggest_after_a_partial_create_reports_the_remainder_and_the_existing_spo():
    """AC-H1: `create` 40 of a line packed 100 (an open PO covers plenty); a second `suggest`
    reports `already_converted: false`, one row in `existing_spos` naming the SPO with its
    own line/qty/created/status figures, and the line's `remaining_qty` = packed minus what
    that SPO already took - `packed_qty` stays the untouched physical fact."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 200, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        line_id = str(lines[0].id)

        created = svc.create(
            db, str(shipment.id),
            [{"shipment_line_id": line_id, "qty": 40, "include": True}],
            actor="tester",
        )
        first_number = created["created_spos"][0]["po_number"]

        out = svc.suggest(db, str(shipment.id))

        assert out["already_converted"] is False
        assert len(out["existing_spos"]) == 1
        spo = out["existing_spos"][0]
        assert spo["po_number"] == first_number
        assert spo["line_count"] == 1
        assert spo["total_qty"] == 40
        assert spo["created_at"]
        assert spo["status"] == "active"

        line = _line(out, line_id)
        assert line["packed_qty"] == 100
        assert line["remaining_qty"] == 60
        assert line["suggested_qty"] == min(line["po_covered_qty"], 60)
        assert line["po_covered_qty"] <= 60


def test_a_line_fully_spod_reads_remaining_zero_and_names_the_spo():
    """AC-H2."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])

        created = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
        first_number = created["created_spos"][0]["po_number"]

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["remaining_qty"] == 0
        assert line["cannot_convert"] is True
        assert line["reason"].startswith("Already on ")
        assert first_number in line["reason"]


def test_a_second_create_on_the_remainder_succeeds_a_third_with_nothing_left_is_422():
    """AC-H3."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 200, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        line_id = str(lines[0].id)

        svc.create(
            db, str(shipment.id),
            [{"shipment_line_id": line_id, "qty": 40, "include": True}],
            actor="tester",
        )
        second = svc.create(
            db, str(shipment.id),
            [{"shipment_line_id": line_id, "qty": 60, "include": True}],
            actor="tester",
        )
        assert len(second["created_spos"]) == 1

        out = svc.suggest(db, str(shipment.id))
        assert len(out["existing_spos"]) == 2
        line = _line(out, line_id)
        assert line["remaining_qty"] == 0

        with pytest.raises(AppException) as exc:
            svc.create(
                db, str(shipment.id),
                [{"shipment_line_id": line_id, "qty": 100, "include": True}],
                actor="tester",
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["detail"] == "nothing_left"


def test_f1_a_second_create_on_the_remainder_never_pulls_from_the_first_spos_own_line():
    """F1 (review round, BLOCKER, live evidence): neither candidate query excluded a CRM
    SPO's own line, so a second `create` on the same shipment's remainder pulled from the
    FIRST SPO's own open line instead of the real PO behind it - live case: SPO-2 pulled 34
    from SPO-1 and advanced SPO-1's own `qty_received`, which is backwards - a CRM SPO line
    is the SHIPMENT LEG of an existing PO, never itself a PO to pull from.

    One open real PO for 409, packed 500: the first `create` asks for the 409 the PO can
    give (fully spending it), leaving a 91 remainder; the second `create` asks for that 91,
    which has nothing REAL left to pull from and must not reach into SPO-1's own 409-qty
    line. SPO-1's own line must be untouched (`qty_received` stays 0 - nothing has pulled
    FROM it), and a wholly separate second shipment for the same product/supplier must also
    see nothing pullable, never either CRM SPO line counted as an open "PO"."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 409, 0)])
        shipment, lines = w.shipment([("A", 500, supplier)])
        line_id = str(lines[0].id)

        first = svc.create(
            db, str(shipment.id),
            [{"shipment_line_id": line_id, "qty": 409, "include": True}],
            actor="tester",
        )
        first_po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == first["created_spos"][0]["purchase_order_id"]
        ).one()

        second = svc.create(
            db, str(shipment.id),
            [{"shipment_line_id": line_id, "qty": 91, "include": True}],
            actor="tester",
        )
        second_po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == second["created_spos"][0]["purchase_order_id"]
        ).one()

        assert svc.parse_source_ref(second_po_line.source_ref)["pulls"] == []
        db.refresh(first_po_line)
        assert float(first_po_line.qty_received) == 0, "nothing may pull FROM SPO-1's own line"

        # A wholly separate shipment of the same product/supplier must not see either CRM
        # SPO line as something a fresh cascade could pull from.
        third_shipment, third_lines = w.shipment([("A", 50, supplier)])
        out = svc.suggest(db, str(third_shipment.id))
        line = _line(out, str(third_lines[0].id))
        assert line["po_covered_qty"] == 0
        assert not any(
            (t.get("po_number") or "").startswith("S-SPO-") for t in line["po_takes"]
        )


def test_f3_concurrent_create_calls_on_the_same_shipment_are_serialised_by_the_row_lock():
    """F3 (review round): nothing serialised two concurrent `create` calls on one shipment -
    both could read the same open-PO remainder and both cascade against it. `create` now
    locks the shipment row (`_shipment_or_404(..., for_update=True)`, `SELECT ... FOR
    UPDATE`) before reading anything.

    Real, committed Postgres via `SessionLocal` (not `pg_session`): the whole point is what a
    SECOND connection sees while the first holds the lock, which a rollback-scoped session on
    one connection cannot show - mirrors `test_media_quota_serialization.py`'s own pattern for
    the identical reason. Cleaned up by hand in `finally` since nothing here rolls back."""
    seed_db = SessionLocal()
    try:
        w = World(seed_db)
        supplier = w.supplier()
        po = w.po("1", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 50, supplier)])
        shipment_id = str(shipment.id)
        product_id = str(w.product("A").id)
        supplier_id = str(supplier.id)
        po_id = str(po.id)
        cat_id = str(w.cat.id)
        uom_id = str(w.uom.id)
        seed_db.commit()
    finally:
        seed_db.close()

    session_a = SessionLocal()
    session_b = SessionLocal()
    # A brand-new `SessionLocal` scopes its very FIRST statement before the test
    # process's own `after_begin` listener has filled in `session.info['company_scope']`
    # (`tests/conftest.py`), which reads back as the row being invisible - nothing to do
    # with the lock under test. A trivial warm-up query settles the scope first, exactly
    # the ordering every route's own `Depends(get_db)` already gives it in production.
    session_a.execute(text("SELECT 1"))
    session_b.execute(text("SELECT 1"))
    b_started = threading.Event()
    b_done = threading.Event()
    try:
        svc._shipment_or_404(session_a, shipment_id, for_update=True)

        def _b():
            b_started.set()
            svc._shipment_or_404(session_b, shipment_id, for_update=True)
            b_done.set()

        thread = threading.Thread(target=_b)
        thread.start()
        assert b_started.wait(timeout=2), "session B never started"
        assert not b_done.wait(timeout=0.5), "session B must block behind A's row lock"

        session_a.rollback()  # releases A's lock
        assert b_done.wait(timeout=5), "session B must unblock once A releases the lock"
        thread.join(timeout=5)
    finally:
        session_a.rollback()
        session_b.rollback()
        session_a.close()
        session_b.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(InboundShipmentLine).filter(
                InboundShipmentLine.shipment_id == shipment_id
            ).delete(synchronize_session=False)
            cleanup.query(InboundShipment).filter(
                InboundShipment.id == shipment_id
            ).delete(synchronize_session=False)
            cleanup.query(PurchaseOrderLine).filter(
                PurchaseOrderLine.purchase_order_id == po_id
            ).delete(synchronize_session=False)
            cleanup.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).delete(
                synchronize_session=False
            )
            cleanup.query(Supplier).filter(Supplier.id == supplier_id).delete(
                synchronize_session=False
            )
            cleanup.query(Product).filter(Product.id == product_id).delete(
                synchronize_session=False
            )
            cleanup.query(ProductCategory).filter(ProductCategory.id == cat_id).delete(
                synchronize_session=False
            )
            cleanup.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom_id).delete(
                synchronize_session=False
            )
            cleanup.commit()
        finally:
            cleanup.close()


def test_unwind_scoped_to_one_purchase_order_id_leaves_the_other_spo():
    """AC-H4."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 200, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        line_id = str(lines[0].id)

        first = svc.create(
            db, str(shipment.id),
            [{"shipment_line_id": line_id, "qty": 40, "include": True}],
            actor="tester",
        )
        second = svc.create(
            db, str(shipment.id),
            [{"shipment_line_id": line_id, "qty": 60, "include": True}],
            actor="tester",
        )
        first_id = first["created_spos"][0]["purchase_order_id"]
        second_id = second["created_spos"][0]["purchase_order_id"]

        out = svc.unwind(db, str(shipment.id), purchase_order_id=first_id)

        assert out["deleted_po_numbers"] == [first["created_spos"][0]["po_number"]]
        assert out["deleted_spo_count"] == 1
        assert db.query(PurchaseOrder).filter(PurchaseOrder.id == first_id).one_or_none() is None
        assert db.query(PurchaseOrder).filter(PurchaseOrder.id == second_id).one_or_none() is not None

        again = svc.suggest(db, str(shipment.id))
        assert len(again["existing_spos"]) == 1
        assert again["existing_spos"][0]["purchase_order_id"] == second_id
        line = _line(again, line_id)
        assert line["remaining_qty"] == 40, "only the surviving SPO's 60 stays taken off the 100 packed"

        with pytest.raises(AppException) as exc:
            svc.unwind(db, str(shipment.id), purchase_order_id=str(uuid.uuid4()))
        assert exc.value.status_code == 404


def test_plan_of_lists_pulls_and_covers_for_a_crm_spo_po_and_is_empty_for_an_import_po():
    """AC-H5."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        source_po = w.po("1", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])

        customer = Customer(
            id=_u(), customer_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
            customer_name=f"{MARKER} dealer",
        )
        db.add(customer)
        db.flush()
        so = SalesOrder(
            id=_u(), so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:6]}",
            customer_id=customer.id, order_date=date(2026, 7, 1), status="open",
        )
        db.add(so)
        db.flush()
        so_line = SalesOrderLine(
            id=_u(), sales_order_id=so.id, product_id=w.product("A").id,
            warehouse_id=wh.id, qty_ordered=100, qty_delivered=0,
            required_date=date(2026, 9, 1), line_status="open",
        )
        db.add(so_line)
        db.flush()

        created = svc.create(
            db, str(shipment.id),
            [{
                "shipment_line_id": str(lines[0].id), "qty": 100, "include": True,
                "so_line_ids": [f"retail:{so_line.id}"],
            }],
            actor="tester",
        )
        po_id = created["created_spos"][0]["purchase_order_id"]

        plan = svc.plan_of(db, po_id)

        assert plan["pulls"] == [{
            "purchase_order_id": str(source_po.id),
            "po_number": source_po.po_number,
            "po_line_label": w.product("A").product_code,
            "qty": 100.0,
        }]
        assert len(plan["covers"]) == 1
        cover = plan["covers"][0]
        assert cover["so_number"] == so.so_number
        assert cover["customer"] == customer.customer_name
        assert cover["qty"] == 100.0
        assert cover["warehouse"] == wh.warehouse_code

        # An AutoCount (non-crm_spo) PO has no plan at all.
        assert svc.plan_of(db, str(source_po.id)) == {"pulls": [], "covers": []}


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


def test_unwind_on_a_line_with_no_pulls_still_succeeds():
    """CAPTAIN'S RULING (3 Sep, sixth amendment): a line with no supporting PO at all still
    creates an SPO line with an EMPTY `source_ref.pulls`. `unwind`'s reversal walk
    (`_reverse_advances`) must not choke on a line with nothing to reverse - it simply finds
    zero reversals for that line and moves on; the SPO still deletes cleanly."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        shipment, lines = w.shipment([("A", 40, supplier)])

        created = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
        po_id = created["created_spos"][0]["purchase_order_id"]
        po_number = created["created_spos"][0]["po_number"]

        out = svc.unwind(db, str(shipment.id))

        assert out["deleted_spo_count"] == 1
        assert out["deleted_po_numbers"] == [po_number]
        assert out["restored_po_line_count"] == 0
        assert db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).one_or_none() is None

        again = svc.suggest(db, str(shipment.id))
        assert again["already_converted"] is False


def test_unwind_deletes_the_order_inquiry_link_before_the_allocation_it_points_at():
    """F9 (review round, pre-existing bug): bulk-deleting `spo_allocations` an
    `OrderInquiryLink` points at violates `ck_order_inquiry_links_one_target` - the FK is
    `ON DELETE SET NULL`, not `CASCADE`, but the CHECK forbids a link with NEITHER target
    set, so the SET NULL Postgres was about to apply left the row with neither and the
    constraint fired: `unwind` raised instead of completing for any SPO an ORDER BACK
    project row had been ticked against. `unwind` must delete this SPO's OWN order-inquiry
    links first - the row simply returns unlinked, which `_project_coverage` then offers in
    full, exactly what deleting the SPO should mean.

    World setup mirrors `test_a_ticked_project_row_is_linked_to_the_spo_allocation_it_will_
    be_served_by` (`test_spo_planner_selection.py`)."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])

        title = f"{MARKER} project {uuid.uuid4().hex[:6]}"
        project = Project(
            id=_u(), title=title, normalised_title=title.lower(),
            project_code=f"{MARKER}-{uuid.uuid4().hex[:8]}",
        )
        db.add(project)
        db.flush()
        pso = ProjectSalesOrder(
            id=_u(), project_id=project.id, area_group="TOWER",
            provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:6]}",
            autocount_doc_no=f"{MARKER}-SI-{uuid.uuid4().hex[:6]}",
            status=SO_STATUS_DRAFT, grouping_origin="area",
            published_at=datetime(2026, 1, 2, 9, 0),
        )
        db.add(pso)
        db.flush()
        pso_line = ProjectSalesOrderLine(
            id=_u(), project_sales_order_id=pso.id, line_no=1,
            product_id=w.product("A").id, description=f"{MARKER} line",
            qty=Decimal("40"), uom="UNIT", unit_price=Decimal("10.00"),
            amount=Decimal("400"), delivery_date=date(2026, 9, 10),
        )
        db.add(pso_line)
        db.flush()
        inquiry = OrderInquiry(id=_u(), project_sales_order_id=pso.id, state=INQUIRY_RAISED)
        db.add(inquiry)
        db.flush()
        row = OrderInquiryRow(
            id=_u(), order_inquiry_id=inquiry.id, so_line_id=pso_line.id,
            item_code=w.product("A").product_code, qty=Decimal("40"),
            delivery_date=date(2026, 9, 10), verb=IV_ORDER_BACK, state=INQUIRY_RAISED,
        )
        db.add(row)
        db.flush()

        svc.create(
            db, str(shipment.id),
            [{
                "shipment_line_id": str(lines[0].id), "qty": 100, "include": True,
                "location_splits": [{"warehouse_id": str(wh.id), "qty": 100}],
                "so_line_ids": [f"project:{row.id}"],
            }],
        )
        link = db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).one()
        assert link.spo_allocation_id is not None, "sanity: the tick must have written a link"

        out = svc.unwind(db, str(shipment.id))

        assert out["deleted_spo_count"] == 1
        assert db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).count() == 0

        again = svc.suggest(db, str(shipment.id))
        assert again["already_converted"] is False
        line_out = _line(again, str(lines[0].id))
        taken_row = next(c for c in line_out["so_coverage"] if c["kind"] == "project")
        assert taken_row["qty"] == 40
        assert taken_row["taken_qty"] == 0


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
        assert again_a["existing_spos"] == []
        again_b = svc.suggest(db, str(shipment_b.id))
        assert again_b["already_converted"] is False
        assert again_b["existing_spos"][0]["purchase_order_id"] == po_b_id
        line_b = _line(again_b, str(lines_b[0].id))
        assert line_b["remaining_qty"] == 0


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
    So the line comes back with nothing left to pull (`suggested_qty` 0, `no_po_qty` 40), not
    restored to 40 - the honest answer here. Sixth amendment (3 Sep): `cannot_convert` is now
    False, because a supplier is still on the line - only a missing supplier blocks it."""
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
        assert out["lines"][0]["cannot_convert"] is False
        assert out["lines"][0]["suggested_qty"] == 0
        assert out["lines"][0]["no_po_qty"] == 40
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

        assert out["already_converted"] is False
        assert out["self_heal_note"] is not None
        remaining_ids = {s["purchase_order_id"] for s in out["existing_spos"]}
        assert remaining_ids == {alive["purchase_order_id"]}

        jiangmen_line = next(l for l in lines if str(l.supplier_id) == str(jiangmen.id))
        kailu_line = next(l for l in lines if str(l.supplier_id) == str(kailu.id))
        assert _line(out, str(jiangmen_line.id))["remaining_qty"] == 50, (
            "the healed (deleted) SPO's line is convertible again"
        )
        assert _line(out, str(kailu_line.id))["remaining_qty"] == 0, (
            "the still-alive SPO's line stays fully spent"
        )


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
    assert re.match(r"^S-SPO-\d{4}/\d{2}-\d{4}$", body["created_spos"][0]["po_number"])


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


def test_route_delete_spo_scoped_to_one_purchase_order_id_leaves_the_other(scm_app):
    """AC-H4, at the route: `?purchase_order_id=` deletes only that one SPO."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)
    client = TestClient(app)

    first = client.post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 6, "include": True}]},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 9, "include": True}]},
    )
    assert second.status_code == 201, second.text
    first_id = first.json()["created_spos"][0]["purchase_order_id"]
    second_id = second.json()["created_spos"][0]["purchase_order_id"]

    r = client.delete(f"{_BASE}/{shipment.id}/spo", params={"purchase_order_id": first_id})

    assert r.status_code == 200, r.text
    assert r.json()["deleted_spo_count"] == 1

    again = client.get(f"{_BASE}/{shipment.id}/spo-suggestion")
    existing_ids = {s["purchase_order_id"] for s in again.json()["existing_spos"]}
    assert existing_ids == {second_id}

    r2 = client.delete(
        f"{_BASE}/{shipment.id}/spo", params={"purchase_order_id": str(uuid.uuid4())}
    )
    assert r2.status_code == 404, r2.text


def test_route_purchase_order_detail_carries_spo_plan_for_a_crm_spo_po_and_none_for_import(
    scm_app,
):
    """AC-H5/H7 through the API - `response_model` silently drops an undeclared field, so
    this asserts `spo_plan` is actually present on the JSON, not merely on the service dict."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    shipment, line = _seed_route_shipment(db)
    client = TestClient(app)

    created = client.post(
        f"{_BASE}/{shipment.id}/spo",
        json={"lines": [{"shipment_line_id": str(line.id), "qty": 15, "include": True}]},
    )
    assert created.status_code == 201, created.text
    spo_id = created.json()["created_spos"][0]["purchase_order_id"]

    r = client.get(f"/api/v1/scm/purchase-orders/{spo_id}")

    assert r.status_code == 200, r.text
    plan = r.json()["spo_plan"]
    assert plan is not None
    assert len(plan["pulls"]) == 1
    assert plan["pulls"][0]["qty"] == 15

    # `_seed_route_shipment` also seeds ONE other (non-`crm_spo`) purchase order, to pull
    # from - that one carries no plan at all.
    source_po_id = str(
        db.query(PurchaseOrder.id).filter(PurchaseOrder.id != spo_id).scalar()
    )
    r2 = client.get(f"/api/v1/scm/purchase-orders/{source_po_id}")
    assert r2.status_code == 200, r2.text
    assert r2.json()["spo_plan"] is None
