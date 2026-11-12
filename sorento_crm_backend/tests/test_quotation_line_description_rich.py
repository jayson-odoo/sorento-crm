"""QUOTE-DESC-RICHTEXT: the proposal / quotation line Description is rich text.

Card: documentation/plans/project-sales/CARD-quote-desc-richtext-10nov.md. The stored format is the
price tag one (`app/utils/tag_rich_text.py`): plain text kept as typed, or sanitised HTML that starts
with a block tag. Styled text prints on the PDF and the sign page; every plain-text reader (Excel,
the price-change alert, SO draft, PO check, sample request, spec sheet, feedback rows) reads it with
no markup. Product wording below is invented.
"""
from __future__ import annotations

from types import SimpleNamespace


from app.utils.tag_rich_text import sanitise_description

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import (
    MARKER,
    PRICED_QTY,
    PRICED_RATE,
    _issue,
    _product,
    _setup,
)

STYLED = (
    '<p><strong>ZZT ONE PIECE WC</strong> (S-TRAP 250MM) '
    '<span style="color: #dc2626">C/W SEAT COVER</span></p>'
)
PLAIN_SENTENCE = "ZZT ONE PIECE WC (S-TRAP 250MM) C/W SEAT COVER"


# ------------------------------------------------------------------ the save rule (pure)


def test_plain_text_is_stored_exactly_as_typed_even_with_angle_brackets():
    assert sanitise_description("PIPE <DN50 & ELBOW>\nc/w seat") == "PIPE <DN50 & ELBOW>\nc/w seat"
    assert sanitise_description("WC <b>white</b>") == "WC <b>white</b>"


def test_styled_html_keeps_marks_and_colour():
    assert sanitise_description(STYLED) == STYLED


def test_script_handlers_and_url_styles_are_removed_on_save():
    dirty = (
        '<p onclick="steal()"><strong>WC</strong><script>alert(1)</script>'
        '<img src=x onerror="alert(2)">'
        '<span style="color: #dc2626; background-image: url(http://evil)">red</span>'
        '<a href="javascript:alert(3)">link</a></p>'
    )
    clean = sanitise_description(dirty)
    assert "script" not in clean
    assert "onclick" not in clean
    assert "onerror" not in clean
    assert "<img" not in clean
    assert "url(" not in clean
    assert "javascript" not in clean
    assert "<strong>WC</strong>" in clean
    assert '<span style="color: #dc2626">red</span>' in clean


def test_an_edit_with_no_styling_is_stored_back_as_plain_lines():
    assert sanitise_description("<p>BASIN MIXER</p><p>c/w pop-up waste</p>") == (
        "BASIN MIXER\nc/w pop-up waste"
    )
    assert sanitise_description("<p>BASIN MIXER<br>c/w waste</p>") == "BASIN MIXER\nc/w waste"
    # Typed angle brackets come back as the characters, not as markup.
    assert sanitise_description("<p>PIPE &lt;DN50&gt; &amp; ELBOW</p>") == "PIPE <DN50> & ELBOW"


def test_an_unstyled_edit_whose_text_would_read_as_html_stays_html():
    # Plain text starting "<p>" would be taken for rich text on the way back out.
    value = "<p>&lt;p&gt; typed literally</p>"
    assert sanitise_description(value) == value


def test_a_leading_invisible_character_cannot_hide_markup_from_the_save_rule():
    clean = sanitise_description('\ufeff<p>WC<img src=x onerror="alert(1)"></p>')
    assert clean == "WC"
    assert "<img" not in (sanitise_description("\u200b<p><strong>A</strong><img src=x></p>") or "")


def test_an_empty_editor_stores_nothing():
    assert sanitise_description("<p></p>") is None
    assert sanitise_description("   ") is None
    assert sanitise_description(None) is None


# ------------------------------------------------------------------ PDF cell (pure)


