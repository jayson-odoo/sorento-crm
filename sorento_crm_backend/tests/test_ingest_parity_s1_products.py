"""RED tests for ingest parity standardisation, Phase S1 (shared resolver and
product rules).

UAC: documentation/plans/autocount/ingest-parity-standardisation-acceptance-criteria.md
     Phase S1, AC-P1-1 .. AC-P1-9.
PLAN: documentation/plans/autocount/PLAN-ingest-parity-standardisation.md sections 2.1, 2.2.

`app/services/rules/` does not exist yet (S1's own deliverable). Two shapes of
test below:

* **Pure-function tests** (`clean_supplier_name`, `resolve_supplier_by_name`,
  the dimension-parser golden set) import the not-yet-existing rules module
  INSIDE the test body. Today that raises `ModuleNotFoundError` - the correct
  red for a function that has not been extracted yet.
* **Behavioural tests** call the real, already-existing services
  (`MasterIngestService`, `ProductService`, `WarehouseService`,
  `SupplierService`, ...) and assert on the outcome. These fail on a plain
  `AssertionError` today, never on an import, because the gap is in what the
  existing code does, not in a module that is missing.

Facts verified in the code before relying on them (see the PR/task report for
the full list): `is_discontinued_from_description` / `is_discontinued_from_row`
/ `parse_dimensions_from_description` live in `app/services/product_service.py`
today; `products` has `dimensions_length` / `dimensions_width` /
`dimensions_height` (`Numeric(10,2)`, mm) but NO `remark` column; `brands` has
`brand_code` / `brand_name` and `products.brand_id` is a nullable FK to it;
`ensure_reference` is a closure INSIDE `bulk_import_products`, not a
standalone function; the xlsx warehouse import
(`InventoryService.bulk_import_warehouses`) already matches
`func.lower(warehouse_code)` and is correct today - not exercised as a red
case here; `WarehouseService.create_warehouse` / `SupplierService.create_supplier`
/ `ProductCategoryService.create_category` / `UnitOfMeasureService.create_uom`
all match on the raw column value (exact, case-sensitive); `MasterIngestService`
matches every non-agent entity's code on the raw column too
(`normalized_code=False` in `ENTITY_SPECS`); `CanonicalProduct` (S0's contract)
has no `is_discontinued` or `remark` field yet, so a payload carrying either
fails today on `extra="forbid"` - that failure IS the correct red for those
two cases, named explicitly rather than worked around. `brand_code` is
DIFFERENT: it already exists on `CanonicalProduct` (verified by reading
`app/schemas/canonical_masters.py` directly, correcting an initial assumption)
- the gap is that `master_ingest_service._product_columns` never reads
`payload.brand_code` at all, so it is accepted and silently ignored, never
resolved into `products.brand_id` and never reported `brand_created`.

Substrate: `tests._pg_fixture.blank_session()`, same as the S0 file.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import SystemSetting
from app.schemas.inventory import WarehouseCreate
from app.schemas.procurement import SupplierCreate
from app.schemas.product import ProductCategoryCreate, ProductCreate, UnitOfMeasureCreate
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.inventory_service import WarehouseService
from app.services.master_ingest_service import IngestOutcome, MasterIngestService
from app.services.procurement_service import SupplierService
from app.services.product_service import ProductCategoryService, ProductService, UnitOfMeasureService

from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTIP1"

_GENERIC_EXCLUDE = {"id", "company_id", "created_at", "updated_at", "source", "created_by"}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def company_b(db) -> str:
    company = Company(id=str(uuid.uuid4()), name=f"{MARKER} B", code=unique_code(MARKER)[:10])
    db.add(company)
    db.flush()
    return str(company.id)


def _esb(db, company_id: str) -> MasterIngestService:
    return MasterIngestService(db, integration_id=None, company_id=company_id)


def _code(stem: str) -> str:
    return unique_code(f"{MARKER}{stem}")[:30]


def _mapped_columns(model) -> list[str]:
    return [
        c.name
        for c in model.__table__.columns
        if c.name not in _GENERIC_EXCLUDE and not c.name.endswith("_id")
    ]


def _row_values(db, table: str, code_column: str, code: str, company_id: str, columns: list[str]):
    cols = ", ".join(columns)
    row = db.execute(
        text(f"SELECT {cols} FROM {table} WHERE {code_column} = :c AND company_id = :cid"),
        {"c": code, "cid": company_id},
    ).mappings().first()
    return dict(row) if row else None


class TestAcP11CaseInsensitiveCodeMatchingAcrossPaths:
    """D17: one `upper(btrim())` code match for every master on every path.
    The xlsx warehouse import already normalises (`func.lower(...)` in
    `bulk_import_warehouses`) and is deliberately not re-tested here since it
    is already correct - only the manual-create and ESB paths are red.
    """

    def test_warehouse_manual_create_does_not_adopt_a_case_and_whitespace_variant(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = _code("BRW")
        db.add(Warehouse(warehouse_code=code, warehouse_name="Main"))
        db.flush()

        WarehouseService(db).create_warehouse(
            WarehouseCreate(warehouse_code=f" {code.lower()} ", warehouse_name="Duplicate")
        )
        count = db.execute(
            text("SELECT count(*) FROM warehouses WHERE upper(btrim(warehouse_code)) = upper(btrim(:c))"),
            {"c": code},
        ).scalar()
        assert count == 1, "manual create must adopt a case+whitespace variant, not duplicate"

    def test_warehouse_esb_push_does_not_adopt_a_case_and_whitespace_variant(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = _code("BRW2")
        db.add(Warehouse(warehouse_code=code, warehouse_name="Main"))
        db.flush()

        svc = _esb(db, DEFAULT_COMPANY_ID)
        result = svc.ingest(
            "warehouses",
            [{"source_ref": f"DK-{code}", "code": f" {code.lower()} ", "name": "Main"}],
        )
        assert result.updated == 1, result.records[0].errors

    def test_supplier_esb_push_does_not_adopt_a_case_and_whitespace_variant(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = _code("SUPCI")
        db.add(Supplier(supplier_code=code, supplier_name="Acme"))
        db.flush()

        svc = _esb(db, DEFAULT_COMPANY_ID)
        result = svc.ingest(
            "suppliers", [{"source_ref": f"DK-{code}", "code": f" {code.lower()} ", "name": "Acme"}]
        )
        assert result.updated == 1, result.records[0].errors

    def test_category_esb_push_does_not_adopt_a_case_and_whitespace_variant(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = _code("CATCI")
        db.add(ProductCategory(category_code=code, category_name="Fasteners"))
        db.flush()

        svc = _esb(db, DEFAULT_COMPANY_ID)
        result = svc.ingest(
            "product_categories",
            [{"source_ref": f"DK-{code}", "code": f" {code.lower()} ", "name": "Fasteners"}],
        )
        assert result.updated == 1, result.records[0].errors

    def test_uom_esb_push_does_not_adopt_a_case_and_whitespace_variant(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = _code("UOMCI")
        db.add(UnitOfMeasure(uom_code=code, uom_name="Each"))
        db.flush()

        svc = _esb(db, DEFAULT_COMPANY_ID)
        result = svc.ingest(
            "units_of_measure", [{"source_ref": f"DK-{code}", "code": f" {code.lower()} ", "name": "Each"}]
        )
        assert result.updated == 1, result.records[0].errors

    def test_product_esb_push_does_not_adopt_a_case_and_whitespace_variant(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code, uom_code = _code("P1CAT"), _code("P1UOM")
        category = ProductCategoryService(db).create_category(
            ProductCategoryCreate(category_code=cat_code, category_name="Cat")
        )
        uom = UnitOfMeasureService(db).create_uom(
            UnitOfMeasureCreate(uom_code=uom_code, uom_name="Each")
        )
        code = _code("P1PRD")
        db.add(
            Product(
                product_code=code,
                product_name="Item",
                category_id=category.id,
                base_uom_id=uom.id,
                list_price=Decimal("1.00"),
            )
        )
        db.flush()

        svc = _esb(db, DEFAULT_COMPANY_ID)
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": f" {code.lower()} ",
                    "name": "Item",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                }
            ],
        )
        assert result.updated == 1, result.records[0].errors


class TestAcP12SupplierNameCleaningAndAmbiguity:
    """D2 in outstanding_import_service (`_clean_supplier_name`) and the
    ambiguity refusal in po_history_service must become one shared
    `master_rules.clean_supplier_name` / `resolve_supplier_by_name`, called by
    the manual create and the ESB masters push too."""

    def test_clean_supplier_name_strips_the_currency_suffix(self):
        from app.services.rules.master_rules import clean_supplier_name

        assert clean_supplier_name("ACME (RMB)") == "ACME"

    def test_resolve_supplier_by_name_refuses_an_ambiguous_cleaned_name(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code_a, code_b = _code("SUPA"), _code("SUPB")
        db.add_all(
            [
                Supplier(supplier_code=code_a, supplier_name="ACME (RMB)"),
                Supplier(supplier_code=code_b, supplier_name="ACME (USD)"),
            ]
        )
        db.flush()

        from app.services.rules.master_rules import resolve_supplier_by_name

        result = resolve_supplier_by_name(db, "ACME (SGD)", DEFAULT_COMPANY_ID)
        assert result is None, "an ambiguous cleaned name must refuse, not silently pick one"

    def test_esb_supplier_name_currency_suffix_is_cleaned(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = _code("SUPRMB")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        result = svc.ingest(
            "suppliers", [{"source_ref": f"DK-{code}", "code": code, "name": "ACME (RMB)"}]
        )
        assert result.created == 1, result.records[0].errors
        name = db.execute(
            text("SELECT supplier_name FROM suppliers WHERE supplier_code = :c"), {"c": code}
        ).scalar()
        assert name == "ACME"

    def test_manual_supplier_name_currency_suffix_is_cleaned(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        code = _code("SUPRMB2")
        supplier = SupplierService(db).create_supplier(
            SupplierCreate(supplier_code=code, supplier_name="ACME (RMB)")
        )
        assert supplier.supplier_name == "ACME"


class TestAcP13DiscontinuedFlagWinsAndWatermarkReset:
    """D2: `is_discontinued = flag if sent else description.startswith('****')`
    on every path; flag wins; true->false resets the notify watermark.

    The Excel import (`bulk_import_products` / `is_discontinued_from_row`)
    already implements this correctly and is not re-tested here - only manual
    create/update (no flag field on the schema at all) and the ESB (no field,
    no derivation, no watermark reset) are red.
    """

    def test_manual_create_has_no_explicit_flag_field_prefix_always_wins(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat = ProductCategoryService(db).create_category(
            ProductCategoryCreate(category_code=_code("DC1CAT"), category_name="Cat")
        )
        uom = UnitOfMeasureService(db).create_uom(
            UnitOfMeasureCreate(uom_code=_code("DC1UOM"), uom_name="Each")
        )
        product = ProductService(db).create_product(
            ProductCreate(
                product_code=_code("DC1PRD"),
                product_name="Old Model",
                description="**** Old Model",
                category_id=cat.id,
                base_uom_id=uom.id,
                list_price=Decimal("1.00"),
                is_discontinued=False,  # not a declared field on ProductCreate - silently dropped
            ),
            created_by=None,
        )
        assert product.is_discontinued is False, "an explicit flag must win over the **** prefix"

    def test_esb_push_does_not_derive_discontinued_from_description(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code, uom_code = _code("DC2CAT"), _code("DC2UOM")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("DC2PRD")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "Old Model",
                    "description": "**** Old Model",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                }
            ],
        )
        assert result.created == 1, result.records[0].errors
        is_discontinued = db.execute(
            text("SELECT is_discontinued FROM products WHERE product_code = :c"), {"c": code}
        ).scalar()
        assert is_discontinued is True, "a **** description must derive discontinued on the ESB path too"

    def test_esb_payload_does_not_yet_accept_an_explicit_discontinued_flag(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code, uom_code = _code("DC3CAT"), _code("DC3UOM")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("DC3PRD")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "Old Model",
                    "description": "**** Old Model",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                    "is_discontinued": False,
                }
            ],
        )
        assert result.created == 1, result.records[0].errors

    def test_esb_update_does_not_reset_watermark_when_flipping_to_not_discontinued(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code, uom_code = _code("DC4CAT"), _code("DC4UOM")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("DC4PRD")
        ref = f"DK-{code}"
        svc.ingest(
            "products",
            [{"source_ref": ref, "code": code, "name": "Old", "category_code": cat_code, "uom_code": uom_code}],
        )
        # Seed the discontinued state + watermark by hand - today's ESB write never
        # touches these columns at all, so there is no other way to get them set.
        db.execute(
            text(
                "UPDATE products SET is_discontinued = true, discontinued_notified_at = now(), "
                "discontinued_notify_batch_id = :bid WHERE product_code = :c"
            ),
            {"bid": str(uuid.uuid4()), "c": code},
        )
        db.flush()

        svc.ingest(
            "products",
            [
                {
                    "source_ref": ref,
                    "code": code,
                    "name": "Not Discontinued Any More",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                }
            ],
        )

        row = db.execute(
            text(
                "SELECT is_discontinued, discontinued_notified_at, discontinued_notify_batch_id "
                "FROM products WHERE product_code = :c"
            ),
            {"c": code},
        ).first()
        assert row == (False, None, None), "true->false must reset the notify watermark on the ESB path too"


class TestAcP14UnknownReferencesCreatedWithWarnings:
    """D3: an unknown category/uom/brand on a product push is created
    (`ensure_reference`), never retryable; a blank uom resolves to the
    configured default. Today `_product_columns` raises `MissingReference`
    for any unresolved category/uom code, and `CanonicalProduct` has no
    `brand_code` field at all."""

    def test_unknown_category_is_created_with_warning_not_retryable(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        uom_code = _code("P4UOM")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("P4PRD")
        cat_code = _code("P4CATX")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "New Item",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                }
            ],
        )
        record = result.records[0]
        assert record.outcome is IngestOutcome.CREATED, record.errors
        assert "category_created" in record.warnings
        created = db.execute(
            text("SELECT category_code, category_name FROM product_categories WHERE category_code = :c"),
            {"c": cat_code},
        ).first()
        assert created == (cat_code, cat_code)

    def test_unknown_uom_is_created_with_warning_not_retryable(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code = _code("P4CAT2")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        code = _code("P4PRD2")
        uom_code = _code("P4UOMX")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "New Item",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                }
            ],
        )
        record = result.records[0]
        assert record.outcome is IngestOutcome.CREATED, record.errors
        assert "uom_created" in record.warnings

    def test_unknown_brand_code_is_silently_ignored_not_created(self, db):
        """`brand_code` already exists on `CanonicalProduct`; the gap is that
        `_product_columns` never reads it, so an unknown brand is neither
        created nor reported - not a validation failure."""
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code, uom_code = _code("P4CAT3"), _code("P4UOM3")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("P4PRD3")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "New Item",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                    "brand_code": "NEWBRAND",
                }
            ],
        )
        record = result.records[0]
        assert record.outcome is IngestOutcome.CREATED, record.errors
        assert "brand_created" in record.warnings

    def test_blank_uom_resolves_to_the_configured_default(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        default_uom = UnitOfMeasureService(db).create_uom(
            UnitOfMeasureCreate(uom_code=_code("P4DEFUOM"), uom_name="Default Each")
        )
        db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co", default_uom_id=default_uom.id))
        db.flush()
        cat_code = _code("P4CAT4")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        code = _code("P4PRD4")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "New Item",
                    "category_code": cat_code,
                    "uom_code": "",
                }
            ],
        )
        assert result.created == 1, result.records[0].errors
        base_uom_id = db.execute(
            text("SELECT base_uom_id FROM products WHERE product_code = :c"), {"c": code}
        ).scalar()
        assert str(base_uom_id) == str(default_uom.id)


class TestAcP15DimensionParserGoldenSet:
    """D4: the shared dimension parser accepts every real AutoCount form -
    mixed x/X, optional parentheses, optional MM suffix, and the 2-D case
    (height NULL). The existing `parse_dimensions_from_description` already
    handles most of these; it does NOT handle the 2-D case at all (its regex
    requires three numbers), which is why this targets the NEW shared
    `product_rules.parse_dimensions` rather than the existing function."""

    GOLDEN_SET = [
        ("880x450x220MM", (Decimal("880"), Decimal("450"), Decimal("220"))),
        ("(600X470X430MM)", (Decimal("600"), Decimal("470"), Decimal("430"))),
        ("1000x500", (Decimal("1000"), Decimal("500"), None)),  # 2-D: height NULL
        ("Cabinet 900X600x450", (Decimal("900"), Decimal("600"), Decimal("450"))),
        ("Sink 45x38CM", (Decimal("450"), Decimal("380"), None)),  # 2-D, cm unit
        ("Wardrobe (1200x600x2000MM)", (Decimal("1200"), Decimal("600"), Decimal("2000"))),
        ("Basin 500 x 400 x 150 mm", (Decimal("500"), Decimal("400"), Decimal("150"))),
        ("Rack 1.2Mx0.6Mx2M", (Decimal("1200"), Decimal("600"), Decimal("2000"))),
        ("****Discontinued 880x450x220MM", (Decimal("880"), Decimal("450"), Decimal("220"))),
        ("No dimensions here", (None, None, None)),
    ]

    def test_golden_set_of_ten_autocount_description_forms(self):
        from app.services.rules.product_rules import parse_dimensions

        for description, expected in self.GOLDEN_SET:
            assert parse_dimensions(description) == expected, description


class TestAcP16RemarkStoredNeverConcatenated:
    """D4: the ESB product payload gains optional `remark` (AutoCount
    `Item.Desc2`), stored on its own column, never concatenated into
    `description` the way the xlsx import's Desc 2 handling does."""

    def test_esb_payload_does_not_yet_accept_remark(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code, uom_code = _code("P6CAT"), _code("P6UOM")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("P6PRD")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "Item",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                    "remark": "Item.Desc2 text",
                }
            ],
        )
        assert result.created == 1, result.records[0].errors

    def test_products_table_has_no_remark_column_yet(self):
        assert "remark" in Product.__table__.columns, (
            "S1 must add products.remark (or an equivalent nullable column) so "
            "Item.Desc2 lands without being concatenated into description"
        )


