"""AGENT-PANEL-COMPOSER Phase 2 (red): the sheet reader behind the panel's attachments.

UAC: documentation/plans/chatbot/agent-panel-composer-8nov-acceptance-criteria.md, S1 to S6 and the
row-cap clause of S5. Pure functions of bytes: no database, no storage.

Contract assumed (tell the captain if one does not fit):
- `read_sheet(data, ext, sheet=None)` takes `ext` WITHOUT a leading dot ("xlsx", "csv", "xls").
- `SheetRead.name` is None for csv, the sheet's title otherwise.
- `SheetRead.rows` holds already-cleaned data rows (S3 applied), header excluded.
- `render_sheet_block` output may or may not end with a newline; the tests compare stripped text.
"""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import openpyxl
import pytest

from app.services.chatbot.agent import batch
from app.services.chatbot import panel_files
from app.services.chatbot.panel_files import ROW_CAP, list_sheets, read_sheet, render_sheet_block

XLS_FIXTURE = Path(__file__).resolve().parents[1] / "scm" / "fixtures" / "legacy_biff_sample.xls"


def xlsx(sheets: dict[str, list[list]]) -> bytes:
    """An in-memory workbook; the first key becomes the first sheet. An empty list is an empty sheet."""
    wb = openpyxl.Workbook()
    first = True
    for title, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = title
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def one(rows: list[list], title: str = "Dealers"):
    return read_sheet(xlsx({title: rows}), "xlsx")


# --------------------------------------------------------------------------- #
# S1: header row
# --------------------------------------------------------------------------- #


def test_s1_header_is_found_below_a_two_row_letterhead():
    got = one([
        ["Sorento Sdn Bhd"],
        [None],
        ["Phone", "Name", "Role"],
        ["60123456789", "Person A", "owner"],
        ["60123456780", "Person B", "staff"],
    ])

    assert got.header_found is True
    assert got.header == ["Phone", "Name", "Role"]
    assert got.rows == [["60123456789", "Person A", "owner"], ["60123456780", "Person B", "staff"]]
    assert got.total_rows == 2


def test_s1_a_number_is_not_text_so_it_does_not_make_a_header():
    # Row 1 has one text cell and a number: not a header. Row 2 has two text cells: the header.
    got = one([["Report", 2026], ["Phone", "Name"], ["601", "Ali"]])

    assert got.header == ["Phone", "Name"]
    assert got.rows == [["601", "Ali"]]


def test_s1_no_header_gives_numbered_columns_and_a_note():
    got = one([[60123456789, 1], [60123456780, 2]])

    assert got.header_found is False
    assert got.header == ["Column 1", "Column 2"]
    assert got.total_rows == 2
    assert got.rows == [["60123456789", "1"], ["60123456780", "2"]]
    block = render_sheet_block("nohdr.xlsx", got, is_csv=False)
    assert "no header row found" in block
    assert "| Column 1 | Column 2 |" in block


# --------------------------------------------------------------------------- #
# S2: blank rows and trailing columns
# --------------------------------------------------------------------------- #


def test_s2_blank_rows_are_dropped_and_not_counted():
    got = one([["Phone", "Name"], ["601", "Ali"], [None, None], ["", "  "], ["602", "Bob"]])

    assert got.rows == [["601", "Ali"], ["602", "Bob"]]
    assert got.total_rows == 2


def test_s2_trailing_empty_columns_are_trimmed():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Phone", "Name"])
    ws.append(["601", "Ali"])
    ws["F1"].value = None  # widens the used range with nothing in it
    ws.cell(row=2, column=8).value = None
    buf = io.BytesIO()
    wb.save(buf)

    got = read_sheet(buf.getvalue(), "xlsx")

    assert got.header == ["Phone", "Name"]
    assert got.rows == [["601", "Ali"]]


# --------------------------------------------------------------------------- #
# S3: cell rendering
# --------------------------------------------------------------------------- #


