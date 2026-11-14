"""SPARE-PART-OR-B fix round 1 (review findings), red-first (Phase 2). Backend half.

Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md (U2, U4)
plus the review findings of round 1. Postgres only (`blank_session` via the shared world);
every row seeded here (CI's database is empty).

F1 BLOCKER: a revision on a row purchasing has LINKED restates the links exactly as an SO qty
   settle does (`_settle_row_in_place`: `_trim_links` then `refresh_link_state`): 10 -> 6 trims
   the link to 6 and the row reads placed; 10 -> 12 leaves the row not fully placed (2 open).
F2 Kill gaps: (a) nothing moved -> no `mark_purchasing_email_trigger`; (b) a row revised to 0
   goes through `ProjectOrderInquiryService.cancel_row_told` (cancel record + handover cancel
   item); (c) `restate_row` is called once per moved row.
F3 `next_inquiry_no` takes a TRANSACTION-scoped advisory lock keyed on company + prefix
   (checked through `pg_locks` of this backend inside the test's transaction).
F4 OR detail while a revision is open: `lines[].total` and header `total` use revised_qty.
F5 Photos: nobody writes row photos while a revision is open (upload -> 403 / 409).
F6 OR list: the "pending_approval" filter includes an approved request whose revision is
   pending; the list row carries `effective_state` (revision_state when one is open, else
   state: NAMED CONTRACT CHOICE); search matches oi_no.
F7 Security: a requester whose create slug was removed cannot PATCH a revision qty (403); the
   requester cannot approve / reject their own pending revision (403); a non-requester cannot
   edit a draft revision (403); a decider not on the stage cannot edit a pending revision
   (403); another request's row id is 404; the backfill numbers two companies independently.
F8 Lead rule: Submit on an open revision whose live rows were all cancelled by purchasing
   answers 200, closes the revision (revision_state null), writes a History entry, sends
   nothing (no handover item, no notification).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.services.error_handler import AppException

from ._forms_chain_support import SORENTO, uid
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    KIND,
    ROW_ATT,
    SPR,
    TINY_PNG,
    approve,
    dec,
    raised,
    reload,
    row_for,
    rows_of,
    sent,
    staged,
    stub_storage,
    submitted,
    svc,
    world,
)


# ------------------------------------------------------------------ helpers


def _oi(w):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    return ProjectOrderInquiryService(w.db)


def _revise(w, inquiry):
    svc().revise(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    return reload(w.db, inquiry)


def _change(w, inquiry, product, qty, actor=None):
    row = row_for(w.db, inquiry, product)
    svc().edit_line(w.db, reload(w.db, inquiry), row.id, actor or w.requester, qty=qty)
    w.db.commit()
    return row_for(w.db, inquiry, product)


def _submit(w, inquiry):
    svc().submit(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    return reload(w.db, inquiry)


def _pending_revision(w, qty="12", product=None):
    inquiry = _revise(w, raised(w))
    _change(w, inquiry, product or w.product_a, qty)
    return _submit(w, inquiry)


def _po_line(w, product, warehouse, qty) -> str:
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier

    supplier = Supplier(
        id=uid(), company_id=w.company_id, supplier_code=f"ZZT-{uid()[:8]}",
        supplier_name="ZZT spare supplier",
    )
    w.db.add(supplier)
    w.db.flush()
    po = PurchaseOrder(
        id=uid(), company_id=w.company_id, po_number=f"ZZT-PO-{uid()[:8]}",
        supplier_id=supplier.id, issue_date=date(2026, 11, 1), status="active",
    )
    w.db.add(po)
    w.db.flush()
    line = PurchaseOrderLine(
        id=uid(), company_id=w.company_id, purchase_order_id=po.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(qty), qty_received=Decimal("0"),
        expected_date=date(2026, 12, 1), line_status="open",
    )
    w.db.add(line)
    w.db.commit()
    return str(line.id)


def _link(w, row, product, warehouse, qty):
    """Purchasing places the row on a PO line (the real link writer)."""
    line_id = _po_line(w, product, warehouse, qty)
    _oi(w).place_on_po_allocations(
        str(row.id), [{"po_line_id": line_id, "qty": Decimal(qty)}], actor_user_id=w.buyer
    )
    w.db.commit()


def _linked_qty(w, row) -> Decimal:
    links = _oi(w)._links_of(str(row.id))  # noqa: SLF001
    return sum((dec(l.qty) for l in links), Decimal("0"))


def _spy(monkeypatch, owner, name):
    calls: list = []
    real = getattr(owner, name)

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(owner, name, wrapper)
    return calls


@pytest.fixture
def handovers(monkeypatch):
    """Every handover email item queued: (row_id, kind, was)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    calls: list = []
    real = ProjectOrderInquiryService._record_handover

    def spy(self, row, *, kind, was=None, **kw):
        calls.append((str(row.id), kind, dict(was) if was else None))
        return real(self, row, kind=kind, was=was, **kw)

    monkeypatch.setattr(ProjectOrderInquiryService, "_record_handover", spy)
    return calls


