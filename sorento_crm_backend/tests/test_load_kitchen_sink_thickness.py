"""`scripts/load_kitchen_sink_thickness.py` - parser units plus one DB round trip.

Fixture shape follows `tests/test_product_spec_authored_write.py` (`db` fixture via
`blank_session`, `_fixtures`, `_product`) - tests run on Postgres only, never sqlite
(`tests/_pg_fixture.py`).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_registry import seed_spec_registry
from scripts.load_kitchen_sink_thickness import (
    RowResult,
    SteelGradeParseError,
    ThicknessParseError,
    _assert_reachable,
    dedupe_rows,
    finish_labels_by_row,
    normalise_sheet_code,
    parse_steel_grade,
    parse_thickness_text,
    run,
    slug_finish,
)
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        _fixtures(s)
        yield s


def _fixtures(db):
    """A Kitchen Sink category (class derives from the `-KS` code suffix, per
    `product_class_signal.CLASS_SUFFIXES`), brand and UOM - mirrors
    `test_product_spec_authored_write.py::_fixtures`."""
    cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-KS", category_name="ZZT-KS")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-KST-PCS", uom_name="Piece")
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-KST-SRT", brand_name="Sorento")
    db.add_all([cat, uom, brand])
    db.flush()
    backfill_category_signals(db)
    _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})


def _product(db, code: str) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description="SORENTO KITCHEN SINK",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------- #
# thickness text (all forms measured in the real workbook)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,expected",
    [
        ("面板3mm, 盆胆 0.8mm", {"board_thickness": 3.0, "thickness": 0.8}),
        ("面板3.0mm, 盆胆 0.7mm", {"board_thickness": 3.0, "thickness": 0.7}),
        ("面板2.5mm, 盆胆 0.7mm", {"board_thickness": 2.5, "thickness": 0.7}),
        ("面板:2.7盆胆:0.7", {"board_thickness": 2.7, "thickness": 0.7}),
        ("面板 3.0 + 盆胆 0.7", {"board_thickness": 3.0, "thickness": 0.7}),
        ("厚度 0.5", {"thickness": 0.5}),
        ("0.9mm", {"thickness": 0.9}),
        ("0.9mm ", {"thickness": 0.9}),
        ("1.15mm", {"thickness": 1.15}),
        ("2.5mm", {"thickness": 2.5}),
        ("0.9", {"thickness": 0.9}),
    ],
)
def test_parse_thickness_text_forms(text, expected):
    assert parse_thickness_text(text) == expected


def test_parse_thickness_text_rejects_unrecognised_text():
    with pytest.raises(ThicknessParseError):
        parse_thickness_text("thick and sturdy")


def test_parse_thickness_text_rejects_blank():
    with pytest.raises(ThicknessParseError):
        parse_thickness_text("")


def test_parse_thickness_text_rejects_an_implausible_bare_number():
    """A bare number with no 面板/盆胆/厚度 marker above 20mm is almost certainly a
    stray code fragment (e.g. "2427"), not a thickness."""
    with pytest.raises(ThicknessParseError):
        parse_thickness_text("2427")


# --------------------------------------------------------------------------- #
# steel grade
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,expected",
    [
        ("SUS201", "201"),
        ("SUS304", "304"),
        ("Stainless Steel 201 ", "201"),
    ],
)
def test_parse_steel_grade_forms(text, expected):
    assert parse_steel_grade(text) == expected


def test_parse_steel_grade_rejects_unrecognised_text():
    with pytest.raises(SteelGradeParseError):
        parse_steel_grade("aluminium")


# --------------------------------------------------------------------------- #
# finish slug + fill-colour grouping
# --------------------------------------------------------------------------- #
def test_slug_finish_collapses_whitespace_and_newlines():
    assert slug_finish("NANO GRAIN\n") == "nano_grain"
    assert slug_finish("NANO   VOLCANO") == "nano_volcano"


def test_finish_groups_by_contiguous_fill_colour():
    """Mirrors the real Iborn FFD0E0E3 group: two codes share one fill, "NANO" sits
    on one row and "VOLCANO" on another, and BOTH codes take the joined finish. A
    third code under a different fill gets its own (single-label) finish, and a
    fourth with no colour and no label gets none."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Model Code ", "Thickness ", "Material", "Finish"])
    ws.append(["IBKS1", "SUS201", "面板 2.5 + 盆胆 0.55", "NANO"])
    ws.append(["IBKS2", "SUS201", "面板 2.5 + 盆胆 0.55", "VOLCANO"])
    ws.append(["IBKS3", "SUS201", "面板 2.5 + 盆胆 0.55", "ANDRIA SERIES"])
    ws.append(["IBKS4", "SUS201", "面板 2.5 + 盆胆 0.55", None])

    volcano_fill = PatternFill(fill_type="solid", fgColor="FFD0E0E3")
    ws["D2"].fill = volcano_fill
    ws["D3"].fill = volcano_fill
    ws["D4"].fill = PatternFill(fill_type="solid", fgColor="FFFFF2CC")
    # D5 keeps openpyxl's default (no fill) - its own group, no label.

    result = finish_labels_by_row(ws, col=4, rows=[2, 3, 4, 5])
    assert result[2] == "nano_volcano"
    assert result[3] == "nano_volcano"
    assert result[4] == "andria_series"
    assert result[5] is None


