"""The CRM client never carries its X-API-Key to another origin on a redirect.

httpx strips `Authorization` on a cross-origin redirect but not a custom header, so with
`follow_redirects=True` a 3xx pointing at another host would have received the shared
X-API-Key. Same-origin redirects (FastAPI's trailing-slash 307) keep working.
"""
import json

import httpx
import pytest

from sorento_crm_mcp.http_client import CRMClient
from sorento_crm_mcp.settings import Settings


def _client(handler) -> CRMClient:
    settings = Settings(crm_base_url="http://crm.test", external_api_key="secret-key")
    return CRMClient(settings, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location",
    [
        "http://evil.test/steal",
        "https://crm.test/api/v1/external/thing",  # scheme change is another origin
        "http://crm.test:8080/api/v1/external/thing",  # port change is another origin
    ],
)
async def test_cross_origin_redirect_is_refused_and_key_not_sent(location):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "crm.test" and request.url.port in (None, 80) and request.url.scheme == "http":
            return httpx.Response(302, headers={"Location": location})
        return httpx.Response(200, json={"leaked": request.headers.get("X-API-Key")})

    crm = _client(handler)
    try:
        out = json.loads(await crm.get("/api/v1/external/thing", tool_name="t"))
    finally:
        await crm.aclose()

    assert len(seen) == 1, f"redirect target was contacted: {[str(r.url) for r in seen]}"
    assert out["error"] == "request_failed"
    assert out["error_type"] == "CrossOriginRedirectRefused"
    assert "secret-key" not in json.dumps(out)


@pytest.mark.asyncio
async def test_same_origin_redirect_is_followed_with_key():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/external/thing":
            return httpx.Response(307, headers={"Location": "/api/v1/external/thing/"})
        return httpx.Response(200, json={"ok": True})

    crm = _client(handler)
    try:
        out = json.loads(await crm.get("/api/v1/external/thing"))
    finally:
        await crm.aclose()

    assert out == {"ok": True}
    assert [r.url.path for r in seen] == ["/api/v1/external/thing", "/api/v1/external/thing/"]
    assert all(r.headers.get("X-API-Key") == "secret-key" for r in seen)


@pytest.mark.asyncio
async def test_https_base_redirect_down_to_http_is_refused():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.scheme == "https":
            return httpx.Response(301, headers={"Location": "http://crm.test/api/v1/external/thing"})
        return httpx.Response(200, json={"leaked": request.headers.get("X-API-Key")})

    settings = Settings(crm_base_url="https://crm.test", external_api_key="secret-key")
    crm = CRMClient(settings, transport=httpx.MockTransport(handler))
    try:
        out = json.loads(await crm.get("/api/v1/external/thing"))
    finally:
        await crm.aclose()

    assert len(seen) == 1
    assert out["error_type"] == "CrossOriginRedirectRefused"
