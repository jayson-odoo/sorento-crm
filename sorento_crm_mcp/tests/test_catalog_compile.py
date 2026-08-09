"""Ensure every catalog entry compiles to a Context-aware tool.

MCP tools are NOT access-gated at this layer — access control lives in the n8n
flow, not the MCP server. So compiled tools take only their declared
path/query/body params; there is no contact_id/space_id guard injection.
"""
from __future__ import annotations

import pytest

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import TOOL_REQUIRED_NARROWING_FILTERS, _compile_tool


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
        # Include is_active=true so any promotion-activity precheck treats the row as active.
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


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", list(CATALOG))
async def test_tool_runs_with_fake_context(spec):
    fn = _compile_tool(spec)
    _PP_UUID = "11111111-1111-4111-8111-111111111111"
    kwargs: dict[str, str] = {p: _PP_UUID for p in spec.path_params}
    for b in spec.body_params:
        kwargs.setdefault(b, "{}")
    # Parent-relation tools (orders_by_product, incoming_stock_by_product, GRN,
    # promotion_products, promotion_attachments, product_attachments) short-circuit
    needed = TOOL_REQUIRED_NARROWING_FILTERS.get(spec.name)
    if needed:
        kwargs.setdefault(needed[0], _PP_UUID)
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
    filtering. Whatever timeframe the user gives is always translated to
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


def test_no_freetext_query_on_data_list_tools():
    """UUID-first contract: entity list tools must not expose a fuzzy `query`
    param. (user_guides_read is a documentation search and lookup_resolve takes
    `raw` — those are not entity filters and are exempt.)
    """
    exempt = {"user_guides_read", "crm_lookup_resolve"}
    for spec in CATALOG:
        if spec.name in exempt:
            continue
        assert "query" not in spec.query_params, f"{spec.name} still exposes free-text query"


def test_product_attachments_accepts_certificate_ids_as_a_narrower():
    """`certificate_ids` must be BOTH a query param and a recognised narrowing
    key. Listed as one but not the other, "the files for this certificate"
    returns an empty page while the filter itself works - a silent wrong answer,
    not an error.
    """
    spec = next(s for s in CATALOG if s.name == "crm_master_product_attachments_list")
    assert "certificate_ids" in spec.query_params
    assert "certificate_ids" in TOOL_REQUIRED_NARROWING_FILTERS[spec.name]
    # And the agent has to be told, or it will never pass it.
    assert "certificate_ids" in spec.description


@pytest.mark.asyncio
async def test_certificate_ids_alone_reaches_the_backend():
    """Not short-circuited: the request must actually carry the filter."""
    spec = next(s for s in CATALOG if s.name == "crm_master_product_attachments_list")
    fn = _compile_tool(spec)
    out = await fn(
        _FakeCtx(_FakeClient()),
        certificate_ids="11111111-1111-4111-8111-111111111111",
    )  # type: ignore[arg-type]
    assert "certificate_ids" in out


def test_resource_attachments_accepts_contact_id_alone_as_a_narrower():
    """A contact IS a narrowing filter, and the one a caller always has.

    The backend answers a contact-scoped call with (is_direct_access types) UNION
    (types granted to this contact) - a handful of documents, not the library. So
    "send me the container status list" needs no type resolution first. Requiring
    one meant a missed resolution left the call with no narrower at all, which
    returns an empty page WITHOUT calling the backend, which reads as "there is no
    such document" about a document that exists.
    """
    spec = next(s for s in CATALOG if s.name == "crm_resource_attachments_list")
    assert "contact_id" in spec.query_params
    assert "contact_id" in TOOL_REQUIRED_NARROWING_FILTERS[spec.name]
    assert "contact_id" in spec.description


def test_resource_attachments_type_filter_is_singular_only():
    """There is no `attachment_type_ids`. A caller that sends the plural has its
    key dropped, ends up with no narrower, and gets the silent empty page above.
    """
    spec = next(s for s in CATALOG if s.name == "crm_resource_attachments_list")
    assert "attachment_type_id" in spec.query_params
    assert "attachment_type_ids" not in spec.query_params
    assert "attachment_type_ids" not in TOOL_REQUIRED_NARROWING_FILTERS[spec.name]


@pytest.mark.asyncio
async def test_contact_id_alone_reaches_the_backend():
    """Not short-circuited: the request must actually carry the contact."""
    spec = next(s for s in CATALOG if s.name == "crm_resource_attachments_list")
    fn = _compile_tool(spec)
    out = await fn(_FakeCtx(_FakeClient()), contact_id="rio_10532f")  # type: ignore[arg-type]
    assert "contact_id" in out
