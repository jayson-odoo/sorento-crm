"""QUOTE-COVER-FIELDS red tests: rows pick a SOURCE field, rows sit in SECTIONS with any number of
columns, Reference No. prints the document number only, Total Pages counts the PDF.

Owner rulings 10 Nov 2026 (plan ``documentation/plans/projects/PLAN-quote-cover-fields-10nov.md``).
Postgres only via ``blank_session``; chains seeded by the shared fixtures; every row carries a
``zzt-`` marker.
"""
from __future__ import annotations

import pytest

from ._pg_fixture import blank_session
from .test_project_quotation_cover_page import MARKER, _full_document
from .test_project_quotation_pdf import _issue, _setup
from .test_project_quotation_template_routes import BASE as TEMPLATES, api  # noqa: F401

LEGACY_KEYS = [
    "reference", "date", "attn", "company", "contact", "address", "email",
    "purpose", "terms", "payment_terms", "validity", "prepared_by",
]
LEGACY_LABELS = [
    "Reference No.", "Date", "Attn", "Company", "Contact", "Add", "Email",
    "Quotation Purpose", "Terms & Conditions", "Payment Terms", "Validity", "Prepared By",
]
DEFAULT_SOURCES = [
    "document_no", "date", "attn", "to_name", "to_tel", "to_address", "to_email",
    "terms", "payment_terms", "validity", "salesperson_name",
]


def legacy_design():
    return {
        "show_letterhead": True,
        "title": "QUOTATION",
        "rows": [
            {"key": k, "shown": True, "label": label} for k, label in zip(LEGACY_KEYS, LEGACY_LABELS)
        ],
        "closing_html": "",
    }


def row(source, label="", shown=True, column=0):
    return {"source": source, "label": label, "shown": shown, "column": column}


def sheet_design():
    """The sales team's cover sheet: a 2-column Propose to block, a title band, numbered terms,
    the signature block and a footer."""
    return {
        "show_letterhead": True,
        "title": "QUOTATION",
        "closing_html": "",
        "sections": [
            {
                "style": "fields",
                "label": "Propose to:",
                "columns": 2,
                "rows": [
                    row("to_name", "Company"),
                    row("to_address", "Address"),
                    row("to_tel", "Tel"),
                    row("to_fax", "Fax"),
                    row("attn", "Attention"),
                    row("to_email", "Email"),
                    row("document_no", "Reference No", column=1),
                    row("total_pages", "Total Pages", column=1),
                    row("date", "Date", column=1),
                    row("salesperson_name", "Sales", column=1),
                    row("salesperson_email", "Email", column=1),
                    row("salesperson_mobile", "Mobile", column=1),
                ],
            },
            {"style": "title", "label": "Project Title:", "columns": 1,
             "rows": [row("project_title")]},
            {
                "style": "numbered",
                "label": "Term & Condition:",
                "columns": 1,
                "rows": [
                    row("terms", "PRICE BASIS"),
                    row("payment_terms", "TERMS OF PAYMENT"),
                    row("validity", "REMARKS"),
                ],
            },
            {
                "style": "signature",
                "label": "Prepared by,",
                "columns": 1,
                "rows": [row("prepared_by_name", "Name"), row("prepared_by_phone", "Phone No")],
            },
            {
                "style": "footer",
                "label": "",
                "columns": 1,
                "rows": [
                    row("company_name"),
                    row("company_address"),
                    row("company_tel", "Tel"),
                    row("company_fax", "Fax"),
                ],
            },
        ],
    }


# ------------------------------------------------------------------ the source registry


def test_sources_list_every_field_with_caption_group_and_default_label():
    from app.services.quotation_cover_service import SOURCES, serialize_sources

    keys = [s["key"] for s in serialize_sources()]
    assert keys == list(SOURCES)
    for key in (
        "document_no", "date", "project_title", "total_pages", "to_name", "to_address",
        "to_tel", "to_fax", "to_email", "attn", "salesperson_name", "salesperson_email",
        "salesperson_mobile", "prepared_by_name", "prepared_by_phone", "terms",
        "payment_terms", "validity", "company_name", "company_address", "company_tel",
        "company_fax",
    ):
        assert key in keys, key
    for entry in serialize_sources():
        assert entry["caption"] and entry["group"]
        assert "default_label" in entry


