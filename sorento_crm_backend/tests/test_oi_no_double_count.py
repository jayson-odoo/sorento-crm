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
    SOAmendment,
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

    def header(self, *, amendment: bool = False) -> OrderInquiry:
        amendment_id = None
        if amendment:
            # L16: an amendment raises a SECOND header on the same sales order.
            row = SOAmendment(
                id=_uid(),
                company_id=self.company_id,
                project_sales_order_id=self.pso.id,
                delta_json={"rows": []},
            )
            self.db.add(row)
            self.db.flush()
            amendment_id = row.id
        inquiry = OrderInquiry(
            id=_uid(),
            company_id=self.company_id,
            project_sales_order_id=self.pso.id,
            amendment_id=amendment_id,
            state=INQUIRY_RAISED,
        )
        self.db.add(inquiry)
        self.db.flush()
        return inquiry

    def line(
        self,
        line_no: int,
        qty: str,
        *,
        line_status: str = "open",
        reconciled: bool = True,
    ):
        """A core line (the SO grid's own No. and Qty) and its mirror, one-to-one.
        `reconciled=False` is a mirror line AutoCount has not matched yet: no core line
        at all, `core_sales_order_line_id` null (`project_so.py`: "NULL is the normal
        state for every unreconciled line")."""
        product = _product(self.db, f"ZZT-ND-{_uid()[:8]}", f"{MARKER} product")
        if not reconciled:
            mirror = ProjectSalesOrderLine(
                id=_uid(),
                company_id=self.company_id,
                project_sales_order_id=self.pso.id,
                core_sales_order_line_id=None,
                line_no=line_no,
                product_id=product.id,
                qty=Decimal(qty),
                uom="UNIT",
                delivery_date=date(2026, 10, 15),
            )
            self.db.add(mirror)
            self.db.flush()
            return product, None, mirror
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


def test_confirming_an_already_confirmed_line_sweeps_its_used_row_AC_ND_24(api):
    """Review N2 (PR #1266): replaces the whole-inquiry test, which the whole-OI
    `acknowledge_scope` held on its own (it already names used rows), so removing the G6
    sweep left it green. This one goes through the sweep: the line's live row was
    confirmed before this PR and its used row still sits in `changed` (review S2 shape
    a); naming only the live row, already acknowledged, still takes the used row on."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5")
    used = order.row(mirror, product, "2", redirected=True, ack_state=ACK_CHANGED)
    fresh = order.row(mirror, product, "5", ack_state=ACK_ACKNOWLEDGED)
    db.commit()
    assert _header_of(client, order.inquiry.id)["lines_to_confirm"] == 1

    response = client.post(ACK_URL, json={"row_ids": [fresh.id]})
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(OrderInquiryRow, used.id).ack_state == ACK_ACKNOWLEDGED
    header = _header_of(client, order.inquiry.id)
    assert header["lines_to_confirm"] == 0
    assert header["status"] == "completed"


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
    amendment = order.header(amendment=True)
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


def test_confirm_never_sweeps_a_used_row_on_a_cross_pair_of_header_and_line_N1(api):
    """Review N1 (PR #1266, both passes): one Confirm names header A line 1 and header B
    line 2. A used row on header A line 2 matches both ids on their own, but its
    (header, line) pair was never confirmed, so it stays `changed`."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product_1, _c1, mirror_1 = order.line(1, "5")
    product_2, _c2, mirror_2 = order.line(2, "9")
    amendment = order.header(amendment=True)
    fresh_a1 = order.row(mirror_1, product_1, "5", ack_state=ACK_CHANGED)
    fresh_b2 = order.row(mirror_2, product_2, "9", inquiry=amendment, ack_state=ACK_CHANGED)
    used_a2 = order.row(mirror_2, product_2, "3", redirected=True, ack_state=ACK_CHANGED)
    db.commit()

    response = client.post(ACK_URL, json={"row_ids": [fresh_a1.id, fresh_b2.id]})
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(OrderInquiryRow, used_a2.id).ack_state == ACK_CHANGED


# =============================================================================
# Review S1 (PR #1266 at a98e01cf): a line AutoCount has not reconciled yet
# =============================================================================


def test_an_unreconciled_sales_order_line_is_one_line_S1_review(api):
    """`core_sales_order_line_id` is null on every line not yet reconciled to AutoCount,
    so a line key off the core line split its used row and its fresh row into two lines
    (lines_total 2, lines_to_confirm 2). The key is the mirror line, one-to-one with the
    core line, and every row carries it so the Lines tab folds on the same key."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5", reconciled=False)
    used = order.row(mirror, product, "2", redirected=True, ack_state=ACK_CHANGED)
    fresh = order.row(mirror, product, "5", ack_state=ACK_CHANGED)
    db.commit()

    by_id = {row["id"]: row for row in _lines_tab(client, order.inquiry.id)}
    assert by_id[used.id]["so_line_id"] == by_id[fresh.id]["so_line_id"] == mirror.id
    assert by_id[fresh.id]["core_line_id"] is None
    assert by_id[fresh.id]["so_line_no"] == 1
    assert Decimal(by_id[fresh.id]["so_line_qty"]) == Decimal("5")

    header = _header_of(client, order.inquiry.id)
    assert header["lines_total"] == 1
    assert header["lines_to_confirm"] == 1
    assert Decimal(str(header["qty_total"])) == Decimal("5")


def test_a_row_with_no_sales_order_line_carries_a_null_so_line_id_S1_review(api):
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, _mirror = order.line(1, "10")
    loose = order.row(None, product, "3")
    db.commit()

    found = next(r for r in _lines_tab(client, order.inquiry.id) if r["id"] == loose.id)
    assert "so_line_id" in found and found["so_line_id"] is None


# =============================================================================
# Review S2 (PR #1266 at a98e01cf, and SF1 at d0d328d7f): one rule for a waiting used
# row. A used row waits while it is not cancelled and its ack is awaiting or changed;
# `lines_to_confirm` counts its line, the line reads To confirm, and Confirm takes it on.
# =============================================================================


def test_a_used_row_still_awaiting_is_swept_with_its_line_S2_review(api):
    """`lines_to_confirm` counted a used row in `awaiting` (a row redirected before
    purchasing read it) while the sweep only took `changed`, so the header sat
    Outstanding after its line was confirmed."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5")
    used = order.row(mirror, product, "2", redirected=True, ack_state=ACK_AWAITING)
    fresh = order.row(mirror, product, "5", ack_state=ACK_AWAITING)
    db.commit()
    assert _header_of(client, order.inquiry.id)["lines_to_confirm"] == 1

    response = client.post(ACK_URL, json={"row_ids": [fresh.id]})
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(OrderInquiryRow, used.id).ack_state == ACK_ACKNOWLEDGED
    header = _header_of(client, order.inquiry.id)
    assert header["lines_to_confirm"] == 0
    assert header["status"] == "completed"


