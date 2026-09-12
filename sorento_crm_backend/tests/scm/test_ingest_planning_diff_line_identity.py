"""Slice A review round, R-S1 (`documentation/plans/scm/PLAN-scm-change-management-one
-engine.md`): `DocumentIngestService._capture_planning_diff_before` /
`_capture_planning_diff_after` (`app/services/document_ingest_service.py`, ~1105-1155)
build `outstanding_diff.Line` objects with `row_ref=str(row.id)` but no `line_id` - the
ESB/AutoCount ingest trigger therefore never gets the line-identity pairing Slice A's rule
5 gives the manual-edit and book-upload triggers, so a product swap arriving through
`document_ingest_service` still reads as a `closed` plus an unrelated `added` instead of one
`product_changed` row.

Smallest unit that reaches these two methods: constructed directly (no route, no full
`ingest()` batch, no parsed `DocumentPayload`) - `DocumentIngestService.__init__` needs only
`db` + `company_id` (see its own docstring: "same constructor... interchangeable"), and both
methods read only `header.id` and `payload.so_number` off their arguments, so a bare
`SimpleNamespace(so_number=...)` stands in for the payload. `tests/test_ingest_documents_v2
_hooks.py` builds the same service through the full route/spec machinery for a different
purpose and has pre-existing failures unrelated to this slice - not depended on here.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import text

from app.models.base import company_scope
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.document_ingest_service import DocumentIngestService
from tests._pg_fixture import blank_session

MARKER = "zzt-ingestlineid"


def _uid() -> str:
    return str(uuid.uuid4())


def test_ingest_capture_carries_line_ids():
    with blank_session() as db:
        company_id = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        with company_scope(db, frozenset({company_id})):
            uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Set")
            category = ProductCategory(
                id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat",
            )
            db.add_all([uom, category])
            db.flush()
            product = Product(
                id=_uid(), product_code=f"ZZT-{_uid()[:8]}", product_name=f"{MARKER} Basin",
                category_id=category.id, base_uom_id=uom.id, list_price=Decimal("120.00"),
            )
            warehouse = Warehouse(
                id=_uid(), warehouse_code=f"ZZT-WH-{_uid()[:4]}", warehouse_name="ZZT wh",
                location="ZZT", is_active=True, fulfilment_planning=True,
            )
            db.add_all([product, warehouse])
            db.flush()

            so = SalesOrder(
                id=_uid(), company_id=company_id, so_number=f"ZZT-INGEST-{_uid()[:8]}",
                status="open", demand_class="project",
            )
            db.add(so)
            db.flush()
            line = SalesOrderLine(
                id=_uid(), company_id=company_id, sales_order_id=so.id, product_id=product.id,
                warehouse_id=warehouse.id, qty_ordered=Decimal("72"), qty_delivered=Decimal("0"),
                required_date=date(2026, 8, 20), line_status="open",
            )
            db.add(line)
            db.commit()

            svc = DocumentIngestService(db, None, company_id=company_id)
            payload = SimpleNamespace(so_number=so.so_number)

            svc._capture_planning_diff_before(so, payload)
            svc._capture_planning_diff_after(so, payload)

    assert len(svc.so_diff_before) == 1, svc.so_diff_before
    assert len(svc.so_diff_after) == 1, svc.so_diff_after
    before_line = svc.so_diff_before[0]
    after_line = svc.so_diff_after[0]
    assert before_line.row_ref == str(line.id)
    assert after_line.row_ref == str(line.id)
    assert before_line.line_id == str(line.id), (
        "the BEFORE capture must carry line_id so a manual/ESB product swap pairs by "
        "identity, exactly as the manual-edit trigger's `_propagate_planning_change` does"
    )
    assert after_line.line_id == str(line.id), (
        "the AFTER capture must carry line_id too - `diff_lines` pairs a before/after "
        "sharing the SAME line_id first (Slice A rule 5)"
    )
