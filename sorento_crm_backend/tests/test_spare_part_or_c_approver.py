"""SPARE-PART-OR-B C, red-first (Phase 2). C1: an approver raises / revises without approval.

Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md C1.1-C1.5.
Postgres only (`blank_session` through the OR-B world); every row seeded here.

NAMED CONTRACT CHOICES (the UAC leaves them open):
1. `spare_part_request_service.is_final_approver(db, user_id, company_id) -> bool`.
   Final level = the configured `spare_part_request` Form SLA level with no next level; any
   tier of its team set counts (`_on_stage_team` / `get_user_tier_in_team_set`).
2. The approver-raise audit row is `SPR_APPROVED` or `SPR_RAISED` whose description reads
   "Raised by approver"; the approver revision's reads "Revised by approver" (C1.2 / C1.3 name
   the words, not the event key, so only the words are asserted).
3. Stage 1's tier-1 member of a ONE-level chain is a final approver and holds the create slug
   (`add_stages` grants it), so it can be a requester.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.error_handler import AppException

from ._spare_part_or_c_support import (  # noqa: F401  (fixtures)
    audit_texts,
    change_qty,
    create_as,
    handovers,
    open_trackers,
    plain,
    plain_two,
    raised_by,
    revise_as,
    row_for,
    rows_of,
    sent,
    submit_as,
    svc,
    worklist_rows,
    world,
)
from ._forms_chain_support import SORENTO


# =============================================================================
# C1.1 - who is an approver
# =============================================================================


def test_C1_1_a_final_level_team_member_is_an_approver(plain):
    w = plain
    assert svc().is_final_approver(w.db, w.stage1.tier1, SORENTO) is True
    assert svc().is_final_approver(w.db, w.stage1.tier2, SORENTO) is True


def test_C1_1_admin_is_an_approver(plain):
    w = plain
    assert svc().is_final_approver(w.db, w.admin, SORENTO) is True


def test_C1_1_a_user_on_no_team_is_not_an_approver(plain):
    w = plain
    assert svc().is_final_approver(w.db, w.outsider, SORENTO) is False
    assert svc().is_final_approver(w.db, w.requester, SORENTO) is False


def test_C1_1_only_the_last_level_counts(plain_two):
    w = plain_two
    assert svc().is_final_approver(w.db, w.stage1.tier1, SORENTO) is False, "level 1 is not final"
    assert svc().is_final_approver(w.db, w.stage2.tier1, SORENTO) is True


# =============================================================================
# C1.2 - an approver's submit raises at once
# =============================================================================


def test_C1_2_an_approver_submit_raises_with_an_oi_number_and_no_open_stage(plain):
    w = plain
    approver = w.stage1.tier1
    inquiry = submit_as(w, create_as(w, approver), approver)
    assert inquiry.state == "raised", inquiry.state
    assert inquiry.oi_no, "the OI number is minted"
    assert str(inquiry.approved_by) == str(approver)
    assert inquiry.approved_at is not None
    assert not open_trackers(w, inquiry), "no approval level opened"
    assert {r.state for r in rows_of(w.db, inquiry)} == {"raised"}


def test_C1_2_the_approver_raise_is_audited_raised_by_approver(plain):
    w = plain
    approver = w.stage1.tier1
    inquiry = submit_as(w, create_as(w, approver), approver)
    texts = [text for _event, text in audit_texts(w, inquiry)]
    assert any("Raised by approver" in t for t in texts), texts


def test_C1_2_an_approver_raise_records_a_raised_handover_line_per_row(plain, handovers):
    w = plain
    approver = w.stage1.tier1
    inquiry = create_as(w, approver)
    handovers.clear()
    inquiry = submit_as(w, inquiry, approver)
    ids = {str(r.id) for r in rows_of(w.db, inquiry)}
    raised_lines = {h[0] for h in handovers if h[1] == "raised"}
    assert raised_lines == ids, handovers


def test_C1_2_the_approver_raise_is_visible_to_purchasing(plain):
    w = plain
    approver = w.stage1.tier1
    inquiry = submit_as(w, create_as(w, approver), approver)
    assert len(worklist_rows(w, inquiry)) == 2


def test_C1_2_an_admin_raises_with_no_approval_level_configured(world):
    """No Form SLA level at all: the 422 "no approval level" does not apply to an admin."""
    w = world
    inquiry = submit_as(w, create_as(w, w.admin), w.admin)
    assert inquiry.state == "raised", inquiry.state
    assert inquiry.oi_no
    assert str(inquiry.approved_by) == str(w.admin)


def test_C1_2_a_non_approver_with_no_level_configured_still_gets_the_422(world):
    w = world
    inquiry = create_as(w, w.requester)
    with pytest.raises(AppException) as excinfo:
        svc().submit(w.db, inquiry, w.requester)
    assert excinfo.value.status_code == 422
    w.db.rollback()


# =============================================================================
# C1.3 - an approver requester's revision applies at Submit
# =============================================================================


def test_C1_3_an_approver_revision_applies_at_submit_with_no_stage(plain):
    w = plain
    approver = w.stage1.tier1
    inquiry = raised_by(w, approver, approver)
    number = inquiry.oi_no
    inquiry = revise_as(w, inquiry, approver)
    change_qty(w, inquiry, w.product_a, "12", approver)
    inquiry = submit_as(w, inquiry, approver)
    assert inquiry.revision_state is None, "applied at once"
    assert not open_trackers(w, inquiry), "no approval level opened"
    row = row_for(w.db, inquiry, w.product_a)
    assert Decimal(str(row.qty)) == Decimal("12")
    assert Decimal(str(row.previous_qty)) == Decimal("10")
    assert row.revised_qty is None
    assert inquiry.oi_no == number


def test_C1_3_the_approver_revision_is_audited_revised_by_approver(plain):
    w = plain
    approver = w.stage1.tier1
    inquiry = revise_as(w, raised_by(w, approver, approver), approver)
    change_qty(w, inquiry, w.product_a, "12", approver)
    inquiry = submit_as(w, inquiry, approver)
    texts = [text for _event, text in audit_texts(w, inquiry)]
    assert any("Revised by approver" in t for t in texts), texts


def test_C1_3_between_revise_and_submit_the_moved_row_waits_for_cs(plain):
    w = plain
    approver = w.stage1.tier1
    inquiry = revise_as(w, raised_by(w, approver, approver), approver)
    row = change_qty(w, inquiry, w.product_a, "12", approver)
    assert worklist_rows(w, inquiry)[str(row.id)].get("waiting_for_cs") is True


# =============================================================================
# C1.4 - a non-approver requester is unchanged
# =============================================================================


def test_C1_4_a_non_approver_submit_opens_level_one(plain):
    w = plain
    inquiry = submit_as(w, create_as(w, w.requester), w.requester)
    assert inquiry.state == "pending_approval"
    assert inquiry.oi_no is None
    assert open_trackers(w, inquiry), "level 1 is open"


def test_C1_4_a_non_approver_revision_needs_approval(plain):
    w = plain
    inquiry = revise_as(w, raised_by(w, w.requester, w.stage1.tier1), w.requester)
    change_qty(w, inquiry, w.product_a, "12", w.requester)
    inquiry = submit_as(w, inquiry, w.requester)
    assert inquiry.revision_state == "pending_approval"
    assert Decimal(str(row_for(w.db, inquiry, w.product_a).qty)) == Decimal("10")


def test_C1_4_a_level_one_member_of_a_two_level_chain_is_not_an_approver(plain_two):
    w = plain_two
    member = w.stage1.tier1
    inquiry = submit_as(w, create_as(w, member), member)
    assert inquiry.state == "pending_approval", "level 1 is not the final level"


# =============================================================================
# C1.5 - can_decide unchanged
# =============================================================================


def test_C1_5_a_final_approver_cannot_decide_level_one_of_someone_elses_request(plain_two):
    w = plain_two
    inquiry = submit_as(w, create_as(w, w.requester), w.requester)
    assert inquiry.state == "pending_approval", "precondition"
    assert svc().can_decide(w.db, inquiry, w.stage2.tier1) is False
    with pytest.raises(AppException) as excinfo:
        svc().approve(w.db, inquiry, w.stage2.tier1)
    assert excinfo.value.status_code == 403
    w.db.rollback()
