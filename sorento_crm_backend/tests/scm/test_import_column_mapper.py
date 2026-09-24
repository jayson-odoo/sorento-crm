"""Red tests for the inline import column mapper (PLAN-import-column-mapper-24sep.md).

Phase 2, tester-first: written BEFORE the coder touches the backend, from the UAC
(`import-column-mapper-24sep-acceptance-criteria.md`), the plan's B1-B7 contract, and the
FE's committed Phase 1 contract (`sorento_crm_frontend/app/(protected)/scm/services/
importMappingService.ts`). None of `app.services.scm.header_probe`,
`AliasResolver.for_supplier`, `IGNORE_FIELD`, `/scm/import-mapping/probe` or
`/scm/import-mapping/save` exist yet - every import of them is INSIDE the test that needs
it, deliberately, so one missing module does not mask the other tests' own failure reasons.

Fixtures under `tests/fixtures/scm/import_mapper/` are the four real supplier files the
plan measured (ASCII-renamed copies of the owner's originals, 24 Sep 2026):
  - dafuyuan_pi_20260922.xlsx   - DAFUYUAN PI, header row 14 (+ spliced sub-header row 15)
  - ny_pi_FSCU8706420.xlsx      - NEW YANGGANG PI, header row 15
  - ny_pi_OOLU9610547.xlsx      - NEW YANGGANG PI, header row 15
  - ny_stock_20260921.xlsx      - NEW YANGGANG stock list, header row 2

Two corrections to the captain's test list, made against the actual bytes (measured with
openpyxl, 24 Sep) rather than invented numbers - see the tester's handback for detail:
  - FSCU8706420 has FOUR real data lines (rows 16-19; row 20 is the file's own "合计"
    total, cartons 257 / qty 1262 / amount 220290), not three. The brief's line-count is
    wrong for this file; OOLU9610547 (three lines, qty 251, total 79542) is correct as
    given.
  - The `件数\n（件）` sample pair `["148", "55"]` the brief names "on FSCU" is actually
    OOLU9610547's data (FSCU's own column reads `["15", "54"]`). T2 asserts it on OOLU.

Fix-round (review R1, second correction against the real bytes): the coordinator's R7
carton width/height numbers (0.54, 0.31) are OOLU9610547's first line, not FSCU8706420's
(FSCU's own first line reads 0.6/2.35; OOLU's second item happens to share FSCU's numbers,
which is almost certainly what mixed the two up) - R7 asserts them on OOLU, same
correction shape as T2's. ny_stock_20260921.xlsx holds 44 real data rows (序号 1-44, row
47 the "总计：" total), not 38 as the ORIGINAL brief said - R9 uses the measured count.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from tests._pg_fixture import pg_session
from tests.scm.conftest import grant_permission, requires_pg
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZICM"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "scm" / "import_mapper"


def _fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def _packing_list_workbook() -> bytes:
    """A synthetic packing-list-SHAPED file (R7): titled `装箱单` so `classify()` (title
    cell, checked first) recognises it as a packing list without any alias resolving
    anything - the only way to get a file that IS a packing list with its required set
    genuinely unresolved for a fresh supplier, since header-shape classification itself
    needs an alias to already answer (chicken-and-egg, same reason the mapper exists).
    Every header is `{MARKER}`-prefixed so it cannot collide with a real shared alias.
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([f"装箱单 {MARKER} R7"])
    ws.append([f"{MARKER}型号", f"{MARKER}数量", f"{MARKER}箱数", f"{MARKER}净重", f"{MARKER}备注"])
    ws.append(["ABC-1", 10, 2, 5.5, "n/a"])
    ws.append(["ABC-2", 20, 4, 11.0, "n/a"])
    from io import BytesIO

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _create_supplier(db, *, code_suffix: str = "") -> str:
    """Create a supplier under whatever company scope is CURRENTLY set on `db`.

    For a route test (T4/T5/T8), that is the scope `as_company_user` already registered -
    both on the session AND on the `apply_company_scope` dependency override the request
    re-applies on every call. Creating a SEPARATE company here (rather than reusing the
    scope already in force) would make the supplier invisible the moment that override
    resets the scope back on the next request - the "conftest company-scope race"
    (see MEMORY.md project note of the same name): the supplier would sit under a company
    the running request never sees, and `assert_supplier` would refuse it as "does not
    exist" - a fixture bug, not a real 422.
    """
    from app.models.procurement import Supplier

    supplier_id = str(uuid.uuid4())
    db.add(
        Supplier(
            id=supplier_id,
            supplier_code=f"{MARKER}-{code_suffix}-{uuid.uuid4().hex[:6]}".upper(),
            supplier_name=f"{MARKER} supplier {code_suffix}",
            is_active=True,
        )
    )
    db.flush()
    return supplier_id


def _seed_supplier_with_company(db, *, code_suffix: str = "") -> str:
    """A fresh company, scoped on `db`, with one supplier under it. For T3's bare
    `pg_session()` - no `as_company_user` request-scope override to race against."""
    from app.models.base import set_company_scope
    from app.models.company import Company

    company_id = str(uuid.uuid4())
    db.add(
        Company(
            id=company_id,
            name=f"{MARKER} co {company_id[:8]}",
            code=f"{MARKER}{uuid.uuid4().hex[:6]}".upper()[:50],
            is_active=True,
        )
    )
    db.flush()
    set_company_scope(db, frozenset({company_id}))
    return _create_supplier(db, code_suffix=code_suffix)


def _seed_supplier_other_company(db) -> str:
    """A supplier under a DIFFERENT, freshly created company - for the "caller's company
    cannot see this supplier" refusal (T4)."""
    from app.models.base import company_scope
    from app.models.company import Company
    from app.models.procurement import Supplier

    other_company_id = str(uuid.uuid4())
    db.add(
        Company(
            id=other_company_id,
            name=f"{MARKER} other co {other_company_id[:8]}",
            code=f"{MARKER}OTH{uuid.uuid4().hex[:6]}".upper()[:50],
            is_active=True,
        )
    )
    db.flush()
    other_supplier_id = str(uuid.uuid4())
    with company_scope(db, frozenset({other_company_id})):
        db.add(
            Supplier(
                id=other_supplier_id,
                supplier_code=f"{MARKER}-OTH-{uuid.uuid4().hex[:6]}".upper(),
                supplier_name=f"{MARKER} other supplier",
                is_active=True,
            )
        )
        db.flush()
    return other_supplier_id


# --------------------------------------------------------------------------- #
# T1 - probe finds the header row and the data row, no aliases involved (AC-M1)
# --------------------------------------------------------------------------- #


