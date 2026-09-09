"""Slice C of `PLAN-scm-oi-reserving-feedback-8sep.md` - `source_po_number` at the HTTP
surface.

The service layer (`OrderInquiryWorklistService.get_spo_detail`,
`ProjectOrderInquiryService.links_for_rows`) already emits the field correctly. Both HTTP
routes declare a `response_model` that never named it, so FastAPI silently stripped it on
the wire - the documented lesson ("`response_model` silently drops undeclared fields.
Assert the field in a test."). Every test below goes through a `TestClient`, never the
service directly, because the response_model boundary is the whole point.

`scm_app` (savepoint-per-test, rolled back) with every row behind the `ZZTOISRC` marker.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.project_so import (
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from tests.scm.conftest import as_user, grant_permission, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTOISRC"

BASE = "/api/v1/project-sales"
LIST = f"{BASE}/order-inquiries"
VIEW = "projects.projects.view"


def _client(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    # `projects.projects.view` gates both routes under test. No migration grants it to any
    # role, so CI's dataless database returns 403 for every call without this - see
    # `grant_permission`'s own docstring.
    grant_permission(db, role_slug, VIEW)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _product(db) -> str:
    cat, uom, pid = (str(uuid.uuid4()) for _ in range(3))
    db.execute(text("INSERT INTO product_categories (id, category_code, category_name) "
                    "VALUES (:id, :c, :c)"), {"id": cat, "c": f"{MARKER}-CAT-{cat[:8]}"})
    db.execute(text("INSERT INTO units_of_measure (id, uom_code, uom_name) "
                    "VALUES (:id, :c, :c)"), {"id": uom, "c": f"{MARKER}U{uom[:8]}"})
    db.execute(text(
        "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, "
        "list_price, is_active, is_discontinued, created_at, updated_at) "
        "VALUES (:id, :code, :code, :cat, :uom, 10, true, false, now(), now())"
    ), {"id": pid, "code": f"{MARKER}-P-{pid[:8]}", "cat": cat, "uom": uom})
    return pid


def _po_line(db, product_id: str, *, po_number: str) -> tuple[str, str]:
    """A real CRM `purchase_order_lines` row. Returns (purchase_order_id, line_id)."""
    po_id, line_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency) "
        "VALUES (:i, :n, 'active', :d, 'MYR')"
    ), {"i": po_id, "n": po_number, "d": date(2026, 8, 1)})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
        "qty_ordered, qty_received, line_status) "
        "VALUES (:i, :po, :p, 10, 0, 'open')"
    ), {"i": line_id, "po": po_id, "p": product_id})
    db.flush()
    return po_id, line_id


def _allocation(db, product_id: str, *, spo_number: str, **extra) -> str:
    aid = str(uuid.uuid4())
    columns = {
        "id": aid,
        "spo_number": spo_number,
        "spo_line_number": 1,
        "product_id": product_id,
        "warehouse_id": None,
        "location_code": f"{MARKER}-RESERVE",
        "allocated_quantity": 12,
        "quantity_received": 12,
        "receipt_status": "fully_received",
        "line_status": "closed",
        "source_system": "scm_spo_history",
        "expected_date": date.today() + timedelta(days=10),
        "po_line_id": None,
        "from_po_number": None,
        **extra,
    }
    db.execute(text(
        "INSERT INTO spo_allocations (id, spo_number, spo_line_number, product_id, "
        "warehouse_id, location_code, allocated_quantity, quantity_received, "
        "receipt_status, line_status, source_system, expected_date, po_line_id, "
        "from_po_number, created_at) "
        "VALUES (:id, :spo_number, :spo_line_number, :product_id, :warehouse_id, "
        ":location_code, :allocated_quantity, :quantity_received, :receipt_status, "
        ":line_status, :source_system, :expected_date, :po_line_id, :from_po_number, now())"
    ), columns)
    db.flush()
    return aid


def _worklist_row(db, *, qty: str = "10") -> tuple[OrderInquiryRow, str]:
    """One purchasing instruction on a project-less ('adopted') order, so no project
    registration chain is needed - `_base`'s only INNER joins are to the inquiry and its
    own sales order, everything else (project, core order, supplier...) is OUTER."""
    pid = _product(db)
    order = ProjectSalesOrder(
        id=str(uuid.uuid4()),
        project_id=None,
        provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        autocount_doc_no=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        status="adopted",
    )
    db.add(order)
    db.flush()
    line = ProjectSalesOrderLine(
        id=str(uuid.uuid4()),
        project_sales_order_id=order.id,
        line_no=1,
        product_id=pid,
        description=f"{MARKER} line",
        qty=Decimal(qty),
        uom="UNIT",
        delivery_date=date(2026, 6, 1),
    )
    db.add(line)
    db.flush()
    inquiry = OrderInquiry(
        id=str(uuid.uuid4()),
        project_sales_order_id=order.id,
        state=INQUIRY_RAISED,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=str(uuid.uuid4()),
        order_inquiry_id=inquiry.id,
        so_line_id=line.id,
        item_code=f"{MARKER}-ITEM-{uuid.uuid4().hex[:6]}",
        qty=Decimal(qty),
        verb=IV_ORDER,
        state=INQUIRY_RAISED,
        delivery_date=date(2026, 6, 1),
    )
    db.add(row)
    db.flush()
    return row, pid


def _spo_link(db, row: OrderInquiryRow, spo_allocation_id: str, *, qty: str = "10") -> None:
    db.add(
        OrderInquiryLink(
            id=str(uuid.uuid4()),
            row_id=row.id,
            spo_allocation_id=spo_allocation_id,
            qty=Decimal(qty),
        )
    )
    db.flush()


def _po_link(db, row: OrderInquiryRow, po_line_id: str, *, qty: str = "10") -> None:
    db.add(
        OrderInquiryLink(
            id=str(uuid.uuid4()),
            row_id=row.id,
            po_line_id=po_line_id,
            qty=Decimal(qty),
        )
    )
    db.flush()


def _spo_detail(client, spo_number: str) -> dict:
    response = client.get(f"{LIST}/spo/{spo_number}")
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------ AC-C1 / AC-C3 / AC-C4: SPO detail


def test_a_spo_detail_line_with_from_po_number_prints_it_as_source_po_number(scm_app):
    """AC-C1."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-C1-{uuid.uuid4().hex[:8]}"
    _allocation(db, pid, spo_number=spo_number, from_po_number="PO-2020/01-0099")

    with TestClient(app) as c:
        detail = _spo_detail(c, spo_number)
    assert len(detail["lines"]) == 1, detail["lines"]
    assert detail["lines"][0]["source_po_number"] == "PO-2020/01-0099"


