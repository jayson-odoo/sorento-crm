"""CHATBOT-SPEED: the respond.io client keeps one open connection per process.

Every inbox turn makes a respond.io contact lookup for the takeover check before the engine starts
(`inbox_queue._run_row` -> `direct_ingress._lookup_contact`). `RespondClient._http` built a new `httpx.Client` per
call, so each turn paid a fresh TLS handshake to respond.io. `_http` now lends a shared client (per timeout), still
counted by `respond_call_counter`, still closed by nobody. No network: `httpx.HTTPTransport.handle_request` is stubbed.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services import http_keepalive, respond_call_counter
from app.services.integration_service import RespondClient


def _client() -> RespondClient:
    return RespondClient(api_key="test-key", base_url="https://api.respond.io", space_id="364817")


@pytest.fixture
def transport(monkeypatch):
    seen: dict[str, list] = {"clients": [], "requests": [], "counted": []}
    real_init = httpx.Client.__init__

    def init(self, *a, **k):
        seen["clients"].append(self)
        real_init(self, *a, **k)

    def handle(self, request):
        # Stubbed at the transport, under `Client.send`, so the client's event hooks (the call counter) still run.
        seen["requests"].append((self, request))
        return httpx.Response(200, json={"id": 1}, request=request)

    monkeypatch.setattr(httpx.Client, "__init__", init)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    monkeypatch.setattr(respond_call_counter, "record", lambda method, url: seen["counted"].append(str(url)))
    http_keepalive.reset()
    yield seen
    http_keepalive.reset()


def test_two_lookups_share_one_client(transport):
    _client().get_contact_by_identifier("id:1")
    _client().get_contact_by_identifier("id:2")
    assert len(transport["requests"]) == 2
    assert len(transport["clients"]) == 1, "each respond.io call opened a new connection (no keep-alive)"


def test_the_shared_client_is_not_closed_after_a_call(transport):
    _client().get_contact_by_identifier("id:1")
    assert transport["clients"][0].is_closed is False


def test_every_call_is_still_counted(transport):
    _client().get_contact_by_identifier("id:1")
    _client().get_contact_by_identifier("id:2")
    assert len(transport["counted"]) == 2


def test_each_timeout_keeps_its_own_value(transport):
    _client().get_contact_by_identifier("id:1")  # 15 s
    _client().list_contacts(limit=1)  # 30 s
    reads = [r.extensions["timeout"]["read"] for _, r in transport["requests"]]
    assert reads == [15, 30]


def test_a_patched_constructor_gets_its_fake_not_a_cached_client(transport):
    """Tests that replace `httpx.Client` (e.g. tests/test_respond_close_conversation.py) still reach their fake."""
    _client().get_contact_by_identifier("id:1")  # caches a real client

    class _Fake:
        def get(self, url, headers=None):
            return httpx.Response(200, json={"fake": True}, request=httpx.Request("GET", url))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("app.services.integration_service.httpx.Client", return_value=_Fake()):
        assert _client().get_contact_by_identifier("id:2") == {"fake": True}


def test_a_cookie_one_call_got_is_never_sent_on_the_next(monkeypatch):
    """The per-call client threw cookies away; a shared one must too, or a respond.io / CloudFront Set-Cookie from one
    workspace's call would ride along on every later call in the process (reviewer, 12 Nov)."""
    sent: list[str | None] = []

    def handle(self, request):
        sent.append(request.headers.get("cookie"))
        return httpx.Response(200, json={"id": 1}, headers={"set-cookie": "zzt_waf=abc; Path=/"}, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    http_keepalive.reset()
    try:
        _client().get_contact_by_identifier("id:1")
        _client().get_contact_by_identifier("id:2")
    finally:
        http_keepalive.reset()
    assert sent == [None, None], sent
