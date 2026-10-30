"""`crm_report_ask` reaches the route with no period: the outstanding kinds leave both dates off (every date), and the
route (not a required MCP argument) enforces `period_required` for the sales bases."""
from __future__ import annotations

import pytest

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import TOOL_REQUIRED_QUERY_HINTS, _compile_tool

TOOL = "crm_report_ask"


class _Settings:
    crm_base_url = "http://crm.local"
    external_api_key = "test-key"


class _Ctx:
    def __init__(self, client) -> None:
        self.request_context = type("RC", (), {"lifespan_context": {"client": client, "settings": _Settings()}})()


class _Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def request(self, method, path, path_params=None, query=None, body=None, tool_name=None):
        self.calls.append({"path": path, "query": dict(query or {})})
        return '{"status":"ok","rows":[],"total":{"qty":0,"amount":0}}'


def test_the_period_is_not_a_required_argument_of_the_report_ask() -> None:
    assert TOOL_REQUIRED_QUERY_HINTS[TOOL] == ("contact_id", "space_id")


@pytest.mark.asyncio
async def test_an_outstanding_ask_with_no_dates_reaches_the_http_call() -> None:
    spec = next(s for s in CATALOG if s.name == TOOL)
    client = _Client()
    await _compile_tool(spec)(
        _Ctx(client), contact_id="900000008", space_id="364817", basis="outstanding", view="raw"
    )
    assert client.calls, "the ask never reached the route"
    assert "date_from" not in client.calls[0]["query"] and client.calls[0]["query"].get("basis") == "outstanding"
