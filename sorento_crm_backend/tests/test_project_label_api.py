"""API surface for `project_label`/`project_label_source` (PLAN-so-project-label.md).

  AC-A1  GET SO detail declares both fields on the response model (presence, not truthiness -
         `response_model` silently drops an undeclared field)
  AC-A2  the list returns `project_label` per row and `query` matches it
  AC-A3  the fulfilment board's row reads the column first, the note second

Postgres. A1/A2 use `scm_app`'s own rolled-back savepoint against the REAL database (the SCM
M1 route fixtures, `tests/scm/conftest.py`) - so a pre-existing label has to be seeded with
raw SQL, and the real table does not carry the column yet even though the ORM model now maps
it. A3 uses `blank_session` (the board's own substrate, see `test_board_order_inquiry.py`),
which builds its scratch schema fresh from the current models each run and so already has
both columns - a red there names a genuine gap in the board's own read, not a missing column.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests.scm.conftest import as_user, requires_pg, scm_app, seed_user  # noqa: F401

from ._pg_fixture import blank_session, unique_code

pytestmark = requires_pg

MARKER = "ZZTPLAPI"


def _uid() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{_uid()[:8]}".upper()


def _seed_order(scm_app, *, label=None, source=None):
    app, db, gcu, gcuak = scm_app
    as_user(app, gcu, gcuak, seed_user(db, "purchasing"))

    uom = UnitOfMeasure(id=_uid(), uom_code=_code("UOM")[:20], uom_name="Pieces")
    category = ProductCategory(
        id=_uid(), category_code=_code("CAT"), category_name=f"{MARKER} category"
    )
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(), product_code=_code("SKU"), product_name=f"{MARKER} basin",
        category_id=category.id, base_uom_id=uom.id, list_price=100,
    )
    customer = Customer(
        id=_uid(), customer_code=_code("CUS"), customer_name=f"{MARKER} Kitchens Sdn Bhd",
        is_active=True,
    )
    warehouse = Warehouse(
        id=_uid(), warehouse_code=_code("WH")[:20], warehouse_name=f"{MARKER} store",
        is_active=True,
    )
    db.add_all([product, customer, warehouse])
    db.flush()
    so = SalesOrder(
        id=_uid(), so_number=_code("SO"), customer_id=customer.id, status="open",
        priority="normal", order_date=date(2026, 7, 16), source_system="scm_upload",
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_uid(), sales_order_id=so.id, product_id=product.id, warehouse_id=warehouse.id,
        qty_ordered=10, qty_delivered=0, line_status="open",
    ))
    db.flush()
    if label is not None:
        # Raw SQL: the real table does not carry `project_label` yet even though the ORM
        # model does, so this is where the red shows up until migration 511 is applied
        # there (the same real-database gap `test_migration_511...` and
        # `test_project_label_order_inquiry_import.py` hit).
        db.execute(
            text(
                "UPDATE sales_orders SET project_label = :label, "
                "project_label_source = :source WHERE id = :id"
            ),
            {"label": label, "source": source, "id": so.id},
        )
        db.flush()
    return app, db, so


def test_a1_the_detail_response_declares_project_label_and_its_source(scm_app):
    app, db, so = _seed_order(scm_app, label="BAMBOO RESIDENCE / KUALA LUMPUR", source="inquiry")

    with TestClient(app) as c:
        res = c.get(f"/api/v1/scm/sales-orders/{so.id}")

    assert res.status_code == 200, res.text
    body = res.json()
    # Presence, not just truthiness: `response_model` silently drops an undeclared field.
    assert "project_label" in body
    assert "project_label_source" in body
    assert body["project_label"] == "BAMBOO RESIDENCE / KUALA LUMPUR"
    assert body["project_label_source"] == "inquiry"


def test_a2_the_list_returns_project_label_and_query_finds_it(scm_app):
    app, db, so = _seed_order(scm_app, label="BAMBOO RESIDENCE / KUALA LUMPUR", source="inquiry")

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders", params={"query": "BAMBOO"})

    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    match = next((r for r in rows if r["id"] == str(so.id)), None)
    assert match is not None, "query=BAMBOO must find the order by its project label"
    assert match["project_label"] == "BAMBOO RESIDENCE / KUALA LUMPUR"


# ------------------------------------------------------------------ AC-A3, the board


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def test_a3_the_board_row_reads_the_column_before_falling_back_to_the_note():
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    with blank_session() as db:
        _sorento(db)
        uom = UnitOfMeasure(id=_uid(), uom_code=unique_code(MARKER)[:12], uom_name="Unit")
        category = ProductCategory(
            id=_uid(), category_code=unique_code(MARKER), category_name=f"{MARKER} cat"
        )
        db.add_all([uom, category])
        db.flush()
        product = Product(
            id=_uid(), product_code=unique_code(MARKER), product_name=f"{MARKER} product",
            category_id=category.id, base_uom_id=uom.id, list_price=100,
        )
        db.add(product)
        warehouse = Warehouse(
            id=_uid(), warehouse_code=unique_code(MARKER)[:12], warehouse_name=f"{MARKER} wh",
            is_active=True, segment="project", fulfilment_planning=True,
        )
        db.add(warehouse)
        db.flush()
        order = SalesOrder(
            id=_uid(), so_number=unique_code(f"{MARKER}-SO"), order_date=date(2026, 1, 1),
            demand_class="project", status="open",
            # The column names one project; the note names a DIFFERENT one, so the
            # assertion below can only pass if the column is read FIRST.
            project_label="COLUMN LABEL",
            internal_note="***PROJECT : NOTE LABEL",
        )
        db.add(order)
        db.flush()
        db.add(SalesOrderLine(
            id=_uid(), sales_order_id=order.id, product_id=product.id,
            warehouse_id=warehouse.id, qty_ordered=10, qty_delivered=0,
            required_date=date(2026, 9, 3), line_status="open",
            purchasing_status="not_reviewed",
        ))
        db.flush()

        board = FulfilmentBoardService(db).build(
            [order.so_number], granularity="week", as_of=date(2026, 8, 19)
        )

        cell = next(c for c in board["cells"] if c["item_code"] == product.product_code)
        assert cell["contributions"][0]["project_label"] == "COLUMN LABEL"
