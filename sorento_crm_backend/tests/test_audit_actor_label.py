"""AC-13 (BE half): `GET /api/v1/audit/logs/` renders the actor as words.

`documentation/plans/identity/s0-contract.md` section 5. `AuditLogResponse` does not
carry `actor_type` / `auth_method` / `real_user_id` / `integration_id` / `job_id` /
`actor_label` yet, and `AuditLog` has no columns to seed them from - each case below
either fails constructing its own row (`TypeError`, an invalid keyword) or fails
reading a response field that is not there. One test per row of the contract's
table, so a partial implementation shows partial green.
"""
from __future__ import annotations

import re
import uuid

from fastapi.testclient import TestClient

import app.main  # noqa: F401  registers routers
from app.dependencies import get_current_user_or_api_key
from app.main import app
from app.models.access import RespondContact
from app.models.audit import AuditLog
from app.models.integration import Integration
from app.models.user import User
from tests._pg_fixture import blank_session, unique_code

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def _seed_user(db, *, name: str) -> User:
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('u')}@example.com".lower(), name=name, status="ACTIVE")
    db.add(user)
    db.flush()
    return user


def _seed_contact(db, *, name: str) -> RespondContact:
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"+6011{uuid.uuid4().int % 10_000_000:07d}", name=name)
    db.add(contact)
    db.flush()
    return contact


def _fetch_row(client, entity_id: str) -> dict:
    resp = client.get("/api/v1/audit/logs/", params={"entity_id": entity_id})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1, data
    return data[0]


def _client_for(db):
    from app.database import get_db

    def _override_db():
        yield db

    def _override_user():
        return {"id": "zzt-staff", "email": "staff@example.com", "name": "Staff"}

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_or_api_key] = _override_user
    return TestClient(app)


def _teardown(app_):
    app_.dependency_overrides.clear()


def test_actor_label_user_with_phone_otp_shows_name_and_method_word():
    with blank_session() as db:
        aisyah = _seed_user(db, name="Aisyah")
        entity_id = str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=entity_id, action="UPDATE",
                actor_type="user", user_id=aisyah.id, real_user_id=aisyah.id, auth_method="phone_otp",
            )
        )
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "Aisyah (phone)"


def test_actor_label_impersonation_shows_on_behalf_of():
    with blank_session() as db:
        aisyah = _seed_user(db, name="Aisyah")
        nurain = _seed_user(db, name="Nurain")
        entity_id = str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=entity_id, action="UPDATE",
                actor_type="user", user_id=aisyah.id, real_user_id=nurain.id, auth_method="impersonation",
            )
        )
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "Nurain on behalf of Aisyah"


def test_actor_label_integration_shows_integration_and_act_as_user():
    with blank_session() as db:
        act_as = _seed_user(db, name="Ops Bot")
        integration = Integration(id=str(uuid.uuid4()), name="n8n", type="automation", act_as_user_id=act_as.id, is_active=True)
        db.add(integration)
        db.flush()
        entity_id = str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=entity_id, action="UPDATE",
                actor_type="integration", user_id=act_as.id, integration_id=integration.id, auth_method="api_key",
            )
        )
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "Integration: n8n as Ops Bot"


def test_actor_label_worker_shows_background_job_for_user():
    with blank_session() as db:
        aisyah = _seed_user(db, name="Aisyah")
        entity_id = str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=entity_id, action="UPDATE",
                actor_type="worker", user_id=aisyah.id, job_id="job-1",
            )
        )
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "Background job for Aisyah"


def test_actor_label_scheduler_shows_scheduled_and_job_id():
    with blank_session() as db:
        entity_id = str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=entity_id, action="UPDATE",
                actor_type="scheduler", job_id="daily-reorder-run",
            )
        )
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "Scheduled: daily-reorder-run"


def test_actor_label_contact_with_no_user_shows_portal_no_user():
    with blank_session() as db:
        contact = _seed_contact(db, name="Aisyah")
        entity_id = str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=entity_id, action="UPDATE",
                actor_type="contact", contact_id=contact.id, auth_method="portal_token",
            )
        )
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "Portal: Aisyah (no user)"


def test_actor_label_public_link():
    with blank_session() as db:
        entity_id = str(uuid.uuid4())
        db.add(AuditLog(entity_type="users", entity_id=entity_id, action="UPDATE", actor_type="public_link"))
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "Public link"


def test_actor_label_system():
    with blank_session() as db:
        entity_id = str(uuid.uuid4())
        db.add(AuditLog(entity_type="users", entity_id=entity_id, action="UPDATE", actor_type="system"))
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "System"


def test_actor_label_legacy_falls_back_to_user_display_name():
    with blank_session() as db:
        someone = _seed_user(db, name="Legacy Someone")
        entity_id = str(uuid.uuid4())
        # No actor_type at all - the pre-S0 shape (server_default 'legacy').
        db.add(AuditLog(entity_type="users", entity_id=entity_id, action="UPDATE", user_id=someone.id))
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert row["actor_label"] == "Legacy Someone"


def test_no_actor_label_is_ever_a_bare_uuid():
    with blank_session() as db:
        aisyah = _seed_user(db, name="Aisyah")
        nurain = _seed_user(db, name="Nurain")
        entity_id = str(uuid.uuid4())
        db.add(
            AuditLog(
                entity_type="users", entity_id=entity_id, action="UPDATE",
                actor_type="user", user_id=aisyah.id, real_user_id=nurain.id, auth_method="impersonation",
            )
        )
        db.commit()
        client = _client_for(db)
        try:
            row = _fetch_row(client, entity_id)
        finally:
            _teardown(app)
        assert not _UUID_RE.search(row["actor_label"] or ""), row["actor_label"]
