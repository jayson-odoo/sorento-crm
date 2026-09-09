"""S9 AC-G1/G2/G3, now narrowed by S3 (AC-C1): a packing-list-alone file never creates
an `inbound_shipments` row any more, so this file tests only what still writes anything
- the standalone `preview`/`validate` (unchanged, `packing_list_service.apply` is
deleted) - and the S2/S3 surviving equivalents everything else moved to. See the retired-
test notes below each removed scenario for where its ground is pinned now.
"""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest

from app.models.import_alias import ImportFieldAlias
from app.models.procurement import InboundShipment, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.error_handler import AppException
from app.services.scm import packing_list_service as svc
from tests._pg_fixture import pg_session

pytestmark = pytest.mark.usefixtures("no_live_llm")

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


# --------------------------------------------------------------------------------- #
# S3 (AC-C1): `packing_list_service.apply` is deleted outright - a packing-list-alone
# file never creates an `inbound_shipments` row any more (a shipment is born by convert
# or by hand, AC-C2). The five tests this section used to hold pinned exactly that
# reader-to-shipment path (blocks become shipments, dedupe of that route, the pre-load
# variant of it, an unknown code inside a shipment line, an empty block creating no
# shipment) - all retired outright rather than ported, because the behaviour itself is
# gone, not moved:
#   - "each container block becomes its own shipment" / "re-uploading creates no second
#     set" / "a pre-load block still imports and stays one shipment" (AC-G1/G2/G3) -
#     the pre-load-no-container half is still pinned at the reader
#     (`test_packing_list_reader.py::test_a_pre_load_list_with_no_container_and_no_
#     bill_of_lading_still_reads`); the shipment-creation and dedupe halves have no
#     surviving equivalent to port to.
#   - "a code we do not hold is named rather than invented" - the surviving equivalent
#     (a resolved-or-not PRODUCT, never an invented one) is pinned at the S2 packing-rows
#     level already: `test_proforma_invoice_packing_lines.py::test_b4_jiexia_lid_row_is_
#     an_unmatched_packing_row_never_an_invoice_line` asserts `match_state == "unmatched"`
#     for exactly this case.
#   - "a block whose every line is unknown creates no empty shipment" - there is no
#     shipment to be empty or not any more; nothing to port.
# --------------------------------------------------------------------------------- #


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


# "a file that is not a packing list is refused with the reason" (svc.apply, 422) is
# retired: the surviving equivalent is the unified upload's own refusal,
# `test_supplier_document_service.py::test_apply_refuses_the_whole_batch_when_one_file_
# is_unclassifiable`, which already pins the same 422-with-a-reason for an unclassifiable
# file at the channel operators actually upload through.

# "the shipment carries the quantities the file stated" is retired outright: it pinned
# `packing_list_service.apply`'s own arithmetic (sum -> `total_items_shipped`, one row's
# `quantity_shipped` per product), and `InboundShipmentService.create_shipment` - the
# surviving writer, per AC-C2 ("a shipment is born by convert or by hand") - already has
# that exact ground covered from the hand side: `test_packing_list_multi_supplier.py` and
# `test_packing_list_split_lines.py` both assert `quantity_shipped` values landed from a
# `create_shipment` call across many scenarios. Nothing here would pin new ground.


def test_a_blocks_bl_no_fills_the_attached_invoices_bl_ref_when_it_stated_none():
    """Q1's own ruling (`提单号` is a booking reference, never invented as a bill-of-
    lading number) still holds, but the field it fills moved: since S3 a packing-list-
    alone file never creates a shipment (AC-C1) - it attaches to a PROFORMA INVOICE
    instead, and it is the invoice's own `bl_ref` that the block's 提单号 fills when the
    invoice itself stated none (S2/S4/S5 ruling, `supplier_document_service.apply`)."""
    from app.models.scm import ProformaInvoice
    from app.services.scm import supplier_document_service
    from app.services.scm.proforma_invoice_service import get_or_404

    with pg_session() as db:
        w = World(db)
        invoice = ProformaInvoice(
            id=str(uuid.uuid4()), supplier_id=w.supplier.id, pi_number="PI-1",
            container_ref=f"{MARKER}U1",
        )
        db.add(invoice)
        db.commit()

        rows = [[f"货柜号：{MARKER}U1"], ["提单号：BL-991"], HEADER,
                [w.code("A"), "座厕", 3, 1, 0.2]]

        supplier_document_service.apply(
            db, [("pl.xlsx", workbook(rows), None)], supplier_id=str(w.supplier.id),
        )
        db.commit()

        refreshed = get_or_404(db, invoice.id)
        assert refreshed.bl_ref == "BL-991"


