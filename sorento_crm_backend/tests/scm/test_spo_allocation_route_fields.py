"""What `GET /procurement/spo-allocations` says about an imported shipping order.

Two things this pins, and both have burned this codebase before.

**`response_model` silently drops a field the schema does not declare.** The SPO document's
own columns - `location_code`, `line_status`, `expected_date` - reach the row and would
reach nothing else, so the screen would show a location we do hold as blank and every
imported line as though it were open.

**The GRN-computed receipt must not overwrite a stated one.** The listing recomputes
`quantity_received` from approved GRN lines, which is right for a row this system raised and
wrong for 74,016 lines of 2020-2023 history that arrived stating their own: recomputing
those returns 0, and three years of delivered purchases would read as outstanding.

Runs on the shared database inside the `scm_app` savepoint, because it is a WIRE test: the
route, its `response_model` and the service, exactly as they are mounted.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTSPOAPI"


def _client(scm_app, role_slug="purchasing"):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
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
        **extra,
    }
    db.execute(text(
        "INSERT INTO spo_allocations (id, spo_number, spo_line_number, product_id, "
        "warehouse_id, location_code, allocated_quantity, quantity_received, "
        "receipt_status, line_status, source_system, expected_date, created_at) "
        "VALUES (:id, :spo_number, :spo_line_number, :product_id, :warehouse_id, "
        ":location_code, :allocated_quantity, :quantity_received, :receipt_status, "
        ":line_status, :source_system, :expected_date, now())"
    ), columns)
    db.flush()
    return aid


def _row(client, spo_number: str) -> dict:
    response = client.get(
        "/api/v1/procurement/spo-allocations/", params={"query": spo_number, "limit": 50}
    )
    assert response.status_code == 200, response.text
    rows = [r for r in response.json()["data"] if r["spo_number"] == spo_number]
    assert len(rows) == 1, rows
    return rows[0]


def test_the_documents_own_columns_reach_the_response(scm_app):
    app, db = _client(scm_app)
    product_id = _product(db)
    spo_number = f"SPO-2026/08-{uuid.uuid4().hex[:6]}"
    _allocation(db, product_id, spo_number=spo_number)

    row = _row(TestClient(app), spo_number)

    assert row["location_code"] == f"{MARKER}-RESERVE"
    assert row["line_status"] == "closed"
    assert row["expected_date"] == (date.today() + timedelta(days=10)).isoformat()
    assert row["source_system"] == "scm_spo_history"
    # The two that became nullable: a document with no container and no location we hold.
    assert row["warehouse_id"] is None
    assert row["inbound_shipment_id"] is None


def test_an_imported_row_keeps_the_receipt_it_states(scm_app):
    app, db = _client(scm_app)
    product_id = _product(db)
    spo_number = f"SPO-2026/08-{uuid.uuid4().hex[:6]}"
    _allocation(db, product_id, spo_number=spo_number)

    row = _row(TestClient(app), spo_number)

    assert row["quantity_received"] == 12
    assert row["receipt_status"] == "fully_received"
