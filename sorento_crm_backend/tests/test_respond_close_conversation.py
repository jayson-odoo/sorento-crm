"""Unit tests for RespondClient.close_conversation.

Resolve = Respond close: resolving a conversation SLA best-effort closes the
contact's Respond.io conversation. These pin the wire contract (URL, id: prefix,
Bearer auth, closing-note body) and the best-effort swallow behavior.

Endpoint is POST .../conversation/status with body {"status": "close", ...} —
NOT a /conversation/close path (that 404s on Respond.io; see
RespondClient.close_conversation's own docstring). These tests originally
pinned the wrong (never-worked) path; updated to match the implementation.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.integration_service import RespondClient


def _client() -> RespondClient:
    return RespondClient(api_key="test-key", base_url="https://api.respond.io", space_id="364817")


def test_close_conversation_builds_correct_request():
    captured = {}

    class _Resp:
        content = b'{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class _HttpClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Resp()

    with patch("app.services.integration_service.httpx.Client", return_value=_HttpClient()):
        out = _client().close_conversation(
            "12345", category="Resolved", summary="done"
        )

    assert out == {"ok": True}
    assert captured["url"] == "https://api.respond.io/v2/contact/id:12345/conversation/status"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"] == {"status": "close", "category": "Resolved", "summary": "done"}


def test_close_conversation_omits_empty_note_fields():
    captured = {}

    class _Resp:
        content = b""

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class _HttpClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["json"] = json
            return _Resp()

    with patch("app.services.integration_service.httpx.Client", return_value=_HttpClient()):
        _client().close_conversation("phone:+60123")

    # No category/summary -> only the required status key (don't send keys the
    # workspace may reject).
    assert captured["json"] == {"status": "close"}


def test_close_conversation_keeps_existing_identifier_prefix():
    captured = {}

    class _Resp:
        content = b""

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class _HttpClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            return _Resp()

    with patch("app.services.integration_service.httpx.Client", return_value=_HttpClient()):
        _client().close_conversation("phone:+60123")

    # phone:/id: already present -> not double-prefixed.
    assert captured["url"].endswith("/v2/contact/phone:+60123/conversation/status")


def test_close_conversation_requires_api_key():
    # Constructor falls back to settings.respond_api_key; force-clear to assert guard.
    client = _client()
    client.api_key = None
    with pytest.raises(ValueError):
        client.close_conversation("12345")
