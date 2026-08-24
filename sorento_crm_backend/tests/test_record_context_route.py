"""Route-level tests for GET /api/v1/assistant/record-context/{entity_type}/{id}.

Auth-override pattern copied from test_lookup_public_api.py. The route is wrapped
in ``require_permission`` (JWT-only) so:
  - a permitted (superadmin) principal → 200,
  - a user lacking complaint.view → 403,
  - an EXTERNAL_API_KEY / X-API-Key principal → denied (no JWT → 401), proving the
    assembler is never reachable from n8n/WhatsApp (UAC §3.6).
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

_ADMIN_ID = "119c091d-f6bd-5b97-9a60-f65b08a723f6"
_ADMIN_ROLE = "101e642d-cb99-53a2-9297-0326d1fe083a"
_NOPERM_ID = "ceb49c23-4415-5447-92bf-eeda221add96"
_COMPLAINT_ID = str(uuid.uuid4())
_INQUIRY_ID = str(uuid.uuid4())


def _seed(db: Session) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment
    from app.models.complaints import Complaint
    from app.models.procurement import StockInquiry

    db.add(
        UserRole(
            id=_ADMIN_ROLE,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(User(id=_ADMIN_ID, email="rc-admin@test.com", name="RC Admin", status="ACTIVE"))
    db.add(User(id=_NOPERM_ID, email="rc-noperm@test.com", name="No Perm", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_ADMIN_ID, role_id=_ADMIN_ROLE))
    db.add(
        Complaint(
            id=_COMPLAINT_ID,
            complaint_number="CMP-2026-9001",
            complaint_type="Defect",
            product_type="Tiles",
            defect_description="Broken on arrival",
            customer_name="Test Co",
            status="new",
            created_at=datetime(2026, 6, 20, 0, 0, 0),
        )
    )
    db.add(
        StockInquiry(
            id=_INQUIRY_ID,
            inquiry_number="SI-2026-9001",
            salesperson="Sales Rep",
            product_code="ABC-1",
            item_description="Need 10 boxes",
            project_name="Test Project",
            status="new",
            created_at=datetime(2026, 6, 20, 0, 0, 0),
        )
    )
    db.commit()


@pytest.fixture
def db_and_app():
    from app.dependencies import get_current_user, get_db

    with blank_session() as db:
        _seed(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        yield db, get_current_user

        app.dependency_overrides.clear()


def test_permitted_user_gets_200(db_and_app):
    db, get_current_user = db_and_app
    app.dependency_overrides[get_current_user] = lambda: {"id": _ADMIN_ID, "email": "rc-admin@test.com"}

    with TestClient(app) as c:
        res = c.get(f"/api/v1/assistant/record-context/complaint/{_COMPLAINT_ID}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["entity_type"] == "complaint"
    assert body["display_ref"] == "CMP-2026-9001"
    assert body["about"]["description"] == "Broken on arrival"


def test_user_lacking_view_perm_gets_403(db_and_app):
    db, get_current_user = db_and_app
    app.dependency_overrides[get_current_user] = lambda: {"id": _NOPERM_ID, "email": "rc-noperm@test.com"}

    with TestClient(app) as c:
        res = c.get(f"/api/v1/assistant/record-context/complaint/{_COMPLAINT_ID}")
    assert res.status_code == 403, res.text


def test_api_key_principal_denied(db_and_app):
    # No get_current_user override → the real JWT-only dependency runs. An
    # X-API-Key-only request carries no bearer token, so it is rejected (401).
    import os

    with TestClient(app) as c:
        res = c.get(
            f"/api/v1/assistant/record-context/complaint/{_COMPLAINT_ID}",
            headers={"X-API-Key": os.environ.get("EXTERNAL_API_KEY", "any-key")},
        )
    assert res.status_code in (401, 403), res.text


def test_stock_inquiry_no_extra_perm_required(db_and_app):
    # stock_inquiry has no view permission slug → any authenticated user (even
    # one lacking complaint.view) gets 200.
    db, get_current_user = db_and_app
    app.dependency_overrides[get_current_user] = lambda: {"id": _NOPERM_ID, "email": "rc-noperm@test.com"}

    with TestClient(app) as c:
        res = c.get(f"/api/v1/assistant/record-context/stock_inquiry/{_INQUIRY_ID}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["entity_type"] == "stock_inquiry"
    assert body["display_ref"] == "SI-2026-9001"
    assert body["about"]["description"] == "Need 10 boxes"


def test_stock_inquiry_api_key_principal_denied(db_and_app):
    # The JWT-only dependency denies an X-API-Key-only request for the new types
    # too - the assembler stays out of n8n/WhatsApp reach (UAC §3.6).
    import os

    with TestClient(app) as c:
        res = c.get(
            f"/api/v1/assistant/record-context/stock_inquiry/{_INQUIRY_ID}",
            headers={"X-API-Key": os.environ.get("EXTERNAL_API_KEY", "any-key")},
        )
    assert res.status_code in (401, 403), res.text
