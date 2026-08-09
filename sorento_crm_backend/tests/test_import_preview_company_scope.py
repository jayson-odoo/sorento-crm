"""An import preview answers for ONE company - the same one the import will run at.

The previews built their own session and pinned it to `set_company_scope(db, None)`
(all companies), while the real import runs at the job's single-company snapshot
(`_apply_import_job_scope`). So a preview resolved products, warehouses and GRN
headers the scoped import cannot see, said "would succeed", and then the import
skipped those rows as not-found. A green preview that disagrees with the import is
worse than no preview.

The route now passes `get_company_scope(db)` - the scope already resolved for that
request - into the preview.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO
from unittest.mock import patch

import openpyxl
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.procurement import PickingHeader
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.tasks.import_tasks import validate_grn_lines_import

from ._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"
LINE_HEADERS = ["Doc No", "Item Code", "Location", "Qty"]


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def mocha_only_grn():
    """A GRN header + product + warehouse that exist ONLY under Mocha.

    `SessionLocal` is patched to hand the preview a session on this test's
    connection, because the preview opens its own session (that is the whole
    reason its scope had to be passed in rather than inherited).
    """
    with blank_session() as session:
        set_company_scope(session, None)
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()

        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        session.add(ProductCategory(id=cat, category_code=unique_code("C")[:50], category_name="C"))
        session.add(UnitOfMeasure(id=uom, uom_code=unique_code("U")[:20], uom_name="Each"))
        session.flush()

        fixture = {
            "grn": unique_code("GR")[:50],
            "product_code": unique_code("P")[:50],
            "warehouse_code": unique_code("W")[:20],
        }
        session.add(
            PickingHeader(
                id=str(uuid.uuid4()), picking_number=fixture["grn"],
                picking_type="goods_received", picking_date=date.today(),
                picking_status="approved", inspection_status="pending",
                company_id=MOCHA_ID,
            )
        )
        session.add(
            Product(
                id=str(uuid.uuid4()), product_code=fixture["product_code"],
                product_name=fixture["product_code"], category_id=cat, base_uom_id=uom,
                list_price=10, is_active=True, company_id=MOCHA_ID,
            )
        )
        session.add(
            Warehouse(
                id=str(uuid.uuid4()), warehouse_code=fixture["warehouse_code"],
                warehouse_name=fixture["warehouse_code"], company_id=MOCHA_ID,
            )
        )
        session.commit()

        bind = session.get_bind()

        def _session_on_this_connection():
            db = Session(bind=bind, join_transaction_mode="create_savepoint")
            # blank_session pins search_path on the connection, but a raw-SQL read
            # inside the preview resolves through the session's own settings.
            db.execute(text("SELECT 1"))
            return db

        with patch("app.tasks.import_tasks.SessionLocal", _session_on_this_connection):
            yield fixture


def _lines_workbook(fixture) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(LINE_HEADERS)
    ws.append([fixture["grn"], fixture["product_code"], fixture["warehouse_code"], 5])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_the_preview_sees_only_the_callers_company(mocha_only_grn):
    """Sorento asked, so Mocha's GRN / product / warehouse are not there - exactly
    what a Sorento-scoped import would report."""
    result = validate_grn_lines_import(
        _lines_workbook(mocha_only_grn),
        company_scope=frozenset({DEFAULT_COMPANY_ID}),
    )

    assert result["valid"] is False
    assert result["summary"]["would_succeed"] == 0
    assert result["summary"]["would_skip"] == 1
    reasons = " ".join(d["reason"] for d in result["summary"]["skipped_rows_detail"])
    assert mocha_only_grn["grn"] in reasons


def test_the_preview_passes_under_the_owning_company(mocha_only_grn):
    """Same file, same rows, Mocha scope: everything resolves. Guards against the
    fix turning every preview into a fail."""
    result = validate_grn_lines_import(
        _lines_workbook(mocha_only_grn),
        company_scope=frozenset({MOCHA_ID}),
    )

    assert result["errors"] == []
    assert result["valid"] is True
    assert result["summary"]["would_succeed"] == 1


def test_an_unscoped_caller_still_reads_all_companies(mocha_only_grn):
    """Back-compat for non-HTTP callers (scripts, tests): no scope passed means
    system-scoped, logged as a warning rather than silently failing closed."""
    result = validate_grn_lines_import(_lines_workbook(mocha_only_grn))

    assert result["summary"]["would_succeed"] == 1