def test_a_spo_detail_line_with_no_from_po_number_is_null_not_a_guess(scm_app):
    """AC-C3."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-C3-{uuid.uuid4().hex[:8]}"
    _allocation(db, pid, spo_number=spo_number, from_po_number=None)

    with TestClient(app) as c:
        detail = _spo_detail(c, spo_number)
    assert detail["lines"][0]["source_po_number"] is None


def test_from_po_line_ref_never_appears_anywhere_in_the_spo_detail_response(scm_app):
    """AC-C4 - a resolver key, never a thing a buyer reads, on either surface."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-C4-{uuid.uuid4().hex[:8]}"
    _allocation(
        db, pid, spo_number=spo_number, from_po_number="PO-2020/02-0011",
        from_po_line_ref="DTL-99887-DISTINCTIVE",
    )

    with TestClient(app) as c:
        response = c.get(f"{LIST}/spo/{spo_number}")
    assert response.status_code == 200, response.text
    assert "DTL-99887-DISTINCTIVE" not in response.text
    assert "from_po_line_ref" not in response.text


def test_response_model_does_not_drop_source_po_number_on_the_spo_detail(scm_app):
    """The regression this ticket exists for: `OrderInquirySpoDetailLine` never declared
    `source_po_number`, so `response_model` silently stripped it at this route."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-REG1-{uuid.uuid4().hex[:8]}"
    _allocation(db, pid, spo_number=spo_number, from_po_number="PO-2021/03-0044")

    with TestClient(app) as c:
        response = c.get(f"{LIST}/spo/{spo_number}")
    assert response.status_code == 200, response.text
    line = response.json()["lines"][0]
    assert "source_po_number" in line, "response_model dropped the new field on the wire"
    assert line["source_po_number"] == "PO-2021/03-0044"


# --------------------------------------------------------- AC-C5: worklist links


def test_an_spo_link_with_from_po_number_prints_it_on_the_worklist_link(scm_app):
    """AC-C5, surface 1 - `OrderInquiryWorklistRow.links[].source_po_number`."""
    app, db = _client(scm_app)
    row, pid = _worklist_row(db)
    spo_number = f"{MARKER}-C5A-{uuid.uuid4().hex[:8]}"
    allocation_id = _allocation(
        db, pid, spo_number=spo_number, from_po_number="PO-2019/11-0007"
    )
    _spo_link(db, row, allocation_id)
    db.commit()

    with TestClient(app) as c:
        response = c.get(LIST)
    assert response.status_code == 200, response.text
    body = {r["id"]: r for r in response.json()["data"]}
    link = body[row.id]["links"][0]
    assert link["kind"] == "spo"
    assert link["source_po_number"] == "PO-2019/11-0007"


def test_a_po_kind_link_still_resolves_po_id_and_reports_source_po_number_as_null(scm_app):
    """AC-C5 and "the existing CRM `po` column is untouched" together: a plain PO link's
    own `po_id` still addresses the PO popover exactly as before this slice, and
    `source_po_number` answers a different question it has nothing to say about - a link
    to a purchase order names no AutoCount source document, because it already IS one."""
    app, db = _client(scm_app)
    row, pid = _worklist_row(db)
    po_number = f"{MARKER}-C5B-PO-{uuid.uuid4().hex[:8]}"
    po_id, po_line_id = _po_line(db, pid, po_number=po_number)
    _po_link(db, row, po_line_id)
    db.commit()

    with TestClient(app) as c:
        response = c.get(LIST)
    assert response.status_code == 200, response.text
    body = {r["id"]: r for r in response.json()["data"]}
    link = body[row.id]["links"][0]
    assert link["kind"] == "po"
    assert link["po_id"] == po_id
    assert link["source_po_number"] is None


def test_an_spo_links_po_id_is_null_and_independent_of_source_po_number(scm_app):
    """The other half of the same pair, on an SPO-kind link: `po_id` stays null (there is
    no purchase order THIS link addresses - `po_id`'s own docstring), while
    `source_po_number` carries the book's plain-text statement. The two never conflate."""
    app, db = _client(scm_app)
    row, pid = _worklist_row(db)
    spo_number = f"{MARKER}-C5C-{uuid.uuid4().hex[:8]}"
    allocation_id = _allocation(
        db, pid, spo_number=spo_number, from_po_number="PO-2018/07-0003",
    )
    _spo_link(db, row, allocation_id)
    db.commit()

    with TestClient(app) as c:
        response = c.get(LIST)
    assert response.status_code == 200, response.text
    body = {r["id"]: r for r in response.json()["data"]}
    link = body[row.id]["links"][0]
    assert link["kind"] == "spo"
    assert link["po_id"] is None
    assert link["source_po_number"] == "PO-2018/07-0003"


def test_response_model_does_not_drop_source_po_number_on_the_worklist_links(scm_app):
    """The regression this ticket exists for, on the second surface:
    `OrderInquiryLinkOut` (shared by the worklist AND the per-project rows) never declared
    `source_po_number`, so `response_model` silently stripped it here too."""
    app, db = _client(scm_app)
    row, pid = _worklist_row(db)
    spo_number = f"{MARKER}-REG2-{uuid.uuid4().hex[:8]}"
    allocation_id = _allocation(
        db, pid, spo_number=spo_number, from_po_number="PO-2022/09-0055"
    )
    _spo_link(db, row, allocation_id)
    db.commit()

    with TestClient(app) as c:
        response = c.get(LIST)
    assert response.status_code == 200, response.text
    body = {r["id"]: r for r in response.json()["data"]}
    link = body[row.id]["links"][0]
    assert "source_po_number" in link, "response_model dropped the new field on the wire"
    assert link["source_po_number"] == "PO-2022/09-0055"
