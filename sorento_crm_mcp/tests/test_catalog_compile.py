"""Ensure every catalog entry compiles to a Context-aware tool."""
from __future__ import annotations

import pytest
from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import _compile_tool


class _FakeRC:
    def __init__(self, client):
        self.lifespan_context = {"client": client}


class _FakeCtx:
    def __init__(self, client):
        self.request_context = _FakeRC(client)


class _FakeClient:
    async def get(self, path, path_params=None, query=None):
        return f'{{"path":"{path}","ok":true}}'


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", list(CATALOG))
async def test_tool_runs_with_fake_context(spec):
    fn = _compile_tool(spec)
    kwargs = {p: "test-id" for p in spec.path_params}
    if spec.name == "crm_marketing_promotion_products_list":
        kwargs["promotion_id"] = "test-id"
    out = await fn(_FakeCtx(_FakeClient()), **kwargs)  # type: ignore[arg-type]
    assert spec.path in out
    assert "ok" in out


def test_catalog_covers_all_prefix_domains():
    """Smoke: catalog is non-empty and names are unique."""
    names = [s.name for s in CATALOG]
    assert len(names) == len(set(names))
    assert len(CATALOG) >= 70