# =============================================================================
# F1 BLOCKER - a linked row restates its links like an SO qty settle
# =============================================================================


def test_F1_a_revision_down_to_6_trims_the_link_to_6_and_the_row_stays_placed(staged, handovers):
    w = staged
    inquiry = raised(w)
    row = row_for(w.db, inquiry, w.product_a)  # qty 10
    _link(w, row, w.product_a, w.loc_a, 10)
    assert _linked_qty(w, row_for(w.db, inquiry, w.product_a)) == Decimal("10"), "precondition"
    assert row_for(w.db, inquiry, w.product_a).state == "placed", "precondition: fully placed"

    inquiry = _pending_revision(w, qty="6")
    approve(w, inquiry, w.stage1.tier1)
    row = row_for(w.db, inquiry, w.product_a)
    assert dec(row.qty) == Decimal("6")
    assert _linked_qty(w, row) == Decimal("6"), "the link is trimmed to the new qty"
    assert row.state == "placed", "refresh_link_state: fully covered still"


def test_F1_a_revision_up_to_12_leaves_the_row_not_fully_placed(staged, handovers):
    w = staged
    inquiry = raised(w)
    row = row_for(w.db, inquiry, w.product_a)
    _link(w, row, w.product_a, w.loc_a, 10)
    assert _linked_qty(w, row_for(w.db, inquiry, w.product_a)) == Decimal("10"), "precondition"
    assert row_for(w.db, inquiry, w.product_a).state == "placed", "precondition"

    inquiry = _pending_revision(w, qty="12")
    approve(w, inquiry, w.stage1.tier1)
    row = row_for(w.db, inquiry, w.product_a)
    assert dec(row.qty) == Decimal("12")
    assert _linked_qty(w, row) == Decimal("10"), "the 10 placed stays"
    assert row.state != "placed", "2 of 12 are uncovered: refresh_link_state re-reads it"
    assert row.state == "partly_linked"


def test_F1_the_link_trim_and_refresh_run_through_the_settle_functions(staged, handovers, monkeypatch):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    w = staged
    inquiry = raised(w)
    row = row_for(w.db, inquiry, w.product_a)
    _link(w, row, w.product_a, w.loc_a, 10)
    inquiry = _pending_revision(w, qty="6")
    trims = _spy(monkeypatch, ProjectOrderInquiryService, "_trim_links")
    refreshes = _spy(monkeypatch, ProjectOrderInquiryService, "refresh_link_state")
    approve(w, inquiry, w.stage1.tier1)
    assert any(str(args[1].id) == str(row.id) for args, _kw in trims), "_trim_links on the row"
    assert any(
        str(row.id) in {str(r.id) for r in args[1]} for args, _kw in refreshes
    ), "refresh_link_state on the row"


# =============================================================================
# F2 - kill gaps on the approval path
# =============================================================================