def test_s3_cells_render_the_way_the_spec_says():
    got = one([
        ["Phone", "Amount", "Day", "Moment", "Flag", "Off", "Name"],
        [60123456789.0, 3.25, dt.datetime(2026, 11, 8), dt.datetime(2026, 11, 8, 14, 30), True, False, "  Ali  "],
    ])

    assert got.rows[0] == ["60123456789", "3.25", "2026-11-08", "2026-11-08 14:30", "TRUE", "FALSE", "Ali"]


def test_s3_a_none_cell_is_empty_text():
    got = one([["Phone", "Name", "Role"], ["601", None, "owner"]])
    assert got.rows == [["601", "", "owner"]]


def test_s3_pipe_becomes_slash_and_newline_becomes_space():
    got = one([["Phone", "Note"], ["601", "a|b\nc"]])
    assert got.rows == [["601", "a/b c"]]


def test_s3_a_cell_is_cut_at_200_chars():
    got = one([["Phone", "Note"], ["601", "z" * 300]])
    assert got.rows[0][1] == "z" * 200


# --------------------------------------------------------------------------- #
# S4: csv encodings and delimiters, and xls
# --------------------------------------------------------------------------- #


def test_s4_csv_utf8_with_bom_has_the_bom_stripped():
    data = "Phone,Name\n601,Café\n".encode("utf-8-sig")
    got = read_sheet(data, "csv")

    assert got.header == ["Phone", "Name"], "the BOM stayed glued to the first header cell"
    assert got.rows == [["601", "Café"]]
    assert got.name is None


def test_s4_csv_falls_back_to_cp1252():
    data = "Phone,Name\n601,Café\n".encode("cp1252")  # b'\xe9' is not valid utf-8
    got = read_sheet(data, "csv")

    assert got.rows == [["601", "Café"]]


def test_s4_csv_semicolon_delimiter_is_sniffed():
    got = read_sheet(b"Phone;Name\n601;Ali\n602;Bob\n", "csv")

    assert got.header == ["Phone", "Name"]
    assert got.rows == [["601", "Ali"], ["602", "Bob"]]


def test_s4_csv_tab_delimiter_is_sniffed():
    got = read_sheet(b"Phone\tName\n601\tAli\n", "csv")

    assert got.header == ["Phone", "Name"]
    assert got.rows == [["601", "Ali"]]


def test_s4_csv_default_delimiter_is_comma():
    got = read_sheet(b"Phone,Name\n601,Ali\n", "csv")
    assert got.rows == [["601", "Ali"]]


def test_s4_xls_is_read_through_xlrd():
    # xlwt is not installed, so a committed BIFF fixture stands in (header Doc No, Item Code, Qty, Date).
    got = read_sheet(XLS_FIXTURE.read_bytes(), "xls")

    assert got.header_found is True
    assert got.header[:3] == ["Doc No", "Item Code", "Qty"]
    assert got.rows[0][0] == "202001-S0001"
    assert got.rows[0][2] == "450", "an integer-valued float must print as plain digits"


# --------------------------------------------------------------------------- #
# S5: the rendered block and the row cap
# --------------------------------------------------------------------------- #


def test_s5_row_cap_is_the_batch_cap_not_a_copy():
    assert ROW_CAP == batch.MAX_ROWS == 50
    assert panel_files.MAX_PDF_PAGES == 20


def test_s5_block_text_for_a_short_sheet_is_exact():
    rows = [["Phone", "Name", "Role"]] + [[f"6012345678{i}", f"Person {chr(65 + i)}", "owner"] for i in range(10)]
    rows.append(["60123456789", "Person K", "owner"])
    rows.append(["60123456780", "Person L", "owner"])
    got = one(rows)

    block = render_sheet_block("Dealer contacts Nov.xlsx", got, is_csv=False)

    lines = block.strip().split("\n")
    assert lines[0] == 'Attached file "Dealer contacts Nov.xlsx", sheet "Dealers": 12 rows.'
    assert lines[1] == "| Phone | Name | Role |"
    assert lines[2] == "| --- | --- | --- |"
    assert lines[3] == "| 60123456780 | Person A | owner |"
    assert lines[-1] == "| 60123456780 | Person L | owner |"
    assert len(lines) == 3 + 12


