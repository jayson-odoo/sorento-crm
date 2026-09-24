"""Red tests for PI header fields, convert-with-repeated-products, and async packing-list
download (PLAN-pi-header-fields-convert-fixes-24sep.md).

Phase 2, tester-first: written BEFORE the coder touches the backend, from the UAC
(`pi-header-fields-convert-fixes-24sep-acceptance-criteria.md`), the plan's design sections
A-F, and the captain's own test list. Every test below exercises PRODUCTION code that exists
today (the reader, the packing-service binder, the convert grouping, the mapper probe/save,
the export route) and pins the NEW contract - so each one is expected to fail for a clean,
specific reason: a missing dict key (`header_fields`, `seal_no`, `convert_carry`), a 404 for
a route that is not mounted yet, an AttributeError for a task function that does not exist,
or a wrong number/None where the fixed reader should have split a multi-pair cell.

Postgres only (`requires_pg` / `pg_session` / `scm_app`, same substrate as every other SCM
route suite here), and every row is seeded fresh under a `ZZPIH` marker or inside a fresh
company - nothing is borrowed from an existing table, and CI's database starts empty.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event, text

from tests._pg_fixture import pg_session
from tests.scm.conftest import grant_permission, requires_pg
from tests.scm.test_import_column_mapper import _XLSX, _create_supplier, _fixture
from tests.scm.test_order_sheet_export_downloads import _NoCloseSession, _savepoint_session
from tests.scm.test_outstanding_import_routes import as_company_user
from tests.scm.test_proforma_invoice_import import workbook

pytestmark = requires_pg

MARKER = "ZZPIH"


def _u() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------------- #
# Shared seeding helpers
# --------------------------------------------------------------------------------- #


def _seed_company_and_products(db, tag: str, codes: list[str]):
    """A fresh company (scoped on `db`), a supplier, and one real `Product` per code in
    `codes` - the exact spelling `_products_by_code` matches on (case-insensitive,
    company-scoped). Returns (company_id, supplier_id, {code: product_id})."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.procurement import Supplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    company_id = _u()
    db.add(Company(
        id=company_id, name=f"{MARKER} co {tag}",
        code=f"{MARKER}{tag}"[:50], is_active=True,
    ))
    db.flush()
    set_company_scope(db, frozenset({company_id}))

    cat = ProductCategory(id=_u(), category_code=f"{MARKER}-CAT-{tag}", category_name="cat")
    uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()

    supplier_id = _u()
    db.add(Supplier(
        id=supplier_id, supplier_code=f"{MARKER}-S-{tag}",
        supplier_name=f"{MARKER} supplier {tag}", is_active=True,
    ))
    db.flush()

    product_ids: dict[str, str] = {}
    for code in codes:
        pid = _u()
        db.add(Product(
            id=pid, product_code=code, product_name=code,
            category_id=cat.id, base_uom_id=uom.id, list_price=0,
            is_active=True, is_discontinued=False,
        ))
        product_ids[code] = pid
    db.flush()
    return company_id, supplier_id, product_ids


def _big_container_size(db, tag: str) -> str:
    """A container size with essentially unlimited volume, so a capacity refusal never
    shadows the assertion under test - these tests are about which LINES a convert
    produces, not the capacity gate."""
    from app.models.scm import ContainerSize

    cs_id = _u()
    db.add(ContainerSize(
        id=cs_id, code=f"{MARKER}-BIG-{tag}"[:30], label="huge", cbm=Decimal("999999"),
        is_default=False, is_active=True,
    ))
    db.flush()
    return cs_id


#: Every distinct item_code on the real DAFUYUAN fixture's 15 data rows (rows 16-30),
#: measured with openpyxl - CWCY604 (3x), CWCX604-S-RL-NEW (2x), CWCX1009-SH (3x),
#: CWCY1009 (3x) are the repeated ones C1/C2 are about.
_DAFUYUAN_CODES = [
    "CWCY604", "CWCX604-S-RL", "CWCX604-S-RL-NEW", "CWCSC604-QQ",
    "CWCX1009-SH", "CWCY1009", "SRTWC8066-SH-UF",
]