def test_F2a_a_revision_approval_with_nothing_moved_marks_no_email_trigger(staged, monkeypatch):
    """Nothing moved: the requester changed a qty and changed it back before submit is
    refused (422), so the case is a decider moving it back while pending."""
    from app.services import project_order_inquiry_service as poi

    w = staged
    inquiry = _pending_revision(w, qty="12")
    _change(w, inquiry, w.product_a, "10", actor=w.stage1.tier1)
    marks = _spy(monkeypatch, poi, "mark_purchasing_email_trigger")
    approve(w, reload(w.db, inquiry), w.stage1.tier1)
    assert marks == [], "nothing moved, nothing marked"


def test_F2a_a_revision_approval_that_moved_a_row_marks_the_trigger(staged, monkeypatch):
    """The control for F2a: the spy sees the call when a row moved."""
    from app.services import project_order_inquiry_service as poi

    w = staged
    inquiry = _pending_revision(w, qty="12")
    marks = _spy(monkeypatch, poi, "mark_purchasing_email_trigger")
    approve(w, inquiry, w.stage1.tier1)
    assert len(marks) == 1


def test_F2b_a_row_revised_to_zero_goes_through_cancel_row_told(staged, handovers, monkeypatch):
    from app.models.audit import AuditLog
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    w = staged
    inquiry = _revise(w, raised(w))
    _change(w, inquiry, w.product_b, "0")
    inquiry = _submit(w, inquiry)
    row_b = row_for(w.db, inquiry, w.product_b)
    cancels = _spy(monkeypatch, ProjectOrderInquiryService, "cancel_row_told")
    handovers.clear()
    approve(w, inquiry, w.stage1.tier1)
    assert [str(args[1].id) for args, _kw in cancels] == [str(row_b.id)]
    row_b = row_for(w.db, inquiry, w.product_b)
    assert row_b.state == "cancelled"
    records = w.db.query(AuditLog).filter(
        AuditLog.event == "OI_ROW_CANCELLED", AuditLog.entity_id == str(row_b.id)
    ).all()
    assert records, "the cancel record (_record_cancel)"
    told = [h for h in handovers if h[0] == str(row_b.id)]
    assert [k for _r, k, _w in told] == ["cancelled"], told
    assert dec(told[0][2]["qty"]) == Decimal("4")


def test_F2c_restate_row_once_per_moved_row(staged, handovers, monkeypatch):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    w = staged
    inquiry = _revise(w, raised(w))
    _change(w, inquiry, w.product_a, "12")
    _change(w, inquiry, w.product_b, "5")
    inquiry = _submit(w, inquiry)
    row_a = row_for(w.db, inquiry, w.product_a)
    row_b = row_for(w.db, inquiry, w.product_b)
    restates = _spy(monkeypatch, ProjectOrderInquiryService, "restate_row")
    approve(w, inquiry, w.stage1.tier1)
    restated = sorted(str(args[1].id) for args, _kw in restates)
    assert restated == sorted([str(row_a.id), str(row_b.id)])


def test_F2c_an_unchanged_row_is_not_restated(staged, handovers, monkeypatch):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    w = staged
    inquiry = _pending_revision(w, qty="12")
    row_a = row_for(w.db, inquiry, w.product_a)
    restates = _spy(monkeypatch, ProjectOrderInquiryService, "restate_row")
    approve(w, inquiry, w.stage1.tier1)
    assert [str(args[1].id) for args, _kw in restates] == [str(row_a.id)]


# =============================================================================
# F3 - next_inquiry_no serialises on an advisory lock per company + prefix
# =============================================================================


def _advisory_locks(db) -> set:
    return {
        (r.classid, r.objid, r.objsubid)
        for r in db.execute(
            text(
                "SELECT classid, objid, objsubid FROM pg_locks "
                "WHERE locktype = 'advisory' AND pid = pg_backend_pid() AND granted"
            )
        )
    }