def test_s5_a_long_sheet_is_cut_and_says_so():
    rows = [["Phone", "Name"]] + [[f"601{i:04d}", f"Person {i}"] for i in range(212)]
    got = one(rows, title="Dealers")

    assert len(got.rows) == ROW_CAP
    assert got.total_rows == 212
    block = render_sheet_block("All dealers.xlsx", got, is_csv=False)
    lines = block.strip().split("\n")
    assert lines[0] == 'Attached file "All dealers.xlsx", sheet "Dealers": first 50 of 212 rows.'
    assert len(lines) == 3 + 50


def test_s5_a_csv_block_has_no_sheet_part():
    got = read_sheet(b"Phone,Name\n601,Ali\n", "csv")

    block = render_sheet_block("people.csv", got, is_csv=True)

    assert block.strip().split("\n")[0] == 'Attached file "people.csv": 1 rows.'
    assert "sheet" not in block.split("\n")[0]


# --------------------------------------------------------------------------- #
# S6: picking a sheet, and listing them
# --------------------------------------------------------------------------- #


def test_s6_a_named_sheet_is_read():
    data = xlsx({"First": [["A1", "B1"], ["x", "y"]], "Second": [["Phone", "Name"], ["601", "Ali"]]})

    got = read_sheet(data, "xlsx", "Second")

    assert got.name == "Second"
    assert got.rows == [["601", "Ali"]]


def test_s6_an_unknown_or_missing_sheet_falls_back_to_the_first_non_empty_sheet():
    data = xlsx({"Blank": [], "Real": [["Phone", "Name"], ["601", "Ali"]], "Other": [["P", "Q"], ["1", "2"]]})

    for pick in (None, "No such sheet"):
        got = read_sheet(data, "xlsx", pick)
        assert got.name == "Real"
        assert got.rows == [["601", "Ali"]]


def test_s6_list_sheets_skips_empty_sheets_and_counts_data_rows():
    data = xlsx({
        "Empty one": [],
        "Dealers": [["Phone", "Name"], ["601", "Ali"], ["602", "Bob"], [None, None]],
        "Empty two": [],
    })

    assert list_sheets(data, "xlsx") == [{"name": "Dealers", "rows": 2}]


def test_s6_list_sheets_keeps_workbook_order():
    data = xlsx({
        "Zed": [["Phone", "Name"], ["1", "a"]],
        "Alpha": [["Phone", "Name"], ["1", "a"], ["2", "b"]],
    })

    assert [s["name"] for s in list_sheets(data, "xlsx")] == ["Zed", "Alpha"]


def test_c5_a_formula_is_never_evaluated():
    # C5: values only. A formula cell without a cached value reads as empty, never evaluated.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Phone", "Name"])
    ws.append(["601", "=1+1"])
    buf = io.BytesIO()
    wb.save(buf)

    got = read_sheet(buf.getvalue(), "xlsx")

    assert got.rows[0][1] != "2", "a formula was evaluated"


# --------------------------------------------------------------------------- #
# R2 (review round 1): reading is bounded however large a sheet DECLARES itself
# --------------------------------------------------------------------------- #

import multiprocessing
import time
import zipfile


def _declare_huge(data: bytes, ref: str = "A1:XFD1048576") -> bytes:
    """The same workbook with every sheet's `<dimension>` rewritten to claim a full worksheet."""
    import re

    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            body = src.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet"):
                body = re.sub(rb'<dimension ref="[^"]*"\s*/>', f'<dimension ref="{ref}"/>'.encode(), body)
                assert ref.encode() in body, "the fixture did not declare the huge dimension"
            dst.writestr(item, body)
    return out.getvalue()