def test_probe_finds_header_and_data_row_per_fixture():
    from app.services.scm.header_probe import probe

    # Every one of these four files opens its table with a 序号 (row number) column whose
    # first two data cells are always 1 then 2 - proving the DATA row was found (not just
    # the header) without hardcoding a "data_row" field this contract does not promise.
    cases = [
        ("dafuyuan_pi_20260922.xlsx", 14),
        ("ny_pi_FSCU8706420.xlsx", 15),
        ("ny_pi_OOLU9610547.xlsx", 15),
        ("ny_stock_20260921.xlsx", 2),
    ]
    for filename, expected_header_row in cases:
        result = probe(_fixture(filename))
        assert result.header_row == expected_header_row, filename
        assert result.columns, filename
        first_col = result.columns[0]
        assert first_col.header == "序号", (filename, first_col.header)
        assert first_col.samples[:2] == ["1", "2"], (filename, first_col.samples)


# --------------------------------------------------------------------------- #
# T2 - blank merged columns named `<parent> [n]`; a second header row spliced (AC-M2)
# --------------------------------------------------------------------------- #


def test_probe_names_blank_merged_columns_and_splices_second_row():
    from app.services.scm.header_probe import probe

    # NEW YANGGANG: 外箱/木托尺寸 is one merged header (G15:I15) over three columns with no
    # text of their own.
    oolu = probe(_fixture("ny_pi_OOLU9610547.xlsx"))
    headers = [c.header for c in oolu.columns]
    assert "外箱/木托尺寸" in headers
    assert "外箱/木托尺寸 [2]" in headers
    assert "外箱/木托尺寸 [3]" in headers

    # Corrected against the real file (see module docstring): OOLU9610547's own 件数\n（件）
    # column reads 148 then 55 on its first two data rows; FSCU8706420's reads 15 then 54.
    cartons_col = next(c for c in oolu.columns if c.header == "件数\n（件）")
    assert cartons_col.samples[:2] == ["148", "55"]

    # DAFUYUAN: 箱子 CTN SIZE (CM) is merged N14:P14 over a SECOND header row (L/W/H) at
    # row 15 - spliced into the parent, not left blank.
    dafuyuan = probe(_fixture("dafuyuan_pi_20260922.xlsx"))
    da_headers = [c.header for c in dafuyuan.columns]
    assert "箱子 CTN SIZE (CM) L (长)" in da_headers
    assert "箱子 CTN SIZE (CM) W (宽)" in da_headers
    assert "箱子 CTN SIZE (CM) H (高)" in da_headers


# --------------------------------------------------------------------------- #
# T3 - for_supplier precedence + ignore (AC-M5, AC-M7, R2)
# --------------------------------------------------------------------------- #


def test_for_supplier_precedence_and_ignore():
    from app.models.import_alias import ImportFieldAlias
    from app.services.import_alias_service import IGNORE_FIELD, AliasResolver

    with pg_session() as db:
        supplier_a = _seed_supplier_with_company(db, code_suffix="A")
        supplier_b = _seed_supplier_with_company(db, code_suffix="B")

        doc_type = "proforma_invoice"
        header_qty = f"{MARKER}件数"
        header_ignore = f"{MARKER}序号"
        header_unknown = f"{MARKER}未知列"

        db.add_all(
            [
                # A shared row every supplier without an override would resolve.
                ImportFieldAlias(doc_type=doc_type, field="qty", alias=header_qty, supplier_id=None),
                # Supplier A's own override of the SAME header text, to a DIFFERENT field.
                ImportFieldAlias(
                    doc_type=doc_type, field="cartons", alias=header_qty, supplier_id=supplier_a
                ),
                # Supplier A ignoring a column entirely (G2/R3).
                ImportFieldAlias(
                    doc_type=doc_type, field=IGNORE_FIELD, alias=header_ignore, supplier_id=supplier_a
                ),
            ]
        )
        db.flush()

        resolver_a = AliasResolver.for_supplier(db, doc_type, supplier_a)
        assert resolver_a.field_for_header(header_qty) == "cartons", (
            "a supplier row must beat the shared row on the same normalised header"
        )

        resolver_b = AliasResolver.for_supplier(db, doc_type, supplier_b)
        assert resolver_b.field_for_header(header_qty) == "qty", (
            "another supplier's own row must be invisible to this supplier's resolver"
        )

        assert resolver_a.field_for_header(header_ignore) is None, (
            "ignore must resolve to nothing at read time"
        )

        unmapped = resolver_a.unmapped_headers({header_ignore: "x", header_unknown: "y"})
        assert header_ignore not in unmapped, "an ignored column counts as known (AC-M7)"
        assert header_unknown in unmapped, "a header nobody has ever mapped is still unmapped"


# --------------------------------------------------------------------------- #
# T4 - save upserts, replaces, rejects, accepts ignore, scopes by company (AC-M5/M6/M7)
# --------------------------------------------------------------------------- #


def test_save_upserts_replaces_rejects(scm_app):
    from sqlalchemy import text

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    supplier_id = _create_supplier(db, code_suffix="S4")

    client = TestClient(app)
    header = f"{MARKER}件数"

    r1 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": header, "field": "qty"}],
        },
    )
    assert r1.status_code in (200, 201), r1.text

    # Re-mapping the SAME header for the SAME supplier replaces, never accumulates (AC-M6).
    r2 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": header, "field": "cartons"}],
        },
    )
    assert r2.status_code in (200, 201), r2.text

    rows = db.execute(
        text(
            "SELECT field FROM import_field_alias "
            "WHERE supplier_id = :s AND doc_type = 'proforma_invoice' AND alias = :h"
        ),
        {"s": supplier_id, "h": header},
    ).fetchall()
    assert len(rows) == 1, f"expected exactly one row after a re-map, got {rows}"
    assert rows[0][0] == "cartons"

    # An unknown field is refused.
    r3 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": f"{MARKER}未知", "field": "not_a_real_field"}],
        },
    )
    assert r3.status_code == 422, r3.text

    # `ignore` is a saved choice, not an error (G2/AC-M7).
    r4 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": f"{MARKER}忽略", "field": "ignore"}],
        },
    )
    assert r4.status_code in (200, 201), r4.text
    ignore_row = db.execute(
        text(
            "SELECT field FROM import_field_alias "
            "WHERE supplier_id = :s AND doc_type = 'proforma_invoice' AND alias = :h"
        ),
        {"s": supplier_id, "h": f"{MARKER}忽略"},
    ).scalar()
    assert ignore_row == "ignore"

    # A combined file (G4): one save, two doc types, same rows land under both.
    r5 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice", "packing_list"],
            "mappings": [{"header": f"{MARKER}双写", "field": "item_code"}],
        },
    )
    assert r5.status_code in (200, 201), r5.text
    for doc_type in ("proforma_invoice", "packing_list"):
        count = db.execute(
            text(
                "SELECT count(*) FROM import_field_alias "
                "WHERE supplier_id = :s AND doc_type = :d AND alias = :h"
            ),
            {"s": supplier_id, "d": doc_type, "h": f"{MARKER}双写"},
        ).scalar()
        assert count == 1, doc_type

    # A supplier the caller's company cannot see - refused, same as any other route that
    # scopes a supplier today (`proforma_invoice_service.assert_supplier`, 422).
    other_supplier_id = _seed_supplier_other_company(db)
    r6 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": other_supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": f"{MARKER}x", "field": "item_code"}],
        },
    )
    assert r6.status_code in (403, 404, 422), r6.text