# --------------------------------------------------------------------------- #
# codes
# --------------------------------------------------------------------------- #
def test_normalise_sheet_code_strips_parenthetical_and_upcases():
    assert normalise_sheet_code(" srtks1025-bl (new) ") == "SRTKS1025-BL"


# --------------------------------------------------------------------------- #
# _assert_reachable - the inline stand-in for the route's _validate_reachable
# --------------------------------------------------------------------------- #
def test_assert_reachable_refuses_a_value_with_no_synonym():
    with pytest.raises(SystemExit):
        _assert_reachable("enum", ["a", "b"], {"a": ["a word"]})


def test_assert_reachable_accepts_a_fully_covered_enum():
    _assert_reachable("enum", ["a", "b"], {"a": ["a word"], "b": ["b word"]})


def test_assert_reachable_ignores_non_enum_types():
    _assert_reachable("numeric", [], {})


# --------------------------------------------------------------------------- #
# dedupe_rows - same rule whether the duplicate is on one sheet or two
# --------------------------------------------------------------------------- #
def test_dedupe_rows_writes_an_identical_duplicate_once():
    rows = [
        RowResult(sheet="Sorento", row=2, code="SRTKS1", entries={"thickness": 0.8}),
        RowResult(sheet="Cabana", row=5, code="SRTKS1", entries={"thickness": 0.8}),
    ]
    to_write, origin, conflicts = dedupe_rows(rows)
    assert to_write == {"SRTKS1": {"thickness": 0.8}}
    assert origin == {"SRTKS1": ("Sorento", 2)}
    assert conflicts == []


def test_dedupe_rows_skips_and_reports_a_conflicting_duplicate():
    rows = [
        RowResult(sheet="Sorento", row=2, code="SRTKS1", entries={"thickness": 0.8}),
        RowResult(sheet="Cabana", row=5, code="SRTKS1", entries={"thickness": 0.9}),
    ]
    to_write, origin, conflicts = dedupe_rows(rows)
    assert to_write == {}
    assert origin == {}
    assert conflicts == [("SRTKS1", [("Sorento", 2), ("Cabana", 5)])]


def test_dedupe_rows_ignores_blank_and_parse_failure_rows():
    rows = [
        RowResult(sheet="Sorento", row=2, code="SRTKS1", blank=True),
        RowResult(sheet="Sorento", row=3, code="SRTKS2", parse_failure="bad"),
    ]
    to_write, origin, conflicts = dedupe_rows(rows)
    assert to_write == {}
    assert origin == {}
    assert conflicts == []


# --------------------------------------------------------------------------- #
# DB round trip - the loader's apply path, against a real Postgres schema
# --------------------------------------------------------------------------- #
def _spec_for(db, code: str) -> ProductSpecifications:
    return (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == code)
        .one()
    )