def test_pdf_plain_description_prints_as_today():
    from app.services import project_quotation_pdf_service as pdf

    assert pdf._description_html("BASIN MIXER\nc/w <waste> & trap") == (
        "BASIN MIXER<br/>c/w &lt;waste&gt; &amp; trap"
    )
    assert pdf._description_html(None) == ""


def test_pdf_styled_description_prints_its_styling():
    from app.services import project_quotation_pdf_service as pdf

    html = pdf._description_html(STYLED)
    assert '<div class="rt">' in html
    assert "<strong>ZZT ONE PIECE WC</strong>" in html
    assert '<span style="color: #dc2626">C/W SEAT COVER</span>' in html


def test_pdf_re_sanitises_a_stored_value_that_skipped_the_save_path():
    from app.services import project_quotation_pdf_service as pdf

    html = pdf._description_html(
        '<p>WC<script>alert(1)</script><img src="file:///etc/passwd"></p>'
    )
    assert "script" not in html
    assert "<img" not in html
    assert "WC" in html


# ------------------------------------------------------------------ copy (pure)


def test_revision_and_proposal_to_quotation_copy_keeps_the_styling():
    from app.models.projects import ProjectQuotationLine
    from app.services import project_quotation_service as quotes

    line = ProjectQuotationLine(description_snapshot=STYLED, unit_price=1, quantity=1)
    copy = quotes.copy_line(line, version_id="v", company_id=None)
    assert copy.description_snapshot == STYLED


# ------------------------------------------------------------------ write path + readers (DB)


def _styled_issue(db, *, description=STYLED):
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    env = _setup(db)
    owner = env["owner"]
    product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} catalogue WC")
    document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
    scope = qdocs.add_scope(db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner)
    line = quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=owner,
        payload={
            "product_id": product.id,
            "unit_price": PRICED_RATE,
            "quantity": PRICED_QTY,
            "description_snapshot": description,
        },
    )
    return env, document, line


def test_every_line_write_sanitises_the_description():
    with blank_session() as db:
        _env, _document, line = _styled_issue(
            db, description='<p><strong>WC</strong><script>x()</script></p>'
        )
        db.refresh(line)
        assert line.description_snapshot == "<p><strong>WC</strong></p>"


def test_a_plain_catalogue_default_is_still_the_starting_text():
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        env = _setup(db)
        owner = env["owner"]
        product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} catalogue WC")
        document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
        scope = qdocs.add_scope(db, document=document, scope_label=f"{MARKER} A", actor_user_id=owner)
        line = quotes.upsert_line(
            db,
            version=quotes.current_version(db, scope.id),
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": PRICED_RATE, "quantity": 1,
                     "description_snapshot": "<p></p>"},
        )
        assert line.description_snapshot == f"{MARKER} catalogue WC"


def test_the_issued_pdf_prints_the_styling():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env, document, _line = _styled_issue(db)
        issued = _issue(db, document, env["owner"])
        html = qpdf.build_issue_html(db, issued)
        assert "<strong>ZZT ONE PIECE WC</strong>" in html
        assert '<span style="color: #dc2626">C/W SEAT COVER</span>' in html
        # Not escaped into visible tags.
        assert "&lt;strong&gt;" not in html


def test_the_sign_page_carries_the_styled_value_for_its_safe_renderer():
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env, document, _line = _styled_issue(db)
        issued = _issue(db, document, env["owner"])
        page = qdocs.serialize_sign_page(db, issued)
        descriptions = [row["description"] for scope in page["scopes"] for row in scope["lines"]]
        assert STYLED in descriptions


def test_the_excel_export_reads_the_text_without_markup():
    from app.services import project_quotation_excel_service as qxlsx

    with blank_session() as db:
        env, document, _line = _styled_issue(db)
        issued = _issue(db, document, env["owner"])
        workbook = qxlsx.build_issue_workbook(db, issued)
        values = [
            cell.value
            for sheet in workbook.worksheets
            for row in sheet.iter_rows()
            for cell in row
            if isinstance(cell.value, str)
        ]
        assert any(PLAIN_SENTENCE in value for value in values)
        assert not any("<strong>" in value or "<span" in value for value in values)