def test_sources_drop_quotation_purpose_and_offer_no_sale_admin():
    from app.services.quotation_cover_service import SOURCES

    assert "purpose" not in SOURCES and "quotation_purpose" not in SOURCES
    assert not any("admin" in key for key in SOURCES)
    assert "project_short_name" not in SOURCES


def test_sources_route_serves_the_list_gated_like_the_list(api):
    from app.services.quotation_cover_service import serialize_sources

    from .test_quote_cover_design_preview import without

    client, *_ = api
    res = client.get(f"{TEMPLATES}/cover-sources")
    assert res.status_code == 200, res.text
    assert res.json()["data"] == serialize_sources()
    with without("projects.types.view"):
        assert client.get(f"{TEMPLATES}/cover-sources").status_code == 403


def test_cover_default_route_serves_the_sections_default(api):
    from app.services.quotation_cover_service import default_design

    client, *_ = api
    body = client.get(f"{TEMPLATES}/cover-default").json()
    assert body == default_design()


# ------------------------------------------------------------------ the design


def test_default_design_is_todays_rows_in_one_single_column_section_then_the_title_band():
    from app.services.quotation_cover_service import default_design

    d = default_design()
    assert d["show_letterhead"] is True and d["title"] == "QUOTATION" and d["closing_html"] == ""
    assert len(d["sections"]) == 2
    assert d["sections"][1] == {
        "style": "title",
        "label": "Project Title:",
        "columns": 1,
        "rows": [{"source": "project_title", "label": "", "shown": True, "column": 0}],
    }
    section = d["sections"][0]
    assert section["style"] == "fields" and section["columns"] == 1 and section["label"] == ""
    assert [r["source"] for r in section["rows"]] == DEFAULT_SOURCES
    labels = {r["source"]: r["label"] for r in section["rows"]}
    assert labels["document_no"] == "Reference No."
    assert labels["to_tel"] == "Contact" and labels["to_address"] == "Add"
    assert labels["salesperson_name"] == "Prepared By"
    assert all(r["shown"] and r["column"] == 0 for r in section["rows"])


def test_validate_accepts_the_sheet_with_any_column_count_and_a_source_twice():
    from app.services.quotation_cover_service import validate_design

    d = sheet_design()
    d["sections"][0]["columns"] = 4
    d["sections"][0]["rows"].append(row("salesperson_email", "Email again", column=3))
    clean = validate_design(d)
    assert clean["sections"][0]["columns"] == 4
    assert [s["style"] for s in clean["sections"]] == [
        "fields", "title", "numbered", "signature", "footer",
    ]
    sources = [r["source"] for r in clean["sections"][0]["rows"]]
    assert sources.count("salesperson_email") == 2


@pytest.mark.parametrize(
    "mutate,needle",
    [
        (lambda d: d["sections"][0]["rows"].append(row("purpose")), "Unknown"),
        (lambda d: d["sections"][0]["rows"].append(row("to_name", column=2)), "column"),
        (lambda d: d["sections"][0].update(columns=0), "column"),
        (lambda d: d["sections"][0].update(columns=7), "column"),
        (lambda d: d["sections"][0].update(style="poster"), "style"),
        (lambda d: d["sections"][0].update(label="x" * 61), "60"),
        (lambda d: d["sections"][0]["rows"][0].update(label="x" * 61), "60"),
        (lambda d: d["sections"][0]["rows"][0].update(shown="yes"), "tick"),
        (lambda d: d.update(sections=[]), "section"),
        (lambda d: d.update(sections=[dict(d["sections"][1]) for _ in range(13)]), "section"),
    ],
)
def test_validate_refuses_bad_designs_with_a_422(mutate, needle):
    from app.services.error_handler import AppException
    from app.services.quotation_cover_service import validate_design

    d = sheet_design()
    mutate(d)
    with pytest.raises(AppException) as raised:
        validate_design(d)
    assert raised.value.status_code == 422
    assert needle.lower() in str(raised.value.message).lower()


