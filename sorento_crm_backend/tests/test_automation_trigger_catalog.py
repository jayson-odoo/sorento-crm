"""The trigger catalog's ``supports_grouping`` flag.

Grouping is implemented by ``automation_service._EXPIRY_BATCH_SPECS``; the flag
on ``TriggerSpec`` is only how that fact reaches the frontend, which uses it to
decide whether to render the "Combine into one email" switch. So the one thing
worth pinning is that the two lists cannot drift: a trigger that groups but
does not advertise it ships a feature nobody can turn on, and a trigger that
advertises grouping it cannot do shows a switch that does nothing.

No DB rows are needed - the registry is in-process and the catalog route reads
no table - so the endpoint test only overrides auth plus the permission gate.
"""
from __future__ import annotations

import pytest

from app.services import automation_triggers
from app.services.automation_service import _EXPIRY_BATCH_SPECS

CATALOG_URL = "/api/v1/system/automation/triggers/catalog"
VIEW_PERMISSION = "automation.automations.view"


def _spec(trigger_type: str):
    return next(s for s in automation_triggers.list_specs() if s.type == trigger_type)


# ------------------------------------------------------------------- registry
@pytest.mark.parametrize(
    "trigger_type",
    ["days_before_promotion_end", "days_before_certificate_expiry"],
)
def test_both_expiry_triggers_support_grouping(trigger_type):
    assert _spec(trigger_type).supports_grouping is True


def test_an_event_driven_trigger_does_not_support_grouping():
    """complaint_approved fires one match at a time, so there is nothing to fold."""
    assert _spec("complaint_approved").supports_grouping is False


def test_supports_grouping_matches_the_batch_spec_table_exactly():
    """The anti-drift assertion: the flag and the engine are one list, not two."""
    flagged = {s.type for s in automation_triggers.list_specs() if s.supports_grouping}
    assert flagged == set(_EXPIRY_BATCH_SPECS)


@pytest.mark.parametrize(
    ("trigger_type", "default"),
    [("days_before_promotion_end", 7), ("days_before_certificate_expiry", 30)],
)
def test_each_expiry_trigger_declares_its_days_before_default(trigger_type, default):
    """The FE renders the number input from this schema and seeds it with the
    default, so a missing title/default would silently save trigger_config={}
    and the trigger would fall back to its own hardcoded window."""
    schema = _spec(trigger_type).config_schema
    days_before = schema["properties"]["days_before"]
    assert days_before["default"] == default
    assert days_before["title"]
    assert schema["required"] == ["days_before"]


# ------------------------------------------------------------------- endpoint
@pytest.fixture
def api(monkeypatch):
    """TestClient with a controllable permission gate; ``allow`` holds slugs."""
    from fastapi.testclient import TestClient

    import app.dependencies as deps
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()

    app.dependency_overrides[deps.get_current_user] = lambda: {"id": "u-admin"}
    # The system router carries a module guard resolving through this dependency.
    app.dependency_overrides[deps.get_current_user_or_api_key] = lambda: {"id": "u-admin"}
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow
    finally:
        app.dependency_overrides.pop(deps.get_current_user, None)
        app.dependency_overrides.pop(deps.get_current_user_or_api_key, None)


def test_catalog_endpoint_exposes_supports_grouping(api):
    client, allow = api
    allow.add(VIEW_PERMISSION)

    res = client.get(CATALOG_URL)
    assert res.status_code == 200, res.text

    by_type = {t["type"]: t for t in res.json()["triggers"]}
    assert by_type["days_before_promotion_end"]["supports_grouping"] is True
    assert by_type["days_before_certificate_expiry"]["supports_grouping"] is True
    assert by_type["complaint_approved"]["supports_grouping"] is False
    # The days_before schema must survive serialization too - it is what the FE
    # builds the input (and its default) from.
    certificate_schema = by_type["days_before_certificate_expiry"]["config_schema"]
    assert certificate_schema["properties"]["days_before"]["default"] == 30


def test_catalog_endpoint_denies_a_user_without_the_view_permission(api):
    client, _allow = api
    res = client.get(CATALOG_URL)
    assert res.status_code == 403, res.text


def test_catalog_endpoint_rejects_an_unauthenticated_caller():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        res = client.get(CATALOG_URL)
    assert res.status_code in (401, 403), res.text
