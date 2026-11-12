"""OI-WHOLE-SO-CANCEL v2, red tests: the OI shows the SO's current values, and any SO change
since CS's last Confirm reads "Waiting for CS" until CS Confirms.

UAC: documentation/plans/scm/oi-whole-so-cancel-acceptance-criteria.md, section v2
(AC-V2-2 .. AC-V2-6; AC-V2-1 lives in test_oi_whole_so_cancel.py and
test_ac_removed_lines_ingest.py).

Endpoints (BASE /api/v1/project-sales), through `env.client`:
  worklist     GET  /order-inquiries   (blank schema: only this test's rows exist)
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


def _world(env, change=None, *, qty=10, row_qtys=None, ack=ACK_AWAITING):
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
    first_qty = (row_qtys or [qty])[0]
    w.row_id, _ = _so_mirror_row(
        env, w.header, w.line_x, state=INQUIRY_RAISED, ack=ack, qty=str(first_qty)
    )
    w.inquiry_id = str(_so_mirror_row.last[1])
    w.mirror_id = str(_so_mirror_row.last[0].id)
    w.pso_id = str(_so_mirror_row.last[0].project_sales_order_id)
    w.row_ids = [w.row_id]
    w.confirm_qty = qty
    for extra_qty in (row_qtys or [])[1:]:
        more, _ = _so_mirror_row(
            env, w.header, w.line_x, state=INQUIRY_RAISED, ack=ACK_AWAITING,
            qty=str(extra_qty), share=_so_mirror_row.last,
        )
        w.row_ids.append(more)
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
        w.confirm_qty = 7
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
        params={"limit": 100, **params},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _wl_row(env, w, **params):
    rows = [r for r in _worklist(env, w, **params) if r["id"] == w.row_id]
    assert len(rows) == 1, f"the OI row is not on the worklist: {rows}"
    return rows[0]


def _confirm(w):
    """CS Confirm of the pending batch for the line, the way the board does. A date / qty
    change goes through the board's own route (POST /sales-orders/{pso}/confirm with
    batch_id, the line composed as a Buy of the SO's current qty); a cancel kind is applied
    (`planning_change_service.apply`)."""
    env = w.env
    env.db.expire_all()
    rows = (
        env.db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.core_line_id == str(w.line_x["id"]))
        .all()
    )
    assert rows, "precondition: the change waits on the board"
    batch_id = str(rows[0].batch_id)
    if any(r.kind != "cancelled" for r in rows):
        res = env.client.post(
            f"{BASE}/sales-orders/{w.pso_id}/confirm",
            json={
                "batch_id": batch_id,
                "lines": [
                    {
                        "project_line_id": w.mirror_id,
                        "buy_qty": str(w.confirm_qty),
                        "buy_reason": "ZZT no stock anywhere",
                    }
                ],
            },
        )
        assert res.status_code == 200, res.text
    else:
        planning_change_service.apply(env.db, batch_id, _USER_ID)
        env.db.commit()
    env.db.expire_all()


# ============================================================================ AC-V2-2
@pytest.mark.parametrize("change", CHANGES)
def test_ac_v2_2_a_row_waits_for_cs_after_the_push_and_clears_after_confirm(env, change):
    w = _world(env, change)

    assert _wl_row(env, w).get("waiting_for_cs") is True

    _confirm(w)

    # A cancel kind retires the OI row, which the list hides by default (#992): read it
    # with the state filter that lists cancelled rows.
    cancelled_kind = change in ("one_removed", "last_open", "header_cancel", "delete")
    params = {"state": "cancelled"} if cancelled_kind else {}
    assert _wl_row(env, w, **params).get("waiting_for_cs") is False


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
        f"{BASE}/order-inquiries/acknowledge", json={"filter": {"state": "raised"}}
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


def test_ac_v2_4b_a_line_with_two_rows_keeps_each_rows_qty_and_shows_the_line_was(env):
    """ORDER 6 + ORDER 4 on a line of 10; AutoCount cuts the line to 7: each row keeps its own
    confirmed qty, the SO line column reads 7 with Was 10, both rows wait for CS."""
    w = _world(env, "qty", row_qtys=[6, 4])
    assert len(w.row_ids) == 2

    rows = {r["id"]: r for r in _worklist(env, w) if r["id"] in w.row_ids}

    assert set(rows) == set(w.row_ids), rows
    assert sorted(r["qty"] for r in rows.values()) == ["4", "6"], rows
    for row in rows.values():
        assert row["so_line_qty"] == "7", row
        assert row.get("previous_so_line_qty") == "10", row
        assert row.get("waiting_for_cs") is True, row


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
        "list export (POST /order-inquiries/export)": service.export_xlsx()[1],
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
        # the mirror order carries its own S/O NO; the seeded row is the only ZZT-CL-PUSH one
        mine = [r for r in rows if r.get("ITEM CODE") == "ZZT-CL-PUSH"]
        assert mine, (name, rows)
        changed = [r for r in mine if _as_ddmmyyyy(r.get("DELIVERY DATE")) == "01/02/2027"]
        assert len(changed) == 1, (name, mine)
        assert changed[0].get("STATUS") == "Waiting for CS", (name, changed[0])
        assert _as_ddmmyyyy(changed[0].get("WAS DATE")) == "01/01/2027", (name, changed[0])


def test_ac_v2_6_the_per_project_export_route_carries_status_and_was_columns(env):
    """GET /projects/{project_id}/order-inquiry-export (ProjectOrderInquiryService.export_xlsx):
    the same STATUS / WAS QTY / WAS DATE columns, "Waiting for CS" for a date-changed row."""
    from app.models.project_so import ProjectSalesOrder
    from app.models.projects import Project

    w = _world(env, "date")
    title = f"ZZT waiting project {w.so_number}"
    project = Project(
        company_id=env.company_a,
        project_code=f"ZZTWC{w.so_number[-6:]}",
        title=title,
        normalised_title=title.lower(),
        owner_user_id=_USER_ID,
    )
    env.db.add(project)
    env.db.flush()
    pso = env.db.get(ProjectSalesOrder, str(_so_mirror_row.last[0].project_sales_order_id))
    pso.project_id = project.id
    env.db.commit()

    res = env.client.get(f"{BASE}/projects/{project.id}/order-inquiry-export")

    assert res.status_code == 200, res.text
    header, rows = _sheet_rows(res.content)
    for column in ("STATUS", "WAS QTY", "WAS DATE"):
        assert column in header, header
    mine = [r for r in rows if r.get("ITEM CODE") == "ZZT-CL-PUSH"]
    assert len(mine) == 1, rows
    assert mine[0].get("STATUS") == "Waiting for CS", mine[0]
    assert _as_ddmmyyyy(mine[0].get("DELIVERY DATE")) == "01/02/2027", mine[0]
    assert _as_ddmmyyyy(mine[0].get("WAS DATE")) == "01/01/2027", mine[0]


# ================================================================ v2 review gaps (B1..S4)
def _cover_with_po(env, w, *, qty=None):
    """A live PO link covering the row's qty (a real PO line of the same company)."""
    from .test_ac_removed_lines_ingest import _push_po
    from .test_order_inquiry_kinds import _link

    po = _push_po(env)
    link = _link(
        env.db, env.company_a, w.row_id, str(qty or 10),
        po_line_id=po.line_b, document=po.po_number,
    )
    env.db.commit()
    return po, link