def test_a_legacy_design_is_read_as_one_section_with_purpose_dropped():
    from app.services.quotation_cover_service import normalize_design, validate_design

    legacy = legacy_design()
    legacy["rows"][1]["shown"] = False
    legacy["rows"][0]["label"] = "Our Ref"
    legacy["rows"][2]["label"] = "  "  # the old cover printed the default label for a blank one
    for clean in (normalize_design(legacy), validate_design(legacy)):
        assert "rows" not in clean
        section, title = clean["sections"]
        assert title["style"] == "title" and title["rows"][0]["source"] == "project_title"
        assert section["rows"][2]["label"] == "Attn"
        assert section["style"] == "fields" and section["columns"] == 1
        sources = [r["source"] for r in section["rows"]]
        assert sources == [
            "document_no", "date", "attn", "to_name", "to_tel", "to_address", "to_email",
            "terms", "payment_terms", "validity", "salesperson_name",
        ]
        assert section["rows"][0]["label"] == "Our Ref"
        assert section["rows"][1]["shown"] is False


# ------------------------------------------------------------------ values


def _document(db, env, **over):
    document = _full_document(db, env)
    document.signatory_name = f"{MARKER} Prepared Person"
    document.signatory_phone = "012-000 0001"
    document.recipient_fax_snapshot = "03-0000 0001"
    for key, value in over.items():
        setattr(document, key, value)
    db.flush()
    return document


def _system_settings(db, **values):
    from app.models.user import SystemSetting

    settings = db.query(SystemSetting).order_by(SystemSetting.id).first()
    if settings is None:
        settings = SystemSetting(name=f"{MARKER} Sorento")
        db.add(settings)
    for key, value in values.items():
        setattr(settings, key, value)
    db.flush()
    return settings


def test_values_reference_is_the_number_only_and_the_title_is_its_own_source():
    from app.services.project_quotation_document_service import quotation_no
    from app.services.quotation_cover_service import source_values

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env, subject_title=f"{MARKER} SERI MUTIARA RESIDENCES")
        record = _issue(db, document, env["owner"])
        values = source_values(db, document, record)
        assert values["document_no"] == quotation_no(
            document.document_no, record.issue_no, record.revision_label
        )
        assert env["project"].title not in values["document_no"]
        assert values["project_title"] == f"{MARKER} SERI MUTIARA RESIDENCES"


def test_values_salesperson_prepared_by_fax_and_company_footer():
    from app.models.user import User
    from app.services.quotation_cover_service import source_values

    with blank_session() as db:
        env = _setup(db)
        owner = db.query(User).filter(User.id == env["owner"]).first()
        owner.email = f"{MARKER}-owner@zzt.test"
        owner.contact_number = "+60 12-000 0099"
        _system_settings(
            db, address=f"{MARKER} Lot 1, Jalan Satu", support_phone="+60 17-000 0501", fax="+60 17-000 0502"
        )
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        values = source_values(db, document, record)
        assert values["salesperson_name"] == owner.name
        assert values["salesperson_email"] == f"{MARKER}-owner@zzt.test"
        assert values["salesperson_mobile"] == "+60 12-000 0099"
        assert values["prepared_by_name"] == f"{MARKER} Prepared Person"
        assert values["prepared_by_phone"] == "012-000 0001"
        assert values["to_fax"] == "03-0000 0001"
        assert values["company_address"] == f"{MARKER} Lot 1, Jalan Satu"
        assert values["company_tel"] == "+60 17-000 0501"
        assert values["company_fax"] == "+60 17-000 0502"
        assert values["company_name"]
        assert values["total_pages"] == ""  # only the PDF knows its pages


# ------------------------------------------------------------------ sections payload


def test_sections_place_rows_in_their_columns_and_drop_empty_and_unticked_rows():
    from app.services.quotation_cover_service import sections_for_design, validate_design

    d = sheet_design()
    d["sections"][0]["rows"][4]["shown"] = False  # attn
    values = {
        "to_name": "ACME", "to_address": "", "to_tel": "03-1", "attn": "Ms A",
        "document_no": "PRJQ-1-A", "date": "10/11/2026", "terms": "<p>Prices in RM</p>",
        "project_title": "BIG PROJECT",
    }
    sections = sections_for_design(values, validate_design(d))
    first = sections[0]
    assert first["style"] == "fields" and first["label"] == "Propose to:" and first["columns"] == 2
    assert [[c["source"] for c in col] for col in first["cells"]] == [
        ["to_name", "to_tel"],
        ["document_no", "date"],
    ]
    assert first["cells"][0][0] == {"source": "to_name", "label": "Company", "text": "ACME"}
    styles = [s["style"] for s in sections]
    # no signature or footer values: those sections drop out entirely
    assert styles == ["fields", "title", "numbered"]
    terms = sections[2]["cells"][0][0]
    assert terms["html"] == "<p>Prices in RM</p>" and "text" not in terms


