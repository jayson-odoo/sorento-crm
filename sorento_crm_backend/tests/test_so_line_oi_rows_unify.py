"""SO-LINE-OI-STATUS-UNIFY (`documentation/plans/scm/PLAN-so-line-oi-status-unify-05nov.md`).

The Sales Order Lines tab's "Order inquiry" cell must read the SAME status as the OI Lines
tab's State cell. The OI page folds the line's rows (`orderInquiryLineFold.ts`) and reads
the primary live row's `ack_state`. Until now the SO read sent only the NEWEST row's
`state` (`_line_inquiries`, last writer wins), so a row linked to a PO but not yet
confirmed by purchasing (`state='placed'`, `ack_state='awaiting'`, owner's SO429216
CKSW015, 5 Nov 2026) read "On PO/SPO" on the SO and "To order" on the OI.

The fix sends the line's rows in the OI worklist's own row shape
(`order_inquiry_rows`), so the FE runs the OI page's fold over them. These tests pin the
payload: every row of the line is there with the fields the fold and the pill read, used
rows included (the fold hides them, the same rule as the OI page).

Runs on the REAL database harness (`test_planning_change_apply_on_board`), seeded behind
the ZZT marker and rolled back.
"""
from __future__ import annotations

from app.models.project_so import OrderInquiryRow

from .test_order_inquiry_rows_deep_link_ids import _raise_one_row
from .test_planning_change_apply_on_board import api, world

__all__ = ["api", "world"]


def _so_line(client, fixture):
    detail = client.get(f"/api/v1/scm/sales-orders/{fixture['core_so'].id}")
    assert detail.status_code == 200, detail.text
    lines = {ln["id"]: ln for ln in detail.json()["lines"]}
    return lines[str(fixture["core"].id)]


def test_so_line_carries_its_oi_rows_in_the_worklist_shape(api):
    """CKSW015's shape: the row is `placed` (a link exists) but purchasing has not
    confirmed it (`ack_state='awaiting'`). The SO line must carry the row with BOTH
    fields, so the shared fold reads "To order" off `ack_state` exactly as the OI page."""
    client, world = api
    fixture = _raise_one_row(api, qty="4")
    row = fixture["row"]
    row.state = "placed"
    row.ack_state = "awaiting"
    world.db.commit()

    line_out = _so_line(client, fixture)
    assert "order_inquiry_rows" in line_out, sorted(line_out)
    rows = line_out["order_inquiry_rows"]
    assert [r["id"] for r in rows] == [str(row.id)], rows
    out = rows[0]
    assert out["state"] == "placed", out
    assert out["ack_state"] == "awaiting", out
    # What the fold and the shared cell read beside the state.
    for key in (
        "order_inquiry_id",
        "inquiry_no",
        "so_line_id",
        "core_line_id",
        "verb",
        "qty",
        "redirected_to_pool",
        "links",
        "reserve_state",
        "rejected_reason",
    ):
        assert key in out, (key, sorted(out))
    assert out["order_inquiry_id"] == str(row.order_inquiry_id), out
    assert out["core_line_id"] == str(fixture["core"].id), out
    assert out["redirected_to_pool"] is False, out


def test_so_line_oi_rows_include_used_and_cancelled_rows_for_the_fold(api):
    """The fold, not the backend, applies the one visibility rule (`isLiveInquiryRow`),
    exactly as on the OI page's Lines tab (`include_history`). So a used row
    (`redirected_to_pool`) and a cancelled row reach the payload flagged as such, and the
    LIVE row is still there beside them: last-writer-wins must not hide it."""
    client, world = api
    fixture = _raise_one_row(api, qty="4")
    live = fixture["row"]
    used = OrderInquiryRow(
        company_id=live.company_id,
        order_inquiry_id=live.order_inquiry_id,
        so_line_id=live.so_line_id,
        item_code=live.item_code,
        qty=live.qty,
        verb=live.verb,
        state="placed",
        redirected_to_pool=True,
    )
    cancelled = OrderInquiryRow(
        company_id=live.company_id,
        order_inquiry_id=live.order_inquiry_id,
        so_line_id=live.so_line_id,
        item_code=live.item_code,
        qty=live.qty,
        verb=live.verb,
        state="cancelled",
    )
    world.db.add_all([used, cancelled])
    world.db.commit()

    line_out = _so_line(client, fixture)
    by_id = {r["id"]: r for r in line_out["order_inquiry_rows"]}
    assert set(by_id) == {str(live.id), str(used.id), str(cancelled.id)}, by_id
    assert by_id[str(used.id)]["redirected_to_pool"] is True
    assert by_id[str(cancelled.id)]["state"] == "cancelled"
    assert by_id[str(live.id)]["state"] == "raised"


def test_so_line_without_oi_rows_sends_none(api):
    """A line nobody raised an inquiry on: `order_inquiry_rows` is null, the same answer
    `order_inquiry` gives ("nobody was told"), so the cell prints a dash."""
    client, world = api
    fixture = _raise_one_row(api, qty="4")
    world.db.delete(fixture["row"])
    world.db.commit()

    line_out = _so_line(client, fixture)
    assert line_out.get("order_inquiry_rows") is None, line_out.get("order_inquiry_rows")
