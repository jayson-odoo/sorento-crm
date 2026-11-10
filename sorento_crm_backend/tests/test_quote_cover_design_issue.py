"""QUOTE-COVER-DESIGN red tests, part 2: send (layout 3 stamp + copy), PDF html and the
countersign payload for layout 3. UAC C1-C4, D1, E1. Postgres only via ``blank_session``."""
from __future__ import annotations

import re

from sqlalchemy import text

from ._pg_fixture import blank_session
from .test_project_quotation_cover_page import (  # noqa: F401  (helpers, not tests)
    KEYS,
    LABELS,
    PRINTED_KEYS,
    PRINTED_LABELS,
    MARKER as COVER_MARKER,
    TERMS,
    _force_layout_3,
    _full_document,
)
from .test_project_quotation_pdf import _issue, _setup

MARKER = COVER_MARKER  # the cover helpers' own marker keeps the seeded chain recognisable
INTRO = f"<p>{MARKER} intro line</p>"
CLOSING = f"<p>{MARKER} closing words</p>"


def make_design(**over):
    d = {
        "show_letterhead": True,
        "title": "QUOTATION",
        "rows": [{"key": k, "shown": True, "label": label} for k, label in zip(KEYS, LABELS)],
        "closing_html": "",
    }
    d.update(over)
    return d


def seed_design(db, env, d, *, body="", name=None, active=True):
    from app.services import project_quotation_template_service as templates

    return templates.create_template(
        db,
        company_id=env["company_id"],
        payload={
            "kind": "cover_page",
            "name": name or f"{MARKER} design {len(str(d))}",
            "body_html": body,
            "design": d,
            "is_active": active,
        },
    )


def prepared(db, env, d=None, *, terms=TERMS, kind="quotation"):
    """A document filled in, with intro and closing set, after any design is seeded."""
    if d is not None:
        seed_design(db, env, d)
    document = _full_document(db, env, terms=terms)
    document.cover_letter_html = INTRO
    document.cover_closing_html = CLOSING
    document.kind = kind
    db.flush()
    return document


def designed(**over):
    """Reordered, relabelled design with two rows hidden and a custom title."""
    d = make_design(title=f"{MARKER} OFFER", **over)
    by = {r["key"]: r for r in d["rows"]}
    order = ["prepared_by", "reference", "date", "company", "attn", "terms", "payment_terms",
             "validity", "purpose", "contact", "address", "email"]
    d["rows"] = [by[k] for k in order]
    by["reference"]["label"] = "Offer Number"
    by["company"]["label"] = "Sent To"
    by["email"]["shown"] = False
    by["contact"]["shown"] = False
    return d


def sign_body(db, record):
    from app.services import project_quotation_document_service as qdocs

    from .test_project_quotation_signing import _public_client

    token = qdocs.issue_sign_link(db, record=record)
    db.commit()
    client, app = _public_client(db)
    try:
        return client.get(f"/api/v1/public/quotation-sign/{token}").json()
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------------ send


def test_issue_stamps_layout_4_and_copies_the_active_design_and_closing():
    from app.services.quotation_cover_service import COVER_LAYOUT_SECTIONS, normalize_design

    d = designed(closing_html="<p>design closing</p>")
    with blank_session() as db:
        env = _setup(db)
        record = _issue(db, prepared(db, env, d), env["owner"])
        db.refresh(record)
        assert record.layout_version == COVER_LAYOUT_SECTIONS
        assert record.cover_design == normalize_design(d)
        assert MARKER in record.cover_closing_rendered and "closing words" in record.cover_closing_rendered


def test_issue_with_no_active_design_copies_the_default_design():
    from app.services.quotation_cover_service import COVER_LAYOUT_SECTIONS, default_design

    with blank_session() as db:
        env = _setup(db)
        record = _issue(db, prepared(db, env), env["owner"])
        db.refresh(record)
        assert record.layout_version == COVER_LAYOUT_SECTIONS
        assert record.cover_design == default_design()