def test_a_section_keeps_its_column_count_when_a_column_is_empty():
    from app.services.quotation_cover_service import sections_for_design, validate_design

    sections = sections_for_design({"to_name": "ACME"}, validate_design(sheet_design()))
    assert sections[0]["columns"] == 2
    assert sections[0]["cells"] == [[{"source": "to_name", "label": "Company", "text": "ACME"}], []]


# ------------------------------------------------------------------ issue + PDF + sign page


def _activate(db, env, design):
    from app.services import project_quotation_template_service as templates

    template = templates.create_template(
        db,
        company_id=env["project"].company_id,
        actor_user_id=env["owner"],
        payload={"kind": "cover_page", "name": f"{MARKER} sheet", "body_html": "", "design": design},
    )
    templates.activate_template(db, template=template)
    db.flush()
    return template


def test_issue_freezes_a_sections_design_and_stamps_layout_4():
    from app.services.quotation_cover_service import COVER_LAYOUT_SECTIONS

    with blank_session() as db:
        env = _setup(db)
        _activate(db, env, sheet_design())
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        db.refresh(record)
        assert COVER_LAYOUT_SECTIONS == 4
        assert record.layout_version == 4
        assert record.cover_design["sections"][0]["columns"] == 2


def test_issue_under_a_stored_legacy_template_freezes_it_normalized():
    from app.models.projects import QuotationTemplate as ProjectQuotationTemplate

    with blank_session() as db:
        env = _setup(db)
        template = _activate(db, env, sheet_design())
        # A design saved before this lane: still the 12-row shape in the database.
        db.query(ProjectQuotationTemplate).filter(ProjectQuotationTemplate.id == template.id).update(
            {"design": legacy_design()}
        )
        db.flush()
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        db.refresh(record)
        assert record.layout_version == 4
        sources = [r["source"] for r in record.cover_design["sections"][0]["rows"]]
        assert "purpose" not in sources and sources[0] == "document_no"


def test_pdf_layout_4_prints_bands_columns_title_numbered_terms_signature_and_footer():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        _system_settings(db, fax="03-1111 0001")
        _activate(db, env, sheet_design())
        document = _document(db, env, subject_title=f"{MARKER} THE BIG PROJECT TITLE")
        record = _issue(db, document, env["owner"])
        html = qpdf.build_issue_html(db, record, total_pages="1+3")
        cover = html.split('<section class="cover', 1)[1].split("</section>", 1)[0]
        assert "Propose to:" in cover and "Project Title:" in cover and "Term &amp; Condition:" in cover
        assert cover.count('class="cover-col"') >= 3  # 2 columns + the single-column sections
        assert f"{MARKER} THE BIG PROJECT TITLE" in cover
        assert "1+3" in cover
        assert "<ol" in cover and "PRICE BASIS" in cover
        assert "Prepared by," in cover and f"{MARKER} Prepared Person" in cover
        assert "03-0000 0001" in cover and "03-1111 0001" in cover
        # Reference No. is the number only
        number = record.our_ref_text
        assert number in cover
        assert f"{number} {env['project'].title}" not in html


