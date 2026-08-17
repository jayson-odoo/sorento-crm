"""Uninstalling the `projects` module with purge must empty its own tables and NOTHING else.

ADR-0009 settled two things this file pins:

* the module owes a purge handler at ``app/modules/projects/purge.py``, picked up by the
  additive discovery in ``app/services/module_purge_service.py`` rather than by a new
  hardcoded entry, and
* purge deletes rows from MODULE-OWNED tables only. The two core-to-module foreign keys
  (``complaints.project_id``, ``purchase_requests.project_id``) go NULL through
  ``ON DELETE SET NULL`` when the project row dies. That is the mechanism, and a complaint
  is a legal record that must outlive the pursuit it was attached to.

Labels are asserted through ``__tablename__`` rather than as string literals: the handler
deletes via ORM model classes, so a table rename moves both sides at once and a test that
hardcoded the old name would be the only thing left holding it.
"""
from __future__ import annotations

import pytest

from app.models.base import set_company_scope
from app.models.complaints import Complaint
from app.models.project_so import (
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.projects import (
    Project,
    ProjectLead,
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationLine,
    ProjectQuotationVersion,
)
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


def _seed(db) -> dict:
    """A minimal chain from lead to order inquiry, plus a complaint pointing at the project."""
    lead = ProjectLead(
        lead_code=unique_code("lead"),
        title="ZZT Tower Lead",
        normalised_title="zzt tower lead",
    )
    db.add(lead)
    db.flush()

    project = Project(
        project_code=unique_code("proj"),
        title="ZZT Tower",
        normalised_title=unique_code("zzt tower"),
        lead_id=lead.id,
    )
    db.add(project)
    db.flush()

    document = ProjectQuotationDocument(
        project_id=project.id,
        document_no=unique_code("Q"),
    )
    db.add(document)
    db.flush()

    quotation = ProjectQuotation(
        project_id=project.id,
        document_id=document.id,
        scope_label="ZZT house units",
    )
    db.add(quotation)
    db.flush()

    version = ProjectQuotationVersion(quotation_id=quotation.id, version_no=1)
    db.add(version)
    db.flush()

    line = ProjectQuotationLine(
        version_id=version.id,
        description_snapshot="ZZT basin",
        unit_price=100,
        quantity=2,
        line_total=200,
    )
    db.add(line)
    db.flush()

    sales_order = ProjectSalesOrder(
        project_id=project.id,
        provisional_ref=unique_code("SO"),
    )
    db.add(sales_order)
    db.flush()

    so_line = ProjectSalesOrderLine(
        project_sales_order_id=sales_order.id,
        line_no=1,
        qty=2,
        quotation_line_id=line.id,
    )
    db.add(so_line)
    db.flush()

    inquiry = OrderInquiry(project_sales_order_id=sales_order.id)
    db.add(inquiry)
    db.flush()

    inquiry_row = OrderInquiryRow(
        order_inquiry_id=inquiry.id,
        so_line_id=so_line.id,
        qty=2,
        verb="ORDER",
    )
    db.add(inquiry_row)

    complaint = Complaint(
        complaint_number=unique_code("CMP"),
        project_id=project.id,
        project_title="ZZT Tower",
        customer_name="ZZT Buyer",
        status="submitted",
    )
    db.add(complaint)
    db.commit()

    return {
        "lead": lead.id,
        "project": project.id,
        "document": document.id,
        "quotation": quotation.id,
        "version": version.id,
        "line": line.id,
        "sales_order": sales_order.id,
        "so_line": so_line.id,
        "inquiry": inquiry.id,
        "inquiry_row": inquiry_row.id,
        "complaint": complaint.id,
    }


def test_purge_empties_every_module_owned_table(db):
    from app.modules.projects.purge import PURGE_ORDER, purge

    _seed(db)

    purge(db)
    db.commit()
    db.expire_all()

    left = {m.__table__.fullname: db.query(m).count() for m in PURGE_ORDER}
    assert left == {m.__table__.fullname: 0 for m in PURGE_ORDER}


def test_purge_counts_name_the_tables_it_emptied(db):
    from app.modules.projects.purge import PURGE_ORDER, purge

    _seed(db)

    counts = purge(db)
    db.commit()

    # One entry per module-owned table, keyed by the SCHEMA-QUALIFIED physical name
    # (ADR-0011). Seven of these bare names are also core tables the purge leaves
    # alone, and an operator reading `sales_orders: 1` could not tell which book was
    # emptied.
    assert set(counts) == {m.__table__.fullname for m in PURGE_ORDER}
    assert counts[Project.__table__.fullname] == 1
    assert counts[ProjectLead.__table__.fullname] == 1
    assert counts[ProjectQuotationDocument.__table__.fullname] == 1
    assert counts[ProjectQuotation.__table__.fullname] == 1
    assert counts[ProjectQuotationVersion.__table__.fullname] == 1
    assert counts[ProjectQuotationLine.__table__.fullname] == 1
    assert counts[ProjectSalesOrder.__table__.fullname] == 1
    assert counts[ProjectSalesOrderLine.__table__.fullname] == 1
    assert counts[OrderInquiry.__table__.fullname] == 1
    assert counts[OrderInquiryRow.__table__.fullname] == 1
    # Untouched tables still report, as zero: the operator sees what was considered.
    # Keys are schema-qualified so `projects.sales_orders` above cannot be read as
    # core's order book (ADR-0011).
    assert counts["projects.parties"] == 0


def test_purge_keeps_the_complaint_and_nulls_its_project_id(db):
    """The core row survives; the FK column goes NULL through ON DELETE SET NULL."""
    from app.modules.projects.purge import purge

    seeded = _seed(db)

    purge(db)
    db.commit()
    db.expire_all()

    complaint = db.query(Complaint).filter(Complaint.id == seeded["complaint"]).one()
    assert complaint.project_id is None
    # Everything else about it is intact, including the typed-in project name that
    # kept working before the FK existed.
    assert complaint.project_title == "ZZT Tower"
    assert complaint.customer_name == "ZZT Buyer"


def test_discovery_wires_the_handler_onto_the_projects_module_key(db):
    """purge_module_data(db, "projects") must resolve without a hardcoded registry entry."""
    from app.modules.projects.purge import purge as projects_purge
    from app.services import module_purge_service

    module_purge_service._merge_discovered_handlers()
    assert module_purge_service.MODULE_PURGE_HANDLERS["projects"] is projects_purge

    _seed(db)
    counts = module_purge_service.purge_module_data(db, "projects")
    db.commit()

    assert counts[Project.__table__.fullname] == 1
    assert db.query(Project).count() == 0