def _seed_dafuyuan_products(db, tag: str) -> None:
    """One real `Product` per DAFUYUAN item_code, under whatever company is currently
    scoped on `db` - so `apply()`'s `_products_by_code` (and later `convert_to_draft_
    shipment`'s grouping, which needs a `product_id` to have anything to group) resolves
    every line rather than refusing the whole convert as unmatched."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    cat = ProductCategory(id=_u(), category_code=f"{MARKER}-CAT-{tag}", category_name="cat")
    uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    for code in _DAFUYUAN_CODES:
        db.add(Product(
            id=_u(), product_code=code, product_name=code,
            category_id=cat.id, base_uom_id=uom.id, list_price=0,
            is_active=True, is_discontinued=False,
        ))
    db.flush()


def _save_dafuyuan_unit_price_mapping(db, supplier_id: str) -> None:
    """DAFUYUAN's own price header `单价 (RMB)` has no SHARED alias (only bare `RMB` and
    `单价` do) - a supplier-scoped mapping is what `test_pi_preview_oolu_and_dafuyuan_numbers`
    (test_import_column_mapper.py) already proves resolves header row 14."""
    from app.services.scm import import_mapping_service

    import_mapping_service.save(
        db, supplier_id=supplier_id, doc_types=["proforma_invoice"],
        mappings=[("单价 (RMB)", "unit_price")],
    )
    db.flush()


# =================================================================================== #
# H1/H2/H3/H4 - the header cell splits into its several label:value pairs (design A)
# =================================================================================== #


def test_H1_dafuyuan_header_cell_splits_bl_container_seal(scm_app):
    """AC-H1: DAFUYUAN's one cell `提单号 ：OOLU… 柜号 ：FSCU… 封条号：OOLLGZ7182` must
    become THREE separate document facts, not one field holding the whole cell.

    Today `_labelled` only ever partitions a cell on its FIRST colon (no ` / ` / `／`
    separator here), so `bl_no` comes back as the entire tail and `container_no`/`seal_no`
    are never reached - this is expected to fail on the container/seal asserts."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role="purchasing")
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    client = TestClient(app)

    supplier_id = _create_supplier(db, code_suffix="H1")
    _save_dafuyuan_unit_price_mapping(db, supplier_id)

    r = client.post(
        "/api/v1/scm/proforma-invoices/preview",
        files={"file": ("dafuyuan.xlsx", _fixture("dafuyuan_pi_20260922.xlsx"), _XLSX)},
        data={"supplier_id": supplier_id, "header_row": "14"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, body
    doc = body["documents"][0]

    assert doc["bl_no"] == "OOLU2339207730", doc
    assert doc["container_no"] == "FSCU9304169", doc
    # `seal_no` is not even on the preview summary today (design A3) - `.get` so a missing
    # key reads as an honest None rather than a KeyError masking the real assertion.
    assert doc.get("seal_no") == "OOLLGZ7182", doc


def test_H2_new_yanggang_bl_empty_container_and_bare_seal_alias(scm_app):
    """AC-H2: `提单号：   柜号：FSCU8706420   封条：OOLLJN6147` - BL states no value (empty),
    container splits out, and the BARE `封条` label (not `封条号`/`封签号`) resolves seal_no
    once the A2 shared alias lands."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role="purchasing")
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    client = TestClient(app)

    supplier_id = _create_supplier(db, code_suffix="H2")
    from app.services.scm import import_mapping_service

    import_mapping_service.save(
        db, supplier_id=supplier_id, doc_types=["proforma_invoice"],
        mappings=[
            ("客户型号", "item_code"),
            ("总数量\n（个）", "qty"),
            ("单价\n（元）", "unit_price"),
        ],
    )
    db.flush()

    r = client.post(
        "/api/v1/scm/proforma-invoices/preview",
        files={"file": ("ny_fscu.xlsx", _fixture("ny_pi_FSCU8706420.xlsx"), _XLSX)},
        data={"supplier_id": supplier_id, "header_row": "15"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, body
    doc = body["documents"][0]

    assert doc["bl_no"] is None, doc
    assert doc["container_no"] == "FSCU8706420", doc
    assert doc.get("seal_no") == "OOLLJN6147", doc


def test_H3_single_pair_unchanged_and_first_labelled_value_wins():
    """AC-H3 (unchanged-behaviour guard + a new-alias dependency in one function):

    Scenario A - a single-pair cell (`提单号：ABC123`) reads exactly as it does today,
    and a label three rows further down (`柜号：XYZ999`) still names the SAME document's
    container - this half already passes; it is here so a future regression on the split
    path is caught alongside the new behaviour.

    Scenario B - a label stating no value (`提单号：`) contributes nothing, and a LATER
    row stating the real one (`提单号：REAL`) is what `_absorb`'s first-wins keeps -
    already-existing behaviour, asserted here as a guard.
    """
    from app.services.scm.proforma_invoice_reader import read_workbook

    with pg_session() as db:
        data_a = workbook([
            [f"{MARKER} H3a letterhead"],
            ["提单号：ABC123"],
            [],
            [],
            ["柜号：XYZ999"],
            [],
            ["产品型号", "数量", "单价"],
            ["CODE1", 5, 10],
        ])
        result_a = read_workbook(data_a, db=db)
        assert result_a.documents, result_a.problems
        doc_a = result_a.documents[0]
        assert doc_a.bl_no == "ABC123", doc_a
        # RED half: 柜号 has no shared alias yet (design A2) - once it lands this splits
        # the same way container_no does on the real DAFUYUAN cell (H1).
        assert doc_a.container_no == "XYZ999", doc_a

        data_b = workbook([
            [f"{MARKER} H3b letterhead"],
            ["提单号："],
            [],
            ["提单号：REAL"],
            [],
            ["产品型号", "数量", "单价"],
            ["CODE1", 5, 10],
        ])
        result_b = read_workbook(data_b, db=db)
        assert result_b.documents, result_b.problems
        doc_b = result_b.documents[0]
        assert doc_b.bl_no == "REAL", doc_b


def test_H4_apply_writes_container_bl_seal_refs_onto_the_pi_row(scm_app):
    """AC-A3/D2c's own precondition: apply() must persist what the reader now parses onto
    `proforma_invoice.container_ref` / `bl_ref` / `seal_ref` - convert's header carry-over
    (B1) reads these columns, not the reader's in-memory document."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role="purchasing")
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    client = TestClient(app)

    supplier_id = _create_supplier(db, code_suffix="H4")
    _save_dafuyuan_unit_price_mapping(db, supplier_id)

    r = client.post(
        "/api/v1/scm/proforma-invoices/apply",
        files={"file": ("dafuyuan.xlsx", _fixture("dafuyuan_pi_20260922.xlsx"), _XLSX)},
        data={"supplier_id": supplier_id, "header_row": "14"},
    )
    assert r.status_code == 200, r.text

    row = db.execute(
        text(
            "SELECT container_ref, bl_ref, seal_ref FROM scm.proforma_invoice "
            "WHERE supplier_id = :sid"
        ),
        {"sid": supplier_id},
    ).mappings().first()
    assert row is not None, "apply did not create a proforma_invoice row"
    assert row["bl_ref"] == "OOLU2339207730", row
    assert row["container_ref"] == "FSCU9304169", row
    assert row["seal_ref"] == "OOLLGZ7182", row


# =================================================================================== #
# F1/F2 - header fields in the import mapper (design F, R-D)
# =================================================================================== #


def test_F1_probe_returns_header_fields_for_dafuyuan():
    """AC-F1/F2: every `label：value` pair ABOVE the table header (and, per F1, a label
    cell followed by its value in the NEXT cell) comes back as a `header_fields` entry -
    `{row, label, sample, field, source}` - and a title cell with no colon
    (`PROFORMA INVOICE - 形式发票`) is never one of them."""
    from app.services.scm import import_mapping_service

    with pg_session() as db:
        from app.models.base import set_company_scope
        from app.models.company import Company
        from app.models.procurement import Supplier

        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} F1 co", code=f"{MARKER}F1"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        supplier_id = _u()
        db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-F1", supplier_name="F1 supplier", is_active=True))
        db.flush()

        result = import_mapping_service.probe(
            db, _fixture("dafuyuan_pi_20260922.xlsx"),
            supplier_id=supplier_id, doc_types=["proforma_invoice"], header_row=14,
        )

        assert "header_fields" in result, sorted(result.keys())
        entries = result["header_fields"]
        by_label = {e["label"].strip(): e for e in entries}

        assert "提单号" in by_label, by_label.keys()
        assert by_label["提单号"]["sample"] == "OOLU2339207730", by_label["提单号"]
        assert by_label["提单号"]["field"] == "bl_no", by_label["提单号"]

        assert "柜号" in by_label, by_label.keys()
        assert by_label["柜号"]["sample"] == "FSCU9304169", by_label["柜号"]

        assert "封条号" in by_label, by_label.keys()
        assert by_label["封条号"]["sample"] == "OOLLGZ7182", by_label["封条号"]
        assert by_label["封条号"]["field"] == "seal_no", by_label["封条号"]

        assert "Date:" in by_label, by_label.keys()
        assert "2026" in str(by_label["Date:"]["sample"]), by_label["Date:"]
        assert by_label["Date:"]["field"] == "invoice_date", by_label["Date:"]

        assert "PI No.:" in by_label, by_label.keys()
        assert by_label["PI No.:"]["sample"] == "DFY20260922", by_label["PI No.:"]
        assert by_label["PI No.:"]["field"] == "pi_number", by_label["PI No.:"]

        for e in entries:
            assert set(e.keys()) >= {"row", "label", "sample", "field", "source"}, e
            assert e["field"] != "consignee", e

        # Title cells with no colon are never header_fields (F1).
        titles = {"PROFORMA INVOICE - 形式发票", "DAFUYUAN CERAMIC INDUSTRIAL LIMITED"}
        assert not (titles & set(by_label.keys())), by_label.keys()


def test_F2_supplier_scoped_header_field_splits_and_currency_field_is_accepted():
    """AC-F3/F4: a header-field mapping saved for ONE supplier resolves through
    `for_supplier` the same way a column mapping does, with no admin-page edit and no
    dependency on the shared alias landing. Also pins a real contract mismatch: the PI
    reader's own canonical currency field is `currency` (`_BLOCK_FIELDS`), but
    `canonical_fields("proforma_invoice")` currently lists the dataclass name
    `currency_hint` instead - so `save()` 422s a header-field pick of `currency` today."""
    from app.services.scm import import_mapping_service, proforma_invoice_service

    with pg_session() as db:
        from app.models.base import set_company_scope
        from app.models.company import Company
        from app.models.procurement import Supplier

        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} F2 co", code=f"{MARKER}F2"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        supplier_id = _u()
        db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-F2", supplier_name="F2 supplier", is_active=True))
        db.flush()

        # Defensive against A2 landing first (owner ruling in the captain's brief): delete
        # any shared 柜号 alias so this proves the SUPPLIER row alone resolves it.
        db.execute(
            text(
                "DELETE FROM import_field_alias WHERE doc_type = 'proforma_invoice' "
                "AND alias = :a AND supplier_id IS NULL"
            ),
            {"a": "柜号"},
        )

        import_mapping_service.save(
            db, supplier_id=supplier_id, doc_types=["proforma_invoice"],
            mappings=[
                ("柜号", "container_no"),
                ("单价 (RMB)", "unit_price"),
            ],
        )
        db.flush()

        parsed = proforma_invoice_service.preview(
            db, _fixture("dafuyuan_pi_20260922.xlsx"), supplier_id=supplier_id, header_row=14,
        )
        assert parsed["ok"] is True, parsed
        assert parsed["documents"][0]["container_no"] == "FSCU9304169", parsed["documents"][0]

        # The 422 that `save()` currently raises for `field == "currency"` - a plain
        # `save()` call (no HTTP layer) so the exception's own message is the failure
        # reason, not a route-level status code translation.
        import_mapping_service.save(
            db, supplier_id=supplier_id, doc_types=["proforma_invoice"],
            mappings=[("A CURRENCY LABEL", "currency")],
        )


# =================================================================================== #
# C1/C2/C3 - convert with a repeated product (design C)
# =================================================================================== #


def test_C1_replace_and_rebind_packing_rows_bind_by_sheet_order_not_by_product():
    """AC-C1/repeated-product binder: three packing rows of the SAME product, in sheet
    order (qty 40/125/12), must bind to the three DIFFERENT invoice lines of that product
    in the same order - row i -> line i - never all three onto one line.

    Today `replace_packing_rows` builds `line_by_product = {product_id: line}` over an
    UNORDERED query, so every row of a repeated product collapses onto ONE line (whichever
    happened to win the dict), and `rebind_packing_rows` picks the FIRST matching line
    instead - two different wrong answers to the same question."""
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoicePackingLine
    from app.services.scm.packing_list_reader import PackingLine
    from app.services.scm.proforma_invoice_packing_service import (
        rebind_packing_rows,
        replace_packing_rows,
    )

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        code = f"{MARKER}-CWCY604-{tag}"
        _, supplier_id, product_ids = _seed_company_and_products(db, tag, [code])
        product_id = product_ids[code]

        invoice = ProformaInvoice(
            id=_u(), supplier_id=supplier_id, pi_number=f"PI-{MARKER}-{tag}",
        )
        db.add(invoice)
        db.flush()

        line_ids = []
        for i, qty in enumerate((40, 125, 12), start=1):
            line = ProformaInvoiceLine(
                id=_u(), invoice_id=invoice.id, line_no=i, item_code=code,
                qty=Decimal(qty), unit_price=Decimal("1"), product_id=product_id,
            )
            db.add(line)
            line_ids.append(line.id)
        db.flush()

        packing_lines = [
            PackingLine(row_number=i, item_code=code, qty=float(qty))
            for i, qty in enumerate((40, 125, 12), start=1)
        ]
        replace_packing_rows(db, invoice, packing_lines, supplier_id=supplier_id)
        db.flush()

        rows = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice.id)
            .order_by(ProformaInvoicePackingLine.row_no)
            .all()
        )
        assert len(rows) == 3, rows
        bound = [str(r.proforma_invoice_line_id) for r in rows]
        assert bound == [str(i) for i in line_ids], (
            "each packing row must bind to its own line by sheet order, not collapse "
            f"onto one line: {bound} vs {line_ids}"
        )

        # rebind_packing_rows must agree - same product, same three lines, same order.
        rebind_packing_rows(
            db, supplier_id=supplier_id, code=code, product_id=product_id, product_set_id=None,
        )
        db.flush()
        rows_after = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice.id)
            .order_by(ProformaInvoicePackingLine.row_no)
            .all()
        )
        bound_after = [str(r.proforma_invoice_line_id) for r in rows_after]
        assert bound_after == [str(i) for i in line_ids], bound_after


