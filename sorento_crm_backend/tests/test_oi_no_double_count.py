"""Order inquiry view without double counting, S1 backend (issue #1248).

Contract: `documentation/plans/scm/PLAN-oi-no-double-count-25sep.md` ("Backend seam", slice
S1) and `oi-no-double-count-25sep-acceptance-criteria.md` AC-ND-20 to AC-ND-25, with the
owner's 26 Sep rulings folded in (G6: Confirm sweeps a line's used rows; G10: the header
list's Lines and Qty equal exactly what the Lines tab renders).

TEST-FIRST: written before `include_history`, `so_line_qty` / `so_line_no`, the G10 header
counts or the Confirm sweep exist. Every test fails today on a missing key, an unchanged
count or an untouched `ack_state`, never on a fixture typo.

AC-ND-26 (no write path changes) is held by the existing suites staying green unchanged
(`test_oi_replan_received_links*`, `test_oi_cancelled_line_used_confirm.py`); nothing here
writes a row through the replan path.

Postgres only, on `blank_session()` scratch schemas: every count asserted is exact because
nothing else lives there. Every chain is seeded here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_CANCEL_BALANCE,
    IV_ORDER,
    SO_STATUS_ADOPTED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)

from ._pg_fixture import blank_session
from .test_order_inquiry_kinds import _client, _product, _restore, _sorento, _uid, _user

MARKER = "zzt-oi-nd"
BASE = "/api/v1/project-sales"
LIST = f"{BASE}/order-inquiries"
ACK_URL = f"{LIST}/acknowledge"
HEADERS = f"{BASE}/order-inquiry-headers"
VIEW = "projects.projects.view"
ACKNOWLEDGE = "projects.order_inquiries.acknowledge"


# ---------------------------------------------------------------------------
# seeding
# ---------------------------------------------------------------------------


class _Order:
    """One core sales order, its adopted mirror and ONE order inquiry header on it."""

    def __init__(self, db, company_id: str):
        self.db = db
        self.company_id = company_id
        self.so = SalesOrder(
            id=_uid(),
            company_id=company_id,
            so_number=f"ZZT-ND-{_uid()[:8]}",
            status="open",
            demand_class="project",
        )
        db.add(self.so)
        db.flush()
        self.pso = ProjectSalesOrder(
            id=_uid(),
            company_id=company_id,
            project_id=None,
            provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
            status=SO_STATUS_ADOPTED,
            so_id=self.so.id,
        )
        db.add(self.pso)
        db.flush()
        self.inquiry = self.header()

    def header(self) -> OrderInquiry:
        inquiry = OrderInquiry(
            id=_uid(),
            company_id=self.company_id,
            project_sales_order_id=self.pso.id,
            state=INQUIRY_RAISED,
        )
        self.db.add(inquiry)
        self.db.flush()
        return inquiry

    def line(self, line_no: int, qty: str, *, line_status: str = "open"):
        """A core line (the SO grid's own No. and Qty) and its mirror, one-to-one."""
        product = _product(self.db, f"ZZT-ND-{_uid()[:8]}", f"{MARKER} product")
        core = SalesOrderLine(
            id=_uid(),
            company_id=self.company_id,
            sales_order_id=self.so.id,
            product_id=product.id,
            qty_ordered=Decimal(qty),
            qty_delivered=Decimal("0"),
            required_date=date(2026, 10, 15),
            line_status=line_status,
            line_no=line_no,
        )
        self.db.add(core)
        self.db.flush()
        mirror = ProjectSalesOrderLine(
            id=_uid(),
            company_id=self.company_id,
            project_sales_order_id=self.pso.id,
            core_sales_order_line_id=core.id,
            line_no=line_no,
            product_id=product.id,
            qty=Decimal(qty),
            uom="UNIT",
            delivery_date=date(2026, 10, 15),
        )
        self.db.add(mirror)
        self.db.flush()
        return product, core, mirror

    def row(
        self,
        mirror,
        product,
        qty: str,
        *,
        inquiry: OrderInquiry | None = None,
        verb: str = IV_ORDER,
        state: str = INQUIRY_RAISED,
        ack_state: str = ACK_AWAITING,
        redirected: bool = False,
    ) -> OrderInquiryRow:
        row = OrderInquiryRow(
            id=_uid(),
            company_id=self.company_id,
            order_inquiry_id=(inquiry or self.inquiry).id,
            so_line_id=mirror.id if mirror is not None else None,
            item_code=product.product_code,
            qty=Decimal(qty),
            delivery_date=date(2026, 10, 15),
            verb=verb,
            state=state,
            ack_state=ack_state,
            redirected_to_pool=redirected,
        )
        self.db.add(row)
        self.db.flush()
        return row


@pytest.fixture()
def api():
    """A scratch schema, the Sorento company, one user holding view + acknowledge."""
    with blank_session() as db:
        company_id = _sorento(db)
        user_id = _user(db, f"{MARKER} purchasing")
        db.commit()
        client, originals = _client(db, user_id, [VIEW, ACKNOWLEDGE])
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id
        finally:
            _restore(originals)


def _lines_tab(client, inquiry_id: str, **params) -> list[dict]:
    response = client.get(
        LIST, params={"inquiry_id": inquiry_id, "limit": 200, **params}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _header_of(client, inquiry_id: str) -> dict:
    response = client.get(HEADERS, params={"state": "all", "limit": 100})
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["data"] if item["id"] == inquiry_id)


# =============================================================================
# AC-ND-20: include_history returns every row of the header, cancelled included
# =============================================================================


def test_include_history_returns_cancelled_rows_of_the_header_AC_ND_20(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "10")
    live = order.row(mirror, product, "10")
    superseded = order.row(mirror, product, "8", state=INQUIRY_CANCELLED)
    used = order.row(mirror, product, "2", redirected=True)
    # Another header's cancelled row must never reach this header's read.
    other = _Order(db, company_id)
    other_product, _c, other_mirror = other.line(1, "5")
    other.row(other_mirror, other_product, "5", state=INQUIRY_CANCELLED)
    db.commit()

    with_history = {row["id"] for row in _lines_tab(client, order.inquiry.id, include_history="true")}
    assert with_history == {live.id, superseded.id, used.id}

    without = {row["id"] for row in _lines_tab(client, order.inquiry.id)}
    assert without == {live.id, used.id}, "without the flag the response is unchanged"


def test_include_history_does_not_override_an_explicit_state_filter_AC_ND_20(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "10")
    live = order.row(mirror, product, "10")
    order.row(mirror, product, "8", state=INQUIRY_CANCELLED)
    db.commit()

    rows = _lines_tab(client, order.inquiry.id, include_history="true", state="raised")
    assert [row["id"] for row in rows] == [live.id]


# =============================================================================
# AC-ND-21: so_line_qty and so_line_no on every worklist row
# =============================================================================


def test_every_row_carries_so_line_qty_and_so_line_no_AC_ND_21(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product_a, _core_a, mirror_a = order.line(3, "728")
    product_b, _core_b, mirror_b = order.line(5, "220")
    row_a1 = order.row(mirror_a, product_a, "364")
    row_a2 = order.row(mirror_a, product_a, "364")
    row_b = order.row(mirror_b, product_b, "38")
    row_none = order.row(None, product_b, "7")
    db.commit()

    by_id = {row["id"]: row for row in _lines_tab(client, order.inquiry.id)}
    for row in by_id.values():
        # response_model drops what it is not told about: asserted by name.
        assert "so_line_qty" in row and "so_line_no" in row, row

    assert Decimal(by_id[row_a1.id]["so_line_qty"]) == Decimal("728")
    assert Decimal(by_id[row_a2.id]["so_line_qty"]) == Decimal("728")
    assert by_id[row_a1.id]["so_line_no"] == 3
    assert Decimal(by_id[row_b.id]["so_line_qty"]) == Decimal("220")
    assert by_id[row_b.id]["so_line_no"] == 5
    assert by_id[row_none.id]["so_line_qty"] is None
    assert by_id[row_none.id]["so_line_no"] is None


def test_so_line_qty_is_the_sales_order_grid_qty_not_the_mirror_AC_ND_21(api):
    """The SO grid shows the core line's `qty_ordered`; an amended core line whose mirror
    still carries the old figure reads the SO grid's number."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, core, mirror = order.line(1, "5")
    mirror.qty = Decimal("2")
    row = order.row(mirror, product, "5")
    db.commit()

    found = next(r for r in _lines_tab(client, order.inquiry.id) if r["id"] == row.id)
    assert Decimal(found["so_line_qty"]) == Decimal(core.qty_ordered) == Decimal("5")


# =============================================================================
# AC-ND-22 / AC-ND-23: header Lines and Qty equal the Lines tab (G10)
# =============================================================================


def test_used_row_is_not_a_second_line_nor_in_qty_AC_ND_22(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "220")
    order.row(mirror, product, "182", redirected=True, ack_state=ACK_ACKNOWLEDGED)
    order.row(mirror, product, "220", ack_state=ACK_ACKNOWLEDGED)
    db.commit()

    header = _header_of(client, order.inquiry.id)
    assert header["lines_total"] == 1
    assert Decimal(str(header["qty_total"])) == Decimal("220")


def test_cancelled_line_counts_as_a_line_but_adds_no_qty_AC_ND_22(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product_open, _c1, mirror_open = order.line(1, "10")
    product_gone, _c2, mirror_gone = order.line(2, "40", line_status="cancelled")
    order.row(mirror_open, product_open, "10")
    order.row(mirror_gone, product_gone, "40")
    db.commit()

    header = _header_of(client, order.inquiry.id)
    assert header["lines_total"] == 2, "the cancelled line is a rendered grey row"
    assert Decimal(str(header["qty_total"])) == Decimal("10")


def test_split_rows_and_notice_rows_fold_into_one_line_AC_ND_22(api):
    """G5: a 364 + 364 split and a CANCEL_BALANCE notice are ONE line; the notice adds to
    no quantity, a superseded row is neither a line nor a quantity."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "728")
    order.row(mirror, product, "364")
    order.row(mirror, product, "364")
    order.row(mirror, product, "30", verb=IV_CANCEL_BALANCE)
    order.row(mirror, product, "900", state=INQUIRY_CANCELLED)
    db.commit()

    header = _header_of(client, order.inquiry.id)
    assert header["lines_total"] == 1
    assert Decimal(str(header["qty_total"])) == Decimal("728")


def test_a_line_whose_rows_are_all_superseded_is_not_rendered_AC_ND_22(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product_a, _c1, mirror_a = order.line(1, "10")
    product_b, _c2, mirror_b = order.line(2, "4")
    order.row(mirror_a, product_a, "10")
    order.row(mirror_b, product_b, "4", state=INQUIRY_CANCELLED)
    db.commit()

    header = _header_of(client, order.inquiry.id)
    assert header["lines_total"] == 1


def test_two_null_line_rows_count_as_two_lines_AC_ND_23(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, _mirror = order.line(1, "10")
    order.row(None, product, "3")
    order.row(None, product, "4")
    db.commit()

    header = _header_of(client, order.inquiry.id)
    assert header["lines_total"] == 2
    assert Decimal(str(header["qty_total"])) == Decimal("7")


def test_lines_to_confirm_counts_lines_not_rows_G10(api):
    """A line with a live row and a used row both waiting is ONE line to confirm."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5")
    order.row(mirror, product, "2", redirected=True, ack_state=ACK_CHANGED)
    order.row(mirror, product, "5", ack_state=ACK_CHANGED)
    db.commit()

    header = _header_of(client, order.inquiry.id)
    assert header["lines_to_confirm"] == 1
    assert header["status"] == "outstanding"


# =============================================================================
# AC-ND-24 / AC-ND-25: Confirm sweeps the line's used rows (G6)
# =============================================================================


def test_confirming_a_line_acknowledges_its_used_rows_AC_ND_24(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5")
    used = order.row(mirror, product, "2", redirected=True, ack_state=ACK_CHANGED)
    fresh = order.row(mirror, product, "5", ack_state=ACK_CHANGED)
    db.commit()

    response = client.post(ACK_URL, json={"row_ids": [fresh.id]})
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(OrderInquiryRow, fresh.id).ack_state == ACK_ACKNOWLEDGED
    assert db.get(OrderInquiryRow, used.id).ack_state == ACK_ACKNOWLEDGED
    header = _header_of(client, order.inquiry.id)
    assert header["lines_to_confirm"] == 0
    assert header["status"] == "completed"


def test_whole_inquiry_confirm_leaves_nothing_waiting_AC_ND_24(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5")
    order.row(mirror, product, "2", redirected=True, ack_state=ACK_CHANGED)
    order.row(mirror, product, "5", ack_state=ACK_CHANGED)
    db.commit()

    response = client.post(
        ACK_URL, json={"filter": {"inquiry_id": order.inquiry.id}}
    )
    assert response.status_code == 200, response.text
    assert _header_of(client, order.inquiry.id)["lines_to_confirm"] == 0


def test_confirm_leaves_used_rows_on_other_lines_and_headers_alone_AC_ND_25(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product_a, _c1, mirror_a = order.line(1, "5")
    product_b, _c2, mirror_b = order.line(2, "9")
    fresh_a = order.row(mirror_a, product_a, "5", ack_state=ACK_CHANGED)
    used_other_line = order.row(
        mirror_b, product_b, "3", redirected=True, ack_state=ACK_CHANGED
    )
    # The same sales order line, but on an amendment header (L16): not this inquiry.
    amendment = order.header()
    used_other_header = order.row(
        mirror_a, product_a, "2", inquiry=amendment, redirected=True, ack_state=ACK_CHANGED
    )
    # A cancelled used row is history, never taken on.
    used_cancelled = order.row(
        mirror_a, product_a, "1", redirected=True, ack_state=ACK_CHANGED,
        state=INQUIRY_CANCELLED,
    )
    db.commit()

    response = client.post(ACK_URL, json={"row_ids": [fresh_a.id]})
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(OrderInquiryRow, fresh_a.id).ack_state == ACK_ACKNOWLEDGED
    assert db.get(OrderInquiryRow, used_other_line.id).ack_state == ACK_CHANGED
    assert db.get(OrderInquiryRow, used_other_header.id).ack_state == ACK_CHANGED
    assert db.get(OrderInquiryRow, used_cancelled.id).ack_state == ACK_CHANGED
