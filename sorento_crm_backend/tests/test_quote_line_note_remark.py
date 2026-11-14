"""QUOTE-LINE-NOTE-REMARK: a quotation line's note prints in the customer's REMARK column.

UAC: documentation/plans/projects/quote-line-note-remark-12nov-acceptance-criteria.md. One
formatter (`quotation_columns.remark` / `for_lines`) feeds the PDF, the sign page and the Excel
workbook: the Non-cancellable flag first, then the trimmed note on its OWN line ("\\n", never
" · "); a blank note adds nothing; a heading row never prints a remark; a note is never cut.

Postgres only, via ``blank_session``; every row is seeded here (masked ZZT data).
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.models.product import ProductCategory
from app.models.projects import ProjectQuotationLine
from app.services import non_cancellable_service as nc
from app.services import quotation_columns

from ._pg_fixture import blank_session
from .test_non_cancellable_items import _line, _product, _scope, _series, world  # noqa: F401

NOTE = "Lead time 6 weeks"
FLAG = "Non-cancellable"
LONG_NOTE = ("ZZT-A1 supply only, colour to be confirmed on site. " * 12)[:600]


def _ns(**kw):
    base = {"is_non_cancellable": False, "is_section": False, "notes": None}
    base.update(kw)
    return SimpleNamespace(**base)


# ------------------------------------------------------------- AC-1 / AC-2: remark()


def test_remark_flag_only_reads_non_cancellable():
    assert quotation_columns.remark(_ns(is_non_cancellable=True)) == FLAG


def test_remark_note_only_reads_the_trimmed_note():
    assert quotation_columns.remark(_ns(notes=f"  {NOTE}  ")) == NOTE


def test_remark_flag_and_note_sit_on_separate_lines():
    got = quotation_columns.remark(_ns(is_non_cancellable=True, notes=NOTE))
    assert got == f"{FLAG}\n{NOTE}"
    assert " · " not in got


def test_remark_blank_note_adds_nothing():
    assert quotation_columns.remark(_ns(notes="   \n\t ")) == ""
    assert quotation_columns.remark(_ns(is_non_cancellable=True, notes="  ")) == FLAG


def test_remark_keeps_line_breaks_inside_a_note():
    assert quotation_columns.remark(_ns(notes="ZZT-A1 line one\nline two")) == (
        "ZZT-A1 line one\nline two"
    )


def test_remark_never_truncates_a_long_note():
    assert len(LONG_NOTE.strip()) >= 500
    assert quotation_columns.remark(_ns(notes=LONG_NOTE)) == LONG_NOTE.strip()


def test_remark_heading_row_prints_nothing_whatever_its_note():
    assert quotation_columns.remark(_ns(is_section=True, notes=NOTE)) == ""
    assert quotation_columns.remark(_ns(is_section=True, is_non_cancellable=True, notes=NOTE)) == ""


# ------------------------------------------------------------------ AC-3: for_lines()


def _keys(lines):
    return [k for k, _l in quotation_columns.for_lines(lines)]


def test_for_lines_shows_remark_for_a_note_only_line():
    keys = _keys([_ns(), _ns(notes=NOTE)])
    assert quotation_columns.REMARK in keys
    assert keys[-1] == "amount" and keys[-2] == quotation_columns.REMARK


def test_for_lines_hides_remark_for_a_whitespace_only_note():
    assert quotation_columns.REMARK not in _keys([_ns(notes="   \n ")])


def test_for_lines_hides_remark_for_a_section_line_with_a_note():
    assert quotation_columns.REMARK not in _keys([_ns(is_section=True, notes=NOTE), _ns()])


# ------------------------------------------------------------------ AC-5: the PDF


def _remark_cell_lines(html: str) -> list:
    """What the customer reads in the first REMARK cell, one entry per printed line.

    Either form prints two lines: a ``<br>`` between them, or a raw newline in a cell whose
    ``td.remark`` style is ``white-space: pre-line`` (or ``pre-wrap``).
    """
    match = re.search(r'<td class="remark"[^>]*>(.*?)</td>', html, re.S)
    assert match is not None, "no REMARK cell in the scope"
    content = match.group(1)
    if re.search(r"<br\s*/?>", content):
        return [part.strip() for part in re.split(r"<br\s*/?>", content)]
    styled = re.search(r"\.remark[^{]*\{[^}]*white-space:\s*pre-(line|wrap)", html)
    assert styled, f"REMARK cell has no <br> and no pre-line style; content={content!r}"
    return [part.strip() for part in content.split("\n")]


def _flagged_line_with_note(world, note):  # noqa: F811
    db, cid, owner = world["db"], world["company_id"], world["owner"]
    tub = _product(db, cid, world["bath"].id, world["uom"], name="ZZT-A1 Bathtub")
    series = _series(db, cid, [world["bath"].id], [world["bath"].id])
    _q, version = _scope(db, cid, owner, series_id=series.id)
    line = _line(db, version, owner, tub)
    assert line.is_non_cancellable is True
    line.notes = note
    db.flush()
    return line


def test_pdf_plain_scope_prints_flag_and_note_on_separate_lines(world):  # noqa: F811
    from app.services import project_quotation_pdf_service as pdf

    line = _flagged_line_with_note(world, f"{NOTE}, A & B")
    html = pdf._scope_html(
        world["db"], {"lines": [line], "label": "House Units", "total": Decimal("1")}, {}
    )
    assert "<th>REMARK</th>" in html
    assert _remark_cell_lines(html) == [FLAG, f"{NOTE}, A &amp; B"]
    assert "A & B" not in html


def test_pdf_matrix_scope_prints_flag_and_note_on_separate_lines(world):  # noqa: F811
    from app.services import project_quotation_pdf_service as pdf

    line = _flagged_line_with_note(world, f"{NOTE}, A & B")
    line.qty_cells = {"ta_bh": "2.00"}
    world["db"].flush()
    columns = [{"key": "ta", "label": "TYPE A", "cols": [{"key": "ta_bh", "label": "1 BH"}]}]
    html = pdf._scope_html(
        world["db"],
        {"lines": [line], "label": "House Units", "total": Decimal("1"), "matrix_columns": columns},
        {},
    )
    assert "REMARK" in html
    assert _remark_cell_lines(html) == [FLAG, f"{NOTE}, A &amp; B"]
    assert "A & B" not in html


def test_pdf_prints_a_long_note_whole(world):  # noqa: F811
    from app.services import project_quotation_pdf_service as pdf

    line = _flagged_line_with_note(world, LONG_NOTE)
    html = pdf._scope_html(
        world["db"], {"lines": [line], "label": "House Units", "total": Decimal("1")}, {}
    )
    assert _remark_cell_lines(html) == [FLAG, LONG_NOTE.strip()]


# ---------------------------------------------- AC-4 / AC-6: sign page and Excel (issued)


def _issued_with_notes(db):
    """Scope A: a Non-cancellable line with a note. Scope B: an ordinary line with a note only."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    from .test_project_quotation_pdf import PRICED_QTY, PRICED_RATE, _issue, _setup
    from .test_project_quotation_pdf import _product as pdf_product

    env = _setup(db)
    cid, owner = env["company_id"], env["owner"]
    marked = ProductCategory(
        id=str(uuid.uuid4()),
        company_id=cid,
        category_code=f"ZZT-{uuid.uuid4().hex[:8]}",
        category_name="zzt-note ZZT Bathtubs",
    )
    db.add(marked)
    db.flush()
    nc.create_rule(db, company_id=cid, payload={"category_id": marked.id}, actor_user_id=owner)
    tub = pdf_product(db, marked.id, env["uom"], description="ZZT-A1 freestanding bathtub")
    trap = pdf_product(db, env["category"].id, env["uom"], description="ZZT-A2 bottle trap")

    document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
    a = qdocs.add_scope(db, document=document, scope_label="ZZT A", actor_user_id=owner)
    b = qdocs.add_scope(db, document=document, scope_label="ZZT B", actor_user_id=owner)
    flagged = quotes.upsert_line(
        db,
        version=quotes.current_version(db, a.id),
        actor_user_id=owner,
        payload={"product_id": tub.id, "unit_price": PRICED_RATE, "quantity": PRICED_QTY},
    )
    plain = quotes.upsert_line(
        db,
        version=quotes.current_version(db, b.id),
        actor_user_id=owner,
        payload={"product_id": trap.id, "unit_price": PRICED_RATE, "quantity": PRICED_QTY},
    )
    assert flagged.is_non_cancellable is True
    assert plain.is_non_cancellable is False
    for row_id, note in ((flagged.id, f"{NOTE}, A & B"), (plain.id, NOTE)):
        row = db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == row_id).one()
        row.notes = note
    db.flush()
    return _issue(db, document, owner)


