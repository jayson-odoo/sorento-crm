"""SUPPLIER-COST-ACCESS: cost and supplier price only for holders of `products.cost.view`.

Owner + management, 9 Nov 2026: the product Supplier tab, unit costs and last purchase / PO
costs are for purchasing and management only; History still shows THAT a cost changed, with the
values hidden. Plan: `documentation/plans/products/PLAN-supplier-cost-access-10nov.md`.

Every route test runs through the REAL `get_current_user(_or_api_key)` with a real
`user_sessions` Bearer token (`mint_session`), because the mask is set by those dependencies:
only `get_db` and `apply_company_scope` are overridden. Postgres only (scratch schema).
"""
from __future__ import annotations

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  (first app import, repo convention)

from tests._pg_fixture import blank_session
from tests.support.cost_price_env import CostPriceEnv, PS_VIEW_PERM

COST_PERM = "products.cost.view"
PRODUCTS_VIEW = "master_data.products.view"
PRODUCTS_EXPORT = "master_data.products.export"
PRODUCTS_URL = "/api/v1/master-data/products"
AUDIT_URL = "/api/v1/audit/logs/"
LAST_COST_URL = "/api/v1/procurement/purchase-orders/last-cost"
LIST_QUERY = "/api/v1/list-query"
MIGRATION = "sca_0001_products_cost_view.py"


class _Env(CostPriceEnv):
    auto_cost_view = False  # this suite tests the cost permission itself

    def bearer(self, user: dict) -> dict:
        from app.services.user_session_service import mint_session

        return {"Authorization": f"Bearer {mint_session(self.db, user['id']).token}"}

    def get(self, user: dict, url: str, **params):
        return self.client.get(url, headers=self.bearer(user), params=params)

    def post(self, user: dict, url: str, body: dict):
        return self.client.post(url, headers=self.bearer(user), json=body)


@pytest.fixture
def env():
    from app.dependencies import get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        e = _Env(db)

        def _db():
            yield db

        async def _scope():
            set_company_scope(db, e.scope)
            return e.scope

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[apply_company_scope] = _scope
        e.client = TestClient(app)
        try:
            yield e
        finally:
            app.dependency_overrides.clear()


def _costed_product(e: _Env, cost: str = "123.45"):
    p = e.product()
    p.cost_price = Decimal(cost)
    p.list_price = Decimal("300.00")
    e.db.commit()
    return p


# --------------------------------------------------------------------------- B1 product API


def test_product_detail_hides_cost_without_permission(env):
    p = _costed_product(env)
    sales = env.user(PRODUCTS_VIEW, name="Sales")
    r = env.get(sales, f"{PRODUCTS_URL}/{p.id}")
    assert r.status_code == 200, r.text
    assert r.json()["cost_price"] is None
    assert Decimal(str(r.json()["list_price"])) == Decimal("300.00")


def test_product_detail_shows_cost_with_permission(env):
    p = _costed_product(env)
    buyer = env.user(PRODUCTS_VIEW, COST_PERM, name="Buyer")
    r = env.get(buyer, f"{PRODUCTS_URL}/{p.id}")
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["cost_price"])) == Decimal("123.45")


def test_product_detail_shows_cost_to_superadmin(env):
    p = _costed_product(env)
    admin = env.superadmin()
    r = env.get(admin, f"{PRODUCTS_URL}/{p.id}")
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["cost_price"])) == Decimal("123.45")


def test_product_list_hides_cost_without_permission(env):
    p = _costed_product(env)
    sales = env.user(PRODUCTS_VIEW)
    r = env.get(sales, f"{PRODUCTS_URL}/", product_ids=str(p.id))
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert [row["id"] for row in rows] == [str(p.id)]
    assert rows[0]["cost_price"] is None


def test_product_list_shows_cost_with_permission(env):
    p = _costed_product(env)
    buyer = env.user(PRODUCTS_VIEW, COST_PERM)
    r = env.get(buyer, f"{PRODUCTS_URL}/", product_ids=str(p.id))
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["data"][0]["cost_price"])) == Decimal("123.45")


# --------------------------------------------------------------------------- B1 writes


