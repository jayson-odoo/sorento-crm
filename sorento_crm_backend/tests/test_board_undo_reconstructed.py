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
from types import SimpleNamespace

import pytest

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.project_so import (
    ACK_AWAITING,
    ALLOC_SOURCE_ORDER,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
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

from .test_board_undo_email import _load_undone_headline_migration
from .test_so_supply_confirmation import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    _suffix,
    _uid,
    _user,
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


def _undone_template_stand_in():
    """The `oihr_0002_undone_headline` migration's OWN post-migration subject/body
    constants, read straight off the loaded module rather than applied to the DB
    (CI xdist fix, `--dist loadfile`): a different worker running `test_board_undo_
    email.py` at the same wall-clock moment writes the SAME `email_templates` row
    (`code='order_inquiry_undone_default'`), so this test must never touch it -
    that migration's own idempotency/downgrade contract is pinned once, in
    `test_board_undo_email.py`, next to the seed migration it extends. A
    `SimpleNamespace` stands in for the `EmailTemplate` row: `EmailTemplateService.
    render` only ever reads `.subject` / `.body_html` / `.body_text` off whatever it
    is given."""
    module = _load_undone_headline_migration()
    return SimpleNamespace(
        subject=module._SUBJECT,
        body_html=module._BODY_HTML,
        body_text=module._BODY_TEXT,
    )


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

    # B3 (review round 1): the dispatched CONTEXT carrying `headline` is not enough -
    # the migration's own body must actually print the RECONSTRUCTED word somewhere,
    # not silently drop it. Rendered from the migration module's own constants (no
    # DB write - see `_undone_template_stand_in`'s own docstring for why).
    from app.services.email_template_service import EmailTemplateService

    rendered = EmailTemplateService(db).render(
        _undone_template_stand_in(), matches[-1]["context"]
    )
    rendered_text = (
        (rendered.get("subject") or "")
        + (rendered.get("body_html") or "")
        + (rendered.get("body_text") or "")
    )
    assert "RECONSTRUCTED" in rendered_text, (
        "B3: the RECONSTRUCTED headline must actually render somewhere in the "
        "migration's own template, not just sit in the dispatched context"
    )


def test_journal_undo_renders_without_the_reconstructed_word(api, monkeypatch):
    """B3 (review round 1): a JOURNAL undo's own email (headline the plain default,
    not RECONSTRUCTED) must never print the word - the template's own headline
    branch must be genuinely conditional, not a static insertion."""
    from app.services.email_template_service import EmailTemplateService
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )
    from app.services.project_supply_undo_service import undo_last_confirm

    calls: list[dict] = []

    def _fake_dispatch(self, trigger_type, *, context, source_kind, source_id):
        calls.append({"trigger_type": trigger_type, "context": context})
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event", _fake_dispatch
    )
    register_order_inquiry_post_commit_dispatch()

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    confirm = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [{"project_line_id": str(line.id), "buy_qty": "20"}]},
    )
    assert confirm.status_code == 200, confirm.text

    undo_last_confirm(db, order, actor_user_id=world.eling)
    db.commit()

    matches = [c for c in calls if c["trigger_type"] == "order_inquiry_undone"]
    assert matches, "the journal undo must dispatch its own undone-order email"
    undo_ctx = matches[-1]["context"].get("undo") or {}
    assert undo_ctx.get("headline") != "RECONSTRUCTED"

    # Rendered against the migration's own POST-migration constants (headline
    # branch present) - or this render is only ever against a word-free body and
    # proves nothing about the branch's own conditional. No DB write - see
    # `_undone_template_stand_in`'s own docstring.
    rendered = EmailTemplateService(db).render(
        _undone_template_stand_in(), matches[-1]["context"]
    )
    rendered_text = (
        (rendered.get("subject") or "")
        + (rendered.get("body_html") or "")
        + (rendered.get("body_text") or "")
    )
    assert "RECONSTRUCTED" not in rendered_text, (
        "B3: a journal undo must never print the word RECONSTRUCTED"
    )


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


