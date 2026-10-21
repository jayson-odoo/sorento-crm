"""OI-RESERVE-PILL-QTY round 2 (owner ruling 21 Oct 2026, "we just need more visibility"):
the OI Excel - the list export and the file the handover email attaches, both printed by
`OrderInquiryWorklistService.export_xlsx` - carries REQUESTED RESERVE and RESERVED right
after QTY, so a 170 line with a 70 reserve request reads as two numbers side by side
(real case: OI-2609-0165, CB315 qty 170, request 70). The planning-board worksheet keeps
its own ten columns, unchanged.

Postgres only (`tests/_pg_fixture.py`), seeded through the reserve suite's own fixtures.
"""
from __future__ import annotations

import io

import openpyxl

from app.services.order_inquiry_worklist_service import (
    EXPORT_HEADINGS,
    WORKSHEET_HEADINGS,
    OrderInquiryWorklistService,
)

from .test_order_inquiry_reserve import _open_row, _service, api  # noqa: F401  (fixture)


def _sheet(world, columns=EXPORT_HEADINGS):
    _name, data = OrderInquiryWorklistService(world.db).export_xlsx(
        inquiry_id=world.inquiry.id, columns=columns
    )
    sheet = openpyxl.load_workbook(io.BytesIO(data)).active
    values = [list(r) for r in sheet.iter_rows(values_only=True)]
    heads = values[1]
    return heads, {r[heads.index("ITEM CODE")]: r for r in values[2:]}


def test_requested_reserve_and_reserved_sit_right_after_qty():
    at = EXPORT_HEADINGS.index("QTY")
    assert EXPORT_HEADINGS[at : at + 3] == ("QTY", "REQUESTED RESERVE", "RESERVED")
    # Nothing else moved relative to each other, and REMARK stays last.
    assert EXPORT_HEADINGS[-1] == "REMARK"
    assert "TOTAL QTY" in EXPORT_HEADINGS


def test_worksheet_keeps_its_own_ten_columns():
    assert WORKSHEET_HEADINGS == (
        "SO DATE", "S/O NO", "ITEM CODE", "QTY", "TOTAL QTY", "DELIVERY DATE",
        "PROJECT/CUSTOMER", "SUPPLIER", "PO NO ", "LOCATION",
    )


def test_excel_prints_the_request_and_the_reserve_beside_the_line_qty(api):
    _client, world = api
    cb315 = _open_row(world, qty="170", item_code="CB315")
    done = _open_row(world, qty="40", item_code="DONE40")
    plain = _open_row(world, qty="9", item_code="PLAIN9")
    service = _service(world.db)
    service.create_request(
        inquiry_id=world.inquiry.id,
        rows=[
            {"row_id": cb315.id, "qty_requested": "70", "warehouse_id": world.site.id},
            {"row_id": done.id, "qty_requested": "25", "warehouse_id": world.site.id},
        ],
        note=None,
        actor_user_id=world.requester,
    )
    world.db.commit()
    service.commit_request(
        inquiry_id=world.inquiry.id,
        reserves=[
            {"row_id": done.id, "warehouse_id": world.site.id, "qty_reserved": "25", "reason": None}
        ],
        amendments=[],
        actor_user_id=world.reserver,
    )
    world.db.commit()

    heads, rows = _sheet(world)
    qty, req, res = (heads.index(h) for h in ("QTY", "REQUESTED RESERVE", "RESERVED"))
    assert (rows["CB315"][qty], rows["CB315"][req], rows["CB315"][res]) == (170.0, 70.0, None)
    # Answered in full: the ask stays beside the answer (owner ruling, 21 Oct 2026).
    assert (rows["DONE40"][qty], rows["DONE40"][req], rows["DONE40"][res]) == (40.0, 25.0, 25.0)
    assert (rows["PLAIN9"][qty], rows["PLAIN9"][req], rows["PLAIN9"][res]) == (9.0, None, None)
    # The columns after the two new ones still carry their own values.
    assert rows["CB315"][heads.index("LOCATION")] == world.site.warehouse_code

    work_heads, work_rows = _sheet(world, WORKSHEET_HEADINGS)
    assert tuple(work_heads) == WORKSHEET_HEADINGS
    assert work_rows["CB315"][work_heads.index("LOCATION")] == world.site.warehouse_code


def test_a_partial_answer_keeps_the_asked_qty_beside_the_reserved_one(api):
    """Owner ruling (21 Oct 2026, crew relay): asked 70, CS reserved 50 - both numbers stay
    visible, REQUESTED RESERVE 70 and RESERVED 50, on the list row and in the Excel. The
    list row carries the asked figure as `asked_reserve_qty`; `requested_qty` stays the
    OPEN request only (the `Request to reserve N` pill and the tick read that)."""
    from .test_order_inquiry_worklist import LIST

    client, world = api
    cb315 = _open_row(world, qty="170", item_code="CB315")
    service = _service(world.db)
    service.create_request(
        inquiry_id=world.inquiry.id,
        rows=[{"row_id": cb315.id, "qty_requested": "70", "warehouse_id": world.site.id}],
        note=None,
        actor_user_id=world.requester,
    )
    world.db.commit()
    service.commit_request(
        inquiry_id=world.inquiry.id,
        reserves=[
            {"row_id": cb315.id, "warehouse_id": world.site.id, "qty_reserved": "50", "reason": "only 50 on hand"}
        ],
        amendments=[],
        actor_user_id=world.reserver,
    )
    world.db.commit()

    heads, rows = _sheet(world)
    qty, req, res = (heads.index(h) for h in ("QTY", "REQUESTED RESERVE", "RESERVED"))
    assert (rows["CB315"][qty], rows["CB315"][req], rows["CB315"][res]) == (170.0, 70.0, 50.0)

    response = client.get(LIST, params={"query": "CB315"})
    assert response.status_code == 200, response.text
    (row,) = [r for r in response.json()["data"] if r["item_code"] == "CB315"]
    assert (row["asked_reserve_qty"], row["requested_qty"], row["reserved_qty"]) == ("70", "0", "50")


def test_a_cancelled_unanswered_request_asks_for_nothing(api):
    """A request purchasing cancelled before CS answered is no longer an ask."""
    _client, world = api
    row = _open_row(world, qty="40", item_code="CANCELLED40")
    service = _service(world.db)
    request = service.create_request(
        inquiry_id=world.inquiry.id,
        rows=[{"row_id": row.id, "qty_requested": "40", "warehouse_id": world.site.id}],
        note=None,
        actor_user_id=world.requester,
    )
    world.db.commit()
    service.cancel_request(request_id=request.id, actor_user_id=world.requester)
    world.db.commit()

    heads, rows = _sheet(world)
    assert rows["CANCELLED40"][heads.index("REQUESTED RESERVE")] is None
