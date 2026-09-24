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
