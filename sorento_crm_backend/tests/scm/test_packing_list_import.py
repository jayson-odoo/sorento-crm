"""S9 AC-G1/G2/G3 - a workbook of container blocks becomes one shipment each, once.

Idempotency is the property worth the most here: the same file uploaded twice must land on the
same shipments. It is not tested by reading the code, because the thing that provides it is the
DERIVED shipment name meeting a duplicate resolver that lives in another service, and either
half could change without the other noticing.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest

from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.error_handler import AppException
from app.services.scm import packing_list_service as svc
from tests._pg_fixture import pg_session

MARKER = "ZZPL"
HEADER = ["产品型号", "品名", "数量", "箱数", "体积(cbm)"]


def workbook(rows: list[list]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class World:
    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:8].upper()
        self.tag = tag
        self.cat = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=f"{MARKER}-CAT-{tag}",
            category_name=f"{MARKER} category",
        )
        self.uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs"
        )
        db.add_all([self.cat, self.uom])
        db.flush()
        self.supplier = Supplier(
            id=str(uuid.uuid4()),
            supplier_code=f"{MARKER}-S-{tag}",
            supplier_name=f"{MARKER} supplier",
            is_active=True,
        )
        db.add(self.supplier)
        db.flush()
        self.products: dict[str, Product] = {}

    def product(self, key: str) -> Product:
        if key not in self.products:
            p = Product(
                id=str(uuid.uuid4()),
                product_code=f"{MARKER}-{key}-{self.tag}",
                product_name=key,
                category_id=self.cat.id,
                base_uom_id=self.uom.id,
                list_price=0,
                is_active=True,
                is_discontinued=False,
            )
            self.db.add(p)
            self.db.flush()
            self.products[key] = p
        return self.products[key]

    def code(self, key: str) -> str:
        return self.product(key).product_code


def _file(w: World, blocks: list[tuple[str, list[tuple[str, float]]]]) -> bytes:
    rows: list[list] = []
    for container, items in blocks:
        if container:
            rows.append([f"货柜号：{container}"])
        rows.append(HEADER)
        rows.extend([w.code(k), "座厕", qty, 2, 0.21] for k, qty in items)
        rows.append([])
    return workbook(rows)


def _shipments(db, w: World) -> list[InboundShipment]:
    return (
        db.query(InboundShipment)
        .filter(InboundShipment.supplier_id == w.supplier.id)
        .order_by(InboundShipment.shipment_number)
        .all()
    )


def test_each_container_block_becomes_its_own_shipment():
    # AC-G1. One document, several containers, several shipments.
    with pg_session() as db:
        w = World(db)
        data = _file(w, [
            (f"{MARKER}U1", [("A", 10), ("B", 20)]),
            (f"{MARKER}U2", [("C", 5)]),
        ])

        out = svc.apply(db, data, supplier_id=str(w.supplier.id), actor_id=None)

        assert out["shipments_created"] == 2
        rows = _shipments(db, w)
        assert [r.shipping_container_number for r in rows] == [f"{MARKER}U1", f"{MARKER}U2"]
        assert sorted(len(r.shipment_lines) for r in rows) == [1, 2]


def test_re_uploading_the_same_file_creates_no_second_set():
    # AC-G3, and the thing that stops a nervous second click doubling a container.
    with pg_session() as db:
        w = World(db)
        data = _file(w, [(f"{MARKER}U1", [("A", 10)]), (f"{MARKER}U2", [("B", 5)])])

        svc.apply(db, data, supplier_id=str(w.supplier.id))
        second = svc.apply(db, data, supplier_id=str(w.supplier.id))

        assert second["shipments_created"] == 0
        assert second["shipments_updated"] == 2
        assert len(_shipments(db, w)) == 2


def test_a_pre_load_block_with_no_container_still_imports_and_stays_one_shipment():
    # AC-G2 and AC-G3 together: no container number, and re-uploading still does not duplicate.
    with pg_session() as db:
        w = World(db)
        data = _file(w, [("", [("A", 10)]), ("", [("B", 5)])])

        first = svc.apply(db, data, supplier_id=str(w.supplier.id), source_ref="preload-aug.xlsx")
        second = svc.apply(db, data, supplier_id=str(w.supplier.id), source_ref="preload-aug.xlsx")

        assert first["shipments_created"] == 2
        assert second["shipments_created"] == 0
        rows = _shipments(db, w)
        assert len(rows) == 2
        assert all(r.shipping_container_number is None for r in rows)
        # Named by the file and the position, so the two blank blocks are distinguishable.
        assert {r.shipment_number for r in rows} == {"PRELOAD-preload-aug-1", "PRELOAD-preload-aug-2"}


def test_a_code_we_do_not_hold_is_named_rather_than_invented():
    with pg_session() as db:
        w = World(db)
        rows = [[f"货柜号：{MARKER}U1"], HEADER,
                [w.code("A"), "座厕", 10, 1, 0.2],
                ["NOT-A-REAL-CODE", "座厕", 4, 1, 0.2]]

        out = svc.apply(db, workbook(rows), supplier_id=str(w.supplier.id))

        assert out["unmatched_item_codes"] == ["NOT-A-REAL-CODE"]
        assert out["lines_skipped"] == 1
        assert len(_shipments(db, w)[0].shipment_lines) == 1


def test_a_block_whose_every_line_is_unknown_creates_no_empty_shipment():
    # A shipment with no lines is a row somebody has to explain later.
    with pg_session() as db:
        w = World(db)
        rows = [[f"货柜号：{MARKER}U9"], HEADER, ["NOPE-1", "座厕", 4, 1, 0.2]]

        out = svc.apply(db, workbook(rows), supplier_id=str(w.supplier.id))

        assert out["shipments_created"] == 0
        assert _shipments(db, w) == []
        assert "matched a product" in out["results"][0]["reason"]


def test_the_preview_describes_every_block_before_anything_is_written():
    with pg_session() as db:
        w = World(db)
        data = _file(w, [(f"{MARKER}U1", [("A", 10), ("B", 20)]), (f"{MARKER}U2", [("C", 5)])])

        out = svc.preview(db, data)

        assert out["ok"] is True
        assert out["block_count"] == 2
        assert out["line_count"] == 3
        assert [b["qty"] for b in out["blocks"]] == [30, 5]
        assert _shipments(db, w) == []


def test_validate_names_the_codes_it_could_not_match():
    with pg_session() as db:
        w = World(db)
        rows = [HEADER, [w.code("A"), "座厕", 10, 1, 0.2], ["MISSING-1", "座厕", 4, 1, 0.2]]

        out = svc.validate(db, workbook(rows))

        assert out["valid"] is True
        assert any("MISSING-1" in warn for warn in out["warnings"])


def test_a_file_that_is_not_a_packing_list_is_refused_with_the_reason():
    with pg_session() as db:
        World(db)
        with pytest.raises(AppException) as e:
            svc.apply(db, workbook([["a", "b"], ["c", "d"]]))
        assert e.value.status_code == 422


def test_the_shipment_carries_the_quantities_the_file_stated():
    with pg_session() as db:
        w = World(db)
        data = _file(w, [(f"{MARKER}U1", [("A", 10), ("B", 20)])])

        svc.apply(db, data, supplier_id=str(w.supplier.id), shipment_date=date(2026, 8, 1))

        shipment = _shipments(db, w)[0]
        assert shipment.shipment_date == date(2026, 8, 1)
        assert shipment.total_items_shipped == 30
        by_product = {
            str(ln.product_id): ln for ln in
            db.query(InboundShipmentLine).filter(
                InboundShipmentLine.shipment_id == shipment.id
            ).all()
        }
        assert float(by_product[str(w.product("A").id)].quantity_shipped) == 10
        assert float(by_product[str(w.product("B").id)].quantity_shipped) == 20


def test_the_bill_of_lading_reaches_the_shipment():
    with pg_session() as db:
        w = World(db)
        rows = [[f"货柜号：{MARKER}U1"], ["提单号：BL-991"], HEADER,
                [w.code("A"), "座厕", 3, 1, 0.2]]

        svc.apply(db, workbook(rows), supplier_id=str(w.supplier.id))

        assert _shipments(db, w)[0].bill_of_lading_number == "BL-991"
