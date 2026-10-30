"""OI-AUTO-CONFIRM review round 2, backend (red tests).

UAC: `documentation/plans/scm/oi-auto-confirm-29oct-acceptance-criteria.md` (AC-AC-9,
AC-AC-10a, AC-AC-10e, live-link product read). Postgres only, every test seeds its own chain.

1. Blocker 1 (AC-AC-9): a cancelled SPO push that retires an allocation but KEEPS its link
   reads `awaiting` through the hook (the retired filter in `live_link_filters`).
2. Should-fix 1 (AC-AC-10e): an `actioned` / plain acknowledged ORDER row with a live PO link
   on a line that is then cancelled is `changed` and stays so after a later `auto_confirm`.
3. Should-fix 2 (AC-AC-10a): rejecting a manually confirmed host through `reject_row`
   reopens its companion.
4. Should-fix 3: the product read for cover is the SO line's product, not `item_code`.
5. Nit a: a line split of a covered Done row leaves it Done with its old `changed_at`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.procurement import Supplier
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    INQUIRY_ACTIONED,
    INQUIRY_RAISED,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from ._pg_fixture import blank_session
from .test_ac_removed_lines_spo_ingest import QTY, _push_spo, _repush, _row_on_spo, _snapshot
from .test_ingest_documents import env  # noqa: F401  (fixture)
from .test_oi_cancel_bugs_so422492 import api, world  # noqa: F401  (fixtures)
from .test_oi_auto_confirm import _new_user, _reload, bundle_world  # noqa: F401  (fixture)
from .test_oi_auto_confirm_review1 import _flag_cancelled_line
from .test_oi_cancelled_line_used_confirm import _inquiry, _line_chain, _oi_row
from .test_order_inquiry_kinds import _link, _po_line, _product, _sorento, _spo_allocation, _uid


# =============================================================================================
# 1. Blocker 1: a retired SPO allocation that keeps its link is not cover
# =============================================================================================


def test_hook_a_cancelled_spo_push_that_retires_a_line_but_keeps_its_link_reopens_the_row(
    env, monkeypatch
):
    from .test_ac_removed_lines_ingest import Quiet

    w = _push_spo(env)
    row_id, inquiry_id, link_ids = _row_on_spo(env, w, links=[(w.alloc_a, QTY)])
    Quiet(env, monkeypatch)

    # the document is pushed cancelled AND no longer names line A: `force_closed`, so the
    # placement is kept (AC-RL-31) while `retired_at` is set
    _repush(env, w, lines=[w.payload_b], status="cancelled")

    after = _snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), "the cancelled push keeps the link"
    assert after["ack_state"] == ACK_AWAITING, "a retired allocation is not live cover"


# =============================================================================================
# 2. Should-fix 1: buy rows on a cancelled line (actioned included)
# =============================================================================================


def _po_linked_row(db, *, ack_state=ACK_ACKNOWLEDGED, actioned=False, redirected=False):
    company_id = _sorento(db)
    product = _product(db, f"ZZT-R2-{_uid()[:6]}", "zzt review2 cancelled line")
    supplier = Supplier(
        id=_uid(), company_id=company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name="ZZT review2 supplier",
    )
    db.add(supplier)
    db.flush()
    _order, po_line = _po_line(db, company_id, product, supplier)
    _so, _core, pso, mirror = _line_chain(
        db, company_id, product, qty="10", line_status="open"
    )
    inquiry = _inquiry(db, company_id, pso.id)
    row = _oi_row(
        db, company_id, inquiry.id, mirror.id, product.product_code, "10",
        delivery_date=date(2026, 1, 15), state=INQUIRY_RAISED, ack_state=ack_state,
        redirected=redirected,
    )
    _link(db, company_id, row.id, "10", po_line_id=po_line.id, document=_order.po_number)
    if actioned:
        row.state = INQUIRY_ACTIONED
    db.flush()
    # the real precondition of the flag: the core line is now cancelled
    _core.line_status = "cancelled"
    db.flush()
    return company_id, row


@pytest.mark.parametrize("actioned", [True, False], ids=["actioned", "plain"])
def test_ac_ac_10e_an_acknowledged_covered_buy_row_on_a_cancelled_line_is_done_and_stays(
    actioned,
):
    with blank_session() as db:
        company_id, row = _po_linked_row(db, actioned=actioned)
        _flag_cancelled_line(db, company_id, row)
        after_flag = _reload(db, row).ack_state
        svc = ProjectOrderInquiryService(db)
        with company_scope(db, frozenset({company_id})):
            svc.refresh_link_state([row])
            svc.auto_confirm([row.id])
        after_auto = _reload(db, row).ack_state
        assert (after_flag, after_auto) == (ACK_ACKNOWLEDGED, ACK_ACKNOWLEDGED), (
            after_flag, after_auto,
        )


def test_ac_ac_8_guard_a_used_row_on_a_cancelled_line_stays_done():
    with blank_session() as db:
        company_id, row = _po_linked_row(db, redirected=True)
        _flag_cancelled_line(db, company_id, row)
        with company_scope(db, frozenset({company_id})):
            ProjectOrderInquiryService(db).auto_confirm([row.id])
        assert _reload(db, row).ack_state == ACK_ACKNOWLEDGED


# =============================================================================================
# 3. Should-fix 2: the reject press on a manually confirmed host
# =============================================================================================


def test_ac_ac_10a_rejecting_a_manually_confirmed_host_reopens_its_companion(bundle_world):
    w = bundle_world
    w.rule("CKSW015", ["CKS1050"], supplier=None, ratio="1")
    host = w.row("CKS1050", 1, ack_state=ACK_AWAITING)
    companion = w.row("CKSW015", 1, ack_state=ACK_AWAITING)
    w.svc.derive_bundles(w.inquiry)
    w.db.flush()
    buyer = _new_user(w.db)
    w.svc.acknowledge_rows([host.id], actor_user_id=buyer)
    w.db.flush()
    assert _reload(w.db, companion).ack_state == ACK_ACKNOWLEDGED

    w.svc.reject_row(host.id, reason="not buying this", actor_user_id=buyer)
    w.db.flush()

    assert _reload(w.db, host).ack_state == ACK_REJECTED
    assert _reload(w.db, companion).ack_state == ACK_AWAITING, (
        companion.ack_state, companion.bundled_qty,
    )


# =============================================================================================
# 4. Should-fix 3: cover is read against the SO line's product, not item_code
# =============================================================================================


def _row_with_other_item_code(db, *, link_on_line_product: bool):
    """The SO line is for `line_product`; the row's item_code names `stale_product`."""
    company_id = _sorento(db)
    line_product = _product(db, f"ZZT-R2L-{_uid()[:6]}", "zzt line product")
    stale_product = _product(db, f"ZZT-R2S-{_uid()[:6]}", "zzt stale product")
    _so, _core, pso, mirror = _line_chain(db, company_id, line_product, qty="10")
    inquiry = _inquiry(db, company_id, pso.id)
    row = _oi_row(
        db, company_id, inquiry.id, mirror.id, stale_product.product_code, "10",
        delivery_date=date(2026, 1, 15), state=INQUIRY_RAISED, ack_state=ACK_AWAITING,
    )
    target = line_product if link_on_line_product else stale_product
    allocation = _spo_allocation(db, company_id, target, qty=10)
    _link(db, company_id, row.id, "10", spo_allocation_id=allocation.id,
          document=allocation.spo_number)
    db.flush()
    return company_id, row


