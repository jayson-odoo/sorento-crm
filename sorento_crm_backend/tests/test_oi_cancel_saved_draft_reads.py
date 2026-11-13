"""OI-WHOLE-SO-CANCEL crew pass a710622e, red: after a draft is saved for a book-cancelled line
(PUT the board draft route, approved verdict), a fresh read must still carry it.

(A1) the board read: `contribution.draft` on each cancelled line of the SO (the board attaches
     drafts to a cancelled row only when `cancel_open_oi_rows` is truthy, and a pending-change
     cancelled row has 0, so the saved draft vanishes and a re-save answers 409);
(A2) the SO detail read: `supply_saved == []` on those lines (an approval with an empty
     composition).

Fixtures from tests/test_oi_whole_so_cancel_board.py. Postgres only, own seeded chain.
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from sqlalchemy import text

from .test_oi_whole_so_cancel_board import BASE, _board, _world, env  # noqa: F401

SCM = "/api/v1/scm/sales-orders"


def _save_every_cancelled_line(env, w):
    contributions = [c for c in _board(env, w)["contributions"] if c.get("cancelled")]
    assert contributions, "precondition: the board lists the pending cancelled lines"
    for contribution in contributions:
        assert contribution["pending_change_batch_id"], contribution
        assert not contribution.get("cancel_open_oi_rows"), contribution
        res = env.client.put(
            f"{BASE}/fulfilment-planning/lines/{quote(contribution['key'], safe='')}/draft",
            json={"decision": {"verdict": "approved"}},
        )
        assert res.status_code == 200, res.text
    env.db.expire_all()
    return contributions


@pytest.mark.parametrize("how", ("delete", "push"))
def test_a1_the_board_read_after_the_save_carries_the_draft_on_each_cancelled_line(env, how):
    w = _world(env, how)
    saved = _save_every_cancelled_line(env, w)

    after = {c["key"]: c for c in _board(env, w)["contributions"] if c.get("cancelled")}

    assert set(after) == {c["key"] for c in saved}
    for key, contribution in after.items():
        assert contribution.get("draft"), f"saved draft missing on {key}: {contribution}"
        assert contribution["draft"]["decision"]["verdict"] == "approved", contribution["draft"]


@pytest.mark.parametrize("how", ("delete", "push"))
def test_a2_the_so_detail_after_the_save_gives_those_lines_supply_saved_empty(env, how):
    w = _world(env, how)
    saved = _save_every_cancelled_line(env, w)
    so_id = str(
        env.db.execute(
            text("SELECT id FROM sales_orders WHERE so_number = :n"), {"n": w["so_number"]}
        ).scalar()
    )

    res = env.client.get(f"{SCM}/{so_id}")

    assert res.status_code == 200, res.text
    by_id = {ln["id"]: ln for ln in res.json()["lines"]}
    for contribution in saved:
        line = by_id[contribution["line_id"]]
        assert line["supply_saved"] == [], (line["id"], line.get("supply_saved"))


# --------------------------------------------------------------------------------------------
# Crew pass ee74c892 (comment 6845735172), red: the board's Confirm on a deleted / header-
# cancelled SO retires the saved cancel lines, but their drafts survived it, so the SO page read
# Decision "Saved" on every confirmed line. A confirmation takes the drafts it promoted with it
# (`project_supply_service.py` S4 rule); the cancel lines it retires are promoted too.
def _drafts_on_lines(env, line_ids):
    return env.db.execute(
        text("SELECT count(*) FROM so_supply_decision_drafts WHERE core_line_id::text = ANY(:ids)"),
        {"ids": list(line_ids)},
    ).scalar()


@pytest.mark.parametrize("how", ("delete", "push"))
def test_b1_the_board_confirm_takes_the_saved_cancel_drafts_with_it(env, monkeypatch, how):
    from .test_oi_whole_so_cancel_board import _confirm_through_the_board_route

    w = _world(env, how)
    saved = _save_every_cancelled_line(env, w)
    line_ids = [c["line_id"] for c in saved]
    assert _drafts_on_lines(env, line_ids) == len(line_ids), "precondition: drafts saved"

    _confirm_through_the_board_route(env, monkeypatch, w)

    assert _drafts_on_lines(env, line_ids) == 0, "the saved cancel drafts survived the Confirm"


@pytest.mark.parametrize("how", ("delete", "push"))
def test_b2_the_so_detail_after_the_confirm_reads_no_saved_decision(env, monkeypatch, how):
    from .test_oi_whole_so_cancel_board import _confirm_through_the_board_route

    w = _world(env, how)
    saved = _save_every_cancelled_line(env, w)
    _confirm_through_the_board_route(env, monkeypatch, w)
    so_id = str(
        env.db.execute(
            text("SELECT id FROM sales_orders WHERE so_number = :n"), {"n": w["so_number"]}
        ).scalar()
    )

    res = env.client.get(f"{SCM}/{so_id}")

    assert res.status_code == 200, res.text
    by_id = {ln["id"]: ln for ln in res.json()["lines"]}
    for contribution in saved:
        line = by_id[contribution["line_id"]]
        assert line.get("supply_saved") is None, (line["id"], line.get("supply_saved"))
