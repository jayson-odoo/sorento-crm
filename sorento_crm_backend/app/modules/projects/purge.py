"""Delete every row the `projects` module owns, when it is uninstalled with purge (ADR-0009).

Discovered, not registered: ``app.modules.runtime.discovery.discover_module_purge_handlers``
picks this file up because it is ``app/modules/projects/purge.py`` and exposes ``purge(db)``,
and ``app.services.module_purge_service`` merges it onto the key ``projects`` additively. There
is no line to add to the hardcoded ``MODULE_PURGE_HANDLERS`` dict, which is the point: the
module carries its own uninstall story.

Two rules govern what is in here, both from ADR-0009:

* **Module-owned tables only, and the model file is what says so.** 35 of the 47 tables carry
  the ``project_`` prefix; the other 12 predate the convention and are just as owned:
  ``so_amendments``, ``order_change_notices``, ``so_draft_findings``, ``so_line_allocations``,
  ``allocation_claims``, ``delivery_schedules``, ``delivery_schedule_versions``,
  ``delivery_schedule_cells``, ``customer_item_code_map``, ``quotation_templates``,
  ``quotation_signatures`` and ``price_floor_rules``. Ownership is therefore "declared in
  ``app/models/projects.py`` or ``app/models/project_so.py``" - which is exactly what
  ``tests/test_projects_module_purge_invariants.py`` asserts - and the prefix is the naming
  convention for NEW tables, not the membership test. Nothing outside the module reads any
  of them.
* **Core rows are never touched.** The ``sales_orders`` the demand feed created stay, and so
  do complaints, purchase requests, customers, attachments and statuses. The two core-to-module
  foreign keys (``complaints.project_id``, ``purchase_requests.project_id``) go NULL through
  ``ON DELETE SET NULL`` when the project row dies. That is the mechanism; purge does not
  reach across the boundary to do it by hand.

Deletes go through the ORM model classes rather than raw table names, so a table rename moves
both sides at once. ``project_order_inquiries`` was ``order_inquiries`` until recently and the
Python names (``OrderInquiry`` / ``OrderInquiryRow``) did not move with it, which is exactly the
kind of drift a hardcoded string list absorbs silently.

``PURGE_ORDER`` is children-first over the REAL foreign key graph, not alphabetical. Most of
those FKs are ``CASCADE`` and would take the children anyway, but every table gets its own
statement so the returned counts tell an operator what was actually removed rather than
under-reporting whatever the database quietly swept up. Four ``RESTRICT`` edges make the order
load-bearing and are marked inline below; get one of them wrong and the uninstall fails
half-way through, with the rows it already deleted gone.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Type

from sqlalchemy.orm import Session

from app.models.project_so import (
    AllocationClaim,
    CustomerItemCodeMap,
    DeliverySchedule,
    DeliveryScheduleCell,
    DeliveryScheduleVersion,
    OrderChangeNotice,
    OrderInquiry,
    OrderInquiryRow,
    ProjectDeliveryPhase,
    ProjectPOAnnotation,
    ProjectPOLine,
    ProjectPOVersion,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    ProjectSODivergence,
    ProjectSODivergenceLine,
    SOAmendment,
    SODraftFinding,
    SOLineAllocation,
)
from app.models.projects import (
    PriceFloorRule,
    Project,
    ProjectBrand,
    ProjectCollaborator,
    ProjectLead,
    ProjectParty,
    ProjectPurchaseOrder,
    ProjectPurchaseOrderLine,
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationIssue,
    ProjectQuotationIssueScope,
    ProjectQuotationLine,
    ProjectQuotationVersion,
    ProjectSalesProfile,
    ProjectSample,
    ProjectSeries,
    ProjectSeriesCategory,
    ProjectSeriesProduct,
    ProjectStakeholder,
    ProjectTakeoverRequest,
    ProjectTask,
    ProjectTemplate,
    ProjectTemplateRole,
    ProjectTemplateTask,
    ProjectType,
    QuotationSignature,
    QuotationTemplate,
)

logger = logging.getLogger(__name__)


#: Every module-owned table, children first. Read off the foreign keys declared on the models.
PURGE_ORDER: List[Type] = [
    # --- sales order side: divergences, inquiries and amendments hang off the SO -------
    ProjectSODivergenceLine,
    ProjectSODivergence,
    OrderInquiryRow,
    OrderInquiry,
    SOAmendment,
    # so_amendments.ocn_id points here, so the notice outlives the amendment by one step.
    OrderChangeNotice,
    SODraftFinding,
    # so_line_allocations.claim_id points at a claim: allocations first, claims after.
    SOLineAllocation,
    AllocationClaim,
    ProjectSalesOrderLine,
    # RESTRICT on project_sales_orders.project_id: this MUST precede Project.
    ProjectSalesOrder,
    # --- delivery schedules and the phases they populate -------------------------------
    DeliveryScheduleCell,
    DeliveryScheduleVersion,
    DeliverySchedule,
    ProjectDeliveryPhase,
    # --- the customer PO and its scanned documents -------------------------------------
    ProjectPOAnnotation,
    ProjectPOLine,
    ProjectPOVersion,
    ProjectPurchaseOrderLine,
    ProjectPurchaseOrder,
    ProjectSample,
    # --- quotations: issues reference scopes and versions, documents sit under them -----
    ProjectQuotationIssueScope,
    ProjectQuotationIssue,
    ProjectQuotationLine,
    ProjectQuotationVersion,
    ProjectQuotation,
    ProjectQuotationDocument,
    # Signatures are referenced by documents and issues, so they go once those are gone.
    QuotationSignature,
    QuotationTemplate,
    PriceFloorRule,
    # --- catalogue the quotations priced from -------------------------------------------
    ProjectSeriesProduct,
    ProjectSeriesCategory,
    ProjectSeries,
    # --- everything hanging directly off a project --------------------------------------
    ProjectTask,
    ProjectTemplateTask,
    ProjectTakeoverRequest,
    ProjectCollaborator,
    # RESTRICT on project_stakeholders.role_id: this MUST precede ProjectTemplateRole.
    ProjectStakeholder,
    ProjectBrand,
    ProjectSalesProfile,
    CustomerItemCodeMap,
    # RESTRICT on projects.developer_party_id / type_id / template_id: Project MUST precede
    # ProjectParty, ProjectType and ProjectTemplate.
    Project,
    # RESTRICT on project_leads.developer_party_id: leads MUST precede ProjectParty. After
    # Project rather than before it, so a lead is never detached from a registration that is
    # about to be deleted anyway.
    ProjectLead,
    ProjectTemplateRole,
    # RESTRICT on project_templates.type_id: templates MUST precede ProjectType.
    ProjectTemplate,
    ProjectType,
    ProjectParty,
]


def _count_deleted(db: Session, model: Type) -> int:
    label = model.__tablename__
    n = db.query(model).delete(synchronize_session=False)
    logger.info("Purge %s: deleted %s rows", label, n)
    return n


def purge(db: Session) -> Dict[str, int]:
    """Empty every module-owned table. Returns ``{table_name: rows_deleted}``.

    Tables that were already empty report zero rather than being omitted: an operator reading
    the uninstall result needs to see what was CONSIDERED, not only what happened to be there.
    The caller commits.
    """
    return {model.__tablename__: _count_deleted(db, model) for model in PURGE_ORDER}
