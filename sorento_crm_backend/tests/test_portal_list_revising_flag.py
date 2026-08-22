"""Portal list `has_revision_draft`: a row with an unsent revision draft parked
carries the flag, so the FE list card can show a "Revising" chip - separate
from the row's real `status`, which stays untouched (see
SubmissionForm.tsx's status pill and PortalLanding.tsx's Revising badge).

``PortalService._ids_with_revision_draft`` is what computes it: one query per
list call, filtered on BOTH ``source_entity_id`` and ``source_entity_type`` so
a draft on one submission type can never leak the flag onto a same-id row of
a different kind.

Run: pytest tests/test_portal_list_revising_flag.py -v
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from app.services.portal_revision_service import PortalRevisionService
from app.services.portal_service import PortalService
from tests._pg_fixture import blank_session
from tests._revision_harness import (
    seed_config,
    seed_contact,
    seed_entity,
    seed_system_settings,
    seed_token,
)


@pytest.fixture(autouse=True)
def no_queue():
    """Never enqueue a real RQ job from a test: a worker in another worktree would
    pick it up."""
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _flags(db, token, kind) -> dict[str, bool]:
    summaries = PortalService(db).list_submissions(token, kind)
    return {s["id"]: s["has_revision_draft"] for s in summaries}


def test_list_marks_only_the_row_with_a_saved_draft(db):
    seed_system_settings(db, cap=3)
    seed_config(db, "stock_inquiry")
    contact = seed_contact(db)
    token = seed_token(contact)
    drafted = seed_entity(db, "stock_inquiry", contact)
    untouched = seed_entity(db, "stock_inquiry", contact)

    PortalRevisionService(db).save_draft(
        token,
        "stock_inquiry",
        str(drafted.id),
        {"quantity": "9"},
        "Thinking about the quantity",
        drafted.revision_no,
    )

    flags = _flags(db, token, "stock_inquiry")
    assert flags[str(drafted.id)] is True
    assert flags[str(untouched.id)] is False


def test_flag_clears_for_both_rows_once_the_draft_is_sent(db):
    seed_system_settings(db, cap=3)
    seed_config(db, "stock_inquiry")
    contact = seed_contact(db)
    token = seed_token(contact)
    drafted = seed_entity(db, "stock_inquiry", contact)
    untouched = seed_entity(db, "stock_inquiry", contact)
    service = PortalRevisionService(db)

    service.save_draft(
        token,
        "stock_inquiry",
        str(drafted.id),
        {"item_description": "Updated description"},
        "Thinking about the quantity",
        drafted.revision_no,
    )
    assert _flags(db, token, "stock_inquiry")[str(drafted.id)] is True

    service.revise(
        token,
        "stock_inquiry",
        str(drafted.id),
        {"item_description": "Updated description"},
        "Wrong quantity, corrected it",
        drafted.revision_no,
    )

    flags = _flags(db, token, "stock_inquiry")
    assert flags[str(drafted.id)] is False
    assert flags[str(untouched.id)] is False


def test_flag_clears_once_the_draft_is_discarded(db):
    seed_system_settings(db, cap=3)
    seed_config(db, "stock_inquiry")
    contact = seed_contact(db)
    token = seed_token(contact)
    drafted = seed_entity(db, "stock_inquiry", contact)
    service = PortalRevisionService(db)

    service.save_draft(
        token,
        "stock_inquiry",
        str(drafted.id),
        {"quantity": "9"},
        "Reason",
        drafted.revision_no,
    )
    assert _flags(db, token, "stock_inquiry")[str(drafted.id)] is True

    service.discard_draft("stock_inquiry", str(drafted.id))

    assert _flags(db, token, "stock_inquiry")[str(drafted.id)] is False


def test_ids_with_revision_draft_filters_on_source_entity_type(db):
    """A draft parked under one kind (e.g. purchase_request) must never mark a
    row of a different kind (sponsorship_form) that happens to share the same
    id, even though both kinds are stored on the SAME PurchaseRequestHeader
    table and discriminated only by request_type."""
    seed_system_settings(db, cap=3)
    seed_config(db, "purchase_request")
    contact = seed_contact(db)
    token = seed_token(contact)
    row = seed_entity(db, "purchase_request", contact)

    PortalRevisionService(db).save_draft(
        token,
        "purchase_request",
        str(row.id),
        {"purpose": "Updated purpose"},
        "Reason",
        row.revision_no,
    )

    service = PortalService(db)
    assert service._ids_with_revision_draft("purchase_request", [str(row.id)]) == {
        str(row.id)
    }
    # Same id, different kind: the draft must not leak across the discriminator.
    assert service._ids_with_revision_draft("sponsorship_form", [str(row.id)]) == set()
