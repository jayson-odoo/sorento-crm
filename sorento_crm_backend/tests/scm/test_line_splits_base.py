"""OI-LINE-SPLIT owner hand test 18 Oct (AC-B2, AC-A3): the base of a line AutoCount ADDED and then
EDITED inside one never-applied planning-change batch, and lines delivered in full.

SO417636 shape: the batch holds an older row per line (`added`, `superseded`, to 417 @ 20 Oct)
and a newer PENDING row with an EMPTY `from` (a newer row carries the older row's `from`, here
none): `advanced` -> 14 @ 20 Sep. The line as it arrived (the older `added` row's `to`) is its
base, not 0. Matching is by the AutoCount line (`core_line_id`) only. Every row is seeded here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.planning_change import (
    PLANNING_CHANGE_STATE_PENDING,
    PLANNING_CHANGE_STATE_SUPERSEDED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from tests.scm.test_line_splits_api import _get, _line, _mirror, _put, _sp, _url  # noqa: F401
from tests.test_planning_change_apply_on_board import api, world  # noqa: F401 - fixtures
from tests.test_planning_changes import _core_so, _project_so

D_417, D_14 = date(2026, 10, 20), date(2026, 9, 20)
D_192, D_632 = date(2026, 11, 20), date(2026, 11, 20)
D_504, D_670, D_649 = date(2026, 12, 20), date(2027, 1, 2), date(2027, 1, 2)
D_167 = date(2029, 11, 20)


class _S:
    pass


def _row(db, batch, order, *, core, line, kind, state, to_qty, to_date, at, line_no):
    row = PlanningChangeRow(
        batch_id=batch.id, project_sales_order_id=str(order.id),
        project_line_id=str(line.id) if line is not None else None,
        core_line_id=str(core.id), line_no=line_no, kind=kind, from_json={},
        to_json={"qty": float(to_qty), "required_date": to_date.isoformat()},
        facts_json={}, applied_state=state, board_link="", created_at=at,
        company_id=order.company_id,
    )
    db.add(row)
    return row


def _seed(api):
    """Lines 480 (417 -> 14), 608 (192 -> 632), 752 (504 -> 670 -> 649), 900 (only an `added`
    row), 950 (a pending row but NO earlier `added` row of its own; a decoy `added` row of
    another core line holds 417)."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    mk = lambda no, qty, when: _mirror(  # noqa: E731
        db, order, core_so, world.product, world.own_wh, line_no=no, qty=qty, when=when)
    s.c480, s.l480 = mk(480, 14, D_14)
    s.c608, s.l608 = mk(608, 632, D_632)
    s.c752, s.l752 = mk(752, 649, D_649)
    s.c900, s.l900 = mk(900, 4, date(2026, 10, 16))
    s.c950, s.l950 = mk(950, 5, date(2026, 8, 1))
    s.decoy, _ = mk(960, 417, D_417)  # another AutoCount line; its `added` row holds 417
    db.flush()
    batch = PlanningChangeBatch(company_id=world.company_id, created_by=world.actor)
    db.add(batch)
    db.flush()
    s.batch = batch
    t0 = datetime(2026, 9, 24, 9, 0, 0)
    step = lambda n: t0 + timedelta(minutes=n)  # noqa: E731
    sup, pen = PLANNING_CHANGE_STATE_SUPERSEDED, PLANNING_CHANGE_STATE_PENDING
    row = lambda **k: _row(db, batch, order, **k)  # noqa: E731
    row(core=s.c480, line=None, kind="added", state=sup, to_qty=417, to_date=D_417, at=step(0), line_no=480)
    row(core=s.c608, line=None, kind="added", state=sup, to_qty=192, to_date=D_192, at=step(0), line_no=608)
    row(core=s.c752, line=None, kind="added", state=sup, to_qty=504, to_date=D_504, at=step(0), line_no=752)
    row(core=s.decoy, line=None, kind="added", state=sup, to_qty=417, to_date=D_417, at=step(0), line_no=960)
    row(core=s.c752, line=None, kind="delayed", state=sup, to_qty=670, to_date=D_670, at=step(5), line_no=752)
    row(core=s.c480, line=s.l480, kind="advanced", state=pen, to_qty=14, to_date=D_14, at=step(10), line_no=480)
    row(core=s.c608, line=s.l608, kind="qty_up", state=pen, to_qty=632, to_date=D_632, at=step(10), line_no=608)
    row(core=s.c752, line=s.l752, kind="qty_down", state=pen, to_qty=649, to_date=D_649, at=step(10), line_no=752)
    row(core=s.c900, line=s.l900, kind="added", state=pen, to_qty=4, to_date=date(2026, 10, 16), at=step(10), line_no=900)
    row(core=s.c950, line=s.l950, kind="qty_up", state=pen, to_qty=5, to_date=date(2026, 8, 1), at=step(10), line_no=950)
    db.commit()
    return s