def test_a_code_another_company_also_uses_resolves_to_ours():
    """Product codes are not unique across companies, and raw SQL has no company filter.

    Unscoped, the lookup matched whichever row came back first, so a document could be
    received against ANOTHER company's product. It imported cleanly and then had nothing to
    allocate, because that product has no purchase order of ours to draw down - a failure that
    looks like missing data rather than the wrong row.

    Ported from `packing_list_service.apply` (deleted, AC-C1) to `proforma_invoice_
    service.apply`: the SAME `_products_by_code` guard the packing-list channel used to
    exercise is shared code, called from `proforma_invoice_service.apply` (a document's own
    lines) and from `proforma_invoice_packing_service.replace_packing_rows` (a packing
    list's rows) alike - so pinning it here still pins the packing channel's own safety.
    """
    from app.models.company import Company
    from app.services.scm import proforma_invoice_service

    with pg_session() as db:
        w = World(db)
        mine = w.product("A")
        other_company = Company(
            id=str(uuid.uuid4()),
            name=f"{MARKER} other company",
            code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        )
        db.add(other_company)
        db.flush()

        # Stamped explicitly: the auto-stamp fills Sorento when company_id is None, which
        # would collide with `mine` on (company_id, product_code) before the point is made.
        twin = Product(
            id=str(uuid.uuid4()), product_code=mine.product_code,
            product_name=f"{MARKER} twin", category_id=w.cat.id, base_uom_id=w.uom.id,
            list_price=0, is_active=True, is_discontinued=False,
            company_id=str(other_company.id),
        )
        db.add(twin)
        db.flush()

        data = workbook([["产品型号", "数量", "PRICE"], [mine.product_code, 3, 12.5]])
        proforma_invoice_service.apply(
            db, data, supplier_id=str(w.supplier.id), currency="USD",
        )

        from app.models.scm import ProformaInvoice, ProformaInvoiceLine

        invoice = (
            db.query(ProformaInvoice).filter(ProformaInvoice.supplier_id == w.supplier.id).one()
        )
        line = (
            db.query(ProformaInvoiceLine)
            .filter(ProformaInvoiceLine.invoice_id == invoice.id)
            .one()
        )
        assert str(line.product_id) == str(mine.id)


# --------------------------------------------------------------------------------- #
# G3c / AC-P5 - the pre-loading list stops dropping its prices.
# --------------------------------------------------------------------------------- #


# "the shipment line carries the unit price and currency the file stated" and "an
# unpriced file is unaffected" are retired: since S2 a packing list never carries a price
# to persistence at all - `ProformaInvoicePackingLine` (the row a packing list writes,
# `replace_packing_rows`) has no `unit_cost`/`currency` column, price lives only on the
# proforma invoice's own lines. There is nothing left to port either half onto; the
# standalone `preview`/`validate` still report a file's `priced_lines`/`currency` for
# whoever calls them directly (unchanged, still covered below and by
# `test_validate_names_the_codes_it_could_not_match`), but nothing WRITES a price off a
# packing list any more, so "carries" and "unaffected" are both statements about a write
# that does not happen.


def test_a_priced_file_with_no_resolvable_currency_is_refused():
    # AC-P5.2. `validate` still runs the same currency resolution and refusal on a
    # standalone packing-list preview; `apply`'s own refusal of the same file is retired
    # (S3, AC-C1) rather than ported - a packing list never writes a price, so there is
    # nothing left for a missing currency to block at write time.
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


def test_a_supplier_id_that_is_not_an_id_is_a_422_not_a_500():
    """The packing-list channel takes the supplier on the form, and the currency resolution it
    runs consults that supplier's price list - a UUID column comparison. A typed value that
    is not an id reached it raw and came back as a 500 with the session aborted, while the same
    value on the proforma channel was a 422 naming the field. `apply`'s own entry point is
    retired (AC-C1); `preview`/`validate` are the two that remain, and the guard is one
    function shared by both.
    """
    with pg_session() as db:
        w = World(db)
        data = _file(w, [(f"{MARKER}U9", [("A", 4)])])

        for call in (
            lambda: svc.preview(db, data, supplier_id="not-a-uuid"),
            lambda: svc.validate(db, data, supplier_id="not-a-uuid"),
        ):
            with pytest.raises(AppException) as exc:
                call()
            assert exc.value.status_code == 422
            assert exc.value.detail["detail"] == "supplier_id"


def test_a_supplier_we_do_not_hold_is_refused_before_anything_is_read():
    # `apply`'s own refusal is retired with the route (AC-C1); `preview`'s is the
    # surviving entry point and runs the same `_check_supplier` guard before `_parse`.
    with pg_session() as db:
        w = World(db)
        data = _file(w, [(f"{MARKER}UA", [("A", 4)])])

        with pytest.raises(AppException) as exc:
            svc.preview(db, data, supplier_id=str(uuid.uuid4()))

        assert exc.value.status_code == 422