def test_F3_next_inquiry_no_takes_an_advisory_lock_per_company_and_prefix(world):
    from app.models.project_so import next_inquiry_no

    w = world
    before = _advisory_locks(w.db)
    next_inquiry_no(w.db, w.company_id, date(2026, 9, 15))
    sep = _advisory_locks(w.db) - before
    assert len(sep) == 1, f"one advisory lock for (company, OI-2609-), got {sep}"
    next_inquiry_no(w.db, w.company_id, date(2026, 9, 20))
    assert _advisory_locks(w.db) - before == sep, "the same month takes the same lock"
    next_inquiry_no(w.db, w.company_id, date(2026, 10, 1))
    assert len(_advisory_locks(w.db) - before) == 2, "another prefix is another lock"


def test_F3_the_lock_is_transaction_scoped(world):
    """A session-level advisory lock would survive the transaction; pg_try_advisory_xact_lock
    style locks do not. Checked by releasing every SESSION-level advisory lock: an
    xact-scoped one is still held afterwards."""
    from app.models.project_so import next_inquiry_no

    w = world
    before = _advisory_locks(w.db)
    next_inquiry_no(w.db, w.company_id, date(2026, 9, 15))
    taken = _advisory_locks(w.db) - before
    assert taken, "precondition: a lock was taken"
    w.db.execute(text("SELECT pg_advisory_unlock_all()"))
    assert taken <= _advisory_locks(w.db), "transaction-scoped: not released by unlock_all"


# =============================================================================
# F4 - OR detail totals during a revision
# =============================================================================


def test_F4_the_or_detail_totals_use_the_revised_qty(staged):
    w = staged
    inquiry = _revise(w, raised(w))  # a: 10 x 25.00, b: 4 x 12.50
    row = _change(w, inquiry, w.product_a, "12")
    res = w.as_user(w.requester).get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, res.text
    data = res.json()
    line_a = next(l for l in data["lines"] if l["id"] == str(row.id))
    assert dec(line_a["qty"]) == Decimal("12"), "precondition (U4.6)"
    assert dec(line_a["total"]) == Decimal("300"), "12 x 25.00"
    assert dec(data["total"]) == Decimal("350"), "300 + 4 x 12.50"


# =============================================================================
# F5 - no photo writes while a revision is open
# =============================================================================


@pytest.fixture
def photos(staged, monkeypatch):
    from app.models.resources import AttachmentType

    stub_storage(monkeypatch)
    staged.db.add(
        AttachmentType(
            id=uid(), type_name="Sales Order Line Attachment", code="so_line_attachment",
            allowed_extensions="jpg,jpeg,png,webp,gif,pdf,xlsx,xls", max_file_size_mb=10,
        )
    )
    staged.db.commit()
    return staged


def _upload(w, user_id, row_id):
    return w.as_user(user_id).post(
        f"{ROW_ATT}/{row_id}/attachments", files=[("files", ("seal.png", TINY_PNG, "image/png"))]
    )


def test_F5_can_write_photos_is_false_for_everyone_while_a_revision_is_open(photos):
    w = photos
    draft_rev = _revise(w, raised(w))
    pending_rev = _pending_revision(w)
    for inquiry in (draft_rev, pending_rev):
        for who in (w.requester, w.stage1.tier1, w.admin, w.buyer):
            assert not svc().can_write_photos(w.db, reload(w.db, inquiry), who), (
                inquiry.revision_state, who,
            )


def test_F5_a_decider_cannot_upload_a_photo_on_a_pending_revision(photos):
    w = photos
    inquiry = _pending_revision(w)
    row = row_for(w.db, inquiry, w.product_a)
    res = _upload(w, w.stage1.tier1, row.id)
    assert res.status_code in (403, 409), res.text


def test_F5_the_requester_cannot_upload_a_photo_on_a_draft_revision(photos):
    w = photos
    inquiry = _revise(w, raised(w))
    row = row_for(w.db, inquiry, w.product_a)
    res = _upload(w, w.requester, row.id)
    assert res.status_code in (403, 409), res.text