def test_reconstruct_refuses_an_auto_link_landing_well_after_the_confirm(api):
    """B1 (review round 1): `auto=True` is not a blanket exemption - today's
    `reconstruct_refusal` only ever refuses a NON-auto link (`if not auto and ...`),
    so an AutoCount pairing that runs LATER, well after D's own confirm, is never
    caught even though it is exactly the same "purchasing acted on this since"
    situation a manual link already refuses. A link auto-placed more than the
    settle window (60s) after D's own confirm must refuse the reconstruct just like
    a manual one, and nothing is deleted."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]
    world = fx["world"]

    po, po_line = _po_line(db, world, qty=5)
    db.add(
        OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=fx["row_a"].id,
            po_line_id=po_line.id, document=po.po_number, qty=Decimal("5"),
            linked_by=world.eling, auto=True,
            linked_at=fx["decision_d"].confirmed_at + timedelta(seconds=61),
        )
    )
    db.commit()

    with pytest.raises(AppException) as exc_info:
        reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=world.eling)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "linked", (
        "B1: an auto link landing well after D's own confirm is not the confirm's "
        "own cascade and must refuse just like a manual one"
    )

    db.expire_all()
    row_a_still_there = (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.id == fx["row_a"].id).first()
    )
    assert row_a_still_there is not None, "a refused reconstruct must delete nothing"


def test_reconstruct_does_not_refuse_an_auto_link_inside_the_confirm_window(api):
    """B1 boundary pair (review round 1): an `auto=True` link landing INSIDE D's own
    confirm window (+/- 60s) is the confirm's own cascade and must not refuse - the
    guard, alongside the test above."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]
    world = fx["world"]

    po, po_line = _po_line(db, world, qty=5)
    db.add(
        OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=fx["row_a"].id,
            po_line_id=po_line.id, document=po.po_number, qty=Decimal("5"),
            linked_by=world.eling, auto=True,
            linked_at=fx["decision_d"].confirmed_at + timedelta(seconds=45),
        )
    )
    db.commit()

    result = reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=world.eling)
    assert result["revision_no"] == fx["decision_d"].revision_no


def test_reconstructed_execute_rechecks_role_after_a_demotion(api, monkeypatch):
    """B2 (review round 1): the reconstructed path's own EXECUTE step must re-check
    the actor's role, not trust the park-time gate alone - `record_actions._undo_
    confirm`'s `mode == "reconstructed"` branch today never reads the actor's role at
    all, only `app.api.v1.system.pending_actions._assert_undo_not_refused` does, at
    PARK time. A role demoted between park and the countdown lapsing (or a caller
    that reaches execute directly) must still be refused 403, and nothing written."""
    from app.services.form_action_registry import get_action
    from app.services.user_service import UserPermissionService

    fx = _reconstruct_world(api)
    db = fx["db"]
    order = fx["order"]
    decision_d = fx["decision_d"]

    monkeypatch.setattr(
        UserPermissionService, "get_user_role_slugs", lambda self, uid: {"user"}
    )

    action = get_action("project_sales_order.undo_confirm")
    assert action is not None

    with pytest.raises(AppException) as exc_info:
        action.execute(
            db,
            {
                "entity_id": str(order.id), "decision_id": str(decision_d.id),
                "mode": "reconstructed", "requested_by_id": fx["world"].eling,
            },
        )
    assert exc_info.value.status_code == 403, (
        "B2: execute must re-check the actor's role, not trust park alone"
    )

    db.expire_all()
    d_still_there = (
        db.query(SOSupplyDecision).filter(SOSupplyDecision.id == decision_d.id).first()
    )
    assert d_still_there is not None, "a refused execute must write nothing"