class TestAcP17DefaultSupplierLeadTimeOnEsbProduct:
    """D5: the ESB creates/updates a product-supplier link to the configured
    default supplier with the configured standard lead time, exactly as the
    Excel import does. Today `_product_columns`/`_apply` never touches
    `product_suppliers` at all."""

    def test_esb_create_links_default_supplier_with_configured_lead_time(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        supplier = SupplierService(db).create_supplier(
            SupplierCreate(supplier_code=_code("P7SUP"), supplier_name="Default Supplier")
        )
        db.add(
            SystemSetting(
                id=str(uuid.uuid4()),
                name=f"{MARKER} Co",
                default_product_supplier_id=supplier.id,
                default_product_standard_lead_time_days=45,
            )
        )
        db.flush()
        cat_code, uom_code = _code("P7CAT"), _code("P7UOM")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("P7PRD")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "Item",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                }
            ],
        )
        assert result.created == 1, result.records[0].errors
        product_id = result.records[0].entity_id
        lead_time = db.execute(
            text(
                "SELECT standard_lead_time_days FROM product_suppliers "
                "WHERE product_id = :p AND supplier_id = :s"
            ),
            {"p": product_id, "s": supplier.id},
        ).scalar()
        assert lead_time == 45

    def test_esb_update_refreshes_the_default_suppliers_lead_time(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        supplier = SupplierService(db).create_supplier(
            SupplierCreate(supplier_code=_code("P7SUP2"), supplier_name="Default Supplier")
        )
        settings = SystemSetting(
            id=str(uuid.uuid4()),
            name=f"{MARKER} Co",
            default_product_supplier_id=supplier.id,
            default_product_standard_lead_time_days=30,
        )
        db.add(settings)
        db.flush()
        cat_code, uom_code = _code("P7CAT2"), _code("P7UOM2")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("P7PRD2")
        ref = f"DK-{code}"
        result = svc.ingest(
            "products",
            [{"source_ref": ref, "code": code, "name": "Item", "category_code": cat_code, "uom_code": uom_code}],
        )
        product_id = result.records[0].entity_id
        # The create call above already links the default supplier at the
        # then-configured lead time (30) - AC-P1-7's create half, proven by
        # the sibling test above. This test is only about the REFRESH-on-update
        # half: bump the configured lead time and re-push the same product.
        settings.default_product_standard_lead_time_days = 45
        db.flush()
        svc.ingest(
            "products",
            [
                {
                    "source_ref": ref,
                    "code": code,
                    "name": "Item Updated",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                }
            ],
        )

        lead_time = db.execute(
            text(
                "SELECT standard_lead_time_days FROM product_suppliers "
                "WHERE product_id = :p AND supplier_id = :s"
            ),
            {"p": product_id, "s": supplier.id},
        ).scalar()
        assert lead_time == 45


class TestAcP18BrandCodeResolveOrCreate:
    """D5: both channels resolve-or-create the brand named by `brand_code` and
    set `products.brand_id`. `brand_code` already exists on `CanonicalProduct`
    - the gap is entirely in `master_ingest_service._product_columns`, which
    never reads it, so it is accepted and silently dropped rather than
    resolved."""

    def test_esb_brand_code_is_accepted_but_never_resolved_into_brand_id(self, db):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code, uom_code = _code("P8CAT"), _code("P8UOM")
        svc = _esb(db, DEFAULT_COMPANY_ID)
        svc.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        svc.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        code = _code("P8PRD")
        result = svc.ingest(
            "products",
            [
                {
                    "source_ref": f"DK-{code}",
                    "code": code,
                    "name": "Item",
                    "category_code": cat_code,
                    "uom_code": uom_code,
                    "brand_code": "ACME-BRAND",
                }
            ],
        )
        assert result.created == 1, result.records[0].errors
        brand_id = db.execute(
            text("SELECT brand_id FROM products WHERE product_code = :c"), {"c": code}
        ).scalar()
        assert brand_id is not None
        brand_code = (
            db.execute(text("SELECT brand_code FROM brands WHERE id = :i"), {"i": brand_id}).scalar()
            if brand_id
            else None
        )
        assert brand_code == "ACME-BRAND"


class TestAcP19BulkImportVsEsbParity:
    """A scaled-down stand-in for the UAC's 20-real-row AED_SORENTO fixture
    (building and committing that exact fixture is left to the coder/reviewer
    pass): three representative shapes - plain, ****-discontinued, and a
    dimensioned description - through `bulk_import_products` into company A
    and through the ESB into company B. `remark` is excluded from the diff by
    design (xlsx concatenates Desc 2 into description, the ESB will store it
    separately - PLAN 2.1); today `Product` has no `remark` column at all, so
    the exclusion is a no-op filter, kept for when S1 adds the column.
    """

    def test_representative_product_rows_bulk_import_vs_esb_parity(self, db, company_b):
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        cat_code, uom_code = _code("P9CAT"), _code("P9UOM")
        ProductCategoryService(db).create_category(
            ProductCategoryCreate(category_code=cat_code, category_name="Cat")
        )
        UnitOfMeasureService(db).create_uom(UnitOfMeasureCreate(uom_code=uom_code, uom_name="Each"))

        rows = [
            {"code": _code("P9PLAIN"), "name": "Plain Product", "description": "A plain product"},
            {"code": _code("P9DISC"), "name": "Discontinued Product", "description": "**** Old Model"},
            {
                "code": _code("P9DIM"),
                "name": "Dimensioned Product",
                "description": "Cabinet 880x450x220MM",
            },
        ]

        xlsx_rows = [
            {
                "product_code": r["code"],
                "product_name": r["name"],
                "description": r["description"],
                "item_group": cat_code,
                "uom": uom_code,
                "list_price": "10.00",
            }
            for r in rows
        ]
        ProductService(db).bulk_import_products(xlsx_rows, user_id=None)

        esb = _esb(db, company_b)
        esb.ingest("product_categories", [{"source_ref": f"DK-{cat_code}", "code": cat_code, "name": "Cat"}])
        esb.ingest("units_of_measure", [{"source_ref": f"DK-{uom_code}", "code": uom_code, "name": "Each"}])
        for r in rows:
            esb.ingest(
                "products",
                [
                    {
                        "source_ref": f"DK-{r['code']}",
                        "code": r["code"],
                        "name": r["name"],
                        "description": r["description"],
                        "category_code": cat_code,
                        "uom_code": uom_code,
                        "list_price": "10.00",
                    }
                ],
            )

        columns = [c for c in _mapped_columns(Product) if c != "remark"]
        for r in rows:
            manual_row = _row_values(db, "products", "product_code", r["code"], DEFAULT_COMPANY_ID, columns)
            esb_row = _row_values(db, "products", "product_code", r["code"], company_b, columns)
            diff = {k: (manual_row.get(k), esb_row.get(k)) for k in columns if manual_row.get(k) != esb_row.get(k)}
            assert diff == {}, (r["code"], diff)
