"""Reconstructed undo of a journal-less revision (`PLAN-scm-oi-handover-r2-undo.md` S5).

RED for Phase 2: `app.services.project_supply_undo_reconstruct_service` does not exist
yet, so `from ... import reconstruct_undo` raises `ModuleNotFoundError` on every test in
this file - that is the "right reason" until the coder writes the module. Each test's
import sits FIRST, before any fixture building, so the failure is immediate and uniform
rather than a partial fixture running into an AttributeError deeper in.

Every decision (`P`, the prior/reinstated one, and `D`, the journal-less one being
reconstructed) is built BY HAND rather than through a real Confirm: `reconstruct_undo`
reads only `order_inquiry_rows.supply_decision_id` / `previous_qty` /
`previous_delivery_date` / notes / state, plus `so_line_allocations.decision_id` and
`stock_transfers.supply_decision_id`, per the plan's own step list (S5, AC-R2-31 a-h) -
none of it depends on a real journal (D has none by definition), so a hand-built pair of
decisions plus the touched rows is what a genuinely journal-less pre-lane revision
actually looks like on prod, not a shortcut.

Postgres only, via `tests/_pg_fixture.py::blank_session` (through the `api` fixture
imported from `tests/test_so_supply_confirmation.py`, the same harness
`test_board_undo_last_confirm.py` uses). Every row is seeded behind the `ZZT` marker;
nothing is borrowed from an existing table.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.project_so import (
    ALLOC_SOURCE_ORDER,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    SOLineAllocation,
    SOSupplyDecision,
    SOSupplyDecisionDraft,
)
from app.models.scm import OrderLinkClaim
from app.models.stock_transfer import (
    TRANSFER_CANCELLED,
    TRANSFER_KIND_OWN_GROUP,
    TRANSFER_PROPOSED,
    StockTransfer,
)
from app.services.error_handler import AppException

from .test_so_supply_confirmation import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    _suffix,
    _uid,
    api,
)

MARKER = "zzt-undo-reconstructed"


def _po_line(db, world, *, qty):
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_suffix()}",
        issue_date=datetime.utcnow().date(), status="active",
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal(str(qty)), qty_received=Decimal("0"),
        expected_date=datetime.utcnow().date(), line_status="open",
    )
    db.add(line)
    db.flush()
    return po, line


def _reconstruct_world(api, *, buyer=None):
    """One order, one line, decision `P` (superseded, journalled or not - irrelevant to
    reconstruct) and decision `D` (ACTIVE, journal-less, `supersedes_id = P.id`), plus
    one row for each of the letters AC-R2-31 a-h names. `T0` is P's own confirm,
    `T1` D's - both well in the past so "after P.confirmed_at" / "within 60s of
    D.confirmed_at" are unambiguous.
    """
    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="100")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    t0 = datetime.utcnow() - timedelta(hours=2)
    t1 = datetime.utcnow() - timedelta(hours=1)

    inquiry = OrderInquiry(
        company_id=world.company_id, project_sales_order_id=order.id,
        state=INQUIRY_RAISED, raised_by=world.eling,
    )
    db.add(inquiry)
    db.flush()

    p = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="superseded",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=t0,
        superseded_at=t1, superseded_reason="Superseded by revision 2",
    )
    d = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=2, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=t1, supersedes_id=p.id,
        undo_journal=None,
    )
    db.add_all([p, d])
    db.flush()

    # (a) raised by D after P: a fresh row, no purchasing action on it, one CASCADE
    # (auto) link D's own raise placed - deleting it must free its claim.
    row_a = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("30"), verb=IV_ORDER,
        state=INQUIRY_RAISED, supply_decision_id=d.id,
        created_at=t1 + timedelta(seconds=5),
    )
    db.add(row_a)
    db.flush()
    po_a, po_line_a = _po_line(db, world, qty=30)
    claim_a = OrderLinkClaim(
        id=_uid(), company_id=world.company_id, so_number=f"ZZT-{_suffix()}",
        po_number=po_a.po_number, item_code=world.product.product_code,
        source="order_inquiry", po_line_id=po_line_a.id,
    )
    db.add(claim_a)
    db.flush()
    link_a = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row_a.id, po_line_id=po_line_a.id,
        document=po_a.po_number, qty=Decimal("30"), linked_by=buyer or world.eling,
        auto=True, linked_at=t1 + timedelta(seconds=10), claim_id=claim_a.id,
    )
    db.add(link_a)

    # (b) settled by D: predates D (created under P), D repointed + restated it within
    # the 60s settle window.
    row_b = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("20"), verb=IV_ORDER,
        state=INQUIRY_RAISED, supply_decision_id=d.id,
        created_at=t0 + timedelta(seconds=5),
        previous_qty=Decimal("25"), previous_delivery_date=None,
        changed_at=t1 + timedelta(seconds=3),
        note="Was 25 NOS",
    )
    db.add(row_b)

    # (c) cancelled BY D (D's own supersede of an old row it replaced).
    row_c = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("15"), verb=IV_ORDER,
        state=INQUIRY_CANCELLED, supply_decision_id=None,
        note=f"Superseded by revision {d.revision_no}",
    )
    db.add(row_c)

    # (d) released by D (redirected to pool, D's own placement redirect).
    row_d = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("10"), verb=IV_ORDER,
        state=INQUIRY_RAISED, supply_decision_id=None, redirected_to_pool=True,
        note=f"released at revision {d.revision_no}",
    )
    db.add(row_d)
    db.flush()

    # (e) SOLineAllocation + StockTransfer under D.
    alloc = SOLineAllocation(
        id=_uid(), company_id=world.company_id, so_line_id=line.id,
        source_type=ALLOC_SOURCE_ORDER, qty=Decimal("30"), decision_id=d.id,
    )
    db.add(alloc)
    proposed_transfer = StockTransfer(
        id=_uid(), company_id=world.company_id, transfer_no=f"ZZT-TR-{_suffix()}",
        # `stock_transfers.so_line_id` FKs the CORE `sales_order_lines` row, not the
        # project mirror - `core_line.id`, never `line.id`.
        so_line_id=core_line.id, project_sales_order_id=order.id, supply_decision_id=d.id,
        product_id=world.product.id, from_warehouse_id=world.pool_wh.id,
        to_warehouse_id=world.own_wh.id, qty=Decimal("5"),
        kind=TRANSFER_KIND_OWN_GROUP, state=TRANSFER_PROPOSED,
    )
    db.add(proposed_transfer)
    cancelled_transfer = StockTransfer(
        id=_uid(), company_id=world.company_id, transfer_no=f"ZZT-TR-{_suffix()}",
        so_line_id=core_line.id, project_sales_order_id=order.id, supply_decision_id=None,
        product_id=world.product.id, from_warehouse_id=world.pool_wh.id,
        to_warehouse_id=world.own_wh.id, qty=Decimal("8"),
        kind=TRANSFER_KIND_OWN_GROUP, state=TRANSFER_CANCELLED,
        cancelled_reason=f"Superseded by revision {d.revision_no}",
    )
    db.add(cancelled_transfer)
    db.commit()

    return {
        "client": client, "world": world, "db": db, "order": order, "core_so": core_so,
        "line": line, "decision_p": p, "decision_d": d, "inquiry": inquiry,
        "row_a": row_a, "row_b": row_b, "row_c": row_c, "row_d": row_d,
        "link_a": link_a, "claim_a": claim_a,
        "allocation": alloc, "proposed_transfer": proposed_transfer,
        "cancelled_transfer": cancelled_transfer,
    }


# --------------------------------------------------------------------------- #
# AC-R2-31: reconstruct_undo, one test per letter (a-h)                       #
# --------------------------------------------------------------------------- #


def test_reconstruct_undo_step_a_deletes_rows_raised_after_p(api):
    """(a) every row D raised (created after P's confirm) is deleted with its links;
    the link's claim is freed with it."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]

    reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()

    assert db.query(OrderInquiryRow).filter(OrderInquiryRow.id == fx["row_a"].id).first() is None
    assert (
        db.query(OrderInquiryLink).filter(OrderInquiryLink.id == fx["link_a"].id).first()
        is None
    )
    assert (
        db.query(OrderLinkClaim).filter(OrderLinkClaim.id == fx["claim_a"].id).first() is None
    ), "the freed claim must be deleted, not left orphaned"


def test_reconstruct_undo_step_b_restores_settled_row_and_repoints_to_p(api):
    """(b) a row D settled in place (changed_at within 60s of D's confirm) has its qty
    and delivery date restored from `previous_qty`/`previous_delivery_date`, those two
    columns cleared, a note appended, and `supply_decision_id` repointed to P."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]

    reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()

    db.expire_all()
    row_b = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == fx["row_b"].id).one()
    assert row_b.qty == Decimal("25"), "qty must be restored from previous_qty"
    assert row_b.previous_qty is None
    assert row_b.previous_delivery_date is None
    assert row_b.supply_decision_id == fx["decision_p"].id
    assert "reconstructed" in (row_b.note or "").lower()


def test_reconstruct_undo_step_c_reinstates_cancelled_rows(api):
    """(c) a row D cancelled (note "Superseded by revision N", N = D's own) is set back
    to `raised`, note appended."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]

    reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()

    db.expire_all()
    row_c = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == fx["row_c"].id).one()
    assert row_c.state == INQUIRY_RAISED
    assert "reinstated" in (row_c.note or "").lower()


def test_reconstruct_undo_step_d_flags_redirected_rows_back(api):
    """(d) a row D released (`redirected_to_pool = True`, note "released at revision N")
    has the flag set back to False."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]

    reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()

    db.expire_all()
    row_d = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == fx["row_d"].id).one()
    assert row_d.redirected_to_pool is False


def test_reconstruct_undo_step_e_cleans_up_allocations_and_transfers(api):
    """(e) `so_line_allocations` under D are deleted; `stock_transfers` under D still
    `proposed` are deleted; those `cancelled` with D's own supersede reason return to
    `proposed` under P."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]

    reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()

    assert (
        db.query(SOLineAllocation).filter(SOLineAllocation.id == fx["allocation"].id).first()
        is None
    )
    assert (
        db.query(StockTransfer)
        .filter(StockTransfer.id == fx["proposed_transfer"].id)
        .first()
        is None
    )
    db.expire_all()
    restored = (
        db.query(StockTransfer).filter(StockTransfer.id == fx["cancelled_transfer"].id).one()
    )
    assert restored.state == TRANSFER_PROPOSED
    assert restored.supply_decision_id == fx["decision_p"].id


def test_reconstruct_undo_step_f_deletes_d_and_reactivates_p(api):
    """(f) D is deleted with an audit delete row (same as the journal undo writes); P
    becomes `active` with `superseded_at`/`superseded_reason` NULL."""
    from app.models.audit import AuditLog
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]
    d_id = fx["decision_d"].id

    reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()

    assert db.query(SOSupplyDecision).filter(SOSupplyDecision.id == d_id).first() is None
    audit_row = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == str(d_id), AuditLog.action == "DELETE")
        .first()
    )
    assert audit_row is not None, "the reconstructed undo must write the same audit DELETE"

    db.expire_all()
    p = db.query(SOSupplyDecision).filter(SOSupplyDecision.id == fx["decision_p"].id).one()
    assert p.state == "active"
    assert p.superseded_at is None
    assert p.superseded_reason is None