# --------------------------------------------------------------------------- #
# T5 - PI preview names every unresolved column, and reads a saved layout (AC-M4, B6)
# --------------------------------------------------------------------------- #


def test_pi_preview_uses_saved_layout_and_names_missing(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    supplier_id = _create_supplier(db, code_suffix="S5")

    file_bytes = _fixture("ny_pi_FSCU8706420.xlsx")
    client = TestClient(app)

    # Without a saved layout: today, `qty` is correctly reported missing, but
    # `unmapped_headers` stays empty because no aliases resolve enough of the required set
    # to recognise the header row at all (Measured, PLAN-import-column-mapper-24sep.md) -
    # exactly the AC-M4 gap this lane closes.
    r_before = client.post(
        "/api/v1/scm/proforma-invoices/preview",
        files={"file": ("FSCU8706420.xlsx", file_bytes, _XLSX)},
        data={"supplier_id": supplier_id},
    )
    assert r_before.status_code == 200, r_before.text
    body_before = r_before.json()
    assert "qty" in body_before["missing_columns"], body_before
    assert body_before["unmapped_headers"], (
        "AC-M4: every unresolved column must be named, even with required fields missing"
    )

    # Save a NEW YANGGANG layout for this supplier THROUGH THE REAL ENDPOINT (T4 proves the
    # endpoint's own upsert/replace/reject behaviour; this is a preview-reads-it proof).
    # A direct ORM insert of a row the migrations already seed as SHARED (客户型号 ->
    # item_code) hits `uq_import_field_alias_triple` - that triple has no `supplier_id`
    # in it, by design (see the model's own comment: a supplier row that says the same
    # thing as a shared row is redundant) - the save endpoint's `ON CONFLICT DO NOTHING`
    # is what makes that a safe no-op instead of a 500.
    mapping = {
        "客户型号": "item_code",
        "总数量\n（个）": "qty",
        "件数\n（件）": "cartons",
        "单价\n（元）": "unit_price",
        "金额\n（元）": "amount",
    }
    r_save = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": header, "field": field} for header, field in mapping.items()],
        },
    )
    assert r_save.status_code == 200, r_save.text

    r_after = client.post(
        "/api/v1/scm/proforma-invoices/preview",
        files={"file": ("FSCU8706420.xlsx", file_bytes, _XLSX)},
        data={"supplier_id": supplier_id, "header_row": "15"},
    )
    assert r_after.status_code == 200, r_after.text
    body_after = r_after.json()
    assert body_after["ok"] is True, body_after
    # Measured against the real file (module docstring): FOUR data lines, not three.
    assert body_after["line_count"] == 4, body_after
    documents = body_after["documents"]
    assert len(documents) == 1, documents
    assert documents[0]["qty"] == 1262, documents[0]
    assert documents[0]["total"] == 220290, documents[0]

    # Cartons is not on the HTTP summary at all today - proved at the reader level instead,
    # which is also where supplier-scoped resolution (B1's `for_supplier`) actually lives.
    from app.services.import_alias_service import AliasResolver
    from app.services.scm.proforma_invoice_reader import read_workbook

    resolver = AliasResolver.for_supplier(db, "proforma_invoice", supplier_id)
    result = read_workbook(file_bytes, resolver=resolver)
    assert result.ok, result.missing_columns
    total_cartons = sum(
        ln.cartons for doc in result.documents for ln in doc.lines if ln.cartons is not None
    )
    assert total_cartons == 257, total_cartons


# --------------------------------------------------------------------------- #
# T6 - canonical_fields serves the stock list and leaks no internal names (AC-M8, B7)
# --------------------------------------------------------------------------- #


def test_canonical_fields_stock_list_and_no_internal_names():
    from app.services.import_alias_service import canonical_fields

    stock_fields = canonical_fields("supplier_inventory")
    assert stock_fields, "supplier_inventory must be mappable through the API (AC-M8)"
    assert "item_code" in stock_fields
    assert "qty_packed" in stock_fields

    deny = {"row_number", "index", "header_row", "lines", "problems"}
    for doc_type in ("proforma_invoice", "packing_list", "supplier_inventory"):
        fields = set(canonical_fields(doc_type))
        leaked = deny & fields
        assert not leaked, f"{doc_type} leaks internal dataclass names: {leaked}"

    # REQUIRED per doc type, exported (not the private `_REQUIRED_COLUMNS`) so the probe
    # endpoint (B4) can flag them without importing a private name.
    from app.services.scm.packing_list_reader import REQUIRED_COLUMNS as pl_required
    from app.services.scm.proforma_invoice_reader import REQUIRED_COLUMNS as pi_required
    from app.services.scm.supplier_inventory_reader import REQUIRED_COLUMNS as si_required

    assert tuple(pi_required) == ("item_code", "qty", "unit_price")
    assert tuple(pl_required) == ("item_code", "qty")
    assert tuple(si_required) == ("item_code", "qty_packed")


# --------------------------------------------------------------------------- #
# T7 - the header-row stepper actually re-reads the sheet (AC-M3)
# --------------------------------------------------------------------------- #


def test_probe_header_row_override():
    from app.services.scm.header_probe import probe

    stock_bytes = _fixture("ny_stock_20260921.xlsx")
    natural = probe(stock_bytes)
    overridden = probe(stock_bytes, header_row=2)
    assert overridden.header_row == 2 == natural.header_row
    assert [c.header for c in overridden.columns] == [c.header for c in natural.columns], (
        "an override that agrees with the guess must read exactly the same table"
    )

    fscu_bytes = _fixture("ny_pi_FSCU8706420.xlsx")
    natural_fscu = probe(fscu_bytes)
    assert natural_fscu.header_row == 15
    forced = probe(fscu_bytes, header_row=14)
    assert forced.header_row == 14
    # Row 14 is a single merged title cell (A14:T14), not the real header - forcing it must
    # actually re-derive columns/samples from THAT row, not just relabel row 15's guess.
    assert [c.header for c in forced.columns] != [c.header for c in natural_fscu.columns]
    assert forced.columns[0].samples != natural_fscu.columns[0].samples