# =============================================================================
# F6 - OR list: effective state, filter, oi_no search
# =============================================================================


def _list(w, user_id, **params):
    res = w.as_user(user_id).get(SPR, params={"limit": 50, **params})
    assert res.status_code == 200, res.text
    return {r["id"]: r for r in res.json()["data"]}


def test_F6_the_pending_filter_includes_a_pending_revision(staged):
    w = staged
    revising = _pending_revision(w)
    plain_raised = raised(w)
    pending = submitted(w)
    rows = _list(w, w.requester, state=["pending_approval"])
    assert str(pending.id) in rows
    assert str(revising.id) in rows, "a revision waiting for approval is pending approval"
    assert str(plain_raised.id) not in rows


def test_F6_the_raised_filter_leaves_out_a_pending_revision(staged):
    w = staged
    revising = _pending_revision(w)
    plain_raised = raised(w)
    rows = _list(w, w.requester, state=["raised"])
    assert str(plain_raised.id) in rows
    assert str(revising.id) not in rows


def test_F6_list_rows_carry_the_effective_state(staged):
    w = staged
    revising = _pending_revision(w)
    plain_raised = raised(w)
    rows = _list(w, w.requester)
    assert rows[str(revising.id)].get("effective_state") == "pending_approval"
    assert rows[str(plain_raised.id)].get("effective_state") == "raised"


def test_F6_the_list_search_matches_oi_no(staged):
    w = staged
    done = raised(w)
    other = raised(w)
    number = reload(w.db, done).oi_no
    assert number, "precondition"
    rows = _list(w, w.requester, query=number)
    assert str(done.id) in rows
    assert str(other.id) not in rows


# =============================================================================
# F7 - security
# =============================================================================


def _drop_roles(w, user_id):
    from app.models.user import UserRoleAssignment

    w.db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id).delete()
    w.db.commit()


