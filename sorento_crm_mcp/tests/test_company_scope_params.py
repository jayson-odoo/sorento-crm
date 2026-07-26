"""Multi-company isolation (PLAN-multi-company-isolation §3.13/§8b, UAC AC-F7/F8).

Company-scoped tools MUST declare `contact_id` + `space_id` as forwardable params
(query for GET tools, body for the POST lookup tool) so n8n can scope owned data
to the calling contact's company/companies. Global tools MUST NOT — they return
data that is not company-owned.

This is a catalog-level guard: a NEW scoped tool that forgets the two params (or a
global tool that wrongly gains them) fails here, mirroring the AC-F7/F8 matrix.
"""
from __future__ import annotations

import inspect

import pytest

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.server import _compile_tool

# AC-F7 — company-scoped owned-data tools that MUST forward contact_id + space_id.
SCOPED_TOOLS: frozenset[str] = frozenset({
    "crm_master_products_list",
    "crm_master_brands_list",
    "crm_master_product_categories_list",
    "crm_master_units_of_measure_list",
    "crm_master_product_attachments_list",
    "crm_marketing_promotions_list",
    "crm_marketing_promotion_products_list",
    "crm_marketing_promotion_attachments_list",
    "crm_resource_attachments_list",
    "crm_resource_attachments_catalogue",
    "crm_resource_attachments_current_stock_list",
    "crm_inventory_stock_balance_list",
    "crm_inventory_warehouses_list",
    "crm_order_management_orders_list",
    "crm_order_management_orders_by_product_list",
    "crm_order_analytics",
    "crm_incoming_stock_by_product",
    "crm_incoming_stock_shipments",
    "crm_incoming_stock_list",
    "crm_master_customers_list",
    "crm_lookup_resolve",
})

# AC-F8 — global (non-owned-data) tools that MUST NOT gain the scope params.
GLOBAL_TOOLS: frozenset[str] = frozenset({
    "crm_complaints_list",
    "crm_complaint_analytics",
    "crm_sla_conversation_tracking_dashboard",
    "crm_sla_conversation_tracking_list",
    "crm_sla_conversation_event_logs_list",
    "crm_forms_management_forms_list",
    "crm_system_tool_capabilities_summary",
})

_SCOPE_PARAMS = ("contact_id", "space_id")


def _spec(name):
    return next(s for s in CATALOG if s.name == name)


def _forwardable(spec) -> set[str]:
    """Params that actually reach the backend as request params (query OR body)."""
    return set(spec.query_params) | set(spec.body_params)


def test_scoped_and_global_sets_are_real_tools():
    names = {s.name for s in CATALOG}
    missing_scoped = SCOPED_TOOLS - names
    missing_global = GLOBAL_TOOLS - names
    assert not missing_scoped, f"scoped tools not in catalog: {missing_scoped}"
    assert not missing_global, f"global tools not in catalog: {missing_global}"
    # A tool cannot be both scoped and global.
    assert not (SCOPED_TOOLS & GLOBAL_TOOLS)


@pytest.mark.parametrize("name", sorted(SCOPED_TOOLS))
def test_scoped_tool_forwards_contact_and_space(name):
    spec = _spec(name)
    fwd = _forwardable(spec)
    for p in _SCOPE_PARAMS:
        assert p in fwd, f"{name} must forward `{p}` (query or body) for company scoping"
    # Description advertises the scope capability for RAG tool routing.
    assert "contact_id" in spec.description and "space_id" in spec.description


@pytest.mark.parametrize("name", sorted(GLOBAL_TOOLS))
def test_global_tool_has_no_scope_params(name):
    spec = _spec(name)
    fwd = _forwardable(spec)
    for p in _SCOPE_PARAMS:
        assert p not in fwd, f"global tool {name} must NOT carry `{p}` (AC-F8)"


@pytest.mark.parametrize("name", sorted(SCOPED_TOOLS))
def test_scope_params_are_optional_in_compiled_signature(name):
    """Backward-compat: existing n8n calls omit both → all-company results.
    Both params must be optional (default present) in the generated signature.
    """
    impl = _compile_tool(_spec(name))
    params = inspect.signature(impl).parameters
    for p in _SCOPE_PARAMS:
        assert p in params, f"{name} compiled tool is missing `{p}` argument"
        assert params[p].default is not inspect._empty, (
            f"{name}.{p} must be optional (have a default) for backward-compat"
        )


def test_portal_link_get_scope_params_untouched():
    """crm_portal_link_get carries contact_id/space_id for a different purpose
    (minting a portal token); it is NOT in the AC-F7 scoping set and its body
    contract must stay exactly {contact_id, space_id, submission_type, base_url}.
    """
    spec = _spec("crm_portal_link_get")
    assert "crm_portal_link_get" not in SCOPED_TOOLS
    assert set(spec.body_params) == {"contact_id", "space_id", "submission_type", "base_url"}
