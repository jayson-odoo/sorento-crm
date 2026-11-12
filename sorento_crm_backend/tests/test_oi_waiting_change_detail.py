"""OI-WHOLE-SO-CANCEL v2, owner hand-test note, red: a waiting row says WHAT changed.

The worklist row gains `waiting_change`: null, or {kind, was, now} read from the line's
pending planning-change row(s): `so_cancelled` (header cancelled / SO deleted), `line_removed`
(a cancelled change on an open SO), `date` (was / now as dd/mm/yyyy), `qty` (was / now qty).
Reuses the helpers of tests/test_oi_waiting_for_cs.py.
"""
from __future__ import annotations

import pytest

from .test_oi_waiting_for_cs import (  # noqa: F401 - fixtures/helpers reused
    _wl_row,
    _world,
    env,
)


def _change(env, change):
    w = _world(env, change)
    row = _wl_row(env, w)
    assert row.get("waiting_for_cs") is True, "precondition"
    return row.get("waiting_change")


def test_ac_v2_wc_detail_a_date_change_names_the_old_and_new_date(env):
    assert _change(env, "date") == {"kind": "date", "was": "01/01/2027", "now": "01/02/2027"}


def test_ac_v2_wc_detail_a_qty_change_names_the_old_and_new_qty(env):
    assert _change(env, "qty") == {"kind": "qty", "was": "10", "now": "7"}


@pytest.mark.parametrize("change", ("header_cancel", "delete"))
def test_ac_v2_wc_detail_a_cancelled_or_deleted_so_reads_so_cancelled(env, change):
    detail = _change(env, change)

    assert detail is not None and detail.get("kind") == "so_cancelled", detail


@pytest.mark.parametrize("change", ("one_removed", "last_open"))
def test_ac_v2_wc_detail_a_removed_line_on_an_open_so_reads_line_removed(env, change):
    detail = _change(env, change)

    assert detail is not None and detail.get("kind") == "line_removed", detail


def test_ac_v2_wc_detail_a_row_with_no_pending_change_has_no_waiting_change(env):
    w = _world(env)
    row = _wl_row(env, w)

    assert "waiting_change" in row, "the field is declared on the worklist row"
    assert row["waiting_change"] is None


@pytest.mark.parametrize("change", ("one_removed", "header_cancel", "delete"))
def test_ac_v2_wc_detail_a_waiting_cancel_matches_both_the_line_cancelled_and_waiting_filters(
    env, change
):
    """Crew 12 Nov: every shown value is filterable, so a waiting cancelled line is listed under
    BOTH ack=line_cancelled and ack=waiting_for_cs (the Confirmed filter's two words)."""
    w = _world(env, change)

    for ack in ("line_cancelled", "waiting_for_cs"):
        res = env.client.get(
            "/api/v1/project-sales/order-inquiries", params={"limit": 100, "ack": ack}
        )
        assert res.status_code == 200, res.text
        assert w.row_id in {r["id"] for r in res.json()["data"]}, ack
