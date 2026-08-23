"""P8a: match back, the divergence it raises, and how a person answers it (AC-N1..N7, AC-F11).

The comparison arithmetic is proven without a database in
``test_project_so_divergence_engine.py``. What is proven HERE is everything the engine
cannot see: that an AutoCount document finds the sales order it belongs to WITHOUT being
identical to it, that an ambiguous match writes nothing, that our values survive the
ingest, that an open divergence stops an amendment, and that each resolution does what the
table in `PLAN-project-so-divergence.md` says it does.

Postgres, blank scratch schema, rolled back at teardown. Every FK target is real and
seeded here: CI's database is empty, so nothing is borrowed from an existing row.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.order import Customer
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    DIVERGENCE_OPEN,
    DIVERGENCE_RESOLVED,
    RESOLUTION_ACCEPT_THEIRS,
    RESOLUTION_KEEP_OURS,
    SO_STATUS_PUBLISHED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    ProjectSODivergence,
    ProjectSODivergenceLine,
    SOLineAllocation,
)
from app.models.projects import ProjectParty, ProjectPurchaseOrder
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException
from app.services.project_so_delta_service import ProjectSODeltaService
from app.services.project_so_divergence_engine import (
    PRESENCE_BOTH,
    PRESENCE_OURS_ONLY,
    PRESENCE_THEIRS_ONLY,
)
from app.services.project_so_divergence_service import ProjectSODivergenceService
from app.services.project_so_ingest_service import (
    OUTCOME_AMBIGUOUS,
    OUTCOME_DIVERGENT,
    OUTCOME_MATCHED,
    OUTCOME_UNMATCHED,
    IngestDocument,
    IngestLine,
    ProjectSOIngestService,
)

from ._pg_fixture import blank_session

MARKER = "zzt-div"

MAR = date(2026, 3, 10)
APR = date(2026, 4, 10)


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    """Seeded with the module's own reference data: project registration draws a number
    from a sequence, and a blank schema has none until the seeder runs."""
    with blank_session() as session:
        company_id = session.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        project_seed_service.run(session, company_id=company_id)
        yield session


@pytest.fixture()
def company(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


@pytest.fixture()
def actor(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} CS"))
    db.flush()
    return user_id


def _product(db, code: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tuju Residences {_uid()[:12]}",
    )


def _customer(db, code: str) -> Customer:
    row = Customer(id=_uid(), customer_code=code, customer_name=f"{MARKER} {code}")
    db.add(row)
    db.flush()
    return row


def _po(db, project, customer, *, po_number: str, term_days: int = 60) -> ProjectPurchaseOrder:
    party = ProjectParty(
        id=_uid(),
        company_id=project.company_id,
        party_type="contractor",
        name=f"{MARKER} {customer.customer_name}",
        customer_id=customer.id,
    )
    db.add(party)
    db.flush()
    row = ProjectPurchaseOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        issuing_party_id=party.id,
        po_number=po_number,
        po_date=date(2026, 2, 1),
        term_days=term_days,
        status="approved",
    )
    db.add(row)
    db.flush()
    return row


def _order(db, project, po, *, area_group: str = "TOWER") -> ProjectSalesOrder:
    row = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        purchase_order_id=po.id,
        area_group=area_group,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        status=SO_STATUS_PUBLISHED,
        published_at=datetime.utcnow(),
        grouping_origin="area",
    )
    db.add(row)
    db.flush()
    return row


def _line(
    db, order, product, qty: str, price: str, delivery: date | None = MAR, *, line_no: int = 1
) -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        line_no=line_no,
        product_id=product.id,
        description=f"{MARKER} {product.product_code}",
        qty=Decimal(qty),
        uom="UNIT",
        unit_price=Decimal(price),
        amount=Decimal(qty) * Decimal(price),
        delivery_date=delivery,
    )
    db.add(row)
    db.flush()
    return row


def _document(
    *,
    doc_no: str = "SO397450",
    customer_code: str,
    po_number: str,
    area_group: str = "TOWER",
    terms: str = "*Net 60 days",
    total: str = "7500.00",
    lines: list[IngestLine],
) -> IngestDocument:
    return IngestDocument(
        doc_no=doc_no,
        customer_code=customer_code,
        customer_po_no=po_number,
        area_group=area_group,
        terms=terms,
        total_amount=Decimal(total),
        lines=lines,
    )


def _their(
    code: str, qty: str, price: str, delivery: date | None = MAR, *, line_no: int = 1
) -> IngestLine:
    return IngestLine(
        line_no=line_no,
        product_code=code,
        description=f"{MARKER} {code}",
        qty=Decimal(qty),
        unit_price=Decimal(price),
        uom="UNIT",
        delivery_date=delivery,
    )


@pytest.fixture()
def scenario(db, company, actor):
    """One published sales order: 600 CB6633 at 12.50, one line, PO-778, TOWER."""
    project = _project(db, company, actor)
    customer = _customer(db, f"ZZTC{_uid()[:6]}")
    po = _po(db, project, customer, po_number=f"PO-778-{_uid()[:6]}")
    order = _order(db, project, po)
    product = _product(db, f"CB{_uid()[:6]}")
    line = _line(db, order, product, "600", "12.50")
    order.total_amount = Decimal("7500.00")
    db.flush()
    return {
        "project": project,
        "customer": customer,
        "po": po,
        "order": order,
        "product": product,
        "line": line,
    }


def _ingest(db, scenario, *, lines=None, actor_user_id, **kwargs):
    doc = _document(
        customer_code=scenario["customer"].customer_code,
        po_number=scenario["po"].po_number,
        lines=lines
        if lines is not None
        else [_their(scenario["product"].product_code, "600", "12.50")],
        **kwargs,
    )
    return ProjectSOIngestService(db).ingest(doc, actor_user_id=actor_user_id)


def _divergence(db, order_id):
    return (
        db.query(ProjectSODivergence)
        .filter(ProjectSODivergence.project_sales_order_id == order_id)
        .all()
    )


def _rows(db, divergence_id):
    return (
        db.query(ProjectSODivergenceLine)
        .filter(ProjectSODivergenceLine.divergence_id == divergence_id)
        .all()
    )


# --------------------------------------------------------------------------- #
# Match back (AC-F11, AC-F11a)                                                 #
# --------------------------------------------------------------------------- #


def test_a_document_matches_even_though_its_lines_differ(db, scenario, actor):
    """The fingerprint cannot be the primary key: a divergent document has a DIFFERENT
    one by definition, so keying on it would report every divergence as unmatched."""
    result = _ingest(
        db,
        scenario,
        lines=[_their(scenario["product"].product_code, "550", "12.50")],
        actor_user_id=actor,
    )

    assert result.outcome == OUTCOME_DIVERGENT
    assert result.project_sales_order_id == scenario["order"].id


def test_the_returned_document_number_is_adopted_onto_our_record(db, scenario, actor):
    """AC-F11. The column existed and nothing wrote it until this slice."""
    assert scenario["order"].autocount_doc_no is None

    _ingest(db, scenario, doc_no="SO397450", actor_user_id=actor)

    db.refresh(scenario["order"])
    assert scenario["order"].autocount_doc_no == "SO397450"


def test_a_document_for_a_po_we_never_published_is_unmatched(db, scenario, actor):
    doc = _document(
        customer_code=scenario["customer"].customer_code,
        po_number="PO-NOT-OURS",
        lines=[_their(scenario["product"].product_code, "600", "12.50")],
    )

    result = ProjectSOIngestService(db).ingest(doc, actor_user_id=actor)

    assert result.outcome == OUTCOME_UNMATCHED
    assert result.project_sales_order_id is None
    assert _divergence(db, scenario["order"].id) == []


def test_a_different_area_group_does_not_match(db, scenario, actor):
    result = _ingest(db, scenario, area_group="PODIUM", actor_user_id=actor)

    assert result.outcome == OUTCOME_UNMATCHED


def test_two_candidates_are_separated_by_the_line_fingerprint(db, scenario, actor):
    """Finding G4: two sales orders on one PO within one area group."""
    twin = _order(db, scenario["project"], scenario["po"])
    other = _product(db, f"AB{_uid()[:6]}")
    _line(db, twin, other, "40", "300.00")
    twin.total_amount = Decimal("12000.00")
    db.flush()

    result = _ingest(
        db,
        scenario,
        lines=[_their(other.product_code, "40", "300.00")],
        total="12000.00",
        actor_user_id=actor,
    )

    assert result.outcome == OUTCOME_MATCHED
    assert result.project_sales_order_id == twin.id


def test_two_candidates_neither_matching_is_ambiguous_and_writes_nothing(db, scenario, actor):
    twin = _order(db, scenario["project"], scenario["po"])
    other = _product(db, f"AB{_uid()[:6]}")
    _line(db, twin, other, "40", "300.00")
    db.flush()

    result = _ingest(
        db,
        scenario,
        lines=[_their(scenario["product"].product_code, "550", "12.50")],
        actor_user_id=actor,
    )

    assert result.outcome == OUTCOME_AMBIGUOUS
    assert result.project_sales_order_id is None
    assert result.candidate_ids and len(result.candidate_ids) == 2
    assert _divergence(db, scenario["order"].id) == []
    assert _divergence(db, twin.id) == []
    db.refresh(scenario["order"])
    assert scenario["order"].autocount_doc_no is None


def test_an_unpublished_draft_is_never_a_candidate(db, scenario, actor):
    scenario["order"].status = "draft"
    db.flush()

    result = _ingest(db, scenario, actor_user_id=actor)

    assert result.outcome == OUTCOME_UNMATCHED


# --------------------------------------------------------------------------- #
# What ingest writes (AC-N2, AC-N3)                                            #
# --------------------------------------------------------------------------- #


def test_an_identical_document_adopts_the_number_and_raises_nothing(db, scenario, actor):
    result = _ingest(db, scenario, actor_user_id=actor)

    assert result.outcome == OUTCOME_MATCHED
    assert result.divergence_id is None
    assert _divergence(db, scenario["order"].id) == []


def test_our_values_are_held_beside_theirs_and_never_overwritten(db, scenario, actor):
    result = _ingest(
        db,
        scenario,
        lines=[_their(scenario["product"].product_code, "550", "11.00", APR)],
        total="6050.00",
        actor_user_id=actor,
    )

    db.refresh(scenario["line"])
    assert scenario["line"].qty == Decimal("600.0000")
    assert scenario["line"].unit_price == Decimal("12.50000")
    assert scenario["line"].delivery_date == MAR

    line_rows = [r for r in _rows(db, result.divergence_id) if r.scope == "line"]
    assert len(line_rows) == 1
    assert set(line_rows[0].differing_fields) == {"qty", "unit_price", "delivery_date"}
    assert line_rows[0].theirs_json["qty"] == "550.0000"
    assert line_rows[0].ours_json["qty"] == "600.0000"


def test_agreeing_lines_are_stored_so_the_screen_can_collapse_them(db, scenario, actor):
    second = _product(db, f"AB{_uid()[:6]}")
    _line(db, scenario["order"], second, "40", "300.00", line_no=2)
    db.flush()

    result = _ingest(
        db,
        scenario,
        lines=[
            _their(scenario["product"].product_code, "550", "12.50"),
            _their(second.product_code, "40", "300.00", line_no=2),
        ],
        actor_user_id=actor,
    )

    divergence = db.get(ProjectSODivergence, result.divergence_id)
    assert divergence.agreeing_count >= 1
    agreeing = [
        r for r in _rows(db, result.divergence_id) if r.scope == "line" and not r.differing_fields
    ]
    assert [r.product_code for r in agreeing] == [second.product_code]


def test_the_ingest_source_is_recorded(db, scenario, actor):
    result = _ingest(db, scenario, lines=[_their(scenario["product"].product_code, "1", "12.50")], actor_user_id=actor)

    assert db.get(ProjectSODivergence, result.divergence_id).ingest_source == "upload"


def test_the_same_export_uploaded_twice_is_one_reconciliation(db, scenario, actor):
    lines = [_their(scenario["product"].product_code, "550", "12.50")]
    first = _ingest(db, scenario, lines=lines, actor_user_id=actor)
    second = _ingest(db, scenario, lines=lines, actor_user_id=actor)

    assert first.divergence_id == second.divergence_id
    assert len(_divergence(db, scenario["order"].id)) == 1


def test_a_second_upload_recomputes_the_open_divergence(db, scenario, actor):
    first = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    second = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "500", "12.50")], actor_user_id=actor
    )

    assert first.divergence_id == second.divergence_id
    line_rows = [r for r in _rows(db, second.divergence_id) if r.scope == "line"]
    assert line_rows[0].theirs_json["qty"] == "500.0000"


def test_a_document_that_now_agrees_closes_the_open_divergence(db, scenario, actor):
    """Somebody fixed it in AutoCount. Re-ingesting is the honest way to say so."""
    first = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    result = _ingest(db, scenario, actor_user_id=actor)

    assert result.outcome == OUTCOME_MATCHED
    divergence = db.get(ProjectSODivergence, first.divergence_id)
    assert divergence.status == DIVERGENCE_RESOLVED
    assert divergence.resolved_at is not None


# --------------------------------------------------------------------------- #
# The block (AC-N5)                                                            #
# --------------------------------------------------------------------------- #


def test_an_open_divergence_blocks_an_amendment(db, scenario, actor):
    _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )

    with pytest.raises(AppException) as exc:
        ProjectSODeltaService(db).create(
            scenario["order"].id, po_version_id=_uid(), reason="whatever", actor_user_id=actor
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "so_divergence_unresolved"


def test_a_resolved_divergence_stops_blocking(db, scenario, actor):
    result = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    service = ProjectSODivergenceService(db)
    for row in _rows(db, result.divergence_id):
        if row.differing_fields or row.presence != PRESENCE_BOTH:
            service.resolve_line(
                result.divergence_id,
                row.id,
                resolution=RESOLUTION_KEEP_OURS,
                reason=f"{MARKER} ours is right",
                actor_user_id=actor,
            )

    # No longer the divergence guard: it fails later, on the version that does not exist.
    with pytest.raises(AppException) as exc:
        ProjectSODeltaService(db).create(
            scenario["order"].id, po_version_id=_uid(), reason="whatever", actor_user_id=actor
        )
    assert exc.value.detail["code"] != "so_divergence_unresolved"


# --------------------------------------------------------------------------- #
# Resolution (AC-N4, AC-N7)                                                    #
# --------------------------------------------------------------------------- #


def _line_row(db, divergence_id, presence=PRESENCE_BOTH):
    rows = [
        r
        for r in _rows(db, divergence_id)
        if r.scope == "line" and r.presence == presence
    ]
    assert rows, f"no {presence} line row"
    return rows[0]


def test_accepting_theirs_updates_our_line_and_the_order_total(db, scenario, actor):
    result = _ingest(
        db,
        scenario,
        lines=[_their(scenario["product"].product_code, "550", "11.00", APR)],
        actor_user_id=actor,
    )
    row = _line_row(db, result.divergence_id)

    ProjectSODivergenceService(db).resolve_line(
        result.divergence_id,
        row.id,
        resolution=RESOLUTION_ACCEPT_THEIRS,
        reason=f"{MARKER} CS corrected it in AutoCount",
        actor_user_id=actor,
    )

    db.refresh(scenario["line"])
    assert scenario["line"].qty == Decimal("550.0000")
    assert scenario["line"].unit_price == Decimal("11.00000")
    assert scenario["line"].delivery_date == APR
    assert scenario["line"].amount == Decimal("6050.00")
    db.refresh(scenario["order"])
    assert scenario["order"].total_amount == Decimal("6050.00")


def test_a_resolution_is_audited(db, scenario, actor):
    result = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    row = _line_row(db, result.divergence_id)

    ProjectSODivergenceService(db).resolve_line(
        result.divergence_id,
        row.id,
        resolution=RESOLUTION_ACCEPT_THEIRS,
        reason=f"{MARKER} their count is right",
        actor_user_id=actor,
    )

    db.refresh(row)
    assert row.resolution == RESOLUTION_ACCEPT_THEIRS
    assert row.resolved_by == actor
    assert row.resolved_at is not None
    assert row.reason == f"{MARKER} their count is right"


def test_a_resolution_without_a_reason_is_refused(db, scenario, actor):
    result = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    row = _line_row(db, result.divergence_id)

    with pytest.raises(AppException) as exc:
        ProjectSODivergenceService(db).resolve_line(
            result.divergence_id,
            row.id,
            resolution=RESOLUTION_ACCEPT_THEIRS,
            reason="   ",
            actor_user_id=actor,
        )

    assert exc.value.status_code == 422


def test_keeping_ours_queues_a_corrective_publish(db, scenario, actor):
    result = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    row = _line_row(db, result.divergence_id)

    ProjectSODivergenceService(db).resolve_line(
        result.divergence_id,
        row.id,
        resolution=RESOLUTION_KEEP_OURS,
        reason=f"{MARKER} the PO says 600",
        actor_user_id=actor,
    )

    db.refresh(scenario["line"])
    assert scenario["line"].qty == Decimal("600.0000")
    assert db.get(ProjectSODivergence, result.divergence_id).corrective_publish_required is True


def test_a_line_autocount_dropped_is_cancelled_rather_than_deleted(db, scenario, actor):
    """Allocations, claims and inquiry rows point at it. Zero is this system's word for
    a cancelled balance; a delete would take the audit trail with it."""
    warehouse = Warehouse(id=_uid(), warehouse_code=f"ZZT{_uid()[:6]}", warehouse_name=MARKER)
    db.add(warehouse)
    db.flush()
    allocation = SOLineAllocation(
        id=_uid(),
        company_id=scenario["order"].company_id,
        so_line_id=scenario["line"].id,
        source_type="own",
        warehouse_id=warehouse.id,
        qty=Decimal("600"),
        confirmed_by=actor,
        confirmed_at=datetime.utcnow(),
    )
    db.add(allocation)
    db.flush()

    result = _ingest(db, scenario, lines=[], total="0.00", actor_user_id=actor)
    row = _line_row(db, result.divergence_id, presence=PRESENCE_OURS_ONLY)

    ProjectSODivergenceService(db).resolve_line(
        result.divergence_id,
        row.id,
        resolution=RESOLUTION_ACCEPT_THEIRS,
        reason=f"{MARKER} cancelled by the customer",
        actor_user_id=actor,
    )

    db.refresh(scenario["line"])
    assert scenario["line"].qty == Decimal("0.0000")
    assert scenario["line"].amount == Decimal("0.00")
    assert db.get(ProjectSalesOrderLine, scenario["line"].id) is not None
    assert db.get(SOLineAllocation, allocation.id) is not None


def test_a_line_only_autocount_has_is_inserted_when_theirs_is_accepted(db, scenario, actor):
    extra = _product(db, f"ZZ{_uid()[:6]}")
    result = _ingest(
        db,
        scenario,
        lines=[
            _their(scenario["product"].product_code, "600", "12.50"),
            _their(extra.product_code, "5", "88.00", APR, line_no=2),
        ],
        total="7940.00",
        actor_user_id=actor,
    )
    row = _line_row(db, result.divergence_id, presence=PRESENCE_THEIRS_ONLY)

    ProjectSODivergenceService(db).resolve_line(
        result.divergence_id,
        row.id,
        resolution=RESOLUTION_ACCEPT_THEIRS,
        reason=f"{MARKER} CS added it on their side",
        actor_user_id=actor,
    )

    lines = (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == scenario["order"].id)
        .all()
    )
    added = [line for line in lines if line.product_id == extra.id]
    assert len(added) == 1
    assert added[0].qty == Decimal("5.0000")
    assert added[0].unit_price == Decimal("88.00000")
    assert added[0].delivery_date == APR
    db.refresh(row)
    assert row.so_line_id == added[0].id


def test_a_line_naming_a_product_we_do_not_stock_cannot_be_accepted(db, scenario, actor):
    result = _ingest(
        db,
        scenario,
        lines=[
            _their(scenario["product"].product_code, "600", "12.50"),
            _their("NOT-A-PRODUCT", "5", "88.00", line_no=2),
        ],
        actor_user_id=actor,
    )
    row = _line_row(db, result.divergence_id, presence=PRESENCE_THEIRS_ONLY)

    with pytest.raises(AppException) as exc:
        ProjectSODivergenceService(db).resolve_line(
            result.divergence_id,
            row.id,
            resolution=RESOLUTION_ACCEPT_THEIRS,
            reason=f"{MARKER} adopt it",
            actor_user_id=actor,
        )

    assert exc.value.status_code == 422
    assert "NOT-A-PRODUCT" in exc.value.detail["message"]


def test_accepting_a_header_difference_records_it_without_rewriting_the_po(db, scenario, actor):
    """AutoCount's copy of the terms is not authority over the customer's document."""
    result = _ingest(db, scenario, terms="*Net 30 days", actor_user_id=actor)
    header = [r for r in _rows(db, result.divergence_id) if r.scope == "header"][0]
    assert header.differing_fields == ["terms"]

    ProjectSODivergenceService(db).resolve_line(
        result.divergence_id,
        header.id,
        resolution=RESOLUTION_ACCEPT_THEIRS,
        reason=f"{MARKER} noted",
        actor_user_id=actor,
    )

    db.refresh(scenario["po"])
    assert scenario["po"].term_days == 60


def test_answering_every_row_closes_the_divergence(db, scenario, actor):
    result = _ingest(
        db,
        scenario,
        lines=[_their(scenario["product"].product_code, "550", "12.50")],
        total="6875.00",
        actor_user_id=actor,
    )
    service = ProjectSODivergenceService(db)
    outstanding = [
        r
        for r in _rows(db, result.divergence_id)
        if r.differing_fields or r.presence != PRESENCE_BOTH
    ]
    assert len(outstanding) == 2  # the line and the header total

    for index, row in enumerate(outstanding):
        divergence = service.resolve_line(
            result.divergence_id,
            row.id,
            resolution=RESOLUTION_ACCEPT_THEIRS,
            reason=f"{MARKER} agreed",
            actor_user_id=actor,
        )
        expected = DIVERGENCE_RESOLVED if index == len(outstanding) - 1 else DIVERGENCE_OPEN
        assert divergence.status == expected

    divergence = db.get(ProjectSODivergence, result.divergence_id)
    assert divergence.resolved_by == actor
    assert divergence.resolved_at is not None


def test_a_row_that_agrees_needs_no_answer(db, scenario, actor):
    second = _product(db, f"AB{_uid()[:6]}")
    _line(db, scenario["order"], second, "40", "300.00", line_no=2)
    db.flush()
    result = _ingest(
        db,
        scenario,
        lines=[
            _their(scenario["product"].product_code, "550", "12.50"),
            _their(second.product_code, "40", "300.00", line_no=2),
        ],
        total="6875.00",
        actor_user_id=actor,
    )
    service = ProjectSODivergenceService(db)

    for row in _rows(db, result.divergence_id):
        if row.differing_fields or row.presence != PRESENCE_BOTH:
            service.resolve_line(
                result.divergence_id,
                row.id,
                resolution=RESOLUTION_ACCEPT_THEIRS,
                reason=f"{MARKER} agreed",
                actor_user_id=actor,
            )

    assert db.get(ProjectSODivergence, result.divergence_id).status == DIVERGENCE_RESOLVED


def test_a_row_cannot_be_answered_twice(db, scenario, actor):
    result = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    row = _line_row(db, result.divergence_id)
    service = ProjectSODivergenceService(db)
    service.resolve_line(
        result.divergence_id,
        row.id,
        resolution=RESOLUTION_KEEP_OURS,
        reason=f"{MARKER} ours",
        actor_user_id=actor,
    )

    with pytest.raises(AppException) as exc:
        service.resolve_line(
            result.divergence_id,
            row.id,
            resolution=RESOLUTION_ACCEPT_THEIRS,
            reason=f"{MARKER} changed my mind",
            actor_user_id=actor,
        )

    assert exc.value.status_code == 409


# --------------------------------------------------------------------------- #
# The management list (AC-N6) and the corrective publish                       #
# --------------------------------------------------------------------------- #


def test_the_list_carries_the_age_of_each_divergence(db, scenario, actor):
    result = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    divergence = db.get(ProjectSODivergence, result.divergence_id)
    divergence.detected_at = datetime.utcnow() - timedelta(days=9)
    db.flush()

    rows = ProjectSODivergenceService(db).list_divergences(status=DIVERGENCE_OPEN)["data"]

    mine = [row for row in rows if row["id"] == result.divergence_id]
    assert len(mine) == 1
    assert mine[0]["age_days"] == 9
    assert mine[0]["differing_count"] >= 1
    assert mine[0]["project_title"] == scenario["project"].title


def test_the_corrective_import_file_is_stamped_when_taken(db, scenario, actor):
    result = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )
    service = ProjectSODivergenceService(db)
    row = _line_row(db, result.divergence_id)
    service.resolve_line(
        result.divergence_id,
        row.id,
        resolution=RESOLUTION_KEEP_OURS,
        reason=f"{MARKER} the PO says 600",
        actor_user_id=actor,
    )

    filename, body = service.corrective_import_file(result.divergence_id)

    assert filename.endswith(".csv")
    assert "600" in body
    assert db.get(ProjectSODivergence, result.divergence_id).corrective_publish_taken_at is not None


def test_a_corrective_file_is_refused_when_nothing_was_kept(db, scenario, actor):
    result = _ingest(
        db, scenario, lines=[_their(scenario["product"].product_code, "550", "12.50")], actor_user_id=actor
    )

    with pytest.raises(AppException) as exc:
        ProjectSODivergenceService(db).corrective_import_file(result.divergence_id)

    assert exc.value.status_code == 409