def test_C2_convert_dafuyuan_yields_fifteen_lines_qty_903_no_orphans(scm_app):
    """AC-C2/AC-C6 (line count half): DAFUYUAN converts to exactly 15 shipment lines
    totalling 903 - the owner's own reported numbers. Today the repeated-product binder
    (C1's bug) leaves some invoice lines with no row of their own, and those lines fall
    back to the (product, supplier) grouping ON TOP of the row-grouped ones, producing
    extra orphan lines and a higher total quantity (the owner saw 20 lines / 1,484)."""
    from app.models.procurement import InboundShipmentLine
    from app.services.scm import import_mapping_service, proforma_invoice_service
    from app.services.scm.packing_list_reader import read_workbook as read_packing_workbook
    from app.services.scm.proforma_invoice_packing_service import replace_packing_rows

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role="purchasing")
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")

    tag = uuid.uuid4().hex[:8]
    _seed_dafuyuan_products(db, tag)

    supplier_id = _create_supplier(db, code_suffix=f"C2{tag}")
    import_mapping_service.save(
        db, supplier_id=supplier_id, doc_types=["proforma_invoice"],
        mappings=[("单价 (RMB)", "unit_price")],
    )
    db.flush()

    out = proforma_invoice_service.apply(
        db, _fixture("dafuyuan_pi_20260922.xlsx"), supplier_id=supplier_id, header_row=14,
    )
    invoice_id = out["results"][0]["invoice_id"] if out.get("results") else None
    assert invoice_id, out
    from app.models.scm import ProformaInvoice

    invoice = db.query(ProformaInvoice).filter(ProformaInvoice.id == invoice_id).one()

    # The SAME file, read as a packing list (its rows carry item_code/qty via already
    # SHARED aliases - no supplier mapping needed for this half).
    packing_result = read_packing_workbook(
        _fixture("dafuyuan_pi_20260922.xlsx"),
        resolver=None, db=db, header_row=14,
    )
    assert packing_result.blocks, packing_result.problems
    lines = packing_result.blocks[0].lines
    assert len(lines) == 15, len(lines)
    replace_packing_rows(db, invoice, lines, supplier_id=supplier_id)
    db.flush()

    container_size_id = _big_container_size(db, tag)
    result = proforma_invoice_service.convert_to_draft_shipment(
        db, [str(invoice.id)], container_size_id=container_size_id,
    )
    shipment_lines = (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == result["shipment_id"])
        .all()
    )
    assert len(shipment_lines) == 15, [
        (str(l.product_id), l.quantity_shipped) for l in shipment_lines
    ]
    assert sum(int(l.quantity_shipped) for l in shipment_lines) == 903, [
        l.quantity_shipped for l in shipment_lines
    ]


def test_C3_backfill_rebinds_a_repeated_product_and_dry_run_writes_nothing():
    """AC-C7: a one-off backfill script rebinds an EXISTING PI whose repeated-product
    packing rows all point at one line - after it runs, the three rows carry three
    DISTINCT line ids; a dry run reports the count (1 affected PI) and writes nothing."""
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoicePackingLine

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        code = f"{MARKER}-CWCY604-{tag}"
        _, supplier_id, product_ids = _seed_company_and_products(db, tag, [code])
        product_id = product_ids[code]

        invoice = ProformaInvoice(id=_u(), supplier_id=supplier_id, pi_number=f"PI-{MARKER}-{tag}")
        db.add(invoice)
        db.flush()

        line_ids = []
        for i in range(1, 4):
            line = ProformaInvoiceLine(
                id=_u(), invoice_id=invoice.id, line_no=i, item_code=code,
                qty=Decimal(10 * i), unit_price=Decimal("1"), product_id=product_id,
            )
            db.add(line)
            line_ids.append(line.id)
        db.flush()

        # The BROKEN shape directly: all three packing rows bound to line_ids[0], the
        # exact state `replace_packing_rows`'s dict-collapse bug leaves behind today.
        for i in range(1, 4):
            db.add(ProformaInvoicePackingLine(
                id=_u(), proforma_invoice_id=invoice.id, row_no=i, item_code=code,
                qty=Decimal(10 * i), product_id=product_id,
                proforma_invoice_line_id=line_ids[0], match_state="matched",
            ))
        db.flush()

        from scripts.rebind_repeated_product_packing_rows import rebind_repeated_products

        dry = rebind_repeated_products(db, dry_run=True)
        assert dry.get("count") == 1, dry
        db.flush()
        rows_after_dry = (
            db.query(ProformaInvoicePackingLine.proforma_invoice_line_id)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice.id)
            .all()
        )
        assert {str(r[0]) for r in rows_after_dry} == {str(line_ids[0])}, (
            "a dry run must write nothing"
        )

        rebind_repeated_products(db, dry_run=False)
        db.flush()
        rows_after = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice.id)
            .order_by(ProformaInvoicePackingLine.row_no)
            .all()
        )
        bound = {str(r.proforma_invoice_line_id) for r in rows_after}
        assert bound == {str(i) for i in line_ids}, (
            f"expected three distinct line ids after the backfill, got {bound}"
        )


# =================================================================================== #
# B1/B3 - convert carries container/seal/SO/consignee (design B)
# =================================================================================== #


