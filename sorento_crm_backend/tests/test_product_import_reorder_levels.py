"""The product list upload carries AutoCount's reorder level and reorder quantity.

> "this is the reorder level and quantity sheet, this is uploaded at the product list ...
>  now we need to capture the reorder level and reorder quantity which is by product"

The whole risk of this feature is in three values that must stay apart:

  * a NUMBER (including 0) - a real threshold; the SCM engine plans against it
  * BLANK   - AutoCount says there is no level; the held one is cleared
  * ABSENT  - the file does not carry the column; every held level is left alone

The frontend parses the sheet with `sheet_to_json`, which omits blank cells, so BLANK and
ABSENT arrive as the same row dict. The importer therefore decides column presence ONCE
per file. `test_a_file_with_no_reorder_column_leaves_a_held_level_alone` is the regression
that matters: without it, one upload of an older product file empties every level in the
system.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import product_service as product_service_mod
from app.services.product_service import (
    ABSENT,
    ReorderCellError,
    _REORDER_LEVEL_HEADERS,
    _REORDER_QTY_HEADERS,
    ProductService,
    file_carries_reorder_column,
    reorder_cell,
)
from tests._pg_fixture import blank_session

USER_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _isolate_side_effects(monkeypatch):
    """Embeddings enqueue RQ jobs and suppliers are irrelevant to reorder levels."""
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_bulk_publish_product_embedding_events",
        lambda self, *a, **kw: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_resolve_default_supplier_for_new_product",
        lambda self: None,
    )
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_default_standard_lead_time_days",
        lambda self: None,
    )


@pytest.fixture(autouse=True)
def _no_scm_writes(monkeypatch):
    """These tests are about the item master.

    The planning half is exercised in `scm/test_reorder_level_import.py`, against the
    service that owns it. Stubbed here so a blank schema without the `scm` tables cannot
    turn an item-master assertion into a schema failure.
    """
    monkeypatch.setattr(
        product_service_mod.ProductService,
        "_apply_reorder_levels_to_scm",
        lambda self, *a, **kw: {},
    )


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def uom(db):
    row = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="EA", uom_name="Each")
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def held(db, uom):
    """A product already holding a reorder level, as a curated value would be."""
    cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-FT", category_name="SRT-FT")
    db.add(cat)
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code="HELD-1",
        product_name="held",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=0,
        is_active=True,
        is_discontinued=False,
        reorder_level=250,
        reorder_quantity=100,
    )
    db.add(product)
    db.commit()
    return product


def _row(code: str, **over):
    row = {
        "Item Code": code,
        "Description": f"desc {code}",
        "Item Group": "SRT-FT",
        "Item Brand": "SORENTO",
        "Price": "10",
        "Is Active": "T",
    }
    row.update(over)
    return row


# --------------------------------------------------------------------------- #
# the three-way cell read
# --------------------------------------------------------------------------- #

def test_a_missing_column_reads_as_absent_not_as_blank():
    assert reorder_cell({"Item Code": "P1"}, _REORDER_LEVEL_HEADERS) is ABSENT


@pytest.mark.parametrize("cell", ["", "   ", None])
def test_an_empty_cell_reads_as_blank(cell):
    assert reorder_cell({"Reorder Level": cell}, _REORDER_LEVEL_HEADERS) is None


@pytest.mark.parametrize(
    "cell,expected",
    [(0, 0), ("0", 0), (0.0, 0), ("0.0", 0), (250, 250), ("250.0", 250), ("1,200", 1200)],
)
def test_a_number_reads_as_that_number_and_zero_is_a_number(cell, expected):
    assert reorder_cell({"Reorder Level": cell}, _REORDER_LEVEL_HEADERS) == expected


def test_a_fractional_level_rounds_rather_than_failing_the_product_row():
    assert reorder_cell({"Reorder Level": "2.6"}, _REORDER_LEVEL_HEADERS) == 3


def test_a_non_numeric_cell_is_an_error_the_row_can_be_reported_with():
    with pytest.raises(ReorderCellError):
        reorder_cell({"Reorder Level": "abc"}, _REORDER_LEVEL_HEADERS)


def test_the_alias_spellings_are_all_understood():
    for header in ("Reorder Level", "Re-order Level", "ReorderLevel", "Min Level"):
        assert reorder_cell({header: 7}, _REORDER_LEVEL_HEADERS) == 7
    for header in ("Reorder Qty", "Reorder Quantity", "Re-order Qty", "ReorderQty"):
        assert reorder_cell({header: 7}, _REORDER_QTY_HEADERS) == 7


# --------------------------------------------------------------------------- #
# column presence, decided once per file
# --------------------------------------------------------------------------- #

def test_a_file_that_names_a_level_anywhere_carries_the_column():
    rows = [{"Item Code": "A"}, {"Item Code": "B", "Reorder Level": 0}]
    assert file_carries_reorder_column(rows, _REORDER_LEVEL_HEADERS) is True


def test_a_file_whose_every_cell_is_blank_is_treated_as_not_carrying_it():
    """Indistinguishable from a file with no column, and clearing every level in the
    system is the wrong way to resolve that ambiguity."""
    rows = [{"Item Code": "A", "Reorder Level": ""}, {"Item Code": "B", "Reorder Level": None}]
    assert file_carries_reorder_column(rows, _REORDER_LEVEL_HEADERS) is False


def test_a_junk_value_still_proves_the_column_is_there():
    rows = [{"Item Code": "A", "Reorder Level": "abc"}]
    assert file_carries_reorder_column(rows, _REORDER_LEVEL_HEADERS) is True


# --------------------------------------------------------------------------- #
# what the import writes
# --------------------------------------------------------------------------- #

def test_a_level_and_a_quantity_land_on_a_new_product(db, uom):
    ProductService(db).bulk_import_products(
        [_row("P1", **{"Reorder Level": 250, "Reorder Qty": 100})], USER_ID
    )

    product = db.query(Product).filter(Product.product_code == "P1").one()
    assert product.reorder_level == 250
    assert product.reorder_quantity == 100


def test_zero_is_stored_as_zero_not_as_nothing(db, uom):
    """A NULL level means nobody set one and the SCM engine emits `needs_level`; a 0 is a
    real threshold it plans against. 7,852 of the 11,649 rows in the sample file are 0."""
    ProductService(db).bulk_import_products(
        [_row("P1", **{"Reorder Level": 0, "Reorder Qty": 0})], USER_ID
    )

    product = db.query(Product).filter(Product.product_code == "P1").one()
    assert product.reorder_level == 0
    assert product.reorder_quantity == 0


def test_a_blank_cell_on_a_new_product_leaves_it_unset(db, uom):
    ProductService(db).bulk_import_products(
        [_row("P1", **{"Reorder Level": ""}), _row("P2", **{"Reorder Level": 5})], USER_ID
    )

    assert db.query(Product).filter(Product.product_code == "P1").one().reorder_level is None


def test_a_blank_cell_clears_a_held_level(db, held):
    """AutoCount owns the number: a blank in a column the file carries means it is gone."""
    ProductService(db).bulk_import_products(
        [_row("HELD-1", **{"Reorder Level": ""}), _row("P2", **{"Reorder Level": 5})], USER_ID
    )

    db.refresh(held)
    assert held.reorder_level is None


def test_a_blank_cell_the_sheet_parser_dropped_still_clears(db, held):
    """The shape a REAL upload has.

    `sheet_to_json` on the frontend omits blank cells entirely, so the blank row arrives
    with no `Reorder Level` key at all - not with an empty string. A version of this that
    only handled the empty string wrote its ABSENT sentinel into the column instead of
    clearing it, and every test using an explicit "" passed anyway.
    """
    rows = [_row("HELD-1"), _row("P2", **{"Reorder Level": 5})]
    assert "Reorder Level" not in rows[0]

    ProductService(db).bulk_import_products(rows, USER_ID)

    db.refresh(held)
    assert held.reorder_level is None
    assert held.reorder_quantity == 100, "no Reorder Qty column, so the held qty stands"


def test_a_dropped_blank_on_a_new_product_leaves_it_unset(db, uom):
    ProductService(db).bulk_import_products(
        [_row("P1"), _row("P2", **{"Reorder Level": 5, "Reorder Qty": 2})], USER_ID
    )

    p1 = db.query(Product).filter(Product.product_code == "P1").one()
    assert p1.reorder_level is None
    assert p1.reorder_quantity is None


def test_a_file_with_no_reorder_column_leaves_a_held_level_alone(db, held):
    """The regression that matters: every product upload predating this feature has no
    such column, and must not be read as "every level is blank"."""
    ProductService(db).bulk_import_products([_row("HELD-1")], USER_ID)

    db.refresh(held)
    assert held.reorder_level == 250
    assert held.reorder_quantity == 100


def test_a_column_present_but_empty_everywhere_leaves_a_held_level_alone(db, held):
    ProductService(db).bulk_import_products(
        [_row("HELD-1", **{"Reorder Level": ""})], USER_ID
    )

    db.refresh(held)
    assert held.reorder_level == 250


def test_the_two_columns_are_read_independently(db, held):
    """25 rows of the sample file carry one without the other."""
    ProductService(db).bulk_import_products(
        [_row("HELD-1", **{"Reorder Level": 400})], USER_ID
    )

    db.refresh(held)
    assert held.reorder_level == 400
    # No Reorder Qty column anywhere in this file, so the held quantity stands.
    assert held.reorder_quantity == 100


def test_a_non_numeric_level_skips_the_row_with_a_reason(db, uom):
    result = ProductService(db).bulk_import_products(
        [_row("P1", **{"Reorder Level": "abc"})], USER_ID
    )

    assert db.query(Product).filter(Product.product_code == "P1").first() is None
    assert any("must be a number" in e for e in result["errors"])


# --------------------------------------------------------------------------- #
# what the job says happened
# --------------------------------------------------------------------------- #

def test_the_result_counts_what_was_applied_and_what_was_cleared(db, held):
    result = ProductService(db).bulk_import_products(
        [_row("HELD-1", **{"Reorder Level": ""}), _row("P2", **{"Reorder Level": 5})], USER_ID
    )

    assert result["levels_applied"] == 1
    assert result["levels_cleared"] == 1


def test_a_cleared_level_gets_its_own_code_and_still_only_one_outcome_row(db, held):
    """Two entries for one row would push `processed_rows` past `total_rows`."""
    from app.services import import_outcome_codes as oc
    from app.services.import_outcome import ImportOutcome

    outcome = ImportOutcome(None, persist=False)
    rows = [_row("HELD-1", **{"Reorder Level": ""}), _row("P2", **{"Reorder Level": 5})]
    ProductService(db).bulk_import_products(rows, USER_ID, outcome=outcome)

    assert outcome.count_of(oc.REORDER_LEVEL_CLEARED) == 1
    assert outcome.processed == len(rows)


def test_clearing_a_level_that_was_never_set_is_not_reported_as_a_clear(db, uom):
    result = ProductService(db).bulk_import_products(
        [_row("P1", **{"Reorder Level": 5})], USER_ID
    )
    assert result["levels_cleared"] == 0

    result = ProductService(db).bulk_import_products(
        [_row("P1", **{"Reorder Level": ""}), _row("P2", **{"Reorder Level": 9})], USER_ID
    )
    # P1 held 5 and lost it: one clear. P2 is new and blank-free.
    assert result["levels_cleared"] == 1