# --------------------------------------------------------------------------- #
# T8 - the probe endpoint's response shape matches the FE's committed contract (B4)
# --------------------------------------------------------------------------- #


def test_probe_endpoint_shape(scm_app):
    from app.services.import_alias_service import AliasResolver

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    supplier_id = _create_supplier(db, code_suffix="S8")
    client = TestClient(app)

    # One supplier-scoped mapping saved first, so at least one column comes back
    # source="supplier" rather than every non-"none" column reading as one of the
    # migrations' own SHARED seed rows (`客户型号 -> item_code`, `品名 -> description`,
    # `单价(元)` / `单价` -> unit_price, ... - the private DB is not empty).
    r_save = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": "件数\n（件）", "field": "cartons"}],
        },
    )
    assert r_save.status_code == 200, r_save.text

    r = client.post(
        "/api/v1/scm/import-mapping/probe",
        files={"file": ("FSCU8706420.xlsx", _fixture("ny_pi_FSCU8706420.xlsx"), _XLSX)},
        data={"supplier_id": supplier_id, "doc_types": "proforma_invoice"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {
        "header_row",
        "columns",
        "required_fields",
        "missing_required",
        "fields",
    }
    assert body["header_row"] == 15
    assert body["columns"], body

    # A supplier-agnostic resolver, to prove a "shared" column's answer really came from
    # the migrations' seed rather than something this test itself planted.
    shared_resolver = AliasResolver.for_doc_type(db, "proforma_invoice")
    saw_supplier_source = False
    for col in body["columns"]:
        assert set(col.keys()) >= {"position", "header", "samples", "field", "source", "required"}
        assert col["source"] in ("supplier", "shared", "none")
        if col["source"] == "none":
            assert col["field"] is None, col
        elif col["source"] == "shared":
            assert col["field"] is not None, col
            assert shared_resolver.field_for_header(col["header"]) == col["field"], col
        else:  # "supplier"
            assert col["field"] is not None, col
            if col["header"] == "件数\n（件）":
                assert col["field"] == "cartons", col
                saw_supplier_source = True
    assert saw_supplier_source, "the saved supplier mapping must come back source='supplier'"

    # 客户型号 (item_code) and 单价\n（元） (unit_price) resolve through the shared seed;
    # 总数量\n（个） (qty) has no shared alias for this literal header text - the only
    # required field still missing.
    assert body["required_fields"] == ["item_code", "qty", "unit_price"]
    assert body["missing_required"] == ["qty"], body["missing_required"]
    assert {"field": "item_code", "label": "Item code"} in body["fields"]


# =============================================================================
# Fix-round (review R1): the coder's now-landed implementation, probed harder.
# =============================================================================


# --------------------------------------------------------------------------- #
# R1 - save refuses a doc_types shape it does not understand
# --------------------------------------------------------------------------- #


def test_save_rejects_unknown_doc_type(scm_app):
    from sqlalchemy import text

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    grant_permission(db, "purchasing", "scm.reorder.run")
    supplier_id = _create_supplier(db, code_suffix="R1")
    client = TestClient(app)

    # `ignore` bypasses save()'s "is this field known to any requested doc type" check
    # entirely - it is written under EVERY doc_type asked for, unconditionally. Nothing
    # today refuses a doc_type the mapper does not even serve, so this row would land in
    # the table under a doc_type no reader will ever ask for.
    r1 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["outstanding_so"],
            "mappings": [{"header": f"{MARKER}osoh", "field": "ignore"}],
        },
    )
    assert r1.status_code == 422, r1.text
    written = db.execute(
        text(
            "SELECT count(*) FROM import_field_alias "
            "WHERE supplier_id = :s AND doc_type = 'outstanding_so'"
        ),
        {"s": supplier_id},
    ).scalar()
    assert written == 0, "an unknown doc_type must write nothing"

    r2 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={"supplier_id": supplier_id, "doc_types": [], "mappings": []},
    )
    assert r2.status_code == 422, r2.text

    r3 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice", "packing_list", "supplier_inventory"],
            "mappings": [],
        },
    )
    assert r3.status_code == 422, r3.text


# --------------------------------------------------------------------------- #
# R2 - a permission grants ONLY the doc types its own upload endpoint covers
# --------------------------------------------------------------------------- #


def test_save_permission_per_doc_type(scm_app):
    from app.models.user import UserRole

    app, db, gcu, gcuk = scm_app

    # A caller who can only upload proforma invoices / packing lists must not be able to
    # save (or probe) a STOCK LIST layout through this back door - `require_any_permission`
    # today grants either permission the RUN of doc types requested, not just the ones its
    # own permission actually covers.
    role_a = f"zzicm-role-a-{uuid.uuid4().hex[:8]}"
    db.add(UserRole(id=str(uuid.uuid4()), slug=role_a, name=f"{MARKER} role A {role_a}"))
    db.flush()
    as_company_user(app, db, gcu, gcuk, role=role_a)
    grant_permission(db, role_a, "scm.proforma_invoice.upload")
    supplier_a = _create_supplier(db, code_suffix="R2A")
    client = TestClient(app)

    r1 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_a,
            "doc_types": ["supplier_inventory"],
            "mappings": [{"header": f"{MARKER}h1", "field": "ignore"}],
        },
    )
    assert r1.status_code == 403, r1.text

    r1p = client.post(
        "/api/v1/scm/import-mapping/probe",
        files={"file": ("stock.xlsx", _fixture("ny_stock_20260921.xlsx"), _XLSX)},
        data={"supplier_id": supplier_a, "doc_types": "supplier_inventory"},
    )
    assert r1p.status_code == 403, r1p.text

    # `scm.reorder.run` already reaches `/supplier-documents/apply` (proforma invoice /
    # packing list uploads), so saving those doc types with only that permission mirrors a
    # capability this role already has today - the coordinator's own positive case.
    role_b = f"zzicm-role-b-{uuid.uuid4().hex[:8]}"
    db.add(UserRole(id=str(uuid.uuid4()), slug=role_b, name=f"{MARKER} role B {role_b}"))
    db.flush()
    as_company_user(app, db, gcu, gcuk, role=role_b)
    grant_permission(db, role_b, "scm.reorder.run")
    supplier_b = _create_supplier(db, code_suffix="R2B")

    r2 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_b,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": f"{MARKER}h2", "field": "ignore"}],
        },
    )
    assert r2.status_code == 200, r2.text

    r2p = client.post(
        "/api/v1/scm/import-mapping/probe",
        files={"file": ("FSCU8706420.xlsx", _fixture("ny_pi_FSCU8706420.xlsx"), _XLSX)},
        data={"supplier_id": supplier_b, "doc_types": "proforma_invoice"},
    )
    assert r2p.status_code == 200, r2p.text