def _apply_dafuyuan_pi(db, tag: str):
    """Company + supplier + the DAFUYUAN unit_price mapping + apply() the real file.
    Returns (company_id, supplier_id, invoice)."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.procurement import Supplier
    from app.models.scm import ProformaInvoice
    from app.services.scm import import_mapping_service, proforma_invoice_service

    company_id = _u()
    db.add(Company(id=company_id, name=f"{MARKER} B co {tag}", code=f"{MARKER}B{tag}"[:50], is_active=True))
    db.flush()
    set_company_scope(db, frozenset({company_id}))

    supplier_id = _u()
    db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-B-{tag}", supplier_name="B supplier", is_active=True))
    db.flush()

    _seed_dafuyuan_products(db, tag)

    import_mapping_service.save(
        db, supplier_id=supplier_id, doc_types=["proforma_invoice"],
        mappings=[("单价 (RMB)", "unit_price")],
    )
    db.flush()

    proforma_invoice_service.apply(
        db, _fixture("dafuyuan_pi_20260922.xlsx"), supplier_id=supplier_id, header_row=14,
    )
    invoice = (
        db.query(ProformaInvoice)
        .filter(ProformaInvoice.supplier_id == supplier_id)
        .one()
    )
    return company_id, supplier_id, invoice


def test_B1_convert_carries_container_seal_so_and_company_as_consignee():
    """AC-C6/R-B: the draft shipment gets `shipping_container_number` = the PI's
    container, `seal_number` = the PI's seal, `forwarder_order_ref` (the SO field) = the
    PI's BL (提单号, R-A/6-Sep ruling, unchanged), `consignee` = the PI's OWN COMPANY name
    (R-B, 24 Sep - ALWAYS, never the sheet's own `consignee_ref`), and `shipper` stays
    unset (never stated on this sheet)."""
    from app.models.company import Company
    from app.models.procurement import InboundShipment
    from app.services.scm import proforma_invoice_service

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        company_id, supplier_id, invoice = _apply_dafuyuan_pi(db, tag)

        container_size_id = _big_container_size(db, tag)
        out = proforma_invoice_service.convert_to_draft_shipment(
            db, [str(invoice.id)], container_size_id=container_size_id,
        )
        shipment = (
            db.query(InboundShipment).filter(InboundShipment.id == out["shipment_id"]).one()
        )
        company = db.query(Company).filter(Company.id == company_id).one()

        assert shipment.shipping_container_number == "FSCU9304169", shipment.shipping_container_number
        assert shipment.seal_number == "OOLLGZ7182", shipment.seal_number
        assert shipment.forwarder_order_ref == "OOLU2339207730", shipment.forwarder_order_ref
        assert shipment.consignee == company.name, (shipment.consignee, company.name)
        assert shipment.shipper is None, shipment.shipper


def test_B3_convert_carry_on_the_pi_detail_matches_what_convert_will_write():
    """AC-C5: the PI detail payload names a `convert_carry` object - `{container, seal,
    so, consignee}` - that is exactly what B1's convert will write, so the dialog's
    "Carried onto the draft" line can read the server rather than echo the PI's own
    fields (today's bug: it prints them unconditionally, ignoring the one-container
    condition B1 relies on)."""
    from app.services.scm import proforma_invoice_service

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        _, _, invoice = _apply_dafuyuan_pi(db, tag)

        payload = proforma_invoice_service.serialize(db, invoice)
        assert "convert_carry" in payload, sorted(payload.keys())
        carry = payload["convert_carry"]
        assert carry["container"] == "FSCU9304169", carry
        assert carry["seal"] == "OOLLGZ7182", carry
        assert carry["so"] == "OOLU2339207730", carry
        assert carry["consignee"], carry


def test_B4_pi_detail_consignee_is_the_company():
    """R-B (24 Sep, owner) extends past `convert_carry` (B1/B3): the PI's OWN displayed
    consignee - both the detail payload (`serialize`, what GET .../{id} returns) and the
    upload preview's summary - must be the invoice's own company name too, regardless of
    what the sheet stated (`consignee_ref`/`doc.consignee`). Today `serialize()` still
    returns `invoice.consignee_ref` verbatim and `preview()`'s summary returns the
    reader's raw parsed `doc.consignee` - neither reads the company, so this is red until
    both are pointed at `_company_name_for`/`_convert_carry`'s own company lookup."""
    from app.models.company import Company
    from app.services.scm import proforma_invoice_service

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        company_id, supplier_id, invoice = _apply_dafuyuan_pi(db, tag)
        # A sheet that DID state a consignee, and it differs from the company - proves the
        # detail payload does not just happen to agree because the field was empty.
        invoice.consignee_ref = "SOME OTHER COMPANY SDN BHD"
        db.flush()

        company = db.query(Company).filter(Company.id == company_id).one()

        detail = proforma_invoice_service.serialize(db, invoice)
        assert detail["consignee"] == company.name, (detail["consignee"], company.name)

        preview = proforma_invoice_service.preview(
            db, _fixture("dafuyuan_pi_20260922.xlsx"), supplier_id=supplier_id, header_row=14,
        )
        assert preview["documents"][0]["consignee"] == company.name, (
            preview["documents"][0]["consignee"], company.name,
        )


# =================================================================================== #
# E1/E2 - async packing-list download (design E)
# =================================================================================== #


def test_E1_export_endpoint_creates_download_row_and_lists_it(scm_app, monkeypatch):
    """AC-D1: `POST /inbound-shipments/{id}/packing-list/export` creates a
    `user_downloads` row (`kind="packing_list_xlsx"`, `source_entity_type=
    "inbound_shipment"`, `source_entity_id=<shipment id>`) and it is then visible on the
    per-entity list `GET /api/v1/downloads?source_entity_type=...&source_entity_id=...`.

    R12 (review round 1): `enqueue_job` is patched at its SOURCE
    (`app.services.queue_service`, same as `test_order_sheet_export_downloads.py`'s own
    note explains) BEFORE the request fires - the route re-imports it function-locally on
    every call, so patching the module attribute here is what the route actually calls.
    Un-mocked, this test pushed a REAL job onto the lane's shared Redis `imports` queue,
    which a live worker in another lane could pick up and run against rolled-back test
    data."""
    from app.models.procurement import InboundShipment
    from app.services import queue_service
    from app.tasks.export_tasks import generate_packing_list_xlsx

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role="purchasing")
    grant_permission(db, "purchasing", "scm.dashboard.view")
    client = TestClient(app)

    tag = uuid.uuid4().hex[:8]
    shipment = InboundShipment(
        id=_u(), shipment_number=f"{MARKER}-E1-{tag}", shipment_date=date.today(),
        shipment_status="draft",
    )
    db.add(shipment)
    db.flush()

    calls: list[dict] = []

    def _fake_enqueue(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})

        class _Job:
            id = "fake-job-id"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)

    r = client.post(f"/api/v1/scm/inbound-shipments/{shipment.id}/packing-list/export")
    assert r.status_code == 202, r.text
    body = r.json()

    assert len(calls) == 1, calls
    assert calls[0]["func"] is generate_packing_list_xlsx, calls[0]["func"]
    assert calls[0]["args"] == (body["id"], str(shipment.id)), calls[0]["args"]

    row = db.execute(
        text(
            "SELECT kind, source_entity_type, source_entity_id::text AS source_entity_id "
            "FROM user_downloads WHERE id = :id"
        ),
        {"id": body["id"]},
    ).mappings().first()
    assert row is not None, "no user_downloads row was created"
    assert row["kind"] == "packing_list_xlsx", row
    assert row["source_entity_type"] == "inbound_shipment", row
    assert row["source_entity_id"] == str(shipment.id), row

    listed = client.get(
        "/api/v1/downloads",
        params={"source_entity_type": "inbound_shipment", "source_entity_id": str(shipment.id)},
    )
    assert listed.status_code == 200, listed.text
    ids = [d["id"] for d in listed.json()["downloads"]]
    assert body["id"] in ids, ids


def test_E2_generate_packing_list_xlsx_task_renders_same_bytes_and_marks_ready(scm_app, monkeypatch):
    """AC-D2: the RQ task renders the SAME workbook bytes the existing synchronous export
    (`consolidated_packing_list.to_xlsx`) produces for the same shipment, and marks the
    download row ready - the same pattern `generate_complaint_pdf` already follows."""
    from app.models.company import UserCompany
    from app.models.procurement import InboundShipment
    from app.services.download_service import DownloadService
    from app.services.scm import consolidated_packing_list
    from app.tasks import export_tasks

    app, db, gcu, gcuk = scm_app
    scope = as_company_user(app, db, gcu, gcuk, role="purchasing")

    from tests.scm.conftest import seed_user

    tag = uuid.uuid4().hex[:8]
    uid = seed_user(db, "purchasing")
    shipment = InboundShipment(
        id=_u(), shipment_number=f"{MARKER}-E2-{tag}", shipment_date=date.today(),
        shipment_status="draft",
    )
    db.add(shipment)
    db.flush()

    # R7: the task now refuses a download whose owning user has no membership in the
    # shipment's own company - a real membership row, not just the request-scope override
    # `as_company_user` also installs.
    db.add(UserCompany(id=_u(), user_id=uid, company_id=next(iter(scope))))
    db.flush()

    dl = DownloadService(db).create(
        user_id=uid, kind="packing_list_xlsx", source_entity_type="inbound_shipment",
        source_entity_id=str(shipment.id), filename=f"packing-list-{tag}.xlsx",
    )

    expected_payload = consolidated_packing_list.build(db, str(shipment.id))
    expected_bytes = consolidated_packing_list.to_xlsx(expected_payload)

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

    class _FakeBackend:
        def __init__(self):
            self.uploaded = None

        def upload_file(self, *, file_content, file_path, content_type):
            self.uploaded = file_content
            return (file_path, None)

    backend = _FakeBackend()
    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: backend)

    result = export_tasks.generate_packing_list_xlsx(str(dl.id), str(shipment.id))

    assert result["status"] == "ready", result
    assert backend.uploaded == expected_bytes, "rendered bytes must match the sync export"
    row = DownloadService(db).get(str(dl.id))
    assert row.status == "ready", row.status
    assert row.storage_key, "no storage_key was written"


# =================================================================================== #
# Fix round 1 (review findings) - PLAN-pi-header-fields-convert-fixes-24sep-fixes-24sep.md
# =================================================================================== #


def test_R1_header_fields_saved_as_ignore_stay_known():
    """R1 (blocker AC-F3): a header-field label saved as `ignore` must stay KNOWN on the
    next probe - `field == "ignore"`, `source == "supplier"` - the same as an ignored
    COLUMN already does (`raw_field_for_header`, used by the columns section of `probe`).
    Today `header_field_candidates` (`packing_list_reader.py`) resolves every label
    through `field_for_header`, which folds `IGNORE_FIELD` to `None`, so a saved ignore
    never comes back recognised - the mapper would keep re-showing it on every later
    upload from the same supplier (the opposite of AC-F3's "folds into the summary")."""
    from app.services.scm import import_mapping_service

    with pg_session() as db:
        from app.models.base import set_company_scope
        from app.models.company import Company
        from app.models.procurement import Supplier

        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} R1 co", code=f"{MARKER}R1"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        supplier_id = _u()
        db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-R1", supplier_name="R1 supplier", is_active=True))
        db.flush()

        first = import_mapping_service.probe(
            db, _fixture("dafuyuan_pi_20260922.xlsx"),
            supplier_id=supplier_id, doc_types=["proforma_invoice"], header_row=14,
        )
        entries = first["header_fields"]
        assert entries, "the fixture must yield header_fields to prove anything here"

        # Two picked as REAL fields (the ones TEL/FAX give: nothing a shared alias already
        # answers, so the save is guaranteed to write a genuine supplier row rather than
        # no-op against an existing shared one), everything else ignored.
        mappings = []
        real_picks = {"TEL": "bl_no", "FAX": "seal_no"}
        for e in entries:
            label = e["label"].strip()
            mappings.append((e["label"], real_picks.get(label, "ignore")))
        import_mapping_service.save(
            db, supplier_id=supplier_id, doc_types=["proforma_invoice"], mappings=mappings,
        )
        db.flush()

        second = import_mapping_service.probe(
            db, _fixture("dafuyuan_pi_20260922.xlsx"),
            supplier_id=supplier_id, doc_types=["proforma_invoice"], header_row=14,
        )
        second_entries = second["header_fields"]
        assert second_entries, second

        for e in second_entries:
            assert e["field"] is not None, e
            assert e["source"] == "supplier", e

        by_label = {e["label"].strip(): e["field"] for e in second_entries}
        assert by_label.get("TEL") == "bl_no", by_label
        assert by_label.get("FAX") == "seal_no", by_label
        for label, field in by_label.items():
            if label not in real_picks:
                assert field == "ignore", (label, field)


