"""RED tests B9: GET /api/v1/master-data/costing/export (.xlsx). PRODUCT-COSTING.
AC-CG-09, AC-CG-05 (blank + reason), AC-AX-01.

Contract 4.5: same query as /rows minus paging. Row 1 is the title
`Costing - <Company standard | CODE NAME> - as of <d MMM yyyy>`; row 2 the headers; data from
row 3. Numeric cells are numbers, unknown is an EMPTY cell, Note = reason texts joined by "; ".

Choices the contract leaves open (the coder follows these):
  * The workbook's first (active) sheet is read.
  * A numeric cell holds the full-precision value (31.71875) with a 2 dp number_format; the
    2 dp half-up rounding is display only.
  * Cost method cell = the label ("Primary supplier"); Transport mode cell compares
    case-insensitively with "add" / "multiply".
  * Rate (per MYR) = `units_per_base` (1.6), as the page shows it.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook

from tests.support.costing_env import costing_env  # noqa: F401

A = pytest.approx

HEADERS = [
    "Category", "Code", "Name", "Supplier", "Currency", "Cost", "Rate (per MYR)", "SST",
    "Transport mode", "Transport value", "Landing (RM)", "Cost method", "Mark-up %", "Final (RM)",
    "List price (AutoCount)", "Margin %", "Note",
]
COL = {name: i for i, name in enumerate(HEADERS)}


def _sheet(response):
    assert response.status_code == 200, response.text
    assert "spreadsheetml" in response.headers["content-type"]
    return load_workbook(BytesIO(response.content)).active


def _export(e, **params):
    return e.get("/export", **params)


def _rows(ws):
    """code -> list of the 17 cell objects, from row 3 down."""
    out = {}
    for cells in ws.iter_rows(min_row=3):
        if cells[COL["Code"]].value is None:
            continue
        out[cells[COL["Code"]].value] = cells
    return out


def _v(cells, header):
    return cells[COL[header]].value


def _setup(costing_env):
    e = costing_env
    w = e.workbook()
    e.as_user(e.viewer())
    return e, w


def test_ac_cg_09_title_row_names_the_view_and_the_as_of_date(costing_env):
    e, w = _setup(costing_env)
    ws = _sheet(_export(e, as_of="2026-11-11"))
    assert ws.cell(row=1, column=1).value == "Costing - Company standard - as of 11 Nov 2026"

    ws = _sheet(_export(e, as_of="2026-10-31", party_id=w.customer.id))
    assert ws.cell(row=1, column=1).value == (
        "Costing - 304-R017 RELATED - BATHPLUS SDN BHD - as of 31 Oct 2026"
    )


def test_ac_cg_09_headers_are_in_the_sheet1_order_on_row_two(costing_env):
    e, w = _setup(costing_env)
    ws = _sheet(_export(e, as_of="2026-11-11"))
    assert [c.value for c in ws[2]][: len(HEADERS)] == HEADERS


def test_ac_cg_09_standard_workbook_row_cells(costing_env):
    e, w = _setup(costing_env)
    cells = _rows(_sheet(_export(e, as_of="2026-11-11")))["CGB9032B"]
    assert _v(cells, "Category") == "Ceramics"
    assert _v(cells, "Name") == "WB 245 basin"
    assert _v(cells, "Supplier") == "SUP-A01"
    assert _v(cells, "Currency") == "RMB"
    assert _v(cells, "Cost") == A(34.5)
    assert _v(cells, "Rate (per MYR)") == A(1.6, abs=1e-4)
    assert _v(cells, "SST") == A(1.1)
    assert str(_v(cells, "Transport mode")).lower() == "add"
    assert _v(cells, "Transport value") == A(8.0)
    assert _v(cells, "Landing (RM)") == A(31.71875, abs=1e-6)
    assert _v(cells, "Cost method") == "Primary supplier"
    assert _v(cells, "Mark-up %") == A(149.0640394, abs=1e-6)
    assert _v(cells, "Final (RM)") == A(79.0)
    assert _v(cells, "List price (AutoCount)") == A(79.0)
    assert _v(cells, "Margin %") is None  # no margin in the Company standard view
    assert _v(cells, "Note") in (None, "")


def test_ac_cg_09_numbers_are_numbers_with_a_two_place_display_format(costing_env):
    e, w = _setup(costing_env)
    cells = _rows(_sheet(_export(e, as_of="2026-11-11")))["CGB9032B"]
    for header in ("Cost", "Rate (per MYR)", "SST", "Transport value", "Landing (RM)", "Mark-up %",
                   "Final (RM)", "List price (AutoCount)"):
        value = _v(cells, header)
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (header, value)
    assert cells[COL["Landing (RM)"]].number_format.endswith("0.00")
    assert cells[COL["Final (RM)"]].number_format.endswith("0.00")


def test_ac_cg_09_costless_rows_are_blank_cells_with_the_reason_in_note(costing_env):
    e, w = _setup(costing_env)
    rows = _rows(_sheet(_export(e, as_of="2026-11-11")))

    acc = rows["A-4001"]
    for header in ("Cost", "Landing (RM)", "Mark-up %", "Margin %"):
        assert _v(acc, header) is None, header  # empty cell, not 0
    assert _v(acc, "Note") == "No cost"

    bare = rows["N-9001"]
    assert _v(bare, "Landing (RM)") is None and _v(bare, "Supplier") is None
    assert _v(bare, "Note") == "Set a primary supplier"


def test_ac_cg_09_note_joins_reason_texts_with_semicolons(costing_env):
    e, w = _setup(costing_env)
    cat = e.category("NoRule")
    p = e.item("EUR-3", category=cat, list_price="60")  # EUR with no rate AND no transport rule
    e.cost_link(p, w.sup_d, cost="7.50", currency="EUR", primary=True)
    e.db.commit()
    cells = _rows(_sheet(_export(e, as_of="2026-11-11")))["EUR-3"]
    assert _v(cells, "Landing (RM)") is None
    assert _v(cells, "Cost") == A(7.5)
    note = _v(cells, "Note")
    assert note == "No rate for EUR on 11 Nov 2026; No transport rule"


def test_ac_cg_09_party_export_has_party_price_markup_and_margin(costing_env):
    e, w = _setup(costing_env)
    rows = _rows(_sheet(_export(e, party_id=w.customer.id, as_of="2026-11-11")))
    assert set(rows) == {"CGB9032B", "JAC-5001"}
    wb = rows["CGB9032B"]
    assert _v(wb, "Mark-up %") == A(8.0)
    assert _v(wb, "Final (RM)") == A(34.25625, abs=1e-6)
    assert _v(wb, "Margin %") == A(130.6148513, abs=1e-6)
    jac = rows["JAC-5001"]
    assert _v(jac, "Mark-up %") == A(10.0)
    assert _v(jac, "Final (RM)") == A(1861.6125, abs=1e-6)
    assert _v(jac, "Margin %") == A(114.8100101, abs=1e-6)


def test_ac_cg_09_the_whole_filtered_set_is_exported_with_no_paging(costing_env):
    e, w = _setup(costing_env)
    for i in range(52):
        e.item(f"BULK-{i:03d}", category=w.cat_taps, list_price="10")
    e.db.commit()
    rows = _rows(_sheet(_export(e, as_of="2026-11-11")))
    assert len(rows) == 8 + 52  # > the page default of 50
    only_bulk = _rows(_sheet(_export(e, as_of="2026-11-11", q="BULK-")))
    assert len(only_bulk) == 52


def test_ac_cg_09_the_same_filters_as_rows_apply(costing_env):
    e, w = _setup(costing_env)
    assert set(_rows(_sheet(_export(e, as_of="2026-11-11", has_cost="true")))) == {
        "CGB9032B", "JAC-5001", "T-1001", "K-2001", "S-3001", "Z-0001"}
    assert set(_rows(_sheet(_export(e, as_of="2026-11-11", category_id=w.cat_taps.id)))) == {"T-1001"}
    assert set(_rows(_sheet(_export(e, as_of="2026-11-11", q="jac")))) == {"JAC-5001"}


def test_ac_cg_09_as_of_changes_the_exported_landing(costing_env):
    e, w = _setup(costing_env)
    cells = _rows(_sheet(_export(e, as_of="2026-10-31")))["CGB9032B"]
    assert _v(cells, "Rate (per MYR)") == A(1.62, abs=1e-4)
    assert _v(cells, "Landing (RM)") == A(34.5 * 0.617284 * 1.1 + 8, abs=1e-6)


def test_ac_ax_01_export_needs_cost_view(costing_env):
    e, w = _setup(costing_env)
    e.as_user(e.user())
    assert _export(e, as_of="2026-11-11").status_code == 403
    e.as_user(e.user("products.party_costing.manage"))
    assert _export(e, as_of="2026-11-11").status_code == 403