def test_F7_a_requester_without_the_create_slug_cannot_patch_a_revision_qty(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    row = row_for(w.db, inquiry, w.product_a)
    _drop_roles(w, w.requester)
    res = w.as_user(w.requester).patch(f"{SPR}/{inquiry.id}/lines/{row.id}", json={"qty": "12"})
    assert res.status_code == 403, res.text
    assert dec(row_for(w.db, inquiry, w.product_a).revised_qty) == Decimal("10")


def test_F7_the_requester_cannot_approve_their_own_pending_revision(staged):
    """The requester sits on stage 1's tier-2 team (support A2), so only "never the
    requester" stops this."""
    w = staged
    inquiry = _pending_revision(w)
    with pytest.raises(AppException) as excinfo:
        svc().approve(w.db, reload(w.db, inquiry), w.requester)
    assert excinfo.value.status_code == 403
    w.db.rollback()


def test_F7_the_requester_cannot_reject_their_own_pending_revision(staged):
    w = staged
    inquiry = _pending_revision(w)
    with pytest.raises(AppException) as excinfo:
        svc().reject(w.db, reload(w.db, inquiry), w.requester, "No")
    assert excinfo.value.status_code == 403
    w.db.rollback()


def test_F7_a_non_requester_cannot_edit_a_draft_revision(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    row = row_for(w.db, inquiry, w.product_a)
    for who in (w.outsider, w.stage1.tier1, w.buyer):
        with pytest.raises(AppException) as excinfo:
            svc().edit_line(w.db, reload(w.db, inquiry), row.id, who, qty="12")
        assert excinfo.value.status_code == 403, who
        w.db.rollback()


def test_F7_a_decider_not_on_the_stage_cannot_edit_a_pending_revision(staged):
    w = staged
    inquiry = _pending_revision(w)
    row = row_for(w.db, inquiry, w.product_a)
    for who in (w.outsider, w.buyer):
        with pytest.raises(AppException) as excinfo:
            svc().edit_line(w.db, reload(w.db, inquiry), row.id, who, qty="11")
        assert excinfo.value.status_code == 403, who
        w.db.rollback()


def test_F7_another_requests_row_id_is_404(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    other = raised(w)
    foreign = row_for(w.db, other, w.product_a)
    with pytest.raises(AppException) as excinfo:
        svc().edit_line(w.db, reload(w.db, inquiry), foreign.id, w.requester, qty="12")
    assert excinfo.value.status_code == 404
    w.db.rollback()
    assert reload(w.db, other).revision_state is None
    assert row_for(w.db, other, w.product_a).revised_qty is None


def test_F7_the_backfill_numbers_two_companies_independently(world):
    from app.models.base import set_company_scope
    from app.models.company import Company

    w = world
    other_id = str(uuid.uuid4())
    w.db.add(Company(id=other_id, name="ZZT Other Co", code=f"ZZC{other_id[:6]}"))
    w.db.flush()
    set_company_scope(w.db, frozenset({SORENTO, other_id}))
    p = "current_schema() || '_projects'"
    schema = w.db.execute(text(f"SELECT {p}")).scalar()
    ids = {}
    for key, company, raised_at, number in (
        ("a1", SORENTO, datetime(2026, 9, 2, 2), "OR-2609-0001"),
        ("b1", other_id, datetime(2026, 9, 3, 2), "OR-2609-0001"),
        ("a2", SORENTO, datetime(2026, 9, 4, 2), "OR-2609-0002"),
    ):
        ids[key] = str(uuid.uuid4())
        w.db.execute(
            text(
                f'INSERT INTO "{schema}".order_inquiries '
                "(id, company_id, inquiry_no, inquiry_type, state, raised_at) "
                "VALUES (:i, :c, :n, :t, 'raised', :r)"
            ),
            {"i": ids[key], "c": company, "n": number, "t": KIND, "r": raised_at},
        )
    w.db.flush()
    svc().backfill_oi_numbers(w.db)
    w.db.flush()
    got = {
        str(r.id): r.oi_no
        for r in w.db.execute(
            text(f'SELECT id, oi_no FROM "{schema}".order_inquiries WHERE id::text = ANY(:ids)'),
            {"ids": list(ids.values())},
        )
    }
    assert got[ids["a1"]] == "OI-2609-0001"
    assert got[ids["a2"]] == "OI-2609-0002"
    assert got[ids["b1"]] == "OI-2609-0001", "the other company has its own series"


# =============================================================================
# F8 - submit when purchasing cancelled every live row
# =============================================================================


def test_F8_submit_on_a_revision_with_every_row_cancelled_closes_it_quietly(staged, handovers):
    from app.models.audit import AuditLog

    w = staged
    inquiry = _revise(w, raised(w))
    for product in (w.product_a, w.product_b):
        _oi(w).cancel_row_told(
            row_for(w.db, inquiry, product), cause="zzt_purchasing_cancel", stamp="Cancelled",
            actor_user_id=w.buyer,
        )
    w.db.commit()
    assert all(r.state == "cancelled" for r in rows_of(w.db, inquiry)), "precondition"
    audits_before = w.db.query(AuditLog).filter(
        AuditLog.entity_type == "project_order_inquiries", AuditLog.entity_id == str(inquiry.id)
    ).count()
    handovers.clear()
    w.sent.clear()

    res = w.as_user(w.requester).post(f"{SPR}/{inquiry.id}/submit")
    assert res.status_code == 200, res.text
    inquiry = reload(w.db, inquiry)
    assert inquiry.revision_state is None, "the revision is closed"
    audits_after = w.db.query(AuditLog).filter(
        AuditLog.entity_type == "project_order_inquiries", AuditLog.entity_id == str(inquiry.id)
    ).count()
    assert audits_after > audits_before, "a History entry is written"
    assert handovers == [], "no email item"
    assert w.sent == [], "no notification"
