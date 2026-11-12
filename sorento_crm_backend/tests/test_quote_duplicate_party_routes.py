"""QUOTE-DUPLICATE-PARTY at the HTTP boundary: POST .../duplicate answers 201 with the copy's
payload (Copied from + the picked To), 422 without a party, and the GET of the copy carries the
"Copied from" fields through ``response_model``. Every name is invented (public repo)."""
from __future__ import annotations

import pytest

from ._pg_fixture import blank_session
from .test_project_po_document_save import _client, _restore
from .test_quote_duplicate_party import _world

BASE = "/api/v1/project-sales"


@pytest.fixture()
def env():
    from app.models.base import company_scope

    with blank_session() as db:
        w = _world(db)
        db.commit()
        client, originals = _client(db, w.copier)
        try:
            with company_scope(db, frozenset({w.company_id})):
                yield client, db, w
        finally:
            _restore(originals)


def _url(w, document_id=None):
    return f"{BASE}/projects/{w.project.id}/quotation-documents/{document_id or w.source.id}/duplicate"


def test_duplicate_route_returns_the_copy(env):
    client, db, w = env
    response = client.post(_url(w), json={"recipient_party_id": w.architect.id, "attn_contact_ids": [w.attn.id]})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] != w.source.id
    assert body["recipient_name_snapshot"] == w.architect.name
    assert body["attn_name"] == "Ar. Test Person"
    assert body["copied_from_document_id"] == w.source.id
    assert body["copied_from_label"] == w.source.document_no

    again = client.get(f"{BASE}/projects/{w.project.id}/quotation-documents/{body['id']}")
    assert again.status_code == 200
    assert again.json()["copied_from_label"] == w.source.document_no


def test_duplicate_route_needs_a_party(env):
    client, _db, w = env
    response = client.post(_url(w), json={})
    assert response.status_code == 422, response.text


def test_duplicate_route_404_for_a_document_not_on_the_project(env):
    import uuid

    client, _db, w = env
    response = client.post(_url(w, str(uuid.uuid4())), json={"recipient_party_id": w.architect.id})
    assert response.status_code == 404, response.text
