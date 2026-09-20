"""Order inquiries: cancelled lines and used rows are shown, and purchasing confirms them.

Contract: `documentation/plans/scm/PLAN-oi-cancelled-line-used-confirm.md` and
`documentation/plans/scm/oi-cancelled-line-used-confirm-acceptance-criteria.md` (AC-CL-1 to
AC-CL-20). This file pins the BACKEND acceptance criteria only (AC-CL-1, 4-15, 18); the
FE-tagged ones (AC-CL-2, 3, 16, 17) and the agent-browser evidence run (AC-CL-19) are not
backend pytest.

TEST-FIRST: written before the coder touches any of `order_inquiry_worklist_service.py`,
`project_order_inquiry_service.py`, `document_ingest_service.py`,
`project_order_inquiry_import_service.py`, or the new `oi_cancelled_used_backfill` module.
Every test either fails on a missing `line_cancelled` key/attribute, a `ModuleNotFoundError`
for the not-yet-written backfill module, or a wrong `ack_state`/`changed_at` value - never on
a fixture typo or an import error unrelated to the contract.

Postgres only (`tests/_pg_fixture.py`), never sqlite. Every test seeds its own chain; nothing
borrows an existing row (CI's database is empty). Four substrates, reused rather than
reinvented:

* `blank_session()` (own helpers below) for the worklist READ (AC-CL-1/4/5), the acknowledge
  ROUTE (AC-CL-9) and the new backfill module (AC-CL-10/14) - a scratch schema, so the totals
  asserted are exact (nothing else lives there).
* `pg_session()` (own `db` fixture below, matching `tests/test_planning_record_mirror.py`'s own
  AC-PR3 harness) for `SalesOrderService.update` - write site 1 of the two the plan names
  (AC-CL-6/7).
* The `env` fixture from `tests/test_ingest_documents.py` for `document_ingest_service` - write
  site 2 (AC-CL-6/7), reusing its own `test_cancelled_on_a_re_push_keeps_the_rows` shape.
* The `api`/`world` fixtures from `tests/test_order_inquiry_draft_links.py` (re-exporting
  `tests/test_order_inquiry_handshake.py`'s own harness) for the used-row writer
  (`_redirect_row_if_received`, AC-CL-12/15) and the sheet importer's `World`/`sheet()` from
  `tests/test_project_order_inquiry_import_migration.py` for the birth-state tests
  (AC-CL-8/13) and the whole journey (AC-CL-18).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    SO_STATUS_ADOPTED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.services import import_outcome_codes as oc

from ._pg_fixture import blank_session, pg_session, unique_code
from .test_ingest_documents import (
    INGEST_SO,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from .test_oi_sheet_pairing_repair import _apply, _rollback
from .test_oi_sheet_rebuild_from_planning import (
    _Capture,
    _adopted_mirror,
    _stamped_row,
    _used_sibling,
)
from .test_oi_sheet_rebuild_from_planning import world as rebuild_world
from .test_order_inquiry_draft_links import (
    _as_purchasing,
    _links_of,
    _open_po_line,
    _link_row_to,
    _raise_one_row,
    _received_spo,
    _settle,
    api,  # noqa: F401 - pytest fixture, imported for reuse
    world,  # noqa: F401 - pytest fixture, imported for reuse
)
from .test_order_inquiry_kinds import (
    _client,
    _link,
    _product,
    _restore,
    _sorento,
    _spo_allocation,
    _uid,
    _user,
)
from .test_project_order_inquiry_import_migration import D_OCT as MIG_D_OCT
from .test_project_order_inquiry_import_migration import sheet as mig_sheet
from .test_project_order_inquiry_import_migration import world as mig_world

__all__ = ["env", "api", "world"]

MARKER = "zzt-oi-cl"
BASE = "/api/v1/project-sales"
LIST = f"{BASE}/order-inquiries"
SUMMARY = f"{LIST}/summary"
ACK_URL = f"{LIST}/acknowledge"
VIEW = "projects.projects.view"
ACKNOWLEDGE = "projects.order_inquiries.acknowledge"


# ---------------------------------------------------------------------------
# shared seeding helpers (blank_session substrate: AC-CL-1/4/5/9, backfill)
# ---------------------------------------------------------------------------


def _line_chain(
    db,
    company_id: str,
    product: Product,
    *,
    qty: str = "10",
    delivery_date: date = date(2026, 1, 15),
    line_status: str = "open",
):
    """One core SO + line (the real `line_status` this whole lane reads), an ADOPTED
    mirror with no project (`project_id IS NULL`), exactly the "adopted, unauthored"
    shape `_upsert_lines`'s own dependents check never refuses."""
    so = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=f"ZZT-CORE-{_uid()[:8]}",
        status="open",
        demand_class="project",
    )
    db.add(so)
    db.flush()
    core_line = SalesOrderLine(
        id=_uid(),
        company_id=company_id,
        sales_order_id=so.id,
        product_id=product.id,
        qty_ordered=Decimal(qty),
        qty_delivered=Decimal("0"),
        required_date=delivery_date,
        line_status=line_status,
    )
    db.add(core_line)
    db.flush()
    pso = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=None,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        status=SO_STATUS_ADOPTED,
        so_id=so.id,
    )
    db.add(pso)
    db.flush()
    mirror = ProjectSalesOrderLine(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=pso.id,
        core_sales_order_line_id=core_line.id,
        line_no=1,
        product_id=product.id,
        qty=Decimal(qty),
        uom="UNIT",
        delivery_date=delivery_date,
    )
    db.add(mirror)
    db.flush()
    return so, core_line, pso, mirror


def _inquiry(db, company_id: str, project_sales_order_id) -> OrderInquiry:
    inquiry = OrderInquiry(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=project_sales_order_id,
        state=INQUIRY_RAISED,
    )
    db.add(inquiry)
    db.flush()
    return inquiry