def _q(x):
    return Decimal(str(x))


def test_a_line_added_then_edited_reads_the_line_as_it_arrived_as_its_base(api):
    s = _seed(api)
    out = _get(s)
    l480, l608, l752 = (_line(out, x.id) for x in (s.l480, s.l608, s.l752))
    assert (_q(l480["base_qty"]), l480["base_date"]) == (Decimal("417"), "2026-10-20")
    assert l480["pending_change"] is True
    assert (_q(l480["now_qty"]), l480["now_date"]) == (Decimal("14"), "2026-09-20")
    assert (_q(l608["base_qty"]), l608["base_date"]) == (Decimal("192"), "2026-11-20")
    assert (_q(l608["now_qty"]), l608["now_date"]) == (Decimal("632"), "2026-11-20")
    assert (_q(l752["base_qty"]), l752["base_date"]) == (Decimal("504"), "2026-12-20"), (
        "three rows: added 504, delayed 670 (superseded), qty_down 649: the arrival is the base"
    )


def test_a_line_whose_only_pending_row_is_its_added_row_keeps_base_zero(api):
    s = _seed(api)
    l900 = _line(_get(s), s.l900.id)
    assert _q(l900["base_qty"]) == 0
    assert l900["base_date"] is None
    assert l900["pending_change"] is True
    assert _q(l900["now_qty"]) == 4


def test_matching_is_by_the_autocount_line_only(api):
    """Another core line's superseded `added` row (417) is never used for line 950."""
    s = _seed(api)
    l950 = _line(_get(s), s.l950.id)
    assert _q(l950["base_qty"]) != 417
    assert _q(l950["base_qty"]) == 0


def test_splits_on_the_derived_base_are_accepted_and_act(api):
    s = _seed(api)
    r = _put(s, [{"line_id": str(s.l480.id), "splits": [
        _sp(14, D_14, on=str(s.l480.id)),
        _sp(236, D_192, on=str(s.l608.id)),
        _sp(167, D_167, on=None),
    ]}])
    assert r.status_code == 200, r.text
    l480 = _line(_get(s), s.l480.id)
    assert l480["split_state"] == "acting"
    assert l480["acting"] is True
    assert _q(l480["base_qty"]) == 417
    assert [_q(x["qty"]) for x in l480["splits"]] == [14, 236, 167]


def test_a_sum_that_misses_the_derived_base_is_refused(api):
    s = _seed(api)
    r = _put(s, [{"line_id": str(s.l480.id), "splits": [
        _sp(14, D_14, on=str(s.l480.id)), _sp(236, D_192, on=str(s.l608.id))]}])
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# A line delivered in full is listed, read-only
# ---------------------------------------------------------------------------


def _delivered(api):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    s.c32, s.l32 = _mirror(db, order, core_so, world.product, world.own_wh,
                           line_no=32, qty=301, when=D_14)
    s.c32.qty_delivered = Decimal("301")
    s.c20, s.l20 = _mirror(db, order, core_so, world.product, world.own_wh,
                           line_no=20, qty=100, when=D_417)
    db.commit()
    return s


def test_a_line_delivered_in_full_is_listed_read_only_with_its_ordered_qty(api):
    s = _delivered(api)
    l32 = _line(_get(s), s.l32.id)
    assert l32.get("delivered_in_full") is True
    assert _q(l32["delivered_qty"]) == 301, "the sheet shows QTY = delivered_qty"
    assert _q(l32["base_qty"]) == 0, "base_qty stays the OPEN base the sum check reads"
    assert l32["base_date"] == "2026-09-20"
    assert l32["now_date"] == "2026-09-20"
    assert l32["splits"] == []
    l20 = _line(_get(s), s.l20.id)
    assert not l20.get("delivered_in_full")


def test_a_line_delivered_in_full_is_refused_as_a_sits_on_target(api):
    s = _delivered(api)
    r = _put(s, [{"line_id": str(s.l20.id), "splits": [
        _sp(60, D_417, on=str(s.l20.id)), _sp(40, D_417, on=str(s.l32.id))]}])
    assert r.status_code == 422, r.text


def test_a_line_delivered_in_full_cannot_be_split(api):
    s = _delivered(api)
    r = _put(s, [{"line_id": str(s.l32.id), "splits": [
        _sp(100, D_14, on=str(s.l32.id)), _sp(201, D_417, on=str(s.l32.id))]}])
    assert r.status_code == 422, r.text
    message = r.json().get("message", "")
    assert "32" in message and "delivered" in message.lower(), message
    assert "add up" not in message, "refused as delivered, not as a sum mismatch"


