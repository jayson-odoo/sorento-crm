"""MCP -> CRM call attribution headers. Covers UAC OBS-S3-07.

Before this, the CRM could not tell an MCP call from an n8n call at all: both
authenticate with the same shared EXTERNAL_API_KEY and neither sent anything
else. Every external request landed in one undifferentiated bucket.

`X-Correlation-Id` is the piece that makes the two halves joinable — the client
already measured `elapsed_ms` but only wrote it to stdout, so network time and
server time could never be separated.
"""
import httpx
import pytest

from sorento_crm_mcp.http_client import CRMClient
from sorento_crm_mcp.settings import Settings


@pytest.fixture
def captured():
    return []


@pytest.fixture
def client(captured, monkeypatch):
    settings = Settings(crm_base_url="http://crm.test", external_api_key="test-key")
    crm = CRMClient(settings)

    async def fake_request(method, url, **kwargs):
        captured.append({"method": method, "url": url, "headers": kwargs.get("headers") or {}})
        return httpx.Response(200, json={"ok": True}, request=httpx.Request(method, url))

    monkeypatch.setattr(crm._client, "request", fake_request)
    return crm


@pytest.mark.asyncio
async def test_source_header_identifies_mcp(client, captured):
    await client.get("/api/v1/external/work-calendar", tool_name="work_calendar")
    assert captured[0]["headers"]["X-Source"] == "mcp"


@pytest.mark.asyncio
async def test_tool_name_is_sent(client, captured):
    await client.get("/api/v1/external/stock", tool_name="stock_balance")
    assert captured[0]["headers"]["X-Tool-Name"] == "stock_balance"


@pytest.mark.asyncio
async def test_tool_name_is_omitted_when_absent(client, captured):
    """An empty header is worse than none — it would store '' as a tool name."""
    await client.get("/api/v1/external/thing")
    assert "X-Tool-Name" not in captured[0]["headers"]


@pytest.mark.asyncio
async def test_correlation_id_is_present_and_unique_per_call(client, captured):
    await client.get("/api/v1/external/thing", tool_name="a")
    await client.get("/api/v1/external/thing", tool_name="b")

    first = captured[0]["headers"]["X-Correlation-Id"]
    second = captured[1]["headers"]["X-Correlation-Id"]
    assert first and second
    # Per-call, not per-client: a shared id would collapse every span into one.
    assert first != second


@pytest.mark.asyncio
async def test_api_key_header_is_still_sent(client, captured):
    """Per-request headers merge with the client defaults rather than replacing
    them — dropping X-API-Key here would 401 every MCP tool."""
    await client.get("/api/v1/external/thing", tool_name="a")
    # httpx.Headers is a case-insensitive mapping; dict() would lowercase the
    # keys and hide that the client default is still in place.
    assert client._client.headers["X-API-Key"] == "test-key"
    # The per-request headers carry only the attribution, never credentials.
    assert "X-API-Key" not in captured[0]["headers"]


@pytest.mark.asyncio
async def test_post_calls_are_attributed_too(client, captured):
    await client.post("/api/v1/external/thing", body={"a": 1}, tool_name="submit_thing")
    assert captured[0]["headers"]["X-Source"] == "mcp"
    assert captured[0]["headers"]["X-Tool-Name"] == "submit_thing"
