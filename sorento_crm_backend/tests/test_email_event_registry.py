"""Tests for the email event registry constant + seed helper."""
from unittest.mock import MagicMock

from app.services.email_event_registry import (
    EMAIL_EVENT_REGISTRY,
    EVENT_REGISTRY_INDEX,
    get_event_def,
    seed_event_configs,
)


def test_registry_keys_are_unique():
    keys = [e.event_key for e in EMAIL_EVENT_REGISTRY]
    assert len(keys) == len(set(keys)), "Duplicate event_key in EMAIL_EVENT_REGISTRY"


def test_registry_covers_known_business_events():
    keys = {e.event_key for e in EMAIL_EVENT_REGISTRY}
    must_have = {
        "password_reset",
        "user_invitation",
        "purchase_request_approval_link",
        "purchase_request_approved",
        "purchase_request_rejected",
        "stock_inquiry_created",
        "stock_inquiry_created_external",
        "complaint_created_external",
        "ticket_assigned",
        "ticket_responded",
        "ticket_resolved",
        "external_product_attachment",
        "external_promotion_uploader_notice",
        "external_form_created",
        "external_packing_list_created",
        "form_sla_assigned",
        "form_sla_escalated",
        "form_sla_updated",
        "import_job_completed",
        "workflow_form_state_transition",
        "daily_sla_summary",
        "notification_delivery",
    }
    missing = must_have - keys
    assert not missing, f"Missing events from registry: {missing}"


def test_registry_priority_zero_for_user_facing_events():
    high_priority_keys = {"password_reset", "user_invitation", "purchase_request_approval_link"}
    for evt in EMAIL_EVENT_REGISTRY:
        if evt.event_key in high_priority_keys:
            assert evt.priority == 0, f"{evt.event_key} should be priority 0 (high), got {evt.priority}"


def test_attachment_linkage_events_have_coalesce_window():
    coalesce_required = {
        "external_product_attachment",
        "external_promotion_uploader_notice",
        "external_form_created",
        "external_packing_list_created",
    }
    for evt in EMAIL_EVENT_REGISTRY:
        if evt.event_key in coalesce_required:
            assert evt.coalesce_window_seconds, (
                f"{evt.event_key} must have a coalesce_window_seconds (incident root cause)"
            )


def test_get_event_def_returns_known_keys():
    assert get_event_def("password_reset") is not None
    assert get_event_def("does_not_exist") is None


def test_event_registry_index_matches_registry():
    assert len(EVENT_REGISTRY_INDEX) == len(EMAIL_EVENT_REGISTRY)


def test_seed_event_configs_skips_existing():
    db = MagicMock()
    existing = [MagicMock(event_key=e.event_key) for e in EMAIL_EVENT_REGISTRY]
    db.query.return_value.all.return_value = existing
    inserted = seed_event_configs(db)
    assert inserted == 0
    db.commit.assert_not_called()


def test_seed_event_configs_inserts_missing():
    db = MagicMock()
    db.query.return_value.all.return_value = []
    inserted = seed_event_configs(db)
    assert inserted == len(EMAIL_EVENT_REGISTRY)
    db.commit.assert_called_once()
