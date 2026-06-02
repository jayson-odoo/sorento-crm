"""
Route-level tests for GET /api/v1/resource-management/upload-activity.

Auth bypass pattern copied from test_lookup_public_api.py.
"""
import json
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# MUST be first app import — resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402


_USER_ID = "test-user-1"
_ROLE_ID = "role-superadmin"


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
    db.add(User(id=_USER_ID, email="u1@test.com", name="U1", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    db.commit()


@pytest.fixture
def client():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.user import User, UserRole, UserRoleAssignment
    from app.models.resources import Attachment
    from app.models.integration import IntegrationLog
    from app.models.job import ImportJob
    from app.models.lookup import LookupBinding  # validator listener checks this table

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create only the tables touched by this endpoint — Attachment has a JSONB
    # column (`access_levels`) that SQLite can't render, so swap to JSON for tests.
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.types import JSON as GenericJSON

    # Monkeypatch column types where JSONB blocks SQLite create_all.
    for col in list(Attachment.__table__.columns):
        if isinstance(col.type, JSONB):
            col.type = GenericJSON()
    for col in list(ImportJob.__table__.columns):
        if isinstance(col.type, JSONB):
            col.type = GenericJSON()

    tables = [
        User.__table__,
        UserRole.__table__,
        UserRoleAssignment.__table__,
        Attachment.__table__,
        IntegrationLog.__table__,
        ImportJob.__table__,
        LookupBinding.__table__,
    ]
    from app.database import Base
    Base.metadata.create_all(engine, tables=tables)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    _seed_user(db)

    def _override_get_db():
        yield db

    def _override_current_user():
        return {"id": _USER_ID, "email": "u1@test.com"}

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_current_user_or_api_key] = _override_current_user

    with TestClient(app) as c:
        yield c, db

    app.dependency_overrides.clear()
    db.close()


def _add_attachment(
    db: Session,
    *,
    filename: str,
    batch_id: str | None = None,
    created_at: datetime | None = None,
) -> str:
    from app.models.resources import Attachment

    attachment_id = str(uuid.uuid4())
    db.add(
        Attachment(
            id=attachment_id,
            original_filename=filename,
            stored_filename=filename,
            file_path=f"/x/{filename}",
            file_size_bytes=10,
            mime_type="image/jpeg",
            access_levels=["dealer"],
            uploaded_by=_USER_ID,
            upload_batch_id=batch_id,
            created_at=created_at or datetime.utcnow(),
            uploaded_at=created_at or datetime.utcnow(),
        )
    )
    db.commit()
    return attachment_id


def _add_log(
    db: Session,
    *,
    attachment_id: str,
    status: str = "success",
    payload: dict | None = None,
    error_code: str | None = None,
) -> str:
    from app.models.integration import IntegrationLog

    log_id = str(uuid.uuid4())
    db.add(
        IntegrationLog(
            id=log_id,
            integration_channel="n8n",
            business_table="attachments",
            business_id=attachment_id,
            direction="outbound",
            endpoint="https://example.invalid/webhook",
            http_method="POST",
            status=status,
            response_payload=json.dumps(payload) if payload is not None else None,
            error_code=error_code,
            processed_at=datetime.utcnow(),
        )
    )
    db.commit()
    return log_id


def test_returns_empty_when_no_attachments(client):
    c, _db = client
    r = c.get("/api/v1/resource-management/upload-activity")
    assert r.status_code == 200, r.text
    assert r.json() == {"sessions": []}


def test_single_attachment_renders_as_single_session(client):
    c, db = client
    aid = _add_attachment(db, filename="receipt.pdf")
    _add_log(
        db,
        attachment_id=aid,
        status="success",
        payload={
            "schema_version": 1,
            "outcome": "linked",
            "summary": "Linked",
            "linked": [
                {
                    "entity_type": "product",
                    "entity_id": "p1",
                    "display_name": "CBMC5570",
                    "matched_by": "filename_token",
                }
            ],
            "unlinked_reasons": [],
            "errors": [],
        },
    )

    r = c.get("/api/v1/resource-management/upload-activity")
    assert r.status_code == 200, r.text
    sessions = r.json()["sessions"]
    assert len(sessions) == 1
    s = sessions[0]
    assert s["session_type"] == "single"
    assert s["status"] == "linked"
    assert s["aggregate"]["linked"] == 1
    assert s["files"][0]["status"] == "linked"
    # Linked entities are now read from the DB link tables (product_attachments
    # etc.), not from response_payload. With no actual product link seeded the
    # list is empty even when the n8n payload claims a linked product.
    assert s["files"][0]["linked"] == []


def test_multi_file_batch_groups_attachments(client):
    c, db = client
    batch = str(uuid.uuid4())
    a1 = _add_attachment(db, filename="a.jpg", batch_id=batch)
    a2 = _add_attachment(db, filename="b.jpg", batch_id=batch)
    _add_log(db, attachment_id=a1, status="success", payload={"schema_version": 1, "outcome": "linked", "summary": "ok", "linked": [], "unlinked_reasons": [], "errors": []})
    _add_log(db, attachment_id=a2, status="failed", error_code="N8N_CALLBACK_TIMEOUT")

    r = c.get("/api/v1/resource-management/upload-activity")
    assert r.status_code == 200, r.text
    sessions = r.json()["sessions"]
    multi = [s for s in sessions if s["session_type"] == "multi"]
    assert len(multi) == 1
    assert multi[0]["aggregate"]["total"] == 2
    assert multi[0]["aggregate"]["failed"] == 1
    assert multi[0]["status"] == "partial"
    assert multi[0]["needs_action"] is True


def test_bulk_zip_session_when_batch_matches_import_job(client):
    from app.models.job import ImportJob

    c, db = client
    job_id = str(uuid.uuid4())
    db.add(
        ImportJob(
            id=uuid.uuid4(),
            job_id=job_id,
            job_type="attachment_bulk_import",
            status="finished",
            user_id=_USER_ID,
            filename="brand_2026.zip",
        )
    )
    db.commit()
    a1 = _add_attachment(db, filename="x.jpg", batch_id=job_id)
    _add_log(db, attachment_id=a1, status="success", payload={"schema_version": 1, "outcome": "linked", "summary": "ok", "linked": [], "unlinked_reasons": [], "errors": []})

    r = c.get("/api/v1/resource-management/upload-activity")
    assert r.status_code == 200, r.text
    sessions = r.json()["sessions"]
    bulk = [s for s in sessions if s["session_type"] == "bulk_zip"]
    assert len(bulk) == 1
    assert bulk[0]["import_job_id"] == job_id
    assert bulk[0]["title"] == "brand_2026.zip"


def test_since_query_filters_old_attachments(client):
    c, db = client
    old_aid = _add_attachment(
        db,
        filename="old.jpg",
        created_at=datetime.utcnow() - timedelta(days=14),
    )
    _add_log(db, attachment_id=old_aid, status="success", payload={"schema_version": 1, "outcome": "linked", "summary": "ok", "linked": [], "unlinked_reasons": [], "errors": []})

    # Default 7-day cutoff: 14-day-old attachment excluded.
    r = c.get("/api/v1/resource-management/upload-activity")
    assert r.status_code == 200, r.text
    assert r.json() == {"sessions": []}


def test_unsupported_scope_rejected(client):
    c, _db = client
    r = c.get("/api/v1/resource-management/upload-activity?scope=tenant")
    assert r.status_code == 422