def test_reconstructed_execute_refuses_without_project_rights(api, monkeypatch):
    """B2 (review round 1, mirrors `test_undo_requires_the_confirmers_project_
    rights` in `test_board_undo_last_confirm.py`): an admin who is neither the
    project's owner nor an approved collaborator must be refused at EXECUTE time on
    the reconstructed path too, exactly like the journalled path already is. Today
    `reconstruct_undo` runs no project-rights check at all - only `reconstruct_
    refusal`'s linked/actioned predicate."""
    from app.services.form_action_registry import get_action
    from app.services.project_service import assert_can_edit_project, get_project_or_404
    from app.services.user_service import UserPermissionService

    fx = _reconstruct_world(api)
    db = fx["db"]
    world = fx["world"]
    order = fx["order"]
    decision_d = fx["decision_d"]

    outsider = _user(db, f"{MARKER} Outsider")
    db.commit()

    # Sanity: Confirm's OWN check would refuse this exact user too - same project, no
    # ownership, no collaboration.
    project = get_project_or_404(db, world.project.id)
    with pytest.raises(AppException) as confirm_exc:
        assert_can_edit_project(db, project, outsider, {"projects.projects.edit"})
    assert confirm_exc.value.status_code == 403

    monkeypatch.setattr(
        UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"}
    )

    action = get_action("project_sales_order.undo_confirm")
    with pytest.raises(AppException) as exc_info:
        action.execute(
            db,
            {
                "entity_id": str(order.id), "decision_id": str(decision_d.id),
                "mode": "reconstructed", "requested_by_id": outsider,
            },
        )
    assert exc_info.value.status_code in (403, 404), (
        "B2: the reconstructed path must re-run Confirm's own per-project "
        "authorisation at execute time"
    )

    db.expire_all()
    d_still_there = (
        db.query(SOSupplyDecision).filter(SOSupplyDecision.id == decision_d.id).first()
    )
    assert d_still_there is not None, "a refused execute must write nothing"


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


# =============================================================================== #
# Review round 1 - S2 ack-awaiting restore, S3 donor rows, S6 no-prior           #
# decision, and three nits.                                                       #
# =============================================================================== #


