"""Ensure every catalog entry compiles to a Context-aware tool."""
from __future__ import annotations

import pytest

from sorento_crm_mcp import access_guard, server as server_mod
from sorento_crm_mcp.access_guard import AccessDecision
from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import _compile_tool


class _FakeSettings:
    crm_base_url = "http://crm.local"
    external_api_key = "test-key"


class _FakeRC:
    def __init__(self, client):
        self.lifespan_context = {"client": client, "settings": _FakeSettings()}


class _FakeCtx:
    def __init__(self, client):
        self.request_context = _FakeRC(client)


class _FakeClient:
    async def get(self, path, path_params=None, query=None, tool_name=None):
        # Include is_active=true so the promotion-activity precheck (used by
        # several marketing *_get / *_by_promotion tools) treats the row as active.
        return (
            f'{{"path":"{path}","ok":true,"is_active":true,'
            f'"query":{list((query or {}).keys())!r}}}'
        )

    async def post(self, path, path_params=None, query=None, body=None, tool_name=None):
        return f'{{"path":"{path}","ok":true,"method":"POST"}}'

    async def request(self, method, path, path_params=None, query=None, body=None, tool_name=None):
        return (
            f'{{"path":"{path}","ok":true,"is_active":true,'
            f'"method":"{method}","query":{list((query or {}).keys())!r}}}'
        )


@pytest.fixture(autouse=True)
def _stub_access_guard(monkeypatch):
    async def _allow(*_args, **_kwargs):
        return AccessDecision(allowed=True, decision="allow", agent_name="stub")

    monkeypatch.setattr(access_guard, "check_access", _allow)
    monkeypatch.setattr(server_mod, "check_access", _allow)
    # The compiled tool captured the original `check_access` reference at module
    # import time via the namespace dict, so patch its binding too.
    import sorento_crm_mcp.server as _srv  # noqa: PLC0415
    _orig = _srv.check_access
    monkeypatch.setattr(_srv, "check_access", _allow)
    yield
    monkeypatch.setattr(_srv, "check_access", _orig, raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", list(CATALOG))
async def test_tool_runs_with_fake_context(spec, monkeypatch):
    # Re-bind the compiled tool's frozen namespace reference to the stubbed guard.
    async def _allow(*_args, **_kwargs):
        return AccessDecision(allowed=True, decision="allow", agent_name="stub")

    monkeypatch.setattr("sorento_crm_mcp.server.check_access", _allow)
    fn = _compile_tool(spec)
    # Use a real UUID so *_get tools don't fall back to the sibling list endpoint
    # (path mismatch would break the `spec.path in out` assertion below).
    _PP_UUID = "11111111-1111-4111-8111-111111111111"
    kwargs: dict[str, str] = {p: _PP_UUID for p in spec.path_params}
    # Every compiled tool requires guard params (contact_id, space_id) — the
    # generated signature prepends them regardless of whether the backend
    # endpoint consumes them.
    kwargs["contact_id"] = "respond-test"
    kwargs["space_id"] = "space-test"
    for b in spec.body_params:
        kwargs.setdefault(b, "{}")
    # Tools that declare contact_id/space_id as REQUIRED query hints additionally
    # need them in the forwarded query — which the compiled tool re-injects from
    # the guard params, so kwargs above are sufficient.
    out = await fn(_FakeCtx(_FakeClient()), **kwargs)  # type: ignore[arg-type]
    assert spec.path in out
    assert "ok" in out


def test_catalog_covers_all_prefix_domains():
    """Smoke: catalog is non-empty and names are unique."""
    names = [s.name for s in CATALOG]
    assert len(names) == len(set(names))
    assert len(CATALOG) >= 20


def test_orders_list_uses_actual_delivery_date_only():
    """orders_list exposes ONLY `actual_delivery_date_from` / `_to` for date
    filtering. The decision-table / order_date split was removed because it
    biased the agent toward today-only delivery filters and self-contradicted
    on order verbs. Whatever timeframe the user gives is always translated to
    actual_delivery_date — no order_date params.
    """
    spec = next(s for s in CATALOG if s.name == "crm_order_management_orders_list")
    desc = spec.description
    assert "actual_delivery_date_from" in desc
    assert "actual_delivery_date_to" in desc
    assert "order_date_from" not in desc
    assert "order_date_to" not in desc
    assert "order_date_from" not in spec.query_params
    assert "order_date_to" not in spec.query_params
    assert "actual_delivery_date_from" in spec.query_params
    assert "actual_delivery_date_to" in spec.query_params
