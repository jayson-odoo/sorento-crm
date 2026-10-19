"""ATTACH-ACCEPT: the portal file picker follows the attachment type's list.

The portal's file input used to hard-code `image/*,video/*,.pdf,.txt`, so an
admin who allowed xlsx/csv on the "Portal Submission" type still could not
pick one. `/me` now hands the browser the type's own list, and the upload
check reads the same parse, so the picker and the server cannot disagree.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.access import RespondContact
from app.models.portal import PortalToken
from app.models.procurement import StockInquiry
from tests._pg_fixture import blank_session


class _FakeStorageBackend:
    def upload_file(self, *args, **kwargs):
        key = args[1] if len(args) > 1 else kwargs.get("file_path")
        return key, f"https://cdn.test/{key}"


def _seed_portal_attachment_type(db: Session, allowed_extensions: str) -> None:
    from app.models.resources import AttachmentType
    from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE

    db.add(
        AttachmentType(
            id=str(uuid.uuid4()),
            code=PORTAL_ATTACHMENT_TYPE_CODE,
            type_name="Portal Submission",
            allowed_extensions=allowed_extensions,
            max_file_size_mb=10,
        )
    )
    db.commit()


@pytest.fixture
def client(monkeypatch):
    from app.database import get_db
    import app.services.storage_router as storage_router

    with blank_session() as db:
        fake_backend = _FakeStorageBackend()
        monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
        monkeypatch.setattr(storage_router, "get_backend", lambda provider: fake_backend)
        monkeypatch.setattr(
            storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}"
        )

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


def _contact_token(db: Session) -> tuple[RespondContact, PortalToken]:
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+6011{uuid.uuid4().hex[:8]}", name="Contact"
    )
    db.add(contact)
    db.flush()
    token = PortalToken(
        id=str(uuid.uuid4()),
        token=f"tok-{uuid.uuid4().hex}",
        contact_id=contact.id,
        space_id="space-1",
        expires_at=datetime.utcnow() + timedelta(days=30),
        verified_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(token)
    db.commit()
    return contact, token


def _inquiry(db: Session, contact: RespondContact) -> StockInquiry:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number="PORTAL-ACCEPT-1",
        status="pending_purchasing",
        contact_id=contact.id,
        space_id="space-1",
    )
    db.add(row)
    db.commit()
    return row


def _me(c: TestClient, token: PortalToken):
    return c.get("/api/v1/public/portal/me", headers={"X-Portal-Token": token.token})


def _upload(c: TestClient, token: PortalToken, inquiry: StockInquiry, name: str, mime: str):
    return c.post(
        "/api/v1/public/portal/attachments",
        data={"kind": "stock_inquiry", "submission_id": str(inquiry.id)},
        files={"file": (name, io.BytesIO(b"bytes"), mime)},
        headers={"X-Portal-Token": token.token},
    )


def test_me_returns_the_portal_attachment_types_allowed_extensions(client):
    c, db = client
    # Admins type the list by hand: spaces, capitals and a stray dot all occur.
    _seed_portal_attachment_type(db, "jpg, PNG,.xlsx,csv,,pdf")
    _, token = _contact_token(db)

    res = _me(c, token)

    assert res.status_code == 200, res.text
    assert res.json()["attachment_allowed_extensions"] == ["csv", "jpg", "pdf", "png", "xlsx"]


def test_me_still_loads_when_the_portal_attachment_type_is_missing(client):
    c, db = client
    _, token = _contact_token(db)

    res = _me(c, token)

    assert res.status_code == 200, res.text
    assert res.json()["attachment_allowed_extensions"] == []


def test_upload_accepts_xlsx_and_csv_when_the_type_lists_them(client):
    c, db = client
    _seed_portal_attachment_type(db, "jpg,png,pdf,xlsx,csv")
    contact, token = _contact_token(db)
    inquiry = _inquiry(db, contact)

    xlsx = _upload(
        c,
        token,
        inquiry,
        "stock_debt_reserve.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    csv = _upload(c, token, inquiry, "stock_debt_reserve.csv", "text/csv")

    assert xlsx.status_code == 200, xlsx.text
    assert csv.status_code == 200, csv.text


def test_upload_refusal_names_the_same_list_me_returns(client):
    c, db = client
    _seed_portal_attachment_type(db, "jpg, PNG,.xlsx,csv")
    contact, token = _contact_token(db)
    inquiry = _inquiry(db, contact)
    allowed = _me(c, token).json()["attachment_allowed_extensions"]

    res = _upload(c, token, inquiry, "setup.exe", "application/octet-stream")

    assert res.status_code == 400, res.text
    assert f"Allowed: {', '.join(allowed)}." in res.text
