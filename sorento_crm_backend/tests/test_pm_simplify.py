"""PM-SIMPLIFY: the project PO and delivery schedule, simplified.

Plan `documentation/plans/projects/PLAN-pm-simplify-17oct.md`, UAC
`pm-simplify-17oct-acceptance-criteria.md`. Fixtures reuse the P7 drafting helpers so
the build under test is the real one.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.project_so import ProjectSalesOrder
from app.services.error_handler import AppException
from app.services.project_so_draft_service import ProjectSODraftService

from .test_project_so_draft import (  # noqa: F401 - `seeded` is a fixture
    _cell,
    _party,
    _phase,
    _po,
    _po_version,
    _product,
    _project,
    _quotation,
    _schedule,
    seeded,
)


def _one_line_po(db, company_id, owner, *, po_confirmed=True, schedule_confirmed=True):
    project = _project(db, company_id, owner)
    product = _product(db, "SRTA-100")
    quotation = _quotation(db, project, lines=[(product, "300", "10.00")])
    po = _po(db, project, party=_party(db, company_id), quotation_version=quotation)
    po_version = _po_version(
        db,
        po,
        lines=[(1, product, "SRTA-100", "300", "UNIT", "10.00", "3000.00", False)],
        extracted_total="3000.00",
        confirmed=po_confirmed,
    )
    schedule = _schedule(db, project, po, po_version=po_version, confirmed=schedule_confirmed)
    phase = _phase(
        db,
        project,
        area_group="TOWER",
        sequence=1,
        label="Level 2 & 7",
        delivery_date=date(2026, 7, 1),
        version=schedule,
    )
    _cell(db, schedule, phase, product, "300")
    return project, po, po_version, schedule, phase, product


# ------------------------------------------------------------------ D3 build gate


def test_build_refuses_an_unconfirmed_schedule(seeded):
    db, company_id, owner = seeded
    _project_row, po, _v, schedule, _phase_row, _p = _one_line_po(
        db, company_id, owner, schedule_confirmed=False
    )

    with pytest.raises(AppException) as caught:
        ProjectSODraftService(db).build(po.id, schedule.id)

    assert caught.value.status_code == 409
    assert caught.value.code == "schedule_not_confirmed"
    assert db.query(ProjectSalesOrder).filter(ProjectSalesOrder.purchase_order_id == po.id).count() == 0


def test_build_refuses_a_scanned_po_with_no_confirmed_version(seeded):
    db, company_id, owner = seeded
    _project_row, po, _v, schedule, _phase_row, _p = _one_line_po(
        db, company_id, owner, po_confirmed=False
    )

    with pytest.raises(AppException) as caught:
        ProjectSODraftService(db).build(po.id, schedule.id)

    assert caught.value.status_code == 409
    assert caught.value.code == "po_not_confirmed"


def test_build_reads_the_latest_confirmed_po_version_not_a_newer_unconfirmed_one(seeded):
    db, company_id, owner = seeded
    _project_row, po, _v1, schedule, _phase_row, product = _one_line_po(db, company_id, owner)
    # Version 2 arrived and nobody has read it: its 999 must not reach the sales order.
    schedule.po_version_id = None
    _po_version(
        db,
        po,
        lines=[(1, product, "SRTA-100", "999", "UNIT", "10.00", "9990.00", False)],
        version_no=2,
        confirmed=False,
    )
    db.flush()

    result = ProjectSODraftService(db).build(po.id, schedule.id)

    assert result["data"][0]["total_amount"] == Decimal("3000.00")


# ------------------------------------------------- progress and area dates (fixture)


def _two_line_po(db, company_id, owner):
    """PO lines A 300 and B 60 over three TOWER areas. B is scheduled 50: 10 short."""

    project = _project(db, company_id, owner)
    product_a = _product(db, "SRTA-100")
    product_b = _product(db, "SRTB-200")
    quotation = _quotation(
        db, project, lines=[(product_a, "300", "10.00"), (product_b, "60", "20.00")]
    )
    po = _po(db, project, party=_party(db, company_id), quotation_version=quotation)
    po_version = _po_version(
        db,
        po,
        lines=[
            (1, product_a, "SRTA-100", "300", "UNIT", "10.00", "3000.00", False),
            (2, product_b, "SRTB-200", "60", "UNIT", "20.00", "1200.00", False),
        ],
        extracted_total="4200.00",
    )
    schedule = _schedule(db, project, po, po_version=po_version)
    dates = [date(2030, 7, 1), date(2030, 8, 1), date(2030, 9, 1)]
    phases = []
    for sequence, delivery_date in enumerate(dates, start=1):
        phase = _phase(
            db,
            project,
            area_group="TOWER",
            sequence=sequence,
            label=f"Level {sequence}",
            delivery_date=delivery_date,
            version=schedule,
        )
        _cell(db, schedule, phase, product_a, "100")
        _cell(db, schedule, phase, product_b, "20" if sequence < 3 else "10")
        phases.append(phase)
    ProjectSODraftService(db).build(po.id, schedule.id)
    return po, phases, product_a, product_b


def _orders(db, po):
    return db.query(ProjectSalesOrder).filter(ProjectSalesOrder.purchase_order_id == po.id).all()


def _so_lines(db, po, *, phase=None, product=None):
    from app.models.project_so import ProjectSalesOrderLine

    query = db.query(ProjectSalesOrderLine).filter(
        ProjectSalesOrderLine.project_sales_order_id.in_([order.id for order in _orders(db, po)])
    )
    if phase is not None:
        query = query.filter(ProjectSalesOrderLine.phase_id == phase.id)
    if product is not None:
        query = query.filter(ProjectSalesOrderLine.product_id == product.id)
    return query.all()


def _deliver(db, so_line, qty):
    """Link a project SO line to a core line AutoCount has delivered `qty` of."""
    import uuid as _uuid

    from app.models.order import SalesOrder, SalesOrderLine

    header = SalesOrder(id=str(_uuid.uuid4()), so_number=f"ZZT-SO-{_uuid.uuid4().hex[:8]}", status="open")
    db.add(header)
    db.flush()
    core = SalesOrderLine(
        id=str(_uuid.uuid4()),
        sales_order_id=header.id,
        product_id=so_line.product_id,
        qty_ordered=so_line.qty,
        qty_delivered=Decimal(qty),
        required_date=so_line.delivery_date,
    )
    db.add(core)
    db.flush()
    so_line.core_sales_order_line_id = core.id
    db.flush()


def _publish_all(db, po):
    for order in _orders(db, po):
        order.status = "published"
    db.flush()


def test_progress_reads_ordered_scheduled_delivered_and_outstanding_per_line(seeded):
    """AC-L1."""
    from app.services.project_po_progress_service import po_progress

    db, company_id, owner = seeded
    po, phases, product_a, product_b = _two_line_po(db, company_id, owner)
    _publish_all(db, po)
    first_a = _so_lines(db, po, phase=phases[0], product=product_a)[0]
    _deliver(db, first_a, "40")

    progress = po_progress(db, po)
    by_no = {line["line_no"]: line for line in progress["lines"]}

    assert by_no[1]["ordered"] == Decimal("300")
    assert by_no[1]["scheduled"] == Decimal("300")
    assert by_no[1]["delivered"] == Decimal("40")
    assert by_no[1]["outstanding"] == Decimal("260")
    assert by_no[1]["next_delivery_date"] == date(2030, 7, 1)
    assert [row["delivery_date"] for row in by_no[1]["deliveries"]] == [
        date(2030, 7, 1),
        date(2030, 8, 1),
        date(2030, 9, 1),
    ]
    assert by_no[1]["deliveries"][0]["delivered"] == Decimal("40")
    assert by_no[1]["deliveries"][0]["area_group"] == "TOWER"

    assert by_no[2]["scheduled"] == Decimal("50")
    assert by_no[2]["schedule_gap"] == Decimal("-10")
    assert by_no[2]["delivered"] == Decimal("0")
    assert by_no[2]["outstanding"] == Decimal("60")

    totals = progress["totals"]
    assert totals["ordered"] == Decimal("360")
    assert totals["delivered"] == Decimal("40")
    assert totals["schedule_short_lines"] == 1

    areas = progress["areas"]
    assert [area["label"] for area in areas] == ["Level 1", "Level 2", "Level 3"]
    assert areas[0]["units"] == Decimal("120")
    assert areas[0]["delivered"] == Decimal("40")
    assert areas[0]["sales_orders"] and areas[0]["sales_orders"][0]["status"] == "published"


def test_a_draft_order_delivers_nothing_even_with_a_core_link(seeded):
    from app.services.project_po_progress_service import po_progress

    db, company_id, owner = seeded
    po, phases, product_a, _b = _two_line_po(db, company_id, owner)
    _deliver(db, _so_lines(db, po, phase=phases[0], product=product_a)[0], "40")

    progress = po_progress(db, po)

    assert progress["totals"]["delivered"] == Decimal("0")


def test_the_po_list_carries_ordered_delivered_and_next_delivery(seeded):
    """AC-O3."""
    from app.services import project_po_service as po_svc

    db, company_id, owner = seeded
    po, phases, product_a, _b = _two_line_po(db, company_id, owner)
    _publish_all(db, po)
    _deliver(db, _so_lines(db, po, phase=phases[0], product=product_a)[0], "40")

    row = po_svc.serialize_pos(db, [po])[0]

    assert row["ordered_units"] == Decimal("360")
    assert row["delivered_units"] == Decimal("40")
    assert row["next_delivery_date"] == date(2030, 7, 1)
    assert row["has_document"] is True


def test_moving_an_area_moves_its_draft_lines_and_undo_puts_them_back(seeded):
    """AC-D2 + AC-D3 (and D6: a line carrying a stale date takes the area's new one)."""
    from app.services.project_po_progress_service import change_area_date

    db, company_id, owner = seeded
    po, phases, _a, _b = _two_line_po(db, company_id, owner)
    area = phases[2]
    lines = _so_lines(db, po, phase=area)
    stale = lines[0]
    stale.delivery_date = date(2030, 3, 1)  # built from an older schedule
    db.flush()

    result = change_area_date(
        db, area, delivery_date=date(2030, 10, 15), actor_user_id=owner
    )

    assert area.delivery_date == date(2030, 10, 15)
    assert {line.delivery_date for line in _so_lines(db, po, phase=area)} == {date(2030, 10, 15)}
    assert result["moved_lines"] == len(lines)
    assert result["previous_date"] == date(2030, 9, 1)
    assert result["amendments"] == []
    # Other areas are untouched.
    assert {line.delivery_date for line in _so_lines(db, po, phase=phases[0])} == {date(2030, 7, 1)}

    change_area_date(
        db,
        area,
        delivery_date=result["previous_date"],
        actor_user_id=owner,
        restore_lines=result["previous_lines"],
    )

    assert area.delivery_date == date(2030, 9, 1)
    restored = {line.id: line.delivery_date for line in _so_lines(db, po, phase=area)}
    assert restored[stale.id] == date(2030, 3, 1)
    assert sorted(set(restored.values())) == [date(2030, 3, 1), date(2030, 9, 1)]


def test_a_published_order_is_not_rewritten_it_gets_an_amendment(seeded):
    """AC-D2: published lines keep their date; a DELAY amendment with its OCN is proposed."""
    from app.models.project_so import OrderChangeNotice, SOAmendment
    from app.services.project_po_progress_service import change_area_date

    db, company_id, owner = seeded
    po, phases, _a, _b = _two_line_po(db, company_id, owner)
    _publish_all(db, po)
    area = phases[1]
    before = {line.id: line.delivery_date for line in _so_lines(db, po, phase=area)}

    result = change_area_date(db, area, delivery_date=date(2030, 8, 20), actor_user_id=owner)

    after = {line.id: line.delivery_date for line in _so_lines(db, po, phase=area)}
    assert after == before
    assert result["moved_lines"] == 0
    assert len(result["amendments"]) == 1
    amendment_id = result["amendments"][0]["amendment_id"]
    assert amendment_id
    amendment = db.query(SOAmendment).filter(SOAmendment.id == amendment_id).one()
    assert amendment.from_version_kind == "area_date"
    rows = amendment.delta_json["rows"]
    assert len(rows) == len(before)
    assert {row["verb"] for row in rows} == {"DELAY"}
    assert {row["to_value"] for row in rows} == {"2030-08-20"}
    ocn = db.query(OrderChangeNotice).filter(OrderChangeNotice.id == amendment.ocn_id).one()
    assert ocn.source_document_kind == "none"


def test_undo_refuses_a_line_that_is_not_a_draft_line_on_the_area(seeded):
    from app.services.project_po_progress_service import change_area_date

    db, company_id, owner = seeded
    po, phases, _a, _b = _two_line_po(db, company_id, owner)
    other = _so_lines(db, po, phase=phases[0])[0]

    with pytest.raises(AppException) as caught:
        change_area_date(
            db,
            phases[1],
            delivery_date=date(2030, 8, 1),
            actor_user_id=owner,
            restore_lines=[{"id": other.id, "delivery_date": date(2001, 1, 1)}],
        )

    assert caught.value.status_code == 422
    assert caught.value.code == "area_date_restore_foreign_line"


# ------------------------------------------------------------------ D1 one line set


def test_a_scanned_po_refuses_hand_line_edits(seeded):
    from app.services import project_po_service as po_svc

    db, company_id, owner = seeded
    _project_row, po, _v, _s, _phase_row, _p = _one_line_po(db, company_id, owner)

    with pytest.raises(AppException) as caught:
        po_svc.save_po_document(db, po=po, payload={"lines": []})

    assert caught.value.status_code == 409
    assert caught.value.code == "po_lines_from_document"
    # A header-only save still works on a scanned PO.
    po_svc.save_po_document(db, po=po, payload={"notes": "called the site"})
    assert po.notes == "called the site"


def test_a_hand_keyed_po_keeps_its_line_editor(seeded):
    from app.services import project_po_service as po_svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    po = _po(db, project, party=_party(db, company_id))

    lines = po_svc.save_po_document(
        db,
        po=po,
        payload={"lines": [{"product_code": "SRTA-100", "unit_price": Decimal("1"), "quantity": 3}]},
    )

    assert len(lines) == 1


def test_the_new_routes_are_mounted():
    from app.api.v1.projects.schedules import router

    paths = {getattr(route, "path", "") for route in router.routes}
    assert "/purchase-orders/{po_id}/progress" in paths
    assert "/delivery-phases/{phase_id}/date" in paths


def test_the_sales_order_list_narrows_to_one_po(seeded):
    """The PO page's Sales orders tab lists that PO's orders only."""
    import uuid as _uuid

    from app.models.projects import Project

    db, company_id, owner = seeded
    po, _phases, _a, _b = _two_line_po(db, company_id, owner)
    project = db.query(Project).filter(Project.id == po.project_id).one()
    other_po = _po(db, project, party=_party(db, company_id))
    db.add(
        ProjectSalesOrder(
            id=str(_uuid.uuid4()),
            company_id=company_id,
            project_id=project.id,
            purchase_order_id=other_po.id,
            provisional_ref=f"ZZT-{_uuid.uuid4().hex[:8]}",
            status="draft",
        )
    )
    db.flush()

    rows, total = ProjectSODraftService(db).list_for_project(
        project.id, purchase_order_id=po.id
    )
    everything, all_total = ProjectSODraftService(db).list_for_project(project.id)

    assert total == len(_orders(db, po))
    assert {row.purchase_order_id for row in rows} == {po.id}
    assert all_total == total + 1


def test_an_adopted_order_on_the_area_is_named_not_rewritten(seeded):
    """Security review N1: an order adopted from AutoCount is neither rewritten nor amended
    here, and the result says so."""
    from app.services.project_po_progress_service import change_area_date

    db, company_id, owner = seeded
    po, phases, _a, _b = _two_line_po(db, company_id, owner)
    for order in _orders(db, po):
        order.status = "adopted"
    db.flush()
    area = phases[0]
    before = {line.id: line.delivery_date for line in _so_lines(db, po, phase=area)}

    result = change_area_date(db, area, delivery_date=date(2030, 7, 9), actor_user_id=owner)

    assert {line.id: line.delivery_date for line in _so_lines(db, po, phase=area)} == before
    assert result["amendments"] and all(row["refused"] for row in result["amendments"])
    assert all(row["amendment_id"] is None for row in result["amendments"])


def test_the_sales_order_list_refuses_a_malformed_po_filter(seeded):
    """Security review S1: a non-UUID filter is a clean client error, never a database
    error echoed back in a 500."""
    import asyncio

    from app.api.v1.projects.sales_orders import list_project_sales_orders

    db, company_id, owner = seeded
    po, _phases, _a, _b = _two_line_po(db, company_id, owner)

    with pytest.raises(AppException) as caught:
        asyncio.run(
            list_project_sales_orders(
                project_id=po.project_id,
                query=None,
                so_status=None,
                purchase_order_id="x",
                page=1,
                limit=50,
                sort="created_at",
                dir="desc",
                _user={"id": owner},
                db=db,
            )
        )
    assert caught.value.status_code in (404, 422)
    assert "uuid" not in str(caught.value.detail).lower()
