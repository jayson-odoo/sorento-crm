"""QUOTE-COVER-DESIGN fix round 1 red tests: tokens filled on every save and in previews (T),
security should-fixes (S: linear cleaners, 50000 caps), deactivate a cover design (A)."""
from __future__ import annotations

import time

import pytest

from .test_project_quotation_document_routes import (  # noqa: F401  (api is a fixture)
    BASE as PS,
    _add_scope,
    _create_document,
    _sign,
    api,
)
from .test_quote_cover_design_preview import counts, project_url, without
from .test_quote_cover_design_templates import design

MARKER = "zzt-qcround1"
TEMPLATES = f"{PS}/config/quotation-templates"
CAP = 50000


def root(project):
    return f"{PS}/projects/{project.id}/quotation-documents"


# ------------------------------------------------------------------ T. tokens filled


def test_create_fills_tokens_in_letter_and_closing(api):
    client, _db, _c, _u, project, _party = api
    created = _create_document(
        client,
        project.id,
        attn_name=f"{MARKER} Kelly",
        cover_letter_html="<p>Re {{project_title}}</p>",
        cover_closing_html="<p>Dear {{attn_name}}</p>",
        scopes=[{"scope_label": f"{MARKER} Townhouse", "lines": []}],
    )
    assert project.title in created["cover_letter_html"]
    assert f"{MARKER} Kelly" in created["cover_closing_html"]
    assert "{{" not in created["cover_letter_html"] + created["cover_closing_html"]
    again = client.get(f"{root(project)}/{created['id']}").json()
    assert "{{" not in (again["cover_letter_html"] or "") + (again["cover_closing_html"] or "")