def test_R2_header_fields_skip_value_cells_and_format_dates():
    """R2: DAFUYUAN's `Date:` pair (label `Date:` in one cell, the value a raw
    `datetime` in the NEXT cell) must format as a plain date - not Python's
    `str(datetime)`, which carries a trailing `00:00:00` nobody typed - and that same
    value cell's OWN embedded colons (`00:00:00`) must never be re-split into a
    spurious `"00"` header field of their own. Today `header_field_candidates` scans
    EVERY cell in the row for inline `label：value` pairs, including cells that are
    themselves already a VALUE for another label, so the date's own string
    representation gets fed back through `_split_label_pairs` a second time."""
    from app.services.scm import import_mapping_service

    with pg_session() as db:
        from app.models.base import set_company_scope
        from app.models.company import Company
        from app.models.procurement import Supplier

        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} R2 co", code=f"{MARKER}R2"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        supplier_id = _u()
        db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-R2", supplier_name="R2 supplier", is_active=True))
        db.flush()

        result = import_mapping_service.probe(
            db, _fixture("dafuyuan_pi_20260922.xlsx"),
            supplier_id=supplier_id, doc_types=["proforma_invoice"], header_row=14,
        )
        entries = result["header_fields"]
        labels = [e["label"].strip() for e in entries]
        assert "00" not in labels, labels

        by_label = {e["label"].strip(): e for e in entries}
        assert "Date:" in by_label, labels
        sample = str(by_label["Date:"]["sample"])
        assert "00:00:00" not in sample, sample
        assert sample.startswith("2026-09-22") or sample == "22/09/2026", sample


def test_R3_note_row_mid_table_does_not_split_documents_and_ignored_label_bounds_value():
    """R3 (M-1): two independent shapes of the same underlying gap - a label recognised
    ANYWHERE in a cell's text, with no regard for whether the cell is a genuine header
    block or running prose in the middle of the line table.

    Part A: a note row (`Note: see PI No.: 123`) sitting BETWEEN two pairs of priced
    lines must never be read as the start of a second document - `_labelled` resolves
    "PI No." out of the sentence (a real block-field alias, matched mid-string) and the
    reader treats that as the label introducing the NEXT container, splitting one
    4-line invoice into two 2-line ones.

    Part B (R-D dependency): a cell holding a recognised label (提单号) followed
    immediately by a SECOND label this supplier has mapped to `ignore` (船名, "vessel
    name") must still bound the first label's VALUE at the second label's own
    position - `bl_no` must read `OOLU1`, not `OOLU1  船名：MSC XYZ`. Today
    `_split_label_pairs`'s boundary search uses `field_for_header` (folds
    `IGNORE_FIELD` to `None`), so a label saved as `ignore` is invisible to it and
    never bounds anything - the same underlying gap R1 fixes for the mapper's own
    probe, here breaking the READER's actual document parse."""
    from app.services.import_alias_service import AliasResolver
    from app.services.scm.proforma_invoice_reader import DOC_TYPE, read_workbook

    with pg_session() as db:
        data_a = workbook([
            [f"{MARKER} R3A letterhead"],
            ["提单号：ABC123"],
            [],
            ["产品型号", "数量", "单价"],
            ["CODE1", 5, 10],
            ["CODE2", 3, 10],
            ["Note: see PI No.: 123"],
            ["CODE3", 2, 10],
            ["CODE4", 1, 10],
        ])
        result_a = read_workbook(data_a, db=db)
        assert not result_a.missing_columns, result_a.missing_columns
        assert len(result_a.documents) == 1, [
            (d.pi_number, len(d.lines)) for d in result_a.documents
        ]
        assert len(result_a.documents[0].lines) == 4, result_a.documents[0].lines
        assert result_a.documents[0].pi_number != "123", result_a.documents[0].pi_number

        from app.models.base import set_company_scope
        from app.models.company import Company
        from app.models.procurement import Supplier
        from app.services.scm import import_mapping_service

        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} R3B co", code=f"{MARKER}R3B"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        supplier_id = _u()
        db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-R3B", supplier_name="R3B supplier", is_active=True))
        db.flush()
        import_mapping_service.save(
            db, supplier_id=supplier_id, doc_types=["proforma_invoice"],
            mappings=[("船名", "ignore")],
        )
        db.flush()
        resolver = AliasResolver.for_supplier(db, DOC_TYPE, supplier_id)

        data_b = workbook([
            [f"{MARKER} R3B letterhead"],
            ["提单号：OOLU1  船名：MSC XYZ"],
            [],
            ["产品型号", "数量", "单价"],
            ["CODE1", 5, 10],
        ])
        result_b = read_workbook(data_b, resolver=resolver)
        assert result_b.documents, result_b.problems
        assert result_b.documents[0].bl_no == "OOLU1", result_b.documents[0].bl_no


def test_R4_convert_fewer_packing_rows_than_lines_no_double_count():
    """R4 (M-2): three invoice lines of the SAME product (qty 40/125/12) but only ONE
    packing row for that product (qty 177, the supplier boxed all three priced lines
    into one carton row) - `convert_to_draft_shipment` must total 177 for the product,
    not 314. C1's binder only assigns rows to lines it HAS a row for (`lines_with_rows`);
    a line the sheet never gave its own row falls back to the (product, supplier)
    grouping that pre-dates C1, which fires ALONGSIDE the one row-grouped shipment line
    for this product, double-counting the units that row already carries."""
    from app.models.procurement import InboundShipmentLine
    from app.services.scm.packing_list_reader import PackingLine
    from app.services.scm.proforma_invoice_packing_service import replace_packing_rows
    from app.services.scm import proforma_invoice_service

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        code = f"{MARKER}-CWCY604-{tag}"
        _, supplier_id, product_ids = _seed_company_and_products(db, tag, [code])
        product_id = product_ids[code]

        from app.models.scm import ProformaInvoice, ProformaInvoiceLine

        invoice = ProformaInvoice(id=_u(), supplier_id=supplier_id, pi_number=f"PI-{MARKER}-{tag}")
        db.add(invoice)
        db.flush()

        for i, qty in enumerate((40, 125, 12), start=1):
            db.add(ProformaInvoiceLine(
                id=_u(), invoice_id=invoice.id, line_no=i, item_code=code,
                qty=Decimal(qty), unit_price=Decimal("1"), product_id=product_id,
            ))
        db.flush()

        packing_lines = [PackingLine(row_number=1, item_code=code, qty=177.0)]
        replace_packing_rows(db, invoice, packing_lines, supplier_id=supplier_id)
        db.flush()

        container_size_id = _big_container_size(db, tag)
        result = proforma_invoice_service.convert_to_draft_shipment(
            db, [str(invoice.id)], container_size_id=container_size_id,
        )
        shipment_lines = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == result["shipment_id"])
            .all()
        )
        assert len(shipment_lines) == 1, [
            (str(l.product_id), l.quantity_shipped) for l in shipment_lines
        ]
        assert sum(int(l.quantity_shipped) for l in shipment_lines) == 177, [
            l.quantity_shipped for l in shipment_lines
        ]


