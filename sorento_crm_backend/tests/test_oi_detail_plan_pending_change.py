"""OI-WHOLE-SO-CANCEL v2 (owner FAIL round), red: the SO detail's Plan button shows only when
`plannable_lines > 0`, but for a deleted or header-cancelled SO whose pending `cancelled` change
waits on the board, `plannable_lines` is 0 (it counts only undecided demand on admitted orders),
so the owner cannot plan it from the detail while the list's Plan selected opens a board that
admits the lines (AC-WC-9). `plannable_lines` (detail AND list row) must equal the number of
lines the board admits for it, and fall back to 0 once the batch applies.

Reuses the fixtures of tests/test_oi_whole_so_cancel_board.py.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services import planning_change_service

from .test_ingest_documents import _USER_ID
from .test_oi_whole_so_cancel import _cancelled_rows
from .test_oi_whole_so_cancel_board import (  # noqa: F401 - fixtures/helpers reused
    BASE,
    _board,
    _contributions_for_line,
    _world,
    env,
)

SCM = "/api/v1/scm/sales-orders"


def _so_id(env, w) -> str:
    return str(
        env.db.execute(
            text("SELECT id FROM sales_orders WHERE so_number = :n"), {"n": w["so_number"]}
        ).scalar()
    )


def _plannable(env, w) -> tuple[int, int]:
    """(detail, list-row) `plannable_lines` of the SO."""
    detail = env.client.get(f"{SCM}/{_so_id(env, w)}")
    assert detail.status_code == 200, detail.text
    listed = env.client.get(SCM, params={"query": w["so_number"], "limit": 50})
    assert listed.status_code == 200, listed.text
    rows = [r for r in listed.json()["data"] if r["so_number"] == w["so_number"]]
    assert len(rows) == 1, rows
    return detail.json()["plannable_lines"], rows[0]["plannable_lines"]


@pytest.mark.parametrize("how", ("delete", "push"))
def test_ac_v2_plan_a_pending_cancel_makes_the_lines_plannable_then_zero_after_apply(env, how):
    w = _world(env, how)  # delete = a deleted SO, push = a header-cancelled SO
    board_lines = len(_board(env, w)["contributions"])
    assert board_lines > 0, "precondition: the board admits the pending cancelled lines"

    detail, listed = _plannable(env, w)

    assert detail == board_lines, f"detail plannable_lines {detail} vs board {board_lines}"
    assert listed == board_lines, f"list plannable_lines {listed} vs board {board_lines}"

    batch_id = str(_cancelled_rows(env, w["line_x"])[0].batch_id)
    # F2 12/13 Nov: a cancel is saved like any change before Confirm
    from ._cancel_decide import decide_cancelled_rows

    decide_cancelled_rows(env.db, batch_id)
    planning_change_service.apply(env.db, batch_id, _USER_ID)
    env.db.commit()
    env.db.expire_all()

    assert _plannable(env, w) == (0, 0)


def test_ac_v2_plan_guard_an_ordinary_undecided_open_so_keeps_its_plannable_lines(env):
    from .test_ac_removed_lines_ingest import _push_so, _so_mirror_row
    from .test_oi_whole_so_cancel_board import _seed_planning_gaps
    from .test_oi_whole_so_cancel import ACK_AWAITING, INQUIRY_RAISED

    record, header, line_x, y = _push_so(env)
    _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING)
    _seed_planning_gaps(env, header, _so_mirror_row.last[0])
    w = {"so_number": record["so_number"]}

    detail, listed = _plannable(env, w)

    assert detail == listed == 2, (detail, listed)
