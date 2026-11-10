"""QUOTE-COVER-DESIGN red tests, part 1: the design on a cover_page template (HTTP seam) and the
create-document copy. UAC A2, A4, B1, B4. Postgres only; chains seeded by the shared fixtures."""
from __future__ import annotations

import pytest

from .test_project_quotation_document_routes import (  # noqa: F401  (api is a fixture)
    BASE as PS,
    _create_document,
    api as doc_api,
)
from .test_project_quotation_template_routes import (  # noqa: F401  (api is a fixture)
    BASE as TEMPLATES,
    MARKER as TMPL_MARKER,
    api,
)

MARKER = "zzt-qcdesign"
KEYS = [
    "reference", "date", "attn", "company", "contact", "address", "email",
    "purpose", "terms", "payment_terms", "validity", "prepared_by",
]
LABELS = [
    "Reference No.", "Date", "Attn", "Company", "Contact", "Add", "Email",
    "Quotation Purpose", "Terms & Conditions", "Payment Terms", "Validity", "Prepared By",
]


def design(**over):
    base = {
        "show_letterhead": True,
        "title": "QUOTATION",
        "rows": [{"key": k, "shown": True, "label": label} for k, label in zip(KEYS, LABELS)],
        "closing_html": "",
    }
    base.update(over)
    return base


def post_design(client, *, name=None, body="<p>Hello</p>", d=None, **extra):
    return client.post(
        TEMPLATES,
        json={
            "kind": "cover_page",
            "name": name or f"{MARKER} design",
            "body_html": body,
            "design": d if d is not None else design(),
            **extra,
        },
    )


def test_default_design_constant_is_the_2088_cover():
    from app.services.quotation_cover_service import COVER_LAYOUT_DESIGNED, DEFAULT_DESIGN

    assert COVER_LAYOUT_DESIGNED == 3
    assert DEFAULT_DESIGN["title"] == "QUOTATION"
    assert DEFAULT_DESIGN["show_letterhead"] is True
    assert DEFAULT_DESIGN["closing_html"] == ""
    assert [r["key"] for r in DEFAULT_DESIGN["rows"]] == KEYS
    assert [r["label"] for r in DEFAULT_DESIGN["rows"]] == LABELS
    assert all(r["shown"] is True for r in DEFAULT_DESIGN["rows"])


def test_cover_page_design_round_trips_create_get_and_list_with_an_empty_intro(api):
    from app.services.quotation_cover_service import normalize_design

    client, *_ = api
    d = design(title=f"{MARKER} OFFER", show_letterhead=False, closing_html="<p>Thanks</p>")
    d["rows"][2]["shown"] = False
    d["rows"][0]["label"] = "Our Ref"
    created = post_design(client, body="", d=d)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["kind"] == "cover_page"
    # QUOTE-COVER-FIELDS: the 12-row shape is served normalized (sections, purpose dropped)
    want = normalize_design(d)
    assert body["design"] == want
    assert body["is_active"] is True
    assert client.get(f"{TEMPLATES}/{body['id']}").json()["design"] == want
    listed = client.get(TEMPLATES, params={"kind": "cover_page"}).json()["data"]
    assert [r["design"] for r in listed if r["id"] == body["id"]] == [want]


def test_update_round_trips_the_design(api):
    from app.services.quotation_cover_service import normalize_design

    client, *_ = api
    made = post_design(client).json()
    d = design(title=f"{MARKER} NEW", closing_html="<p>Bye {{project_title}}</p>")
    d["rows"] = list(reversed(d["rows"]))
    put = client.put(f"{TEMPLATES}/{made['id']}", json={"design": d})
    assert put.status_code == 200, put.text
    assert put.json()["design"] == normalize_design(d)
    assert client.get(f"{TEMPLATES}/{made['id']}").json()["design"] == normalize_design(d)


def sectioned(**over):
    """A valid design in the sections shape (QUOTE-COVER-FIELDS)."""
    base = {
        "show_letterhead": True,
        "title": "QUOTATION",
        "closing_html": "",
        "sections": [
            {
                "style": "fields",
                "label": "",
                "columns": 2,
                "rows": [
                    {"source": "document_no", "label": "Reference No.", "shown": True, "column": 0},
                    {"source": "date", "label": "Date", "shown": True, "column": 1},
                ],
            }
        ],
    }
    base.update(over)
    return base


def _bad_unknown():
    d = sectioned()
    d["sections"][0]["rows"][0]["source"] = "nope"
    return d


def _bad_column():
    d = sectioned()
    d["sections"][0]["rows"][1]["column"] = 2
    return d


def _bad_style():
    d = sectioned()
    d["sections"][0]["style"] = "banner"
    return d


def _bad_label():
    d = design()
    d["rows"][0]["label"] = "x" * 61
    return d


BAD = [
    _bad_unknown(), _bad_column(), _bad_style(), _bad_label(),
    design(title="x" * 61),
    sectioned(sections=[]),
]


