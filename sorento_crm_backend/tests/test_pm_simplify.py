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
