"""Meta-log removal — POST /api/v1/integrations/logs/{log_id}/status (WS1a).

The callback endpoint updates the ORIGINAL log's status from the body (success
AND failed) and must NOT write a secondary `integration_log_update` meta-log row
(it previously hardcoded a success meta-log, blinding the health dashboard).

Endpoint test: TestClient hits the real route with an sqlite-backed session.
The route itself carries no auth dependency, but the router-level module guard
resolves get_current_user_or_api_key, so we override that + get_db.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON

from app.main import app  # noqa: E402  (import first to settle app wiring)
import app.database as app_database
from app.database import Base
from app.dependencies import get_current_user_or_api_key
from app.models.integration import IntegrationLog
from app.models.lookup import LookupBinding


def _prep(*models):
    for model in models:
        for col in model.__table__.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                col.type = JSON()
                col.server_default = None


@pytest.fixture
def db():
    _prep(IntegrationLog, LookupBinding)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine, tables=[IntegrationLog.__table__, LookupBinding.__table__]
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db):
    def _override_db():
        yield db

    app.dependency_overrides[app_database.get_db] = _override_db
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": "admin"}
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_log(db):
    log = IntegrationLog(
        id=str(uuid.uuid4()),
        integration_channel="respond_io",
        business_table="attachments",
        business_id=str(uuid.uuid4()),
        direction="outbound",
        endpoint="https://example.invalid/webhook",
        http_method="POST",
        status="sent",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def test_status_callback_marks_original_failed_no_meta_log(client, db):
    log = _seed_log(db)

    r = client.post(
        f"/api/v1/integrations/logs/{log.id}/status",
        json={"status": "failed", "error_code": "E1", "error_message": "downstream"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "success"  # endpoint envelope

    db.expire_all()
    # Original log flipped to failed from the body.
    updated = db.query(IntegrationLog).filter(IntegrationLog.id == log.id).one()
    assert updated.status == "failed"
    assert updated.error_code == "E1"
    assert updated.processed_at is not None

    # No secondary meta-log channel row was created.
    all_logs = db.query(IntegrationLog).all()
    assert len(all_logs) == 1
    assert all(l.integration_channel != "integration_log_update" for l in all_logs)


def test_status_callback_marks_original_success_no_meta_log(client, db):
    log = _seed_log(db)

    r = client.post(
        f"/api/v1/integrations/logs/{log.id}/status",
        json={"status": "success"},
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    updated = db.query(IntegrationLog).filter(IntegrationLog.id == log.id).one()
    assert updated.status == "success"
    assert updated.processed_at is not None
    assert db.query(IntegrationLog).count() == 1
