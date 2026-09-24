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

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests._pg_fixture import pg_session
from tests.scm.conftest import grant_permission, requires_pg
from tests.scm.test_import_column_mapper import _XLSX, _create_supplier, _fixture
from tests.scm.test_order_sheet_export_downloads import _NoCloseSession
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


# =================================================================================== #
# E1/E2 - async packing-list download (design E)
# =================================================================================== #


def test_E1_export_endpoint_creates_download_row_and_lists_it(scm_app):
    """AC-D1: `POST /inbound-shipments/{id}/packing-list/export` creates a
    `user_downloads` row (`kind="packing_list_xlsx"`, `source_entity_type=
    "inbound_shipment"`, `source_entity_id=<shipment id>`) and it is then visible on the
    per-entity list `GET /api/v1/downloads?source_entity_type=...&source_entity_id=...`."""
    from app.models.procurement import InboundShipment

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

    r = client.post(f"/api/v1/scm/inbound-shipments/{shipment.id}/packing-list/export")
    assert r.status_code == 202, r.text
    body = r.json()

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
    from app.models.procurement import InboundShipment
    from app.services.download_service import DownloadService
    from app.services.scm import consolidated_packing_list
    from app.tasks import export_tasks

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role="purchasing")

    from tests.scm.conftest import seed_user

    tag = uuid.uuid4().hex[:8]
    uid = seed_user(db, "purchasing")
    shipment = InboundShipment(
        id=_u(), shipment_number=f"{MARKER}-E2-{tag}", shipment_date=date.today(),
        shipment_status="draft",
    )
    db.add(shipment)
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
