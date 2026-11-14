"""CHATBOT-SPEED: the Gemini model calls and the chatbot sender POST keep one open connection per process.

`GeminiProvider._request` called the module-level `httpx.request` and the inbox drain's sender POST called
`httpx.post`: both open a new TCP + TLS connection per call. Prod's parser and span calls are both Gemini since
4 Nov, so every turn paid at least two handshakes inside the model time, plus one on the send. They now go through
`http_keepalive.request` / `http_keepalive.post`, which reuse the process's shared client. A test that replaced the
module-level `httpx.request` / `httpx.post` (the seam about 15 test files fake) still gets its stand-in.
No network: `httpx.HTTPTransport.handle_request` is stubbed.
"""
from __future__ import annotations

import time

import httpx
import pytest

from app.services import http_keepalive
from app.services.llm_provider import GeminiProvider


@pytest.fixture
def wire(monkeypatch):
    seen: dict[str, list] = {"clients": [], "requests": []}
    real_init = httpx.Client.__init__

    def init(self, *a, **k):
        seen["clients"].append(self)
        real_init(self, *a, **k)

    def handle(self, request):
        seen["requests"].append(request)
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(httpx.Client, "__init__", init)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    http_keepalive.reset()
    yield seen
    http_keepalive.reset()


def test_two_gemini_calls_share_one_connection(wire):
    provider = GeminiProvider("zz-test-key")
    provider._request("POST", "models/zz:generateContent", json_body={"a": 1}, timeout=5.0)
    provider._request("POST", "models/zz:generateContent", json_body={"a": 2}, timeout=5.0)
    assert len(wire["requests"]) == 2
    assert len(wire["clients"]) == 1, "each Gemini call opened a new connection (no keep-alive)"


def test_a_gemini_call_keeps_its_headers_and_timeout(wire):
    GeminiProvider("zz-test-key")._request("POST", "models/zz:generateContent", json_body={}, timeout=5.0)
    request = wire["requests"][0]
    assert request.headers["x-goog-api-key"] == "zz-test-key"
    assert request.extensions["timeout"]["read"] == 5.0


def test_a_patched_httpx_request_is_still_the_gemini_seam(wire, monkeypatch):
    calls = []

    def fake(method, url, **kwargs):
        calls.append((method, url))
        return httpx.Response(200, json={"fake": True}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake)
    assert GeminiProvider("zz-test-key")._request("GET", "models") == {"fake": True}
    assert len(calls) == 1 and wire["clients"] == []


def test_two_posts_share_one_connection_and_keep_follow_redirects_off(wire):
    http_keepalive.post("sender", "https://zz-sender.invalid/hook", json={"a": 1}, timeout=5.0, follow_redirects=False)
    http_keepalive.post("sender", "https://zz-sender.invalid/hook", json={"a": 2}, timeout=5.0, follow_redirects=False)
    assert len(wire["clients"]) == 1 and len(wire["requests"]) == 2


def test_a_patched_httpx_post_is_still_the_sender_seam(wire, monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "post", lambda url, **kw: calls.append(url) or httpx.Response(200))
    http_keepalive.post("sender", "https://zz-sender.invalid/hook", json={}, timeout=5.0)
    assert calls == ["https://zz-sender.invalid/hook"] and wire["clients"] == []