# ---------------------------------------------------------------------------
# Confirm acts on the derived base (SO417636: 417 -> 14 with 403 linked to 192 -> 632)
# ---------------------------------------------------------------------------


def test_confirm_moves_the_links_of_a_split_made_on_the_derived_base(api):
    from datetime import datetime as _dt

    from app.models.project_so import OrderInquiryRow  # noqa: F401
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from app.services.scm.outstanding_diff import QTY_CHANGED
    from tests.scm.test_line_splits_confirm import _linked, _live
    from tests.test_oi_cancel_bugs_so422492 import _TOLD
    from tests.test_planning_change_apply_on_board import (
        _build, _change, _confirm, _link, _order_row, _po_line, _supplier,
    )
    from tests.test_planning_changes import _line_payload

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    core_a, line_a = _mirror(db, order, core_so, world.product, world.own_wh,
                             line_no=20, qty=417, when=D_417)
    core_b, line_b = _mirror(db, order, core_so, world.product, world.own_wh,
                             line_no=30, qty=192, when=D_192)
    db.commit()
    r = _confirm(client, order.id, [_line_payload(line_a.id, buy_qty="417"),
                                    _line_payload(line_b.id, buy_qty="192")])
    assert r.status_code == 200, r.text
    row_a, row_b = _order_row(world, line_a), _order_row(world, line_b)
    _po, po_line = _po_line(world, _supplier(world), qty=417, expected_date=date(2026, 9, 30))
    _link(world, row_a, po_line, qty=417, document="202609-S0417")
    db.commit()

    core_a.qty_ordered, line_a.qty = Decimal("14"), Decimal("14")
    core_b.qty_ordered, line_b.qty = Decimal("632"), Decimal("632")
    db.commit()
    batch = _build(world, [
        _change(QTY_CHANGED, core_a, so_number=core_so.so_number,
                old_date=D_417, new_date=D_417, old_qty="417", new_qty="14"),
        _change(QTY_CHANGED, core_b, so_number=core_so.so_number,
                old_date=D_192, new_date=D_192, old_qty="192", new_qty="632"),
    ], core_so, [str(core_a.id), str(core_b.id)])
    assert batch is not None, "premise: the pending change batch exists"
    # Reshape into the owner's real data: the pending rows carry NO `from`, and the arrival
    # of each line is an older superseded `added` row of the same batch.
    rows = db.query(PlanningChangeRow).filter(PlanningChangeRow.batch_id == batch.id).all()
    for pending in rows:
        qty_from = (pending.from_json or {}).get("qty")
        date_from = (pending.from_json or {}).get("required_date")
        pending.from_json = {}
        _row(db, batch, order, core=db.get(type(core_a), pending.core_line_id), line=None,
             kind="added", state=PLANNING_CHANGE_STATE_SUPERSEDED, to_qty=qty_from,
             to_date=date.fromisoformat(str(date_from)[:10]),
             at=(pending.created_at or datetime(2026, 9, 24)) - timedelta(minutes=5),
             line_no=pending.line_no)
    db.commit()

    s = _S()
    s.client, s.order = client, order
    r = _put(s, [{"line_id": str(line_a.id), "splits": [
        _sp(14, D_14, on=str(line_a.id)), _sp(403, D_192, on=str(line_b.id))]}])
    assert r.status_code == 200, f"premise: the splits save on the derived base ({r.status_code}) {r.text}"

    before = len(_TOLD)
    r = _confirm(client, order.id, [_line_payload(line_a.id, buy_qty="14"),
                                    _line_payload(line_b.id, buy_qty="632")],
                 batch_id=str(batch.id))
    assert r.status_code == 200, r.text
    db.commit()
    db.expire_all()
    remarks = [(h.get("line_no"), h["line"]["remark"]) for h in _TOLD[before:]]
    from app.models.project_so import INQUIRY_CANCELLED  # noqa: F401
    from tests.scm.test_line_splits_confirm import IV_CANCEL_BALANCE, IV_ORDER
    assert _live(_Ctx(db), line_a, IV_CANCEL_BALANCE) == [], "no CANCEL BALANCE for the moved 403"
    assert not [x for x in remarks if x[0] == 20 and "CANCEL" in x[1]], remarks
    live_b = _live(_Ctx(db), line_b, IV_ORDER)
    assert len(live_b) == 1, "no second ORDER row for the moved qty"
    links = ProjectOrderInquiryService(db)._links_of(live_b[0].id)
    assert sum(Decimal(str(l.qty)) for l in links if l.po_line_id == po_line.id) == Decimal("403")


class _Ctx:
    def __init__(self, db):
        self.db = db
