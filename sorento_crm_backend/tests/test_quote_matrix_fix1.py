"""PS-QUOTE-MATRIX fix round 1 (backend): rendered vertical headings, Excel safety and size,
feedback limits and the notification collapse. Postgres only, borrowing the lane's worlds."""
from __future__ import annotations

import re
from io import BytesIO

import pytest

from ._pg_fixture import blank_session
from .test_project_proposal_quotation import MARKER, _issue, _price, _setup
from .test_quote_matrix_render import UNIT_LABEL, _one_grid, _workbook
from .test_quote_matrix_service import COLUMNS, grid_world, set_grid


# ------------------------------------------------------------------ PDF: truly vertical headings


def _pdf_lines(db, record):
    import fitz

    from app.services import project_quotation_pdf_service as qpdf

    pdf_bytes, _name = qpdf.render_issue_pdf(db, record)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    found = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"]).strip()
                found.append((text, tuple(round(v) for v in line["dir"]), line["bbox"]))
    return found


def test_a_wide_scope_renders_its_leaf_headings_vertically_in_the_pdf():
    with blank_session() as db:
        record = _one_grid(db, 13)
        lines = _pdf_lines(db, record)
        leaf = [entry for entry in lines if re.fullmatch(r"R\d+", entry[0])]
        assert len(leaf) == 13, lines
        for text, direction, bbox in leaf:
            assert direction in ((0, -1), (0, 1)), (text, direction)
            assert (bbox[3] - bbox[1]) > (bbox[2] - bbox[0]), (text, bbox)


def test_a_narrow_scope_keeps_its_leaf_headings_horizontal_in_the_pdf():
    with blank_session() as db:
        record = _one_grid(db, 12)
        leaf = [e for e in _pdf_lines(db, record) if re.fullmatch(r"R\d+", e[0])]
        assert len(leaf) == 12
        assert all(direction == (1, 0) for _t, direction, _b in leaf)


def test_the_pdf_footer_is_blank_under_empty_columns_and_a_rate_only_pair_prints_a_dash():
    from app.services import project_quotation_pdf_service as qpdf

    from .test_quote_matrix_render import _scope_block, _tds

    with blank_session() as db:
        w = grid_world(db)
        footer = _tds(_scope_block(qpdf.build_issue_html(db, w.record), UNIT_LABEL), "tfoot")
        qty_row = next(r for r in footer if "TOTAL QTY" in r)
        # tb_kit and tank are empty in this world: nothing prints under them, never "0".
        assert "0" not in qty_row

    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        line = _price(db, scope, product, owner, "10.00", 1)
        line.is_rate_only = True
        from app.services import project_quotation_service as quotes

        columns = [
            {"key": "a", "label": "A", "cols": [{"key": "a1", "label": "A1"}, {"key": "a2", "label": "A2"}]},
            {"key": "b", "label": "B", "cols": [{"key": "b1", "label": "B1"}, {"key": "b2", "label": "B2"}]},
        ]
        set_grid(db, quotes.current_version(db, scope.id), columns, [(line, {"a1": "3.00"})])
        record = _issue(db, document, owner)
        db.flush()
        rows = _tds(_scope_block(qpdf.build_issue_html(db, record), UNIT_LABEL), "tbody")
        row = next(r for r in rows if "10.00" in r)
        assert row.count("-") >= 3  # A's amount (rate only) and both cells of B


# ------------------------------------------------------------------ Excel


def _all_cells(sheet):
    return [c for row in sheet.iter_rows() for c in row if c.value is not None]


def test_excel_text_that_looks_like_a_formula_is_written_as_text():
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        line = _price(db, scope, product, owner, "10.00", 1)
        line.description_snapshot = '=HYPERLINK("http://x","y")'
        columns = [
            {"key": "h1", "label": '=HYPERLINK("x","y")', "cols": [{"key": "c1", "label": "+SUM(1)"}]},
        ]
        set_grid(db, quotes.current_version(db, scope.id), columns, [(line, {"c1": "2.00"})])
        record = _issue(db, document, owner)
        db.flush()
        sheet = _workbook(db, record).worksheets[0]
        texts = [c for c in _all_cells(sheet) if isinstance(c.value, str) and c.value[:1] in "=+-@"]
        by_value = {c.value: c for c in texts}
        for typed in ('=HYPERLINK("http://x","y")', '=HYPERLINK("x","y")', "+SUM(1)"):
            assert by_value[typed].data_type == "s", typed
        # Our own sums are still formulas.
        assert any(c.data_type == "f" for c in _all_cells(sheet))


def test_excel_a_plain_scope_description_starting_with_equals_is_text_too():
    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        line = _price(db, scope, product, owner, "10.00", 1)
        line.description_snapshot = "=1+1"
        record = _issue(db, document, owner)
        db.flush()
        sheet = _workbook(db, record).worksheets[0]
        cell = next(c for c in _all_cells(sheet) if c.value == "=1+1")
        assert cell.data_type == "s"


