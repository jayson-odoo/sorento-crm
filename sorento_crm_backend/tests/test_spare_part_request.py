"""SPARE-PART-ORDER-REQUEST, service level, red-first (Phase 2).

Every test cites its captain test-list id (T1..T16) and the UAC ids it proves
(documentation/plans/purchasing/spare-part-order-request-12nov-acceptance-criteria.md).
The API contract is the brief's: `app/services/spare_part_request_service.py` with
`create / update / submit / approve / reject / revise / edit_line / can_decide`.

Postgres only (`blank_session` via `_spare_part_request_support.world`); every chain is
seeded here. A red before implementation is ModuleNotFoundError on the service module (or a
missing model constant / column), never a fixture bug. Named assumptions: see the support
module's docstring (actor = user id str, data = JSON-shaped dict, create returns the OI).

T2 (DB CHECK) and T13 (committed demand) need the MIGRATED database (the CHECK and
`scm.committed_v` live in migrations): `tests/test_spare_part_request_demand.py`.
API, visibility and row attachments (T5 API, T14, T15): `tests/test_spare_part_request_api.py`.
"""
from __future__ import annotations

import pytest

from app.models.audit import AuditLog
from app.services.error_handler import AppException

from ._forms_chain_support import open_tracker, trackers
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    CREATE,
    KIND,
    OI_RAISED_NOTICE,
    approve,
    body,
    create,
    dec,
    line,
    raised,
    reload,
    row_for,
    rows_of,
    sent,
    staged,
    submitted,
    svc,
    two_staged,
    world,
)


def _consts():
    from app.models import project_so as m

    return m


# =============================================================================
# T1 - create saves a draft spare-part inquiry (R1, R2)
# =============================================================================


def test_T1_create_saves_a_draft_oi_of_type_spare_part_request(world):
    m = _consts()
    assert m.INQUIRY_TYPE_SPARE_PART == "spare_part_request"
    assert m.INQUIRY_TYPE_SALES_ORDER == "sales_order"
    assert m.INQUIRY_DRAFT == "draft"
    assert m.IV_REPLENISH == "REPLENISH"

    inquiry = create(world)

    assert inquiry.inquiry_type == m.INQUIRY_TYPE_SPARE_PART
    assert inquiry.state == m.INQUIRY_DRAFT
    assert inquiry.project_sales_order_id is None
    assert inquiry.inquiry_no.startswith("OI-"), inquiry.inquiry_no
    assert str(inquiry.requested_by) == world.requester
    assert inquiry.currency == "MYR"
    assert str(inquiry.needed_by) == "2026-12-15"
    assert inquiry.default_location == world.loc_a.warehouse_code
    assert inquiry.reason == "Spare parts for the service van"
    assert inquiry.submitted_at is None

    rows = rows_of(world.db, inquiry)
    assert len(rows) == 2
    for row in rows:
        assert row.state == m.INQUIRY_DRAFT
        assert row.verb == m.IV_REPLENISH
        assert row.ack_state == m.ACK_AWAITING
        assert row.so_line_id is None
    a = row_for(world.db, inquiry, world.product_a)
    assert a.item_code == world.product_a.product_code
    assert a.description in {world.product_a.product_name, world.product_a.description}
    assert a.description
    assert a.stock_location == world.loc_a.warehouse_code
    assert dec(a.qty) == dec("10")
    assert dec(a.unit_price) == dec("25.00")
    b = row_for(world.db, inquiry, world.product_b)
    assert b.stock_location == world.loc_b.warehouse_code
    assert dec(b.qty) * dec(b.unit_price) == dec("50.00")  # line total = qty x unit price


def test_T1_a_line_with_no_location_takes_the_header_default(world):
    """R2: location starts with the header default; each line can differ."""
    inquiry = create(world, lines=[line(world.product_a, None, qty="3", unit_price="9.90")])
    (row,) = rows_of(world.db, inquiry)
    assert row.stock_location == world.loc_a.warehouse_code


def test_T1_create_refuses_a_line_without_a_catalogue_product(world):
    """R2: catalogue product only, never a free-text line."""
    bad = {"product_id": None, "stock_location": world.loc_a.warehouse_code, "qty": "1", "unit_price": "1"}
    with pytest.raises(AppException) as excinfo:
        svc().create(world.db, body(world, lines=[bad]), world.requester)
    assert excinfo.value.status_code == 422


