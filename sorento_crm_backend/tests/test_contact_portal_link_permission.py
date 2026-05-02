"""Verify the contact portal link permission slug is registered."""
from app.rbac.permission_registry import PERMISSION_REGISTRY


def test_contact_portal_link_permission_registered() -> None:
    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert "user_management.contacts.portal_link" in slugs


def test_contact_portal_link_permission_has_human_label() -> None:
    entry = next(
        (e for e in PERMISSION_REGISTRY if e["slug"] == "user_management.contacts.portal_link"),
        None,
    )
    assert entry is not None
    assert entry["name"] == "Get contact portal link"
    assert entry["description"]