def _in_child(fn, data: bytes, queue) -> None:
    try:
        queue.put(("ok", fn(data)))
    except BaseException as exc:  # noqa: BLE001
        queue.put(("error", repr(exc)))


def _bounded(fn, data: bytes, seconds: float = 10.0):
    """`(finished, seconds taken, result)`; a run past `seconds` is killed so a regression cannot hang the suite."""
    ctx = multiprocessing.get_context("fork")
    queue = ctx.Queue()
    proc = ctx.Process(target=_in_child, args=(fn, data, queue))
    started = time.monotonic()
    proc.start()
    proc.join(seconds)
    taken = time.monotonic() - started
    if proc.is_alive():
        proc.kill()
        proc.join()
        return False, taken, None
    status, value = queue.get(timeout=2)
    assert status == "ok", value
    return True, taken, value


def _read_it(data: bytes):
    got = read_sheet(data, "xlsx")
    return got.rows, got.total_rows


def _list_it(data: bytes):
    return list_sheets(data, "xlsx")


def test_r2_read_sheet_ignores_a_declared_full_worksheet_dimension():
    small = xlsx({"Dealers": [["Phone", "Name"], ["601", "Ali"], ["602", "Bob"], ["603", "Cai"]]})
    bomb = _declare_huge(small)
    assert len(bomb) < 5_000

    finished, taken, value = _bounded(_read_it, bomb)

    assert finished, "read_sheet did not return within 10 s on a sheet that declares A1:XFD1048576"
    assert taken < 2.0, f"read_sheet took {taken:.1f}s"
    assert value == ([["601", "Ali"], ["602", "Bob"], ["603", "Cai"]], 3)


def test_r2_list_sheets_ignores_a_declared_full_worksheet_dimension():
    small = xlsx({"Dealers": [["Phone", "Name"], ["601", "Ali"], ["602", "Bob"], ["603", "Cai"]]})

    finished, taken, value = _bounded(_list_it, _declare_huge(small))

    assert finished, "list_sheets did not return within 10 s on a sheet that declares A1:XFD1048576"
    assert taken < 2.0, f"list_sheets took {taken:.1f}s"
    assert value == [{"name": "Dealers", "rows": 3}]


def test_r2_at_most_100_columns_are_read():
    wide = xlsx({"Wide": [[f"H{i}" for i in range(150)], [f"v{i}" for i in range(150)]]})

    got = read_sheet(wide, "xlsx")

    assert len(got.header) <= 100
    assert len(got.rows[0]) <= 100


def test_r2_at_most_20_sheets_are_scanned():
    many = xlsx({f"S{i:02d}": [["Phone", "Name"], ["601", f"P{i}"]] for i in range(25)})

    listed = list_sheets(many, "xlsx")

    assert len(listed) == 20
    assert [s["name"] for s in listed] == [f"S{i:02d}" for i in range(20)]


def test_r2_a_sheet_past_the_scan_limit_is_not_read_by_name_either():
    many = xlsx({f"S{i:02d}": [["Phone", "Name"], ["601", f"P{i}"]] for i in range(25)})

    got = read_sheet(many, "xlsx", "S24")

    # Not in the first 20, so S6 applies: unknown sheet -> the first non-empty one.
    assert got.name == "S00"


def test_r2_a_long_sheet_that_declares_a_full_width_is_not_padded_to_16384_columns():
    """The cost an attacker controls: every real row padded out to the declared width."""
    rows = [["Phone", "Name"]] + [[f"601{i}", f"P{i}"] for i in range(30_000)]
    bomb = _declare_huge(xlsx({"Dealers": rows}))

    finished, taken, value = _bounded(_read_it, bomb, seconds=30.0)

    assert finished
    assert value[1] == 30_000
    assert taken < 2.0, f"read_sheet took {taken:.1f}s on a sheet that declares {16384} columns"
