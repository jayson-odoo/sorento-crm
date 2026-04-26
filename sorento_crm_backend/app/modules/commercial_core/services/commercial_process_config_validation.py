"""Optional validation hooks for commercial transactional APIs (pipeline codes, checkpoint seeding)."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.modules.commercial_core.models import CommercialTenderMilestone
from app.modules.commercial_core.models_process_config import (
    CommercialTenderCheckpointTemplate,
)
from app.models.workflow_stage import (
    WORKFLOW_DOMAIN_QUOTATION,
    WORKFLOW_DOMAIN_TENDER,
    WorkflowStage,
)


def is_active_tender_stage_code(db: Session, stage_code: str) -> bool:
    if not stage_code:
        return False
    row = (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain == WORKFLOW_DOMAIN_TENDER,
            WorkflowStage.code == stage_code,
            WorkflowStage.is_active.is_(True),
        )
        .first()
    )
    return row is not None


def is_active_master_quotation_stage_code(db: Session, stage_code: str) -> bool:
    if not stage_code:
        return False
    row = (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
            WorkflowStage.code == stage_code,
            WorkflowStage.is_active.is_(True),
        )
        .first()
    )
    return row is not None


def copy_checkpoint_templates_to_tender(
    db: Session,
    tender_id: str,
    *,
    only_active_templates: bool = True,
) -> List[CommercialTenderMilestone]:
    """
    Create milestone rows from checkpoint templates. Caller must commit.
    Returns new milestone ORM instances (added to session).
    """
    q = db.query(CommercialTenderCheckpointTemplate).order_by(CommercialTenderCheckpointTemplate.sort_order)
    if only_active_templates:
        q = q.filter(CommercialTenderCheckpointTemplate.is_active.is_(True))
    templates = q.all()
    created: List[CommercialTenderMilestone] = []
    for i, t in enumerate(templates):
        m = CommercialTenderMilestone(
            tender_id=tender_id,
            milestone_code=t.checkpoint_code,
            due_on=None,
            achieved_at=None,
            sort_order=t.sort_order if t.sort_order is not None else i * 10,
        )
        db.add(m)
        created.append(m)
    return created