# =============================================================================
# T3 - submit refuses an incomplete request, and refuses with no stage configured (R5)
# =============================================================================


def _submit_status(w, inquiry) -> int:
    with pytest.raises(AppException) as excinfo:
        svc().submit(w.db, inquiry, w.requester)
    w.db.rollback()
    return excinfo.value.status_code


def test_T3_submit_with_no_lines_is_422(staged):
    inquiry = create(staged, lines=[])
    assert _submit_status(staged, inquiry) == 422
    assert reload(staged.db, inquiry).state == "draft"


def test_T3_submit_with_a_zero_qty_line_is_422(staged):
    inquiry = create(staged, lines=[line(staged.product_a, staged.loc_a, qty="0")])
    assert _submit_status(staged, inquiry) == 422


def test_T3_submit_with_no_currency_is_422(staged):
    inquiry = create(staged, currency=None)
    assert _submit_status(staged, inquiry) == 422


def test_T3_submit_with_a_line_without_location_is_422(staged):
    inquiry = create(staged, default_location=None, lines=[line(staged.product_a, None, qty="2")])
    assert _submit_status(staged, inquiry) == 422


def test_T3_submit_with_no_active_stage_configured_is_422_with_a_plain_message(world):
    inquiry = create(world)
    with pytest.raises(AppException) as excinfo:
        svc().submit(world.db, inquiry, world.requester)
    assert excinfo.value.status_code == 422
    assert excinfo.value.message and "_" not in excinfo.value.message, (
        "a plain sentence for the admin, not an internal key"
    )
    world.db.rollback()
    assert reload(world.db, inquiry).state == "draft"


def test_T3_an_inactive_stage_counts_as_none(staged):
    staged.stage1.config.is_active = False
    staged.db.commit()
    inquiry = create(staged)
    assert _submit_status(staged, inquiry) == 422


# =============================================================================
# T4 - submit moves to Pending approval at stage 1 (A1)
# =============================================================================


def test_T4_submit_moves_to_pending_approval_and_starts_stage_one(staged):
    m = _consts()
    inquiry = submitted(staged)

    assert inquiry.state == m.INQUIRY_PENDING_APPROVAL == "pending_approval"
    assert inquiry.submitted_at is not None
    for row in rows_of(staged.db, inquiry):
        assert dec(row.requested_qty) == dec(row.qty)
        assert dec(row.requested_unit_price) == dec(row.unit_price)
        assert row.state == m.INQUIRY_DRAFT, "rows stay out of purchasing's reach until raised"
    tracker = open_tracker(staged.db, KIND, inquiry.id)
    assert tracker.team_set_code == staged.stage1.team_set
    assert tracker.assigned_to_id == staged.stage1.tier1


# =============================================================================
# T5 - who may decide (A2)
# =============================================================================


def test_T5_can_decide_is_the_stage_team_or_admin_never_the_requester(staged):
    inquiry = submitted(staged)
    s = svc()
    assert s.can_decide(staged.db, inquiry, staged.requester) is False, "requester, even on the team"
    assert s.can_decide(staged.db, inquiry, staged.outsider) is False
    assert s.can_decide(staged.db, inquiry, staged.stage1.tier1) is True
    assert s.can_decide(staged.db, inquiry, staged.stage1.tier2) is True
    assert s.can_decide(staged.db, inquiry, staged.admin) is True


def test_T5_the_requester_on_the_team_cannot_approve(staged):
    inquiry = submitted(staged)
    with pytest.raises(AppException) as excinfo:
        svc().approve(staged.db, inquiry, staged.requester)
    assert excinfo.value.status_code == 403


def test_T5_a_non_member_cannot_approve_or_reject(staged):
    inquiry = submitted(staged)
    with pytest.raises(AppException) as excinfo:
        svc().approve(staged.db, inquiry, staged.outsider)
    assert excinfo.value.status_code == 403
    staged.db.rollback()
    with pytest.raises(AppException) as excinfo:
        svc().reject(staged.db, inquiry, staged.outsider, "Not needed")
    assert excinfo.value.status_code == 403


def test_T5_a_stage_member_approves(staged):
    inquiry = approve(staged, submitted(staged), staged.stage1.tier2)
    assert inquiry.state == "raised"