def test_reconstruct_undo_step_b_restores_awaiting_row_with_no_changed_at(api):
    """S2 (review round 1): a row D settled in place while still `ACK_AWAITING`
    never gets `changed_at` stamped (`_settle_row_in_place`'s own rule: "a row still
    AWAITING is left alone and says nothing"), even though `previous_qty` IS written
    unconditionally on a real change. Reconstruct's own settle-window check reads
    `changed_at` alone (`if row.changed_at and ...`), so this row's `previous_qty`
    is silently never restored today - the ack_state, not a timestamp nobody wrote,
    is what a row outside the window should be judged by."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]
    world = fx["world"]

    awaiting_row = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=fx["inquiry"].id,
        so_line_id=fx["line"].id, item_code=world.product.product_code,
        qty=Decimal("40"), verb=IV_ORDER, state=INQUIRY_RAISED,
        supply_decision_id=fx["decision_d"].id,
        created_at=fx["decision_p"].confirmed_at + timedelta(seconds=5),
        previous_qty=Decimal("55"), previous_delivery_date=None,
        changed_at=None, ack_state=ACK_AWAITING,
    )
    db.add(awaiting_row)
    db.commit()

    reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=world.eling)
    db.commit()

    db.expire_all()
    row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == awaiting_row.id).one()
    assert row.qty == Decimal("55"), (
        "S2: a row settled while still AWAITING has no changed_at stamp, but its "
        "own previous_qty must still be restored"
    )
    assert row.previous_qty is None


def test_reconstruct_restores_the_donor_orders_own_rows_too(api):
    """S3 (review round 1): a borrow's donor re-issue is a SEPARATE decision on the
    DONOR's own order (`test_a_borrow_from_a_donor_journals_the_donor_re_issue`,
    `test_board_undo_journal.py`, adapted here to journal-less) - the journalled path
    catches it because it all lands in the BORROWER's own journal. Reconstruct has
    no journal, and today's `reconstruct_undo` only ever touches rows whose `supply_
    decision_id` is the decision it was CALLED with; it never discovers the donor's
    own re-issued decision at all, so reconstructing the borrower's confirm leaves
    the donor's side (a row cancelled "Superseded by revision N", a fresh row raised
    by that same re-issue) untouched."""
    from app.services.project_service import register_project
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    client, world = api
    db = world.db

    donor_project = register_project(
        db, company_id=world.company_id, actor_user_id=world.eling, developer_party_id=None,
        title=f"{MARKER} Donor Heights",
    )
    donor_core_so = _core_so(db, world.company_id)
    donor_core_line = _core_line(
        db, donor_core_so, world.product, world.own_wh, qty_ordered="40"
    )
    donor_order = _project_so(db, donor_project, so_id=donor_core_so.id)
    donor_line = _project_line(
        db, donor_order, line_no=10, product=world.product, core_line=donor_core_line
    )

    borrower_order = _project_so(db, world.project)
    borrower_core_so = _core_so(db, world.company_id)
    borrower_core_line = _core_line(
        db, borrower_core_so, world.product, world.own_wh, qty_ordered="15"
    )
    borrower_line = _project_line(
        db, borrower_order, line_no=10, product=world.product, core_line=borrower_core_line
    )
    db.commit()

    t0 = datetime.utcnow() - timedelta(hours=2)
    t1 = datetime.utcnow() - timedelta(hours=1)

    decision_d = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=borrower_order.id,
        revision_no=1, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": borrower_line.id}],
        confirmed_by=world.eling, confirmed_at=t1, undo_journal=None,
    )
    db.add(decision_d)

    donor_p = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=donor_order.id,
        revision_no=1, state="superseded",
        line_snapshots=[{"line_no": 10, "project_line_id": donor_line.id}],
        confirmed_by=world.eling, confirmed_at=t0,
        superseded_at=t1, superseded_reason="Superseded by revision 2",
    )
    donor_d2 = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=donor_order.id,
        revision_no=2, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": donor_line.id}],
        confirmed_by=world.eling, confirmed_at=t1, supersedes_id=donor_p.id,
        undo_journal=None,
    )
    db.add_all([donor_p, donor_d2])
    db.flush()

    donor_inquiry = OrderInquiry(
        company_id=world.company_id, project_sales_order_id=donor_order.id,
        state=INQUIRY_RAISED, raised_by=world.eling,
    )
    db.add(donor_inquiry)
    db.flush()

    donor_cancelled_row = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=donor_inquiry.id,
        so_line_id=donor_line.id, item_code=world.product.product_code,
        qty=Decimal("40"), verb=IV_ORDER, state=INQUIRY_CANCELLED,
        supply_decision_id=None, note=f"Superseded by revision {donor_d2.revision_no}",
    )
    donor_raised_row = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=donor_inquiry.id,
        so_line_id=donor_line.id, item_code=world.product.product_code,
        qty=Decimal("25"), verb=IV_ORDER, state=INQUIRY_RAISED,
        supply_decision_id=donor_d2.id, created_at=t1 + timedelta(seconds=5),
    )
    db.add_all([donor_cancelled_row, donor_raised_row])
    db.commit()

    reconstruct_undo(db, borrower_order, decision_d, actor_user_id=world.eling)
    db.commit()

    db.expire_all()
    reinstated = (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.id == donor_cancelled_row.id).one()
    )
    assert reinstated.state == INQUIRY_RAISED, (
        "S3: the donor's own superseded row must come back too, not just the "
        "borrower's own rows"
    )
    gone = (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.id == donor_raised_row.id).first()
    )
    assert gone is None, "S3: the donor's own re-issued row must be removed too"


def test_reconstruct_with_no_prior_decision_clears_everything_to_null(api):
    """S6 (review round 1): a journal-less D with `supersedes_id = None` (the FIRST
    revision this order ever had) reconstructs to NOTHING, not to a second decision -
    every row's `supply_decision_id` goes NULL, a cancelled transfer's `supply_
    decision_id` goes NULL, the order ends with no active decision at all, and
    `restored_to` reads None."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="30")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    inquiry = OrderInquiry(
        company_id=world.company_id, project_sales_order_id=order.id,
        state=INQUIRY_RAISED, raised_by=world.eling,
    )
    db.add(inquiry)
    db.flush()

    t1 = datetime.utcnow() - timedelta(hours=1)
    decision_d = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=t1, supersedes_id=None,
        undo_journal=None,
    )
    db.add(decision_d)
    db.flush()

    remaining_row = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("30"), verb=IV_ORDER,
        state=INQUIRY_RAISED, supply_decision_id=decision_d.id,
        created_at=t1 - timedelta(hours=1),
    )
    db.add(remaining_row)
    cancelled_transfer = StockTransfer(
        id=_uid(), company_id=world.company_id, transfer_no=f"ZZT-TR-{_suffix()}",
        so_line_id=core_line.id, project_sales_order_id=order.id,
        supply_decision_id=None, product_id=world.product.id,
        from_warehouse_id=world.pool_wh.id, to_warehouse_id=world.own_wh.id,
        qty=Decimal("5"), kind=TRANSFER_KIND_OWN_GROUP, state=TRANSFER_CANCELLED,
        cancelled_reason=f"Superseded by revision {decision_d.revision_no}",
    )
    db.add(cancelled_transfer)
    db.commit()

    result = reconstruct_undo(db, order, decision_d, actor_user_id=world.eling)
    assert result["restored_to"] is None

    db.expire_all()
    active = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == "active",
        )
        .first()
    )
    assert active is None, "S6: no prior means no active decision after reconstruct"

    row = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == remaining_row.id).one()
    assert row.supply_decision_id is None

    transfer = db.query(StockTransfer).filter(StockTransfer.id == cancelled_transfer.id).one()
    assert transfer.state == TRANSFER_PROPOSED
    assert transfer.supply_decision_id is None


def test_reconstruct_refuses_cleanly_when_confirmed_at_is_none(api):
    """Nit (review round 1): a decision with `confirmed_at IS NULL` must refuse the
    reconstruct with a clean 409, not crash - today `cutoff = decision.confirmed_at -
    timedelta(...)` raises `TypeError` before any refusal check can catch it."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]
    world = fx["world"]

    decision_d = fx["decision_d"]
    decision_d.confirmed_at = None
    db.commit()

    with pytest.raises(AppException) as exc_info:
        reconstruct_undo(db, fx["order"], decision_d, actor_user_id=world.eling)
    assert exc_info.value.status_code == 409

# Nit "duplicate inquiry headers do not 500 the reconstruct" (review round 1) is not
# written: the premise does not hold. `order_inquiries` carries a partial UNIQUE index,
# `uq_project_order_inquiry_per_sales_order` (`app/models/project_so.py`,
# `postgresql_where="amendment_id IS NULL"`), so two headers with `amendment_id IS
# NULL` on the same order cannot exist - inserting a second one 23505s at the INSERT
# itself, before `reconstruct_undo`'s own `.scalar()` read is ever reached. Verified by
# attempting exactly this fixture: `psycopg2.errors.UniqueViolation` on `uq_project_
# order_inquiry_per_sales_order`. Reported to the captain rather than landing a test
# against a state the schema already forbids.



