"""Project import: the masked owner's workbook (AC-PI-50).

Two halves:

* the builder's own shape, against `project-import-file-shape.md` (these pass today: they
  prove the fixture before anything is built on it);
* the full preview on that workbook, asserting the exact counts per outcome and code from
  `EXPECTED` (RED until `app/services/project_import/service.py` exists).

`EXPECTED` is derived from the builder's row specs (`compute_expected`), never typed by
hand; the classification it encodes is documented on `unmapped_outcome()`.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import openpyxl
import pytest

from tests.fixtures.project_import import build_so_summary as fx
from tests.fixtures.project_import.build_so_summary import (
    EXPECTED,
    HEADERS,
    MONTHLY_SHEETS,
    SHEET_ORDER,
    SUMMARY_MERGES,
    SUMMARY_SHEET,
    build_workbook,
)

from ._project_import_support import (  # noqa: F401  fixtures
    memory_storage,
    new_run,
    snapshot,
    world,
)

_REPO = Path(__file__).resolve().parents[2]
_SHAPE_DOC = "project-import-file-shape.md"


def _shape_doc() -> str:
    for base in ("documentation/plans/project-sales", "documentation/plans/_archive/project-sales"):
        path = _REPO / base / _SHAPE_DOC
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise AssertionError(f"{_SHAPE_DOC} not found under documentation/plans")


@pytest.fixture(scope="module")
def book():
    return openpyxl.load_workbook(io.BytesIO(build_workbook()))


# --------------------------------------------------------------------------- builder shape


def test_ac_pi_50_build_is_deterministic(tmp_path):
    first = build_workbook()
    fx._build_bytes.cache_clear()
    target = tmp_path / "so_summary.xlsx"
    second = build_workbook(target)
    assert first == second
    assert target.read_bytes() == first


def test_ac_pi_50_nine_sheets_in_order_with_trailing_space_names(book):
    assert book.sheetnames == SHEET_ORDER == [
        "JAN'26", "FEB'26", "MAC'26 ", "APR'26", "MAY'26", "JUN'26 ", "SUMMARY JAN-JUN",
        "JUL'26 ", "AUG'26",
    ]
    assert all(ws.sheet_state == "visible" for ws in book.worksheets)


def test_ac_pi_50_headers_are_verbatim_from_the_shape_doc(book):
    doc = _shape_doc().split("### Columns A..O")[1].split("## 3.")[0]
    expected = []
    for line in doc.splitlines():
        m = re.match(r"\| ([A-O]) \| `([^`]*)`", line)
        if m:
            expected.append(m.group(2).replace("\\n", "\n"))
    assert len(expected) == 15
    assert HEADERS == expected
    for spec in MONTHLY_SHEETS:
        ws = book[spec.name]
        assert [ws.cell(row=1, column=c).value for c in range(1, 16)] == expected, spec.name
        assert ws.cell(row=1, column=17).value is None


def test_ac_pi_50_used_ranges_and_ps_ranges_match_the_shape_doc(book):
    doc = _shape_doc()
    ranges = dict(re.findall(r"\| `([^`]+)`[^|]*\| (A1:AK\d+|B2:P26) \|", doc))
    assert len(ranges) == 9
    for name in SHEET_ORDER:
        assert book[name].dimensions == ranges[name], name

    seen = []
    for spec in MONTHLY_SHEETS:
        ws = book[spec.name]
        ps = [ws.cell(row=r, column=1).value for r in range(2, 2 + spec.count)]
        assert ps == [f"PS26-{n:04d}" for n in range(spec.first_ps, spec.first_ps + spec.count)]
        seen.extend(ps)
    assert seen == [f"PS26-{n:04d}" for n in range(1, 1399)]


def test_ac_pi_50_data_rows_placeholders_total_row_rollup_and_q8(book):
    data = placeholders = 0
    for spec in MONTHLY_SHEETS:
        ws = book[spec.name]
        last = 1 + spec.count
        for r in range(2, last + 1):
            if ws.cell(row=r, column=4).value:
                data += 1
            else:
                placeholders += 1
                assert spec.name == "AUG'26"
                assert all(ws.cell(row=r, column=c).value is None for c in range(2, 16))
        assert ws.cell(row=last + 1, column=1).value is None
        assert ws.cell(row=last + 1, column=8).value == f"=SUM(H2:H{last})"
        title_row = last + 1 + spec.blank_rows + 1
        assert ws.cell(row=title_row, column=2).value == spec.rollup_title
        assert [ws.cell(row=title_row + 1, column=c).value for c in (2, 3, 4)] == [
            "SALESPERSON", "TOTAL PO", "TOTAL AMOUNT"]
        assert ws["Q8"].value == " " * 300
    assert data == EXPECTED["data_rows"] == 1282
    assert placeholders == 116


def test_ac_pi_50_summary_sheet_has_its_merged_cells_and_no_ps_heading(book):
    ws = book[SUMMARY_SHEET]
    assert sorted(str(r) for r in ws.merged_cells.ranges) == sorted(SUMMARY_MERGES)
    assert ws["B2"].value == "WITH SCHEDULE"
    assert ws["F2"].value == "WITHOUT SCHEDULE"
    assert ws["B25"].value == "REVENUE TOTALS"
    assert ws["L24"].value == "."
    for spec in MONTHLY_SHEETS:
        assert book[spec.name].merged_cells.ranges == [] or not book[spec.name].merged_cells.ranges


def test_ac_pi_50_every_dirty_pattern_is_present():
    specs = fx.row_specs()
    data = [s for s in specs if fx.fold(s.customer)]
    assert EXPECTED["dash_rows"] == 7
    assert EXPECTED["multi_so_rows"] == 18
    assert EXPECTED["numeric_po_rows"] > 100
    assert sum(1 for s in data if s.po_date.year == 2025) == 16
    assert [s.po_date.year for s in specs[:3]] == [2025, 2025, 2025]
    assert sum(1 for s in data if s.po_date.year == 2026 and s.po_date.month != s.month) == 10
    sched = [s.schedule for s in specs]
    assert sched.count("YES") == 1064
    assert sched.count("O/C") == 207
    assert (sched.count("NO"), sched.count("YS"), sched.count("CBD")) == (1, 1, 1)
    assert sched.count(None) == 124
    texts_j = {s.amended for s in data if isinstance(s.amended, str)}
    assert {"amend 9/4/2026", "AMEND 14/5/2026", "revised 3/4/2026", "REVISED", "amend", " ",
            "AMEND 8/4/202"} <= texts_j
    assert sum(1 for s in data if not isinstance(s.amended, (str, type(None)))) == 6
    delivery = [s.delivery for s in data]
    assert delivery.count("IMMEDIATE") == 485
    assert {"NEXTWEEK", "AFTER CNY", "1Q 2027", "TBA/ FEB 2027", "IMMDIATE", "URGNT"} <= set(
        d for d in delivery if isinstance(d, str))
    assert sum(1 for d in delivery if not isinstance(d, (str, type(None)))) >= 326
    outstanding = {s.outstanding for s in data if s.outstanding}
    assert {"CANCELLED", "CANCELLED 12/6/2026", "on hold 23/4/2026"} <= outstanding
    so_cells = {s.so_cell for s in data if s.so_cell}
    assert {"CANCELLED", "CANCELLED 11/5/2026", "refer PS26-0022"} <= so_cells
    assert any(", " in c for c in so_cells) and any(re.search(r"SO\d{6},SO", c) for c in so_cells)
    remarks = {s.remarks for s in data if s.remarks}
    assert {"WAIVE TRANSPORT CHARGE", "WAIVE TRASNPORT CHARGE", "WAIVE TRASPORT CHARGE",
            "WAIVE TRANPORT CHARGE", "WAIVE TRANSPORT CHARGES", "CANCELLED",
            "CANCELLED BY CASH", "CANCEL PS NO", "HOLD"} <= remarks
    assert any(re.fullmatch(r"SO\d{6}", r) for r in remarks)
    assert sum(1 for s in data if s.customer != s.customer.strip()) == 28
    assert sum(1 for s in data if s.salesperson != s.salesperson.strip()) == 45
    assert sum(1 for s in data if s.project and s.project != fx.fold(s.project)) >= 40
    assert len({fx.fold(s.salesperson) for s in data}) == 17
    assert len({fx.fold(s.customer_service) for s in data}) == 12
    assert EXPECTED["distinct"]["customer"] == 202
    assert sum(1 for s in data if not fx.fold(s.project)) > 300
    pairs = {}
    for s in data:
        pairs.setdefault((fx.fold(s.customer), s.po), []).append(s.ps)
    assert sum(1 for v in pairs.values() if len(v) > 1) == 3
    # Fake names only.
    for s in data:
        assert re.fullmatch(r"CUSTOMER \d{3} (SDN BHD|SENDIRIAN BERHAD)", fx.fold(s.customer))


def test_expected_is_derived_from_the_row_specs():
    again = fx.compute_expected(fx.row_specs())
    assert again == EXPECTED
    assert sum(EXPECTED["counts"].values()) == EXPECTED["ps_rows"] == 1398
    assert EXPECTED["skip_codes"]["placeholder"] == 116
    assert EXPECTED["skip_codes"]["cancelled"] == 9


# --------------------------------------------------------------------------- full preview


@pytest.fixture
def full_preview(world):
    from app.services.project_import import service

    w = world
    content = build_workbook()
    run = new_run(w, content, filename="TOTAL SALES ORDER SUMMARY 2026.xlsx",
                  sheets=[s.name for s in MONTHLY_SHEETS])
    w.db.commit()
    before = snapshot(w.db)
    report = service.preview(w.db, run, user_id=w.admin_id)
    return w, run, report, before


def test_ac_pi_50_full_preview_counts_per_outcome(full_preview):
    _w, _run, report, _before = full_preview
    counts = {k: v for k, v in report["counts"].items() if v}
    assert counts == {k: v for k, v in EXPECTED["counts"].items() if v}
    assert len(report["rows"]) == EXPECTED["ps_rows"]


def test_ac_pi_50_full_preview_skip_and_blocking_codes(full_preview):
    _w, _run, report, _before = full_preview
    for code, n in {**EXPECTED["skip_codes"], **EXPECTED["review_codes"]}.items():
        assert report["codes"].get(code, 0) == n, code


def test_ac_pi_50_full_preview_row_flags(full_preview):
    _w, _run, report, _before = full_preview
    for code, n in EXPECTED["flags"].items():
        assert report["codes"].get(code, 0) == n, code


def test_ac_pi_50_full_preview_codes_exactly(full_preview):
    _w, _run, report, _before = full_preview
    assert {k: v for k, v in report["codes"].items() if v} == EXPECTED["codes"]


def test_ac_pi_50_full_preview_rows_carry_the_spec_outcome(full_preview):
    _w, _run, report, _before = full_preview
    expected = {s.ps: fx.unmapped_outcome(s) for s in fx.row_specs()}
    for r in report["rows"]:
        outcome, codes = expected[r["ps_number"]]
        assert r["outcome"] == outcome, r["ps_number"]
        assert r["sheet"].strip() in {m.name.strip() for m in MONTHLY_SHEETS}
        if outcome == "skipped":
            assert r["codes"] == codes, r["ps_number"]


def test_ac_pi_50_full_preview_writes_nothing(full_preview):
    w, _run, _report, before = full_preview
    assert snapshot(w.db) == before