def test_T5_an_admin_approves(staged):
    inquiry = approve(staged, submitted(staged), staged.admin)
    assert inquiry.state == "raised"


# =============================================================================
# T6 - approver edits a line while pending (A3)
# =============================================================================


def _audits_for(db, inquiry, row) -> list:
    db.expire_all()
    ids = {str(inquiry.id), str(row.id)}
    return [
        a
        for a in db.query(AuditLog).order_by(AuditLog.changed_at, AuditLog.id).all()
        if str(a.entity_id) in ids or str(getattr(a, "root_entity_id", "") or "") == str(inquiry.id)
    ]


def _numbers(values) -> set:
    out = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        else:
            try:
                out.add(dec(v).normalize())
            except Exception:  # noqa: BLE001 - not a number
                pass

    walk(values or {})
    return out


def test_T6_approver_changes_qty_and_price_requested_values_stay_and_each_change_is_audited(staged):
    inquiry = submitted(staged)
    row = row_for(staged.db, inquiry, staged.product_a)
    before = len(_audits_for(staged.db, inquiry, row))

    svc().edit_line(staged.db, inquiry, row.id, staged.stage1.tier1, qty="8")
    staged.db.commit()
    svc().edit_line(staged.db, inquiry, row.id, staged.stage1.tier1, unit_price="27.50")
    staged.db.commit()

    row = row_for(staged.db, inquiry, staged.product_a)
    assert dec(row.qty) == dec("8")
    assert dec(row.unit_price) == dec("27.50")
    assert dec(row.requested_qty) == dec("10")
    assert dec(row.requested_unit_price) == dec("25.00")

    audits = _audits_for(staged.db, inquiry, row)
    new = audits[before:]
    assert len(new) >= 2, "one History row per change"
    qty_change = [a for a in new if dec("10") in _numbers(a.old_values) and dec("8") in _numbers(a.new_values)]
    price_change = [
        a for a in new
        if dec("25") in _numbers(a.old_values) and dec("27.5") in _numbers(a.new_values)
    ]
    assert qty_change, "qty 10 -> 8 audited old -> new"
    assert price_change, "unit price 25 -> 27.50 audited old -> new"
    assert all(str(a.user_id) == staged.stage1.tier1 for a in qty_change + price_change)


def test_T6_edit_line_on_a_draft_is_409(staged):
    inquiry = create(staged)
    row = row_for(staged.db, inquiry, staged.product_a)
    with pytest.raises(AppException) as excinfo:
        svc().edit_line(staged.db, inquiry, row.id, staged.stage1.tier1, qty="5")
    assert excinfo.value.status_code == 409


def test_T6_edit_line_by_a_non_member_or_the_requester_is_403(staged):
    inquiry = submitted(staged)
    row = row_for(staged.db, inquiry, staged.product_a)
    for who in (staged.outsider, staged.requester):
        with pytest.raises(AppException) as excinfo:
            svc().edit_line(staged.db, inquiry, row.id, who, qty="5")
        assert excinfo.value.status_code == 403
        staged.db.rollback()
    assert dec(row_for(staged.db, inquiry, staged.product_a).qty) == dec("10")


# =============================================================================
# T7 - approve with every line at 0 is refused (A4)
# =============================================================================


def test_T7_approve_with_every_line_at_zero_is_422(staged):
    inquiry = submitted(staged)
    for row in rows_of(staged.db, inquiry):
        svc().edit_line(staged.db, inquiry, row.id, staged.stage1.tier1, qty="0")
    staged.db.commit()
    with pytest.raises(AppException) as excinfo:
        svc().approve(staged.db, inquiry, staged.stage1.tier1)
    assert excinfo.value.status_code == 422
    staged.db.rollback()
    assert reload(staged.db, inquiry).state == "pending_approval"


# =============================================================================
# T8 - two chained stages (A6, non-final stage)
# =============================================================================


