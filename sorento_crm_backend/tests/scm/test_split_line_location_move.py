"""SPLIT-SHEET-LOCATION (review S3): a line with acting splits is told through its plan rows
(`_tell_splits` replaces the saved line), so the location AutoCount moved it from must ride
on those rows. Owner Q3: the Confirm email states the move, "NEW LOCATION (was <old>)".

Seed: `test_line_splits_round3`'s owner case (480 / 608 / 752 confirmed as Buy, a pending
AutoCount batch), the New-line plan saved on 480, then AutoCount moves 480 to a sibling
location in the same pool before the batch Confirm.
"""
from __future__ import annotations

from tests.scm.test_line_splits_outputs import emails  # noqa: F401 - the SENT handover
from tests.scm.test_line_splits_round3 import _confirm_batch, _new_line_plan, _save, _seed
from tests.test_oi_handover_excel import stored  # noqa: F401 - autouse storage stub
from tests.test_planning_change_apply_on_board import api, world  # noqa: F401
from tests.test_planning_changes import _warehouse


def test_a_moved_line_with_acting_splits_says_new_location_once(api, emails):
    from app.models.order import SalesOrderLine

    s = _seed(api)
    _save(s, _new_line_plan())
    old = s.world.own_wh.warehouse_code
    sibling = _warehouse(s.db, f"{old}X", segment="project",
                         pool_warehouse_id=s.world.pool_wh.id)
    s.db.get(SalesOrderLine, s.core[480].id).warehouse_id = sibling.id
    s.db.commit()

    sent = _confirm_batch(s, emails)

    lines = [ln for h in sent for ln in h.get("lines") or []]
    phrase = f"NEW LOCATION (was {old})"
    told = [ln for ln in lines if phrase in (ln.get("remark") or "")]
    assert len(told) == 1, [(ln.get("location"), ln.get("remark")) for ln in lines]
    assert told[0]["location"] == sibling.warehouse_code, told[0]
    # The lines AutoCount did not move say nothing about a location.
    assert sum("NEW LOCATION" in (ln.get("remark") or "") for ln in lines) == 1


def test_a_first_confirmed_moved_line_with_splits_says_new_location_once(api, emails):
    """Review round 3 S-a: no earlier decision, only a raised ORDER at the old location; the
    line carries saved splits and AutoCount moved it. The rows' line carries the move into
    the plan rows (`_say_moved` -> `moved_from`), said once."""
    from types import SimpleNamespace

    from tests.scm.test_line_splits_api import _put, _sp
    from tests.test_oi_saved_line_email import D_A, D_B
    from tests.test_so_line_location_change_email import _imported, _post
    from tests.test_planning_changes import _line_payload

    _client, world = api
    order, line, old, new_wh = _imported(api, ["10"], line_qty="10")
    s = SimpleNamespace(client=_client, order=order)
    r = _put(s, [{"line_id": str(line.id), "splits": [
        _sp(6, D_A, on=str(line.id)), _sp(4, D_B, on=None),
    ]}])
    assert r.status_code == 200, f"premise: the splits save ({r.status_code}) {r.text}"
    emails.clear()

    _post(api, order, [_line_payload(line.id, buy_qty="10")])

    lines = [ln for h in emails for ln in h.get("lines") or []]
    told = [ln for ln in lines if f"NEW LOCATION (was {old})" in (ln.get("remark") or "")]
    assert len(told) == 1, [(ln.get("location"), ln.get("remark")) for ln in lines]
