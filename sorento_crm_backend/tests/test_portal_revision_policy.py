"""Revision policy matrix (UAC A3/A4, B1-B3, C3).

The policy is what the portal renders the Revise action off, and it is re-checked
server side on every revise - so every branch that can say "no" is pinned here, for
ALL THREE enabled types rather than for stock inquiry alone.

Run: pytest tests/test_portal_revision_policy.py -v
"""
from __future__ import annotations

import pytest

from app.services.portal_revision_service import PortalRevisionService
from tests._revision_harness import (
    REVISABLE_TYPES,
    seed_config,
    seed_contact,
    seed_entity,
    seed_system_settings,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _policy(db, kind, **entity_kwargs):
    contact = seed_contact(db)
    row = seed_entity(db, kind, contact, **entity_kwargs)
    return PortalRevisionService(db).resolve_policy(kind, row)


# ---------------------------------------------------------------- enabled path


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_allowed_at_a_permitted_status(db, kind):
    seed_config(db, kind)
    policy = _policy(db, kind)
    assert policy.enabled is True
    assert policy.allowed is True
    assert policy.blocked_reason is None


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_null_max_inherits_the_global_cap(db, kind):
    seed_system_settings(db, cap=3)
    seed_config(db, kind, max_revisions=None)
    policy = _policy(db, kind)
    assert policy.max == 3
    assert policy.remaining == 3


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_per_type_max_overrides_the_global_cap(db, kind):
    seed_system_settings(db, cap=2)
    seed_config(db, kind, max_revisions=5)
    policy = _policy(db, kind)
    assert policy.max == 5


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_remaining_counts_down_from_used(db, kind):
    seed_system_settings(db, cap=3)
    seed_config(db, kind)
    policy = _policy(db, kind, revision_no=1)
    assert (policy.used, policy.max, policy.remaining) == (1, 3, 2)
    assert policy.allowed is True


# ---------------------------------------------------------------- blocked paths


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_missing_config_row_fails_closed(db, kind):
    """A type with no config row is disabled, never accidentally open (UAC A3)."""
    policy = _policy(db, kind)
    assert (policy.enabled, policy.allowed) == (False, False)
    assert policy.blocked_reason == "This form cannot be revised."


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_per_type_disabled(db, kind):
    seed_config(db, kind, is_enabled=False)
    policy = _policy(db, kind)
    assert (policy.enabled, policy.allowed) == (False, False)


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_global_kill_switch_beats_an_enabled_type(db, kind):
    seed_system_settings(db, enabled=False)
    seed_config(db, kind, is_enabled=True)
    policy = _policy(db, kind)
    assert (policy.enabled, policy.allowed) == (False, False)


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_zero_cap_disables_the_type_whatever_is_enabled_says(db, kind):
    seed_config(db, kind, is_enabled=True, max_revisions=0)
    policy = _policy(db, kind)
    assert (policy.enabled, policy.allowed, policy.max) == (False, False, 0)


@pytest.mark.parametrize(
    "kind,status",
    [
        ("stock_inquiry", "closed"),
        ("stock_inquiry", "rejected"),
        ("stock_inquiry", "voided"),
        ("purchase_request", "processed_by_cs"),
        ("purchase_request", "rejected"),
        ("sponsorship_form", "closed"),
    ],
)
def test_terminal_status_blocks_with_its_own_sentence(db, kind, status):
    seed_config(db, kind)
    policy = _policy(db, kind, status=status)
    assert policy.enabled is True  # the TYPE is on; this record is not eligible
    assert policy.allowed is False
    assert status.replace("_", " ") in policy.blocked_reason


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_status_outside_allowed_list_blocks(db, kind):
    seed_config(db, kind)
    policy = _policy(db, kind, status="draft")
    assert policy.allowed is False
    assert policy.blocked_reason


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_a_draft_is_edited_not_revised(db, kind):
    from datetime import datetime

    seed_config(db, kind)
    policy = _policy(db, kind, portal_draft_at=datetime.utcnow())
    assert policy.allowed is False
    assert "draft" in policy.blocked_reason.lower()


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_cap_reached_says_how_many_were_used(db, kind):
    seed_system_settings(db, cap=2)
    seed_config(db, kind)
    policy = _policy(db, kind, revision_no=2)
    assert (policy.allowed, policy.remaining) == (False, 0)
    assert policy.blocked_reason == "You have used all 2 revisions."


@pytest.mark.parametrize("kind", REVISABLE_TYPES)
def test_voided_record_blocks(db, kind):
    from datetime import datetime

    seed_config(db, kind)
    policy = _policy(db, kind, voided_at=datetime.utcnow())
    assert policy.allowed is False
    assert "voided" in policy.blocked_reason.lower()


def test_complaint_has_no_adapter_and_is_disabled(db):
    """Complaint ships with a config row so it is one checkbox away, but with no
    adapter registered it still fails closed today (UAC A5, K)."""
    seed_config(db, "complaint", is_enabled=True, allowed_statuses=["submitted"])
    contact = seed_contact(db)
    service = PortalRevisionService(db)
    from app.models.complaints import Complaint

    import uuid

    complaint = Complaint(id=str(uuid.uuid4()), status="submitted", contact_id=contact.id)
    db.add(complaint)
    db.commit()
    policy = service.resolve_policy("complaint", complaint)
    assert (policy.enabled, policy.allowed) == (False, False)


def test_policy_block_carries_every_declared_field(db):
    """The response contract (UAC B1). A missing key here is a silently dead
    Revise button on the portal."""
    seed_config(db, "stock_inquiry")
    policy = _policy(db, "stock_inquiry")
    assert set(policy.as_dict()) == {
        "enabled",
        "allowed",
        "used",
        "max",
        "remaining",
        "blocked_reason",
        # The confirm dialog names the restart destination from config (UAC E1a).
        # See tests/test_revision_restart_stage_label.py for what it resolves to.
        "restart_stage_label",
    }