# --------------------------------------------------------------------------- #
# R3 - save bounds: header length, a header that normalises to nothing, mapping count
# --------------------------------------------------------------------------- #


def test_save_bounds(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    supplier_id = _create_supplier(db, code_suffix="R3")
    client = TestClient(app)

    # `import_field_alias.alias` is `String(255)` - a 256-char header must be REFUSED
    # (422), not left to crash the insert into a raw Postgres DataError (500).
    long_header = "H" * 256
    r1 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": long_header, "field": "ignore"}],
        },
    )
    assert r1.status_code == 422, r1.text

    for blank_header in ("   ", "()"):
        r2 = client.post(
            "/api/v1/scm/import-mapping/save",
            json={
                "supplier_id": supplier_id,
                "doc_types": ["proforma_invoice"],
                "mappings": [{"header": blank_header, "field": "ignore"}],
            },
        )
        assert r2.status_code == 422, (blank_header, r2.text)

    too_many = [{"header": f"{MARKER}bulk{i}", "field": "ignore"} for i in range(501)]
    r3 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={"supplier_id": supplier_id, "doc_types": ["proforma_invoice"], "mappings": too_many},
    )
    assert r3.status_code == 422, r3.text


# --------------------------------------------------------------------------- #
# R4 - probe refuses an unreadable file with a plain 422, not a raw 500
# --------------------------------------------------------------------------- #


def test_probe_unreadable_file_422(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    supplier_id = _create_supplier(db, code_suffix="R4")
    client = TestClient(app)

    r = client.post(
        "/api/v1/scm/import-mapping/probe",
        files={"file": ("not-a-workbook.xlsx", b"this is not a zip file at all", _XLSX)},
        data={"supplier_id": supplier_id, "doc_types": "proforma_invoice"},
    )
    assert r.status_code == 422, r.text
    text = str(r.json())
    assert "Traceback" not in text
    assert "BadZipFile" not in text
    assert ".py" not in text


# --------------------------------------------------------------------------- #
# R5 - for_doc_type answers from SHARED rows only; the word composer is unaffected
# --------------------------------------------------------------------------- #


def test_for_doc_type_reads_shared_rows_only():
    from app.models.import_alias import ImportFieldAlias
    from app.services.import_alias_service import AliasResolver

    with pg_session() as db:
        supplier_id = _seed_supplier_with_company(db, code_suffix="R5")
        # A marker-prefixed header guarantees no shared row already answers for it, so
        # the assertion below is a deterministic proof of leakage, not a race against
        # Postgres's own (unordered) row-return order the way re-using a header the
        # shared seed ALSO answers (like the literal `QTY` the coordinator named) would
        # have been - whichever of the two rows a sequential scan happened to visit
        # first would win `AliasResolver.for_doc_type`'s `setdefault`, real bug or not.
        marker_header = f"{MARKER}QTYR5"
        db.add(
            ImportFieldAlias(
                doc_type="proforma_invoice", field="ignore", alias=marker_header, supplier_id=supplier_id
            )
        )
        db.flush()

        resolver = AliasResolver.for_doc_type(db, "proforma_invoice")
        assert resolver.raw_field_for_header(marker_header) is None, (
            "a supplier-scoped row must not answer for the shared, supplier-agnostic resolver"
        )
        # The real shared seed still answers normally - `for_doc_type` is not broken
        # wholesale, only supplier-scoped leakage into it is the bug.
        assert resolver.field_for_header("QTY") == "qty"

        # `supplier_code_composer.WordList.for_supplier` does NOT go through
        # `AliasResolver.for_doc_type` at all (checked: it runs its own
        # `supplier_id == X OR supplier_id IS NULL` query directly against
        # `ImportFieldAlias`) - so scoping `for_doc_type` to shared rows only cannot
        # break it. Regression guard: a supplier-scoped word row is still reachable the
        # way the composer actually reads it.
        from app.services.scm.supplier_code_composer import WORD_DOC_TYPE, WordList

        word_header = f"{MARKER}WORDR5"
        db.add(
            ImportFieldAlias(
                doc_type=WORD_DOC_TYPE, field="SRT", alias=word_header, supplier_id=supplier_id
            )
        )
        db.flush()
        words = WordList.for_supplier(db, supplier_id)
        assert words.lookup(word_header) == "SRT"


# --------------------------------------------------------------------------- #
# R6 - a re-map under a different literal spelling still replaces, not accumulates
# --------------------------------------------------------------------------- #


def test_remap_deletes_by_normalised_header(scm_app):
    from sqlalchemy import text

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    supplier_id = _create_supplier(db, code_suffix="R6")
    client = TestClient(app)

    # Same normalised key (`normalize_header` strips whitespace/case), different literal
    # text - `_write`'s own DELETE matches the literal `alias` column, not the normalised
    # key, so a re-map spelled differently must still replace the earlier row.
    header_a = f"{MARKER}Qty "
    header_b = f"{MARKER}QTY"
    r1 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": header_a, "field": "cartons"}],
        },
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": header_b, "field": "qty"}],
        },
    )
    assert r2.status_code == 200, r2.text

    rows = db.execute(
        text(
            "SELECT field, alias FROM import_field_alias "
            "WHERE supplier_id = :s AND doc_type = 'proforma_invoice'"
        ),
        {"s": supplier_id},
    ).fetchall()
    assert len(rows) == 1, rows
    assert rows[0][0] == "qty", rows


# --------------------------------------------------------------------------- #
# R7 - the reader actually resolves the PROBE's synthesised header texts (kill-test hole)
# --------------------------------------------------------------------------- #