def _auto_confirm(env, w):
    from app.models.base import company_scope
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    svc = ProjectOrderInquiryService(env.db)
    with company_scope(env.db, frozenset({env.company_a})):
        svc.refresh_link_state([env.db.get(__import__("app.models.project_so", fromlist=["x"]).OrderInquiryRow, w.row_id)])
        svc.auto_confirm([w.row_id])
    env.db.commit()
    env.db.expire_all()


def test_ac_v2_b1a_control_a_covered_ordinary_row_is_auto_confirmed(env):
    """Control for B1a: the same link on a row with no pending change IS acknowledged."""
    from app.models.project_so import ACK_ACKNOWLEDGED

    w = _world(env)
    _cover_with_po(env, w)

    _auto_confirm(env, w)

    assert _row_snapshot(env, w.row_id)["ack_state"] == ACK_ACKNOWLEDGED


def test_ac_v2_b1a_auto_confirm_does_not_acknowledge_a_waiting_row(env):
    w = _world(env, "date")
    _cover_with_po(env, w)

    _auto_confirm(env, w)

    assert _row_snapshot(env, w.row_id)["ack_state"] == ACK_AWAITING


def test_ac_v2_b1a_the_po_line_cascade_does_not_acknowledge_a_waiting_row(env):
    """The cascade a PO push runs (`auto_confirm_rows_on_po_lines`)."""
    from app.services.project_order_inquiry_service import auto_confirm_rows_on_po_lines

    w = _world(env, "date")
    po, _link_row = _cover_with_po(env, w)

    auto_confirm_rows_on_po_lines(env.db, [po.line_b])
    env.db.commit()
    env.db.expire_all()

    assert _row_snapshot(env, w.row_id)["ack_state"] == ACK_AWAITING