def test_the_price_change_alert_names_the_line_without_markup(monkeypatch):
    from app.services import project_quotation_document_service as qdocs

    line = SimpleNamespace(
        product_id="p1", product_set_id=None, product_code_snapshot="ZZT-1",
        description_snapshot=STYLED, unit_price=2, is_rate_only=False,
    )
    monkeypatch.setattr(qdocs, "issue_price_map", lambda db, rec: {"k": 1})
    monkeypatch.setattr(qdocs, "issue_lines", lambda db, rec: [line])
    monkeypatch.setattr(qdocs, "line_key", lambda l: "k")
    changes = qdocs.price_changes(None, object(), object())
    assert changes[0]["description"] == PLAIN_SENTENCE


def test_line_text_is_the_plain_reading():
    from app.services import project_quotation_service as quotes

    assert quotes.line_text(SimpleNamespace(description_snapshot=STYLED)) == PLAIN_SENTENCE
    assert quotes.line_text(SimpleNamespace(description_snapshot="A <b>\nB")) == "A <b>\nB"
    assert quotes.line_text(SimpleNamespace(description_snapshot=None)) is None


# Every place allowed to read the stored value raw: it either writes it, copies it, hands it to a
# renderer that draws runs (editor GET, sign page), or prints it through the PDF's sanitiser.
# Anything else is a plain-text reader and must go through `line_text`.
_RAW_READERS = {
    "app/models/projects.py",
    "app/schemas/projects.py",
    "app/services/project_quotation_service.py",  # write path, copy_line, catalogue default, GET lines
    "app/services/project_quotation_pdf_service.py",  # via _description_html only
    "app/services/project_quotation_document_service.py",  # sign page payload only
}


def test_no_plain_text_reader_reads_the_stored_markup_raw():
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in (root / "app").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        for number, text in enumerate(path.read_text().splitlines(), start=1):
            if "description_snapshot" not in text or text.lstrip().startswith("#"):
                continue
            if rel in _RAW_READERS:
                continue
            offenders.append(f"{rel}:{number}: {text.strip()}")
    assert offenders == []


def test_the_pdf_reads_the_description_only_through_its_sanitiser():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / "app/services/project_quotation_pdf_service.py").read_text()
    for text in source.splitlines():
        if "description_snapshot" in text:
            assert "_description_html(" in text, text


def test_the_document_service_reads_raw_only_for_the_sign_page():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / "app/services/project_quotation_document_service.py").read_text()
    raw = [t.strip() for t in source.splitlines() if "description_snapshot" in t and "line_text(" not in t]
    assert raw == ['"description": line.description_snapshot,']


def test_plain_text_keeps_a_list_marker_on_the_same_line_as_its_item():
    """Crew pass on 7ea1d6efc: the editor wraps each list item's text in a <p>, and the plain
    reading (Excel, WhatsApp, notifications) put the marker alone on a line ("• \\nbullet one")."""
    from app.utils.tag_rich_text import plain_text

    html = (
        "<p>Intro</p><ul><li><p>bullet one</p></li><li><p>bullet two</p></li></ul>"
        "<ol><li><p>num one</p></li><li><p>num two</p><ul><li><p>nested</p></li></ul></li></ol>"
    )
    assert plain_text(html) == (
        "Intro\n• bullet one\n• bullet two\n1. num one\n2. num two\n  • nested"
    )
    # A list item without the inner paragraph reads the same.
    assert plain_text("<ul><li>bare item</li></ul>") == "• bare item"


def test_line_text_of_a_styled_list_reads_one_item_per_line():
    from app.services import project_quotation_service as quotes

    value = '<ul><li><p><strong>WC</strong> c/w seat</p></li><li><p>angle valve</p></li></ul>'
    assert quotes.line_text(SimpleNamespace(description_snapshot=value)) == (
        "• WC c/w seat\n• angle valve"
    )
