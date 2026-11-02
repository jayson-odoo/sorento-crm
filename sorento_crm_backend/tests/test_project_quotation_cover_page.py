"""QUOTE-COVER-PAGE red tests (service, PDF html, countersign route).

Written BEFORE the implementation, from the UAC (A, C, E, F) and the plan's test list. The new
module is imported inside each test so every test fails on its own, not as one collection error.
Postgres only via ``blank_session``; every row carries the ``zzt-qcover`` marker and the chain is
seeded here (CI's database is empty).
"""
from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import text

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import (  # noqa: F401  (helpers, not tests)
    SIGNATURE_DATA_URI,
    _issue,
    _product,
    _setup,
)

MARKER = "zzt-qcover"

TERMS = (
    f"<p><strong>{MARKER} Heading line</strong></p>"
    f"<p>- {MARKER} dash line</p>"
    f"<ul><li>{MARKER} bullet top<ul><li>{MARKER} bullet nested</li></ul></li></ul>"
    f"<p></p>"
    f"<p>{MARKER} closing line</p>"
)

LABELS = [
    "Reference No.",
    "Date",
    "Attn",
    "Company",
    "Contact",
    "Add",
    "Email",
    "Quotation Purpose",
    "Terms & Conditions",
    "Payment Terms",
    "Validity",
    "Prepared By",
]
KEYS = [
    "reference",
    "date",
    "attn",
    "company",
    "contact",
    "address",
    "email",
    "purpose",
    "terms",
    "payment_terms",
    "validity",
    "prepared_by",
]