def test_apply_writes_board_thickness_thickness_steel_material_and_finish(db, tmp_path):
    _product(db, "SRTKS0001")
    seed_spec_registry(db)

    xlsx_path = tmp_path / "kitchen_sink_thickness.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Iborn"
    ws.append(["Model Code ", "Thickness ", "Material", "Finish"])
    ws.append(["SRTKS0001", "SUS201", "面板3mm, 盆胆 0.8mm", "NANO GRAIN"])
    wb.save(str(xlsx_path))

    report = run(db, str(xlsx_path), apply=True)

    assert report["mode"] == "APPLIED"
    sheet_report = next(s for s in report["sheets"] if s.sheet == "Iborn")
    assert sheet_report.written == 1
    assert sheet_report.unmatched == []
    assert sheet_report.parse_failures == []
    assert sheet_report.conflicts == []

    spec = _spec_for(db, "SRTKS0001")
    values = spec.values
    assert values["board_thickness"]["value"] == 3.0
    assert values["thickness"]["value"] == 0.8
    assert values["steel_grade"]["value"] == "201"
    assert values["material"]["value"] == "stainless_steel"
    assert values["surface_texture"]["value"] == "nano_grain"

    for key in ("board_thickness", "thickness", "steel_grade", "material", "surface_texture"):
        assert spec.provenance[key]["source"] == "human"

    board_row = db.query(ProductSpecRegistry).filter_by(spec_key="board_thickness").one()
    assert board_row.source == "user"
    texture_row = db.query(ProductSpecRegistry).filter_by(spec_key="surface_texture").one()
    assert texture_row.source == "user"


def test_dry_run_writes_nothing(db, tmp_path):
    _product(db, "SRTKS0002")
    seed_spec_registry(db)

    xlsx_path = tmp_path / "kitchen_sink_thickness_dry.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Iborn"
    ws.append(["Model Code ", "Thickness ", "Material", "Finish"])
    ws.append(["SRTKS0002", "SUS201", "面板3mm, 盆胆 0.8mm", "NANO GRAIN"])
    wb.save(str(xlsx_path))

    report = run(db, str(xlsx_path), apply=False)

    assert report["mode"] == "DRY-RUN (rolled back)"
    sheet_report = next(s for s in report["sheets"] if s.sheet == "Iborn")
    assert sheet_report.written == 1

    assert db.query(ProductSpecRegistry).filter_by(spec_key="board_thickness").first() is None
    assert (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "SRTKS0002")
        .first()
        is None
    )


def test_apply_reports_unmatched_code_with_near_variants_and_writes_nothing_for_it(db, tmp_path):
    """A code with no exact catalog match is reported unmatched, with the close
    catalog matches that DO exist (`product_code LIKE '<code>%'`) printed beside
    it, and nothing is written for it - the matched code on the same sheet still
    writes normally."""
    _product(db, "SRTKS0003")
    seed_spec_registry(db)

    xlsx_path = tmp_path / "kitchen_sink_thickness_unmatched.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Iborn"
    ws.append(["Model Code ", "Thickness ", "Material", "Finish"])
    ws.append(["SRTKS0003", "SUS201", "面板3mm, 盆胆 0.8mm", "NANO GRAIN"])
    # A truncated code: no exact catalog match, but SRTKS0003 starts with it.
    ws.append(["SRTKS000", "SUS201", "0.9mm", None])
    wb.save(str(xlsx_path))

    report = run(db, str(xlsx_path), apply=True)

    sheet_report = next(s for s in report["sheets"] if s.sheet == "Iborn")
    assert sheet_report.written == 1
    assert sheet_report.unmatched == ["SRTKS000"]
    assert "SRTKS0003" in sheet_report.unmatched_near["SRTKS000"]

    assert (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == "SRTKS000")
        .first()
        is None
    )
    matched_spec = _spec_for(db, "SRTKS0003")
    assert matched_spec.values["thickness"]["value"] == 0.8
