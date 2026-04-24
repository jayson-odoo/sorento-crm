from app.rbac.permission_registry import PERMISSION_REGISTRY


def test_ai_assistant_permission_slugs_registered() -> None:
    slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    assert "system.ai_assistant_chat.use" in slugs
    assert "system.ai_assistant_settings.view" in slugs
    assert "system.ai_assistant_settings.edit" in slugs