@pytest.mark.parametrize("bad", BAD, ids=["unknown", "column", "style", "label61", "title61", "nosections"])
def test_invalid_design_is_refused_on_create_and_update(api, bad):
    client, *_ = api
    refused = post_design(client, d=bad)
    assert refused.status_code == 422, refused.text
    ok = post_design(client, name=f"{MARKER} ok").json()
    put = client.put(f"{TEMPLATES}/{ok['id']}", json={"design": bad})
    assert put.status_code == 422, put.text


def test_label_and_title_of_exactly_60_are_accepted(api):
    client, *_ = api
    d = design(title="T" * 60)
    d["rows"][0]["label"] = "L" * 60
    assert post_design(client, d=d).status_code == 201


def test_unknown_token_in_intro_or_closing_is_refused_with_the_token_named(api):
    client, *_ = api
    refused = post_design(client, body="<p>Dear {{no_such_field}}</p>")
    assert refused.status_code == 422, refused.text
    assert "no_such_field" in refused.text
    refused = post_design(client, d=design(closing_html="<p>{{also_unknown}}</p>"))
    assert refused.status_code == 422, refused.text
    assert "also_unknown" in refused.text
    ok = post_design(client, name=f"{MARKER} fine").json()
    put = client.put(f"{TEMPLATES}/{ok['id']}", json={"body_html": "<p>{{nope_token}}</p>"})
    assert put.status_code == 422
    put = client.put(f"{TEMPLATES}/{ok['id']}", json={"design": design(closing_html="{{nope_token}}")})
    assert put.status_code == 422


def test_a_name_is_required_for_a_design(api):
    client, *_ = api
    assert post_design(client, name=f"{MARKER} named").status_code == 201
    assert post_design(client, name="  ").status_code == 422


def test_activate_keeps_one_active_cover_page_and_leaves_the_terms_template_active(api):
    client, *_ = api
    terms = client.post(
        TEMPLATES,
        json={"kind": "terms", "name": f"{MARKER} terms", "body_html": "<p>clause</p>"},
    ).json()
    assert terms["is_active"] is True
    first = post_design(client, name=f"{MARKER} first").json()
    second = post_design(client, name=f"{MARKER} second").json()
    assert first["is_active"] is True and second["is_active"] is False

    assert client.post(f"{TEMPLATES}/{second['id']}/activate").status_code == 200
    pages = {r["id"]: r for r in client.get(TEMPLATES, params={"kind": "cover_page"}).json()["data"]}
    assert pages[second["id"]]["is_active"] is True
    assert pages[first["id"]]["is_active"] is False
    assert client.get(f"{TEMPLATES}/{terms['id']}").json()["is_active"] is True


# ------------------------------------------------------------------ create document (B1, B4)


def test_create_document_copies_the_active_designs_intro_and_closing_rendered(doc_api):
    client, _db, _company_id, _user_id, project, _party = doc_api
    d = design(closing_html="<p>Closing for {{project_title}}</p>")
    made = client.post(
        f"{PS}/config/quotation-templates",
        json={
            "kind": "cover_page",
            "name": f"{MARKER} active",
            "body_html": "<p>Intro for {{project_title}}</p>",
            "design": d,
        },
    )
    assert made.status_code == 201, made.text
    created = _create_document(client, project.id)
    assert f"Intro for {project.title}" in created["cover_letter_html"]
    assert "{{" not in created["cover_letter_html"]
    assert f"Closing for {project.title}" in created["cover_closing_html"]
    assert "{{" not in created["cover_closing_html"]
    again = client.get(f"{PS}/projects/{project.id}/quotation-documents/{created['id']}").json()
    assert f"Closing for {project.title}" in again["cover_closing_html"]


def test_create_document_with_no_design_has_an_empty_closing(doc_api):
    client, _db, _company_id, _user_id, project, _party = doc_api
    created = _create_document(client, project.id)
    assert "cover_closing_html" in created
    assert not created["cover_closing_html"]


def test_document_patch_round_trips_the_closing(doc_api):
    client, _db, _company_id, _user_id, project, _party = doc_api
    created = _create_document(client, project.id)
    patched = client.patch(
        f"{PS}/projects/{project.id}/quotation-documents/{created['id']}",
        json={"cover_closing_html": f"<p>{MARKER} closing</p>"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["cover_closing_html"] == f"<p>{MARKER} closing</p>"


def test_cover_default_endpoint_returns_the_default_design(api):
    from app.services.quotation_cover_service import default_design

    client, *_ = api
    res = client.get(f"{TEMPLATES}/cover-default")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == default_design()
    assert len(body["sections"]) == 1 and body["sections"][0]["style"] == "fields"
    assert body["sections"][0]["columns"] == 1
    assert [r["source"] for r in body["sections"][0]["rows"]] == [
        "document_no", "date", "attn", "to_name", "to_tel", "to_address", "to_email",
        "terms", "payment_terms", "validity", "salesperson_name",
    ]
    assert body["title"] == "QUOTATION" and body["show_letterhead"] is True


def test_cover_default_endpoint_is_gated_like_the_list(api):
    from .test_quote_cover_design_preview import without

    client, *_ = api
    assert client.get(f"{TEMPLATES}/cover-default").status_code == 200
    with without("projects.types.view"):
        assert client.get(f"{TEMPLATES}/cover-default").status_code == 403