def test_a_line_confirmed_before_this_pr_confirms_from_the_line_S2_shape_a(api):
    """Shape a: every line confirmed before this PR has its live rows acknowledged and its
    used row still `changed`, because nothing swept then. The ticked line sends its live
    row ids and its waiting used row ids; both are accepted and the header completes."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5")
    used = order.row(mirror, product, "2", redirected=True, ack_state=ACK_CHANGED)
    fresh = order.row(mirror, product, "5", ack_state=ACK_ACKNOWLEDGED)
    db.commit()

    response = client.post(ACK_URL, json={"row_ids": [fresh.id, used.id]})
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(OrderInquiryRow, used.id).ack_state == ACK_ACKNOWLEDGED
    assert _header_of(client, order.inquiry.id)["status"] == "completed"


def test_a_line_whose_only_row_is_used_confirms_by_its_used_row_S2_shape_b(api):
    """Shape b (O2, "Nothing to buy"): the line has only a used row, still `changed`. The
    ticked line sends that used row's id, and Confirm takes it on."""
    client, db, company_id = api
    order = _Order(db, company_id)
    product, _core, mirror = order.line(1, "5")
    used = order.row(mirror, product, "5", redirected=True, ack_state=ACK_CHANGED)
    db.commit()
    header = _header_of(client, order.inquiry.id)
    assert header["lines_to_confirm"] == 1
    assert header["status"] == "outstanding"

    response = client.post(ACK_URL, json={"row_ids": [used.id]})
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.get(OrderInquiryRow, used.id).ack_state == ACK_ACKNOWLEDGED
    header = _header_of(client, order.inquiry.id)
    assert header["lines_to_confirm"] == 0
    assert header["status"] == "completed"


# =============================================================================
# Review N3 (PR #1266 at d0d328d7f): include_history under company scope and RBAC
# =============================================================================


def test_include_history_stays_in_company_scope_and_behind_view_N3():
    """The reviewer's scratch test, kept: another company's header read with
    `include_history=true` returns nothing, a company-wide `include_history` read never
    carries another company's cancelled row, no VIEW is 403, and Confirm without
    `acknowledge` is 403 and sweeps nothing."""
    from app.models.company import Company

    with blank_session() as db:
        company_a = _sorento(db)
        company_b = _uid()
        db.add(Company(id=company_b, name=f"{MARKER} other", code=f"ZZT{_uid()[:6]}"))
        db.flush()
        with company_scope(db, frozenset({company_b})):
            theirs = _Order(db, company_b)
            product_b, _cb, mirror_b = theirs.line(1, "5")
            their_cancelled = theirs.row(mirror_b, product_b, "5", state=INQUIRY_CANCELLED)
            theirs.row(mirror_b, product_b, "5")
        with company_scope(db, frozenset({company_a})):
            ours = _Order(db, company_a)
            product_a, _ca, mirror_a = ours.line(1, "5")
            used = ours.row(mirror_a, product_a, "2", redirected=True, ack_state=ACK_CHANGED)
            fresh = ours.row(mirror_a, product_a, "5", ack_state=ACK_CHANGED)
        user_id = _user(db, f"{MARKER} scope")
        db.commit()
        their_inquiry = theirs.inquiry.id
        their_cancelled_id = their_cancelled.id

        client, originals = _client(db, user_id, [VIEW])
        try:
            with company_scope(db, frozenset({company_a})):
                assert _lines_tab(client, their_inquiry, include_history="true") == []
                response = client.get(LIST, params={"include_history": "true", "limit": 1000})
                assert response.status_code == 200, response.text
                ids = {row["id"] for row in response.json()["data"]}
                assert their_cancelled_id not in ids

                # Confirm without `acknowledge`: refused, and the used row is untouched.
                refused = client.post(ACK_URL, json={"row_ids": [fresh.id]})
                assert refused.status_code == 403, refused.text
                db.expire_all()
                assert db.get(OrderInquiryRow, used.id).ack_state == ACK_CHANGED
        finally:
            _restore(originals)

        client, originals = _client(db, user_id, [])
        try:
            with company_scope(db, frozenset({company_a})):
                response = client.get(
                    LIST, params={"inquiry_id": ours.inquiry.id, "include_history": "true"}
                )
                assert response.status_code == 403, response.text
        finally:
            _restore(originals)