def _put(e: _Env, user: dict, product, body: dict):
    return e.client.put(f"{PRODUCTS_URL}/{product.id}", headers=e.bearer(user), json=body)


def test_product_edit_without_permission_keeps_the_cost(env):
    """The form sends `cost_price` on every save; a reader who saw it as null must not wipe it."""
    p = _costed_product(env)
    editor = env.user(PRODUCTS_VIEW, "master_data.products.edit")
    r = _put(env, editor, p, {"product_name": "Renamed by sales", "cost_price": None})
    assert r.status_code == 200, r.text
    r = _put(env, editor, p, {"cost_price": "1.00"})
    assert r.status_code == 200, r.text
    env.db.expire_all()
    env.db.refresh(p)
    assert p.product_name == "Renamed by sales"
    assert p.cost_price == Decimal("123.45")


def test_product_edit_with_permission_changes_the_cost(env):
    p = _costed_product(env)
    buyer = env.user(PRODUCTS_VIEW, "master_data.products.edit", COST_PERM)
    r = _put(env, buyer, p, {"cost_price": "130.00"})
    assert r.status_code == 200, r.text
    env.db.expire_all()
    env.db.refresh(p)
    assert p.cost_price == Decimal("130.00")


# --------------------------------------------------------------------------- B1 list-query


def _seed_product_fields(db) -> None:
    """The two `products` list-query fields these tests use (migration 128's shape); a scratch
    schema carries no metadata rows."""
    from app.models.list_query_metadata import ListQueryField, ListQueryResource

    res = db.query(ListQueryResource).filter_by(resource_key="products").first()
    if res is None:
        res = ListQueryResource(id=str(uuid.uuid4()), resource_key="products", display_name="Products")
        db.add(res)
        db.flush()
    for key, dtype, ops in (
        ("product_code", "string", ["eq", "contains"]),
        ("cost_price", "number", ["eq", "gt", "lt"]),
    ):
        if not db.query(ListQueryField).filter_by(resource_id=res.id, field_key=key).first():
            db.add(ListQueryField(
                id=str(uuid.uuid4()), resource_id=res.id, field_key=key, label=key, data_type=dtype,
                compile_key=f"product.{key}", allowed_operators=ops, filterable=True, exportable=True,
            ))
    db.commit()


def test_list_query_fields_drop_cost_without_permission(env):
    sales = env.user(PRODUCTS_VIEW)
    buyer = env.user(PRODUCTS_VIEW, COST_PERM)
    url = f"{LIST_QUERY}/resources/products/fields"
    _seed_product_fields(env.db)
    sales_keys = {f["field_key"] for f in env.get(sales, url).json()}
    buyer_resp = env.get(buyer, url)
    assert buyer_resp.status_code == 200, buyer_resp.text
    buyer_keys = {f["field_key"] for f in buyer_resp.json()}
    assert "cost_price" in buyer_keys
    assert "product_code" in sales_keys
    assert "cost_price" not in sales_keys


def test_list_query_search_masks_cost_and_refuses_cost_sort(env):
    p = _costed_product(env)
    _seed_product_fields(env.db)
    sales = env.user(PRODUCTS_VIEW)
    body = {"resource": "products", "quick_search": p.product_code}
    r = env.post(sales, f"{LIST_QUERY}/search", body)
    assert r.status_code == 200, r.text
    assert r.json()["data"] and r.json()["data"][0]["cost_price"] is None
    sorted_body = {**body, "sort": "cost_price"}
    assert env.post(sales, f"{LIST_QUERY}/search", sorted_body).status_code == 403
    filtered = {
        **body,
        "filter": {"op": "and", "children": [{"field_key": "cost_price", "op": "gt", "value": 1}]},
    }
    assert env.post(sales, f"{LIST_QUERY}/search", filtered).status_code == 403


def test_list_query_search_keeps_cost_with_permission(env):
    p = _costed_product(env)
    _seed_product_fields(env.db)
    buyer = env.user(PRODUCTS_VIEW, COST_PERM)
    r = env.post(buyer, f"{LIST_QUERY}/search", {"resource": "products", "quick_search": p.product_code})
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["data"][0]["cost_price"])) == Decimal("123.45")