def test_ac_v2_b1b_the_to_confirm_count_matches_what_the_filter_lists(env):
    waiting = _world(env, "date")
    ordinary = _world(env)

    res = env.client.get(f"{BASE}/order-inquiries/summary")
    assert res.status_code == 200, res.text
    chip = res.json()["ack"]["to_confirm"]
    listed = [r["id"] for r in _worklist(env, waiting, ack="to_confirm")]

    assert listed == [ordinary.row_id], listed
    assert chip == len(listed), (chip, listed)


def test_ac_v2_b2_confirming_the_batch_acknowledges_a_row_its_links_fully_cover(env):
    from app.models.project_so import ACK_ACKNOWLEDGED

    w = _world(env, "date")
    _cover_with_po(env, w)
    assert _row_snapshot(env, w.row_id)["ack_state"] == ACK_AWAITING, "precondition"

    _confirm(w)

    assert _row_snapshot(env, w.row_id)["ack_state"] == ACK_ACKNOWLEDGED


def _sheet_cells(content: bytes):
    sheet = openpyxl.load_workbook(io.BytesIO(content)).worksheets[0]
    header = [str(c.value).strip() if c.value is not None else "" for c in sheet[1]]
    return sheet, header


def test_ac_v2_b3_was_date_has_the_same_date_format_as_delivery_date_in_both_exports(env):
    w = _world(env, "date")

    for name, content in _exports(env, w).items():
        sheet, header = _sheet_cells(content)
        assert "WAS DATE" in header, (name, header)
        delivery = sheet.cell(row=2, column=header.index("DELIVERY DATE") + 1)
        was = sheet.cell(row=2, column=header.index("WAS DATE") + 1)
        assert was.value is not None, (name, "WAS DATE is empty")
        assert was.number_format == delivery.number_format, (
            name, was.number_format, delivery.number_format,
        )
        assert "yy" in was.number_format.lower(), (name, was.number_format)


def test_ac_v2_s1_a_date_change_put_back_while_the_item_also_changed_stays_waiting(env):
    w = _world(env, "date")
    assert _wl_row(env, w).get("waiting_for_cs") is True, "precondition"

    # the date goes back to its confirmed value, but the line is now another product
    _push(
        w,
        dict(
            w.record,
            lines=[dict(
                w.x,
                required_date=OLD_DATE,
                product_ref=env.product2_ref,
                product_code=w.y["product_code"],
            ), w.y],
        ),
    )

    assert _wl_row(env, w).get("waiting_for_cs") is True


