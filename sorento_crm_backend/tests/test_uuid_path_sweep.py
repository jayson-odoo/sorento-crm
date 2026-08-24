"""C3 - UUIDPath allowlist sweep (PLAN-fix-security-cluster.md).

Two concerns are pinned here, both sqlite-free (no app/DB boot required):

1. Behaviour of the shared guard `validate_uuid_path` - a non-UUID id raises a
   clean HTTP 404 (existing convention), a real UUID is accepted + lowercased.
   Every allowlisted detail handler calls this as the first line of its `try`,
   so this is the unit-level proof of "bad id -> 404, not 500".

2. Source-introspection guardrails: the guard IS wired onto strictly-internal
   UUID PK params, and is NOT wired onto the excluded params (respond_io_id /
   code-or-uuid resolvers / dual-id contact routes / already-UUID-typed params).
   These would 422/404 otherwise-valid n8n / portal calls - see the CRITICAL
   EXCLUSION LIST in the plan.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi import HTTPException

from app.services.uuid_path_param import validate_uuid_path

BACKEND = pathlib.Path(__file__).resolve().parents[1]
API = BACKEND / "app" / "api" / "v1"


def _src(rel: str) -> str:
    return (API / rel).read_text()


# --------------------------------------------------------------------------- #
# 1. Guard behaviour                                                          #
# --------------------------------------------------------------------------- #
def test_accepts_canonical_uuid():
    u = "0f8fad5b-d9cb-401f-91ce-3b7e4b8a2c10"
    assert validate_uuid_path(u, resource="Thing") == u


def test_lowercases_uuid():
    u = "0F8FAD5B-D9CB-401F-91CE-3B7E4B8A2C10"
    assert validate_uuid_path(u, resource="Thing") == u.lower()


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-uuid",
        "123",
        "",
        "   ",
        "abc",
        "1234567890",          # respond_io_id-shaped (numeric) -> must 404 here
        " STK-0001 ",          # business-code-shaped
        "0f8fad5b-d9cb-401f-91ce-3b7e4b8a2c1",   # one char short
    ],
)
def test_rejects_non_uuid_with_404(bad):
    with pytest.raises(HTTPException) as exc:
        validate_uuid_path(bad, resource="Thing")
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# 2a. Guard IS applied to allowlisted internal-UUID PK params                  #
# --------------------------------------------------------------------------- #
ALLOWLISTED = [
    ("complaints/complaints.py", "complaint_id"),
    ("complaints/complaint_root_causes.py", "root_cause_id"),
    ("complaints/complaint_resolutions.py", "resolution_id"),
    ("order_management/customers.py", "customer_id"),
    ("order_management/order_statuses.py", "status_id"),
    ("resources/attachment_types.py", "type_id"),
    ("resources/attachments.py", "attachment_id"),
    ("resources/directories.py", "directory_id"),
    ("integrations/logs.py", "log_id"),
    ("inventory/storage_zones.py", "zone_id"),
    ("inventory/stock_batches.py", "batch_id"),
    ("marketing/campaigns.py", "campaign_id"),
    ("marketing/campaign_types.py", "type_id"),
    ("marketing/promotions.py", "promotion_id"),
    ("marketing/promotion_attachments.py", "promotion_attachment_id"),
    ("master_data/units_of_measure.py", "uom_id"),
    ("master_data/product_attachments.py", "product_attachment_id"),
    ("master_data/lookup_sets.py", "set_id"),
    ("procurement/suppliers.py", "supplier_id"),
    ("procurement/product_suppliers.py", "product_supplier_id"),
    ("procurement/stock_inquiries.py", "inquiry_id"),
    ("procurement/purchase_requests.py", "request_id"),
    ("sla/sla_policies.py", "policy_id"),
    ("sla/form_sla_config.py", "config_id"),
    ("forms/forms.py", "form_id"),
    ("user_management/teams.py", "team_id"),
    ("user_management/access_agents.py", "agent_id"),
    ("user_management/permissions.py", "permission_id"),
    ("user_management/roles.py", "role_id"),
    ("user_management/users.py", "user_id"),
    ("user_management/quick_access.py", "entry_id"),
    ("notifications/notifications.py", "notification_id"),
    ("system/respond_workspaces.py", "workspace_id"),
    ("downloads/downloads.py", "download_id"),
]


@pytest.mark.parametrize("rel,param", ALLOWLISTED)
def test_guard_applied_to_allowlisted_param(rel, param):
    s = _src(rel)
    assert "from app.services.uuid_path_param import validate_uuid_path" in s, rel
    assert f"validate_uuid_path({param}," in s, f"{rel}: guard not wired onto {param}"


# --------------------------------------------------------------------------- #
# 2b. Guard is NOT applied to excluded params (would break n8n / portal)       #
# --------------------------------------------------------------------------- #
def test_external_conversation_variables_respond_io_id_untouched():
    """Respond.io contact id (not a UUID) is a VALID value - must stay a string."""
    s = _src("external/conversation_variables.py")
    assert "validate_uuid_path" not in s


def test_orders_order_id_not_guarded():
    """get_order resolves UUID OR order_number - a non-UUID is valid."""
    assert "validate_uuid_path(order_id" not in _src("order_management/orders.py")


def test_products_product_id_not_guarded():
    """get_product resolves UUID OR product_code (SKU)."""
    assert "validate_uuid_path(product_id" not in _src("master_data/products.py")


@pytest.mark.parametrize(
    "rel,param",
    [
        ("inventory/warehouses.py", "warehouse_id"),   # warehouse_code/name fallback
        ("master_data/brands.py", "brand_id"),          # brand_code/name fallback
        ("master_data/categories.py", "category_id"),   # category_code/name fallback
        ("procurement/grn.py", "grn_id"),               # picking_number fallback
        ("procurement/packing_lists.py", "shipment_id"),# shipment_number fallback
        ("procurement/spo_allocations.py", "allocation_id"),  # spo_number fallback
    ],
)
def test_code_or_uuid_resolvers_not_guarded(rel, param):
    assert f"validate_uuid_path({param}" not in _src(rel)


def test_user_management_contacts_contact_id_not_guarded():
    """contact_id is heavily overloaded (respond_io_id confusion) - excluded."""
    assert "validate_uuid_path(contact_id" not in _src("user_management/contacts.py")


def test_sla_tracking_tracking_id_not_guarded():
    """tracking_id is already typed `: UUID` so FastAPI validates it (422)."""
    s = _src("sla/sla_tracking.py")
    assert "tracking_id: UUID" in s
    assert "validate_uuid_path(tracking_id" not in s


# --------------------------------------------------------------------------- #
# 2c. Dual-id contact lookups inside conversation routes are preserved         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "rel",
    [
        "complaints/complaints.py",
        "procurement/stock_inquiries.py",
        "procurement/purchase_requests.py",
    ],
)
def test_conversation_dual_id_contact_lookup_preserved(rel):
    """The RespondContact (respond_io_id OR internal id) fallback must remain  - 
    the sweep only guarded the entity PK path param, never this contact lookup."""
    s = _src(rel)
    assert "respond_io_id == contact_id_val" in s
