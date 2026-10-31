"""Path parameters are substituted as exactly one URL segment.

Every catalog tool with a templated path (e.g. ``.../by-number/{number}``) goes through
``CRMClient.request``, so that is the single place a path value is rendered into the URL.
A value must only ever fill its own segment: it is percent-encoded with ``safe=''`` so
``?``, ``#``, ``%`` and spaces stay inside the segment.

Two cases cannot be made safe by encoding and are refused before any request is sent:

- a value containing ``/``: the backend's ASGI server percent-decodes ``%2F`` back to
  ``/`` before route matching, so an encoded slash still splits the segment there;
- a value that is ``.`` or ``..``: those characters are unreserved, so encoding leaves
  them alone and URL normalisation treats them as dot segments.

Empty or whitespace-only values are refused too (they would collapse the segment), and so
are control characters, which no identifier carries.
"""
import json

import httpx
import pytest

from sorento_crm_mcp.http_client import CRMClient
from sorento_crm_mcp.settings import Settings

TEMPLATE = "/api/v1/things/by-number/{number}"
PREFIX = "/api/v1/things/by-number/"


@pytest.fixture
def captured():
    return []


@pytest.fixture
def client(captured, monkeypatch):
    settings = Settings(crm_base_url="http://crm.test", external_api_key="test-key")
    crm = CRMClient(settings)

    async def fake_request(method, url, **kwargs):
        captured.append({"method": method, "url": url, "params": kwargs.get("params")})
        return httpx.Response(200, json={"ok": True}, request=httpx.Request(method, "http://crm.test" + url))

    monkeypatch.setattr(crm._client, "request", fake_request)
    return crm


def _final_path(url: str) -> str:
    """The path the request would actually hit, after httpx parsing/normalisation."""
    return httpx.URL("http://crm.test" + url).raw_path.decode("ascii").split("?", 1)[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value, encoded",
    [
        ("PR-0001", "PR-0001"),
        ("a?b=c", "a%3Fb%3Dc"),
        ("a#frag", "a%23frag"),
        ("100%", "100%25"),
        ("%2F", "%252F"),
        ("a b", "a%20b"),
        ("..x", "..x"),
        (12345, "12345"),
    ],
)
async def test_value_is_encoded_as_one_segment(client, captured, value, encoded):
    out = await client.get(TEMPLATE, path_params={"number": value}, tool_name="t")
    assert json.loads(out) == {"ok": True}
    assert captured[0]["url"] == PREFIX + encoded
    final = _final_path(captured[0]["url"])
    assert final == PREFIX + encoded
    # Still exactly one segment after the fixed prefix.
    assert "/" not in final[len(PREFIX):]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    ["a/b", "../../other", "/", "x/..", "..", ".", "", "   ", "\t", "a\x00b", "a\r\nb", "a\x7f"],
)
async def test_unsafe_or_empty_value_is_refused_without_a_request(client, captured, value):
    out = await client.get(TEMPLATE, path_params={"number": value}, tool_name="t")
    body = json.loads(out)
    assert body["error"] == "invalid_path_param"
    assert body["param"] == "number"
    assert body["status_code"] == 400
    assert captured == []


@pytest.mark.asyncio
async def test_post_path_params_are_encoded_too(client, captured):
    await client.post(
        "/api/v1/things/{thing_id}/close", path_params={"thing_id": "a?b"}, body={}, tool_name="t"
    )
    assert captured[0]["url"] == "/api/v1/things/a%3Fb/close"


@pytest.mark.asyncio
async def test_paramless_path_is_unchanged(client, captured):
    await client.get("/api/v1/external/stock", query={"q": "a/b?c"}, tool_name="t")
    await client.get("/api/v1/external/stock", path_params={}, tool_name="t")
    assert captured[0]["url"] == "/api/v1/external/stock"
    assert captured[0]["params"] == {"q": "a/b?c"}
    assert captured[1]["url"] == "/api/v1/external/stock"


@pytest.mark.asyncio
async def test_promotion_active_check_goes_through_the_encoder(client, captured):
    """`_ensure_promotion_active` used to build its URL with an f-string, outside the encoder."""
    from sorento_crm_mcp.server import _ensure_promotion_active

    await _ensure_promotion_active(client, "a?b")
    assert captured[0]["url"] == "/api/v1/marketing/promotions/a%3Fb"

    captured.clear()
    assert await _ensure_promotion_active(client, "x/y") is None
    assert captured == []
