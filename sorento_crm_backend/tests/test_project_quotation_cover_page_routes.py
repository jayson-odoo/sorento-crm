"""QUOTE-COVER-PAGE red tests, the HTTP seam: the four new document fields, the two template
fields, and the letter-templates payload. Over the wire because response_model silently drops
undeclared fields. Postgres only; chain seeded by the shared ``api`` fixture."""
from __future__ import annotations

from .test_project_quotation_document_routes import (  # noqa: F401  (api is a fixture)
    BASE,
    MARKER as DOC_MARKER,
    _create_document,
    api,
)

TEMPLATES = f"{BASE}/config/quotation-templates"
MARKER = "zzt-qcoverroute"
FIELDS = {
    "recipient_email_snapshot": f"{MARKER}@zzt.test",
    "quotation_purpose": f"{MARKER} Supply of sanitary ware",
    "payment_terms": f"{MARKER} 30 days net",
    "validity": f"{MARKER} 60 days",
}


def test_document_create_patch_and_get_round_trip_the_four_fields(api):
    client, _db, _company_id, _user_id, project, _party = api
    root = f"{BASE}/projects/{project.id}/quotation-documents"

    created = _create_document(client, project.id, **FIELDS)
    for key, value in FIELDS.items():
        assert created[key] == value, key

    patched = client.patch(
        f"{root}/{created['id']}",
        json={"payment_terms": f"{MARKER} 45 days", "validity": f"{MARKER} 90 days"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["payment_terms"] == f"{MARKER} 45 days"
    assert patched.json()["quotation_purpose"] == FIELDS["quotation_purpose"]

    reread = client.get(f"{root}/{created['id']}").json()
    assert reread["validity"] == f"{MARKER} 90 days"
    assert reread["recipient_email_snapshot"] == FIELDS["recipient_email_snapshot"]
    assert reread["quotation_purpose"] == FIELDS["quotation_purpose"]


def test_document_fields_default_to_null(api):
    client, _db, _company_id, _user_id, project, _party = api
    created = _create_document(client, project.id)
    for key in FIELDS:
        assert key in created and created[key] is None, key


def test_template_create_and_update_round_trip_payment_terms_and_validity(api):
    client, *_ = api
    created = client.post(
        TEMPLATES,
        json={
            "kind": "terms",
            "name": f"{MARKER} Standard terms",
            "body_html": "<p>clause</p>",
            "payment_terms": f"{MARKER} 30 days net",
            "validity": f"{MARKER} 60 days",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["payment_terms"] == f"{MARKER} 30 days net"
    assert body["validity"] == f"{MARKER} 60 days"

    updated = client.put(
        f"{TEMPLATES}/{body['id']}",
        json={"payment_terms": f"{MARKER} 14 days", "validity": f"{MARKER} 30 days"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["payment_terms"] == f"{MARKER} 14 days"
    one = client.get(f"{TEMPLATES}/{body['id']}").json()
    assert one["validity"] == f"{MARKER} 30 days"
    assert one["body_html"] == "<p>clause</p>"


def test_letter_templates_returns_the_active_templates_payment_terms_and_validity(api):
    client, _db, _company_id, _user_id, project, _party = api
    made = client.post(
        TEMPLATES,
        json={
            "kind": "terms",
            "name": f"{MARKER} Active terms",
            "body_html": "<p>clause</p>",
            "payment_terms": f"{MARKER} 30 days net",
            "validity": f"{MARKER} 60 days",
        },
    )
    assert made.status_code == 201, made.text
    assert made.json()["is_active"] is True

    got = client.get(f"{BASE}/projects/{project.id}/quotation-documents/letter-templates")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["terms_html"] == "<p>clause</p>"
    assert body["payment_terms"] == f"{MARKER} 30 days net"
    assert body["validity"] == f"{MARKER} 60 days"


def test_letter_templates_with_no_active_template_has_null_payment_terms_and_validity(api):
    client, _db, _company_id, _user_id, project, _party = api
    body = client.get(
        f"{BASE}/projects/{project.id}/quotation-documents/letter-templates"
    ).json()
    assert "payment_terms" in body and body["payment_terms"] is None
    assert "validity" in body and body["validity"] is None


# ------------------------------------------------------------------ fix round 1


import pytest  # noqa: E402


@pytest.mark.parametrize("field", list(FIELDS))
def test_document_free_text_fields_cap_at_2000_characters(api, field):
    client, _db, _company_id, _user_id, project, _party = api
    root = f"{BASE}/projects/{project.id}/quotation-documents"

    too_long = client.post(root, json={field: "x" * 2001})
    assert too_long.status_code == 422, too_long.text

    created = _create_document(client, project.id, **{field: "x" * 2000})
    assert created[field] == "x" * 2000

    patched = client.patch(f"{root}/{created['id']}", json={field: "y" * 2001})
    assert patched.status_code == 422, patched.text


@pytest.mark.parametrize("field", ["payment_terms", "validity"])
def test_template_free_text_fields_cap_at_2000_characters(api, field):
    client, *_ = api
    body = {"kind": "terms", "name": f"{MARKER} cap", "body_html": "<p>c</p>"}
    assert client.post(TEMPLATES, json={**body, field: "x" * 2001}).status_code == 422
    ok = client.post(TEMPLATES, json={**body, field: "x" * 2000})
    assert ok.status_code == 201, ok.text
    assert client.put(f"{TEMPLATES}/{ok.json()['id']}", json={field: "y" * 2001}).status_code == 422


def test_document_response_carries_prepared_by_the_project_owner(api):
    client, _db, _company_id, _user_id, project, _party = api
    created = _create_document(client, project.id)
    assert created["prepared_by"] == f"{DOC_MARKER} Baser"
    got = client.get(f"{BASE}/projects/{project.id}/quotation-documents/{created['id']}").json()
    assert got["prepared_by"] == f"{DOC_MARKER} Baser"


def test_document_prepared_by_falls_back_to_the_creator_when_the_project_has_no_owner(api):
    from sqlalchemy import text

    client, db, _company_id, _user_id, project, _party = api
    created = _create_document(client, project.id)
    db.execute(text("update projects set owner_user_id = null where id = :i"), {"i": str(project.id)})
    db.commit()
    got = client.get(f"{BASE}/projects/{project.id}/quotation-documents/{created['id']}").json()
    assert "prepared_by" in got
    assert got["prepared_by"] == f"{DOC_MARKER} Baser"