def test_patch_fills_tokens_in_letter_closing_and_terms(api):
    client, _db, _c, _u, project, _party = api
    created = _create_document(client, project.id)
    patched = client.patch(
        f"{root(project)}/{created['id']}",
        json={
            "cover_letter_html": "<p>Re {{project_title}}</p>",
            "cover_closing_html": "<p>About {{project_title}}</p>",
            "terms_html": "<p>Terms for {{project_title}}</p>",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    for field in ("cover_letter_html", "cover_closing_html", "terms_html"):
        assert project.title in body[field], field
        assert "{{" not in body[field], field
    again = client.get(f"{root(project)}/{created['id']}").json()
    assert project.title in again["terms_html"]


def test_create_with_scopes_like_the_form_fills_tokens_too(api):
    client, _db, _c, _u, project, _party = api
    created = _create_document(
        client,
        project.id,
        cover_letter_html="<p>Re {{project_title}}</p>",
        terms_html="<p>T {{project_title}}</p>",
        scopes=[{"scope_label": f"{MARKER} Townhouse", "lines": []}],
    )
    for field in ("cover_letter_html", "terms_html"):
        assert project.title in created[field] and "{{" not in created[field], field


def test_new_quotation_preview_fills_tokens_with_no_document_id(api):
    client, db, _c, _u, project, _party = api
    before = counts(db)
    out = client.post(
        project_url(project),
        json={"cover_letter_html": "<p>Re {{project_title}}</p>", "cover_closing_html": "<p>Bye {{project_title}}</p>"},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert project.title in body["cover_intro_html"] and "{{" not in body["cover_intro_html"]
    assert project.title in body["cover_closing_html"]
    assert counts(db) == before


FIELDS = ["cover_letter_html", "cover_closing_html", "terms_html"]


@pytest.mark.parametrize("field", FIELDS)
def test_unknown_token_is_422_on_create_patch_and_preview(api, field):
    client, _db, _c, _u, project, _party = api
    bad = {field: "<p>{{not_a_real_token}}</p>"}
    assert client.post(root(project), json=bad).status_code == 422
    created = _create_document(client, project.id)
    assert client.patch(f"{root(project)}/{created['id']}", json=bad).status_code == 422
    assert client.post(project_url(project), json=bad).status_code == 422


def test_issued_pdf_of_such_a_quotation_has_the_title_and_no_raw_tokens(api):
    from app.models.projects import ProjectQuotationIssue
    from app.services import project_quotation_pdf_service as qpdf

    client, db, _c, _u, project, _party = api
    created = _create_document(
        client,
        project.id,
        cover_letter_html="<p>Intro {{project_title}}</p>",
        cover_closing_html="<p>Closing {{project_title}}</p>",
        terms_html="<p>Terms {{project_title}}</p>",
    )
    _add_scope(client, project.id, created["id"], f"{MARKER} Townhouse")
    _sign(client, root(project), created["id"])
    assert client.post(f"{root(project)}/{created['id']}/issue").status_code == 201
    db.expire_all()
    record = db.query(ProjectQuotationIssue).filter(ProjectQuotationIssue.document_id == created["id"]).one()
    html = qpdf.build_issue_html(db, record)
    assert "{{" not in html
    assert html.count(project.title) >= 3


# ------------------------------------------------------------------ S. security


def test_clean_terms_html_is_linear_on_unbalanced_input():
    from app.services.quotation_cover_service import clean_terms_html

    start = time.monotonic()
    clean_terms_html("<p>" * 80000 + "</li>" * 80000)
    assert time.monotonic() - start < 3


def test_find_unknown_tokens_is_linear_on_many_distinct_tokens():
    from app.services.project_quotation_template_service import find_unknown_tokens

    body = "".join("{{t%d}}" % i for i in range(60000))
    start = time.monotonic()
    found = find_unknown_tokens(body)
    assert time.monotonic() - start < 3
    assert len(found) == 60000 and found[0] == "t0"


def test_document_html_fields_cap_at_50000(api):
    client, _db, _c, _u, project, _party = api
    for field in FIELDS:
        assert client.post(root(project), json={field: "x" * (CAP + 1)}).status_code == 422, field
    created = _create_document(client, project.id)
    for field in FIELDS:
        res = client.patch(f"{root(project)}/{created['id']}", json={field: "y" * (CAP + 1)})
        assert res.status_code == 422, field
    ok = client.post(root(project), json={"cover_letter_html": "x" * CAP})
    assert ok.status_code == 201, ok.text


def test_project_preview_html_fields_cap_at_50000(api):
    client, _db, _c, _u, project, _party = api
    for field in FIELDS:
        assert client.post(project_url(project), json={field: "x" * (CAP + 1)}).status_code == 422, field
    assert client.post(project_url(project), json={"terms_html": "x" * CAP}).status_code == 200


def test_design_preview_and_template_bodies_cap_at_50000(api):
    client, *_ = api
    preview = f"{TEMPLATES}/cover-preview"
    assert client.post(preview, json={"design": design(), "body_html": "x" * (CAP + 1)}).status_code == 422
    assert client.post(preview, json={"design": design(closing_html="x" * (CAP + 1)), "body_html": ""}).status_code == 422
    assert client.post(preview, json={"design": design(closing_html="x" * CAP), "body_html": "x" * CAP}).status_code == 200

    def make(**over):
        return client.post(
            TEMPLATES,
            json={"kind": "cover_page", "name": f"{MARKER} cap", "body_html": "<p>a</p>", "design": design(), **over},
        )

    assert make(body_html="x" * (CAP + 1)).status_code == 422
    assert make(design=design(closing_html="x" * (CAP + 1))).status_code == 422
    made = make(body_html="x" * CAP, design=design(closing_html="x" * CAP))
    assert made.status_code == 201, made.text
    tid = made.json()["id"]
    assert client.put(f"{TEMPLATES}/{tid}", json={"body_html": "y" * (CAP + 1)}).status_code == 422
    assert client.put(f"{TEMPLATES}/{tid}", json={"design": design(closing_html="y" * (CAP + 1))}).status_code == 422
    terms = client.post(TEMPLATES, json={"kind": "terms", "name": f"{MARKER} t", "body_html": "x" * (CAP + 1)})
    assert terms.status_code == 422


# ------------------------------------------------------------------ A. deactivate


def _design(client, name):
    res = client.post(
        TEMPLATES,
        json={"kind": "cover_page", "name": f"{MARKER} {name}", "body_html": "", "design": design(title=f"{MARKER} T")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_deactivate_the_only_cover_design_then_issue_copies_the_default_and_it_can_be_deleted(api):
    from app.models.projects import ProjectQuotationIssue
    from app.services.quotation_cover_service import default_design

    client, db, _c, _u, project, _party = api
    made = _design(client, "only")
    assert made["is_active"] is True
    res = client.post(f"{TEMPLATES}/{made['id']}/deactivate")
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is False
    listed = client.get(TEMPLATES, params={"kind": "cover_page"}).json()["data"]
    assert not any(r["is_active"] for r in listed)

    created = _create_document(client, project.id)
    _add_scope(client, project.id, created["id"], f"{MARKER} Townhouse")
    _sign(client, root(project), created["id"])
    assert client.post(f"{root(project)}/{created['id']}/issue").status_code == 201
    db.expire_all()
    record = db.query(ProjectQuotationIssue).filter(ProjectQuotationIssue.document_id == created["id"]).one()
    assert record.cover_design == default_design()

    assert client.delete(f"{TEMPLATES}/{made['id']}").status_code in (200, 204)


def test_deactivate_a_terms_template_is_422_and_leaves_it_active(api):
    client, *_ = api
    terms = client.post(TEMPLATES, json={"kind": "terms", "name": f"{MARKER} terms", "body_html": "<p>c</p>"}).json()
    res = client.post(f"{TEMPLATES}/{terms['id']}/deactivate")
    assert res.status_code == 422, res.text
    assert client.get(f"{TEMPLATES}/{terms['id']}").json()["is_active"] is True


def test_deactivate_needs_the_same_permission_as_activate(api):
    client, *_ = api
    made = _design(client, "perm")
    with without("projects.types.edit"):
        res = client.post(f"{TEMPLATES}/{made['id']}/deactivate")
    assert res.status_code == 403, res.text
    assert client.get(f"{TEMPLATES}/{made['id']}").json()["is_active"] is True
