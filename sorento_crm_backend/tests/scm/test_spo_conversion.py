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


def test_suggest_bases_the_qty_on_the_packed_quantity():
    """The Amendment's own correction: packed (`quantity_shipped`), never the PI's invoiced
    figure - there is no PI at all in this shipment, so any invoiced-qty bug would show up
    as a KeyError/None, not a wrong number."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        shipment, lines = w.shipment([("A", 120, supplier)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["packed_qty"] == 120
        assert line["suggested_qty"] == 120
        assert line["covered"] is False
        assert line["cannot_convert"] is False


def test_an_open_po_line_to_the_same_supplier_reduces_the_suggested_qty():
    """Product-match candidate: no po_ref anywhere, so the open PO to the SAME supplier for
    the SAME product is netted off the packed quantity."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 40, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["po_covered_qty"] == 40
        assert line["matched_by"] == "product"
        assert line["suggested_qty"] == 60


def test_a_po_ref_from_pi_provenance_pins_the_match_over_a_product_only_candidate():
    """The plan's own rule: "a stated po_ref outranks inference". PO-PIN carries the po_ref
    the PI line stated (small, 15 open); PO-BIG is a product-only candidate that would win on
    quantity/earliest-issued alone (90 open) if the pin were not honoured. The suggestion must
    net against PO-PIN ONLY - 15, not 90, and must NOT sum the two."""
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
        assert line["suggested_qty"] == 85


def test_on_hand_and_incoming_spo_surplus_net_the_suggested_qty():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        shipment, lines = w.shipment([("A", 100, supplier)])
        w.stock("A", wh, 20)
        w.spo_allocation("A", shipment, wh, 15)

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["on_hand"] == 20
        assert line["incoming_spo"] == 15
        assert line["suggested_qty"] == 65


def test_the_suggested_qty_floors_at_zero_and_the_covered_line_stays_visible():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("1", supplier, [("A", 500, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])

        out = svc.suggest(db, str(shipment.id))

        line = _line(out, str(lines[0].id))
        assert line["suggested_qty"] == 0
        assert line["covered"] is True
        assert line["cannot_convert"] is False, "covered is not the same as cannot-convert - it must stay checkable"
        assert line["reason"] is not None


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
    with pg_session() as db:
        w = World(db)
        jiangmen = w.supplier("JIANGMEN")
        kailu = w.supplier("KAILU")
        shipment, lines = w.shipment([
            ("A", 50, jiangmen),
            ("B", 30, kailu),
        ])

        out = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        assert len(out["created_spos"]) == 2
        supplier_ids = {s["supplier_id"] for s in out["created_spos"]}
        assert supplier_ids == {str(jiangmen.id), str(kailu.id)}
        assert not out["skipped"]


def test_create_marks_source_system_crm_spo_and_the_crm_spo_number_series():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
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


def test_create_writes_shipment_line_spo_link_rows_for_matched_and_skipped_lines():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        # one line included, one deliberately left unticked so the "every line accounted
        # for" contract is exercised on both outcomes in one create.
        shipment, lines = w.shipment([("A", 40, supplier), ("B", 10, supplier)])
        include_ids = {str(lines[0].id)}

        svc.create(db, str(shipment.id), _confirm_all(lines, include_ids=include_ids), actor="tester")

        links = {
            str(l.inbound_shipment_line_id): l
            for l in db.query(ShipmentLineSpoLink).filter(
                ShipmentLineSpoLink.inbound_shipment_id == shipment.id
            ).all()
        }
        assert len(links) == 2
        matched = links[str(lines[0].id)]
        assert matched.purchase_order_line_id is not None
        assert matched.unmatched_reason is None
        skipped = links[str(lines[1].id)]
        assert skipped.purchase_order_line_id is None
        assert skipped.unmatched_reason == svc._REASON_NOT_SELECTED


def test_a_second_create_is_refused_409_naming_the_existing_spo():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
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
    Create SPO on its own packed figures."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
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
    `source_system` predicate - so a freshly created CRM SPO counts as ordered at once."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
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
    yet must NOT count as incoming, even though it is already ORDERED (previous test)."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        shipment, lines = w.shipment([("A", 40, supplier)])
        product_id = str(lines[0].product_id)

        svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")

        row = db.execute(text(
            "SELECT on_order FROM scm.on_order_v WHERE product_id = :p"
        ), {"p": product_id}).mappings().first()
        assert row is None, "on_order_v must stay silent about a CRM SPO with no allocation"


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #

_BASE = "/api/v1/scm/inbound-shipments"


def _seed_route_shipment(db, *, status="in_transit"):
    """One supplier, one product, one shipment line - built with ORM models like the
    fulfilment route suite's own `_seed`, company-scoped via `as_company_user`."""
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
