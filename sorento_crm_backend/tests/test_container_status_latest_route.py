"""GET /api/v1/procurement/packing-lists/container-status/latest.

Route-level pin for AC-B2/B3: the response body carries `company_id` /
`company_name` alongside the existing fields, and the 404 copy stays
"No Container Status workbook has been imported yet." when the caller's
company has nothing (and no legacy NULL-company row exists either).

Auth-override pattern from `test_dealer_kit_routes.py` / `test_record_context_route.py`:
`apply_company_scope` is a router-level dependency (`app/main.py`), so it is
overridden directly rather than faked through a bearer token.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.company import Company
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from app.services.container_status_document import ensure_attachment_type

from tests._pg_fixture import blank_session, unique_code

SORENTO_ID = DEFAULT_COMPANY_ID
MOCHA_ID = "00000000-0000-0000-0000-000000000002"

ENDPOINT = "/api/v1/procurement/packing-lists/container-status/latest"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _workbook(db, *, uploaded_at: datetime, company_id: str | None) -> str:
    type_id = ensure_attachment_type(db)
    att_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO attachments (
                id, attachment_type_id, original_filename, stored_filename,
                file_path, mime_type, uploaded_at, is_deleted, company_id
            ) VALUES (:id, :t, :n, :n, :k, :m, :u, false, :c)
            """
        ),
        {
            "id": att_id,
            "t": type_id,
            "n": "Container Status 2026.xlsx",
            "k": f"import-sources/{unique_code('key')}/Container Status 2026.xlsx",
            "m": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "u": uploaded_at,
            "c": company_id,
        },
    )
    db.flush()
    return att_id


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(
        "app.services.storage_router.resolve_signed_url",
        lambda key, provider=None, expires_in=3600: f"https://cdn.test/{key}?sig=zzt",
    )

    with blank_session() as db:
        db.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        db.flush()

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        def _as(company_id: str):
            async def _override_scope():
                scope = frozenset({company_id})
                set_company_scope(db, scope)
                return scope

            app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": str(uuid.uuid4()), "email": "zzt-latest-route@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db, _as

        app.dependency_overrides.clear()


def test_the_response_carries_the_owning_company(api):
    """AC-B2: `company_id` / `company_name` sit alongside the existing fields."""
    db, _as = api
    now = datetime(2026, 8, 7, 10, 0, 0)
    _workbook(db, uploaded_at=now, company_id=SORENTO_ID)
    _workbook(db, uploaded_at=now, company_id=MOCHA_ID)
    db.commit()
    _as(MOCHA_ID)

    with TestClient(app) as c:
        res = c.get(ENDPOINT)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["company_id"] == MOCHA_ID
    assert body["company_name"] == "Mocha"
    for key in ("attachment_id", "url", "filename", "size", "uploaded_at"):
        assert key in body


def test_active_company_only_ever_sees_its_own_workbook(api):
    """AC-B1: two companies each hold a current workbook - the caller's active
    company decides which one comes back."""
    db, _as = api
    now = datetime(2026, 8, 7, 10, 0, 0)
    sorento_wb = _workbook(db, uploaded_at=now, company_id=SORENTO_ID)
    mocha_wb = _workbook(db, uploaded_at=now, company_id=MOCHA_ID)
    db.commit()

    _as(SORENTO_ID)
    with TestClient(app) as c:
        sorento_res = c.get(ENDPOINT)
    assert sorento_res.json()["attachment_id"] == sorento_wb
    assert sorento_res.json()["company_name"] == "Sorento"

    _as(MOCHA_ID)
    with TestClient(app) as c:
        mocha_res = c.get(ENDPOINT)
    assert mocha_res.json()["attachment_id"] == mocha_wb
    assert mocha_res.json()["company_name"] == "Mocha"


def test_404_copy_is_unchanged_when_nothing_has_been_imported(api):
    """AC-B3: no owned workbook and no legacy NULL-company row - the honest
    "nothing uploaded yet" 404, worded exactly as before this change."""
    db, _as = api
    _as(SORENTO_ID)

    with TestClient(app) as c:
        res = c.get(ENDPOINT)

    assert res.status_code == 404
    assert res.json()["detail"] == "No Container Status workbook has been imported yet."


def test_404_when_only_a_sibling_companys_workbook_exists(api):
    """The caller's own company has nothing, even though Mocha does - must not
    leak Mocha's workbook to a Sorento caller."""
    db, _as = api
    _workbook(db, uploaded_at=datetime(2026, 8, 7, 10, 0, 0), company_id=MOCHA_ID)
    db.commit()
    _as(SORENTO_ID)

    with TestClient(app) as c:
        res = c.get(ENDPOINT)

    assert res.status_code == 404