def test_R5_backfill_rebind_works_with_no_scope_set_and_rolls_up_totals():
    """R5 (M-3): the backfill's own function must work on a session carrying NO scope at
    all (`UNSET`) - exactly what `scripts/rebind_repeated_product_packing_rows.py`'s
    `main()` hands it (`SessionLocal()`, fresh, never scoped) - since every ORM query
    against a `CompanyScopedMixin` table (every model this script touches) reads 0 rows
    under `UNSET` (fail-closed). The function must set the scope IT needs rather than
    depend on a caller nothing gives it; today it reads nothing and reports `count: 0`
    on a PI that genuinely needs rebinding.

    Second half: after a REAL (non-dry) rebind, `rollup_invoice` must have run - each
    line's own packing-row figures (`cartons` here) must land on that line once its row
    is its own, not stay whatever the pre-rebind collapse last wrote (or nothing)."""
    from app.models.base import UNSET, set_company_scope
    from app.models.company import Company
    from app.models.procurement import Supplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoicePackingLine
    from scripts.rebind_repeated_product_packing_rows import rebind_repeated_products

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} R5 co", code=f"{MARKER}R5{tag}"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        cat = ProductCategory(id=_u(), category_code=f"{MARKER}-CAT-{tag}", category_name="cat")
        uom = UnitOfMeasure(id=_u(), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs")
        db.add_all([cat, uom])
        db.flush()
        supplier_id = _u()
        db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-S-{tag}", supplier_name="supplier", is_active=True))
        db.flush()
        code = f"{MARKER}-CWCY604-{tag}"
        product = Product(
            id=_u(), product_code=code, product_name=code, category_id=cat.id,
            base_uom_id=uom.id, list_price=0, is_active=True, is_discontinued=False,
        )
        db.add(product)
        db.flush()

        invoice = ProformaInvoice(id=_u(), supplier_id=supplier_id, pi_number=f"PI-{MARKER}-{tag}")
        db.add(invoice)
        db.flush()
        line_ids = []
        for i in range(1, 4):
            line = ProformaInvoiceLine(
                id=_u(), invoice_id=invoice.id, line_no=i, item_code=code,
                qty=Decimal(10 * i), unit_price=Decimal("1"), product_id=product.id,
            )
            db.add(line)
            line_ids.append(line.id)
        db.flush()
        # The collapse bug's own signature: every row bound to the FIRST line, each row
        # carrying its OWN distinct cartons figure so the rollup half is provable.
        for i in range(1, 4):
            db.add(ProformaInvoicePackingLine(
                id=_u(), proforma_invoice_id=invoice.id, row_no=i, item_code=code,
                qty=Decimal(10 * i), cartons=i, product_id=product.id,
                proforma_invoice_line_id=line_ids[0], match_state="matched",
            ))
        db.flush()

        # The exact state a fresh `SessionLocal()` inside the script's `main()` starts
        # from - nobody has ever called `set_company_scope` on this session.
        set_company_scope(db, UNSET)

        dry = rebind_repeated_products(db, dry_run=True)
        assert dry.get("count") == 1, dry

        rebind_repeated_products(db, dry_run=False)
        db.flush()

        rows_after = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice.id)
            .order_by(ProformaInvoicePackingLine.row_no)
            .all()
        )
        bound = {str(r.proforma_invoice_line_id) for r in rows_after}
        assert bound == {str(i) for i in line_ids}, bound

        lines_after = (
            db.query(ProformaInvoiceLine)
            .filter(ProformaInvoiceLine.invoice_id == invoice.id)
            .order_by(ProformaInvoiceLine.line_no)
            .all()
        )
        for i, line in enumerate(lines_after, start=1):
            assert line.cartons == i, (line.line_no, line.cartons)


def test_R6_serialize_convert_carry_uses_packing_row_container_like_convert_does():
    """R6 (M-4): the PI's header states `container_ref = "AAAA"`, but every packing row
    names `"BBBB"` (the container was reassigned after the PI was applied). `_convert_carry`
    already prefers the ROWS' container over the header (`convert_to_draft_shipment`
    passes `rows_by_invoice`) - but `serialize()` calls `_convert_carry(db, [invoice])`
    with NO `rows_by_invoice` at all, so its `convert_carry.container` falls straight to
    the stale header value. The dialog's "Carried onto the draft" line would say `AAAA`
    while Convert itself writes `BBBB` - exactly the drift AC-C5 exists to prevent."""
    from app.models.company import Company
    from app.models.procurement import InboundShipment
    from app.services.scm.packing_list_reader import PackingLine
    from app.services.scm.proforma_invoice_packing_service import replace_packing_rows
    from app.services.scm import proforma_invoice_service

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        code = f"{MARKER}-R6-{tag}"
        company_id, supplier_id, product_ids = _seed_company_and_products(db, tag, [code])
        product_id = product_ids[code]

        from app.models.scm import ProformaInvoice, ProformaInvoiceLine

        invoice = ProformaInvoice(
            id=_u(), supplier_id=supplier_id, pi_number=f"PI-{MARKER}-{tag}",
            container_ref="AAAA",
        )
        db.add(invoice)
        db.flush()
        db.add(ProformaInvoiceLine(
            id=_u(), invoice_id=invoice.id, line_no=1, item_code=code,
            qty=Decimal(10), unit_price=Decimal("1"), product_id=product_id,
        ))
        db.flush()

        packing_lines = [PackingLine(row_number=1, item_code=code, qty=10.0, container_no="BBBB")]
        replace_packing_rows(db, invoice, packing_lines, supplier_id=supplier_id)
        db.flush()

        payload = proforma_invoice_service.serialize(db, invoice)
        assert payload["convert_carry"]["container"] == "BBBB", payload["convert_carry"]

        container_size_id = _big_container_size(db, tag)
        result = proforma_invoice_service.convert_to_draft_shipment(
            db, [str(invoice.id)], container_size_id=container_size_id,
        )
        shipment = (
            db.query(InboundShipment).filter(InboundShipment.id == result["shipment_id"]).one()
        )
        assert shipment.shipping_container_number == "BBBB", shipment.shipping_container_number
        assert payload["convert_carry"]["container"] == shipment.shipping_container_number


def test_R7_export_task_rejects_mismatched_download_row_and_cross_company_user(monkeypatch):
    """R7 (security S2): `generate_packing_list_xlsx(download_id, shipment_id)` takes
    `shipment_id` as its OWN separate argument, never cross-checked against the
    `user_downloads` row's own `source_entity_id` - and it renders under
    `set_company_scope(db, None)` (every company), unconditionally. Two ways that leaks:

    (a) a download row whose `source_entity_id` names one shipment, handed a DIFFERENT
    `shipment_id` at call time - the task renders and stores the WRONG shipment's data
    under that download, with no check that the two even agree.

    (b) a download row's OWNING USER is not a member of the shipment's own company
    (`user_companies`) - since the render scope is `None` (bypassing company isolation
    entirely), nothing today stops it succeeding anyway.

    Both must mark the download `failed` and store NOTHING, mirroring the fix already
    shipped for `generate_order_inquiry_xlsx` (security review fix round 2, item 2,
    sha 002fd3d2e on `fix/order-sheet-cells`) - adopt the resolved entity's own scope
    (or refuse) instead of trusting the caller's arguments at `None`."""
    from app.models.base import set_company_scope
    from app.models.company import Company, UserCompany
    from app.models.procurement import InboundShipment
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    class _FakeBackend:
        def __init__(self):
            self.uploaded = None

        def upload_file(self, *, file_content, file_path, content_type):
            self.uploaded = file_content
            return (file_path, None)

    # --- (a) mismatched shipment id --------------------------------------------------
    with _savepoint_session() as db:
        tag = uuid.uuid4().hex[:8]
        from tests.scm.conftest import seed_user

        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} R7A co", code=f"{MARKER}R7A{tag}"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        real_shipment = InboundShipment(
            id=_u(), shipment_number=f"{MARKER}-R7A-{tag}", shipment_date=date.today(),
            shipment_status="draft",
        )
        other_shipment = InboundShipment(
            id=_u(), shipment_number=f"{MARKER}-R7Ax-{tag}", shipment_date=date.today(),
            shipment_status="draft",
        )
        db.add_all([real_shipment, other_shipment])
        db.flush()

        uid = seed_user(db, "purchasing")
        dl = DownloadService(db).create(
            user_id=uid, kind="packing_list_xlsx", source_entity_type="inbound_shipment",
            source_entity_id=str(real_shipment.id), filename="pl.xlsx",
        )
        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
        backend_a = _FakeBackend()
        monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
        monkeypatch.setattr(export_tasks, "get_backend", lambda provider: backend_a)

        result_a = export_tasks.generate_packing_list_xlsx(str(dl.id), str(other_shipment.id))
        assert result_a["status"] == "failed", result_a
        assert backend_a.uploaded is None, "no file should be stored for a mismatched download row"
        row_a = DownloadService(db).get(str(dl.id))
        assert row_a.status == "failed", row_a.status
        assert not row_a.storage_key, row_a.storage_key

    # --- (b) download row of a user in another company --------------------------------
    with _savepoint_session() as db:
        tag = uuid.uuid4().hex[:8]
        from tests.scm.conftest import seed_user

        company_a = _u()
        company_b = _u()
        db.add_all([
            Company(id=company_a, name=f"{MARKER} R7B-A {tag}", code=f"{MARKER}A{tag}"[:50], is_active=True),
            Company(id=company_b, name=f"{MARKER} R7B-B {tag}", code=f"{MARKER}B{tag}"[:50], is_active=True),
        ])
        db.flush()
        set_company_scope(db, frozenset({company_a}))
        shipment = InboundShipment(
            id=_u(), shipment_number=f"{MARKER}-R7B-{tag}", shipment_date=date.today(),
            shipment_status="draft",
        )
        db.add(shipment)
        db.flush()

        uid = seed_user(db, "purchasing")
        db.add(UserCompany(id=_u(), user_id=uid, company_id=company_b))
        db.flush()

        dl = DownloadService(db).create(
            user_id=uid, kind="packing_list_xlsx", source_entity_type="inbound_shipment",
            source_entity_id=str(shipment.id), filename="pl.xlsx",
        )
        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
        backend_b = _FakeBackend()
        monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
        monkeypatch.setattr(export_tasks, "get_backend", lambda provider: backend_b)

        result_b = export_tasks.generate_packing_list_xlsx(str(dl.id), str(shipment.id))
        assert result_b["status"] == "failed", result_b
        assert backend_b.uploaded is None, "no file should be stored for a cross-company user"
        row_b = DownloadService(db).get(str(dl.id))
        assert row_b.status == "failed", row_b.status