def test_reconstruct_undo_step_g_writes_no_draft(api):
    """(g) nothing is restored to draft - a reconstructed undo never writes
    `SOSupplyDecisionDraft` rows."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]
    order = fx["order"]
    # `SOSupplyDecisionDraft` keys on the CORE sales order (`sales_order_id`) plus
    # `core_line_id` (review round, captain's diagnosis) - it has no
    # `project_sales_order_id` column at all, so the original query raised
    # `AttributeError` before ever reaching the reconstruct call.
    core_so_id = fx["core_so"].id

    before = (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == core_so_id)
        .count()
    )
    assert before == 0, "setup: no draft should exist before the reconstruct"

    reconstruct_undo(db, order, fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()

    after = (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == core_so_id)
        .count()
    )
    assert after == 0


def test_reconstruct_undo_step_h_sends_reconstructed_headline_email(api, monkeypatch):
    """(h) an `order_inquiry_undone` email is sent with headline `RECONSTRUCTED` and one
    line per row removed or restored."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]

    calls: list[dict] = []

    def _fake_dispatch(self, trigger_type, *, context, source_kind, source_id):
        calls.append({"trigger_type": trigger_type, "context": context})
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event", _fake_dispatch
    )
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()

    reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()

    matches = [c for c in calls if c["trigger_type"] == "order_inquiry_undone"]
    assert matches, "the reconstructed undo must dispatch the undone-order email"
    undo_ctx = matches[-1]["context"].get("undo") or {}
    assert undo_ctx.get("headline") == "RECONSTRUCTED", (
        f"AC-R2-31h: expected headline RECONSTRUCTED, got {undo_ctx}"
    )
    assert undo_ctx.get("lines"), "one line per row removed or restored"


