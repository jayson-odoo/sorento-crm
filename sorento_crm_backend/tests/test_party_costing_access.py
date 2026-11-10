"""RED tests B12: who can reach costing, and what must never carry it. PRODUCT-COSTING.
AC-AX-01, AC-AX-02, AC-AX-03, AC-CG-01, AC-CG-10.

The route table below is the whole costing API (contract section 4). The checks:
  1. every route is mounted;
  2. no cost view -> 403 on every route (also with the OTHER costing grants in hand), so removing
     the `products.cost.view` gate from any one route turns a case red (KILL TEST);
  3. an admin (role slug) and a superadmin pass the gates (bypass);
  4. a bare X-API-Key caller and a contact (portal) session get 401/403, and the permission gate
     of each route is built on the staff session dependency, never the API-key one;
  5. customer and product payloads, the portal and the MCP catalog carry no costing field;
  6. no costing route path contains `import` (AC-CG-10).
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.support.costing_env import BASE, COST_VIEW, MANAGE, costing_env  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]


def _specs(w):
    """(label, method, path, json-body) for every costing route, with real ids from the world."""
    cid, pid = w.customer.id, w.wb.id
    return [
        ("rows", "GET", "/rows?as_of=2026-11-11", None),
        ("rows-party", "GET", f"/rows?as_of=2026-11-11&party_id={cid}", None),
        ("suppliers", "GET", f"/rows/{pid}/suppliers?as_of=2026-11-11", None),
        ("history", "GET", f"/rows/{pid}/history", None),
        ("patch-rows", "PATCH", "/rows",
         {"party_id": cid, "changes": [{"product_id": pid, "markup_pct": 9}]}),
        ("export", "GET", "/export?as_of=2026-11-11", None),
        ("settings-get", "GET", "/settings", None),
        ("settings-put", "PUT", "/settings", {"sst_factor": 1.1, "default_method": "primary"}),
        ("rules-get", "GET", "/category-rules", None),
        ("rules-put", "PUT", f"/category-rules/{w.cat_taps.id}", {"mode": "multiply", "value": 1.07}),
        ("rates-get", "GET", "/exchange-rates", None),
        ("rates-post", "POST", "/exchange-rates",
         {"currency": "RMB", "effective_from": "2026-12-01", "rate_to_base": 0.6}),
        ("rates-put", "PUT", f"/exchange-rates/{w.rmb_new.id}", {"rate_to_base": 0.63}),
        ("party-get", "GET", f"/parties/{cid}", None),
        ("party-put", "PUT", f"/parties/{cid}", {"markup_pct": 8, "cost_method": None, "is_active": True}),
        ("party-add", "POST", f"/parties/{cid}/products", {"product_ids": [w.tap.id]}),
    ]


def _call(client, method, path, body, headers=None):
    return client.request(method, f"{BASE}{path}", json=body, headers=headers or {})


def _world(costing_env):
    e = costing_env
    w = e.workbook()
    return e, w


# ------------------------------------------------------------------ 1. the routes exist


def test_the_whole_costing_api_is_mounted():
    paths = {
        (m, r.path)
        for r in app.routes
        if getattr(r, "path", "").startswith(BASE)
        for m in (getattr(r, "methods", None) or ())
    }
    expected = {
        ("GET", f"{BASE}/rows"), ("PATCH", f"{BASE}/rows"),
        ("GET", f"{BASE}/rows/{{product_id}}/suppliers"), ("GET", f"{BASE}/rows/{{product_id}}/history"),
        ("GET", f"{BASE}/export"),
        ("GET", f"{BASE}/settings"), ("PUT", f"{BASE}/settings"),
        ("GET", f"{BASE}/category-rules"), ("PUT", f"{BASE}/category-rules/{{category_id}}"),
        ("GET", f"{BASE}/exchange-rates"), ("POST", f"{BASE}/exchange-rates"),
        ("PUT", f"{BASE}/exchange-rates/{{id}}"),
        ("GET", f"{BASE}/parties/{{customer_id}}"), ("PUT", f"{BASE}/parties/{{customer_id}}"),
        ("POST", f"{BASE}/parties/{{customer_id}}/products"),
    }
    # the exchange-rate id parameter may be spelled differently; compare modulo the name
    def norm(p):
        return re.sub(r"\{[^}]+\}", "{x}", p)

    have = {(m, norm(p)) for m, p in paths}
    missing = sorted(t for t in {(m, norm(p)) for m, p in expected} if t not in have)
    assert not missing, f"costing routes not mounted yet: {missing}"


# ------------------------------------------------------------------ 2. no cost view -> 403


def test_ac_ax_01_every_costing_route_is_403_without_cost_view(costing_env):
    e, w = _world(costing_env)
    e.as_user(e.user())
    for label, method, path, body in _specs(w):
        r = _call(e.client, method, path, body)
        assert r.status_code == 403, (label, r.status_code, r.text)


def test_ac_ax_01_the_other_costing_grants_do_not_stand_in_for_cost_view(costing_env):
    """KILL TEST (cost gate removed from one route): manage + scm.config.manage + scm.dashboard.view
    without products.cost.view must still be refused everywhere, writes included."""
    e, w = _world(costing_env)
    e.as_user(e.user(MANAGE, "scm.config.manage", "scm.dashboard.view"))
    for label, method, path, body in _specs(w):
        r = _call(e.client, method, path, body)
        assert r.status_code == 403, (label, r.status_code, r.text)


def test_ac_ax_01_cost_view_alone_reads_everything_and_writes_nothing(costing_env):
    e, w = _world(costing_env)
    e.as_user(e.viewer())
    for label, method, path, body in _specs(w):
        r = _call(e.client, method, path, body)
        if method == "GET":
            assert r.status_code == 200, (label, r.status_code, r.text)
        else:
            assert r.status_code == 403, (label, r.status_code, r.text)


def test_ac_ax_01_a_refused_call_changed_nothing(costing_env):
    from app.models.costing import CostingSettings, ExchangeRate

    e, w = _world(costing_env)
    rates_before = e.db.query(ExchangeRate).count()
    e.as_user(e.user())
    for label, method, path, body in _specs(w):
        _call(e.client, method, path, body)
    e.db.expire_all()
    assert e.db.query(ExchangeRate).count() == rates_before
    assert e.db.query(CostingSettings).count() == 0
    assert float(w.pp_wb.markup_pct or 0) == 0.0


# ------------------------------------------------------------------ 3. admin / superadmin bypass


@pytest.mark.parametrize("who", ["admin", "superadmin"])
def test_ac_ax_01_admin_and_superadmin_pass_every_gate(costing_env, who):
    e, w = _world(costing_env)
    e.as_user(e.admin() if who == "admin" else e.superadmin())
    for label, method, path, body in _specs(w):
        r = _call(e.client, method, path, body)
        assert r.status_code in (200, 201), (who, label, r.status_code, r.text)


def test_ac_cg_01_the_page_data_is_403_for_a_user_without_cost_view_and_200_with_it(costing_env):
    e, w = _world(costing_env)
    e.as_user(e.user("order_management.orders.view"))
    assert e.rows().status_code == 403
    e.as_user(e.viewer())
    assert e.rows(as_of="2026-11-11").status_code == 200


# ------------------------------------------------------------------ 4. API key and contact sessions


def _anonymous_client(e):
    """Same DB, but with the principal overrides removed, so the real auth dependencies run."""
    from app.dependencies import get_current_user, get_current_user_or_api_key

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_api_key, None)
    return TestClient(app)


def test_ac_ax_02_a_bare_api_key_caller_is_refused_on_every_costing_route(costing_env):
    e, w = _world(costing_env)
    client = _anonymous_client(e)
    for label, method, path, body in _specs(w):
        r = _call(client, method, path, body, headers={"X-API-Key": "ci-dummy-key"})
        assert r.status_code in (401, 403), (label, r.status_code, r.text)


def test_ac_ax_02_a_contact_portal_session_is_refused_on_every_costing_route(costing_env):
    e, w = _world(costing_env)
    client = _anonymous_client(e)
    for headers in (
        {"X-Portal-Token": "portal-contact-token"},
        {"Authorization": "Bearer portal-contact-token"},
    ):
        for label, method, path, body in _specs(w):
            r = _call(client, method, path, body, headers=headers)
            assert r.status_code in (401, 403), (label, headers, r.status_code, r.text)
    # the query-string form portal links use
    r = client.get(f"{BASE}/rows?token=portal-contact-token&as_of=2026-11-11")
    assert r.status_code in (401, 403), r.text


def test_ac_ax_02_no_credentials_at_all_is_401(costing_env):
    e, w = _world(costing_env)
    client = _anonymous_client(e)
    for label, method, path, body in _specs(w):
        assert _call(client, method, path, body).status_code == 401, label


def _gate_calls(dependant) -> set:
    seen, stack = set(), [dependant]
    while stack:
        d = stack.pop()
        if d is None:
            continue
        if d.call is not None:
            seen.add(d.call)
        stack.extend(d.dependencies)
    return seen


def test_ac_ax_02_each_routes_permission_gate_rides_the_staff_session_not_the_api_key():
    """The router-level module guard may use the API-key variant; the route's own
    `require_permission` gate (closure named `_require`) must depend on `get_current_user`."""
    from app.dependencies import get_current_user, get_current_user_or_api_key

    checked = 0
    for route in app.routes:
        if not getattr(route, "path", "").startswith(BASE):
            continue
        gates = [d for d in route.dependant.dependencies if getattr(d.call, "__name__", "") == "_require"]
        assert gates, (route.path, "no require_permission gate on this costing route")
        for gate in gates:
            calls = _gate_calls(gate)
            assert get_current_user in calls, route.path
            assert get_current_user_or_api_key not in calls, route.path
        checked += 1
    assert checked >= 15, f"only {checked} costing routes are mounted"


# ------------------------------------------------------------------ 5. nothing else carries costing


_FORBIDDEN = re.compile(r"costing|markup|mark_up|landing", re.I)


def _keys(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield f"{path}/{k}"
            yield from _keys(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _keys(v, f"{path}[]")


def _assert_no_costing_keys(payload, label):
    bad = [k for k in _keys(payload) if _FORBIDDEN.search(k.rsplit("/", 1)[-1])]
    assert not bad, (label, bad)


def test_ac_ax_03_customer_and_product_payloads_carry_no_costing_field(costing_env):
    e, w = _world(costing_env)
    e.as_user(e.superadmin())
    # the party really has a profile and priced products, created through the costing API
    created = e.put(f"/parties/{w.customer.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})
    assert created.status_code == 200, created.text
    assert e.rows(party_id=w.customer.id, as_of="2026-11-11").status_code == 200

    om = "/api/v1/order-management/customers"
    for label, url in (
        ("customer detail", f"{om}/{w.customer.id}"),
        ("customer list", f"{om}/?limit=50"),
        ("product detail", f"/api/v1/master-data/products/{w.wb.id}"),
        ("product list", "/api/v1/master-data/products/?limit=50"),
    ):
        r = e.client.get(url)
        assert r.status_code == 200, (label, r.status_code, r.text[:300])
        _assert_no_costing_keys(r.json(), label)


def test_ac_ax_03_response_schemas_of_customers_and_products_have_no_costing_field():
    from app.schemas.order import CustomerResponse
    from app.schemas.product import ProductResponse

    for model in (CustomerResponse, ProductResponse):
        bad = [name for name in model.model_fields if _FORBIDDEN.search(name)]
        assert not bad, (model.__name__, bad)


def test_ac_ax_03_the_portal_and_public_routes_never_touch_costing():
    for path in sorted((BACKEND / "app" / "api" / "v1" / "public").glob("*.py")):
        text = path.read_text()
        assert not re.search(r"models\.costing|services\.costing|customer_costing|exchange_rates", text), path.name
    assert not re.search(r"costing", (BACKEND / "app/services/portal_service.py").read_text(), re.I)


def test_ac_ax_02_the_mcp_catalog_exposes_no_costing_tool():
    from app.services.mcp_catalog_copy import CATALOG

    offenders = [
        s.name for s in CATALOG
        if re.search(r"costing|exchange-rates|markup", f"{s.name} {s.path}", re.I)
    ]
    assert not offenders, offenders
    mcp_catalog = BACKEND.parent / "sorento_crm_mcp" / "sorento_crm_mcp" / "catalog.py"
    if mcp_catalog.exists():
        assert "master-data/costing" not in mcp_catalog.read_text()


def test_ac_ax_02_the_external_api_key_surface_does_not_serve_costing():
    for path in sorted((BACKEND / "app" / "api" / "v1" / "external").glob("*.py")):
        assert "services.costing" not in path.read_text(), path.name
        assert "models.costing" not in path.read_text(), path.name
    external = [
        r.path for r in app.routes
        if getattr(r, "path", "").startswith("/api/v1/external") and "costing" in r.path
    ]
    assert external == []


# ------------------------------------------------------------------ 6. no import (AC-CG-10)


def test_ac_cg_10_no_costing_route_path_contains_import():
    mounted = [r.path for r in app.routes if getattr(r, "path", "").startswith(BASE)]
    assert mounted, "costing router is not mounted"
    assert [p for p in mounted if "import" in p.lower()] == []


def test_ac_cg_10_no_costing_service_or_router_module_has_an_import_surface():
    files = [BACKEND / "app" / "api" / "v1" / "master_data" / "costing.py"]
    files += sorted((BACKEND / "app" / "services" / "costing").glob("*.py")) if (
        BACKEND / "app" / "services" / "costing").exists() else []
    assert files[0].exists(), "app/api/v1/master_data/costing.py is not written yet"
    for f_ in files:
        text = f_.read_text()
        assert not re.search(r"def\s+\w*import\w*\s*\(", text, re.I), f_.name
        assert not re.search(r"UploadFile|import_job", text), f_.name