def test_changing_or_activating_designs_afterwards_leaves_the_sent_revision_alone():
    from app.services import project_quotation_pdf_service as qpdf
    from app.services import project_quotation_template_service as templates

    d = designed()
    with blank_session() as db:
        env = _setup(db)
        tmpl = seed_design(db, env, d, name=f"{MARKER} first")
        document = _full_document(db, env)
        document.cover_letter_html = INTRO
        document.cover_closing_html = CLOSING
        record = _issue(db, document, env["owner"])
        html_before = qpdf.build_issue_html(db, record)
        tmpl_id, record_id = tmpl.id, record.id
        body_before = sign_body(db, record)
        # the sign route closes its session (#2126), so reload what was held before it
        tmpl = db.get(type(tmpl), tmpl_id)
        record = db.get(type(record), record_id)

        templates.update_template(db, template=tmpl, payload={"design": make_design(title="CHANGED TITLE")})
        other = seed_design(db, env, make_design(title="OTHER TITLE"), name=f"{MARKER} other", active=False)
        templates.activate_template(db, template=other)
        db.flush()
        db.expire_all()

        assert qpdf.build_issue_html(db, record) == html_before
        assert "CHANGED TITLE" not in html_before and "OTHER TITLE" not in html_before
        body_after = sign_body(db, record)
        assert body_after["cover_rows"] == body_before["cover_rows"]
        assert body_after["cover_title"] == f"{MARKER} OFFER"


# ------------------------------------------------------------------ PDF layout 3


def _html3(db, env, d, **kw):
    from app.services import project_quotation_pdf_service as qpdf

    record = _issue(db, prepared(db, env, d, **kw), env["owner"])
    _force_layout_3(db, record, d)  # guards sent layout 3 revisions (QUOTE-COVER-FIELDS)
    return record, qpdf.build_issue_html(db, record)


def test_pdf_layout_3_title_rows_order_labels_hidden_and_intro_closing_placement():
    with blank_session() as db:
        env = _setup(db)
        _record, html = _html3(db, env, designed())
        assert f"{MARKER} OFFER" in html
        for gone in ("EMAIL:", "CONTACT:", f"{MARKER}@zzt.test"):
            assert gone not in html, gone
        order = ["PREPARED BY:", "OFFER NUMBER:", "DATE:", "SENT TO:", "ATTN:", "TERMS &amp; CONDITIONS:",
                 "PAYMENT TERMS:", "VALIDITY:", "ADD:"]
        assert "PROPOSAL PURPOSE:" not in html
        positions = [html.index(label) for label in order]
        assert positions == sorted(positions)
        assert "REFERENCE NO.:" not in html and "COMPANY:" not in html
        intro, closing = html.index(f"{MARKER} intro line"), html.index(f"{MARKER} closing words")
        assert intro < positions[0]
        assert closing > positions[-1]
        assert html.count(f"{MARKER} intro line") == 1, "the letter is not printed on the price pages"
        assert closing < html.index(f"{MARKER} Townhouse")


def test_pdf_layout_3_letterhead_off_drops_one_letterhead():
    with blank_session() as db:
        env = _setup(db)
        _r, on = _html3(db, env, make_design())
        sender = db.execute(text("select name from companies where code = 'SRT'")).scalar()
    with blank_session() as db:
        env = _setup(db)
        _r, off = _html3(db, env, make_design(show_letterhead=False))
    assert off.count(sender) == on.count(sender) - 1


def test_pdf_layout_3_terms_row_hidden_prints_terms_after_the_total_unnumbered():
    d = make_design()
    next(r for r in d["rows"] if r["key"] == "terms")["shown"] = False
    with blank_session() as db:
        env = _setup(db)
        _r, html = _html3(db, env, d, terms=f"<ol><li>{MARKER} clause one</li></ol>{TERMS}")
        assert "TERMS &amp; CONDITIONS:" not in html
        before, after = html.split("TOTAL AMOUNT", 1)
        assert f"{MARKER} clause one" not in before and f"{MARKER} closing line" not in before
        assert f"{MARKER} clause one" in after and f"{MARKER} closing line" in after
        # printed as written: the user's own <ol> is kept, a user <ul> stays nested, and no
        # heading or dash line is wrapped into the old one-<li>-per-line list.
        assert "<ol>" in after and after.count("<ul>") == 2
        assert not re.search(r"<li>\s*(<strong>)?\s*" + MARKER + r" Heading line", after)
        assert not re.search(r"<li>\s*-\s*" + MARKER + " dash line", after)
        assert f"- {MARKER} dash line" in after


