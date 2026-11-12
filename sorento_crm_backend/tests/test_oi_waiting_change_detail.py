"""OI-WHOLE-SO-CANCEL v2, owner hand-test note, red: a waiting row says WHAT changed.

The worklist row gains `waiting_change`: null, or a LIST of {kind, was, now} (in the order date,
qty, product, location; `so_cancelled` / `line_removed` alone) read from the line's
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
    assert _change(env, "date") == [{"kind": "date", "was": "01/01/2027", "now": "01/02/2027"}]


def test_ac_v2_wc_detail_a_qty_change_names_the_old_and_new_qty(env):
    assert _change(env, "qty") == [{"kind": "qty", "was": "10", "now": "7"}]


@pytest.mark.parametrize("change", ("header_cancel", "delete"))
def test_ac_v2_wc_detail_a_cancelled_or_deleted_so_reads_so_cancelled(env, change):
    detail = _change(env, change)

    assert [d["kind"] for d in detail or []] == ["so_cancelled"], detail


@pytest.mark.parametrize("change", ("one_removed", "last_open"))
def test_ac_v2_wc_detail_a_removed_line_on_an_open_so_reads_line_removed(env, change):
    detail = _change(env, change)

    assert [d["kind"] for d in detail or []] == ["line_removed"], detail


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


def test_ac_v2_wc_detail_a_date_and_qty_change_on_one_line_shows_both(env):
    from .test_oi_waiting_for_cs import NEW_DATE, _push

    w = _world(env)
    _push(w, dict(w.record, lines=[dict(w.x, required_date=NEW_DATE, qty_ordered=7), w.y]))

    assert _wl_row(env, w)["waiting_change"] == [
        {"kind": "date", "was": "01/01/2027", "now": "01/02/2027"},
        {"kind": "qty", "was": "10", "now": "7"},
    ]


def test_ac_v2_wc_detail_a_product_change_that_also_moved_the_date_shows_both(env):
    from .test_oi_waiting_for_cs import NEW_DATE, _push

    w = _world(env)
    new_code = w.y["product_code"]
    _push(
        w,
        dict(
            w.record,
            lines=[
                dict(
                    w.x,
                    required_date=NEW_DATE,
                    product_ref=env.product2_ref,
                    product_code=new_code,
                ),
                w.y,
            ],
        ),
    )

    detail = _wl_row(env, w)["waiting_change"]
    assert [d["kind"] for d in detail or []] == ["date", "product"], detail
    product = detail[1]
    assert product["was"] == w.x["product_code"] and product["now"] == new_code, product


def test_ac_v2_wc_detail_an_added_line_never_yields_a_date_entry(env):
    """A new SO line (no OI row yet) is not a date change: the existing row stays unchanged and
    no worklist row carries a 'date - -> X' entry."""
    from .test_oi_waiting_for_cs import OLD_DATE, _push
    from .test_ingest_documents import _so_line

    w = _world(env)
    added = _so_line(env, product_ref=env.product2_ref, qty_ordered=3, required_date=OLD_DATE)
    _push(w, dict(w.record, lines=[w.x, w.y, added]))

    row = _wl_row(env, w)
    assert row["waiting_change"] is None, row["waiting_change"]
    res = env.client.get("/api/v1/project-sales/order-inquiries", params={"limit": 100})
    for listed in res.json()["data"]:
        for entry in listed.get("waiting_change") or []:
            assert not (entry["kind"] == "date" and entry["was"] is None), entry
