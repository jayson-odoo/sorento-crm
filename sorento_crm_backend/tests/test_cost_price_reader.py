"""RED tests for the supplier price-list reader (#1288, Lane A, AC-S1-01 to AC-S1-05).

TEST-FIRST: `app/services/procurement/supplier_price_list_reader.py` does not exist yet, so
every test here is expected to fail with `ModuleNotFoundError` until the coder writes it -
imported INSIDE each test body (never at module scope) so a missing module fails only the
one test that needs it, not the whole file at collection.

Pure-function tests: no database, no HTTP. `read_supplier_price_list`, `clean_code` and
`clean_price` are the seams the captain's test list pins
(`documentation/plans/purchasing/cost-price-lane-a-test-list.md`).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests.fixtures.cost_price.taiyang_shapes import (
    CB2500_CODE_RAW,
    CB2500_SHEET,
    MERGED_CONFIG_SHEET,
    MERGED_CONFIG_TEXT,
    SHEET_ROW_COUNTS,
    header_at_row,
    merged_price_workbook,
    price_cell_workbook,
    sheet_with_no_header,
    simple_price_list_workbook,
    taiyang_workbook,
)


# --------------------------------------------------------------------------------- AC-S1-01


def test_fixture_parses_every_sheet_with_its_row_counts():
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    result = read_supplier_price_list(taiyang_workbook(), "taiyang.xlsx")

    sheets_by_name = {sheet.name: sheet for sheet in result.sheets}
    assert set(sheets_by_name) == set(SHEET_ROW_COUNTS), sheets_by_name.keys()
    for name, expected_count in SHEET_ROW_COUNTS.items():
        sheet = sheets_by_name[name]
        assert sheet.skipped_reason is None, (name, sheet.skipped_reason)
        assert len(sheet.rows) == expected_count, (name, len(sheet.rows), expected_count)
        for row in sheet.rows:
            assert row.sheet == name
            assert row.row_no >= 7  # first body row, after 5 letterhead rows + the header
            assert row.supplier_code
            assert row.configuration
            assert row.price is not None
            assert row.line_no not in (None, "")


# --------------------------------------------------------------------------------- AC-S1-02


def test_header_found_at_row_4_and_row_9():
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    for row_number in (4, 9):
        result = read_supplier_price_list(header_at_row(row_number), f"hdr{row_number}.xlsx")
        sheet = result.sheets[0]
        assert sheet.header_row == row_number, sheet.header_row
        assert sheet.skipped_reason is None
        assert len(sheet.rows) == 3


def test_sheet_without_header_is_skipped_by_name():
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    result = read_supplier_price_list(
        sheet_with_no_header(sheet_name="mystery sheet"), "no_header.xlsx"
    )
    sheet = result.sheets[0]
    assert sheet.name == "mystery sheet"
    assert sheet.skipped_reason == "no_header"
    assert sheet.rows == []


# --------------------------------------------------------------------------------- AC-S1-03


def test_merged_configuration_fills_down_with_flag():
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    result = read_supplier_price_list(taiyang_workbook(), "taiyang.xlsx")
    sheet = next(s for s in result.sheets if s.name == MERGED_CONFIG_SHEET)
    by_row = {r.row_no: r for r in sheet.rows}

    anchor = by_row[7]
    assert anchor.configuration == MERGED_CONFIG_TEXT
    assert "configuration_from_merge" not in anchor.flags

    for row_no in (8, 9):
        follower = by_row[row_no]
        assert follower.configuration == MERGED_CONFIG_TEXT, row_no
        assert "configuration_from_merge" in follower.flags, row_no
        # item_code (型号) is never filled down, even where 产品配置 is merged.
        assert follower.supplier_code != anchor.supplier_code


def test_merged_price_fills_down_with_flag():
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    result = read_supplier_price_list(merged_price_workbook(), "mp.xlsx")
    sheet = result.sheets[0]
    by_row = {r.row_no: r for r in sheet.rows}

    anchor = by_row[7]
    follower = by_row[8]
    assert anchor.price == Decimal("250")
    assert follower.price == Decimal("250")
    assert "price_from_merge" not in anchor.flags
    assert "price_from_merge" in follower.flags
    assert follower.supplier_code != anchor.supplier_code  # item_code never filled down


# --------------------------------------------------------------------------------- AC-S1-04


def test_code_cleaning_folds_nfkc_trims_and_splits_the_note():
    from app.services.procurement.supplier_price_list_reader import clean_code

    assert clean_code("CB2500SS-BL（彩盒）") == ("CB2500SS-BL", "彩盒")
    assert clean_code(" SRTWT1900-BL-DIY ") == ("SRTWT1900-BL-DIY", None)


def test_reader_keeps_the_verbatim_cell_alongside_the_cleaned_code():
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    result = read_supplier_price_list(taiyang_workbook(), "taiyang.xlsx")
    sheet = next(s for s in result.sheets if s.name == CB2500_SHEET)
    row = next(r for r in sheet.rows if r.supplier_code == "CB2500SS-BL")

    assert row.supplier_code_raw.strip() == CB2500_CODE_RAW
    assert row.code_note == "彩盒"


# --------------------------------------------------------------------------------- AC-S1-05


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("¥512", Decimal("512")),
        ("512.00元", Decimal("512.00")),
        ("512", Decimal("512")),
        (512, Decimal("512")),
        ("RMB 1,512", Decimal("1512")),
        ("面议", None),  # 面议 ("negotiable"), not a number
        (None, None),
        (-5, None),
        (-5.0, None),
    ],
)
def test_price_cleaning(raw, expected):
    from app.services.procurement.supplier_price_list_reader import clean_price

    assert clean_price(raw) == expected


def test_reader_marks_every_unclean_price_cell_as_none():
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    data = price_cell_workbook(
        ["¥512", "512.00元", "512", 512, "RMB 1,512", "面议", None, -5]
    )
    result = read_supplier_price_list(data, "prices.xlsx")
    prices = [row.price for row in result.sheets[0].rows]

    assert prices == [
        Decimal("512"), Decimal("512.00"), Decimal("512"), Decimal("512"),
        Decimal("1512"), None, None, None,
    ]


# --------------------------------------------------------------------------------- AC-S1-15
# (the reader's own caps - AC-S1-15 also covers the route-level refusal, tested in
# test_cost_price_upload_routes.py)


def test_reader_refuses_a_non_excel_file_type():
    from app.services.error_handler import AppException
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    with pytest.raises(AppException) as exc:
        read_supplier_price_list(b"not an excel file at all", "list.csv")
    assert exc.value.status_code == 422
    assert exc.value.code == "file_type"


def test_reader_refuses_xlsm():
    from app.services.error_handler import AppException
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    with pytest.raises(AppException) as exc:
        read_supplier_price_list(taiyang_workbook(), "list.xlsm")
    assert exc.value.status_code == 422
    assert exc.value.code == "file_type"


def test_reader_refuses_a_file_over_25mb():
    from app.services.error_handler import AppException
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    oversized = b"0" * (25 * 1024 * 1024 + 1)
    with pytest.raises(AppException) as exc:
        read_supplier_price_list(oversized, "big.xlsx")
    assert exc.value.status_code == 422
    assert exc.value.code == "file_too_large"


def test_reader_refuses_more_than_5000_rows():
    from app.services.error_handler import AppException
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    rows = [(f"ZZCPC-BIG-{i:05d}", "configuration", 100) for i in range(5001)]
    data = simple_price_list_workbook(rows)
    with pytest.raises(AppException) as exc:
        read_supplier_price_list(data, "too_many.xlsx")
    assert exc.value.status_code == 422
    assert exc.value.code == "too_many_rows"
