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

from app.models.import_alias import ImportFieldAlias
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


def test_a_code_another_company_also_uses_resolves_to_ours():
    """Product codes are not unique across companies, and raw SQL has no company filter.

    Unscoped, the lookup matched whichever row came back first, so a packing list could be
    received against ANOTHER company's product. It imported cleanly and then had nothing to
    allocate, because that product has no purchase order of ours to draw down - a failure that
    looks like missing data rather than the wrong row.
    """
    from sqlalchemy import text

    with pg_session() as db:
        w = World(db)
        mine = w.product("A")
        other_company = db.execute(
            text("SELECT id FROM companies WHERE id <> :sorento LIMIT 1"),
            {"sorento": "00000000-0000-0000-0000-000000000001"},
        ).scalar()
        if other_company is None:
            pytest.skip("this database has only one company, so there is nothing to confuse")

        # Stamped explicitly: the auto-stamp fills Sorento when company_id is None, which
        # would collide with `mine` on (company_id, product_code) before the point is made.
        twin = Product(
            id=str(uuid.uuid4()), product_code=mine.product_code,
            product_name=f"{MARKER} twin", category_id=w.cat.id, base_uom_id=w.uom.id,
            list_price=0, is_active=True, is_discontinued=False,
            company_id=str(other_company),
        )
        db.add(twin)
        db.flush()

        svc.apply(db, _file(w, [(f"{MARKER}U1", [("A", 3)])]), supplier_id=str(w.supplier.id))

        line = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == _shipments(db, w)[0].id)
            .one()
        )
        assert str(line.product_id) == str(mine.id)


# --------------------------------------------------------------------------------- #
# G3c / AC-P5 - the pre-loading list stops dropping its prices.
# --------------------------------------------------------------------------------- #


def _priced_file(w: World, container: str, items: list[tuple[str, float, float]]) -> bytes:
    """Like `_file`, but with an RMB unit-price column, priced per line."""
    rows: list[list] = []
    if container:
        rows.append([f"货柜号：{container}"])
    rows.append(HEADER + ["RMB"])
    rows.extend([w.code(k), "座厕", qty, 2, 0.21, price] for k, qty, price in items)
    rows.append([])
    return workbook(rows)


def test_the_shipment_line_carries_the_unit_price_and_currency_the_file_stated():
    # AC-P5.1. "RMB" in the header states CNY; the price is no longer parsed and dropped.
    with pg_session() as db:
        w = World(db)
        data = _priced_file(w, f"{MARKER}U1", [("A", 10, 25.5)])

        svc.apply(db, data, supplier_id=str(w.supplier.id))

        line = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == _shipments(db, w)[0].id)
            .one()
        )
        assert float(line.unit_cost) == 25.5
        assert line.currency == "CNY"


def test_a_priced_file_with_no_resolvable_currency_is_refused():
    # AC-P5.2. A price with no currency anywhere is refused, not stored guessing one.
    # The real packing-list aliases (RMB / 金额（rmb）) always hint CNY, so a NEUTRAL
    # unit-price header is seeded here, scoped to this test, to reproduce the file that
    # states a price under a column name that names no currency at all.
    with pg_session() as db:
        w = World(db)
        alias = f"{MARKER}COST"
        db.add(ImportFieldAlias(doc_type="packing_list", field="unit_price", alias=alias))
        db.flush()

        rows = [HEADER + [alias], [w.code("A"), "座厕", 10, 2, 0.21, 25.5]]
        data = workbook(rows)

        result = svc.validate(db, data)
        assert result["valid"] is False
        assert any("curren" in e.lower() for e in result["errors"])

        with pytest.raises(AppException) as exc:
            svc.apply(db, data, supplier_id=str(w.supplier.id))
        assert exc.value.status_code == 422
        assert _shipments(db, w) == []


def test_an_unpriced_file_is_unaffected():
    # AC-P5.2, second half: no price anywhere means no currency is demanded, and the
    # existing (pre-price) behaviour of this whole file keeps passing unchanged.
    with pg_session() as db:
        w = World(db)
        data = _file(w, [(f"{MARKER}U1", [("A", 10)])])

        svc.apply(db, data, supplier_id=str(w.supplier.id))

        line = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == _shipments(db, w)[0].id)
            .one()
        )
        assert line.unit_cost is None
        assert line.currency is None


def test_a_blank_bill_of_lading_label_does_not_swallow_the_next_label():
    # AC-P2.4, pinned at the packing-list channel too: the shared `_labelled` helper's
    # fix lives once and must not read a candidate that itself resolves to a KNOWN field
    # (here "货柜号：..." after a blank "提单号：") as if it were a value.
    with pg_session() as db:
        w = World(db)
        rows = [
            ["提单号：", None, f"货柜号：{MARKER}U9"],
            HEADER,
            [w.code("A"), "座厕", 5, 1, 0.2],
        ]

        svc.apply(db, workbook(rows), supplier_id=str(w.supplier.id))

        shipment = _shipments(db, w)[0]
        assert shipment.bill_of_lading_number is None
        assert shipment.shipping_container_number == f"{MARKER}U9"


def test_one_product_on_two_lines_at_two_prices_merges_to_the_weighted_average():
    """The same product twice in one block is merged into one shipment line (the row is
    one per product), and the merged line used to keep whichever price came FIRST.

    That silently values the whole quantity at one of the two prices - here 100 units would
    have been costed at 10.00 instead of 12.00 - and the difference is invisible afterwards
    because the two lines no longer exist separately. The honest merged figure is the
    quantity-weighted average, which is what the container actually cost per unit.
    """
    with pg_session() as db:
        w = World(db)
        rows = [
            [f"货柜号：{MARKER}U5"],
            HEADER + ["RMB"],
            [w.code("A"), "座厕", 40, 2, 0.21, 10],
            [w.code("A"), "座厕", 60, 2, 0.21, 13.5],
        ]

        svc.apply(db, workbook(rows), supplier_id=str(w.supplier.id))

        line = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == _shipments(db, w)[0].id)
            .one()
        )
        assert float(line.quantity_shipped) == 100
        # (40 x 10 + 60 x 13.5) / 100
        assert float(line.unit_cost) == pytest.approx(12.1)
        assert line.currency == "CNY"


def test_a_supplier_id_that_is_not_an_id_is_a_422_not_a_500():
    """The packing-list channel takes the supplier on the form, and the currency resolution it
    now runs consults that supplier's price list - a UUID column comparison. A typed value that
    is not an id reached it raw and came back as a 500 with the session aborted, while the same
    value on the proforma channel was a 422 naming the field. Both channels answer the same way
    now, on all three entry points, because the guard is one function.
    """
    with pg_session() as db:
        w = World(db)
        data = _file(w, [(f"{MARKER}U9", [("A", 4)])])

        for call in (
            lambda: svc.preview(db, data, supplier_id="not-a-uuid"),
            lambda: svc.validate(db, data, supplier_id="not-a-uuid"),
            lambda: svc.apply(db, data, supplier_id="not-a-uuid"),
        ):
            with pytest.raises(AppException) as exc:
                call()
            assert exc.value.status_code == 422
            assert exc.value.detail["detail"] == "supplier_id"


def test_a_supplier_we_do_not_hold_is_refused_before_anything_is_read():
    with pg_session() as db:
        w = World(db)
        data = _file(w, [(f"{MARKER}UA", [("A", 4)])])

        with pytest.raises(AppException) as exc:
            svc.apply(db, data, supplier_id=str(uuid.uuid4()))

        assert exc.value.status_code == 422
        assert not _shipments(db, w)
