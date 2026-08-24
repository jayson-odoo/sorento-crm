"""Route-level (HTTP) tests for GET /api/v1/resource-management/attachments/drive.

The service-level logic is covered by ``tests/test_drive_contents.py``; this file
pins the ENDPOINT itself - route resolution (the /drive segment is NOT captured by
/{attachment_id}), the response-model contract (discriminated ``data[]`` + server
``pagination`` + ``recursive`` flag), serialization of ``directory_path`` onto file
rows, and auth-denial.

Covers the endpoint side of:
  D1 (unified endpoint, discriminated rows, server sort + pagination),
  D2 (directory_path on file rows over the route serializer),
  D5 (route resolution / no regression - /{attachment_id} still wins for a real id),
  A8 (root scope at the HTTP layer),
  RBAC (unauthenticated -> 401/403).

Auth-bypass pattern copied from test_upload_activity_endpoint.py; runs against a
blank Postgres schema, rolled back at teardown.
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

_USER_ID = "773b536d-c675-5a29-b44c-37f956462ba0"
_ROLE_ID = "eb0d8146-c1be-524b-a31a-34b5cdc1ac01"
def _seed_user(db: Session) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.flush()
    db.add(User(id=_USER_ID, email="drive@test.com", name="Drive", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    db.commit()


@pytest.fixture
def client():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_user(db)

        def _override_get_db():
            yield db

        def _override_current_user():
            return {"id": _USER_ID, "email": "drive@test.com"}

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_current_user
        # The real request carries no auth header, so the router-level scope resolver
        # would compute UNSET (fail-closed, 0 rows) and hide the seeded owned rows
        # (directory_path enrichment then reads no AttachmentDirectory). Override it to
        # a no-op so the session keeps the conftest ``after_begin`` Sorento default,
        # matching the company the seeded rows are auto-stamped to.
        app.dependency_overrides[apply_company_scope] = lambda: None

        with TestClient(app) as c:
            yield c, db

        app.dependency_overrides.clear()


def _folder(db: Session, name: str, parent_id: str | None = None) -> str:
    from app.models.resources import AttachmentDirectory

    fid = str(uuid.uuid4())
    db.add(AttachmentDirectory(id=fid, name=name, parent_id=parent_id, is_deleted=False))
    db.commit()
    return fid


def _file(db: Session, *, filename: str, directory_id: str | None = None) -> str:
    from app.models.resources import Attachment

    aid = str(uuid.uuid4())
    db.add(
        Attachment(
            id=aid,
            original_filename=filename,
            stored_filename=filename,
            file_path=f"/x/{filename}",
            directory_id=directory_id,
            file_size_bytes=10,
            mime_type="application/pdf",
            access_levels=["dealer"],
            uploaded_by=_USER_ID,
            uploaded_at=datetime(2026, 5, 1),
            created_at=datetime(2026, 5, 1),
            is_deleted=False,
        )
    )
    db.commit()
    return aid


_URL = "/api/v1/resource-management/attachments/drive"


# --------------------------------------------------------------------------- #
# D1 - endpoint contract: discriminated data[] + pagination + recursive flag
# --------------------------------------------------------------------------- #
def test_drive_endpoint_root_contract(client):
    c, db = client
    top = _folder(db, "Marketing")
    _folder(db, "Nested", parent_id=top)  # must NOT appear at root
    _file(db, filename="root.pdf", directory_id=None)
    _file(db, filename="inside.pdf", directory_id=top)  # must NOT appear at root

    r = c.get(_URL, params={"limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    # Response-model shape.
    assert set(body.keys()) >= {"data", "pagination", "recursive", "empty"}
    assert isinstance(body["data"], list)
    assert body["recursive"] is False
    assert body["pagination"]["total"] == 2  # Marketing + root.pdf only (A8/D10)

    kinds = {row["kind"] for row in body["data"]}
    assert kinds == {"folder", "file"}
    names = {row.get("name") or row.get("original_filename") for row in body["data"]}
    assert "Marketing" in names
    assert "root.pdf" in names
    assert "Nested" not in names
    assert "inside.pdf" not in names


# --------------------------------------------------------------------------- #
# D5 - route resolution: /drive?directory_id=... is the drive handler, a LIST - 
# it is NOT swallowed by GET /{attachment_id}; and a real id still hits single-get.
# --------------------------------------------------------------------------- #
def test_drive_route_not_captured_by_attachment_id(client):
    c, db = client
    top = _folder(db, "Folder")
    _file(db, filename="a.pdf", directory_id=top)

    r = c.get(_URL, params={"directory_id": top, "limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    # A LIST contract (drive handler), not a single AttachmentResponse object.
    assert "data" in body and isinstance(body["data"], list)
    assert "pagination" in body
    assert {row["kind"] for row in body["data"]} <= {"folder", "file"}
    assert any(
        row.get("original_filename") == "a.pdf"
        for row in body["data"]
        if row["kind"] == "file"
    )


def test_single_attachment_get_route_distinct_from_drive(client):
    """Regression: /{attachment_id} resolves to the single-get handler, NOT /drive.

    Whatever the single-get handler returns for this attachment, it is the
    SINGLE-attachment handler executing, not the drive list handler. We assert
    the response is NOT the drive list shape (no ``data[]``/``pagination``/
    ``recursive``), which proves route resolution did not fall through to /drive.
    """
    c, db = client
    aid = _file(db, filename="single.pdf", directory_id=None)
    r = c.get(f"/api/v1/resource-management/attachments/{aid}")
    # Not a 404 (route matched) and not the drive list contract.
    assert r.status_code != 404, r.text
    body = r.json()
    assert "data" not in body
    assert "recursive" not in body
    assert "pagination" not in body


# --------------------------------------------------------------------------- #
# D2 - directory_path serialized onto file rows by the route
# --------------------------------------------------------------------------- #
def test_drive_endpoint_file_rows_carry_directory_path(client):
    c, db = client
    mk = _folder(db, "Marketing")
    camp = _folder(db, "Campaigns", parent_id=mk)
    _file(db, filename="promo.pdf", directory_id=camp)

    r = c.get(_URL, params={"query": "promo", "limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recursive"] is True
    file_rows = [row for row in body["data"] if row["kind"] == "file"]
    assert file_rows, "expected the deep file in recursive search"
    promo = next(row for row in file_rows if row["original_filename"] == "promo.pdf")
    assert promo["directory_path"] == "Marketing / Campaigns"


# --------------------------------------------------------------------------- #
# RBAC - unauthenticated request is rejected
# --------------------------------------------------------------------------- #
def test_drive_endpoint_requires_auth():
    """No dependency override -> real auth dep runs -> 401/403 without a token.

    Uses a bare TestClient (no overrides) so the genuine
    get_current_user_or_api_key dependency executes.
    """
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        r = c.get(_URL)
    assert r.status_code in (401, 403), r.text
