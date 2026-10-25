"""Phase 2 RED tests - MCP catalog entries for logging a sales opportunity in chat (SALES-TARGET-CHAT slice 2).

`documentation/plans/sales/sales-opportunity-chat-25oct-acceptance-criteria.md` O4-1 and
PLAN-sales-opportunity-chat-25oct.md "Design (fixed for the tests)" (Backend routes, MCP). Written
before the ToolSpecs exist: `_spec` raises StopIteration for a missing tool, the module imports fine.
Run with `PYTHONPATH=$PWD` from `sorento_crm_mcp/`.
"""
from __future__ import annotations

import asyncio
import inspect
import json

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import _compile_tool

OPTIONS_TOOL = "crm_sales_opportunity_customer_options"
LOG_TOOL = "crm_sales_opportunity_log"

OPTIONS_PATH = "/api/v1/external/sales-opportunities/customer-options"
LOG_PATH = "/api/v1/external/sales-opportunities"

OPTIONS_QUERY_PARAMS = ("contact_id", "space_id", "q")
LOG_BODY_PARAMS = (
    "contact_id",
    "space_id",
    "customer_id",
    "prospect_name",
    "title",
    "expected_amount",
    "expected_close_date",
    "dry_run",
)


def _spec(name: str):
    return next(s for s in CATALOG if s.name == name)


class _Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def request(self, method, path, path_params=None, query=None, body=None, tool_name=None):
        self.calls.append({"method": method, "path": path, "query": query, "body": body})
        return json.dumps({"items": [], "prospect": True, "blocked": False})


class _Ctx:
    def __init__(self, client: _Client) -> None:
        settings = type("S", (), {"crm_base_url": "http://crm.local", "external_api_key": "k"})()
        self.request_context = type("RC", (), {"lifespan_context": {"client": client, "settings": settings}})()


def test_opportunity_tool_specs() -> None:
    options = _spec(OPTIONS_TOOL)
    assert options.path == OPTIONS_PATH, options.path
    assert options.method == "GET", options.method
    missing = [p for p in OPTIONS_QUERY_PARAMS if p not in options.query_params]
    assert not missing, f"missing query params {missing} (has {options.query_params})"
    assert options.body_params == (), options.body_params

    log = _spec(LOG_TOOL)
    assert log.path == LOG_PATH, log.path
    assert log.method == "POST", log.method
    # A WRITE: never declared read-only, so no chatbot allow-list can follow it in.
    assert log.read_only is False
    assert set(log.body_params) == set(LOG_BODY_PARAMS), log.body_params
    assert log.query_params == (), log.query_params


def test_the_options_tool_compiles_with_its_params() -> None:
    params = inspect.signature(_compile_tool(_spec(OPTIONS_TOOL))).parameters
    missing = [p for p in OPTIONS_QUERY_PARAMS if p not in params]
    assert not missing, sorted(params)


def test_the_log_tool_compiles_with_required_identity_and_optional_customer_or_prospect() -> None:
    params = inspect.signature(_compile_tool(_spec(LOG_TOOL))).parameters
    missing = [p for p in LOG_BODY_PARAMS if p not in params]
    assert not missing, sorted(params)
    # Contract: contact_id and space_id required; customer_id | null, prospect_name | null,
    # dry_run = false may be omitted.
    assert params["contact_id"].default is inspect.Parameter.empty
    assert params["space_id"].default is inspect.Parameter.empty
    for optional in ("customer_id", "prospect_name", "dry_run"):
        assert params[optional].default is None, (optional, params[optional].default)


def test_the_log_tool_posts_its_body_to_the_create_route() -> None:
    client = _Client()
    impl = _compile_tool(_spec(LOG_TOOL))

    asyncio.run(
        impl(
            _Ctx(client),
            contact_id="900000008",
            space_id="364817",
            title="condo job Taman X",
            expected_amount="40000",
            expected_close_date="2026-12-15",
            customer_id="0b5e0f5a-1111-4c1a-9a11-000000000001",
        )
    )

    (call,) = client.calls
    assert call["method"] == "POST", call
    assert call["path"] == LOG_PATH, call
    body = call["body"] or {}
    assert body.get("contact_id") == "900000008", body  # a numeric-looking id stays a string
    assert body.get("space_id") == "364817", body
    assert body.get("title") == "condo job Taman X", body
    assert body.get("expected_close_date") == "2026-12-15", body
    assert body.get("customer_id") == "0b5e0f5a-1111-4c1a-9a11-000000000001", body