def test_list_query_export_refuses_cost_column_without_permission(env):
    _costed_product(env)
    _seed_product_fields(env.db)
    sales = env.user(PRODUCTS_VIEW, PRODUCTS_EXPORT)
    body = {"resource": "products", "fields": [{"field_key": "product_code"}, {"field_key": "cost_price"}]}
    assert env.post(sales, f"{LIST_QUERY}/export", body).status_code == 403
    ok = env.post(sales, f"{LIST_QUERY}/export", {"resource": "products", "fields": [{"field_key": "product_code"}]})
    assert ok.status_code == 200, ok.text


# --------------------------------------------------------------------------- B2 purchase history


def test_purchase_history_refused_without_permission(env):
    p = _costed_product(env)
    sales = env.user(PRODUCTS_VIEW)
    assert env.get(sales, f"{PRODUCTS_URL}/{p.id}/purchase-history").status_code == 403


def test_purchase_history_served_with_permission(env):
    p = _costed_product(env)
    buyer = env.user(PRODUCTS_VIEW, COST_PERM)
    r = env.get(buyer, f"{PRODUCTS_URL}/{p.id}/purchase-history")
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- B3 product-suppliers


def test_product_suppliers_refused_without_cost_permission(env):
    p = _costed_product(env)
    env.link(p, env.supplier(), unit_cost=Decimal("9.99"), currency="MYR")
    env.db.commit()
    sales = env.user(PRODUCTS_VIEW, PS_VIEW_PERM)
    url = f"/api/v1/procurement/product-suppliers/product/{p.id}"
    assert env.get(sales, url).status_code == 403
    assert env.get(sales, "/api/v1/procurement/product-suppliers/").status_code == 403


def test_product_suppliers_served_with_cost_permission(env):
    p = _costed_product(env)
    env.link(p, env.supplier(), unit_cost=Decimal("9.99"), currency="MYR")
    env.db.commit()
    buyer = env.user(PRODUCTS_VIEW, PS_VIEW_PERM, COST_PERM)
    r = env.get(buyer, f"/api/v1/procurement/product-suppliers/product/{p.id}")
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- B4 PO last cost


def test_po_last_cost_refused_for_staff_session_without_permission(env):
    sales = env.user(PRODUCTS_VIEW)
    assert env.get(sales, LAST_COST_URL).status_code == 403


def test_po_last_cost_served_for_staff_session_with_permission(env):
    buyer = env.user(PRODUCTS_VIEW, COST_PERM)
    r = env.get(buyer, LAST_COST_URL)
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- B5 History


def _cost_change_audit(e: _Env, product, actor: dict):
    from app.models.audit import AuditLog

    row = AuditLog(
        id=str(uuid.uuid4()), entity_type="product", entity_id=str(product.id), action="UPDATE",
        user_id=actor["id"], old_values={"cost_price": "120.00", "product_name": "Old name"},
        new_values={"cost_price": "125.00", "product_name": "New name"},
    )
    e.db.add(row)
    e.db.commit()
    return row


def test_history_masks_cost_values_without_permission(env):
    p = _costed_product(env)
    buyer = env.user(PRODUCTS_VIEW, COST_PERM, name="Buyer")
    row = _cost_change_audit(env, p, buyer)
    sales = env.user(PRODUCTS_VIEW, name="Sales")
    r = env.get(sales, AUDIT_URL, entity_type="product", entity_id=str(p.id))
    assert r.status_code == 200, r.text
    (entry,) = [e for e in r.json()["data"] if e["id"] == str(row.id)]
    # That it happened, who and which field stay; the values do not.
    assert entry["user_display_name"] == "Buyer"
    assert entry["old_values"]["cost_price"] == "hidden"
    assert entry["new_values"]["cost_price"] == "hidden"
    assert entry["masked_fields"] == ["cost_price"]
    # Fields that are not cost are untouched.
    assert entry["new_values"]["product_name"] == "New name"
    # No entry on the page (the seeding's own INSERT/UPDATE rows included) leaks a cost value.
    assert "125.00" not in r.text and "120.00" not in r.text and "123.45" not in r.text