def test_T8_stage_one_approval_moves_to_stage_two_then_stage_two_raises(two_staged):
    w = two_staged
    inquiry = submitted(w)

    inquiry = approve(w, inquiry, w.stage1.tier1)
    assert inquiry.state == "pending_approval", "a non-final stage keeps it pending"
    tracker = open_tracker(w.db, KIND, inquiry.id)
    assert tracker.team_set_code == w.stage2.team_set, "stage 2 is now the active stage"
    assert all(r.state == "draft" for r in rows_of(w.db, inquiry))

    with pytest.raises(AppException) as excinfo:
        svc().approve(w.db, inquiry, w.stage1.tier1)
    assert excinfo.value.status_code == 403, "a stage-1-only member cannot decide stage 2"
    w.db.rollback()
    assert svc().can_decide(w.db, inquiry, w.stage1.tier1) is False
    assert svc().can_decide(w.db, inquiry, w.stage2.tier1) is True

    inquiry = approve(w, inquiry, w.stage2.tier1)
    assert inquiry.state == "raised"
    assert not trackers(w.db, KIND, inquiry.id, open_only=True)


# =============================================================================
# T9 - final approval raises, cancels zero lines, notifies purchasing once (A6, P1, P2)
# =============================================================================


def _purchasing_notices(w) -> list:
    return [c for c in w.sent if c[0] == w.buyer and c[1] == OI_RAISED_NOTICE]


def test_T9_final_approval_raises_qty_rows_cancels_zero_rows_and_tells_purchasing_once(staged):
    w = staged
    inquiry = create(w)
    assert not _purchasing_notices(w), "nothing to purchasing on create"
    svc().submit(w.db, inquiry, w.requester)
    w.db.commit()
    assert not _purchasing_notices(w), "nothing to purchasing on submit"

    zero = row_for(w.db, inquiry, w.product_b)
    svc().edit_line(w.db, inquiry, zero.id, w.stage1.tier1, qty="0")
    w.db.commit()
    inquiry = approve(w, reload(w.db, inquiry), w.stage1.tier1)

    assert inquiry.state == "raised"
    assert str(inquiry.approved_by) == w.stage1.tier1
    assert inquiry.approved_at is not None
    assert row_for(w.db, inquiry, w.product_a).state == "raised"
    assert row_for(w.db, inquiry, w.product_b).state == "cancelled"
    assert row_for(w.db, inquiry, w.product_a).verb == "REPLENISH"

    notices = _purchasing_notices(w)
    assert len(notices) == 1, notices
    assert str(notices[0][2]) == str(inquiry.id)
    w.db.commit()  # a later, unrelated commit fires nothing more
    assert len(_purchasing_notices(w)) == 1


# =============================================================================
# T10 - reject needs a reason; resubmit restarts at stage 1 (A5)
# =============================================================================


def test_T10_reject_without_a_reason_is_422(staged):
    inquiry = submitted(staged)
    for reason in (None, "", "   "):
        with pytest.raises(AppException) as excinfo:
            svc().reject(staged.db, inquiry, staged.stage1.tier1, reason)
        assert excinfo.value.status_code == 422
        staged.db.rollback()
    assert reload(staged.db, inquiry).state == "pending_approval"


