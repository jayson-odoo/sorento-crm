"""OI-WHOLE-SO-CANCEL v2, red tests: the OI shows the SO's current values, and any SO change
since CS's last Confirm reads "Waiting for CS" until CS Confirms.

UAC: documentation/plans/scm/oi-whole-so-cancel-acceptance-criteria.md, section v2
(AC-V2-2 .. AC-V2-6; AC-V2-1 lives in test_oi_whole_so_cancel.py and
test_ac_removed_lines_ingest.py).

Endpoints (BASE /api/v1/project-sales), through `env.client`:
  worklist     GET  /order-inquiries?query=<so_number>
  acknowledge  POST /order-inquiries/acknowledge   {"row_ids": [...]} or {"filter": {...}}
Exports: POST /order-inquiries/export and POST /order-inquiries/{id}/export only enqueue a
worker job; the worker renders with `OrderInquiryWorklistService.export_xlsx(**filters)`
({} for the list, {"inquiry_id": id} for one OI), which is what these tests read back.

Postgres only, every test seeds its own chain. No real names, phones, emails or prices.
"""
from __future__ import annotations

import io
from datetime import date, datetime

import openpyxl
import pytest

from app.models.planning_change import PlanningChangeRow
from app.models.project_so import ACK_AWAITING, INQUIRY_RAISED
from app.services import planning_change_service

from .test_ac_removed_lines_ingest import (  # noqa: F401 - fixtures/helpers reused
    INGEST_SO,
    _row_snapshot,
    _so_mirror_row,
    _so_line,
    _so_record,
    env,
)
from .test_ingest_documents import _USER_ID
from .test_oi_whole_so_cancel import _delete_so, _header_cancel_push

BASE = "/api/v1/project-sales"
OLD_DATE = "2027-01-01"
NEW_DATE = "2027-02-01"
WAITING_MESSAGE = "Waiting for CS to confirm the sales order change"

CHANGES = ("date", "qty", "one_removed", "last_open", "header_cancel", "delete")


# --------------------------------------------------------------------------- helpers
class World:
    pass


def _world(env, change=None, *, qty=10):
    """Two-line SO (x carries one live OI row, qty `qty`, dated OLD_DATE; y stays), pushed
    open. If `change` is given it is then applied by an AutoCount push / delete."""
    w = World()
    w.env = env
    x = _so_line(env, qty_ordered=qty, required_date=OLD_DATE)
    y = _so_line(env, product_ref=env.product2_ref, qty_ordered=10, required_date=OLD_DATE)
    w.x, w.y = x, y
    w.record = _so_record(env, lines=[x, y])
    res = env.post(INGEST_SO, [w.record])
    assert res.status_code == 200, res.text
    w.header = env.header("sales_orders", w.record["source_ref"])
    by_ref = {l["source_ref"]: l for l in env.so_lines(w.header["id"])}
    w.line_x = by_ref[x["source_ref"]]
    w.so_number = w.record["so_number"]
    w.row_id, _ = _so_mirror_row(
        env, w.header, w.line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING, qty=str(qty)
    )
    w.inquiry_id = str(_so_mirror_row.last[1])
    if change:
        _apply_change(w, change)
    return w


def _push(w, record):
    res = w.env.post(INGEST_SO, [record])
    assert res.status_code == 200, res.text
    w.env.db.expire_all()


def _apply_change(w, change):
    env = w.env
    if change == "date":
        _push(w, dict(w.record, lines=[dict(w.x, required_date=NEW_DATE), w.y]))
    elif change == "qty":
        _push(w, dict(w.record, lines=[dict(w.x, qty_ordered=7), w.y]))
    elif change == "one_removed":
        _push(w, dict(w.record, lines=[w.y]))
    elif change == "last_open":
        from sqlalchemy import text

        env.db.execute(
            text(
                "UPDATE sales_order_lines SET line_status = 'cancelled', "
                "cancelled_by_cancel_doc = true, qty_cancelled = qty_ordered "
                "WHERE sales_order_id = :h AND id <> :x"
            ),
            {"h": str(w.header["id"]), "x": str(w.line_x["id"])},
        )
        env.db.commit()
        _push(w, dict(w.record, status="open", lines=[w.y]))
    elif change == "header_cancel":
        _header_cancel_push(env, w.record, w.y)
    elif change == "delete":
        _delete_so(env, w.record)
    else:  # pragma: no cover
        raise AssertionError(change)


def _worklist(env, w, **params):
    res = env.client.get(
        f"{BASE}/order-inquiries",
        params={"query": w.so_number, "limit": 100, **params},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _wl_row(env, w, **params):
    rows = [r for r in _worklist(env, w, **params) if r["id"] == w.row_id]
    assert len(rows) == 1, f"the OI row is not on the worklist: {rows}"
    return rows[0]


def _confirm(w):
    """CS Confirm of the pending batch for the line (planning_change_service.apply)."""
    env = w.env
    env.db.expire_all()
    rows = (
        env.db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.core_line_id == str(w.line_x["id"]))
        .all()
    )
    assert rows, "precondition: the change waits on the board"
    planning_change_service.apply(env.db, str(rows[0].batch_id), _USER_ID)
    env.db.commit()
    env.db.expire_all()