# --------------------------------------------------------------------------- #
# AC-R2-32: linked/actioned refusals still apply to a reconstructed undo      #
# --------------------------------------------------------------------------- #


def test_reconstruct_refuses_linked_and_actioned(api):
    """AC-R2-32: a row of D with a manual link written after D's confirm, or a row in
    state `actioned` after D's confirm, refuses the reconstruct with the SAME
    `linked`/`actioned` predicate the journal undo already uses - nothing is touched."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]
    world = fx["world"]

    # A manual (non-auto) link on row_a, written AFTER D's confirm.
    po, po_line = _po_line(db, world, qty=10)
    db.add(
        OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=fx["row_a"].id,
            po_line_id=po_line.id, document=po.po_number, qty=Decimal("10"),
            linked_by=world.eling, auto=False,
            linked_at=fx["decision_d"].confirmed_at + timedelta(minutes=1),
        )
    )
    db.commit()

    with pytest.raises(AppException) as exc_info:
        reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=world.eling)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "linked"

    db.expire_all()
    d_still_there = (
        db.query(SOSupplyDecision).filter(SOSupplyDecision.id == fx["decision_d"].id).first()
    )
    assert d_still_there is not None, "a refused reconstruct must change nothing"


# --------------------------------------------------------------------------- #
# AC-R2-34/35: the action key, payload/journal-state agreement, admin gate    #
# --------------------------------------------------------------------------- #


def test_mode_mismatch_409(api):
    """AC-R2-34: the server refuses (409) a `mode` that does not match the decision's
    own journal state - `mode="journal"` on a journal-less decision, or
    `mode="reconstructed"` on a journalled one."""
    fx = _reconstruct_world(api)
    client = fx["client"]
    order = fx["order"]
    decision_d = fx["decision_d"]

    response = client.post(
        "/api/v1/pending-actions",
        json={
            "action_key": "project_sales_order.undo_confirm",
            "entity_type": "project_sales_order",
            "entity_id": str(order.id),
            "payload": {"decision_id": str(decision_d.id), "mode": "journal"},
        },
    )
    assert response.status_code == 409, response.text


def test_non_admin_reconstructed_403(api):
    """AC-R2-35: a user without the admin role who parks a reconstructed undo by
    hand-crafting the payload gets 403, even though the decision itself is genuinely
    journal-less."""
    fx = _reconstruct_world(api)
    client = fx["client"]
    order = fx["order"]
    decision_d = fx["decision_d"]

    response = client.post(
        "/api/v1/pending-actions",
        json={
            "action_key": "project_sales_order.undo_confirm",
            "entity_type": "project_sales_order",
            "entity_id": str(order.id),
            "payload": {"decision_id": str(decision_d.id), "mode": "reconstructed"},
        },
    )
    assert response.status_code == 403, response.text


# --------------------------------------------------------------------------- #
# AC-R2-30: visible to admin/superadmin only (service-level, complementing    #
# `test_board_undo_last_confirm.py::test_journalless_decision_refuses_non_    #
# admin_offers_reconstructed_to_admin`'s API-level pin)                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role_slugs", [{"user"}, {"purchasing"}])
def test_reconstructed_visible_to_admin_only(api, role_slugs):
    """AC-R2-30: `board_undo_map` (or whichever seam threads the requester's role)
    must admit a journal-less decision's `undo` ONLY for `admin`/`superadmin` - every
    other role slug set gets `undo: None` for that order, same as no active decision."""
    from app.services.project_supply_undo_service import board_undo_map
    from app.services.user_service import UserPermissionService

    fx = _reconstruct_world(api)
    db = fx["db"]
    order = fx["order"]

    original = UserPermissionService.get_user_role_slugs
    UserPermissionService.get_user_role_slugs = lambda self, uid: role_slugs
    try:
        undo_map = board_undo_map(
            db, {order.so_id: order.id}, actor_user_id=fx["world"].eling
        )
    finally:
        UserPermissionService.get_user_role_slugs = original

    assert undo_map.get(order.so_id) is None, (
        f"AC-R2-30: role {role_slugs!r} must not see a reconstructed undo entry"
    )


# --------------------------------------------------------------------------- #
# AC-R2-33: two journal-less revisions reconstructed in turn, then a fresh    #
# Confirm - the SRTWCX8605-S-RL-PJ shape from the plan's own numbers (182 to  #
# 214, "ORDER 32"), scoped to ONE order rather than the full SO314593/        #
# SO314594 pair per the tester's own time budget - AC-R2-16 and the eight     #
# lettered tests above already exercise the amendment-row and per-step shape #
# this scenario would otherwise repeat.                                      #
# --------------------------------------------------------------------------- #


def test_so314594_and_so314593_reconstructed_twice_then_one_confirm_one_email(
    api, monkeypatch
):
    """Two journal-less decisions deep (rev0 -> rev1 -> rev2, both rev1 and rev2
    journal-less), reconstructing twice must return the order to rev0's own numbers -
    the qty this lane's own SRTWCX8605-S-RL-PJ example moved (182), so a subsequent
    real Confirm that settles it to 214 prints exactly ONE line, `182 | 214 | ORDER
    32`, never a cancel+order pair."""
    from app.services.project_order_inquiry_service import (
        ProjectOrderInquiryService,
        register_order_inquiry_post_commit_dispatch,
    )
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    client, world = api
    _register = register_order_inquiry_post_commit_dispatch
    _register()
    db = world.db

    calls: list[dict] = []

    def _fake_dispatch(self, trigger_type, *, context, source_kind, source_id):
        calls.append({"trigger_type": trigger_type, "context": context})
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event", _fake_dispatch
    )

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="182"
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    inquiry = OrderInquiry(
        company_id=world.company_id, project_sales_order_id=order.id,
        state=INQUIRY_RAISED, raised_by=world.eling,
    )
    db.add(inquiry)
    db.flush()

    t0 = datetime.utcnow() - timedelta(hours=3)
    t1 = datetime.utcnow() - timedelta(hours=2)
    t2 = datetime.utcnow() - timedelta(hours=1)

    rev0 = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="superseded",
        line_snapshots=[{"line_no": 1, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=t0,
        superseded_at=t1, superseded_reason="Superseded by revision 2",
    )
    rev1 = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=2, state="superseded",
        line_snapshots=[{"line_no": 1, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=t1, supersedes_id=rev0.id,
        undo_journal=None, superseded_at=t2, superseded_reason="Superseded by revision 3",
    )
    rev2 = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=3, state="active",
        line_snapshots=[{"line_no": 1, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=t2, supersedes_id=rev1.id,
        undo_journal=None,
    )
    db.add_all([rev0, rev1, rev2])
    db.flush()

    row = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("182"), verb=IV_ORDER,
        # Same delivery date the line itself carries (review round, captain's
        # diagnosis): `_project_line` stamps `line.delivery_date = core_line.
        # required_date`, so an unset `row.delivery_date` reads as a genuine move
        # (None -> the required date) once the final Confirm settles this row in
        # place, and `was` honestly grows a `delivery_date` key nothing in this
        # scenario is supposed to change. Matching it keeps only qty moving.
        delivery_date=core_line.required_date,
        state=INQUIRY_RAISED, supply_decision_id=rev2.id,
        created_at=t0 + timedelta(seconds=5),
    )
    db.add(row)
    db.commit()

    # Reconstruct rev2, then rev1 - back to rev0's own state.
    reconstruct_undo(db, order, rev2, actor_user_id=world.eling)
    db.commit()
    db.expire_all()

    active = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == "active",
        )
        .one()
    )
    assert active.id == rev1.id, "the first reconstruct must reinstate rev1"

    reconstruct_undo(db, order, rev1, actor_user_id=world.eling)
    db.commit()
    db.expire_all()

    active = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == "active",
        )
        .one()
    )
    assert active.id == rev0.id, "the second reconstruct must reinstate rev0"

    row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert row.qty == Decimal("182"), "the row must be back at rev0's own qty, 182"

    calls.clear()

    # A fresh Confirm settles the SAME line to 214 - the plan's own SRTWCX8605-S-RL-PJ
    # move.
    core_line.qty_ordered = Decimal("214")
    line.qty = Decimal("214")
    db.flush()
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [{"project_line_id": str(line.id), "buy_qty": "214"}]},
    )
    assert response.status_code == 200, response.text
    db.commit()

    matches = [c for c in calls if c["trigger_type"] == "order_inquiry_handover"]
    assert matches, "the confirm must dispatch exactly one handover email"
    handover_dispatches = [
        c for c in calls if c["trigger_type"] == "order_inquiry_handover"
    ]
    assert len(handover_dispatches) == 1, (
        f"exactly one handover email must be queued, got {len(handover_dispatches)}"
    )
    lines = matches[-1]["context"]["handover"]["lines"]
    assert len(lines) == 1, (
        f"no cancel+order pair - exactly one settled line, got {lines}"
    )
    assert lines[0]["was"] == {"qty": "182"}
    assert lines[0]["qty"] == "214"
    assert lines[0]["remark"] == "ORDER 32"