def test_pdf_layout_3_terms_row_shown_prints_terms_on_page_one_only():
    with blank_session() as db:
        env = _setup(db)
        _r, html = _html3(db, env, make_design())
        assert html.count(f"{MARKER} closing line") == 1
        assert f"{MARKER} closing line" not in html.split("TOTAL AMOUNT", 1)[1]


def test_pdf_layout_3_escapes_title_labels_and_cleans_intro_and_closing():
    d = make_design(title="<script>alert(1)</script>")
    d["rows"][0]["label"] = "A <i>x</i> & B"
    with blank_session() as db:
        env = _setup(db)
        seed_design(db, env, d)
        document = _full_document(db, env)
        document.cover_letter_html = "<p>ok</p><script>alert('x')</script>"
        document.cover_closing_html = '<p onclick="evil()">fine</p><iframe>frame</iframe>'
        record = _issue(db, document, env["owner"])
        _force_layout_3(db, record, d)  # guards sent layout 3 revisions (QUOTE-COVER-FIELDS)
        from app.services import project_quotation_pdf_service as qpdf

        html = qpdf.build_issue_html(db, record)
        assert "<script>alert" not in html and "evil" not in html and "<iframe" not in html
        assert "&lt;script&gt;" in html
        assert "<i>x</i>" not in html and "<I>X</I>" not in html
        assert re.search(r"A &lt;i&gt;x&lt;/i&gt; &amp; b:|A &lt;I&gt;X&lt;/I&gt; &amp; B:", html)


def test_pdf_layout_2_is_unchanged_by_the_designer():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        document = prepared(db, env)
        record = _issue(db, document, env["owner"])
        db.flush()
        db.execute(
            text("update quotation_issues set layout_version = 2, cover_design = null where id = :i"),
            {"i": str(record.id)},
        )
        db.expire_all()
        html = qpdf.build_issue_html(db, record)
        assert "REFERENCE NO.:" in html and "PREPARED BY:" in html
        assert f"{MARKER} closing words" not in html


# ------------------------------------------------------------------ countersign


def test_countersign_layout_3_follows_the_design():
    d = designed(closing_html="")
    with blank_session() as db:
        env = _setup(db)
        document = prepared(db, env, d)
        document.cover_letter_html = "<p>intro <strong>b</strong></p><script>alert(1)</script>"
        document.cover_closing_html = '<p onclick="x()">closing words</p>'
        record = _issue(db, document, env["owner"])
        _force_layout_3(db, record, d)  # guards sent layout 3 revisions (QUOTE-COVER-FIELDS)
        body = sign_body(db, record)
        rows = body["cover_rows"]
        assert [r["key"] for r in rows] == [
            "prepared_by", "reference", "date", "company", "attn", "terms", "payment_terms",
            "validity", "address",
        ]
        by = {r["key"]: r for r in rows}
        assert by["reference"]["label"] == "Offer Number" and by["company"]["label"] == "Sent To"
        assert "email" not in by and "contact" not in by
        assert body["cover_title"] == f"{MARKER} OFFER"
        assert body["cover_show_letterhead"] is True
        assert "<strong>b</strong>" in body["cover_intro_html"] and "<script" not in body["cover_intro_html"]
        assert "closing words" in body["cover_closing_html"] and "onclick" not in body["cover_closing_html"]


def test_countersign_layout_3_letterhead_off_and_terms_hidden_keeps_the_terms_panel():
    d = make_design(show_letterhead=False)
    next(r for r in d["rows"] if r["key"] == "terms")["shown"] = False
    with blank_session() as db:
        env = _setup(db)
        record = _issue(db, prepared(db, env, d), env["owner"])
        body = sign_body(db, record)
        assert body["cover_show_letterhead"] is False
        assert "terms" not in [r["key"] for r in body["cover_rows"]]
        assert f"{MARKER} closing line" in (body["terms"] or "")


def test_countersign_default_design_matches_the_2088_rows_and_title():
    with blank_session() as db:
        env = _setup(db)
        record = _issue(db, prepared(db, env), env["owner"])
        _force_layout_3(db, record)  # guards sent layout 3 revisions (QUOTE-COVER-FIELDS)
        body = sign_body(db, record)
        assert [r["key"] for r in body["cover_rows"]] == PRINTED_KEYS
        assert [r["label"] for r in body["cover_rows"]] == PRINTED_LABELS
        assert body["cover_title"] == "QUOTATION" and body["cover_show_letterhead"] is True