# =============================================================================== #
# AC-R2-19: `covered` from a live, decision-less sheet-migrated inquiry row alone  #
# is a PRE-EXISTING, correct board rule (the 14 Sep ruling) - the fix the owner's  #
# hand test on SO314594 actually needs is on the FE PILL, which must stop reading #
# such a line "Confirmed" (see `BoardDecisionPill.test.tsx`'s own AC-R2-19 cases). #
# This pins today's backend contract (`covered=True, decision=None`) so a later    #
# change does not "fix" `covered` itself and take away the very distinction the   #
# pill now needs to read.                                                         #
# =============================================================================== #


def test_board_reads_covered_true_decision_none_for_a_decisionless_live_inquiry_row(api):
    """AC-R2-19 [BE]. A line whose ONLY order-inquiry row is decision-less
    (`supply_decision_id IS NULL`) and live (state not cancelled/rejected) must read
    `covered=True, decision=None` - the shape `BoardDecisionPill`'s own AC-R2-19 fix
    reads to print "With purchasing" rather than "Confirmed"."""
    client, world = api
    db = world.db

    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="30")
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    inquiry = OrderInquiry(
        company_id=world.company_id, project_sales_order_id=order.id,
        state=INQUIRY_RAISED, raised_by=world.eling,
    )
    db.add(inquiry)
    db.flush()
    db.add(OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("30"), verb=IV_ORDER,
        state=INQUIRY_PLACED, supply_decision_id=None,
    ))
    db.commit()

    response = client.get(
        f"{BASE}/fulfilment-planning/board", params={"orders": core_so.so_number}
    )
    assert response.status_code == 200, response.text
    contribution = next(
        c for c in response.json()["contributions"]
        if c["sales_order_id"] == str(core_so.id) and c["line_no"] == 10
    )
    assert contribution["covered"] is True, (
        "AC-R2-19: a live decision-less inquiry row must still cover the line"
    )
    assert contribution["decision"] is None, (
        "AC-R2-19: covered-by-inquiry must never invent a decision"
    )


