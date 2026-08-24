"""ApiCallLogMiddleware - total coverage of /api/v1/external/* by construction.

Covers UAC OBS-S3-02, OBS-S3-03, OBS-S3-05, OBS-S3-11.

Driven against a throwaway ASGI app rather than the real one: the claim under
test is that the MIDDLEWARE logs any external route, which is only demonstrated
if the route is one the middleware has never seen. Mounting the real app would
prove the routes work, not that coverage is automatic.

The `test_a_brand_new_route_is_logged` case is the whole point of the slice  - 
today logging is opt-in per endpoint and 27 of ~30 external routes forgot.
"""
import json

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.testclient import TestClient

from app.middleware.api_call_log_middleware import ApiCallLogMiddleware


@pytest.fixture
def written():
    """Captured rows, in place of a database."""
    return []


@pytest.fixture
def client(written, monkeypatch):
    import app.services.api_call_log_service as svc

    monkeypatch.setattr(svc, "write_call_log", lambda db, **fields: written.append(fields))
    # The middleware opens its own session; make that a no-op.
    import app.middleware.api_call_log_middleware as mw

    class _Session:
        def close(self):
            pass

    monkeypatch.setattr("app.database.SessionLocal", lambda: _Session())

    router = APIRouter()

    @router.post("/api/v1/external/brand-new-route")
    async def brand_new(payload: dict):
        return {"ok": True, "echo": payload.get("echo")}

    @router.get("/api/v1/external/boom")
    async def boom():
        raise RuntimeError("kaboom")

    @router.get("/api/v1/external/not-found")
    async def not_found():
        return JSONResponse({"detail": "nope"}, status_code=404)

    @router.get("/api/v1/external/plain")
    async def plain():
        return PlainTextResponse("hello")

    @router.get("/api/v1/system/health/summary")
    async def internal():
        return {"ok": True}

    @router.get("/api/v1/master-data/products")
    async def internal_but_mcp_reachable():
        return {"data": []}

    application = FastAPI()
    application.include_router(router)
    application.add_middleware(ApiCallLogMiddleware)
    return TestClient(application, raise_server_exceptions=False)


# --------------------------------------------------------------------------- #
# Coverage                                                                     #
# --------------------------------------------------------------------------- #
def test_a_brand_new_route_is_logged(client, written):
    """OBS-S3-03. This route has no logging code of its own and the middleware
    has no knowledge of it - that is exactly the condition that failed before."""
    r = client.post("/api/v1/external/brand-new-route", json={"echo": "hi"})
    assert r.status_code == 200
    assert len(written) == 1
    assert written[0]["endpoint"] == "/api/v1/external/brand-new-route"
    assert written[0]["method"] == "POST"


def test_exactly_one_row_per_request(client, written):
    for _ in range(3):
        client.post("/api/v1/external/brand-new-route", json={"echo": "x"})
    assert len(written) == 3


def test_mcp_calls_to_NON_external_routes_are_logged(client, written):
    """Found in verification, not by a test: MCP tools mostly proxy ordinary CRM
    endpoints - the products catalogue is /api/v1/master-data/*, not
    /api/v1/external/*. Scoping on the path prefix alone silently missed most
    MCP traffic while the client was sending full attribution."""
    client.get(
        "/api/v1/master-data/products",
        headers={"X-Source": "mcp", "X-Tool-Name": "crm_master_products_list"},
    )
    assert len(written) == 1
    assert written[0]["source"] == "mcp"
    assert written[0]["tool_name"] == "crm_master_products_list"


def test_same_route_without_attribution_is_not_logged(client, written):
    """The UI hits this route constantly. Only self-identifying callers get
    recorded, or the table fills with its own application's traffic."""
    client.get("/api/v1/master-data/products")
    assert written == []


def test_internal_routes_are_not_logged(client, written):
    """Scope discipline: logging /api/v1/* would record the health dashboard's own
    polling and the log page's own reads, feeding the table its own traffic."""
    client.get("/api/v1/system/health/summary")
    assert written == []


def test_downstream_still_receives_the_body(client, written):
    """The middleware buffers the request body; if it failed to replay it the
    handler would see an empty body and 422."""
    r = client.post("/api/v1/external/brand-new-route", json={"echo": "round-trip"})
    assert r.status_code == 200
    assert r.json()["echo"] == "round-trip"


# --------------------------------------------------------------------------- #
# What gets recorded                                                           #
# --------------------------------------------------------------------------- #
def test_request_and_response_payloads_are_captured(client, written):
    client.post("/api/v1/external/brand-new-route", json={"echo": "hi"})
    row = written[0]
    assert "hi" in row["request_payload"]
    assert "ok" in row["response_payload"]


def test_secret_header_never_reaches_the_row(client, written):
    """Headers are not persisted at all, which is the strongest version of this
    guarantee - assert it rather than trusting it."""
    client.post(
        "/api/v1/external/brand-new-route",
        json={"echo": "hi"},
        headers={"X-API-Key": "super-secret-key"},
    )
    assert "super-secret-key" not in json.dumps(written[0], default=str)


def test_secret_in_the_request_body_is_redacted(client, written):
    client.post("/api/v1/external/brand-new-route", json={"echo": "hi", "password": "hunter2"})
    assert "hunter2" not in written[0]["request_payload"]


def test_latency_is_recorded(client, written):
    client.post("/api/v1/external/brand-new-route", json={"echo": "hi"})
    assert written[0]["latency_ms"] is not None
    assert written[0]["latency_ms"] >= 0


def test_mcp_headers_are_attributed(client, written):
    """OBS-S3-05. Today MCP and n8n share one EXTERNAL_API_KEY and are otherwise
    indistinguishable."""
    client.post(
        "/api/v1/external/brand-new-route",
        json={"echo": "hi"},
        headers={
            "X-Source": "mcp",
            "X-Tool-Name": "stock_balance",
            "X-Correlation-Id": "corr-123",
        },
    )
    row = written[0]
    assert row["source"] == "mcp"
    assert row["tool_name"] == "stock_balance"
    assert row["correlation_id"] == "corr-123"


def test_missing_source_header_still_writes_a_row(client, written):
    client.post("/api/v1/external/brand-new-route", json={"echo": "hi"})
    assert written[0]["source"] == "unknown"


# --------------------------------------------------------------------------- #
# Failure paths                                                                #
# --------------------------------------------------------------------------- #
def test_4xx_is_logged_as_client_error(client, written):
    client.get("/api/v1/external/not-found")
    assert written[0]["status_code"] == 404
    assert written[0]["outcome"] == "client_error"


def test_an_unhandled_exception_is_logged_and_still_raised(client, written):
    """The row is evidence about the request; it does not get to swallow it."""
    r = client.get("/api/v1/external/boom")
    assert r.status_code == 500
    assert len(written) == 1
    assert written[0]["outcome"] == "server_error"
    assert "kaboom" in written[0]["error_message"]


def test_a_failing_log_write_does_not_break_the_response(client, written, monkeypatch):
    """OBS-S3-11. Telemetry must never turn a working call into a 500."""
    import app.services.api_call_log_service as svc

    def _explode(db, **fields):
        raise RuntimeError("db is down")

    monkeypatch.setattr(svc, "write_call_log", _explode)

    r = client.post("/api/v1/external/brand-new-route", json={"echo": "hi"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_non_json_response_is_still_logged(client, written):
    client.get("/api/v1/external/plain")
    assert written[0]["response_payload"] == "hello"
