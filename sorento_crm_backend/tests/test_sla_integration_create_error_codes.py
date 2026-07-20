"""POST /conversation-sla-tracking/integration — error-code propagation.

Covers UAC OBS-S1-05b.

This is the endpoint n8n calls to open a conversation SLA. A deliberate refusal
from the service — "Respond contact not found for phone number: X" — is raised as
an `AppException` carrying 400 / VALIDATION_ERROR, but the route's bare
`except Exception: raise handle_internal_error(str(e))` re-wrapped it into
500 / INTERNAL_ERROR. The caller was told the server broke when in fact its input
was rejected, and the real message survived only as a string stuffed inside the
500 body.

Same bug class already fixed in create_/update_/delete_sla_tracking; this handler
was missed because it is a separate function.

`HTTPException` is covered too: it is a subclass of `Exception`, so a deliberate
404/403 raised inside the try was being flattened to 500 by the same arm.
"""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db as database_get_db
from app.dependencies import (
    get_db as dependencies_get_db,
    get_current_user,
    get_current_user_or_api_key,
)
from app.services.error_handler import handle_not_found, handle_validation_error
import app.api.v1.sla.sla_tracking as mod

ENDPOINT = "/api/v1/sla-management/conversation-sla-tracking/integration"

PAYLOAD = {
    "respond_contact_id": "00000000-0000-0000-0000-000000000000",
    "agent_code": "AGENT",
    "team_set_code": "TEAM",
    "contact_phone_number": "+60100000000",
}


@pytest.fixture
def client():
    """The SLA router sits behind the module guard; satisfy both principals."""
    def _user():
        return {"id": "system", "auth_method": "api_key"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_current_user_or_api_key] = _user
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[database_get_db] = _db
    app.dependency_overrides[dependencies_get_db] = _db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _raise(exc):
    def _inner(*_a, **_k):
        raise exc
    return _inner


def test_service_validation_refusal_surfaces_as_400(client, monkeypatch):
    """The live symptom: a not-found contact returned 500 INTERNAL_ERROR."""
    monkeypatch.setattr(
        mod.ConversationSLATrackingService,
        "create_tracking",
        _raise(handle_validation_error("Respond contact not found for phone number: +60100000000")),
    )
    r = client.post(ENDPOINT, json=PAYLOAD)

    assert r.status_code == 400
    body = r.json()
    assert "Respond contact not found" in str(body)
    # The old behaviour buried the real 400 inside an INTERNAL_ERROR envelope.
    assert body.get("code") != "INTERNAL_ERROR"


def test_not_found_refusal_surfaces_as_404(client, monkeypatch):
    monkeypatch.setattr(
        mod.ConversationSLATrackingService,
        "create_tracking",
        _raise(handle_not_found("SLA policy", "00000000-0000-0000-0000-000000000000")),
    )
    assert client.post(ENDPOINT, json=PAYLOAD).status_code == 404


def test_http_exception_is_not_flattened_to_500(client, monkeypatch):
    """HTTPException subclasses Exception, so the bare arm caught it too."""
    monkeypatch.setattr(
        mod.ConversationSLATrackingService,
        "create_tracking",
        _raise(HTTPException(status_code=403, detail="nope")),
    )
    assert client.post(ENDPOINT, json=PAYLOAD).status_code == 403


def test_a_genuine_crash_is_still_a_500(client, monkeypatch):
    """The narrowing must not swallow real faults — that would be the opposite
    regression, hiding a broken server behind a 4xx."""
    monkeypatch.setattr(
        mod.ConversationSLATrackingService,
        "create_tracking",
        _raise(RuntimeError("database on fire")),
    )
    r = client.post(ENDPOINT, json=PAYLOAD)
    assert r.status_code == 500
    assert r.json().get("code") == "INTERNAL_ERROR"


def test_schema_validation_still_returns_422(client):
    """Unchanged: a malformed body is rejected by FastAPI before the handler."""
    assert client.post(ENDPOINT, json={"respond_contact_id": "x"}).status_code == 422