# ============================================================================ AC-V2-2
@pytest.mark.parametrize("change", CHANGES)
def test_ac_v2_2_a_row_waits_for_cs_after_the_push_and_clears_after_confirm(env, change):
    w = _world(env, change)

    assert _wl_row(env, w).get("waiting_for_cs") is True

    _confirm(w)

    assert _wl_row(env, w).get("waiting_for_cs") is False


def test_ac_v2_2_a_date_change_then_changed_back_before_confirm_is_not_waiting(env):
    w = _world(env, "date")
    assert _wl_row(env, w).get("waiting_for_cs") is True, "precondition"

    _push(w, dict(w.record, lines=[dict(w.x, required_date=OLD_DATE), w.y]))

    assert _wl_row(env, w).get("waiting_for_cs") is False


def test_ac_v2_2_a_row_with_no_sales_order_change_is_not_waiting(env):
    w = _world(env)

    assert _wl_row(env, w).get("waiting_for_cs") is False


# ============================================================================ AC-V2-3
def test_ac_v2_3_purchasing_cannot_acknowledge_a_waiting_row(env):
    w = _world(env, "date")

    res = env.client.post(f"{BASE}/order-inquiries/acknowledge", json={"row_ids": [w.row_id]})

    assert res.status_code == 409, res.text
    assert WAITING_MESSAGE in res.text, res.text
    assert _row_snapshot(env, w.row_id)["ack_state"] == ACK_AWAITING


def test_ac_v2_3_the_to_confirm_filter_leaves_a_waiting_row_out_and_no_filter_lists_it(env):
    w = _world(env, "date")

    listed = [r["id"] for r in _worklist(env, w, ack="to_confirm")]
    everything = [r["id"] for r in _worklist(env, w)]

    assert w.row_id not in listed
    assert w.row_id in everything


def test_ac_v2_3_the_select_all_acknowledge_skips_a_waiting_row(env):
    w = _world(env, "date")

    res = env.client.post(
        f"{BASE}/order-inquiries/acknowledge", json={"filter": {"query": w.so_number}}
    )

    assert res.status_code == 200, res.text
    assert _row_snapshot(env, w.row_id)["ack_state"] == ACK_AWAITING


# ============================================================================ AC-V2-4
def test_ac_v2_4_a_qty_change_shows_the_current_qty_with_the_confirmed_one_as_was(env):
    w = _world(env, "qty")

    row = _wl_row(env, w)

    assert (row["qty"], row.get("previous_qty")) == ("7", "10"), row
    assert _row_snapshot(env, w.row_id)["state"] == INQUIRY_RAISED
    from sqlalchemy import text

    stored = env.db.execute(
        text("SELECT qty FROM order_inquiry_rows WHERE id = :i"), {"i": w.row_id}
    ).scalar()
    assert int(stored) == 10, "the stored row qty is CS's confirmed one until Confirm"


# ============================================================================ AC-V2-5
@pytest.mark.parametrize("change", ("header_cancel", "delete"))
def test_ac_v2_5_a_cancelled_or_deleted_so_reads_so_cancelled(env, change):
    w = _world(env, change)

    assert _wl_row(env, w).get("so_cancelled") is True


def test_ac_v2_5_a_removed_line_reads_line_cancelled_not_so_cancelled(env):
    w = _world(env, "one_removed")

    row = _wl_row(env, w)

    assert row["line_cancelled"] is True, row
    assert row.get("so_cancelled") is False, row


# ============================================================================ AC-V2-6
def _sheet_rows(content: bytes):
    sheet = openpyxl.load_workbook(io.BytesIO(content)).worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    return header, [dict(zip(header, r)) for r in rows[1:]]


def _as_ddmmyyyy(value):
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    return value


def _exports(env, w):
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    service = OrderInquiryWorklistService(env.db)
    return {
        "list export (POST /order-inquiries/export)": service.export_xlsx(query=w.so_number)[1],
        "OI export (POST /order-inquiries/{id}/export)": service.export_xlsx(
            inquiry_id=w.inquiry_id
        )[1],
    }


def test_ac_v2_6_both_exports_carry_status_was_qty_and_was_date_columns(env):
    w = _world(env, "date")

    for name, content in _exports(env, w).items():
        header, _rows = _sheet_rows(content)
        for column in ("STATUS", "WAS QTY", "WAS DATE"):
            assert column in header, (name, header)


def test_ac_v2_6_a_date_changed_waiting_row_exports_status_new_date_and_was_date(env):
    w = _world(env, "date")

    for name, content in _exports(env, w).items():
        _header, rows = _sheet_rows(content)
        mine = [r for r in rows if r.get("S/O NO") == w.so_number and r.get("ITEM CODE") == w.x["product_code"]] if "product_code" in w.x else [
            r for r in rows if r.get("S/O NO") == w.so_number
        ]
        assert mine, (name, rows)
        changed = [r for r in mine if _as_ddmmyyyy(r.get("DELIVERY DATE")) == "01/02/2027"]
        assert len(changed) == 1, (name, mine)
        assert changed[0].get("STATUS") == "Waiting for CS", (name, changed[0])
        assert _as_ddmmyyyy(changed[0].get("WAS DATE")) == "01/01/2027", (name, changed[0])