def test_pdf_total_pages_counts_the_rendered_pdf(monkeypatch):
    """One HTML build with a placeholder laid out like the real value, then the count fills it."""
    pytest.importorskip("weasyprint")
    from app.services import project_quotation_pdf_service as qpdf

    seen, filled = [], []
    real_build, real_fill = qpdf.build_issue_html, qpdf._fill_total_pages

    def spy(db, issue, total_pages=None):
        seen.append(total_pages)
        return real_build(db, issue, total_pages=total_pages)

    def fill_spy(html, pages):
        assert qpdf.TOTAL_PAGES_MARK in html  # the row was laid out in the counting pass
        out = real_fill(html, pages)
        filled.append((pages, out))
        return out

    with blank_session() as db:
        env = _setup(db)
        _activate(db, env, sheet_design())
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        monkeypatch.setattr(qpdf, "build_issue_html", spy)
        monkeypatch.setattr(qpdf, "_fill_total_pages", fill_spy)
        try:
            pdf, _name = qpdf.render_issue_pdf(db, record)
        except qpdf.PDFRenderingUnavailable:
            pytest.skip("WeasyPrint native libraries missing")
        assert pdf.startswith(b"%PDF")
        assert seen == [qpdf.TOTAL_PAGES_MARK]
        ((pages, html),) = filled
        assert pages >= 2
        assert f"1+{pages - 1}" in html and qpdf.TOTAL_PAGES_MARK not in html


def test_pdf_without_a_total_pages_row_renders_once(monkeypatch):
    pytest.importorskip("weasyprint")
    from app.services import project_quotation_pdf_service as qpdf

    seen = []
    real = qpdf.build_issue_html

    def spy(db, issue, total_pages=None):
        seen.append(total_pages)
        return real(db, issue, total_pages=total_pages)

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        monkeypatch.setattr(qpdf, "build_issue_html", spy)
        try:
            qpdf.render_issue_pdf(db, record)
        except qpdf.PDFRenderingUnavailable:
            pytest.skip("WeasyPrint native libraries missing")
        assert seen == [None]


def test_sign_page_layout_4_returns_sections_and_the_number_only_reference():
    from app.services import project_quotation_document_service as qdocs

    from .test_project_quotation_signing import _public_client

    with blank_session() as db:
        env = _setup(db)
        _activate(db, env, sheet_design())
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        token = qdocs.issue_sign_link(db, record=record)
        db.commit()
        client, app = _public_client(db)
        try:
            body = client.get(f"/api/v1/public/quotation-sign/{token}").json()
        finally:
            app.dependency_overrides.clear()
        assert body["our_ref"] == record.our_ref_text
        sections = body["cover_sections"]
        assert [s["style"] for s in sections][:3] == ["fields", "title", "numbered"]
        right = [c["source"] for c in sections[0]["cells"][1]]
        assert "document_no" in right and "total_pages" not in right
        assert body["cover_rows"]  # flattened, so "has a cover" still reads true


def test_a_sent_legacy_layout_3_revision_still_prints_as_it_went_out():
    from app.models.projects import ProjectQuotationIssue
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        db.query(ProjectQuotationIssue).filter(ProjectQuotationIssue.id == record.id).update(
            {"layout_version": 3, "cover_design": legacy_design()}
        )
        db.flush()
        db.expire_all()
        record = db.query(ProjectQuotationIssue).filter(ProjectQuotationIssue.id == record.id).one()
        html = qpdf.build_issue_html(db, record)
        assert "QUOTATION PURPOSE:" in html or "PROPOSAL PURPOSE:" in html
        assert 'class="cover-col"' not in html


