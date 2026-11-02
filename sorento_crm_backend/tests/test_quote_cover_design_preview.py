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
    before = counts(db)
    res = client.post(project_url(project), json=body_for_project())
    assert res.status_code == 200, res.text
    out = res.json()
    assert counts(db) == before
    assert out["cover_title"] == d["title"]
    assert out["cover_show_letterhead"] is True
    rows = out["cover_rows"]
    assert [r["key"] for r in rows] == [r["key"] for r in d["rows"] if r["shown"]]
    assert "email" not in [r["key"] for r in rows]
    by = {r["key"]: r for r in rows}
    assert by["reference"]["label"] == "Offer Number"
    assert by["reference"]["text"].endswith(f"-R1 {project.title}")
    assert by["attn"]["text"] == f"{MARKER} Kelly"
    assert by["payment_terms"]["text"] == f"{MARKER} 30 days net"
    assert f"{MARKER} clause" in by["terms"]["html"]
    assert f"{MARKER} intro" in out["cover_intro_html"] and "<script" not in out["cover_intro_html"]
    assert f"{MARKER} closing" in out["cover_closing_html"]
    assert "sender_name" in out and "sender_logo_url" in out


def test_project_preview_with_no_design_follows_the_default_design(api):
    client, db, _c, _u, project, _party = api
    out = client.post(project_url(project), json=body_for_project()).json()
    assert out["cover_title"] == "QUOTATION" and out["cover_show_letterhead"] is True
    keys = [r["key"] for r in out["cover_rows"]]
    assert keys == [k for k in KEYS if k in keys]
    assert {"reference", "attn", "payment_terms", "validity"} <= set(keys)
    assert [r["label"] for r in out["cover_rows"]][0] == LABELS[0]


def test_project_preview_for_an_existing_document_names_its_number_and_next_revision(api):
    client, db, _c, _u, project, _party = api
    created = _create_document(client, project.id)
    before = counts(db)
    out = client.post(project_url(project), json={**body_for_project(), "document_id": created["id"]}).json()
    assert counts(db) == before
    ref = next(r for r in out["cover_rows"] if r["key"] == "reference")["text"]
    assert ref == f"{created['document_no']}-R1 {project.title}"


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
    assert [r["key"] for r in out["cover_rows"]] == [r["key"] for r in d["rows"] if r["shown"]]
    assert out["cover_rows"][0]["label"] == "Our Ref"
    for row in out["cover_rows"]:
        assert row.get("text") or row.get("html"), row["key"]
    assert f"{MARKER} intro" in out["cover_intro_html"]
    assert f"{MARKER} closing" in out["cover_closing_html"]
    again = client.post(f"{TEMPLATES}/cover-preview", json={"design": d, "body_html": ""}).json()
    assert again["cover_rows"] == out["cover_rows"], "sample values are fixed"


def test_design_preview_refuses_an_invalid_design_and_an_unknown_token(api):
    client, *_ = api
    bad = design()
    bad["rows"] = bad["rows"][:-1]
    assert client.post(f"{TEMPLATES}/cover-preview", json={"design": bad, "body_html": ""}).status_code == 422
    res = client.post(f"{TEMPLATES}/cover-preview", json={"design": design(), "body_html": "{{zz_unknown}}"})
    assert res.status_code == 422


def test_design_preview_without_permission_is_403(api):
    client, *_ = api
    with without("projects.types.view", "projects.types.edit"):
        res = client.post(f"{TEMPLATES}/cover-preview", json={"design": design(), "body_html": ""})
    assert res.status_code == 403, res.text