def test_editing_the_document_letter_and_closing_after_send_leaves_pdf_and_sign_payload_alone():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        document = prepared(db, env, designed())
        record = _issue(db, document, env["owner"])
        html_before = qpdf.build_issue_html(db, record)
        body_before = sign_body(db, record)
        assert f"{MARKER} intro line" in html_before and f"{MARKER} closing words" in html_before

        document.cover_letter_html = "<p>EDITED LATER INTRO</p>"
        document.cover_closing_html = "<p>EDITED LATER CLOSING</p>"
        db.flush()
        db.expire_all()

        html_after = qpdf.build_issue_html(db, record)
        assert html_after == html_before
        assert "EDITED LATER" not in html_after
        body_after = sign_body(db, record)
        assert f"{MARKER} intro line" in body_after["cover_intro_html"]
        assert f"{MARKER} closing words" in body_after["cover_closing_html"]
        assert "EDITED LATER" not in body_after["cover_intro_html"] + body_after["cover_closing_html"]


def _style_of(html):
    import re

    return "".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))


def test_layout_2_html_has_exactly_the_2088_style_and_layout_3_adds_the_designed_css():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        env = _setup(db)
        record = _issue(db, prepared(db, env), env["owner"])
        html3 = qpdf.build_issue_html(db, record)
        db.flush()
        db.execute(
            text("update quotation_issues set layout_version = 2, cover_design = null where id = :i"),
            {"i": str(record.id)},
        )
        db.expire_all()
        html2 = qpdf.build_issue_html(db, record)
    designed_css = qpdf._DESIGNED_COVER_STYLE
    assert designed_css.strip() and designed_css not in html2
    assert designed_css in html3
    assert _style_of(html2).strip() == (qpdf._STYLE + qpdf._COVER_STYLE).strip()


# ------------------------------------------------------------------ the noun rule (merge with #2097)


def _cover_of(db, env, kind, d=None):
    from app.services import project_quotation_pdf_service as qpdf

    record = _issue(db, prepared(db, env, d, kind=kind), env["owner"])
    _force_layout_3(db, record, d)  # guards sent layout 3 revisions (QUOTE-COVER-FIELDS)
    db.refresh(record)
    return record, qpdf.build_issue_html(db, record), sign_body(db, record)


def test_unchanged_default_design_prints_the_documents_noun_on_the_pdf_cover():
    with blank_session() as db:
        env = _setup(db)
        record, html, body = _cover_of(db, env, "proposal")
        assert body["cover_title"] == "PROPOSAL"
        assert "PROPOSAL" in html
        assert "PROPOSAL PURPOSE:" not in html and "QUOTATION PURPOSE:" not in html
        assert record.revision_label == "A"
        ref = next(r for r in body["cover_rows"] if r["key"] == "reference")["text"]
        assert ref.split(" ")[0].endswith("-A")
    with blank_session() as db:
        env = _setup(db)
        record, html, body = _cover_of(db, env, "quotation")
        assert body["cover_title"] == "QUOTATION"
        assert "QUOTATION PURPOSE:" not in html and "PROPOSAL PURPOSE:" not in html
        assert record.revision_label == "R1"
        ref = next(r for r in body["cover_rows"] if r["key"] == "reference")["text"]
        assert ref.split(" ")[0].endswith("-R1")


def test_a_designs_own_title_prints_and_its_purpose_row_never_does_for_a_proposal():
    d = make_design(title="OFFER SHEET")
    for row in d["rows"]:
        if row["key"] == "purpose":
            row["label"] = "SCOPE"
    with blank_session() as db:
        env = _setup(db)
        _record, html, body = _cover_of(db, env, "proposal", d)
        assert body["cover_title"] == "OFFER SHEET"
        assert "OFFER SHEET" in html and "SCOPE:" not in html
        assert "PROPOSAL PURPOSE" not in html and "QUOTATION PURPOSE" not in html
        assert "PROPOSAL" not in html.replace("PROPOSAL FROM", "")
