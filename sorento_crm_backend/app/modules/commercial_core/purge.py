"""Purge handler for the commercial_core module."""
import logging
from typing import Dict
from sqlalchemy.orm import Session

from app.modules.commercial_core.models import (
    CommercialLead,
    CommercialLeadNote,
    CommercialMasterQuotation,
    CommercialProject,
    CommercialQuotationRevision,
    CommercialSalesOrder,
    CommercialTender,
    CommercialTenderMilestone,
)
from app.models.workflow_stage import WorkflowStage

logger = logging.getLogger(__name__)


def _count_deleted(db: Session, model, label: str) -> int:
    n = db.query(model).delete(synchronize_session=False)
    logger.info("Purge %s: deleted %s rows", label, n)
    return n


def purge(db: Session) -> Dict[str, int]:
    """Commercial leads through sales orders (FK-safe order)."""
    out: Dict[str, int] = {}
    out["commercial_sales_orders"] = _count_deleted(db, CommercialSalesOrder, "commercial_sales_orders")
    out["commercial_quotation_revisions"] = _count_deleted(
        db, CommercialQuotationRevision, "commercial_quotation_revisions"
    )
    out["commercial_master_quotations"] = _count_deleted(
        db, CommercialMasterQuotation, "commercial_master_quotations"
    )
    out["commercial_tender_milestones"] = _count_deleted(
        db, CommercialTenderMilestone, "commercial_tender_milestones"
    )
    out["commercial_tenders"] = _count_deleted(db, CommercialTender, "commercial_tenders")
    out["commercial_projects"] = _count_deleted(db, CommercialProject, "commercial_projects")
    out["commercial_lead_notes"] = _count_deleted(db, CommercialLeadNote, "commercial_lead_notes")
    out["commercial_leads"] = _count_deleted(db, CommercialLead, "commercial_leads")
    n_ws = (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain.in_(("lead", "quotation", "tender", "task")),
        )
        .delete(synchronize_session=False)
    )
    logger.info("Purge workflow_stages (commercial domains): deleted %s rows", n_ws)
    out["workflow_stages_commercial_domains"] = n_ws
    return out