def test_R8_export_failures_store_a_fixed_message_never_the_raw_exception(monkeypatch):
    """R8 (security S3): `_record_failure` stores `str(error)` verbatim on
    `user_downloads.error` - a field the My Downloads drawer shows the requesting user.
    Any exception whose OWN message happens to carry a SQL fragment, a column name, a
    file path or a stack summary lands there unfiltered. Proven without depending on the
    exact wording either side picks: two DIFFERENT underlying exceptions must produce
    the SAME (fixed) stored message, and neither of their own distinguishing markers may
    appear in it."""
    from app.models.procurement import InboundShipment
    from app.services.download_service import DownloadService
    from app.services.scm import consolidated_packing_list
    from app.tasks import export_tasks
    from tests.scm.conftest import seed_user

    with _savepoint_session() as db:
        tag = uuid.uuid4().hex[:8]
        shipment = InboundShipment(
            id=_u(), shipment_number=f"{MARKER}-R8-{tag}", shipment_date=date.today(),
            shipment_status="draft",
        )
        db.add(shipment)
        db.flush()
        uid = seed_user(db, "purchasing")

        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

        def _boom1(db_, shipment_id):
            raise RuntimeError("SECRET_MARKER_ONE column ghosts.nonexistent does not exist")

        def _boom2(db_, shipment_id):
            raise RuntimeError("SECRET_MARKER_TWO a totally different failure")

        dl1 = DownloadService(db).create(
            user_id=uid, kind="packing_list_xlsx", source_entity_type="inbound_shipment",
            source_entity_id=str(shipment.id), filename="pl1.xlsx",
        )
        monkeypatch.setattr(consolidated_packing_list, "build", _boom1)
        r1 = export_tasks.generate_packing_list_xlsx(str(dl1.id), str(shipment.id))
        row1 = DownloadService(db).get(str(dl1.id))

        dl2 = DownloadService(db).create(
            user_id=uid, kind="packing_list_xlsx", source_entity_type="inbound_shipment",
            source_entity_id=str(shipment.id), filename="pl2.xlsx",
        )
        monkeypatch.setattr(consolidated_packing_list, "build", _boom2)
        r2 = export_tasks.generate_packing_list_xlsx(str(dl2.id), str(shipment.id))
        row2 = DownloadService(db).get(str(dl2.id))

        assert r1["status"] == "failed", r1
        assert r2["status"] == "failed", r2
        assert "SECRET_MARKER_ONE" not in (row1.error or ""), row1.error
        assert "SECRET_MARKER_TWO" not in (row2.error or ""), row2.error
        assert row1.error == row2.error, (row1.error, row2.error)
        assert row1.error, "a failed download must still say SOMETHING"


def test_R9_header_split_bounded_against_a_pathological_cell():
    """R9 (security S1 + minor): a single cell of roughly 3,000 characters carrying 300
    `label:value`-shaped colons and no recognised label anywhere in it must not blow up
    either the mapper's own response size or any one field's string length - `at most
    200 header_fields`, each `label`/`sample` capped at 255 characters - and must not
    take noticeably long to answer (an upload is a synchronous request today). Today
    `header_field_candidates` caps neither the COUNT of pairs a cell can yield (any_label
    accepts every colon-preceded run when nothing resolves) nor the LENGTH of the final
    pair's value, which runs to the end of the cell with nothing to bound it."""
    import time

    from app.services.scm import import_mapping_service

    with pg_session() as db:
        from app.models.base import set_company_scope
        from app.models.company import Company
        from app.models.procurement import Supplier

        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} R9 co", code=f"{MARKER}R9"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        supplier_id = _u()
        db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-R9", supplier_name="R9 supplier", is_active=True))
        db.flush()

        cell = "".join(f"L{i}:V{i} " for i in range(300)) + ("Z" * 3000)
        data = workbook([
            [cell],
            [],
            ["产品型号", "数量", "单价"],
            ["CODE1", 5, 10],
        ])

        start = time.monotonic()
        result = import_mapping_service.probe(
            db, data, supplier_id=supplier_id, doc_types=["proforma_invoice"], header_row=3,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, f"probe took {elapsed:.3f}s against a pathological cell"
        header_fields = result["header_fields"]
        assert len(header_fields) <= 200, len(header_fields)
        for e in header_fields:
            assert len(str(e["label"])) <= 255, e
            assert len(str(e["sample"])) <= 255, e


def test_R10_export_endpoint_non_uuid_404_and_filename_sanitised(scm_app):
    """R10 (nit): `POST /inbound-shipments/{shipment_id}/packing-list/export` with a
    `shipment_id` that is not a valid UUID must 404 - today the raw string reaches
    `InboundShipment.id == shipment_id` (a UUID column), which Postgres refuses with
    `InvalidTextRepresentation`, surfacing as an unhandled 500. Separately, the created
    download row's `filename` is built from the shipment's OWN container number with no
    sanitisation - a container carrying `/`, `\\` or other path-unsafe characters must
    never reach the stored filename verbatim."""
    from app.models.procurement import InboundShipment

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role="purchasing")
    grant_permission(db, "purchasing", "scm.dashboard.view")
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post("/api/v1/scm/inbound-shipments/not-a-uuid/packing-list/export")
    assert r.status_code == 404, (r.status_code, r.text)

    tag = uuid.uuid4().hex[:8]
    shipment = InboundShipment(
        id=_u(), shipment_number=f"{MARKER}-R10-{tag}", shipment_date=date.today(),
        shipment_status="draft", shipping_container_number="FS/CU..\\x",
    )
    db.add(shipment)
    db.flush()

    r2 = client.post(f"/api/v1/scm/inbound-shipments/{shipment.id}/packing-list/export")
    assert r2.status_code == 202, r2.text
    filename = r2.json()["filename"] or ""
    stem = filename.rsplit(".", 1)[0]
    assert re.fullmatch(r"[A-Za-z0-9._-]+", stem), filename


def test_R11_two_binders_agree_on_interleaved_codes_sharing_one_product():
    """R11 (minor): two DIFFERENT item codes (`AAA`, `BBB`) that both resolve to the
    SAME product, their packing rows INTERLEAVED in sheet order (row 1 = AAA, row 2 =
    BBB, row 3 = AAA again). `replace_packing_rows` walks the WHOLE sheet in file order
    with a single per-product cursor, so row 1 -> line 1, row 2 -> line 2, row 3 -> line
    3, regardless of which literal code each row carries. `rebind_packing_rows` is
    called ONCE PER CODE (`code: str` parameter) and resets its OWN per-invoice cursor
    to zero on every call - rebinding AAA's rows (1, 3) first assigns them lines 1 and
    2, then rebinding BBB's row (2) starts its cursor at zero again and ALSO assigns
    line 1 - two different rows collide on the same line and line 3 gets nothing,
    disagreeing with what `replace_packing_rows` computed for the identical rows."""
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoicePackingLine, SupplierProductCodeAlias
    from app.services.scm.packing_list_reader import PackingLine
    from app.services.scm.proforma_invoice_packing_service import rebind_packing_rows, replace_packing_rows

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        code_a = f"{MARKER}-AAA-{tag}"
        code_b = f"{MARKER}-BBB-{tag}"
        _, supplier_id, product_ids = _seed_company_and_products(db, tag, [code_a])
        product_id = product_ids[code_a]

        db.add(SupplierProductCodeAlias(
            id=_u(), supplier_id=supplier_id, supplier_code=code_b, product_id=product_id,
        ))
        db.flush()

        invoice = ProformaInvoice(id=_u(), supplier_id=supplier_id, pi_number=f"PI-{MARKER}-{tag}")
        db.add(invoice)
        db.flush()
        line_ids = []
        for i in range(1, 4):
            line = ProformaInvoiceLine(
                id=_u(), invoice_id=invoice.id, line_no=i, item_code=code_a,
                qty=Decimal(10), unit_price=Decimal("1"), product_id=product_id,
            )
            db.add(line)
            line_ids.append(line.id)
        db.flush()

        packing_lines = [
            PackingLine(row_number=1, item_code=code_a, qty=10.0),
            PackingLine(row_number=2, item_code=code_b, qty=20.0),
            PackingLine(row_number=3, item_code=code_a, qty=5.0),
        ]
        replace_packing_rows(db, invoice, packing_lines, supplier_id=supplier_id)
        db.flush()

        expected = {
            r.row_no: str(r.proforma_invoice_line_id)
            for r in db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice.id)
            .all()
        }
        assert len(set(expected.values())) == 3, expected

        rebind_packing_rows(db, supplier_id=supplier_id, code=code_a, product_id=product_id, product_set_id=None)
        db.flush()
        rebind_packing_rows(db, supplier_id=supplier_id, code=code_b, product_id=product_id, product_set_id=None)
        db.flush()

        got = {
            r.row_no: str(r.proforma_invoice_line_id)
            for r in db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice.id)
            .all()
        }
        assert got == expected, (got, expected)


