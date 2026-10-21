"""OI-ORDERBACK-LOCATION (owner ruling 21 Oct 2026, option B): an email row that tells an
ORDER BACK prints LOCATION = where the stock is ordered back to, the donor (the OI row's own
`stock_location`), the same as the OI Excel (`order_inquiry_worklist_service._LOCATION`).
It reverses the 13/14 Oct "the SO line's own location" rule for ORDER BACK rows only.

Real case: SO426913 line 96, SRTUB206 x4, SO line at BRW-IR, OI row 2 ORDER_BACK at BRW-BB.
The email read BRW-IR, the Excel BRW-BB, and the purchaser was confused.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.project_so import IV_ORDER, IV_ORDER_BACK, ProjectSalesOrderLine

from ._pg_fixture import blank_session  # noqa: F401 - the `api` world opens it
from .test_oi_handover_resend import PREVIEW, _automation, _line, _ok, _oi, rs  # noqa: F401


def _so_line(world, inquiry, *, location):
    line = ProjectSalesOrderLine(
        project_sales_order_id=inquiry.project_sales_order_id,
        line_no=96,
        qty=Decimal("4"),
        stock_location=location,
    )
    world.db.add(line)
    world.db.flush()
    return line


def _cells(body_html, item_code):
    """The text cells of the email row that names `item_code`."""
    import re

    row = next(
        tr for tr in re.findall(r"<tr\b.*?</tr>", body_html, flags=re.S) if item_code in tr
    )
    return [re.sub(r"<[^>]+>", "", td).strip() for td in re.findall(r"<td\b.*?</td>", row, flags=re.S)]


def test_resend_of_an_order_back_row_prints_the_donor_not_the_so_line(rs):
    client, world = rs
    _automation(world)
    inquiry = _oi(world)
    so_line = _so_line(world, inquiry, location="BRW-IR")
    row = _line(world, inquiry, qty="4", item="ZZT-SRTUB206", location="BRW-BB")
    row.verb = IV_ORDER_BACK
    row.so_line_id = so_line.id
    world.db.commit()

    email = _ok(client.post(PREVIEW, json={"inquiry_ids": [inquiry.id]}))["emails"][0]

    assert email["subject"].startswith("OI: BRW-BB @ "), email["subject"]
    cells = _cells(email["body_html"], "ZZT-SRTUB206")
    assert "BRW-BB" in cells and "BRW-IR" not in cells, cells


def test_resend_of_a_plain_order_row_keeps_its_own_location(rs):
    """Control: only ORDER BACK changes; an ORDER row prints its own `stock_location`."""
    client, world = rs
    _automation(world)
    inquiry = _oi(world)
    so_line = _so_line(world, inquiry, location="BRW-IR")
    row = _line(world, inquiry, qty="4", item="ZZT-SRTUB207", location="BRW-IR")
    row.verb = IV_ORDER
    row.so_line_id = so_line.id
    world.db.commit()

    email = _ok(client.post(PREVIEW, json={"inquiry_ids": [inquiry.id]}))["emails"][0]

    assert email["subject"].startswith("OI: BRW-IR @ "), email["subject"]
    assert "BRW-IR" in _cells(email["body_html"], "ZZT-SRTUB207")
