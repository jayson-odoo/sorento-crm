"""Sub-plan B — presigned-URL object-level hardening.

The endpoint used to sign ANY file_path off the shared X-API-Key (IDOR). Now it
only signs a key that resolves to a real attachments row, clamps the TTL, and
audits each presign. The attachment-row requirement is toggleable via settings
as an escape hatch for legit n8n keys with no row.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.dependencies import get_db, get_external_api_user
from tests._external_auth import external_permissions_granted


@pytest.fixture
def client():
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "act-as-user"}

    def _db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _db
    # Authorization is deliberately out of scope here: this suite mocks the
    # database, so the real RBAC lookup cannot answer. Enforcement is covered
    # by test_external_permission_guard / _coverage.
    with external_permissions_granted():
        yield TestClient(app)
    app.dependency_overrides.clear()


_FAKE_ATT = SimpleNamespace(id="att-1", storage_provider="s3")


def _backend():
    b = MagicMock()
    b.get_signed_url.return_value = "https://cdn.example/signed?Policy=x&Key-Pair-Id=y"
    return b


@patch("app.api.v1.external.presigned_url.get_backend")
@patch("app.api.v1.external.presigned_url._entity_link_for", return_value="promotion:p1")
@patch("app.api.v1.external.presigned_url._resolve_attachment", return_value=_FAKE_ATT)
def test_signs_when_attachment_exists(mock_resolve, mock_link, mock_backend, client):
    mock_backend.return_value = _backend()
    r = client.post(
        "/api/v1/external/presigned-url/",
        json={"file_path": "promotion/p1/flyer.pdf", "expires_in": 600},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["presigned_url"].startswith("https://")
    assert body["file_path"] == "promotion/p1/flyer.pdf"
    assert body["expires_in"] == 600
    assert body["storage_provider"] == "s3"


@patch("app.api.v1.external.presigned_url.get_backend")
@patch("app.api.v1.external.presigned_url._resolve_attachment", return_value=None)
def test_404_when_no_attachment_row_and_required(mock_resolve, mock_backend, client):
    assert settings.presigned_require_attachment_row is True
    r = client.post(
        "/api/v1/external/presigned-url/",
        json={"file_path": "totally/made/up/key.pdf", "expires_in": 600},
    )
    assert r.status_code == 404
    mock_backend.assert_not_called()  # never signed an unknown key


@patch("app.api.v1.external.presigned_url.get_backend")
@patch("app.api.v1.external.presigned_url._entity_link_for", return_value="-")
@patch("app.api.v1.external.presigned_url._resolve_attachment", return_value=_FAKE_ATT)
def test_ttl_clamped_to_max(mock_resolve, mock_link, mock_backend, client):
    b = _backend()
    mock_backend.return_value = b
    r = client.post(
        "/api/v1/external/presigned-url/",
        json={"file_path": "promotion/p1/flyer.pdf", "expires_in": 86400},
    )
    assert r.status_code == 200
    assert r.json()["expires_in"] == settings.presigned_max_ttl_seconds
    # The backend was asked to sign with the CLAMPED ttl, not 86400.
    _, kwargs = b.get_signed_url.call_args
    assert kwargs["expires_in"] == settings.presigned_max_ttl_seconds


@patch("app.api.v1.external.presigned_url.get_backend")
@patch("app.api.v1.external.presigned_url._entity_link_for", return_value="-")
@patch("app.api.v1.external.presigned_url._resolve_attachment", return_value=None)
def test_escape_hatch_allows_missing_row(mock_resolve, mock_link, mock_backend, client, monkeypatch):
    monkeypatch.setattr(settings, "presigned_require_attachment_row", False)
    mock_backend.return_value = _backend()
    r = client.post(
        "/api/v1/external/presigned-url/",
        json={"file_path": "legacy/key/no-row.pdf", "expires_in": 300},
    )
    assert r.status_code == 200
