"""S7a - parsing a supplier's stock list, against the headers the supplier actually writes.

The header spellings here are the ones migration 311 seeded from the July samples (型号,
包装好库存, 空瓷, 体积(cbm), 总体积(cbm)), so a change that breaks the real file breaks this
file too. No database: the resolver is built by hand from the same alias pairs, which keeps
the parsing provable against bytes alone.
"""
from __future__ import annotations

from io import BytesIO

import pytest

from app.services.import_alias_service import AliasResolver, normalize_header
from app.services.scm.supplier_inventory_reader import read_workbook

#: The alias rows migration 311 seeds for this document type, as (field, alias).
_ALIASES = [
    ("item_code", "型号"),
    ("item_code", "MODEL"),
    ("brand", "商标"),
    ("spec", "规格"),
    ("product_name", "品名"),
    ("qty_packed", "包装好库存"),
    ("qty_unfinished", "空瓷"),
    ("cbm_per_unit", "体积(cbm)"),
    ("cbm_total", "总体积(cbm)"),
    ("remark", "备注"),
]


def resolver() -> AliasResolver:
    mapping: dict[str, str] = {}
    for field, alias in _ALIASES:
        mapping.setdefault(normalize_header(alias), field)
        mapping.setdefault(normalize_header(field), field)
    return AliasResolver("supplier_inventory", mapping)


def workbook(rows: list[list]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADER = ["型号", "品名", "商标", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def test_packed_and_unfinished_stay_separate():
    # AC-E1/E2. Summing them would put a container of unmade goods on a loading plan.
    data = workbook([HEADER, ["SRTWC8613", "座厕", "SORENTO", 120, 340, 0.21, ""]])

    out = read_workbook(data, resolver())

    assert out.ok
    assert len(out.rows) == 1
    row = out.rows[0]
    assert row.item_code == "SRTWC8613"
    assert row.qty_packed == 120
    assert row.qty_unfinished == 340
    assert row.cbm_per_unit == 0.21


def test_a_title_row_above_the_header_is_not_the_header():
    # The supplier's sheet opens with a title line and sometimes a blank one. Reading row 1
    # as the header would find no columns and report the file as unreadable.
    data = workbook(
        [
            ["2026年7月库存表", None, None, None, None, None, None],
            [None, None, None, None, None, None, None],
            HEADER,
            ["SRTWC8613", "座厕", "SORENTO", 5, 0, 0.21, ""],
        ]
    )

    out = read_workbook(data, resolver())

    assert out.ok
    assert [r.item_code for r in out.rows] == ["SRTWC8613"]


def test_per_unit_volume_is_derived_from_a_line_total_when_the_column_is_blank():
    # Both columns exist in the real file and only one is reliably filled.
    data = workbook(
        [
            ["型号", "包装好库存", "空瓷", "总体积(cbm)"],
            ["SRTWB1001", 10, 0, 2.5],
        ]
    )

    out = read_workbook(data, resolver())

    assert out.rows[0].cbm_per_unit == 0.25


def test_a_row_with_no_volume_at_all_stays_unmeasured_not_zero():
    # Zero would read as "takes no space" and load ahead of everything real.
    data = workbook([["型号", "包装好库存", "空瓷"], ["SRTWB1001", 10, 0]])

    out = read_workbook(data, resolver())

    assert out.rows[0].cbm_per_unit is None


def test_a_file_with_no_packed_column_is_refused_with_the_column_named():
    data = workbook([["型号", "空瓷"], ["SRTWB1001", 4]])

    out = read_workbook(data, resolver())

    assert not out.ok
    assert out.missing_columns == ["qty_packed"]


def test_an_unmapped_column_is_reported_rather_than_dropped():
    # An unmapped header is the first sign the supplier changed their export.
    data = workbook([HEADER + ["新栏位"], ["SRTWC8613", "座厕", "S", 1, 0, 0.2, "", "x"]])

    out = read_workbook(data, resolver())

    assert "新栏位" in out.unmapped_headers


def test_a_blank_model_number_on_a_row_carrying_stock_is_complained_about():
    # A spacing row is silence; a quantity with no model is a line somebody meant to declare.
    data = workbook([HEADER, [None, None, None, 30, 0, None, None], [None] * 7])

    out = read_workbook(data, resolver())

    assert out.rows == []
    assert len(out.problems) == 1
    assert "no model number" in out.problems[0].reason


def test_quantities_survive_thousands_separators():
    data = workbook([HEADER, ["SRTWC8613", "座厕", "S", "1,240", "2,000", "0.21", ""]])

    out = read_workbook(data, resolver())

    assert out.rows[0].qty_packed == 1240
    assert out.rows[0].qty_unfinished == 2000


def test_an_english_export_reads_through_the_same_aliases():
    # The alias table carries MODEL alongside 型号, so a supplier who exports in English is
    # configuration, not a second reader.
    data = workbook([["MODEL", "qty_packed", "qty_unfinished", "cbm_per_unit"],
                     ["SRTWC8613", 7, 1, 0.21]])

    out = read_workbook(data, resolver())

    assert out.ok
    assert out.rows[0].qty_packed == 7


def test_a_workbook_that_is_not_one_is_reported_not_raised():
    out = read_workbook(b"this is not a spreadsheet", resolver())

    assert not out.ok
    assert out.problems and "could not read" in out.problems[0].reason


def test_read_workbook_needs_a_resolver_or_a_session():
    with pytest.raises(ValueError):
        read_workbook(b"", None)