def test_a_new_revision_and_the_draft_preview_never_print_a_stored_purpose():
    """PROPOSAL-FORM-COLLAPSE PFC-5 holds for what is issued today: a document that still stores a
    Quotation Purpose from before the field left the form prints none on a new (layout 4) revision,
    its sign page or the draft preview. Only revisions that already went out print it, as they did."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_pdf_service as qpdf

    from .test_project_quotation_signing import _public_client

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        stored = document.quotation_purpose
        assert stored  # still stored
        preview = qdocs.preview_cover(db, project=env["project"], payload={"document_id": document.id})
        record = _issue(db, document, env["owner"])
        db.refresh(record)
        assert record.layout_version == 4
        html = qpdf.build_issue_html(db, record)
        token = qdocs.issue_sign_link(db, record=record)
        db.commit()
        client, app = _public_client(db)
        try:
            body = client.get(f"/api/v1/public/quotation-sign/{token}").json()
        finally:
            app.dependency_overrides.clear()
        for printed in (html, repr(preview), repr(body)):
            assert stored not in printed
            assert "QUOTATION PURPOSE" not in printed.upper() and "PROPOSAL PURPOSE" not in printed.upper()


def test_designer_preview_returns_sections_with_sample_values():
    from app.services.quotation_cover_service import preview_design

    with blank_session() as db:
        payload = preview_design(db, company_id=None, design=sheet_design(), body_html="")
        sections = payload["cover_sections"]
        assert [s["style"] for s in sections] == [
            "fields", "title", "numbered", "signature", "footer",
        ]
        right = {c["source"]: c["text"] for c in sections[0]["cells"][1]}
        assert right["total_pages"] == "1+3"
        assert payload["cover_rows"]


def test_pdf_layout_4_escapes_every_label_and_value_and_cleans_the_terms():
    from app.services import project_quotation_pdf_service as qpdf

    evil = "<b>x</b>&"
    d = sheet_design()
    for section in d["sections"]:
        section["label"] = f"{section['style']} {evil}"
        for item in section["rows"]:
            item["label"] = f"{item['source']} {evil}"
    with blank_session() as db:
        env = _setup(db)
        _system_settings(db, fax=f"03 {evil}")
        _activate(db, env, d)
        document = _document(
            db,
            env,
            recipient_name_snapshot=f"{MARKER} {evil}",
            subject_title=f"{MARKER} title {evil}",
            signatory_name=f"{MARKER} sig {evil}",
            terms_html=f"<p>{MARKER} ok</p><script>alert(1)</script>",
        )
        record = _issue(db, document, env["owner"])
        html = qpdf.build_issue_html(db, record, total_pages="1+3")
        cover = html.split('<section class="cover', 1)[1].split("</section>", 1)[0]
        assert "<b>x</b>" not in cover
        safe = "&lt;b&gt;x&lt;/b&gt;&amp;"
        for style in ("fields", "title", "numbered", "signature"):
            assert f"{style} {safe}" in cover, style
        for source in ("to_name", "prepared_by_name", "company_fax"):
            assert f"{source} {safe}" in cover, source
        assert "TERMS &lt;B&gt;X&lt;/B&gt;&amp;" in cover  # numbered labels print upper case
        assert f"{MARKER} {safe}" in cover and f"{MARKER} title {safe}" in cover
        assert f"{MARKER} sig {safe}" in cover and f"03 {safe}" in cover
        assert "<script" not in cover and f"{MARKER} ok" in cover


def test_pdf_terms_html_never_follows_a_bare_colon():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        _activate(db, env, sheet_design())
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        cover = qpdf.build_issue_html(db, record).split('<section class="cover', 1)[1]
        assert "<strong>PRICE BASIS:</strong><p>" in cover
        assert ": <p>" not in cover


def test_pdf_default_design_prints_the_terms_label_beside_the_terms():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        cover = qpdf.build_issue_html(db, record).split('<section class="cover', 1)[1]
        assert "<th>Terms &amp; Conditions:</th><td><p>" in cover
        assert "<td>: <p>" not in cover


def test_draft_preview_uses_the_typed_title_and_signatory_and_the_number_only_reference():
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        env = _setup(db)
        _activate(db, env, sheet_design())
        document = _document(db, env)
        out = qdocs.preview_cover(
            db,
            project=env["project"],
            payload={
                "document_id": document.id,
                "subject_title": f"{MARKER} typed title",
                "signatory_name": f"{MARKER} typed signer",
            },
        )
        cells = {
            c["source"]: c.get("text")
            for s in out["cover_sections"]
            for col in s["cells"]
            for c in col
        }
        assert cells["project_title"] == f"{MARKER} typed title"
        assert cells["prepared_by_name"] == f"{MARKER} typed signer"
        assert cells["prepared_by_phone"] == "012-000 0001"  # saved, not typed
        assert cells["document_no"].startswith(document.document_no)
        assert env["project"].title not in cells["document_no"]


def test_pdf_section_classes_never_reuse_the_page_title_class():
    """Browser pass 10 Nov: a title-style section got class "cover-title" and printed its band at
    the page title's 20px. Sections carry "cover-sec-<style>"."""
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        _activate(db, env, sheet_design())
        document = _document(db, env)
        record = _issue(db, document, env["owner"])
        cover = qpdf.build_issue_html(db, record).split('<section class="cover', 1)[1]
        assert 'class="cover-sec cover-sec-title"' in cover
        assert cover.count('class="cover-title') == 1  # the page title only