def test_reader_uses_probe_header_texts(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    grant_permission(db, "purchasing", "scm.reorder.run")
    client = TestClient(app)

    from app.services.import_alias_service import AliasResolver
    from app.services.scm.proforma_invoice_reader import read_workbook

    # NEW YANGGANG, OOLU9610547 (corrected against the real file - see module docstring):
    # the first data LINE's own 外箱/木托尺寸 measurements are width 0.54, height 0.31 -
    # both blank-merged columns the probe names `[2]`/`[3]` (AC-M2), which the raw sheet
    # cell never spells at all. If the reader resolved headers off the raw cells instead
    # of the probe's synthesised texts, neither could ever be mapped to anything.
    supplier_a = _create_supplier(db, code_suffix="R7A")
    mapping_a = {
        "客户型号": "item_code",
        "总数量\n（个）": "qty",
        "单价\n（元）": "unit_price",
        "外箱/木托尺寸 [2]": "carton_width_cm",
        "外箱/木托尺寸 [3]": "carton_height_cm",
    }
    r_save_a = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_a,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": h, "field": f} for h, f in mapping_a.items()],
        },
    )
    assert r_save_a.status_code == 200, r_save_a.text

    resolver_a = AliasResolver.for_supplier(db, "proforma_invoice", supplier_a)
    oolu_bytes = _fixture("ny_pi_OOLU9610547.xlsx")
    result_a = read_workbook(oolu_bytes, resolver=resolver_a, header_row=15)
    assert result_a.ok, result_a.missing_columns
    first_line_a = result_a.documents[0].lines[0]
    assert first_line_a.carton_width_cm == 0.54, first_line_a
    assert first_line_a.carton_height_cm == 0.31, first_line_a

    # DAFUYUAN: 箱子 CTN SIZE (CM) L (长) is a SPLICED second-header-row column (B2/AC-M2) -
    # same proof, the other synthesis shape.
    supplier_b = _create_supplier(db, code_suffix="R7B")
    mapping_b = {
        "产品型号": "item_code",
        "数量": "qty",
        "单价 (RMB)": "unit_price",
        "箱子 CTN SIZE (CM) L (长)": "carton_length_cm",
    }
    r_save_b = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_b,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": h, "field": f} for h, f in mapping_b.items()],
        },
    )
    assert r_save_b.status_code == 200, r_save_b.text

    resolver_b = AliasResolver.for_supplier(db, "proforma_invoice", supplier_b)
    dafuyuan_bytes = _fixture("dafuyuan_pi_20260922.xlsx")
    result_b = read_workbook(dafuyuan_bytes, resolver=resolver_b, header_row=14)
    assert result_b.ok, result_b.missing_columns
    first_line_b = result_b.documents[0].lines[0]
    assert first_line_b.carton_length_cm == 37.5, first_line_b

    # AC-M4 guard, the other two upload channels (T5 already proves the PI single-file
    # preview): unmapped_headers is populated for a packing list whose required fields
    # are unresolved, and for the stock list preview with no layout at all.
    r_pl = client.post(
        "/api/v1/scm/supplier-documents/preview",
        files=[("files", ("packing.xlsx", _packing_list_workbook(), _XLSX))],
        data={"supplier_id": _create_supplier(db, code_suffix="R7C")},
    )
    assert r_pl.status_code == 200, r_pl.text
    pl_file = r_pl.json()["files"][0]
    # `classify()` alone already says "packing_list" (measured directly, no aliases
    # needed - its own title cell says 装箱单); this endpoint's own `kind` downgrades to
    # "unreadable" once the reader's required columns are unresolved (`errors` non-empty)
    # - a DIFFERENT thing from "which document is this", so not asserted here. What AC-M4
    # actually promises is that the unresolved columns are still NAMED regardless.
    assert pl_file.get("unmapped_headers"), pl_file

    r_stock = client.post(
        "/api/v1/scm/supplier-inventory/preview",
        files={"file": ("stock.xlsx", _fixture("ny_stock_20260921.xlsx"), _XLSX)},
        data={"supplier_id": _create_supplier(db, code_suffix="R7D")},
    )
    assert r_stock.status_code == 200, r_stock.text
    # Unlike the PI preview (T5), `supplier_inventory_service.preview()` does not expose
    # `unmapped_headers` at the top level at all today - only `validate()`'s warning TEXT
    # reads `parsed.unmapped_headers` internally. AC-M4 promises the unresolved columns
    # are named; `.get(...)` keeps the failure a clean assertion (missing/empty) rather
    # than a `KeyError` crash.
    assert r_stock.json().get("unmapped_headers"), r_stock.json()


# --------------------------------------------------------------------------- #
# R8 - OOLU9610547 and DAFUYUAN's own numbers, end to end through the preview endpoint
# --------------------------------------------------------------------------- #


def test_pi_preview_oolu_and_dafuyuan_numbers(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    client = TestClient(app)

    supplier_ny = _create_supplier(db, code_suffix="R8NY")
    ny_mapping = {
        "客户型号": "item_code",
        "总数量\n（个）": "qty",
        "件数\n（件）": "cartons",
        "单价\n（元）": "unit_price",
        "金额\n（元）": "amount",
    }
    r_ny = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_ny,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": h, "field": f} for h, f in ny_mapping.items()],
        },
    )
    assert r_ny.status_code == 200, r_ny.text

    r_oolu = client.post(
        "/api/v1/scm/proforma-invoices/preview",
        files={"file": ("OOLU9610547.xlsx", _fixture("ny_pi_OOLU9610547.xlsx"), _XLSX)},
        data={"supplier_id": supplier_ny, "header_row": "15"},
    )
    assert r_oolu.status_code == 200, r_oolu.text
    oolu_body = r_oolu.json()
    assert oolu_body["ok"] is True, oolu_body
    assert oolu_body["line_count"] == 3, oolu_body
    assert oolu_body["documents"][0]["qty"] == 251, oolu_body["documents"][0]
    assert oolu_body["documents"][0]["total"] == 79542, oolu_body["documents"][0]

    supplier_da = _create_supplier(db, code_suffix="R8DA")
    da_mapping = {
        "产品型号": "item_code",
        "数量": "qty",
        "单价 (RMB)": "unit_price",
        "总金额 TOTAL RMB": "amount",
    }
    r_da = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_da,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": h, "field": f} for h, f in da_mapping.items()],
        },
    )
    assert r_da.status_code == 200, r_da.text

    r_dafuyuan = client.post(
        "/api/v1/scm/proforma-invoices/preview",
        files={"file": ("dafuyuan.xlsx", _fixture("dafuyuan_pi_20260922.xlsx"), _XLSX)},
        data={"supplier_id": supplier_da, "header_row": "14"},
    )
    assert r_dafuyuan.status_code == 200, r_dafuyuan.text
    da_body = r_dafuyuan.json()
    assert da_body["ok"] is True, da_body
    assert da_body["line_count"] == 15, da_body
    assert da_body["documents"][0]["qty"] == 903, da_body["documents"][0]
    assert da_body["documents"][0]["total"] == 110434, da_body["documents"][0]


# --------------------------------------------------------------------------- #
# R9 - the stock list's own real row count (corrected: 44, not 38 - see module docstring)
# --------------------------------------------------------------------------- #


