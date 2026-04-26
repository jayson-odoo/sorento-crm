"""Admin CRUD for workflow_stages across domains."""
from __future__ import annotations

import uuid
import re
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.commercial_core.models import CommercialLead, CommercialMasterQuotation, CommercialTask
from app.models.order import Order
from app.modules.commercial_core.models import CommercialProject
from app.models.workflow_stage import (
    WORKFLOW_DOMAIN_LEAD,
    WORKFLOW_DOMAIN_ORDER,
    WORKFLOW_DOMAIN_PROJECT,
    WORKFLOW_DOMAIN_QUOTATION,
    WORKFLOW_DOMAIN_TASK,
    WORKFLOW_DOMAIN_TENDER,
    WorkflowStage,
)
from app.modules.commercial_core.schemas.unified_workflow_stage import UnifiedWorkflowStageCreate, UnifiedWorkflowStageUpdate
from app.modules.commercial_core.services.commercial_process_config_service import _mq_stage_in_use, _tender_stage_in_use
from app.services.error_handler import handle_conflict, handle_not_found, handle_validation_error


_VALID_DOMAINS = frozenset(
    {
        WORKFLOW_DOMAIN_LEAD,
        WORKFLOW_DOMAIN_QUOTATION,
        WORKFLOW_DOMAIN_TENDER,
        WORKFLOW_DOMAIN_TASK,
        WORKFLOW_DOMAIN_ORDER,
        WORKFLOW_DOMAIN_PROJECT,
    }
)
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _normalize_color_hex(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    color = raw.strip()
    if not color:
        return None
    if not _HEX_COLOR_RE.match(color):
        raise handle_validation_error("Color must be a valid hex value like #E7000B.")
    return color.upper()


def list_workflow_stages(
    db: Session,
    *,
    domain: Optional[str] = None,
    include_inactive: bool = False,
) -> List[WorkflowStage]:
    q = db.query(WorkflowStage)
    if domain:
        q = q.filter(WorkflowStage.domain == domain.strip())
    if not include_inactive:
        q = q.filter(WorkflowStage.is_active.is_(True))
    return q.order_by(WorkflowStage.domain, WorkflowStage.sort_order, WorkflowStage.code).all()


def get_workflow_stage(db: Session, stage_id: str) -> Optional[WorkflowStage]:
    return db.query(WorkflowStage).filter(WorkflowStage.id == stage_id).first()


def create_workflow_stage(db: Session, data: UnifiedWorkflowStageCreate) -> WorkflowStage:
    dom = data.domain.strip()
    if dom not in _VALID_DOMAINS:
        raise handle_validation_error(f"Invalid domain: {dom}")
    code = data.code.strip()
    if db.query(WorkflowStage).filter(WorkflowStage.domain == dom, WorkflowStage.code == code).first():
        raise handle_conflict("Stage code already exists for this domain.")
    row = WorkflowStage(
        id=str(uuid.uuid4()),
        domain=dom,
        code=code,
        label=data.label.strip(),
        color_hex=_normalize_color_hex(data.color_hex),
        description=data.description,
        sort_order=data.sort_order,
        is_terminal=data.is_terminal,
        allows_conversion=data.allows_conversion,
        can_go_back=data.can_go_back,
        is_active=data.is_active,
        is_cancelled=data.is_cancelled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_workflow_stage(db: Session, stage_id: str, data: UnifiedWorkflowStageUpdate) -> WorkflowStage:
    row = get_workflow_stage(db, stage_id)
    if not row:
        raise handle_not_found("Workflow stage", stage_id)
    patch = data.model_dump(exclude_unset=True)
    if "label" in patch and patch["label"] is not None:
        row.label = patch["label"].strip()
    if "description" in patch:
        row.description = patch["description"]
    if "color_hex" in patch:
        row.color_hex = _normalize_color_hex(patch["color_hex"])
    if "sort_order" in patch and patch["sort_order"] is not None:
        row.sort_order = patch["sort_order"]
    if "is_terminal" in patch and patch["is_terminal"] is not None:
        row.is_terminal = patch["is_terminal"]
    if "allows_conversion" in patch:
        row.allows_conversion = patch["allows_conversion"]
    if "can_go_back" in patch and patch["can_go_back"] is not None:
        row.can_go_back = patch["can_go_back"]
    if "is_active" in patch and patch["is_active"] is not None:
        row.is_active = patch["is_active"]
    if "is_cancelled" in patch and patch["is_cancelled"] is not None:
        row.is_cancelled = patch["is_cancelled"]
    db.commit()
    db.refresh(row)
    return row


def _task_status_code_in_use(db: Session, stage_code: str) -> bool:
    return (
        db.query(CommercialTask)
        .filter(func.lower(CommercialTask.status) == func.lower(stage_code))
        .first()
        is not None
    )


def _lead_stage_id_in_use(db: Session, stage_id: str) -> bool:
    return db.query(CommercialLead).filter(CommercialLead.lead_stage_id == stage_id).first() is not None


def _mq_stage_id_in_use(db: Session, stage_id: str) -> bool:
    q1 = (
        db.query(CommercialMasterQuotation)
        .filter(CommercialMasterQuotation.quotation_stage_id == stage_id)
        .first()
    )
    if q1:
        return True
    if hasattr(CommercialMasterQuotation, "price_approval_target_stage_id"):
        q2 = (
            db.query(CommercialMasterQuotation)
            .filter(CommercialMasterQuotation.price_approval_target_stage_id == stage_id)
            .first()
        )
        return q2 is not None
    return False


def _order_status_id_in_use(db: Session, stage_id: str) -> bool:
    return db.query(Order).filter(Order.order_status_id == stage_id).first() is not None


def _project_stage_id_in_use(db: Session, stage_id: str) -> bool:
    return db.query(CommercialProject).filter(CommercialProject.project_stage_id == stage_id).first() is not None


def _workflow_stage_in_use(db: Session, row: WorkflowStage) -> bool:
    dom = row.domain
    code = row.code
    sid = str(row.id)
    if dom == WORKFLOW_DOMAIN_LEAD:
        return _lead_stage_id_in_use(db, sid)
    if dom == WORKFLOW_DOMAIN_QUOTATION:
        return _mq_stage_in_use(db, code)
    if dom == WORKFLOW_DOMAIN_TENDER:
        return _tender_stage_in_use(db, code)
    if dom == WORKFLOW_DOMAIN_TASK:
        return _task_status_code_in_use(db, code)
    if dom == WORKFLOW_DOMAIN_ORDER:
        return _order_status_id_in_use(db, sid)
    if dom == WORKFLOW_DOMAIN_PROJECT:
        return _project_stage_id_in_use(db, sid)
    return False


def delete_workflow_stage(db: Session, stage_id: str) -> None:
    row = get_workflow_stage(db, stage_id)
    if not row:
        raise handle_not_found("Workflow stage", stage_id)
    if _workflow_stage_in_use(db, row):
        raise handle_validation_error("Cannot delete a stage that is still in use.")
    db.delete(row)
    db.commit()
