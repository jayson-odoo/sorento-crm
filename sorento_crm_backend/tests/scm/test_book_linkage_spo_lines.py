"""Slice B of `PLAN-scm-book-linkage-on-document-lines.md` - the AutoCount book's own
source purchase order, on the SPO document's Lines tab.

Every AC in `scm-book-linkage-on-document-lines-acceptance-criteria.md`'s "Slice B" and
"Both" sections is named in the test that covers it. `scm_app` (savepoint-per-test,
rolled back) with every row behind the `ZZTBOOKSPO` marker.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, grant_permission, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTBOOKSPO"


def _client(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    # The SPO documents route is behind `require_permission("procurement.spo_allocations.view")`,
    # and NO migration grants that slug to any role - the local prod-copy database only
    # passes because a human granted it there (to `purchasing_manager` and
    # `purchasing_executive`, never to plain `purchasing`). On CI's freshly migrated,
    # dataless database nobody holds it, so every call here returned 403. Granted
    # explicitly inside the savepoint so the test asserts the ROUTE, not the grant table
    # of whichever database it happens to run against.
    grant_permission(db, role_slug, "procurement.spo_allocations.view")
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


def _po_line(db, product_id: str, *, po_number: str) -> str:
    """A real CRM `purchase_order_lines` row, for the `po_line_id` half of AC-B4."""
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
    return line_id


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


def _document_line(client, spo_number: str) -> dict:
    response = client.get(f"/api/v1/procurement/spo-allocations/documents/{spo_number}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["lines"]) == 1, body["lines"]
    return body["lines"][0]


def test_a_line_with_from_po_number_prints_it(scm_app):
    """AC-B1."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-B1-{uuid.uuid4().hex[:8]}"
    _allocation(db, pid, spo_number=spo_number, from_po_number="PO-2020/01-0099")

    with TestClient(app) as c:
        line = _document_line(c, spo_number)
    assert line["from_po_number"] == "PO-2020/01-0099"


def test_a_line_without_one_prints_nothing(scm_app):
    """AC-B2 - the frontend's muted dash, not a guess."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-B2-{uuid.uuid4().hex[:8]}"
    _allocation(db, pid, spo_number=spo_number)

    with TestClient(app) as c:
        line = _document_line(c, spo_number)
    assert line["from_po_number"] is None


def test_the_existing_po_column_is_untouched(scm_app):
    """AC-B3 - same id, same link behaviour, same meaning, still built from
    `po_line_id` alone."""
    app, db = _client(scm_app)
    pid = _product(db)
    po_number = f"{MARKER}-B3-PO-{uuid.uuid4().hex[:8]}"
    po_line_id = _po_line(db, pid, po_number=po_number)
    spo_number = f"{MARKER}-B3-{uuid.uuid4().hex[:8]}"
    # No `from_po_number` on this row - `po` must still resolve from `po_line_id` alone.
    _allocation(db, pid, spo_number=spo_number, po_line_id=po_line_id)

    with TestClient(app) as c:
        line = _document_line(c, spo_number)
    assert line["po"]["po_number"] == po_number
    assert line["from_po_number"] is None


def test_po_and_from_po_number_can_disagree_without_either_being_wrong(scm_app):
    """AC-B4 - the whole point of the plan. `po_line_id` names a CRM line, and
    `from_po_number` names a DIFFERENT AutoCount document; both are correct answers to
    two different questions."""
    app, db = _client(scm_app)
    pid = _product(db)
    crm_po_number = f"{MARKER}-B4-CRM-{uuid.uuid4().hex[:8]}"
    po_line_id = _po_line(db, pid, po_number=crm_po_number)
    spo_number = f"{MARKER}-B4-{uuid.uuid4().hex[:8]}"
    _allocation(
        db, pid, spo_number=spo_number, po_line_id=po_line_id,
        from_po_number="PO-2019/11-0007",
    )

    with TestClient(app) as c:
        line = _document_line(c, spo_number)
    assert line["po"]["po_number"] == crm_po_number
    assert line["from_po_number"] == "PO-2019/11-0007"
    assert line["po"]["po_number"] != line["from_po_number"]


def test_from_po_line_ref_is_never_printed(scm_app):
    """AC-B5 - server-side only, a resolver key, never a thing to print."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-B5-{uuid.uuid4().hex[:8]}"
    _allocation(
        db, pid, spo_number=spo_number, from_po_number="PO-2020/02-0011",
        from_po_line_ref="DTL-99887",
    )

    with TestClient(app) as c:
        line = _document_line(c, spo_number)
    assert "from_po_line_ref" not in line


def test_so_covered_is_unchanged(scm_app):
    """AC-B6 - present and still its own field, unaffected by the new column."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-B6-{uuid.uuid4().hex[:8]}"
    _allocation(db, pid, spo_number=spo_number)

    with TestClient(app) as c:
        line = _document_line(c, spo_number)
    assert line["so_covered"] == []


def test_response_model_does_not_drop_from_po_number_at_the_http_surface(scm_app):
    """AC-C2 - asserted through the ROUTE, not only the service. `response_model` has
    silently dropped an undeclared field here before."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-C2-{uuid.uuid4().hex[:8]}"
    _allocation(db, pid, spo_number=spo_number, from_po_number="PO-2021/03-0044")

    with TestClient(app) as c:
        response = c.get(f"/api/v1/procurement/spo-allocations/documents/{spo_number}")
    assert response.status_code == 200, response.text
    line = response.json()["lines"][0]
    assert "from_po_number" in line, "response_model dropped the new field on the wire"
    assert line["from_po_number"] == "PO-2021/03-0044"


def test_no_uuid_reaches_the_from_po_number_cell(scm_app):
    """AC-C3."""
    app, db = _client(scm_app)
    pid = _product(db)
    spo_number = f"{MARKER}-C3-{uuid.uuid4().hex[:8]}"
    _allocation(db, pid, spo_number=spo_number, from_po_number="PO-2020/05-0002")

    with TestClient(app) as c:
        line = _document_line(c, spo_number)
    try:
        uuid.UUID(str(line["from_po_number"]))
        is_uuid = True
    except (ValueError, AttributeError):
        is_uuid = False
    assert not is_uuid