def test_T10_reject_then_the_requester_edits_and_resubmits_from_stage_one(two_staged):
    w = two_staged
    inquiry = approve(w, submitted(w), w.stage1.tier1)  # now at stage 2
    svc().reject(w.db, inquiry, w.stage2.tier1, "Use the cheaper seal")
    w.db.commit()
    inquiry = reload(w.db, inquiry)
    assert inquiry.state == "rejected"
    assert inquiry.reject_reason == "Use the cheaper seal"
    assert not trackers(w.db, KIND, inquiry.id, open_only=True)

    svc().update(
        w.db, inquiry,
        body(w, lines=[line(w.product_a, w.loc_a, qty="6", unit_price="19.00")]),
        w.requester,
    )
    w.db.commit()
    svc().submit(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    inquiry = reload(w.db, inquiry)
    assert inquiry.state == "pending_approval"
    tracker = open_tracker(w.db, KIND, inquiry.id)
    assert tracker.team_set_code == w.stage1.team_set, "back to level 1"
    (row,) = rows_of(w.db, inquiry)
    assert dec(row.requested_qty) == dec("6") and dec(row.requested_unit_price) == dec("19.00")


def test_T10_only_the_requester_edits_a_rejected_request(staged):
    inquiry = submitted(staged)
    svc().reject(staged.db, inquiry, staged.stage1.tier1, "Wrong part")
    staged.db.commit()
    with pytest.raises(AppException) as excinfo:
        svc().update(staged.db, reload(staged.db, inquiry), body(staged), staged.outsider)
    assert excinfo.value.status_code == 403


# =============================================================================
# T11 - revise until purchasing acknowledges (V1, V2)
# =============================================================================


def test_T11_revise_after_final_approval_with_nothing_acknowledged_returns_to_draft(staged):
    inquiry = raised(staged)
    svc().revise(staged.db, inquiry, staged.requester)
    staged.db.commit()
    inquiry = reload(staged.db, inquiry)
    assert inquiry.state == "draft"
    assert inquiry.approved_at is None and inquiry.approved_by is None
    assert all(r.state == "draft" for r in rows_of(staged.db, inquiry))
    assert not trackers(staged.db, KIND, inquiry.id, open_only=True)


def test_T11_revise_after_purchasing_acknowledged_a_row_is_409(staged):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    inquiry = raised(staged)
    row = row_for(staged.db, inquiry, staged.product_a)
    ProjectOrderInquiryService(staged.db).acknowledge_rows([str(row.id)], actor_user_id=staged.buyer)
    staged.db.commit()
    assert row_for(staged.db, inquiry, staged.product_a).ack_state == "acknowledged"

    with pytest.raises(AppException) as excinfo:
        svc().revise(staged.db, reload(staged.db, inquiry), staged.requester)
    assert excinfo.value.status_code == 409
    staged.db.rollback()
    assert reload(staged.db, inquiry).state == "raised"


def test_T11_only_the_requester_revises(staged):
    inquiry = raised(staged)
    with pytest.raises(AppException) as excinfo:
        svc().revise(staged.db, inquiry, staged.outsider)
    assert excinfo.value.status_code == 403


# =============================================================================
# T12 - the existing OI service refuses draft rows and leaves pre-approval headers alone
# =============================================================================


def _oi_service(db):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    return ProjectOrderInquiryService(db)


def test_T12_acknowledge_a_draft_row_is_409(staged):
    inquiry = submitted(staged)
    row = row_for(staged.db, inquiry, staged.product_a)
    with pytest.raises(AppException) as excinfo:
        _oi_service(staged.db).acknowledge_rows([str(row.id)], actor_user_id=staged.buyer)
    assert excinfo.value.status_code == 409


def test_T12_mark_a_draft_row_is_409(staged):
    inquiry = create(staged)
    row = row_for(staged.db, inquiry, staged.product_a)
    with pytest.raises(AppException) as excinfo:
        _oi_service(staged.db).mark_rows([str(row.id)], state="actioned", actor_user_id=staged.buyer)
    assert excinfo.value.status_code == 409


def test_T12_reject_a_draft_row_is_409(staged):
    inquiry = submitted(staged)
    row = row_for(staged.db, inquiry, staged.product_a)
    with pytest.raises(AppException) as excinfo:
        _oi_service(staged.db).reject_row(str(row.id), reason="No", actor_user_id=staged.buyer)
    assert excinfo.value.status_code == 409


def test_T12_the_header_state_refresh_does_not_move_a_draft_or_pending_header(staged):
    draft = create(staged)
    pending = submitted(staged)
    _oi_service(staged.db)._refresh_inquiry_states({str(draft.id), str(pending.id)})
    staged.db.commit()
    assert reload(staged.db, draft).state == "draft"
    assert reload(staged.db, pending).state == "pending_approval"


# =============================================================================
# T16 - registered: permission slug and the Form SLA type (A1, contract)
# =============================================================================


def test_T16_the_create_slug_is_registered():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert CREATE in {p["slug"] for p in PERMISSION_REGISTRY}


def test_T16_spare_part_request_is_a_form_sla_type_everywhere_it_must_match():
    from app.schemas.sla import _FORM_SLA_TYPES, FormSLAConfigBase
    from app.services import form_sla_service as f

    assert KIND in f.FORM_SLA_TYPES
    assert KIND in _FORM_SLA_TYPES
    assert f._form_detail_link(KIND, "abc") == "/project-sales/order-inquiries/abc"
    row = FormSLAConfigBase(
        source_entity_type=KIND,
        stage_code="spare_part_approval",
        policy_id="00000000-0000-0000-0000-000000000000",
        agent_code="spare_parts",
        start_event="submitted",
    )
    assert row.source_entity_type == KIND