def test_stock_list_preview_reads_44_rows(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.reorder.run")
    supplier_id = _create_supplier(db, code_suffix="R9")
    client = TestClient(app)

    mapping = {"客户型号": "item_code", "总数量（个）": "qty_packed"}
    r_save = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["supplier_inventory"],
            "mappings": [{"header": h, "field": f} for h, f in mapping.items()],
        },
    )
    assert r_save.status_code == 200, r_save.text

    r = client.post(
        "/api/v1/scm/supplier-inventory/preview",
        files={"file": ("stock.xlsx", _fixture("ny_stock_20260921.xlsx"), _XLSX)},
        data={"supplier_id": supplier_id, "header_row": "2"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["readable"] is True, body
    assert body["summary"]["rows"] == 44, body["summary"]


# --------------------------------------------------------------------------- #
# R10 - a numeric sample is rounded, not Python's full float repr
# --------------------------------------------------------------------------- #


def test_probe_samples_are_rounded():
    from app.services.scm.header_probe import probe

    result = probe(_fixture("ny_pi_FSCU8706420.xlsx"))
    fangshu_col = next(c for c in result.columns if c.header == "方数")
    # Row 17's own 方数 value is the float `6.5085120000000005` (Excel's own computed
    # figure, not a typo) - `str()` of it is 18 characters; a sample this long is not
    # something a human is meant to read at a glance (R5's whole point).
    assert fangshu_col.samples[1].startswith("6.5085"), fangshu_col.samples

    # The 12-char cap is about NUMBERS, not text: a product name column (工厂型号,
    # 品名, ...) legitimately carries long strings that must stay verbatim (R5's "never
    # truncated" is about HEADER text, not a licence to truncate a real product name here
    # too) - only samples that parse as a plain number are checked.
    def _looks_numeric(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    for col in result.columns:
        for sample in col.samples:
            if _looks_numeric(sample):
                assert len(sample) <= 12, (col.header, sample)


# =============================================================================
# Round 2 (owner ruling A, 24 Sep 2026): the alias unique constraint moves to
# per-supplier - one partial unique index for shared rows (supplier_id IS NULL), one for
# supplier rows (supplier_id IS NOT NULL). None of this exists yet (model still carries
# the single `uq_import_field_alias_triple`, no migration) - R11-R13 are red until the
# coder's migration lands; R14 is a regression guard for the classify() fix from round 1
# and is already green.
# =============================================================================


# --------------------------------------------------------------------------- #
# R11 - a second supplier saving the SAME header+field keeps its OWN row (owner ruling A)
# --------------------------------------------------------------------------- #


def test_second_supplier_keeps_identical_mapping(scm_app):
    from app.services.import_alias_service import AliasResolver

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.proforma_invoice.upload")
    supplier_a = _create_supplier(db, code_suffix="R11A")
    supplier_b = _create_supplier(db, code_suffix="R11B")
    client = TestClient(app)

    mapping = [
        {"header": "序号", "field": "ignore"},
        {"header": "件数（件）", "field": "cartons"},
    ]
    r_a = client.post(
        "/api/v1/scm/import-mapping/save",
        json={"supplier_id": supplier_a, "doc_types": ["proforma_invoice"], "mappings": mapping},
    )
    assert r_a.status_code == 200, r_a.text

    # Today the table's own unique triple is (doc_type, field, alias) with NO supplier_id
    # in it, so this second, unrelated supplier's IDENTICAL save silently loses the race
    # against A's already-landed row: `ON CONFLICT DO NOTHING` treats B's save as already
    # said, and B ends up with none of ITS OWN rows at all.
    r_b = client.post(
        "/api/v1/scm/import-mapping/save",
        json={"supplier_id": supplier_b, "doc_types": ["proforma_invoice"], "mappings": mapping},
    )
    assert r_b.status_code == 200, r_b.text

    resolver_b = AliasResolver.for_supplier(db, "proforma_invoice", supplier_b)
    assert resolver_b.field_for_header("件数（件）") == "cartons", (
        "supplier B's own identical mapping must resolve for B too, independent of A"
    )
    assert resolver_b.field_for_header("序号") is None, "ignore, for B"
    assert "序号" not in resolver_b.unmapped_headers({"序号": "x"}), "known (ignored), for B"

    # A is unaffected by B ever having saved anything.
    resolver_a = AliasResolver.for_supplier(db, "proforma_invoice", supplier_a)
    assert resolver_a.field_for_header("件数（件）") == "cartons"

    r_probe_b = client.post(
        "/api/v1/scm/import-mapping/probe",
        files={"file": ("FSCU8706420.xlsx", _fixture("ny_pi_FSCU8706420.xlsx"), _XLSX)},
        data={"supplier_id": supplier_b, "doc_types": "proforma_invoice"},
    )
    assert r_probe_b.status_code == 200, r_probe_b.text
    cols_b = {c["header"]: c for c in r_probe_b.json()["columns"]}
    assert cols_b["件数\n（件）"]["source"] == "supplier", cols_b["件数\n（件）"]
    assert cols_b["序号"]["source"] == "supplier", cols_b["序号"]

    # KEEP: a mapping IDENTICAL to an existing SHARED row still writes no supplier row -
    # the existing row already answers the same way theirs would have (this half must
    # still hold once the constraint splits, not just accidentally today).
    supplier_c = _create_supplier(db, code_suffix="R11C")
    r_c = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_c,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": "QTY", "field": "qty"}],
        },
    )
    assert r_c.status_code == 200, r_c.text
    from sqlalchemy import text as _text

    own_rows = db.execute(
        _text(
            "SELECT count(*) FROM import_field_alias "
            "WHERE supplier_id = :s AND doc_type = 'proforma_invoice' AND alias = 'QTY'"
        ),
        {"s": supplier_c},
    ).scalar()
    assert own_rows == 0, "identical-to-shared must not write a redundant supplier row"
    r_probe_c = client.post(
        "/api/v1/scm/import-mapping/probe",
        files={"file": ("FSCU8706420.xlsx", _fixture("ny_pi_FSCU8706420.xlsx"), _XLSX)},
        data={"supplier_id": supplier_c, "doc_types": "proforma_invoice"},
    )
    assert r_probe_c.status_code == 200, r_probe_c.text


# --------------------------------------------------------------------------- #
# R12 - the future per-supplier constraint shape (owner ruling A), exercised directly
# --------------------------------------------------------------------------- #


def test_shared_rows_stay_unique():
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    with pg_session() as db:
        doc_type = "proforma_invoice"

        # Shared (supplier_id NULL) - the seeder shape every existing `INSERT ... ON
        # CONFLICT (doc_type, field, alias) DO NOTHING` already uses, restated with the
        # partial predicate the split adds. Measured (24 Sep): Postgres accepts a full
        # (non-partial) unique index as the arbiter for a MORE restrictive `WHERE`
        # predicate than the index's own (a full index's implicit predicate, TRUE, is
        # implied by any predicate) - so this half already holds against TODAY's single
        # `uq_import_field_alias_triple` too. Not the red half; kept because it is the
        # steady-state behaviour the split must not disturb.
        alias = f"{MARKER}SHAREDR12"
        db.execute(
            text(
                "INSERT INTO import_field_alias (id, doc_type, field, alias, supplier_id) "
                "VALUES (gen_random_uuid(), :dt, 'ignore', :a, NULL)"
            ),
            {"dt": doc_type, "a": alias},
        )
        db.flush()
        db.execute(
            text(
                "INSERT INTO import_field_alias (id, doc_type, field, alias, supplier_id) "
                "VALUES (gen_random_uuid(), :dt, 'ignore', :a, NULL) "
                "ON CONFLICT (doc_type, field, alias) WHERE supplier_id IS NULL DO NOTHING"
            ),
            {"dt": doc_type, "a": alias},
        )
        count = db.execute(
            text(
                "SELECT count(*) FROM import_field_alias "
                "WHERE doc_type = :dt AND alias = :a AND supplier_id IS NULL"
            ),
            {"dt": doc_type, "a": alias},
        ).scalar()
        assert count == 1, "the duplicate SHARED insert must be a no-op"

        # Supplier-scoped (owner ruling A) - the natural arbiter for a supplier row is
        # (doc_type, field, alias, supplier_id), a FOUR-column index that does not exist
        # yet (verified directly against a scratch table carrying only today's 3-column
        # index: Postgres refuses this exact ON CONFLICT target with "no unique or
        # exclusion constraint matching the ON CONFLICT specification", 42P10). This is
        # the half that is genuinely red until `uq_import_field_alias_supplier` exists.
        supplier_id = _seed_supplier_with_company(db, code_suffix="R12")
        supplier_alias = f"{MARKER}SUPR12"
        db.execute(
            text(
                "INSERT INTO import_field_alias (id, doc_type, field, alias, supplier_id) "
                "VALUES (gen_random_uuid(), :dt, 'ignore', :a, :s)"
            ),
            {"dt": doc_type, "a": supplier_alias, "s": supplier_id},
        )
        db.flush()
        try:
            db.execute(
                text(
                    "INSERT INTO import_field_alias (id, doc_type, field, alias, supplier_id) "
                    "VALUES (gen_random_uuid(), :dt, 'ignore', :a, :s) "
                    "ON CONFLICT (doc_type, field, alias, supplier_id) DO NOTHING"
                ),
                {"dt": doc_type, "a": supplier_alias, "s": supplier_id},
            )
        except ProgrammingError as exc:
            raise AssertionError(
                "no unique index on (doc_type, field, alias, supplier_id) exists yet "
                f"(owner ruling A, uq_import_field_alias_supplier): {exc}"
            ) from exc
        count2 = db.execute(
            text(
                "SELECT count(*) FROM import_field_alias "
                "WHERE doc_type = :dt AND alias = :a AND supplier_id = :s"
            ),
            {"dt": doc_type, "a": supplier_alias, "s": supplier_id},
        ).scalar()
        assert count2 == 1, "the duplicate SUPPLIER insert must be a no-op too"


# --------------------------------------------------------------------------- #
# R13 - the migration itself: the two new indexes exist, the old one is gone
# --------------------------------------------------------------------------- #


def test_migration_indexes_exist():
    from sqlalchemy import text

    with pg_session() as db:
        rows = db.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'import_field_alias'")
        ).fetchall()
        names = {r[0] for r in rows}
        # Red until the coder's migration is written AND applied to this private DB
        # (sorento_icm_ci) - today only `uq_import_field_alias_triple` exists.
        assert "uq_import_field_alias_shared" in names, names
        assert "uq_import_field_alias_supplier" in names, names
        assert "uq_import_field_alias_triple" not in names, (
            "the old single triple constraint must be dropped by the migration"
        )


