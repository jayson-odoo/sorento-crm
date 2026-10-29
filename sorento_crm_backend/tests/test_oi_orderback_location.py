"""OI-ORDERBACK-LOCATION (owner ruling 21 Oct 2026 ~11:50 MYT, option A): LOCATION stays the
SO line's own location (13/14 Oct rule) and REMARK names the donor an ORDER BACK is ordered
back to, in the `USE <location>` style, whenever it differs from LOCATION: "ORDER BACK BRW-BB".
A borrow from the line's own location reads plain "ORDER BACK". One row per saved line.

Real case: SO426913 line 96, SRTUB206 x4, SO line at BRW-IR, OI row 2 ORDER_BACK at BRW-BB.
The email read BRW-IR, the Excel BRW-BB, and the purchaser was confused.
"""
from __future__ import annotations

import re
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
    row = next(
        tr for tr in re.findall(r"<tr\b.*?</tr>", body_html, flags=re.S) if item_code in tr
    )
    cells = re.findall(r"<td\b.*?</td>", row, flags=re.S)
    return [re.sub(r"<[^>]+>", "", td).strip() for td in cells]


def test_resend_of_an_order_back_row_names_the_donor_in_remark(rs):
    client, world = rs
    _automation(world)
    inquiry = _oi(world)
    so_line = _so_line(world, inquiry, location="BRW-IR")
    row = _line(world, inquiry, qty="4", item="ZZT-SRTUB206", location="BRW-BB")
    row.verb = IV_ORDER_BACK
    row.so_line_id = so_line.id
    world.db.commit()

    email = _ok(client.post(PREVIEW, json={"inquiry_ids": [inquiry.id]}))["emails"][0]

    assert email["subject"].startswith("OI: BRW-IR @ "), email["subject"]
    cells = _cells(email["body_html"], "ZZT-SRTUB206")
    assert "BRW-IR" in cells, cells
    assert "ORDER BACK BRW-BB" in cells, cells


def test_resend_of_an_order_back_row_at_the_lines_own_location_names_nothing(rs):
    client, world = rs
    _automation(world)
    inquiry = _oi(world)
    so_line = _so_line(world, inquiry, location="BRW-IR")
    row = _line(world, inquiry, qty="4", item="ZZT-SRTUB208", location="BRW-IR")
    row.verb = IV_ORDER_BACK
    row.so_line_id = so_line.id
    world.db.commit()

    email = _ok(client.post(PREVIEW, json={"inquiry_ids": [inquiry.id]}))["emails"][0]

    cells = _cells(email["body_html"], "ZZT-SRTUB208")
    assert "ORDER BACK" in cells and not any("ORDER BACK BRW" in c for c in cells), cells


def test_resend_of_a_plain_order_row_keeps_its_own_location(rs):
    """Control: only ORDER BACK changes; an ORDER row prints its own `stock_location`, not the SO line's."""
    client, world = rs
    _automation(world)
    inquiry = _oi(world)
    so_line = _so_line(world, inquiry, location="BRW-IR")
    row = _line(world, inquiry, qty="4", item="ZZT-SRTUB207", location="BRW-BB")
    row.verb = IV_ORDER
    row.so_line_id = so_line.id
    world.db.commit()

    email = _ok(client.post(PREVIEW, json={"inquiry_ids": [inquiry.id]}))["emails"][0]

    assert email["subject"].startswith("OI: BRW-BB @ "), email["subject"]
    cells = _cells(email["body_html"], "ZZT-SRTUB207")
    assert "BRW-BB" in cells and "BRW-IR" not in cells, cells
    assert "ORDER" in cells and not any("ORDER BACK" in c for c in cells), cells
