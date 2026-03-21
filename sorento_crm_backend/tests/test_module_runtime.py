"""Unit tests for module resolver, disable safety, and permission→module mapping."""
import pytest

from app.modules.runtime.permission_module_map import module_for_permission
from app.modules.runtime.module_manifest import MODULE_BUNDLES, manifest_dependency_graph
from app.modules.runtime.resolver import (
    resolve_install_plan,
    enabled_modules_blocking_disable,
    get_reverse_dependents,
    installed_modules_blocking_uninstall,
)


@pytest.fixture
def dep_graph():
    return manifest_dependency_graph()


def test_resolve_install_plan_inventory_includes_product_and_base(dep_graph):
    plan = resolve_install_plan(dep_graph, ["inventory"])
    assert set(plan) == {"base", "product", "inventory"}
    assert plan.index("base") < plan.index("product") < plan.index("inventory")


def test_resolve_install_plan_commercial_plus_bundle_keys_exist(dep_graph):
    keys = MODULE_BUNDLES["commercial_plus"]
    assert "marketing" in keys and "procurement" in keys
    plan = resolve_install_plan(dep_graph, keys)
    assert set(keys).issubset(set(plan))
    assert all(k in dep_graph for k in plan)
    for k in plan:
        for dep in dep_graph[k]:
            assert plan.index(dep) < plan.index(k)


def test_unknown_module_raises(dep_graph):
    with pytest.raises(ValueError, match="Unknown module"):
        resolve_install_plan(dep_graph, ["not_a_real_module"])


def test_disable_product_blocked_when_inventory_enabled(dep_graph):
    enabled = {"base", "product", "inventory"}
    conflicts = enabled_modules_blocking_disable(dep_graph, "product", enabled)
    assert "inventory" in conflicts


def test_uninstall_product_blocked_when_inventory_installed_even_if_disabled(dep_graph):
    """Uninstall is stricter than disable: disabled-but-installed dependents still block."""
    installed = {"base", "product", "inventory"}
    conflicts = installed_modules_blocking_uninstall(dep_graph, "product", installed)
    assert "inventory" in conflicts


def test_reverse_dependents_product(dep_graph):
    rev = get_reverse_dependents(dep_graph, "product")
    assert "inventory" in rev
    assert "order" in rev


def test_permission_module_map_prefixes():
    assert module_for_permission("master_data.products.view") == "product"
    assert module_for_permission("order_management.orders.view") == "order"
    assert module_for_permission("system.import_logs.view") == "base"
    assert module_for_permission("dashboard.view") == "base"
