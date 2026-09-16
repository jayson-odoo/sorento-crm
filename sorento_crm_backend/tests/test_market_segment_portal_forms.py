"""Market segment create/update/list routes carry and validate
``portal_form_types`` (AC-R3, D1).

The field does not exist on ``MarketSegmentCreate`` / ``Update`` / ``Response``
until the coder's D1 schema change lands (``app/schemas/market_segment.py``):
today a payload carrying it is silently ignored by pydantic's default
"extra=ignore" behaviour, so every echo assertion below KeyErrors and the
unknown-kind 422 never fires because nothing validates the field at all.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/user-management/market-segments/"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client(db, monkeypatch) -> TestClient:
    user = {"id": str(uuid.uuid4())}

    def _db_override():
        yield db

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda *a, **k: True
    )
    return TestClient(app)


def test_create_echoes_portal_form_types(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch)
        code = unique_code("seg").lower()[:50]

        response = client.post(
            BASE,
            json={
                "code": code,
                "name": "ZZT segment",
                "portal_form_types": ["price_tag_request"],
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["portal_form_types"] == ["price_tag_request"]


def test_create_unknown_kind_is_422(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch)
        code = unique_code("seg").lower()[:50]

        response = client.post(
            BASE,
            json={"code": code, "name": "ZZT segment", "portal_form_types": ["not_a_kind"]},
        )

        assert response.status_code == 422, response.text


def test_update_valid_portal_form_types(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch)
        code = unique_code("seg").lower()[:50]
        create = client.post(BASE, json={"code": code, "name": "ZZT segment"})
        assert create.status_code == 201, create.text

        response = client.put(
            f"{BASE}{code}",
            json={"portal_form_types": ["price_tag_request"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["portal_form_types"] == ["price_tag_request"]


def test_update_omitting_field_leaves_it_alone(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch)
        code = unique_code("seg").lower()[:50]
        create = client.post(
            BASE,
            json={
                "code": code,
                "name": "ZZT segment",
                "portal_form_types": ["price_tag_request"],
            },
        )
        assert create.status_code == 201, create.text

        response = client.put(f"{BASE}{code}", json={"name": "ZZT renamed"})

        assert response.status_code == 200, response.text
        assert response.json()["portal_form_types"] == ["price_tag_request"]


def test_update_unknown_kind_is_422(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch)
        code = unique_code("seg").lower()[:50]
        create = client.post(BASE, json={"code": code, "name": "ZZT segment"})
        assert create.status_code == 201, create.text

        response = client.put(f"{BASE}{code}", json={"portal_form_types": ["not_a_kind"]})

        assert response.status_code == 422, response.text


def test_list_carries_portal_form_types(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch)
        code = unique_code("seg").lower()[:50]
        create = client.post(
            BASE,
            json={
                "code": code,
                "name": "ZZT segment",
                "portal_form_types": ["price_tag_request"],
            },
        )
        assert create.status_code == 201, create.text

        response = client.get(BASE)

        assert response.status_code == 200, response.text
        row = next(r for r in response.json() if r["code"] == code)
        assert row["portal_form_types"] == ["price_tag_request"]
