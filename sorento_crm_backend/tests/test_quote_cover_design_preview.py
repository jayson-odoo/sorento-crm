"""QUOTE-COVER-DESIGN red tests, part 3: the two preview endpoints (UAC B2, A3, E2).
They return the sign-payload cover shape and store nothing."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import text

from .test_project_quotation_document_routes import (  # noqa: F401  (api is a fixture)
    ALL_SLUGS,
    BASE as PS,
    _create_document,
    api,
)
from .test_quote_cover_design_templates import KEYS, LABELS, design

MARKER = "zzt-qcpreview"
#: QUOTE-COVER-FIELDS: the source a legacy row key prints (Quotation Purpose has none).
SOURCE_OF = {
    "reference": "document_no", "date": "date", "attn": "attn", "company": "to_name",
    "contact": "to_tel", "address": "to_address", "email": "to_email", "terms": "terms",
    "payment_terms": "payment_terms", "validity": "validity", "prepared_by": "prepared_by_name",
}
DEFAULT_SOURCES = [
    "document_no", "date", "attn", "to_name", "to_tel", "to_address", "to_email",
    "terms", "payment_terms", "validity", "prepared_by_name",
]


def shown_sources(d):
    """A legacy design's shown rows as sources, then the Project Title band every normalized
    design ends with (QUOTE-COVER-FIELDS)."""
    rows = [SOURCE_OF[r["key"]] for r in d["rows"] if r["shown"] and r["key"] in SOURCE_OF]
    return rows + ["project_title"]
TEMPLATES = f"{PS}/config/quotation-templates"


@contextmanager
def without(*slugs):
    from app.services.user_service import UserPermissionService

    granted = [s for s in ALL_SLUGS if s not in slugs]
    check = UserPermissionService.check_user_has_permission
    got = UserPermissionService.get_user_permission_slugs
    UserPermissionService.check_user_has_permission = lambda self, uid, wanted: wanted not in slugs
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    try:
        yield
    finally:
        UserPermissionService.check_user_has_permission = check
        UserPermissionService.get_user_permission_slugs = got


def counts(db):
    return {
        t: db.execute(text(f"select count(*) from {t}")).scalar()
        for t in ("quotation_documents", "quotation_issues", "quotation_templates", "quotation_signatures")
    }


def active_design(client, **over):
    d = design(title=f"{MARKER} OFFER", **over)
    by = {r["key"]: r for r in d["rows"]}
    by["email"]["shown"] = False
    by["reference"]["label"] = "Offer Number"
    d["rows"] = [by["reference"]] + [r for r in d["rows"] if r["key"] != "reference"]
    made = client.post(
        TEMPLATES,
        json={"kind": "cover_page", "name": f"{MARKER} active", "body_html": "<p>x</p>", "design": d},
    )
    assert made.status_code == 201, made.text
    return d


def quotation_document(client, db, project, **body):
    """A saved document of kind quotation (counts R1, R2; prints Quotation), not the default proposal."""
    from .test_project_quotation_document_routes import _document_row

    created = _create_document(client, project.id, **body)
    _document_row(db, created["id"]).kind = "quotation"
    db.flush()
    return created


def project_url(project):
    return f"{PS}/projects/{project.id}/quotation-documents/cover-preview"


def body_for_project(**over):
    return {
        "attn_name": f"{MARKER} Kelly",
        "recipient_email_snapshot": f"{MARKER}@example.com",
        "quotation_purpose": f"{MARKER} Supply of sanitary ware",
        "payment_terms": f"{MARKER} 30 days net",
        "validity": f"{MARKER} 60 days",
        "terms_html": f"<p>{MARKER} clause</p>",
        "cover_letter_html": f"<p>{MARKER} intro</p><script>alert(1)</script>",
        "cover_closing_html": f"<p>{MARKER} closing</p>",
        **over,
    }


def test_project_preview_uses_the_active_design_and_the_unsaved_values(api):
    client, db, _c, _u, project, _party = api
    d = active_design(client)
    created = quotation_document(client, db, project)
    before = counts(db)
    res = client.post(project_url(project), json={**body_for_project(), "document_id": created["id"]})
    assert res.status_code == 200, res.text
    out = res.json()
    assert counts(db) == before
    assert out["cover_title"] == d["title"]
    assert out["cover_show_letterhead"] is True
    rows = out["cover_rows"]
    assert [r["key"] for r in rows] == shown_sources(d)
    assert "to_email" not in [r["key"] for r in rows]
    by = {r["key"]: r for r in rows}
    assert by["document_no"]["label"] == "Offer Number"
    assert by["document_no"]["text"] == f"{created['document_no']}-R1"
    assert out["cover_sections"]
    assert by["attn"]["text"] == f"{MARKER} Kelly"
    assert by["payment_terms"]["text"] == f"{MARKER} 30 days net"
    assert f"{MARKER} clause" in by["terms"]["html"]
    assert f"{MARKER} intro" in out["cover_intro_html"] and "<script" not in out["cover_intro_html"]
    assert f"{MARKER} closing" in out["cover_closing_html"]
    assert "sender_name" in out and "sender_logo_url" in out


def test_project_preview_with_no_design_follows_the_default_design(api):
    client, db, _c, _u, project, _party = api
    created = quotation_document(client, db, project)
    out = client.post(project_url(project), json={**body_for_project(), "document_id": created["id"]}).json()
    assert out["cover_title"] == "QUOTATION" and out["cover_show_letterhead"] is True
    keys = [r["key"] for r in out["cover_rows"]]
    assert keys == [k for k in DEFAULT_SOURCES + ["project_title"] if k in keys]
    assert {"document_no", "attn", "payment_terms", "validity"} <= set(keys)
    assert [r["label"] for r in out["cover_rows"]][0] == LABELS[0]


def test_project_preview_for_an_existing_document_names_its_number_and_next_revision(api):
    client, db, _c, _u, project, _party = api
    created = quotation_document(client, db, project)
    before = counts(db)
    out = client.post(project_url(project), json={**body_for_project(), "document_id": created["id"]}).json()
    assert counts(db) == before
    ref = next(r for r in out["cover_rows"] if r["key"] == "document_no")["text"]
    assert ref == f"{created['document_no']}-R1"


def test_project_preview_after_a_send_names_r2_and_uses_the_typed_values(api):
    from .test_project_quotation_document_routes import _add_scope, _sign

    client, db, _c, _u, project, _party = api
    created = quotation_document(client, db, project, attn_name=f"{MARKER} Saved Attn")
    root = f"{PS}/projects/{project.id}/quotation-documents"
    _add_scope(client, project.id, created["id"], f"{MARKER} Townhouse")
    _sign(client, root, created["id"])
    assert client.post(f"{root}/{created['id']}/issue").status_code == 201
    before = counts(db)
    out = client.post(
        project_url(project),
        json={**body_for_project(attn_name=f"{MARKER} Typed Attn"), "document_id": created["id"]},
    ).json()
    assert counts(db) == before
    by = {r["key"]: r for r in out["cover_rows"]}
    assert by["document_no"]["text"] == f"{created['document_no']}-R2"
    assert by["attn"]["text"] == f"{MARKER} Typed Attn"


def test_new_document_preview_is_a_proposal_with_revision_a_and_a_sent_quotation_previews_r2(api):
    client, db, _c, _u, project, _party = api
    out = client.post(project_url(project), json=body_for_project()).json()
    assert out["cover_title"] == "PROPOSAL"
    ref = next(r for r in out["cover_rows"] if r["key"] == "document_no")["text"]
    assert ref.endswith("-A"), ref

    from .test_project_quotation_document_routes import _add_scope, _sign

    created = quotation_document(client, db, project)
    root = f"{PS}/projects/{project.id}/quotation-documents"
    _add_scope(client, project.id, created["id"], f"{MARKER} Townhouse")
    _sign(client, root, created["id"])
    assert client.post(f"{root}/{created['id']}/issue").status_code == 201
    out = client.post(project_url(project), json={**body_for_project(), "document_id": created["id"]}).json()
    assert out["cover_title"] == "QUOTATION"
    ref = next(r for r in out["cover_rows"] if r["key"] == "document_no")["text"]
    assert ref.endswith("-R2"), ref


def test_project_preview_without_permission_is_403_and_stores_nothing(api):
    client, db, _c, _u, project, _party = api
    before = counts(db)
    with without("projects.projects.view", "projects.projects.edit"):
        res = client.post(project_url(project), json=body_for_project())
    assert res.status_code == 403, res.text
    assert counts(db) == before


def test_design_preview_returns_the_cover_shape_with_sample_values_and_stores_nothing(api):
    client, db, *_ = api
    d = design(title=f"{MARKER} SAMPLE", show_letterhead=False, closing_html=f"<p>{MARKER} closing</p>")
    d["rows"][1]["shown"] = False
    d["rows"][0]["label"] = "Our Ref"
    before = counts(db)
    res = client.post(
        f"{TEMPLATES}/cover-preview",
        json={"design": d, "body_html": f"<p>{MARKER} intro <strong>b</strong></p>"},
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert counts(db) == before
    assert out["cover_title"] == d["title"] and out["cover_show_letterhead"] is False
    assert [r["key"] for r in out["cover_rows"]] == shown_sources(d)
    assert out["cover_sections"]
    assert out["cover_rows"][0]["label"] == "Our Ref"
    for row in out["cover_rows"]:
        assert row.get("text") or row.get("html"), row["key"]
    assert f"{MARKER} intro" in out["cover_intro_html"]
    assert f"{MARKER} closing" in out["cover_closing_html"]
    again = client.post(f"{TEMPLATES}/cover-preview", json={"design": d, "body_html": ""}).json()
    assert again["cover_rows"] == out["cover_rows"], "sample values are fixed"


def test_design_preview_refuses_an_invalid_design_and_an_unknown_token(api):
    client, *_ = api
    bad = {
        "show_letterhead": True,
        "title": "QUOTATION",
        "closing_html": "",
        "sections": [
            {
                "style": "fields", "label": "", "columns": 1,
                "rows": [{"source": "nope", "label": "X", "shown": True, "column": 0}],
            }
        ],
    }
    assert client.post(f"{TEMPLATES}/cover-preview", json={"design": bad, "body_html": ""}).status_code == 422
    bad["sections"][0]["rows"][0].update(source="date", column=1)
    assert client.post(f"{TEMPLATES}/cover-preview", json={"design": bad, "body_html": ""}).status_code == 422
    res = client.post(f"{TEMPLATES}/cover-preview", json={"design": design(), "body_html": "{{zz_unknown}}"})
    assert res.status_code == 422


def test_design_preview_without_permission_is_403(api):
    client, *_ = api
    with without("projects.types.view", "projects.types.edit"):
        res = client.post(f"{TEMPLATES}/cover-preview", json={"design": design(), "body_html": ""})
    assert res.status_code == 403, res.text