# =============================================================================== #
# AC-R2-19a: a reconstructed undo of a planning-change apply must return the       #
# batch to `pending`, the same as the journal path (`test_board_undo_last_confirm  #
# .py::test_undo_of_a_batch_confirm_returns_the_batch_to_pending_and_leaves_the_   #
# book`) - and the board must then re-propose the reopened lines rather than       #
# leave them `covered` by a decision that no longer exists.                       #
# =============================================================================== #


def test_reconstructed_undo_of_a_batch_confirm_returns_the_batch_to_pending_and_reopens_the_board():
    """AC-R2-19a. Reuses `test_planning_change_apply_on_board.py`'s own seeding
    wholesale, exactly the way the journal twin above does, but strips the journal a
    real Confirm always writes BEFORE undoing - standing in for a revision confirmed
    before the journal existed (S5's own premise) - so `undo_confirm`'s `mode ==
    "reconstructed"` branch (AC-R2-34) runs `reconstruct_undo` instead of `undo_last_
    confirm`. A plain (non-batch) revision is covered separately below."""
    from app.models.base import company_scope
    from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
    from app.services import project_seed_service
    from app.services.project_service import register_project
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    from .test_planning_change_apply_on_board import (
        MARKER as BATCH_MARKER,
        _World,
        _apply_from_board,
        _client as batch_client,
        _form_three,
        _product as batch_product,
        _real_db_session,
        _restore as batch_restore,
        _sorento as batch_sorento,
        _uid as batch_uid,
        _user as batch_user,
        _warehouse as batch_warehouse,
    )

    with _real_db_session() as db:
        company_id = batch_sorento(db)
        project_seed_service.run(db, company_id=company_id)
        actor = batch_user(db, f"{BATCH_MARKER} Cyndi")
        project = register_project(
            db, company_id=company_id, actor_user_id=actor, developer_party_id=None,
            title=f"{BATCH_MARKER} Reconstruct Batch World",
        )
        product = batch_product(db)
        pool_wh = batch_warehouse(db, f"ZZT-BRW-{batch_uid()[:4]}", segment="dealer")
        own_wh = batch_warehouse(
            db, f"ZZT-IB-{batch_uid()[:4]}", segment="project", pool_warehouse_id=pool_wh.id
        )
        db.flush()
        db.commit()
        world = _World(db, company_id, actor, project, product, own_wh, pool_wh)

        client, originals = batch_client(db, actor)
        try:
            with company_scope(db, frozenset({company_id})):
                fixture = _form_three((client, world))
                response = _apply_from_board(fixture)
                assert response.status_code == 200, response.text

                decision = (
                    db.query(SOSupplyDecision)
                    .filter(SOSupplyDecision.project_sales_order_id == fixture["order"].id)
                    .order_by(SOSupplyDecision.revision_no.desc())
                    .first()
                )
                assert decision is not None
                batch_id = fixture["batch"].id

                decision.undo_journal = None
                db.commit()

                reconstruct_undo(db, fixture["order"], decision, actor_user_id=actor)
                db.commit()
                db.expire_all()

                batch_rows = (
                    db.query(PlanningChangeRow)
                    .filter(PlanningChangeRow.batch_id == batch_id)
                    .all()
                )
                assert batch_rows, "the batch's own rows must still exist"
                assert all(row.applied_state == "pending" for row in batch_rows), (
                    "AC-R2-19a: a reconstructed undo must return the batch to pending, "
                    "exactly like the journal path"
                )

                batch = (
                    db.query(PlanningChangeBatch)
                    .filter(PlanningChangeBatch.id == batch_id)
                    .one()
                )
                assert batch.applied_at is None, (
                    "AC-R2-19a: applied_at must clear when no applied row of it remains"
                )

                board = client.get(
                    f"{BASE}/fulfilment-planning/board",
                    params={"orders": fixture["core_so"].so_number},
                )
                assert board.status_code == 200, board.text
                core_line_1 = fixture["core_lines"][0]
                contribution = next(
                    c for c in board.json()["contributions"]
                    if c["sales_order_id"] == str(fixture["core_so"].id)
                    and c["line_id"] == str(core_line_1.id)
                )
                assert contribution["covered"] is False, (
                    "AC-R2-19a: a reopened (reopened_by_change) line must not read "
                    f"covered any more: {contribution}"
                )
                assert contribution["sources"], (
                    "AC-R2-19a: a reopened line must be proposed for again, not left blank"
                )
        finally:
            batch_restore(originals)