def _big_grid(db, count: int):
    from app.models.projects import ProjectQuotationLine
    from app.services import project_quotation_service as quotes

    company_id, owner, product, project, document, scope = _setup(db)
    first = _price(db, scope, product, owner, "10.00", 1)
    version = quotes.current_version(db, scope.id)
    lines = [first]
    for i in range(count - 1):
        copy = quotes.copy_line(first, version_id=version.id, company_id=company_id)
        copy.sort_order = i + 2
        db.add(copy)
        lines.append(copy)
    db.flush()
    for i, line in enumerate(lines):
        line.is_rate_only = i % 2 == 1  # alternating, so no long contiguous run exists
    columns = [{"key": "h1", "label": "H", "cols": [{"key": "c1", "label": "C1"}, {"key": "c2", "label": "C2"}]}]
    set_grid(db, version, columns, [(line, {"c1": "1.00", "c2": "2.00"}) for line in lines])
    record = _issue(db, document, owner)
    db.flush()
    return record


def test_excel_every_formula_of_a_1200_line_grid_is_under_the_excel_limit():
    with blank_session() as db:
        record = _big_grid(db, 1200)
        sheet = _workbook(db, record).worksheets[0]
        formulas = [c.value for c in _all_cells(sheet) if c.data_type == "f"]
        assert formulas
        assert max(len(f) for f in formulas) < 8192


def test_excel_grid_money_cells_are_rounded_formulas():
    with blank_session() as db:
        w = grid_world(db)
        sheet = _workbook(db, w.record).worksheets[0]
        rounded = [c.value for c in _all_cells(sheet) if isinstance(c.value, str) and c.value.startswith("=ROUND(")]
        assert len(rounded) >= 3  # two pair amounts + the grand total of the trap row, at least
        assert all(re.fullmatch(r"=ROUND\([A-Z]+\d+\*[A-Z]+\d+,2\)", v) for v in rounded)


def test_excel_a_footer_too_long_for_a_formula_falls_back_to_the_computed_value(monkeypatch):
    from app.services import project_quotation_excel_service as qxl

    monkeypatch.setattr(qxl, "_FORMULA_LIMIT", 20)
    with blank_session() as db:
        record = _big_grid(db, 40)
        sheet = _workbook(db, record).worksheets[0]
        label = max((c for c in _all_cells(sheet) if c.value == "TOTAL QTY"), key=lambda c: c.row)
        values = [sheet.cell(row=label.row, column=label.column + i).value for i in (1, 2)]
        assert values == [20, 40]  # 20 counted rows x 1 and x 2


# ------------------------------------------------------------------ feedback limits and safety

from .test_quote_feedback import _item, _root, _send, fb  # noqa: E402,F401  (fixture reuse)


def test_feedback_over_the_per_issue_cap_is_429(fb, monkeypatch):
    from app.services import quotation_amendment_service as amend

    monkeypatch.setattr(amend, "MAX_REQUESTS_PER_ISSUE", 2)
    for _ in range(2):
        assert _send(fb, [_item(fb.w.trap, "remove")]).status_code == 200
    refused = _send(fb, [_item(fb.w.trap, "remove")])
    assert refused.status_code == 429, refused.text
    assert refused.json()["code"] == "quotation_feedback_limit"


def test_two_submits_in_one_window_send_one_notification(fb):
    from app.models.notification import Notification

    def sent():
        fb.db.expire_all()
        return fb.db.query(Notification).filter(
            Notification.event_type == "project_quotation_amendment_requested"
        ).count()

    assert _send(fb, [_item(fb.w.trap, "note", note="one")]).status_code == 200
    after_first = sent()
    assert after_first >= 1, "the owner should have been notified once"
    assert _send(fb, [_item(fb.w.trap, "note", note="two")]).status_code == 200
    assert sent() == after_first


def test_the_staff_list_is_bounded_but_open_count_counts_everything(fb, monkeypatch):
    from app.services import quotation_amendment_service as amend

    monkeypatch.setattr(amend, "FEEDBACK_LIST_LIMIT", 1)
    for _ in range(2):
        assert _send(fb, [_item(fb.w.trap, "remove")]).status_code == 200
    body = fb.client.get(f"{_root(fb)}/feedback").json()
    assert len(body["requests"]) == 1
    assert body["open_count"] == 2


def test_an_oversized_amount_is_422_not_500(fb):
    huge = "9" * 30
    for item in (
        _item(fb.w.trap, "quantity", value=huge),
        _item(fb.w.trap, "unit_price", value=huge),
        _item(fb.w.trap, "model_swap", model="X", value=huge),
    ):
        response = _send(fb, [item])
        assert response.status_code == 422, response.text


def test_each_staff_feedback_row_names_its_scope_id(fb):
    assert _send(fb, [_item(fb.w.trap, "remove"), _item(fb.w.plain, "remove")]).status_code == 200
    (request,) = fb.client.get(f"{_root(fb)}/feedback").json()["requests"]
    ids = {row["line_id"]: row["scope_id"] for row in request["rows"]}
    assert ids[str(fb.w.trap.id)] == str(fb.w.unit_scope.id)
    assert ids[str(fb.w.plain.id)] == str(fb.w.guard_scope.id)
    assert all(row["scope_label"] for row in request["rows"])
