"""An API-key write is attributed to the key, not to "System" (#1281 S0, AC-S0-11).

`get_current_user_or_api_key` is a sync dependency. FastAPI runs it on a COPIED context in a
threadpool, so the old `set_audit_context(...)` inside it (a contextvar `.set()`) was lost before
the endpoint ran, and every audited write behind it recorded `user_id = NULL`. The report on
#1281 inferred this from the code; this test drives the real dependency with a real integration
key to prove it and to pin the fix (the mutable `AuditContext`).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.main  # noqa: F401
from app.audit_context import set_actor_contact_id, set_audit_context, set_trace_id
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.middleware.logging_middleware import LoggingMiddleware
from app.models.audit import AuditLog
from app.models.integration import Integration
from app.models.product import Brand
from app.models.user import User
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from app.services.integration_key_service import IntegrationKeyService

from ._pg_fixture import blank_session, unique_code


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    set_audit_context(None, None)
    set_trace_id(None)
    set_actor_contact_id(None)


def _app(db, made):
    probe = FastAPI()
    probe.add_middleware(LoggingMiddleware)

    def _db():
        yield db

    probe.dependency_overrides[get_db] = _db

    @probe.post("/api/v1/{path:path}")
    def write(path: str, user=Depends(get_current_user_or_api_key), session=Depends(get_db)):
        b = Brand(brand_code=unique_code("K")[:50], brand_name="Keyed")
        session.add(b)
        session.flush()
        made["id"] = b.id
        return {}

    return TestClient(probe)


@pytest.mark.parametrize(
    "integration_type,path,source",
    [
        ("automation", "master-data/x", "n8n"),
        ("mcp", "master-data/x", "mcp"),
        ("autocount_esb", "master-data/x", "external_api"),
        ("automation", "external/chat/turn", "chatbot"),
    ],
)
def test_ac_s0_11_api_key_write_names_the_key_and_its_user(integration_type, path, source):
    with blank_session() as db:
        principal = User(
            email=f"{uuid.uuid4().hex}@integrations.local", name="Integration", status="ACTIVE",
            is_integration=True,
        )
        db.add(principal)
        db.flush()
        integration = Integration(
            name=unique_code("int"), type=integration_type, act_as_user_id=principal.id
        )
        db.add(integration)
        db.flush()
        key = IntegrationKeyService(db).issue_key(integration)

        made = {}
        r = _app(db, made).post(f"/api/v1/{path}", headers={"X-API-Key": key})
        assert r.status_code == 200, r.text

        (row,) = db.query(AuditLog).filter(AuditLog.entity_id == made["id"]).all()
        assert row.user_id == principal.id
        assert (row.principal_type, row.principal_id) == ("api_key", integration.id)
        assert row.source == source


def test_ac_s0_10_real_api_key_dependency_keeps_the_user_on_an_audited_write():
    """The bug alone, on a table main already audits (customers): user_id must not be NULL."""
    from app.models.order import Customer

    with blank_session() as db:
        principal = User(
            email=f"{uuid.uuid4().hex}@integrations.local", name="Integration", status="ACTIVE",
            is_integration=True,
        )
        db.add(principal)
        db.flush()
        integration = Integration(name=unique_code("int"), type="automation", act_as_user_id=principal.id)
        db.add(integration)
        db.flush()
        key = IntegrationKeyService(db).issue_key(integration)

        probe = FastAPI()
        probe.add_middleware(LoggingMiddleware)

        def _db():
            yield db

        probe.dependency_overrides[get_db] = _db
        made = {}

        @probe.post("/w")
        def write(user=Depends(get_current_user_or_api_key), session=Depends(get_db)):
            c = Customer(customer_code=unique_code("C")[:50], customer_name="Keyed Co")
            session.add(c)
            session.flush()
            made["id"] = c.id
            return {}

        assert TestClient(probe).post("/w", headers={"X-API-Key": key}).status_code == 200
        (row,) = db.query(AuditLog).filter(AuditLog.entity_id == made["id"]).all()
        assert row.user_id == principal.id