def test_reconstructed_undo_of_a_plain_confirm_touches_no_planning_change_row(api):
    """AC-R2-19a. A revision from a PLAIN confirm (no batch anywhere near it) must
    reconstruct cleanly and touch no `planning_change_rows` - `reconstruct_undo` must
    not assume every revision came off a batch apply."""
    from app.models.planning_change import PlanningChangeRow
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    fx = _reconstruct_world(api)
    db = fx["db"]

    result = reconstruct_undo(db, fx["order"], fx["decision_d"], actor_user_id=fx["world"].eling)
    db.commit()
    assert result is not None

    touched = (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.project_sales_order_id == fx["order"].id)
        .count()
    )
    assert touched == 0, "AC-R2-19a: a plain confirm must never touch a batch row"


# =============================================================================== #
# AC-R2-19b: a NO-PRIOR reconstruct settles a settled row to NULL (never a         #
# nonexistent prior decision) and restores its qty, while a row this revision      #
# RAISED is deleted outright - nothing is left pointing at the deleted decision.   #
# =============================================================================== #


def test_reconstruct_with_no_prior_settles_row_to_null_and_deletes_the_raised_one(api):
    """AC-R2-19b. `decision_d` is the order's FIRST and only revision
    (`supersedes_id = None`). One row was sheet-migrated (`supply_decision_id` NULL
    before D touched it) then SETTLED in place by D (182 -> 214, `previous_qty=182`
    recorded, D repointed it to itself within the settle window). A second row was
    RAISED by D fresh, with nothing to fall back to. Reconstructing D away must put
    the settled row back at 182 with `supply_decision_id` NULL (not some invented
    prior), delete the raised row outright, and leave no row pointing at D."""
    from app.services.project_supply_undo_reconstruct_service import reconstruct_undo

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="214")
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    inquiry = OrderInquiry(
        company_id=world.company_id, project_sales_order_id=order.id,
        state=INQUIRY_RAISED, raised_by=world.eling,
    )
    db.add(inquiry)
    db.flush()

    t1 = datetime.utcnow() - timedelta(hours=1)
    decision_d = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=t1, supersedes_id=None,
        undo_journal=None,
    )
    db.add(decision_d)
    db.flush()

    settled_row = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("214"), verb=IV_ORDER,
        state=INQUIRY_RAISED, supply_decision_id=decision_d.id,
        created_at=t1 - timedelta(hours=1),
        previous_qty=Decimal("182"), previous_delivery_date=None,
        changed_at=t1 + timedelta(seconds=3),
        note="Was 182 NOS",
    )
    db.add(settled_row)

    raised_row = OrderInquiryRow(
        company_id=world.company_id, order_inquiry_id=inquiry.id, so_line_id=line.id,
        item_code=world.product.product_code, qty=Decimal("30"), verb=IV_ORDER,
        state=INQUIRY_RAISED, supply_decision_id=decision_d.id,
        created_at=t1 + timedelta(seconds=5),
    )
    db.add(raised_row)
    db.commit()

    reconstruct_undo(db, order, decision_d, actor_user_id=world.eling)
    db.commit()
    db.expire_all()

    settled = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == settled_row.id).one()
    assert settled.supply_decision_id is None, (
        "AC-R2-19b: no prior decision to repoint to, so this must fall to NULL"
    )
    assert settled.qty == Decimal("182"), "AC-R2-19b: the row's qty must be restored"

    raised = (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.id == raised_row.id).first()
    )
    assert raised is None, "AC-R2-19b: a row this revision raised must be deleted outright"

    dangling = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.supply_decision_id == decision_d.id)
        .count()
    )
    assert dangling == 0, "AC-R2-19b: nothing may be left pointing at the deleted decision"