def _oi_row(
    db,
    company_id: str,
    inquiry_id,
    so_line_id,
    item_code: str,
    qty: str,
    *,
    delivery_date: date | None = None,
    state: str = INQUIRY_RAISED,
    ack_state: str = ACK_ACKNOWLEDGED,
    redirected: bool = False,
    changed_at: datetime | None = None,
    acknowledged_at: datetime | None = None,
) -> OrderInquiryRow:
    row = OrderInquiryRow(
        id=_uid(),
        company_id=company_id,
        order_inquiry_id=inquiry_id,
        so_line_id=so_line_id,
        item_code=item_code,
        qty=Decimal(qty),
        delivery_date=delivery_date,
        verb=IV_ORDER,
        state=state,
        ack_state=ack_state,
        redirected_to_pool=redirected,
        changed_at=changed_at,
        acknowledged_at=acknowledged_at,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# AC-CL-1: the worklist row carries `line_cancelled`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line_status,expected",
    [("open", False), ("closed", False), ("cancelled", True)],
)
def test_worklist_row_carries_line_cancelled_flag(line_status, expected):
    """AC-CL-1: the worklist row's JSON carries `line_cancelled`, true only when the
    sales order line under it has `line_status = cancelled`. Asserted on the ROUTE's own
    JSON - `response_model` silently drops a field it was never told about."""
    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(
            db, f"ZZT-CL1-{line_status}-{_uid()[:6]}", f"{MARKER} product"
        )
        _so, _core_line, _pso, mirror = _line_chain(
            db, company_id, product, line_status=line_status
        )
        inquiry = _inquiry(db, company_id, mirror.project_sales_order_id)
        row = _oi_row(
            db,
            company_id,
            inquiry.id,
            mirror.id,
            product.product_code,
            "10",
            delivery_date=date(2026, 1, 15),
        )
        row_id = str(row.id)
        user_id = _user(db, f"{MARKER} tester")
        db.commit()

        client, originals = _client(db, user_id, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                body = client.get(LIST, params={"limit": 200}).json()
        finally:
            _restore(originals)

    found = next(r for r in body["data"] if r["id"] == row_id)
    assert found["line_cancelled"] is expected, found


# ---------------------------------------------------------------------------
# AC-CL-4/5: Buy excludes a cancelled-line row; open/closed are unaffected
# ---------------------------------------------------------------------------


def test_buy_excludes_a_cancelled_line_row_but_keeps_its_link_in_incoming():
    """AC-CL-4: an unlinked row on a cancelled line is out of the Buy card total, the
    `kind=buy` filter and the month-tab reading of the same figure - the three agree. A
    cancelled-line row that already holds a link still counts in Purchased/Incoming."""
    with blank_session() as db:
        company_id = _sorento(db)

        product_open = _product(db, f"ZZT-CL4-OPEN-{_uid()[:6]}", f"{MARKER} open")
        _so_a, _line_a, _pso_a, mirror_a = _line_chain(
            db, company_id, product_open, qty="10", line_status="open"
        )
        inquiry_a = _inquiry(db, company_id, mirror_a.project_sales_order_id)
        row_open = _oi_row(
            db, company_id, inquiry_a.id, mirror_a.id, product_open.product_code, "10",
            delivery_date=date(2026, 1, 15),
        )

        product_unlinked = _product(db, f"ZZT-CL4-UNL-{_uid()[:6]}", f"{MARKER} unlinked")
        _so_b, _line_b, _pso_b, mirror_b = _line_chain(
            db, company_id, product_unlinked, qty="40", line_status="cancelled"
        )
        inquiry_b = _inquiry(db, company_id, mirror_b.project_sales_order_id)
        row_cancelled_unlinked = _oi_row(
            db, company_id, inquiry_b.id, mirror_b.id, product_unlinked.product_code, "40",
            delivery_date=date(2026, 1, 15),
        )

        product_linked = _product(db, f"ZZT-CL4-LNK-{_uid()[:6]}", f"{MARKER} linked")
        _so_c, _line_c, _pso_c, mirror_c = _line_chain(
            db, company_id, product_linked, qty="25", line_status="cancelled"
        )
        inquiry_c = _inquiry(db, company_id, mirror_c.project_sales_order_id)
        row_cancelled_linked = _oi_row(
            db, company_id, inquiry_c.id, mirror_c.id, product_linked.product_code, "25",
            delivery_date=date(2026, 1, 15),
        )
        allocation = _spo_allocation(db, company_id, product_linked, qty=25)
        _link(
            db, company_id, row_cancelled_linked.id, "25",
            spo_allocation_id=allocation.id, document=allocation.spo_number,
        )

        row_open_id = str(row_open.id)
        row_cancelled_linked_id = str(row_cancelled_linked.id)
        row_cancelled_unlinked_id = str(row_cancelled_unlinked.id)
        user_id = _user(db, f"{MARKER} tester")
        db.commit()

        client, originals = _client(db, user_id, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                summary = client.get(SUMMARY).json()
                buy_list = client.get(LIST, params={"kind": "buy", "limit": 200}).json()
                month_summary = client.get(
                    SUMMARY, params={"delivery_month": "2026-01"}
                ).json()
                spo_list = client.get(LIST, params={"kind": "spo", "limit": 200}).json()
        finally:
            _restore(originals)

    assert summary["kinds"]["buy"] == "10", summary["kinds"]
    assert month_summary["kinds"]["buy"] == "10", month_summary["kinds"]
    assert {r["id"] for r in buy_list["data"]} == {row_open_id}, buy_list["data"]

    assert summary["kinds"]["spo"] == "25", summary["kinds"]
    assert row_cancelled_linked_id in {r["id"] for r in spo_list["data"]}
    assert row_cancelled_unlinked_id not in {r["id"] for r in buy_list["data"]}


@pytest.mark.parametrize("line_status", ["open", "closed"])
def test_open_and_closed_lines_are_unaffected_by_the_exclusion(line_status):
    """AC-CL-5: a row on an open or closed line is unaffected in every count and
    filter - `closed` is not `cancelled`."""
    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(
            db, f"ZZT-CL5-{line_status}-{_uid()[:6]}", f"{MARKER} product"
        )
        _so, _line, _pso, mirror = _line_chain(
            db, company_id, product, qty="15", line_status=line_status
        )
        inquiry = _inquiry(db, company_id, mirror.project_sales_order_id)
        row = _oi_row(
            db, company_id, inquiry.id, mirror.id, product.product_code, "15",
            delivery_date=date(2026, 1, 15),
        )
        row_id = str(row.id)
        user_id = _user(db, f"{MARKER} tester")
        db.commit()

        client, originals = _client(db, user_id, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                summary = client.get(SUMMARY).json()
                buy_list = client.get(LIST, params={"kind": "buy", "limit": 200}).json()
        finally:
            _restore(originals)

    assert summary["kinds"]["buy"] == "15", summary["kinds"]
    assert {r["id"] for r in buy_list["data"]} == {row_id}, buy_list["data"]


# ---------------------------------------------------------------------------
# AC-CL-6/7: write site 1, the sales order edit (`SalesOrderService._upsert_lines`)
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _so_edit_chain(
    db,
    *,
    row_state: str = INQUIRY_RAISED,
    row_ack: str = ACK_ACKNOWLEDGED,
    changed_at: datetime | None = None,
):
    """One core SO + line (no explicit `company_id` - the `CompanyScopedMixin`
    before_insert auto-stamp handles it, matching `tests/test_planning_record_mirror.py`'s
    own AC-PR3 harness), an ADOPTED mirror with no project, one live OrderInquiryRow so the
    dependents check cancels rather than deletes on removal."""
    cat = ProductCategory(
        id=_uid(), category_code=unique_code(MARKER), category_name=f"{MARKER} cat"
    )
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
    db.add_all([cat, uom])
    db.flush()
    product = Product(
        id=_uid(), product_code=unique_code("SKU"), product_name=f"{MARKER} p",
        category_id=cat.id, base_uom_id=uom.id, list_price=Decimal("0"), is_active=True,
    )
    db.add(product)
    db.flush()

    so = SalesOrder(
        id=_uid(), so_number=unique_code(MARKER), status="open", demand_class="project",
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_uid(), sales_order_id=so.id, product_id=product.id,
        qty_ordered=Decimal("10"), qty_delivered=Decimal("0"), line_status="open",
    )
    db.add(line)
    db.flush()

    pso = ProjectSalesOrder(
        id=_uid(), project_id=None, provisional_ref=unique_code(MARKER),
        status=SO_STATUS_ADOPTED, so_id=so.id,
    )
    db.add(pso)
    db.flush()
    mirror = ProjectSalesOrderLine(
        id=_uid(), project_sales_order_id=pso.id, core_sales_order_line_id=line.id,
        line_no=1, product_id=product.id, qty=Decimal("10"), uom="PCS",
        delivery_date=date(2027, 1, 1),
    )
    db.add(mirror)
    db.flush()

    inquiry = OrderInquiry(id=_uid(), project_sales_order_id=pso.id, state=INQUIRY_RAISED)
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(), order_inquiry_id=inquiry.id, so_line_id=mirror.id,
        item_code=product.product_code, qty=Decimal("10"), delivery_date=date(2027, 1, 1),
        verb=IV_ORDER, state=row_state, ack_state=row_ack, changed_at=changed_at,
    )
    db.add(row)
    db.flush()
    db.commit()
    return so, product, line, row


def _cancel_via_so_edit(db, so) -> None:
    """Site 1 (AC-CL-6): dropping the order's only line from the payload cancels it
    in place, because the mirror carries a LIVE order-inquiry dependent."""
    from app.schemas.scm_orders import SalesOrderUpdate
    from app.services.scm.sales_order_service import SalesOrderService

    SalesOrderService(db).update(so.id, SalesOrderUpdate(lines=[]), user_id=None)


@pytest.mark.parametrize("row_state", [INQUIRY_RAISED, INQUIRY_PLACED, INQUIRY_ACTIONED])
def test_so_edit_cancel_flags_an_acknowledged_row_changed(db, row_state):
    """AC-CL-6 (write site 1): a live row (raised/placed/actioned) that was
    `acknowledged` becomes `changed` with `changed_at` set the moment its line is
    cancelled by the sales order edit."""
    so, _product, line, row = _so_edit_chain(db, row_state=row_state, row_ack=ACK_ACKNOWLEDGED)

    _cancel_via_so_edit(db, so)

    db.expire_all()
    line = db.get(SalesOrderLine, line.id)
    row = db.get(OrderInquiryRow, row.id)
    assert line.line_status == "cancelled"
    assert row.ack_state == ACK_CHANGED
    assert row.changed_at is not None


@pytest.mark.parametrize(
    "row_ack,pre_changed_at",
    [(ACK_AWAITING, None), (ACK_CHANGED, datetime(2026, 1, 1)), (ACK_REJECTED, None)],
)
def test_so_edit_cancel_leaves_non_acknowledged_rows_untouched(db, row_ack, pre_changed_at):
    """AC-CL-6: a row already `awaiting`, `changed` or `rejected` is left as it is."""
    so, _product, _line, row = _so_edit_chain(
        db, row_state=INQUIRY_RAISED, row_ack=row_ack, changed_at=pre_changed_at
    )

    _cancel_via_so_edit(db, so)

    db.expire_all()
    row = db.get(OrderInquiryRow, row.id)
    assert row.ack_state == row_ack
    assert row.changed_at == pre_changed_at


def test_so_edit_cancel_leaves_a_row_whose_own_state_is_cancelled_untouched(db):
    """AC-CL-6: a row whose OWN state is already `cancelled` is never flagged, even
    when its line transitions - a second, live row on the same line keeps the line's
    dependents check on the CANCEL path so this is a real test of the row filter."""
    so, _product, _line, live_row = _so_edit_chain(
        db, row_state=INQUIRY_RAISED, row_ack=ACK_ACKNOWLEDGED
    )
    dead_row = OrderInquiryRow(
        id=_uid(), order_inquiry_id=live_row.order_inquiry_id,
        so_line_id=live_row.so_line_id, item_code=live_row.item_code,
        qty=Decimal("3"), delivery_date=live_row.delivery_date, verb=IV_ORDER,
        state=INQUIRY_CANCELLED, ack_state=ACK_ACKNOWLEDGED,
    )
    db.add(dead_row)
    db.flush()
    db.commit()

    _cancel_via_so_edit(db, so)

    db.expire_all()
    dead_row = db.get(OrderInquiryRow, dead_row.id)
    assert dead_row.ack_state == ACK_ACKNOWLEDGED
    assert dead_row.changed_at is None


def test_so_edit_repeated_cancel_does_not_reflag_a_reconfirmed_row(db):
    """AC-CL-7 (write site 1): only the TRANSITION flags a row - an edit that leaves an
    already-cancelled line cancelled flags nothing, so a row purchasing has
    re-confirmed does not come back."""
    so, _product, line, row = _so_edit_chain(db, row_state=INQUIRY_RAISED, row_ack=ACK_ACKNOWLEDGED)

    _cancel_via_so_edit(db, so)
    db.expire_all()
    line = db.get(SalesOrderLine, line.id)
    row = db.get(OrderInquiryRow, row.id)
    assert line.line_status == "cancelled"
    assert row.ack_state == ACK_CHANGED
    first_changed_at = row.changed_at
    assert first_changed_at is not None

    # purchasing re-confirms
    row.ack_state = ACK_ACKNOWLEDGED
    db.flush()
    db.commit()

    _cancel_via_so_edit(db, so)

    db.expire_all()
    row = db.get(OrderInquiryRow, row.id)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.changed_at == first_changed_at


# ---------------------------------------------------------------------------
# AC-CL-6/7: write site 2, the AutoCount document push (`document_ingest_service`)
# ---------------------------------------------------------------------------


def _mirror_for_ingest_line(
    env,
    so_id,
    line_id,
    product_id,
    *,
    qty: str = "182",
    row_state: str = INQUIRY_RAISED,
    row_ack: str = ACK_ACKNOWLEDGED,
    changed_at: datetime | None = None,
):
    pso = ProjectSalesOrder(
        id=_uid(), project_id=None, provisional_ref=unique_code(MARKER),
        status=SO_STATUS_ADOPTED, so_id=so_id,
    )
    env.db.add(pso)
    env.db.flush()
    mirror = ProjectSalesOrderLine(
        id=_uid(), project_sales_order_id=pso.id, core_sales_order_line_id=line_id,
        line_no=1, product_id=product_id, qty=Decimal(qty), uom="PCS",
        delivery_date=date(2027, 1, 1),
    )
    env.db.add(mirror)
    env.db.flush()
    inquiry = OrderInquiry(id=_uid(), project_sales_order_id=pso.id, state=INQUIRY_RAISED)
    env.db.add(inquiry)
    env.db.flush()
    row = OrderInquiryRow(
        id=_uid(), order_inquiry_id=inquiry.id, so_line_id=mirror.id,
        item_code="ZZT-CL-PUSH", qty=Decimal(qty), delivery_date=date(2027, 1, 1),
        verb=IV_ORDER, state=row_state, ack_state=row_ack, changed_at=changed_at,
    )
    env.db.add(row)
    env.db.flush()
    env.db.commit()
    return mirror, row


def _create_then_prep_push(env):
    record = _so_record(env, lines=[_so_line(env)])
    res = env.post(INGEST_SO, [record])
    assert res.status_code == 200, res.text
    header = env.header("sales_orders", record["source_ref"])
    line = env.so_lines(header["id"])[0]
    product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
    return record, header, line, product_id


@pytest.mark.parametrize("row_state", [INQUIRY_RAISED, INQUIRY_PLACED, INQUIRY_ACTIONED])
def test_autocount_cancel_push_flags_an_acknowledged_row_changed(env, row_state):
    """AC-CL-6 (write site 2): a cancelled AutoCount push flags a live, acknowledged
    row `changed` with `changed_at` set, same as the sales order edit."""
    record, header, line, product_id = _create_then_prep_push(env)
    _mirror, row = _mirror_for_ingest_line(
        env, header["id"], line["id"], product_id, row_state=row_state, row_ack=ACK_ACKNOWLEDGED,
    )

    res2 = env.post(INGEST_SO, [dict(record, status="cancelled")])
    assert res2.status_code == 200, res2.text

    env.db.expire_all()
    row = env.db.get(OrderInquiryRow, row.id)
    updated_core_line = env.so_lines(header["id"])[0]
    assert updated_core_line["line_status"] == "cancelled"
    assert row.ack_state == ACK_CHANGED
    assert row.changed_at is not None


@pytest.mark.parametrize(
    "row_ack,pre_changed_at",
    [(ACK_AWAITING, None), (ACK_CHANGED, datetime(2026, 1, 1)), (ACK_REJECTED, None)],
)
def test_autocount_cancel_push_leaves_non_acknowledged_rows_untouched(env, row_ack, pre_changed_at):
    """AC-CL-6 (write site 2): a row already `awaiting`, `changed` or `rejected` is
    left as it is by the push too."""
    record, header, line, product_id = _create_then_prep_push(env)
    _mirror, row = _mirror_for_ingest_line(
        env, header["id"], line["id"], product_id, row_ack=row_ack, changed_at=pre_changed_at,
    )

    env.post(INGEST_SO, [dict(record, status="cancelled")])

    env.db.expire_all()
    row = env.db.get(OrderInquiryRow, row.id)
    assert row.ack_state == row_ack
    assert row.changed_at == pre_changed_at


def test_autocount_cancel_push_leaves_a_row_whose_own_state_is_cancelled_untouched(env):
    """AC-CL-6 (write site 2): a row whose own state is already `cancelled` is never
    flagged, with a live sibling keeping the line on the cancel path."""
    record, header, line, product_id = _create_then_prep_push(env)
    _mirror, live_row = _mirror_for_ingest_line(
        env, header["id"], line["id"], product_id, row_state=INQUIRY_RAISED, row_ack=ACK_ACKNOWLEDGED,
    )
    dead_row = OrderInquiryRow(
        id=_uid(), order_inquiry_id=live_row.order_inquiry_id,
        so_line_id=live_row.so_line_id, item_code="ZZT-CL-PUSH-DEAD",
        qty=Decimal("3"), delivery_date=live_row.delivery_date, verb=IV_ORDER,
        state=INQUIRY_CANCELLED, ack_state=ACK_ACKNOWLEDGED,
    )
    env.db.add(dead_row)
    env.db.flush()
    env.db.commit()

    env.post(INGEST_SO, [dict(record, status="cancelled")])

    env.db.expire_all()
    dead_row = env.db.get(OrderInquiryRow, dead_row.id)
    assert dead_row.ack_state == ACK_ACKNOWLEDGED
    assert dead_row.changed_at is None


def test_autocount_repeated_cancel_push_does_not_reflag_a_reconfirmed_row(env):
    """AC-CL-7 (write site 2): a second push of the same already-cancelled document
    flags nothing, so a re-confirmed row does not come back."""
    record, header, line, product_id = _create_then_prep_push(env)
    _mirror, row = _mirror_for_ingest_line(
        env, header["id"], line["id"], product_id, row_ack=ACK_ACKNOWLEDGED,
    )

    env.post(INGEST_SO, [dict(record, status="cancelled")])
    env.db.expire_all()
    row = env.db.get(OrderInquiryRow, row.id)
    assert row.ack_state == ACK_CHANGED
    first_changed_at = row.changed_at
    assert first_changed_at is not None

    row.ack_state = ACK_ACKNOWLEDGED
    env.db.flush()
    env.db.commit()

    env.post(INGEST_SO, [dict(record, status="cancelled")])

    env.db.expire_all()
    row = env.db.get(OrderInquiryRow, row.id)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.changed_at == first_changed_at


# ---------------------------------------------------------------------------
# AC-CL-8: the sheet importer's birth state
# ---------------------------------------------------------------------------


def test_sheet_row_onto_an_already_cancelled_line_is_born_awaiting():
    """AC-CL-8: a row the sheet upload raises ONTO an already cancelled line (the
    fallback pass, `_run_pass`'s own R7 rule - only the fallback may take a cancelled
    line) is born `awaiting`, not the importer's ordinary `acknowledged`."""
    with mig_world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", line_status="cancelled")
        data = mig_sheet([
            (order.so_number, w.product.product_code, 30, MIG_D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        assert row.ack_state == ACK_AWAITING


def test_ordinary_sheet_row_is_still_born_acknowledged():
    """AC-CL-8 (control): a row onto an OPEN line is still born acknowledged, exactly
    as the importer's own G4 migration behaviour."""
    with mig_world() as w:
        order = w.order()
        w.line(order, qty_ordered="50")
        data = mig_sheet([
            (order.so_number, w.product.product_code, 30, MIG_D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        assert row.ack_state == ACK_ACKNOWLEDGED


def test_used_row_from_sheet_rebuild_is_born_awaiting():
    """AC-CL-13: the used row the sheet upload rebuilds (AC-RB-1 of the rebuild lane -
    a sheet row exactly restating a `Replaces N used` fresh row's own previous qty/date)
    is born `awaiting` too, not `acknowledged`."""
    with mig_world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="220", required_date=date(2027, 3, 1))
        mirror = _adopted_mirror(w, order, line)
        old_date = date(2026, 6, 1)
        fresh = _used_sibling(
            w, mirror, qty="220", delivery_date=date(2027, 3, 1),
            previous_qty="182", previous_delivery_date=old_date,
            note="Replaces 182 used; SPO-2026/08-0104 received in full",
        )
        data = mig_sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="cl13.xlsx")

        rows = w.rows()
        used = next(r for r in rows if str(r.id) != str(fresh.id))
        assert used.redirected_to_pool is True
        assert used.ack_state == ACK_AWAITING


# ---------------------------------------------------------------------------
# AC-CL-9: Confirm accepts an actioned/cancelled-line row, refuses a cancelled one
# ---------------------------------------------------------------------------


def test_confirm_by_ids_accepts_an_actioned_cancelled_line_row_and_a_raised_one():
    """AC-CL-9 (by ids): an ACTIONED row on a cancelled line and a RAISED one both
    confirm like any other row - `acknowledged`, stamped, state/qty/links untouched,
    `line_cancelled` stays true. No supply seeded, so the cascade has nothing to link.
    A row whose own state is `cancelled` is still refused, 422."""
    with blank_session() as db:
        company_id = _sorento(db)

        product_a = _product(db, f"ZZT-CL9A-{_uid()[:6]}", f"{MARKER} actioned")
        _so_a, line_a, _pso_a, mirror_a = _line_chain(
            db, company_id, product_a, qty="12", line_status="cancelled"
        )
        inquiry_a = _inquiry(db, company_id, mirror_a.project_sales_order_id)
        row_actioned = _oi_row(
            db, company_id, inquiry_a.id, mirror_a.id, product_a.product_code, "12",
            state=INQUIRY_ACTIONED, ack_state=ACK_CHANGED, changed_at=datetime(2026, 9, 1),
        )

        product_b = _product(db, f"ZZT-CL9B-{_uid()[:6]}", f"{MARKER} raised")
        _so_b, line_b, _pso_b, mirror_b = _line_chain(
            db, company_id, product_b, qty="7", line_status="cancelled"
        )
        inquiry_b = _inquiry(db, company_id, mirror_b.project_sales_order_id)
        row_raised = _oi_row(
            db, company_id, inquiry_b.id, mirror_b.id, product_b.product_code, "7",
            state=INQUIRY_RAISED, ack_state=ACK_AWAITING,
        )

        product_c = _product(db, f"ZZT-CL9C-{_uid()[:6]}", f"{MARKER} cancelled-state")
        _so_c, _line_c, _pso_c, mirror_c = _line_chain(
            db, company_id, product_c, qty="5", line_status="cancelled"
        )
        inquiry_c = _inquiry(db, company_id, mirror_c.project_sales_order_id)
        row_state_cancelled = _oi_row(
            db, company_id, inquiry_c.id, mirror_c.id, product_c.product_code, "5",
            state=INQUIRY_CANCELLED, ack_state=ACK_CHANGED, changed_at=datetime(2026, 9, 1),
        )

        buyer_id = _user(db, f"{MARKER} buyer")
        db.commit()

        client, originals = _client(db, buyer_id, [VIEW, ACKNOWLEDGE])
        try:
            with company_scope(db, frozenset({company_id})):
                resp = client.post(
                    ACK_URL,
                    json={"row_ids": [str(row_actioned.id), str(row_raised.id)]},
                )
                assert resp.status_code == 200, resp.text
                body = resp.json()

                resp_cancelled = client.post(
                    ACK_URL, json={"row_ids": [str(row_state_cancelled.id)]}
                )
                assert resp_cancelled.status_code == 422, resp_cancelled.text
        finally:
            _restore(originals)

        assert body["acknowledged"] == 2, body

        db.refresh(row_actioned)
        db.refresh(row_raised)
        db.refresh(line_a)
        db.refresh(line_b)

    assert row_actioned.ack_state == ACK_ACKNOWLEDGED
    assert row_actioned.acknowledged_by == buyer_id
    assert row_actioned.acknowledged_at is not None
    assert row_actioned.state == INQUIRY_ACTIONED
    assert Decimal(str(row_actioned.qty)) == Decimal("12")
    assert row_actioned.redirected_to_pool is False

    assert row_raised.ack_state == ACK_ACKNOWLEDGED
    assert row_raised.acknowledged_by == buyer_id
    assert row_raised.state == INQUIRY_RAISED
    assert Decimal(str(row_raised.qty)) == Decimal("7")

    assert line_a.line_status == "cancelled"
    assert line_b.line_status == "cancelled"


def test_confirm_by_filter_accepts_matching_rows_and_skips_cancelled_state_only_when_asked():
    """AC-CL-9 (by filter): "select all matching" acknowledges the same actioned and
    raised rows; a row whose own state is cancelled is counted in `skipped` only when
    the filter itself asks `state=cancelled` - a broad filter never even shows it."""
    with blank_session() as db:
        company_id = _sorento(db)

        product_a = _product(db, f"ZZT-CL9D-{_uid()[:6]}", f"{MARKER} actioned2")
        _so_a, _line_a, _pso_a, mirror_a = _line_chain(
            db, company_id, product_a, qty="9", line_status="cancelled"
        )
        inquiry_a = _inquiry(db, company_id, mirror_a.project_sales_order_id)
        row_actioned = _oi_row(
            db, company_id, inquiry_a.id, mirror_a.id, product_a.product_code, "9",
            state=INQUIRY_ACTIONED, ack_state=ACK_CHANGED, changed_at=datetime(2026, 9, 1),
        )

        product_b = _product(db, f"ZZT-CL9E-{_uid()[:6]}", f"{MARKER} raised2")
        _so_b, _line_b, _pso_b, mirror_b = _line_chain(
            db, company_id, product_b, qty="4", line_status="cancelled"
        )
        inquiry_b = _inquiry(db, company_id, mirror_b.project_sales_order_id)
        row_raised = _oi_row(
            db, company_id, inquiry_b.id, mirror_b.id, product_b.product_code, "4",
            state=INQUIRY_RAISED, ack_state=ACK_AWAITING,
        )

        product_c = _product(db, f"ZZT-CL9F-{_uid()[:6]}", f"{MARKER} cancelled-state2")
        _so_c, _line_c, _pso_c, mirror_c = _line_chain(
            db, company_id, product_c, qty="6", line_status="cancelled"
        )
        inquiry_c = _inquiry(db, company_id, mirror_c.project_sales_order_id)
        _row_state_cancelled = _oi_row(
            db, company_id, inquiry_c.id, mirror_c.id, product_c.product_code, "6",
            state=INQUIRY_CANCELLED, ack_state=ACK_CHANGED, changed_at=datetime(2026, 9, 1),
        )

        buyer_id = _user(db, f"{MARKER} buyer2")
        db.commit()

        client, originals = _client(db, buyer_id, [VIEW, ACKNOWLEDGE])
        try:
            with company_scope(db, frozenset({company_id})):
                resp = client.post(ACK_URL, json={"filter": {}})
                assert resp.status_code == 200, resp.text
                body = resp.json()

                resp2 = client.post(ACK_URL, json={"filter": {"state": "cancelled"}})
                assert resp2.status_code == 200, resp2.text
                body2 = resp2.json()
        finally:
            _restore(originals)

        db.refresh(row_actioned)
        db.refresh(row_raised)

    assert body["acknowledged"] == 2, body
    assert body["skipped"] == 0, body
    assert row_actioned.ack_state == ACK_ACKNOWLEDGED
    assert row_raised.ack_state == ACK_ACKNOWLEDGED

    assert body2["acknowledged"] == 0, body2
    assert body2["skipped"] == 1, body2


def test_confirm_is_refused_without_the_acknowledge_permission():
    """AC-CL-9: permission stays `projects.order_inquiries.acknowledge`; a user
    without it gets 403."""
    with blank_session() as db:
        company_id = _sorento(db)
        product = _product(db, f"ZZT-CL9G-{_uid()[:6]}", f"{MARKER} noperm")
        _so, _line, _pso, mirror = _line_chain(
            db, company_id, product, qty="3", line_status="cancelled"
        )
        inquiry = _inquiry(db, company_id, mirror.project_sales_order_id)
        row = _oi_row(
            db, company_id, inquiry.id, mirror.id, product.product_code, "3",
            state=INQUIRY_RAISED, ack_state=ACK_AWAITING,
        )
        cs_user = _user(db, f"{MARKER} cs-only")
        db.commit()

        client, originals = _client(db, cs_user, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                resp = client.post(ACK_URL, json={"row_ids": [str(row.id)]})
        finally:
            _restore(originals)

    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# AC-CL-10/14: the backfill migration data pass
# ---------------------------------------------------------------------------


def test_backfill_flags_cancelled_line_and_used_rows_and_is_idempotent():
    """AC-CL-10/AC-CL-14: `backfill_to_confirm(connection, cutoff)` flags every
    acknowledged live row on a cancelled line AND every acknowledged used row -
    `acknowledged_at` NULL or before the cutoff only - leaves awaiting/changed/rejected
    rows, a row whose own state is cancelled, and a row on an open line alone; a second
    run at the same cutoff changes nothing; a row confirmed AFTER the first run
    (`acknowledged_at` later than the cutoff) is never re-flagged."""
    with blank_session() as db:
        company_id = _sorento(db)
        cutoff = datetime(2026, 9, 20, 0, 0, 0)

        def _row(*, ack_state=ACK_ACKNOWLEDGED, state=INQUIRY_RAISED, redirected=False,
                  acknowledged_at=None, line_status="cancelled"):
            product = _product(db, f"ZZT-CLBF-{_uid()[:8]}", f"{MARKER} bf product")
            _so, _line, _pso, mirror = _line_chain(
                db, company_id, product, qty="9", line_status=line_status
            )
            inquiry = _inquiry(db, company_id, mirror.project_sales_order_id)
            return _oi_row(
                db, company_id, inquiry.id, mirror.id, product.product_code, "9",
                state=state, ack_state=ack_state, redirected=redirected,
                acknowledged_at=acknowledged_at,
            )

        row_null_at = _row(acknowledged_at=None)
        row_before = _row(acknowledged_at=cutoff - timedelta(days=1))
        row_after = _row(acknowledged_at=cutoff + timedelta(days=1))
        row_used = _row(acknowledged_at=None, redirected=True, line_status="open")
        row_awaiting = _row(ack_state=ACK_AWAITING)
        row_rejected = _row(ack_state=ACK_REJECTED)
        row_own_cancelled = _row(state=INQUIRY_CANCELLED, acknowledged_at=None)
        row_open_line = _row(acknowledged_at=None, line_status="open")
        db.commit()

        from app.services.oi_cancelled_used_backfill import backfill_to_confirm

        connection = db.connection()

        changed_first = backfill_to_confirm(connection, cutoff=cutoff)
        db.commit()

        for row in (row_null_at, row_before, row_used):
            db.refresh(row)
            assert row.ack_state == ACK_CHANGED, row.id
            assert row.changed_at is not None, row.id

        db.refresh(row_after)
        assert row_after.ack_state == ACK_ACKNOWLEDGED
        assert row_after.changed_at is None

        db.refresh(row_awaiting)
        assert row_awaiting.ack_state == ACK_AWAITING

        db.refresh(row_rejected)
        assert row_rejected.ack_state == ACK_REJECTED

        db.refresh(row_own_cancelled)
        assert row_own_cancelled.ack_state == ACK_ACKNOWLEDGED
        assert row_own_cancelled.changed_at is None

        db.refresh(row_open_line)
        assert row_open_line.ack_state == ACK_ACKNOWLEDGED
        assert row_open_line.changed_at is None

        assert changed_first == 3, changed_first

        changed_second = backfill_to_confirm(connection, cutoff=cutoff)
        db.commit()
        assert changed_second == 0, changed_second
        for row in (row_null_at, row_before, row_used):
            db.refresh(row)
            assert row.ack_state == ACK_CHANGED

        # A row re-confirmed AFTER the first run must not come back on a re-run.
        row_before.ack_state = ACK_ACKNOWLEDGED
        row_before.acknowledged_at = datetime.utcnow()
        db.flush()
        db.commit()

        changed_third = backfill_to_confirm(connection, cutoff=cutoff)
        db.commit()
        db.refresh(row_before)
        assert row_before.ack_state == ACK_ACKNOWLEDGED
        assert changed_third == 0, changed_third


# ---------------------------------------------------------------------------
# AC-CL-11: a flagged row survives the sheet rollback
# ---------------------------------------------------------------------------


def test_ac_cl_11_rollback_keeps_a_changed_at_row_and_reupload_reports_already_raised():
    """AC-CL-11: a row this lane flags (`changed_at` set) survives the rollback guard
    (AC-RB-17's own `changed_at` trait) and a re-upload of the same file reports it
    `already_raised`, never raised a second time - asserted, not assumed."""
    with rebuild_world() as w:
        order, _line, kept = _stamped_row(w, file_name="cl11.xlsx", trait="changed_at")
        kept_id = str(kept.id)

        counts = _rollback().run(w.db, file_name="cl11.xlsx", apply=True)
        assert counts.get("kept") == 1, counts
        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == kept_id
        ).count() == 1

        capture = _Capture()
        _apply(
            w,
            mig_sheet([
                (order.so_number, w.product.product_code, 30, MIG_D_OCT,
                 w.warehouse.warehouse_code, ""),
            ]),
            file_name="cl11.xlsx",
            outcome=capture,
        )
        assert oc.ALREADY_RAISED in capture.codes(), capture.calls


# ---------------------------------------------------------------------------
# AC-CL-12/15: a row becomes used (`_redirect_row_if_received`)
# ---------------------------------------------------------------------------


def _used_row_fixture(api, *, ack_first: bool):
    _client, world_ = api
    fixture = _raise_one_row(api, qty="182")
    row = fixture["row"]
    if ack_first:
        with _as_purchasing(world_) as buyer:
            resp = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
            assert resp.status_code == 200, resp.text
        world_.db.commit()
        world_.db.refresh(row)
        assert row.ack_state == ACK_ACKNOWLEDGED
    allocation = _received_spo(world_, qty="182")
    _link_row_to(world_, row, qty="182", document=allocation.spo_number, allocation=allocation)
    world_.db.refresh(row)
    _settle(world_, fixture, qty="220", required_date=date(2027, 3, 1))
    world_.db.refresh(row)
    assert row.redirected_to_pool is True
    return world_, row, fixture


def test_settle_flags_an_acknowledged_row_used_changed(api):
    """AC-CL-12: a replan that turns a row into a used row
    (`_redirect_row_if_received`) sets that row `changed` with `changed_at` when it was
    `acknowledged`."""
    _world_, row, _fixture = _used_row_fixture(api, ack_first=True)
    assert row.ack_state == ACK_CHANGED
    assert row.changed_at is not None


def test_settle_leaves_an_awaiting_row_used_awaiting(api):
    """AC-CL-12 (control): a row nobody has acknowledged yet stays `awaiting` when it
    becomes used - there is nothing new for purchasing to be told."""
    _world_, row, _fixture = _used_row_fixture(api, ack_first=False)
    assert row.ack_state == ACK_AWAITING
    assert row.changed_at is None


def test_confirming_a_used_row_moves_no_link_and_draws_no_new_one(api):
    """AC-CL-15: a used row in To confirm is confirmed by the same route; its links
    are IDENTICAL before and after, and no new link lands on it even with ample open
    supply for its own product sitting there - a used row is never linkable."""
    world_, row, fixture = _used_row_fixture(api, ack_first=False)
    assert row.ack_state == ACK_AWAITING  # already "To confirm" today
    before_links = sorted(str(l.id) for l in _links_of(world_, row))

    _open_po_line(world_, qty=999, product=world_.product)

    with _as_purchasing(world_) as buyer:
        resp = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
    assert resp.status_code == 200, resp.text
    world_.db.commit()
    world_.db.refresh(row)

    assert row.ack_state == ACK_ACKNOWLEDGED
    after_links = sorted(str(l.id) for l in _links_of(world_, row))
    assert after_links == before_links


# ---------------------------------------------------------------------------
# AC-CL-18: the whole journey
# ---------------------------------------------------------------------------


def test_ac_cl_18_whole_journey_upload_ack_cancel_read_confirm_read_repush():
    """AC-CL-18: upload a sheet row, acknowledge, cancel its line through the sales
    order edit, read the worklist (row `line_cancelled`, in To confirm, out of Buy),
    confirm, read again (out of To confirm, still listed, still `line_cancelled`), push
    the same cancellation again (still out of To confirm)."""
    from app.schemas.scm_orders import SalesOrderUpdate
    from app.services.scm.sales_order_service import SalesOrderService

    with mig_world() as w:
        order = w.order()
        w.line(order, qty_ordered="30")
        data = mig_sheet([
            (order.so_number, w.product.product_code, 30, MIG_D_OCT,
             w.warehouse.warehouse_code, ""),
        ])
        result = w.apply(data)
        assert result["rows_raised"] == 1, result
        w.db.commit()
        row = w.one_row()
        # The sheet importer's own birth state (AC-CL-8's control): already
        # acknowledged, a migration of instructions purchasing has been working from.
        # "Acknowledge" still runs here as the journey's own step - tolerant of an
        # already-acknowledged row, a genuine no-op (AC-H2's own guard).
        assert row.ack_state == ACK_ACKNOWLEDGED

        buyer_id = _user(w.db, f"{MARKER} journey buyer")
        client, originals = _client(w.db, buyer_id, [VIEW, ACKNOWLEDGE])
        try:
            resp = client.post(ACK_URL, json={"row_ids": [str(row.id)]})
            assert resp.status_code == 200, resp.text
            w.db.commit()
            w.db.refresh(row)
            assert row.ack_state == ACK_ACKNOWLEDGED

            SalesOrderService(w.db).update(order.id, SalesOrderUpdate(lines=[]), user_id=None)
            w.db.expire_all()

            listed = client.get(LIST, params={"limit": 200}).json()
            found = next(r for r in listed["data"] if r["id"] == str(row.id))
            assert found["line_cancelled"] is True, found

            to_confirm = client.get(LIST, params={"ack": "to_confirm", "limit": 200}).json()
            assert str(row.id) in {r["id"] for r in to_confirm["data"]}, to_confirm["data"]

            buy = client.get(LIST, params={"kind": "buy", "limit": 200}).json()
            assert str(row.id) not in {r["id"] for r in buy["data"]}, buy["data"]

            confirm = client.post(ACK_URL, json={"row_ids": [str(row.id)]})
            assert confirm.status_code == 200, confirm.text
            w.db.commit()
            w.db.refresh(row)
            assert row.ack_state == ACK_ACKNOWLEDGED

            to_confirm_after = client.get(
                LIST, params={"ack": "to_confirm", "limit": 200}
            ).json()
            assert str(row.id) not in {r["id"] for r in to_confirm_after["data"]}

            still_listed = client.get(LIST, params={"limit": 200}).json()
            found_after = next(r for r in still_listed["data"] if r["id"] == str(row.id))
            assert found_after["line_cancelled"] is True

            SalesOrderService(w.db).update(order.id, SalesOrderUpdate(lines=[]), user_id=None)
            w.db.expire_all()

            to_confirm_again = client.get(
                LIST, params={"ack": "to_confirm", "limit": 200}
            ).json()
            assert str(row.id) not in {r["id"] for r in to_confirm_again["data"]}
        finally:
            _restore(originals)
