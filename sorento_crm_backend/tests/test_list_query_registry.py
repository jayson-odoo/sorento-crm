"""Tests for list-query registry metadata."""
from app.services.list_query_registry import get_adapter, list_registered_resource_keys, require_adapter


def test_registered_resources_include_existing_list_query_domains():
    keys = set(list_registered_resource_keys())
    assert {"orders", "products", "suppliers", "promotions", "workflow_form_definitions", "workflow_form_submissions"} <= keys


def test_require_adapter_rejects_unknown_resource():
    try:
        require_adapter("not-a-resource")
        assert False, "Expected ValueError for unknown resource"
    except ValueError as ex:
        assert "Unsupported resource" in str(ex)


def test_promotions_adapter_has_export_slug():
    adapter = get_adapter("promotions")
    assert adapter is not None
    assert adapter.export_slug == "marketing.promotions.view"