def _full_document(db, env, *, purpose=f"{MARKER} Supply of sanitary ware", terms=TERMS):
    """A document with every cover field filled, one priced scope, ready to issue."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    owner = env["owner"]
    document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
    document.attn_name = f"{MARKER} Kelly"
    document.signatory_name = f"{MARKER} Signer Only"
    document.recipient_name_snapshot = f"{MARKER} Nadi Cergas Sdn Bhd"
    document.recipient_phone_snapshot = "03-2222 3333"
    document.recipient_address_snapshot = f"{MARKER} Level 8, Menara Lama\nKuala Lumpur"
    document.recipient_email_snapshot = f"{MARKER}@zzt.test"
    document.quotation_purpose = purpose
    document.payment_terms = f"{MARKER} 30 days net"
    document.validity = f"{MARKER} 60 days"
    document.terms_html = terms
    db.flush()
    scope = qdocs.add_scope(
        db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
    )
    product = _product(db, env["category"].id, env["uom"], description=f"{MARKER} WC")
    quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=owner,
        payload={"product_id": product.id, "unit_price": "250.00", "quantity": 4},
    )
    return document


def _force_layout_1(db, record):
    """An issue that existed before release. Raw SQL so it fails now (no column) rather than
    silently setting a plain python attribute."""
    from app.models.projects import ProjectQuotationIssue

    table = ProjectQuotationIssue.__tablename__
    db.flush()
    db.execute(text(f"update {table} set layout_version = 1 where id = :i"), {"i": str(record.id)})
    db.expire_all()


# ------------------------------------------------------------------ 1. clean_terms_html


def _clean(raw):
    from app.services.quotation_cover_service import clean_terms_html

    return clean_terms_html(raw)


def test_clean_terms_keeps_the_allowed_tags_and_maps_b_and_i():
    out = _clean("<p><b>bold</b> <i>ital</i> <u>under</u> <strong>s</strong> <em>e</em></p>")
    assert "<strong>bold</strong>" in out
    assert "<em>ital</em>" in out
    assert "<u>under</u>" in out
    assert "<b>" not in out and "<i>" not in out


def test_clean_terms_drops_every_attribute():
    out = _clean('<p style="color:red" class="x" onclick="evil()">hi</p>')
    assert "hi" in out
    for banned in ("style", "class", "onclick", "evil"):
        assert banned not in out


def test_clean_terms_removes_script_style_and_iframe_with_their_content():
    out = _clean(
        "<p>keep</p><script>alert('xss')</script><style>p{color:red}</style>"
        "<iframe src='http://e.test'>frame body</iframe>"
    )
    assert "keep" in out
    for banned in ("alert", "xss", "color:red", "frame body", "<script", "<style", "<iframe"):
        assert banned not in out


def test_clean_terms_unwraps_other_tags_keeping_their_text():
    out = _clean('<p><a href="http://e.test">link text</a> <span>span text</span></p>')
    assert "link text" in out and "span text" in out
    assert "<a" not in out and "href" not in out and "<span" not in out


def test_clean_terms_escapes_text():
    out = _clean("<p>a &lt;b&gt; &amp; c</p>")
    assert "&lt;b&gt;" in out
    assert "&amp;" in out
    assert "<b>" not in out


def test_clean_terms_balances_unclosed_tags():
    out = _clean("<p><strong>never closed")
    assert out.count("<p>") == out.count("</p>") >= 1
    assert out.count("<strong>") == out.count("</strong>") == 1
    assert "never closed" in out


def test_clean_terms_empty_paragraph_keeps_its_gap_as_nbsp():
    out = _clean("<p>one</p><p></p><p>two</p>")
    assert "<p>&nbsp;</p>" in out
    assert out.index("one") < out.index("&nbsp;") < out.index("two")


def test_clean_terms_a_dash_line_stays_as_typed_with_no_list_item():
    out = _clean("<p>- dashed clause</p>")
    assert "- dashed clause" in out
    assert "<li>" not in out and "<ol" not in out


def test_clean_terms_nested_bullets_stay_nested():
    out = _clean("<ul><li>top<ul><li>inner</li></ul></li></ul>")
    assert out.count("<ul>") == 2 and out.count("</ul>") == 2
    assert out.index("top") < out.index("<ul>", out.index("top")) < out.index("inner")


def test_clean_terms_a_heading_is_never_wrapped_in_a_list():
    out = _clean("<h2>Payment</h2><p><strong>Heading</strong></p><ol><li>one</li></ol>")
    assert "Payment" in out and "Heading" in out
    assert not re.search(r"<li>[^<]*(<strong>)?\s*Heading", out)
    assert not re.search(r"<li>[^<]*Payment", out)
    assert out.count("<ol>") == 1
    assert out.index("Heading") < out.index("<ol>")


def test_clean_terms_none_and_blank_are_empty():
    assert _clean(None) == ""
    assert _clean("") == ""


# ------------------------------------------------------------------ 2. layout_version


def test_an_issue_built_directly_is_layout_1_and_issue_stamps_layout_2():
    from datetime import datetime

    from app.models.projects import ProjectQuotationIssue

    with blank_session() as db:
        env = _setup(db)
        document = _full_document(db, env)
        direct = ProjectQuotationIssue(
            company_id=document.company_id,
            document_id=document.id,
            issue_no=99,
            our_ref_text="direct",
            issued_at=datetime.utcnow(),
            grand_total=0,
        )
        db.add(direct)
        db.flush()
        db.refresh(direct)
        assert direct.layout_version == 1

        record = _issue(db, document, env["owner"])
        db.refresh(record)
        assert record.layout_version == 2


def test_cover_layout_constant_is_2():
    from app.services.quotation_cover_service import COVER_LAYOUT

    assert COVER_LAYOUT == 2


# ------------------------------------------------------------------ cover_rows (service)


def test_cover_rows_in_uac_order_with_reference_and_cleaned_terms():
    from app.services.quotation_cover_service import cover_rows

    with blank_session() as db:
        env = _setup(db)
        document = _full_document(db, env)
        record = _issue(db, document, env["owner"])
        rows = cover_rows(db, document, record)

        assert [r["key"] for r in rows] == KEYS
        assert [r["label"] for r in rows] == LABELS
        by = {r["key"]: r for r in rows}
        assert by["reference"]["text"] == (
            f"{document.document_no}-R{record.issue_no} {env['project'].title}"
        )
        assert by["attn"]["text"] == f"{MARKER} Kelly"
        assert by["company"]["text"] == f"{MARKER} Nadi Cergas Sdn Bhd"
        assert by["contact"]["text"] == "03-2222 3333"
        assert "Menara Lama" in by["address"]["text"] and "\n" in by["address"]["text"]
        assert by["email"]["text"] == f"{MARKER}@zzt.test"
        assert by["payment_terms"]["text"] == f"{MARKER} 30 days net"
        assert by["validity"]["text"] == f"{MARKER} 60 days"
        assert by["prepared_by"]["text"] == "zzt-qpdf Baser Ramli"
        assert "text" not in by["terms"] or by["terms"].get("text") is None
        assert by["terms"]["html"].count("<ul>") == 2
        assert "<ol" not in by["terms"]["html"]


def test_cover_rows_omit_rows_with_no_value():
    from app.services.quotation_cover_service import cover_rows

    with blank_session() as db:
        env = _setup(db)
        document = _full_document(db, env, purpose=None, terms=None)
        document.validity = None
        record = _issue(db, document, env["owner"])
        keys = [r["key"] for r in cover_rows(db, document, record)]
        assert "purpose" not in keys
        assert "terms" not in keys
        assert "validity" not in keys
        assert "reference" in keys and "payment_terms" in keys


# ------------------------------------------------------------------ 3. PDF layout 2


def _html_of(db, env, **doc_kwargs):
    from app.services import project_quotation_pdf_service as qpdf

    document = _full_document(db, env, **doc_kwargs)
    record = _issue(db, document, env["owner"])
    return document, record, qpdf.build_issue_html(db, record)


def test_pdf_layout_2_has_a_portrait_cover_section_before_the_first_scope():
    with blank_session() as db:
        env = _setup(db)
        _doc, _rec, html = _html_of(db, env)
        assert re.search(r"@page\s+cover\s*\{[^}]*A4 portrait", html)
        assert re.search(r"page:\s*cover", html)
        assert html.index("page: cover") < html.index(f"{MARKER} Townhouse")


def test_pdf_layout_2_rows_in_order_with_uppercase_labels_and_no_fax():
    with blank_session() as db:
        env = _setup(db)
        _doc, _rec, html = _html_of(db, env)
        labels = [
            "REFERENCE NO.:",
            "DATE:",
            "ATTN:",
            "COMPANY:",
            "CONTACT:",
            "ADD:",
            "EMAIL:",
            "QUOTATION PURPOSE:",
            "TERMS &amp; CONDITIONS:",
            "PAYMENT TERMS:",
            "VALIDITY:",
            "PREPARED BY:",
        ]
        positions = []
        for label in labels:
            assert label in html, label
            positions.append(html.index(label))
        assert positions == sorted(positions)
        assert "FAX" not in html.upper()


def test_pdf_layout_2_reference_on_cover_and_in_the_price_page_ref():
    with blank_session() as db:
        env = _setup(db)
        document, record, html = _html_of(db, env)
        ref = f"{document.document_no}-R{record.issue_no} {env['project'].title}"
        assert html.count(ref) >= 2
        assert re.search(r"Quotation No\.</th>\s*<td>" + re.escape(ref), html)


def test_pdf_layout_2_values_prepared_by_email_contact_and_letterhead():
    with blank_session() as db:
        env = _setup(db)
        _doc, _rec, html = _html_of(db, env)
        assert f"{MARKER}@zzt.test" in html
        assert "03-2222 3333" in html
        cover = html[: html.index(f"{MARKER} Townhouse")]
        assert re.search(r"PREPARED BY:.*?Baser Ramli", cover, re.S)
        assert "QUOTATION" in cover
        sender = db.execute(text("select name from companies where code = 'SRT'")).scalar()
        assert html.count(sender) >= 2  # letterhead on the cover and on the price page


def test_pdf_layout_2_empty_purpose_row_is_omitted_and_script_is_escaped():
    with blank_session() as db:
        env = _setup(db)
        _d, _r, html = _html_of(db, env, purpose=None)
        assert "QUOTATION PURPOSE" not in html
    with blank_session() as db:
        env = _setup(db)
        _d, _r, html = _html_of(db, env, purpose="<script>alert(1)</script>")
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html


def test_pdf_layout_2_terms_print_on_the_cover_only_and_keep_their_structure():
    with blank_session() as db:
        env = _setup(db)
        _d, _r, html = _html_of(db, env)
        assert f"{MARKER} bullet nested" in html
        assert html.count(f"{MARKER} closing line") == 1
        cover_end = html.index(f"{MARKER} Townhouse")
        assert html.index(f"{MARKER} closing line") < cover_end
        after_total = html.split("TOTAL AMOUNT", 1)[1]
        assert f"{MARKER} closing line" not in after_total
        assert f"{MARKER} dash line" not in after_total
        # the dash line prints as typed, with no list number or bullet before it
        assert not re.search(r"<li>\s*-\s*" + MARKER + " dash line", html)
        assert f"- {MARKER} dash line" in html
        assert "<p>&nbsp;</p>" in html


# ------------------------------------------------------------------ 4. PDF layout 1


def test_pdf_layout_1_is_exactly_the_old_layout():
    from app.models.projects import ProjectQuotationIssue
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        document = _full_document(db, env, terms=f"<ol><li>{MARKER} clause one</li></ol>")
        record = _issue(db, document, env["owner"])
        _force_layout_1(db, record)
        record = db.query(ProjectQuotationIssue).filter_by(id=record.id).one()
        assert record.layout_version == 1

        html = qpdf.build_issue_html(db, record)
        assert "@page cover" not in html and "page: cover" not in html
        assert "REFERENCE NO.:" not in html
        assert f"{document.document_no}-R1 {env['project'].title}" not in html
        assert re.search(
            r"Quotation No\.</th>\s*<td>" + re.escape(f"{document.document_no}-R1") + "</td>", html
        )
        after_total = html.split("TOTAL AMOUNT", 1)[1]
        assert "<ol>" in after_total and f"{MARKER} clause one" in after_total


# ------------------------------------------------------------------ 5. countersign route


def _sign_page(db, env, *, layout=2, **doc_kwargs):
    from app.services import project_quotation_document_service as qdocs

    from .test_project_quotation_signing import _public_client

    document = _full_document(db, env, **doc_kwargs)
    record = _issue(db, document, env["owner"])
    if layout == 1:
        _force_layout_1(db, record)
    token = qdocs.issue_sign_link(db, record=record)
    db.commit()
    client, app = _public_client(db)
    try:
        body = client.get(f"/api/v1/public/quotation-sign/{token}").json()
    finally:
        app.dependency_overrides.clear()
    return document, record, body


def test_countersign_layout_2_returns_cover_rows_in_order_with_the_pdf_reference():
    with blank_session() as db:
        env = _setup(db)
        document, record, body = _sign_page(db, env)
        rows = body["cover_rows"]
        assert [r["key"] for r in rows] == KEYS
        ref = f"{document.document_no}-R{record.issue_no} {env['project'].title}"
        assert rows[0]["text"] == ref
        assert body["our_ref"] == ref
        terms = next(r for r in rows if r["key"] == "terms")
        assert terms["html"].count("<ul>") == 2
        assert "<script" not in terms["html"]


def test_countersign_layout_2_omits_empty_rows():
    with blank_session() as db:
        env = _setup(db)
        _d, _r, body = _sign_page(db, env, purpose=None)
        assert "purpose" not in [r["key"] for r in body["cover_rows"]]


def test_countersign_layout_1_has_null_cover_rows_and_the_old_ref():
    with blank_session() as db:
        env = _setup(db)
        document, record, body = _sign_page(db, env, layout=1)
        assert "cover_rows" in body and body["cover_rows"] is None
        assert body["our_ref"] == f"{document.document_no}-R{record.issue_no}"
