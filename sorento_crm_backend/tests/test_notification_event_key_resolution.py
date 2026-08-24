"""Email event-key resolution (app/tasks/notification_tasks._resolve_event_key).

CHANGE 2 (PLAN-sla-extend-deadline follow-up): the resolver strips a trailing
":<n>" occurrence suffix before lookup so the per-occurrence event types
(deadline_extended:1, deadline_extended:2, ...) all map to the same outbox event
key (sla_deadline_extended). Existing colon composites that are NOT trailing-digits
(e.g. "external_created") must keep working.

Pure-unit: _resolve_event_key reads only notification.type + notification.event_type.

Run:
    venv/bin/pytest tests/test_notification_event_key_resolution.py -q
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tasks.notification_tasks import _resolve_event_key


def _note(type_, event_type):
    return SimpleNamespace(type=type_, event_type=event_type)


# CHANGE 2: ":N" suffix stripped -> maps to sla_deadline_extended.
@pytest.mark.parametrize("notif_type", ["form_sla", "conversation_sla"])
@pytest.mark.parametrize("n", [1, 2, 7, 99])
def test_deadline_extended_occurrence_suffix_maps_to_sla_event(notif_type, n):
    key = _resolve_event_key(_note(notif_type, f"deadline_extended:{n}"))
    assert key == "sla_deadline_extended"


# Conversation-SLA coverage fan-out keys each assignment OCCURRENCE as
# "assigned:<unix_ts>" so a re-assignment of the reused tracker re-notifies coverers.
# The resolver must strip the numeric suffix and resolve WITHOUT error to a REGISTERED
# key - "conversation_sla:assigned" is not mapped, so it falls back to the registered
# "notification_delivery". (Without the strip, the raw "assigned:1782282875" would carry
# into the lookup and silently never match, re-introducing the silent-drop class.)
@pytest.mark.parametrize("ts", [0, 1, 1782282875])
def test_assigned_occurrence_suffix_resolves_to_registered_key(ts):
    from app.services.email_event_registry import get_event_def

    key = _resolve_event_key(_note("conversation_sla", f"assigned:{ts}"))
    assert key == "notification_delivery"
    assert get_event_def(key) is not None


def test_deadline_extended_no_suffix_still_maps(notif_type="form_sla"):
    """The base composite (no suffix) also maps - registry has both forms."""
    assert _resolve_event_key(_note("form_sla", "deadline_extended")) == "sla_deadline_extended"
    assert (
        _resolve_event_key(_note("conversation_sla", "deadline_extended"))
        == "sla_deadline_extended"
    )


# CHANGE 2 guard: non-trailing-digit colon composites are NOT stripped.
def test_external_created_composite_not_stripped():
    """Only a trailing ':<digits>' is stripped - 'external_created' is a real
    composite suffix and must resolve to its own key, not be mangled."""
    key = _resolve_event_key(
        _note("stock_inquiry_notification", "external_created")
    )
    assert key == "stock_inquiry_created_external"


def test_composite_with_internal_digits_not_stripped():
    """A colon-suffix that is not purely trailing digits is left intact."""
    # 'assigned' (form_sla:assigned) is a composite that must remain mapped.
    assert _resolve_event_key(_note("form_sla", "assigned")) == "form_sla_assigned"
    assert _resolve_event_key(_note("form_sla", "escalated")) == "form_sla_escalated"


def test_unknown_type_falls_back_to_notification_delivery():
    assert _resolve_event_key(_note("totally_unknown", "")) == "notification_delivery"


def test_type_only_lookup_when_event_type_empty():
    assert _resolve_event_key(_note("form_sla", "")) == "form_sla_updated"
