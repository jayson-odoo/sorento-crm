"""OI-LINE-SPLIT owner round 18 Oct (AC-A2, AC-A2b): one `handover_moves` function says what moved,
the line-split read carries `new_qty` / `new_date` off it (null = blank, as in the handover email).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services import project_line_split_service, project_order_inquiry_service
from tests.scm.test_line_splits_api import D_192, D_NEW, _get, _line, _seed as _seed_api  # noqa: F401
from tests.scm.test_line_splits_base import _delivered, _q, _seed as _seed_base  # noqa: F401
from tests.test_planning_change_apply_on_board import _build, _change, _confirm, api, world  # noqa: F401 - fixtures

D = date


def _moves(*a):
    return project_order_inquiry_service.handover_moves(*a)


@pytest.mark.parametrize(
    "args, expected",
    [
        ((Decimal("417"), D(2026, 10, 20), Decimal("14"), D(2026, 9, 20)),
         {"qty": Decimal("417"), "delivery_date": D(2026, 10, 20)}),
        ((Decimal("192"), D(2026, 11, 20), Decimal("632"), D(2026, 11, 20)), {"qty": Decimal("192")}),
        ((Decimal("504"), D(2026, 12, 20), Decimal("504"), D(2027, 1, 2)),
         {"delivery_date": D(2026, 12, 20)}),
        ((Decimal("5"), D(2026, 12, 20), Decimal("5"), D(2026, 12, 20)), {}),
        ((Decimal("5"), D(2026, 12, 20), Decimal("5"), None), {}),
        ((Decimal("192"), D(2026, 11, 20), Decimal("632"), None), {"qty": Decimal("192")}),
        ((Decimal("192.0000"), D(2026, 11, 20), Decimal("192"), D(2026, 11, 20)), {}),
        ((Decimal("0"), None, Decimal("335"), D(2027, 1, 2)),
         {"qty": Decimal("0"), "delivery_date": None}),
    ],
)
def test_handover_moves_table(args, expected):
    assert _moves(*args) == expected


def test_line_split_service_uses_the_same_function_object():
    assert project_line_split_service.handover_moves is project_order_inquiry_service.handover_moves


def _nv(line):
    return (None if line["new_qty"] is None else _q(line["new_qty"]), line["new_date"])


def test_get_carries_new_qty_and_new_date_per_line(api):
    s = _seed_base(api)
    out = _get(s)
    assert _nv(_line(out, s.l480.id)) == (Decimal("14"), "2026-09-20")
    assert _nv(_line(out, s.l608.id)) == (Decimal("632"), None)
    assert _nv(_line(out, s.l752.id)) == (Decimal("649"), "2027-01-02")


def test_get_an_added_line_shows_its_qty_and_date_as_new(api):
    s = _seed_base(api)
    l900 = _line(_get(s), s.l900.id)
    assert _q(l900["base_qty"]) == 0
    assert _nv(l900) == (Decimal("4"), "2026-10-16")


def test_get_a_line_delivered_in_full_has_no_new_cells(api):
    s = _delivered(api)
    assert _nv(_line(_get(s), s.l32.id)) == (None, None)


def test_get_a_line_with_no_pending_change_has_no_new_cells(api):
    s = _seed_api(api, with_pending=False)
    out = _get(s)
    assert _nv(_line(out, s.l100.id)) == (None, None)
    assert _nv(_line(out, s.l300.id)) == (None, None)


def test_get_a_line_whose_splits_were_applied_has_no_new_cells(api):
    """AC-A2b: NEW QTY / NEW DATE present a PENDING change only. Once Confirm applied the splits
    the base (417 @ 20 Oct) still differs from AutoCount now (14 @ 20 Sep) but nothing is pending."""
    from tests.scm.test_line_splits_api import _put, _valid_200

    s = _seed_api(api)
    r = _put(s, [_valid_200(s)])
    assert r.status_code == 200, r.text
    s.db.query(type(s.batch)).filter_by(id=s.batch.id).delete()
    s.db.commit()
    out = _get(s)
    l200 = _line(out, s.l200.id)
    assert l200["split_state"] == "applied"
    assert l200["pending_change"] is False
    assert (_q(l200["base_qty"]), l200["base_date"]) == (Decimal("417"), "2026-10-20")
    assert (_q(l200["now_qty"]), l200["now_date"]) == (Decimal("14"), "2026-09-20")
    assert _nv(l200) == (None, None)
    assert _nv(_line(out, s.l100.id)) == (None, None)


def test_get_a_pending_date_only_move_has_a_new_date_and_no_new_qty(api):
    from app.services.scm.outstanding_diff import DATE_MOVED
    from tests.test_planning_changes import _line_payload

    s = _seed_api(api, with_pending=False)
    resp = _confirm(s.client, s.order.id, [_line_payload(s.l300.id, buy_qty="192")])
    assert resp.status_code == 200, resp.text
    s.c300.required_date = D_NEW
    s.l300.delivery_date = D_NEW
    s.db.commit()
    s.batch = _build(s.world, [
        _change(DATE_MOVED, s.c300, so_number=s.core_so.so_number,
                old_date=D_192, new_date=D_NEW, old_qty="192", new_qty="192"),
    ], s.core_so, [str(s.c300.id)])
    assert s.batch is not None, "premise: the pending change row exists"
    l300 = _line(_get(s), s.l300.id)
    assert l300["pending_change"] is True
    assert _nv(l300) == (None, "2027-01-02")