def test_sign_page_line_remark_carries_flag_and_note():
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        issued = _issued_with_notes(db)
        page = qdocs.serialize_sign_page(db, issued)
        scope_a, scope_b = page["scopes"]

        assert scope_a["lines"][0]["remark"] == f"{FLAG}\n{NOTE}, A & B"
        # A note on its own still earns the REMARK column on its scope.
        assert "remark" in [c["key"] for c in scope_b["columns"]]
        assert scope_b["lines"][0]["remark"] == NOTE


def test_excel_remark_cell_holds_the_joined_text_with_wrap_on():
    from app.services import project_quotation_excel_service as qxlsx

    from .test_project_quotation_excel import _column_index, _data_rows

    with blank_session() as db:
        issued = _issued_with_notes(db)
        workbook = qxlsx.build_issue_workbook(db, issued)
        sheet_a, sheet_b = workbook.worksheets[0], workbook.worksheets[1]

        col = _column_index(sheet_a, "REMARK")
        cells = [sheet_a.cell(row=r, column=col) for r in _data_rows(sheet_a)]
        filled = [c for c in cells if c.value]
        assert [c.value for c in filled] == [f"{FLAG}\n{NOTE}, A & B"]
        assert filled[0].alignment.wrap_text is True

        col_b = _column_index(sheet_b, "REMARK")
        values_b = [sheet_b.cell(row=r, column=col_b).value for r in _data_rows(sheet_b)]
        assert NOTE in values_b
