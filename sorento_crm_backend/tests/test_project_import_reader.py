"""Project import: the workbook reader (AC-PI-01..08).

RED tests, written before `app/services/project_import/reader.py` and `service.py` exist
(PLAN-project-import-12nov.md, "Backend contract"). The pure reader tests use in-memory
openpyxl books; the outcome tests (AC-PI-05/06) and the upload refusals (AC-PI-08) go
through the run service on Postgres (`blank_session`).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

import pytest

from tests.fixtures.project_import.build_so_summary import (
    EXPECTED,
    MONTHLY_SHEETS,
    SUMMARY_SHEET,
    build_workbook,
)

from ._project_import_support import (  # noqa: F401  fixtures
    FIELDS,
    HEADER_BY_FIELD,
    api_client,
    fold,
    make_book,
    memory_storage,
    new_run,
    row,
    world,
)

PS_RE = re.compile(r"^PS\d\d-\d{4}$")


def _reader():
    from app.services.project_import import reader

    return reader


def _read(content, sheets, columns=None):
    return _reader().read_rows(
        content, sheets=sheets, columns=dict(columns or HEADER_BY_FIELD)
    )


# --------------------------------------------------------------------------- fold


def test_fold_trims_collapses_and_uppercases_and_changes_nothing_else():
    reader = _reader()
    assert reader.fold("  customer   001 sdn\tbhd \n") == "CUSTOMER 001 SDN BHD"
    assert reader.fold(None) == ""
    # Punctuation is NOT stripped: a different spelling stays a different value.
    assert reader.fold("Customer 001 Sdn. Bhd.") == "CUSTOMER 001 SDN. BHD."


def test_to_date_is_promoted_and_the_private_name_stays_an_alias():
    from app.services.scm import outstanding_reader

    assert outstanding_reader.to_date is outstanding_reader._to_date
    assert outstanding_reader.to_date(datetime(2026, 4, 2, 0, 0)) == date(2026, 4, 2)


# --------------------------------------------------------------------------- AC-PI-01


def test_ac_pi_01_columns_are_found_by_heading_not_position():
    rows = [
        row("PS26-0001", customer="CUSTOMER 001 SDN BHD", po_number="PO-A", po_value=10),
        row("PS26-0002", customer="CUSTOMER 002 SDN BHD", po_number="PO-B", po_value=20),
    ]
    straight = make_book({"JAN'26": rows})
    shuffled = make_book({"JAN'26": rows}, field_order=list(reversed(FIELDS)))

    a = _read(straight, ["JAN'26"]).rows
    b = _read(shuffled, ["JAN'26"]).rows

    assert [r.ps_number for r in a] == ["PS26-0001", "PS26-0002"]
    key = lambda r: (r.ps_number, fold(r.customer), r.po_number, r.po_value)  # noqa: E731
    assert [key(r) for r in a] == [key(r) for r in b]
    assert fold(b[1].customer) == "CUSTOMER 002 SDN BHD"
    assert b[1].po_number == "PO-B"
    assert b[1].po_value == Decimal("20")


# --------------------------------------------------------------------------- AC-PI-02


@pytest.mark.parametrize("missing", ["ps_number", "customer", "po_number"])
def test_ac_pi_02_a_missing_required_heading_is_one_sheet_error_and_other_sheets_read(missing):
    from openpyxl import Workbook
    import io

    good = [row("PS26-0001")]
    bad = [row("PS26-0002")]
    # Two sheets, one of them without the required heading.
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows, drop in (("JAN'26", good, None), ("FEB'26", bad, missing)):
        ws = wb.create_sheet(name)
        fields = [f for f in FIELDS if f != drop]
        for col, f in enumerate(fields, start=1):
            ws.cell(row=1, column=col, value=HEADER_BY_FIELD[f])
        for r, values in enumerate(rows, start=2):
            for col, f in enumerate(fields, start=1):
                if values.get(f) is not None:
                    ws.cell(row=r, column=col, value=values[f])
    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    result = _read(content, ["JAN'26", "FEB'26"])

    assert [r.ps_number for r in result.rows] == ["PS26-0001"]
    assert len(result.sheet_errors) == 1
    err = result.sheet_errors[0]
    assert err["sheet"].strip() == "FEB'26"
    assert err["code"] == "missing_header"
    # Names the heading: either the field key or the file's own heading text.
    assert fold(err["heading"]) in {
        fold(missing),
        fold(HEADER_BY_FIELD[missing]),
        fold(missing.replace("_", " ")),
    }


# --------------------------------------------------------------------------- AC-PI-03


def test_ac_pi_03_sheet_names_match_after_trimming():
    content = make_book({"MAC'26 ": [row("PS26-0299", po_date=datetime(2026, 3, 2))]})

    result = _read(content, ["MAC'26"])  # ticked without the trailing space

    assert [r.ps_number for r in result.rows] == ["PS26-0299"]
    assert result.sheet_errors == []

    probe = _reader().probe(content)
    assert probe[0].name == "MAC'26 "
    assert probe[0].name_trimmed == "MAC'26"


def test_ac_pi_03_summary_sheet_has_no_ps_numbers_and_gives_no_rows():
    content = build_workbook()

    probe = {p.name: p for p in _reader().probe(content)}

    assert list(probe) == [
        "JAN'26", "FEB'26", "MAC'26 ", "APR'26", "MAY'26", "JUN'26 ", SUMMARY_SHEET,
        "JUL'26 ", "AUG'26",
    ]
    assert probe[SUMMARY_SHEET].has_ps_heading is False
    assert probe[SUMMARY_SHEET].row_count == 0
    for sheet in MONTHLY_SHEETS:
        assert probe[sheet.name].has_ps_heading is True

    result = _read(content, [SUMMARY_SHEET])
    assert result.rows == []


# --------------------------------------------------------------------------- AC-PI-04


def test_ac_pi_04_only_ps_numbered_rows_are_data_rows_on_the_full_fixture():
    content = build_workbook()
    result = _read(content, [s.name for s in MONTHLY_SHEETS])

    ps = [r.ps_number for r in result.rows]
    assert len(ps) == EXPECTED["ps_rows"] == 1398
    assert ps == [f"PS26-{n:04d}" for n in range(1, 1399)]
    assert all(PS_RE.match(p) for p in ps)
    assert result.sheet_errors == []

    probe = {p.name: p for p in _reader().probe(content)}
    for name, count in EXPECTED["rows_per_sheet"].items():
        assert probe[name].row_count == count, name


def test_ac_pi_04_total_rows_rollups_and_near_misses_are_not_rows():
    from openpyxl import Workbook
    import io

    wb = Workbook()
    ws = wb.active
    ws.title = "JAN'26"
    for col, f in enumerate(FIELDS, start=1):
        ws.cell(row=1, column=col, value=HEADER_BY_FIELD[f])
    ws.append(["PS26-0001", "ALVIN", "KATE", "CUSTOMER 001 SDN BHD", "PROJECT 001 SAMPLE NAME",
               None, "PO-1", 100, datetime(2026, 1, 3)])
    ws.append([" PS26-0002 ", "ALVIN", "KATE", "CUSTOMER 001 SDN BHD", None, None, "PO-2", 100,
               datetime(2026, 1, 3)])
    ws.append([None, None, None, None, None, None, None, "=SUM(H2:H3)"])
    ws.append([])
    ws.append([None, "SALES ORDER SUMMARY JANUARY 2026"])
    ws.append([None, "SALESPERSON", "TOTAL PO", "TOTAL AMOUNT"])
    ws.append([None, "ALVIN", 2, 200])
    ws.append([None, "Total", "=SUM(C7:C7)", "=SUM(D7:D7)"])
    ws.append(["PS26-12", "ALVIN", "KATE", "CUSTOMER 001 SDN BHD", None, None, "PO-3", 1])
    ws.append(["PS2026-0001", "ALVIN", "KATE", "CUSTOMER 001 SDN BHD", None, None, "PO-4", 1])
    ws.append(["Total", None, None, None, None, None, None, 999])
    buf = io.BytesIO()
    wb.save(buf)

    result = _read(buf.getvalue(), ["JAN'26"])

    assert [r.ps_number for r in result.rows] == ["PS26-0001", "PS26-0002"]


# --------------------------------------------------------------------------- AC-PI-05 / 06


def test_ac_pi_05_and_06_placeholder_and_other_year_rows_are_skipped(world):
    from app.services.project_import import service

    content = make_book({
        "AUG'26": [
            row("PS26-1205", po_date=datetime(2026, 8, 3)),
            {"ps_number": "PS26-1206"},  # pre-numbered placeholder: PS number only
            row("PS25-0042", po_date=datetime(2026, 8, 3)),
        ]
    })
    run = new_run(world, content)

    report = service.preview(world.db, run, user_id=world.admin_id)

    by_ps = {r["ps_number"]: r for r in report["rows"]}
    assert by_ps["PS26-1206"]["outcome"] == "skipped"
    assert by_ps["PS26-1206"]["codes"] == ["placeholder"]
    assert by_ps["PS25-0042"]["outcome"] == "skipped"
    assert by_ps["PS25-0042"]["codes"] == ["other_year"]
    assert by_ps["PS26-1205"]["outcome"] != "skipped"
    assert report["codes"].get("placeholder") == 1
    assert report["codes"].get("other_year") == 1


# --------------------------------------------------------------------------- AC-PI-07


def test_ac_pi_07_cell_quirks_read_correctly():
    content = make_book({
        "JAN'26": [
            row(
                "PS26-0001",
                salesperson="ALVIN ",
                customer=" CUSTOMER 001 SDN BHD ",
                po_number=12119,
                po_value="-",
                po_date=datetime(2026, 1, 5),
                amended_date="amend 9/4/2026",
                schedule="O/C",
                delivery="IMMEDIATE",
                outstanding="on hold 23/4/2026",
                so_number="SO466355,SO466352, SO466351",
            ),
            row(
                "PS26-0002",
                po_number="HQ/75/30/303",
                po_value=49.68,
                amended_date=datetime(2026, 4, 9),
                delivery=datetime(2026, 1, 6),
                so_number="refer PS26-0022",
            ),
            row("PS26-0003", amended_date=" ", delivery="   ", so_number=None, po_value=25487),
        ]
    })

    rows = {r.ps_number: r for r in _read(content, ["JAN'26"]).rows}
    one, two, three = rows["PS26-0001"], rows["PS26-0002"], rows["PS26-0003"]

    # Integer PO number: its digits as text, flagged.
    assert one.po_number == "12119"
    assert one.po_number_numeric is True
    assert two.po_number == "HQ/75/30/303"
    assert two.po_number_numeric is False
    # `-` in TOTAL VALUE gives no amount.
    assert one.po_value is None
    assert one.value_dash is True
    assert two.po_value == Decimal("49.68")
    assert two.value_dash is False
    assert three.po_value == Decimal("25487")
    # Real dates are dates; text dates are kept as typed.
    assert one.po_date == date(2026, 1, 5)
    assert one.amended == "amend 9/4/2026"
    assert two.amended == date(2026, 4, 9)
    assert one.delivery == "IMMEDIATE"
    assert two.delivery == date(2026, 1, 6)
    assert one.schedule == "O/C"
    assert one.outstanding == "on hold 23/4/2026"
    # A comma SO list (`,` or `, `) gives each SO; the raw cell is kept.
    assert one.so_numbers == ["SO466355", "SO466352", "SO466351"]
    assert one.so_cell == "SO466355,SO466352, SO466351"
    assert two.so_numbers == []
    assert two.so_cell == "refer PS26-0022"
    # Junk whitespace cells are ignored.
    assert three.amended is None
    assert three.delivery is None
    assert fold(one.customer) == "CUSTOMER 001 SDN BHD"
    assert one.salesperson.strip() == "ALVIN"
    assert one.sheet.strip() == "JAN'26"
    assert one.row_number == 2


def test_ac_pi_07_headers_with_line_breaks_and_the_q8_junk_column_are_handled():
    content = build_workbook()

    jan = next(p for p in _reader().probe(content) if p.name == "JAN'26")

    headers = [c["header"] for c in jan.columns]
    # Every heading as written (line breaks and padding kept), and nothing for the blank Q
    # column whose only cell is ~300 spaces in Q8.
    assert headers == [HEADER_BY_FIELD[f] for f in FIELDS]
    assert [c["position"] for c in jan.columns] == sorted(c["position"] for c in jan.columns)
    first = jan.columns[0]
    assert PS_RE.match(str(first["sample"]).strip())


# --------------------------------------------------------------------------- AC-PI-08


def _no_ps_book() -> bytes:
    return make_book({}, extra_sheets={SUMMARY_SHEET: [
        [None, "WITH SCHEDULE"], [None, "SALESPERSON", "TOTAL PO", "TOTAL AMOUNT"],
        [None, "ALVIN WONG", 3, 300],
    ]})


@pytest.mark.parametrize(
    "case",
    ["not_xlsx", "too_big", "unreadable", "no_ps_heading"],
)
def test_ac_pi_08_invalid_uploads_are_refused_with_422(world, case):
    from app.services.error_handler import AppException
    from app.services.project_import import service

    if case == "not_xlsx":
        filename, content = "notes.txt", b"just some text, not a workbook"
    elif case == "too_big":
        filename, content = "big.xlsx", build_workbook() + b"\0" * (10 * 1024 * 1024 + 1)
    elif case == "unreadable":
        filename, content = "broken.xlsx", b"PK\x03\x04" + b"garbage" * 200
    else:
        filename, content = "summary-only.xlsx", _no_ps_book()

    with pytest.raises(AppException) as excinfo:
        service.create_run(
            world.db, company_id=world.company_id, user_id=world.admin_id,
            filename=filename, content=content,
        )

    assert excinfo.value.status_code == 422
    message = str(getattr(excinfo.value, "message", "") or excinfo.value)
    assert message.strip()
    assert "Traceback" not in message