def test_ac_v2_s2_was_qty_is_empty_for_a_changed_row_and_filled_for_a_waiting_row(env):
    from sqlalchemy import text

    changed = _world(env)
    env.db.execute(
        text(
            "UPDATE order_inquiry_rows SET ack_state = 'changed', previous_qty = 8, "
            "changed_at = now() WHERE id = :i"
        ),
        {"i": changed.row_id},
    )
    env.db.commit()
    waiting = _world(env, "qty")

    def was_qty(content, so_row_qty):
        sheet, header = _sheet_cells(content)
        rows = list(sheet.iter_rows(min_row=2, values_only=True))
        col = header.index("WAS QTY")
        q = header.index("QTY")
        return [r[col] for r in rows if r[q] == so_row_qty]

    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    service = OrderInquiryWorklistService(env.db)
    changed_sheet = service.export_xlsx(inquiry_id=changed.inquiry_id)[1]
    waiting_sheet = service.export_xlsx(inquiry_id=waiting.inquiry_id)[1]

    assert was_qty(changed_sheet, 10) in ([None], [""]), was_qty(changed_sheet, 10)
    assert was_qty(waiting_sheet, 7) == [10], was_qty(waiting_sheet, 7)


def test_ac_v2_s4_a_cancel_so_document_line_waits_for_cs(env):
    """PROBE: an AutoCount Cancel SO document fully cancels ONE line (header open) of an SO
    with a live OI row. After sync the row keeps (raised, awaiting)."""
    from .test_autocount_cancel_effects import _push_xs
    from .test_oi_cancelled_line_used_confirm import _mirror_for_ingest_line

    x = _so_line(env, ref="SRT_DB:4001:5001", qty_ordered=10)
    record = _so_record(env, number="ZZT-S4-SO", ref="ZZTDOC:SO:ZZT-S4-SO", lines=[x])
    res = env.post(INGEST_SO, [record])
    assert res.status_code == 200, res.text
    header = env.header("sales_orders", record["source_ref"])
    line = env.so_lines(header["id"])[0]
    product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
    _mirror, row = _mirror_for_ingest_line(
        env, header["id"], line["id"], product_id, row_state=INQUIRY_RAISED, row_ack=ACK_AWAITING,
    )

    _push_xs(env, "ZZT-S4-SO", 10)
    res = env.post(INGEST_SO, [dict(record, status="open")])
    assert res.status_code == 200, res.text
    env.db.expire_all()

    assert env.so_lines(header["id"])[0]["line_status"] == "cancelled", "precondition"
    snap = _row_snapshot(env, str(row.id))
    assert (snap["state"], snap["ack_state"]) == (INQUIRY_RAISED, ACK_AWAITING), snap


# ============================================================================ H1
def _headers(env, **params):
    res = env.client.get(f"{BASE}/order-inquiry-headers", params={"limit": 100, **params})
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _header_status(env, w, **params):
    mine = [h for h in _headers(env, **params) if h["id"] == w.inquiry_id]
    return mine[0]["status"] if mine else None


def test_ac_v2_h1_an_oi_with_only_a_waiting_row_reads_waiting_for_cs(env):
    """The OI's only live row was acknowledged (Done), then the SO date changed."""
    from app.models.project_so import ACK_ACKNOWLEDGED

    w = _world(env, "date", ack=ACK_ACKNOWLEDGED)

    assert _header_status(env, w, state="all") == "waiting_for_cs"
    assert _header_status(env, w, state="outstanding") == "waiting_for_cs", "listed as outstanding"
    assert _header_status(env, w, state="completed") is None, "not under completed"


def test_ac_v2_h1_after_cs_confirm_the_header_returns_to_todays_rule(env):
    from app.models.project_so import ACK_ACKNOWLEDGED

    w = _world(env, "date", ack=ACK_ACKNOWLEDGED)
    assert _header_status(env, w, state="all") == "waiting_for_cs", "precondition"

    _confirm(w)

    assert _header_status(env, w, state="all") in ("outstanding", "completed")
