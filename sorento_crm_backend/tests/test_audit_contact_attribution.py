"""Audit contact attribution + display resolution (System Health WS2a).

- log_audit(..., contact_id=X) persists contact_id.
- The auto-flush path (_session_before_flush) stamps set_actor_contact_id() from
  request context onto AuditLog.contact_id.
- GET /api/v1/audit/logs/ resolves user_display_name: contact name (contact_id) >
  staff name (user_id) > "System" (neither); changed_from/changed_to narrows.
- _derive_description turns a status-change UPDATE into "status: old → new".
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON

from app.main import app  # noqa: E402 (import first to settle app wiring)
import app.database as app_database
from app.database import Base
from app.audit_context import set_actor_contact_id
from app.dependencies import get_current_user_or_api_key
from app.models.access import RespondContact
from app.models.audit import AuditLog
from app.models.lookup import LookupBinding
from app.models.user import User, UserStatus
from app.services import audit_service


def _prep(*models):
    for model in models:
        for col in model.__table__.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                col.type = JSON()
                col.server_default = None


_MODELS = [AuditLog, User, RespondContact, LookupBinding]


@pytest.fixture
def db():
    _prep(*_MODELS)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _MODELS])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# --------------------------------------------------------------------------- #
# Persistence: explicit contact_id + auto-flush stamping                       #
# --------------------------------------------------------------------------- #
def test_log_audit_persists_explicit_contact_id(db):
    cid = str(uuid.uuid4())
    entry = audit_service.log_audit(
        db, "complaint", str(uuid.uuid4()), "UPDATE", contact_id=cid
    )
    db.commit()
    row = db.query(AuditLog).filter(AuditLog.id == entry.id).one()
    assert row.contact_id == cid


def test_auto_flush_stamps_actor_contact_from_context(db):
    """The before-flush handler (what the global listener invokes) picks up the
    request's actor-contact id and stamps it onto the auto-written audit row."""
    user = User(
        id=str(uuid.uuid4()),
        email="staff@example.com",
        name="Staff One",
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.commit()

    cid = str(uuid.uuid4())
    set_actor_contact_id(cid)
    try:
        user.name = "Staff Renamed"  # tracked UPDATE (User.__audit_track__)
        # Invoke the exact function the SQLAlchemy before_flush listener calls.
        audit_service._session_before_flush(db, None, None)
        audit_rows = [o for o in db.new if isinstance(o, AuditLog)]
        stamped = [
            r for r in audit_rows
            if r.entity_type == "users" and r.action == "UPDATE" and r.contact_id == cid
        ]
        assert stamped, "auto-flush audit row was not stamped with the actor contact id"
    finally:
        set_actor_contact_id(None)


# --------------------------------------------------------------------------- #
# _derive_description                                                           #
# --------------------------------------------------------------------------- #
def test_derive_description_status_transition():
    class _It:
        description = None
        old_values = {"status": "pending", "updated_at": "x"}
        new_values = {"status": "approved", "updated_at": "y"}

    from app.api.v1.audit.audit_logs import _derive_description

    assert _derive_description(_It()) == "status: pending → approved"


def test_derive_description_prefers_explicit_description():
    class _It:
        description = "Explicit note"
        old_values = {"status": "a"}
        new_values = {"status": "b"}

    from app.api.v1.audit.audit_logs import _derive_description

    assert _derive_description(_It()) == "Explicit note"


def test_derive_description_none_when_no_status_change():
    class _It:
        description = None
        old_values = {"name": "a"}
        new_values = {"name": "b"}

    from app.api.v1.audit.audit_logs import _derive_description

    assert _derive_description(_It()) is None


# --------------------------------------------------------------------------- #
# Endpoint: GET /api/v1/audit/logs/ display resolution + date filter          #
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(db):
    def _override_db():
        yield db

    app.dependency_overrides[app_database.get_db] = _override_db
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": "admin"}
    yield TestClient(app)
    app.dependency_overrides.clear()


BASE = datetime(2026, 7, 1, 10, 0, 0)


def _audit(db, *, minutes, user_id=None, contact_id=None, old=None, new=None):
    row = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="complaint",
        entity_id=str(uuid.uuid4()),
        action="UPDATE",
        user_id=user_id,
        contact_id=contact_id,
        old_values=old,
        new_values=new,
        changed_at=BASE - timedelta(minutes=minutes),
    )
    db.add(row)
    db.commit()
    return row


def test_endpoint_display_resolution(client, db):
    staff = User(
        id=str(uuid.uuid4()),
        email="jane@example.com",
        name="Jane Tan",
        status=UserStatus.ACTIVE.value,
    )
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number="+60123456789",
        name="Ali Contact",
        session_vars={},  # NOT NULL; server_default nulled for sqlite
    )
    db.add_all([staff, contact])
    db.commit()

    r_contact = _audit(db, minutes=1, user_id=None, contact_id=contact.id)
    r_staff = _audit(db, minutes=2, user_id=staff.id)
    r_system = _audit(db, minutes=3, user_id=None, contact_id=None)

    resp = client.get("/api/v1/audit/logs/")
    assert resp.status_code == 200, resp.text
    by_id = {it["id"]: it for it in resp.json()["data"]}

    assert by_id[r_contact.id]["user_display_name"] == "Ali Contact"
    assert by_id[r_staff.id]["user_display_name"] == "Jane Tan"
    assert by_id[r_system.id]["user_display_name"] == "System"


def test_endpoint_derives_status_description(client, db):
    row = _audit(
        db,
        minutes=1,
        user_id=None,
        old={"status": "submitted"},
        new={"status": "resolved"},
    )
    resp = client.get("/api/v1/audit/logs/")
    assert resp.status_code == 200
    it = next(i for i in resp.json()["data"] if i["id"] == row.id)
    assert it["description"] == "status: submitted → resolved"


def test_endpoint_changed_from_to_filter(client, db):
    old_row = _audit(db, minutes=60 * 48)  # 2 days ago
    recent = _audit(db, minutes=30)

    frm = (BASE - timedelta(hours=1)).isoformat()
    to = BASE.isoformat()
    resp = client.get(f"/api/v1/audit/logs/?changed_from={frm}&changed_to={to}")
    assert resp.status_code == 200
    ids = {i["id"] for i in resp.json()["data"]}
    assert recent.id in ids
    assert old_row.id not in ids
