from app.rbac.permission_registry import PERMISSION_REGISTRY


def test_lookup_sets_permissions_present():
    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    assert "master_data.lookup_sets.view" in slugs
    assert "master_data.lookup_sets.add" in slugs
    assert "master_data.lookup_sets.edit" in slugs
    assert "master_data.lookup_sets.delete" in slugs