# =================================================================================== #
# Round 2 (re-review findings) - same PLAN-pi-header-fields-convert-fixes-24sep.md
# =================================================================================== #


def test_S1_export_task_allows_admin_without_company_row(monkeypatch):
    """S1 (blocker): R7's cross-company refusal reads `UserCompany` directly, but the
    platform's own scope resolver (`company_scope_resolver.resolve_user_grant_ids`)
    treats a superadmin/admin as a member of EVERY company, membership row or not - the
    active-company switcher and every other screen already honour that. A download
    owned by an admin, with NO `UserCompany` row for the shipment's own company, must
    still render 'ready'.

    `_savepoint_session()`, not `scm_app`/`pg_session()`: today this test takes the
    task's FAILURE path (it is red), and `_record_failure`'s `db.rollback()` cascades
    past a plain session's savepoints to the outer transaction - the same reason R7/R8
    use it (see that helper's own docstring)."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.procurement import InboundShipment
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks
    from tests.scm.conftest import seed_user

    with _savepoint_session() as db:
        tag = uuid.uuid4().hex[:8]
        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} S1 co", code=f"{MARKER}S1{tag}"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))
        shipment = InboundShipment(
            id=_u(), shipment_number=f"{MARKER}-S1-{tag}", shipment_date=date.today(),
            shipment_status="draft",
        )
        db.add(shipment)
        db.flush()

        # An admin, NO UserCompany row for `company_id` at all - the exact shape R7's
        # raw `UserCompany` check would refuse.
        uid = seed_user(db, "admin")

        dl = DownloadService(db).create(
            user_id=uid, kind="packing_list_xlsx", source_entity_type="inbound_shipment",
            source_entity_id=str(shipment.id), filename="pl-admin.xlsx",
        )

        monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))

        class _FakeBackend:
            def __init__(self):
                self.uploaded = None

            def upload_file(self, *, file_content, file_path, content_type):
                self.uploaded = file_content
                return (file_path, None)

        backend = _FakeBackend()
        monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
        monkeypatch.setattr(export_tasks, "get_backend", lambda provider: backend)

        result = export_tasks.generate_packing_list_xlsx(str(dl.id), str(shipment.id))
        assert result["status"] == "ready", result
        row = DownloadService(db).get(str(dl.id))
        assert row.status == "ready", row.status
        assert row.storage_key, "an admin's export must still store a file"


def test_S2_note_row_without_leading_colon_does_not_split():
    """S2: R3(a)'s "first colon must resolve" gate catches a note row with a leading
    UNRESOLVED label (`Note: see PI No.: 123` - the first colon, right after "Note",
    fails to resolve, so the whole cell is abandoned). It does nothing for a note whose
    only colon IS the one that resolves - `Please refer PI No.: 123` and `see PI No.:
    123 for details` each have exactly ONE colon, and the lookback search finds "PI
    No." within it regardless of the free-text words in front. Both must leave ONE
    document with 4 lines, `pi_number` unchanged - not a second document split off a
    passing mention of "PI No.:" mid-sentence."""
    from app.services.scm.proforma_invoice_reader import read_workbook

    with pg_session() as db:
        for note in ("Please refer PI No.: 123", "see PI No.: 123 for details"):
            data = workbook([
                [f"{MARKER} S2 letterhead"],
                ["提单号：ABC123"],
                [],
                ["产品型号", "数量", "单价"],
                ["CODE1", 5, 10],
                ["CODE2", 3, 10],
                [note],
                ["CODE3", 2, 10],
                ["CODE4", 1, 10],
            ])
            result = read_workbook(data, db=db)
            assert len(result.documents) == 1, (
                note, [(d.pi_number, len(d.lines)) for d in result.documents]
            )
            assert len(result.documents[0].lines) == 4, (note, result.documents[0].lines)
            assert result.documents[0].pi_number != "123", (note, result.documents[0].pi_number)


def test_S3_pre_header_cell_with_unknown_prefix_keeps_known_pairs():
    """S3: R3(a)'s gate ("the FIRST colon must resolve, or the whole cell is
    abandoned") was written for a MID-TABLE note row, but `_labelled` is the SAME
    function the PRE-HEADER letterhead block calls too (`saw_header` still False) - a
    genuine header-block cell carrying an UNMAPPED prefix (`Ref: X`, `Tel: 123`) ahead
    of a real label (提单号/柜号) is not a note, and must not be thrown away wholesale
    the way a note is. The reader must extract `bl_no`/`container_no` from these two
    cells; the mapper's own `header_field_candidates` (`any_label=True`, no such gate)
    already agrees today - both are asserted so a fix that only touches one side is
    still caught."""
    from app.services.import_alias_service import AliasResolver
    from app.services.scm.packing_list_reader import header_field_candidates
    from app.services.scm.proforma_invoice_reader import _BLOCK_FIELDS, DOC_TYPE, read_workbook

    with pg_session() as db:
        rows = [
            ["Ref: X  提单号：OOLU1"],
            ["Tel: 123 柜号：FSCU1"],
        ]
        data = workbook([
            [f"{MARKER} S3 letterhead"],
            *rows,
            [],
            ["产品型号", "数量", "单价"],
            ["CODE1", 5, 10],
        ])
        result = read_workbook(data, db=db)
        assert result.documents, result.problems
        doc = result.documents[0]
        assert doc.bl_no == "OOLU1", doc.bl_no
        assert doc.container_no == "FSCU1", doc.container_no

        resolver = AliasResolver.for_doc_type(db, DOC_TYPE)
        candidates = header_field_candidates(rows, resolver, _BLOCK_FIELDS)
        by_label = {c["label"].strip(): c for c in candidates}
        assert by_label.get("提单号", {}).get("field") == "bl_no", by_label
        assert by_label.get("柜号", {}).get("field") == "container_no", by_label
        assert "Ref" in by_label and by_label["Ref"]["field"] is None, by_label
        assert "Tel" in by_label and by_label["Tel"]["field"] is None, by_label


def _count_queries(db, table_needle: str, fn):
    """Every SQL statement executed by `fn()` that names `table_needle` - the same
    `before_cursor_execute` counting shape `test_s3_reorder_perf_quickwins.py`'s own
    `_count_queries` uses, narrowed to one table so a page's supplier/volume/placement
    lookups (already batched, one query each) don't dilute what is being measured."""
    calls = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        if table_needle in statement.lower():
            calls["n"] += 1

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", _count)
    try:
        result = fn()
    finally:
        event.remove(connection, "before_cursor_execute", _count)
    return result, calls["n"]


def test_S4_pi_list_serialize_no_per_row_company_query():
    """S4: `serialize()`'s own docstring already names the pattern - "resolved once by a
    caller listing several invoices... one query that would otherwise be asked twenty-
    five times" - for `supplier_labels`/`volumes`/`placements`, but `consignee` (R-B,
    `_company_name_for(db, invoice.company_id)`) was never given the same per-page
    batching: it runs INSIDE `serialize()`, once per row. Listing 25 invoices from the
    SAME company must cost at most one `companies` query for the whole page, not 25."""
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.procurement import Supplier
    from app.models.scm import ProformaInvoice
    from app.services.scm import proforma_invoice_service

    with pg_session() as db:
        tag = uuid.uuid4().hex[:8]
        company_id = _u()
        db.add(Company(id=company_id, name=f"{MARKER} S4 co", code=f"{MARKER}S4{tag}"[:50], is_active=True))
        db.flush()
        set_company_scope(db, frozenset({company_id}))

        supplier_id = _u()
        db.add(Supplier(id=supplier_id, supplier_code=f"{MARKER}-S4", supplier_name="S4 supplier", is_active=True))
        db.flush()

        for i in range(25):
            db.add(ProformaInvoice(
                id=_u(), supplier_id=supplier_id, pi_number=f"PI-{MARKER}-S4-{tag}-{i:02d}",
                line_count=0,
            ))
        db.flush()

        result, company_queries = _count_queries(
            db, "companies",
            lambda: proforma_invoice_service.list_for_supplier(
                db, supplier_id=supplier_id, limit=25,
            ),
        )
        assert len(result["data"]) == 25, len(result["data"])
        assert company_queries <= 1, (
            f"{company_queries} `companies` queries for a 25-row page - one per row, "
            "not one for the page"
        )
