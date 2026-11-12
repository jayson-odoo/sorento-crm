"""OI-WHOLE-SO-CANCEL F2 (owner 00:06: "follow the path of Decide / Confirm like normal
fulfilment planning"), red: a book-cancelled line is DECIDED like any other pending change.

* `planning_change_service.set_row_decision(..., "confirm")` with no composition is accepted on a
  `cancelled` row (today it refuses, planning_change_service.py ~3221-3230);
* confirm-all with that saved row retires the OI rows and queues ONE CANCEL ALL handover (the
  same as today's apply);
* a press with nothing saved is refused and cancels nothing (ASSUMPTION: "today's refusal" for
  an undecided pending row; today the press just applies, which is what changes).

Fixtures from tests/test_oi_whole_so_cancel_board.py.
"""
from __future__ import annotations

import pytest

from app.services import planning_change_service

from .test_oi_whole_so_cancel import (
    _assert_rows_cancelled_once_and_one_cancel_mail,
    _cancelled_rows,
)
from .test_oi_whole_so_cancel_board import (  # noqa: F401 - fixtures/helpers reused
    BASE,
    _captured_dispatches,
    _register,
    _world,
    env,
)
from .test_ac_removed_lines_ingest import _row_snapshot


def _batch_and_rows(env, w):
    rows = _cancelled_rows(env, w["line_x"])
    assert rows, "precondition: the cancel waits on the board"
    return str(rows[0].batch_id), rows


def _confirm_all(env, w, batch_id):
    return env.client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={"orders": [{"pso_id": w["pso_id"], "lines": [], "batch_id": batch_id}]},
    )


@pytest.mark.parametrize("how", ("push", "delete"))
def test_f2_set_row_decision_accepts_confirm_on_a_cancelled_row(env, how):
    w = _world(env, how)
    batch_id, rows = _batch_and_rows(env, w)

    for row in rows:
        planning_change_service.set_row_decision(env.db, batch_id, str(row.id), "confirm")
    env.db.commit()
    env.db.expire_all()

    assert [r.decision for r in _cancelled_rows(env, w["line_x"])] == ["confirm"] * len(rows)


@pytest.mark.parametrize("how", ("push", "delete"))
def test_f2_confirm_all_with_the_saved_cancel_retires_the_rows_and_hands_over_once(
    env, monkeypatch, how
):
    from app.services.project_order_inquiry_service import mark_purchasing_email_trigger

    w = _world(env, how)
    batch_id, rows = _batch_and_rows(env, w)
    for row in rows:
        planning_change_service.set_row_decision(env.db, batch_id, str(row.id), "confirm")
    env.db.commit()
    _register(None)
    calls = _captured_dispatches(monkeypatch)
    mark_purchasing_email_trigger(env.db)
    env.db.commit()

    res = _confirm_all(env, w, batch_id)

    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["ok"] is True, res.text
    env.db.expire_all()
    _assert_rows_cancelled_once_and_one_cancel_mail(env, w["rows"], calls)


def test_f2_a_press_with_nothing_saved_is_refused_and_cancels_nothing(env):
    w = _world(env, "push")
    batch_id, _rows = _batch_and_rows(env, w)

    res = _confirm_all(env, w, batch_id)

    refused = res.status_code >= 400 or res.json()["results"][0]["ok"] is False
    assert refused, res.text
    env.db.expire_all()
    for row_id in w["rows"]:
        assert _row_snapshot(env, row_id)["state"] != "cancelled", row_id


# ============================================================ the draft route, as the FE saves it
@pytest.mark.parametrize("how", ("push", "delete"))
def test_f2_saving_a_book_cancelled_line_through_the_draft_route_then_confirm_all_cancels(
    env, monkeypatch, how
):
    """Browser pass: board "Save all suggested" on a deleted / header-cancelled SO PUTs
    /fulfilment-planning/lines/<contribution key>/draft with {decision: {verdict: approved}}
    and got 422 "That sales order line does not exist, or this company cannot see it" for every
    cancelled line, so Confirm (N) stayed 0. The save must work, and the board's confirm-all
    (the cancel posted as an ordinary line, batch_id on the order) must then cancel the OI rows
    and hand over one email with a CANCEL line per row."""
    from urllib.parse import quote

    from app.services.project_order_inquiry_service import mark_purchasing_email_trigger

    w = _world(env, how)
    board = env.client.get(
        f"{BASE}/fulfilment-planning/board", params={"orders": w["so_number"]}
    ).json()
    contribution = next(c for c in board["contributions"] if c["line_id"] == w["line_x"])
    batch_id = str(_cancelled_rows(env, w["line_x"])[0].batch_id)

    saved = env.client.put(
        f"{BASE}/fulfilment-planning/lines/{quote(contribution['key'], safe='')}/draft",
        json={"decision": {"verdict": "approved"}},
    )
    assert saved.status_code == 200, saved.text

    _register(None)
    calls = _captured_dispatches(monkeypatch)
    mark_purchasing_email_trigger(env.db)
    env.db.commit()
    res = env.client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={
            "orders": [
                {
                    "pso_id": w["pso_id"],
                    "batch_id": batch_id,
                    "lines": [
                        {
                            "project_line_id": contribution["project_line_id"],
                            "timely_spo_qty": "0",
                            "reserve": [],
                            "borrow": [],
                            "buy_qty": "0",
                        }
                    ],
                }
            ]
        },
    )

    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["ok"] is True, res.text
    env.db.expire_all()
    _assert_rows_cancelled_once_and_one_cancel_mail(env, w["rows"], calls)