def test_history_shows_cost_values_with_permission(env):
    p = _costed_product(env)
    buyer = env.user(PRODUCTS_VIEW, COST_PERM)
    row = _cost_change_audit(env, p, buyer)
    r = env.get(buyer, AUDIT_URL, entity_type="product", entity_id=str(p.id))
    assert r.status_code == 200, r.text
    (entry,) = [e for e in r.json()["data"] if e["id"] == str(row.id)]
    assert entry["old_values"]["cost_price"] == "120.00"
    assert entry["new_values"]["cost_price"] == "125.00"
    assert not entry.get("masked_fields")


def test_mask_audit_values_covers_every_cost_key():
    from app.services.cost_access import COST_AUDIT_KEYS, mask_audit_values

    old = {k: "1" for k in COST_AUDIT_KEYS} | {"product_name": "x"}
    new = {k: "2" for k in COST_AUDIT_KEYS} | {"nested": {"unit_cost": "3"}}
    m_old, m_new, masked = mask_audit_values(old, new)
    assert set(masked) == set(COST_AUDIT_KEYS)
    assert all(m_old[k] == "hidden" and m_new[k] == "hidden" for k in COST_AUDIT_KEYS)
    assert m_old["product_name"] == "x"
    assert m_new["nested"]["unit_cost"] == "hidden"
    assert {"cost_price", "unit_cost", "supplier_name"} <= set(COST_AUDIT_KEYS)


# --------------------------------------------------------------------------- B6 dealer portal


def test_portal_new_product_application_never_carries_cost():
    from app.services import new_product_application_service as svc

    assert "cost_price" in svc._PORTAL_HIDDEN_COST


# --------------------------------------------------------------------------- B7 assistant


def test_assistant_cost_field_needs_the_cost_permission():
    from app.services.assistant_registry import products

    assert products.COST_PRICE_VIEW == COST_PERM


# --------------------------------------------------------------------------- migration


def _migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / MIGRATION
    spec = importlib.util.spec_from_file_location("_sca_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _role(db, *, slug: str, name: str, perms=()):
    from app.models.user import UserPermission, UserRole, UserRolePermission

    role = UserRole(id=str(uuid.uuid4()), slug=slug, name=name, is_protected=False, is_default=False)
    db.add(role)
    db.flush()
    for p_slug in perms:
        perm = db.query(UserPermission).filter_by(slug=p_slug).one_or_none()
        if perm is None:
            perm = UserPermission(id=str(uuid.uuid4()), slug=p_slug, name=p_slug)
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
    db.flush()
    return role


def _holds(db, role) -> bool:
    from app.models.user import UserPermission, UserRolePermission

    return (
        db.query(UserRolePermission)
        .join(UserPermission, UserPermission.id == UserRolePermission.permission_id)
        .filter(UserRolePermission.role_id == role.id, UserPermission.slug == COST_PERM)
        .count()
        == 1
    )


def test_migration_grants_purchasing_and_management_only():
    """Crew's role list from the dev database (10 Nov 2026), granted by slug. The refused roles
    hold the old cost slugs today, so a sweep from either would have handed cost back."""
    m = _migration()
    with blank_session() as db:
        granted = [
            _role(db, slug=slug, name=f"ZZT {slug}")
            for slug in ("admin", "director", "purchasing_manager", "purchasing", "purchasing_executive")
        ]
        old_cost_slugs = ["procurement.cost_price_changes.view", PS_VIEW_PERM, PRODUCTS_VIEW]
        refused = [
            _role(db, slug=slug, name=f"ZZT {slug}", perms=old_cost_slugs)
            for slug in (
                "salesperson", "retail:salesperson", "portal_user", "customer_service",
                "project.customer.service", "project_sales_coordinator", "project_sales_manager",
                "marketing_executive", "marketing_manager", "warehouse_manager",
                "warehouse_executive", "guest", "integration_foundryx_esb", "integration_mcp",
            )
        ]
        bind = db.connection()
        m.grant_cost_view(bind)
        m.grant_cost_view(bind)  # idempotent
        db.expire_all()
        for role in granted:
            assert _holds(db, role), role.slug
        for role in refused:
            assert not _holds(db, role), role.slug


def test_permission_is_in_the_registry():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert COST_PERM in {p["slug"] for p in PERMISSION_REGISTRY}