# --------------------------------------------------------------------------- #
# R14 - DAFUYUAN through /supplier-documents/preview: one file, one block (regression
# guard for round 1's classify() fix - expected GREEN)
# --------------------------------------------------------------------------- #


def test_supplier_documents_preview_dafuyuan_single_block(scm_app):
    import json

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    grant_permission(db, "purchasing", "scm.reorder.run")
    supplier_id = _create_supplier(db, code_suffix="R14")
    client = TestClient(app)

    mapping = {
        "产品型号": "item_code",
        "数量": "qty",
        "单价 (RMB)": "unit_price",
        "总金额 TOTAL RMB": "amount",
        "序号": "ignore",
        "箱数": "ignore",
    }
    r_save = client.post(
        "/api/v1/scm/import-mapping/save",
        json={
            "supplier_id": supplier_id,
            "doc_types": ["proforma_invoice"],
            "mappings": [{"header": h, "field": f} for h, f in mapping.items()],
        },
    )
    assert r_save.status_code == 200, r_save.text

    r = client.post(
        "/api/v1/scm/supplier-documents/preview",
        files=[("files", ("dafuyuan.xlsx", _fixture("dafuyuan_pi_20260922.xlsx"), _XLSX))],
        data={"supplier_id": supplier_id, "header_rows": json.dumps({"dafuyuan.xlsx": 14})},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["files"]) == 1, body
    f = body["files"][0]
    # Corrected TWICE against the real bytes (measured 24 Sep), both against the
    # function's own name:
    #   1. The file's OWN row 12 reads "SORENTO装箱单 20260922（1）" (the original filename,
    #      embedded as a text line in the sheet itself) alongside row 3's "PROFORMA
    #      INVOICE - 形式发票" - `classify()`'s title scan sees BOTH the PI and the PL
    #      marker and correctly calls it "combined", not "proforma_invoice".
    #   2. "Single block" does not hold either: `packing_list`'s SHARED aliases already
    #      resolve 产品型号/数量/箱数 (item_code/qty/cartons - verified directly against
    #      `sorento_icm_ci`) with nothing supplier-scoped saved for that doc type at all,
    #      so the SAME sheet reads as a valid packing block too (cartons 744, the file's
    #      own stated total) - a combined file's blocks come from BOTH readers (G4's own
    #      design), and this one satisfies both on shared aliases alone. Two blocks is
    #      the real, correct green state; what R14 actually pins is the PI block's own
    #      numbers among them.
    assert f["kind"] == "combined", f
    assert len(f["blocks"]) == 2, f["blocks"]
    pi_block = next(b for b in f["blocks"] if b["amount"] == 110434)
    assert pi_block["line_count"] == 15, pi_block
    pl_block = next(b for b in f["blocks"] if b["cartons"] == 744)
    assert pl_block is not None
