"""The GRN LINE's own SPO drives allocation matching; the header is the fallback.

Runs the real `process_grn_lines_import` over `tests/fixtures/grn_detail_listing_our_po.xlsx`
- four untouched rows lifted out of the AutoCount "GRN DETAIL LISTING (JUNE'26 -
AUG'26)" export (same 34 columns, same order), with the one column that export
does not carry yet added where the AutoCount grid shows it, right after Agent:
**Our PO No.**

The two GRNs in the fixture are the two branches:

- `GR-001093` names `SPO-2026/07-0012` on its LINES while its stored header says
  `SPO-2026/06-0056`. The line wins - that is the whole point: a GRN received
  against several SPOs cannot be told apart by its header cell.
- `GR-001084` leaves "Our PO No." empty, so it falls back to the header's
  `spo_number` - the linkage that shipped before this change.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.job import ImportJob
from app.models.procurement import (
    InboundShipment,
    PickingHeader,
    PickingLine,
    SPOAllocation,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.tasks.import_tasks import process_grn_lines_import

from ._pg_fixture import blank_session, unique_code

FIXTURE = Path(__file__).parent / "fixtures" / "grn_detail_listing_our_po.xlsx"

# Exactly as they read in the export.
LINE_SPO = "SPO-2026/07-0012"   # "Our PO No." on GR-001093's lines
HEADER_SPO = "SPO-2026/06-0056"  # GR-001093's stored header spo_number
FALLBACK_SPO = "SPO-2026/06-0099"  # GR-001084's header; its lines say nothing
GRN_WITH_LINE_SPO = "GR-001093"
GRN_WITHOUT_LINE_SPO = "GR-001084"
# (item code, location, qty) per fixture row.
LINES = {
    GRN_WITH_LINE_SPO: [("MWC7625-SH-S10", "HQ", 328), ("MWC7625-SH-P", "HQ", 80)],
    GRN_WITHOUT_LINE_SPO: [("MWC-SC8606-PP", "MOCHA-WH", 100), ("MWC-SC8606-PP", "MOCHA-WH", 530)],
}


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def seeded():
    """The file's own GRNs, products, warehouses and SPO allocations.

    Seeded from an EMPTY schema - nothing here borrows a live row, so the test
    says the same thing in CI as it does locally.
    """
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))

        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        session.add(ProductCategory(id=cat, category_code=unique_code("C")[:50], category_name="C"))
        session.add(UnitOfMeasure(id=uom, uom_code=unique_code("U")[:20], uom_name="Each"))
        session.flush()

        products: dict[str, str] = {}
        for code in {code for rows in LINES.values() for code, _loc, _qty in rows}:
            products[code] = str(uuid.uuid4())
            session.add(
                Product(
                    id=products[code], product_code=code, product_name=code,
                    category_id=cat, base_uom_id=uom, list_price=10, is_active=True,
                )
            )

        warehouses: dict[str, str] = {}
        for code in {loc for rows in LINES.values() for _c, loc, _q in rows}:
            warehouses[code] = str(uuid.uuid4())
            session.add(
                Warehouse(id=warehouses[code], warehouse_code=code, warehouse_name=code)
            )

        headers = {
            GRN_WITH_LINE_SPO: HEADER_SPO,
            GRN_WITHOUT_LINE_SPO: FALLBACK_SPO,
        }
        for picking_number, spo in headers.items():
            session.add(
                PickingHeader(
                    id=str(uuid.uuid4()), picking_number=picking_number,
                    picking_type="goods_received", picking_date=date(2026, 7, 1),
                    picking_status="approved", inspection_status="pending",
                    spo_number=spo,
                )
            )

        shipment = str(uuid.uuid4())
        session.add(
            InboundShipment(
                id=shipment, shipment_number=unique_code("SHP")[:50],
                shipment_date=date(2026, 6, 1),
            )
        )
        session.flush()

        # One allocation per (SPO, product), big enough to swallow the whole line.
        allocations: dict[tuple[str, str], str] = {}

        def _alloc(spo: str, product_code: str, warehouse_code: str, qty: int) -> None:
            allocations[(spo, product_code)] = str(uuid.uuid4())
            session.add(
                SPOAllocation(
                    id=allocations[(spo, product_code)], spo_number=spo,
                    inbound_shipment_id=shipment, warehouse_id=warehouses[warehouse_code],
                    product_id=products[product_code], allocated_quantity=qty,
                    quantity_received=0,
                )
            )

        for code, loc, qty in LINES[GRN_WITH_LINE_SPO]:
            # The SAME product is allocated under BOTH SPOs, so a link to the
            # right one is a real choice and not the only row available.
            _alloc(LINE_SPO, code, loc, qty)
            _alloc(HEADER_SPO, code, loc, qty)
        _alloc(FALLBACK_SPO, "MWC-SC8606-PP", "MOCHA-WH", 1000)

        job_db_id = uuid.uuid4()
        session.add(
            ImportJob(
                id=job_db_id, job_id=unique_code("job"), job_type="grn_lines_import",
                user_id="test", company_id=uuid.UUID(DEFAULT_COMPANY_ID),
                filename=FIXTURE.name,
            )
        )
        session.commit()

        bind = session.get_bind()

        def _session_on_this_connection():
            db = Session(bind=bind, join_transaction_mode="create_savepoint")
            db.execute(text("SELECT 1"))
            return db

        # The task opens its own session (and ImportOutcome opens another), so both
        # have to land on this test's connection.
        with patch("app.tasks.import_tasks.SessionLocal", _session_on_this_connection):
            yield {
                "session": session,
                "job_db_id": str(job_db_id),
                "products": products,
                "allocations": allocations,
            }


def _run(seeded) -> None:
    process_grn_lines_import(
        seeded["job_db_id"], FIXTURE.read_bytes(), FIXTURE.name, "test"
    )


def _lines(session, picking_number: str) -> list[PickingLine]:
    return (
        session.query(PickingLine)
        .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
        .filter(PickingHeader.picking_number == picking_number)
        .all()
    )


def test_the_lines_own_spo_is_what_the_allocation_links_to(seeded):
    """`Our PO No.` = SPO-2026/07-0012 on every line, header says ...06-0056."""
    _run(seeded)
    session = seeded["session"]

    lines = _lines(session, GRN_WITH_LINE_SPO)
    assert len(lines) == 2, [(l.quantity_picked, l.spo_allocation_id) for l in lines]
    for line in lines:
        code = next(c for c, pid in seeded["products"].items() if pid == line.product_id)
        assert line.spo_allocation_id == seeded["allocations"][(LINE_SPO, code)], (
            f"{code} linked to the header's SPO, not the line's"
        )


def test_a_line_with_no_po_number_still_falls_back_to_the_header(seeded):
    """The pre-existing linkage has to keep working - most of the file has no
    line-level column at all."""
    _run(seeded)
    session = seeded["session"]

    lines = _lines(session, GRN_WITHOUT_LINE_SPO)
    assert len(lines) == 1, "the two rows are the same product+location and sum"
    assert lines[0].quantity_picked == 630
    assert lines[0].spo_allocation_id == seeded["allocations"][(FALLBACK_SPO, "MWC-SC8606-PP")]


def test_a_matched_line_stores_what_the_sheet_said_as_well_as_the_link(seeded):
    """AC-FM-6. The link is the answer; the stated text is the evidence, and it is
    kept whether or not the matcher could use it."""
    _run(seeded)

    for line in _lines(seeded["session"], GRN_WITH_LINE_SPO):
        assert line.spo_allocation_id is not None
        assert line.spo_number_raw == LINE_SPO


def test_an_unmatched_line_still_remembers_the_spo_it_stated(seeded):
    """AC-FM-5. The GRN landing before its SPO is the normal case, not an error -
    a dash here would read as "the sheet said nothing", which is false."""
    session = seeded["session"]
    for spo, code in list(seeded["allocations"]):
        if spo == LINE_SPO:
            session.query(SPOAllocation).filter(
                SPOAllocation.id == seeded["allocations"][(spo, code)]
            ).delete()
    session.flush()

    _run(seeded)

    lines = _lines(session, GRN_WITH_LINE_SPO)
    assert lines, "the lines must still be written, just unlinked"
    for line in lines:
        assert line.spo_allocation_id is None
        assert line.spo_number_raw == LINE_SPO, "character for character as stated"


def test_the_header_fallback_is_what_a_silent_line_stores(seeded):
    """AC-FM-7. Most of the corpus has no line-level column at all."""
    _run(seeded)

    for line in _lines(seeded["session"], GRN_WITHOUT_LINE_SPO):
        assert line.spo_number_raw == FALLBACK_SPO


def test_a_multi_spo_header_leaves_a_silent_line_stating_nothing(seeded):
    """AC-FM-8. A joined value names no single allocation, so storing it would put
    a claim on screen the scalar matcher can never honour."""
    session = seeded["session"]
    header = (
        session.query(PickingHeader)
        .filter(PickingHeader.picking_number == GRN_WITHOUT_LINE_SPO)
        .one()
    )
    header.spo_number = "SPO-2026/06-0099, SPO-2026/06-0100"
    session.flush()

    _run(seeded)

    lines = _lines(session, GRN_WITHOUT_LINE_SPO)
    assert lines
    for line in lines:
        assert line.spo_number_raw is None
        assert line.spo_allocation_id is None


def test_a_corrected_sheet_refreshes_the_stored_text_in_place(seeded):
    """AC-FM-9. The same row is rewritten, not duplicated - which is what makes
    re-uploading a corrected export safe."""
    session = seeded["session"]
    header = (
        session.query(PickingHeader)
        .filter(PickingHeader.picking_number == GRN_WITHOUT_LINE_SPO)
        .one()
    )
    # An SPO no allocation covers, so both runs take the unlinked path and the row
    # identity (header, product, warehouse, NULL allocation) is stable across them.
    header.spo_number = "SPO-2026/06-0912"
    session.flush()
    _run(seeded)
    assert [l.spo_number_raw for l in _lines(session, GRN_WITHOUT_LINE_SPO)] == [
        "SPO-2026/06-0912"
    ]

    header.spo_number = "SPO-2026/06-0913"
    session.flush()
    _run(seeded)

    lines = _lines(session, GRN_WITHOUT_LINE_SPO)
    assert len(lines) == 1, "the corrected sheet must update the row, not add one"
    assert lines[0].spo_number_raw == "SPO-2026/06-0913"


def test_the_job_reports_every_row_as_written(seeded):
    _run(seeded)
    job = (
        seeded["session"].query(ImportJob)
        .filter(ImportJob.id == uuid.UUID(seeded["job_db_id"]))
        .one()
    )

    assert job.failed_rows == 0
    assert job.skipped_rows == 0
    assert job.total_rows == 4