def test_a_link_on_the_so_lines_product_covers_a_row_whose_item_code_differs():
    with blank_session() as db:
        company_id, row = _row_with_other_item_code(db, link_on_line_product=True)
        with company_scope(db, frozenset({company_id})):
            ProjectOrderInquiryService(db).auto_confirm([row.id])
        assert _reload(db, row).ack_state == ACK_ACKNOWLEDGED


def test_a_link_on_the_old_product_does_not_cover_a_line_whose_product_changed():
    with blank_session() as db:
        company_id, row = _row_with_other_item_code(db, link_on_line_product=False)
        with company_scope(db, frozenset({company_id})):
            ProjectOrderInquiryService(db).auto_confirm([row.id])
        assert _reload(db, row).ack_state == ACK_AWAITING


# =============================================================================================
# 5. Nit a: a line split of a covered Done row stamps nothing fresh
# =============================================================================================


def test_a_line_split_of_a_covered_done_row_leaves_it_done_with_its_old_changed_at(api):
    from .test_oi_cancel_bugs_so422492 import (
        D_592, _confirm, _core_line, _core_so, _line_payload, _link as _po_link,
        _order_row, _po_line as _po_line_w, _project_line, _project_so, _supplier,
        Change, ADDED, QTY_CHANGED, Line, _build, _change,
    )
    from app.models.project_so import OrderInquiryRow

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_x = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="30",
                        required_date=D_592)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line_x = _project_line(db, order, line_no=100, product=world.product, core_line=core_x)
    db.commit()
    assert _confirm(client, order.id, [_line_payload(line_x.id, buy_qty="30")]).status_code == 200
    row_x = _order_row(world, line_x)
    _, po_line = _po_line_w(world, _supplier(world), qty=30, expected_date=date(2026, 10, 20))
    _po_link(world, row_x, po_line, qty=30, document="202609-S0099")
    old_stamp = datetime(2026, 1, 2, 3, 4, 5)
    with company_scope(db, frozenset({world.company_id})):
        svc = ProjectOrderInquiryService(db)
        svc.refresh_link_state([row_x])
        svc.auto_confirm([row_x.id])
    row_x.changed_at = old_stamp
    db.commit()
    assert _reload(db, row_x).ack_state == ACK_ACKNOWLEDGED

    core_x.qty_ordered = Decimal("20")
    line_x.qty = Decimal("20")
    core_n = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10",
                        required_date=D_592)
    line_n = _project_line(db, order, line_no=101, product=world.product, core_line=core_n)
    db.commit()
    loc = world.own_wh.warehouse_code
    changes = [
        _change(QTY_CHANGED, core_x, so_number=core_so.so_number,
                old_date=D_592, new_date=D_592, old_qty="30", new_qty="20"),
        Change(ADDED, core_so.so_number, world.product.product_code, loc, before=None,
               after=Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                          location=loc, qty=10.0, required_date=D_592, row_ref="1")),
    ]
    batch = _build(world, changes, core_so, [str(core_x.id), str(core_n.id)])
    assert batch is not None
    response = _confirm(
        client, order.id,
        [_line_payload(line_x.id, buy_qty="20"), _line_payload(line_n.id, buy_qty="10")],
        batch_id=str(batch.id),
    )
    assert response.status_code == 200, response.text
    db.commit()
    db.expire_all()

    row_x = db.get(OrderInquiryRow, row_x.id)
    assert row_x.ack_state == ACK_ACKNOWLEDGED, row_x.ack_state
    assert row_x.changed_at == old_stamp, "a split stamps no fresh changed_at"
    moved = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line_n.id).all()
    assert moved and all(r.ack_state == ACK_ACKNOWLEDGED for r in moved), [
        r.ack_state for r in moved
    ]
