"""CRUD and helpers for commercial process configuration (admin)."""
from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, TypeVar

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.commercial_core.models import CommercialMasterQuotation, CommercialTender
from app.modules.commercial_activity.models import CommercialActivityTemplate
from app.modules.commercial_core.models_process_config import (
    CommercialProcessSettings,
    CommercialReminderDefault,
    CommercialTenderCheckpointTemplate,
)
from app.models.workflow_stage import (
    WORKFLOW_DOMAIN_QUOTATION,
    WORKFLOW_DOMAIN_TASK,
    WORKFLOW_DOMAIN_TENDER,
    WorkflowStage,
)
from app.modules.commercial_core.schemas.commercial_process_config import (
    CommercialActivityTemplateCreate,
    CommercialActivityTemplateUpdate,
    CommercialCheckpointTemplateCreate,
    CommercialCheckpointTemplateUpdate,
    CommercialConfigStageCreate,
    CommercialConfigStageUpdate,
    CommercialProcessSettingsUpdate,
    CommercialReminderDefaultCreate,
    CommercialReminderDefaultUpdate,
)
from app.services.error_handler import handle_conflict, handle_not_found, handle_validation_error

T = TypeVar("T")


def _paginate(q, page: int, limit: int) -> Dict[str, Any]:
    total = q.count()
    offset = (page - 1) * limit
    rows = q.offset(offset).limit(limit).all()
    return {
        "data": rows,
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


# --- Workflow stages (tender / MQ / task) ---
def _list_ws_domain(db: Session, domain: str, page: int, limit: int) -> Dict[str, Any]:
    q = db.query(WorkflowStage).filter(WorkflowStage.domain == domain).order_by(
        WorkflowStage.sort_order, WorkflowStage.code
    )
    return _paginate(q, page, limit)


def _get_ws_by_code(db: Session, domain: str, stage_code: str) -> WorkflowStage:
    row = (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain == domain,
            WorkflowStage.code == stage_code,
        )
        .one_or_none()
    )
    if row is None:
        raise handle_not_found("Stage", stage_code)
    return row


def _create_ws(db: Session, domain: str, data: CommercialConfigStageCreate) -> WorkflowStage:
    code = data.stage_code.strip()
    if db.query(WorkflowStage).filter(WorkflowStage.domain == domain, WorkflowStage.code == code).first():
        raise handle_conflict("Stage code already exists.")
    row = WorkflowStage(
        id=str(uuid.uuid4()),
        domain=domain,
        code=code,
        label=data.stage_name.strip(),
        description=data.description,
        sort_order=data.sort_order,
        is_terminal=data.is_terminal,
        allows_conversion=None,
        can_go_back=False,
        is_active=data.is_active,
        is_cancelled=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _update_ws(db: Session, domain: str, stage_code: str, data: CommercialConfigStageUpdate) -> WorkflowStage:
    row = _get_ws_by_code(db, domain, stage_code)
    patch = data.model_dump(exclude_unset=True)
    if "stage_name" in patch and patch["stage_name"] is not None:
        row.label = patch["stage_name"].strip()
    if "description" in patch:
        row.description = patch["description"]
    if "sort_order" in patch and patch["sort_order"] is not None:
        row.sort_order = patch["sort_order"]
    if "is_terminal" in patch and patch["is_terminal"] is not None:
        row.is_terminal = patch["is_terminal"]
    if "is_active" in patch and patch["is_active"] is not None:
        row.is_active = patch["is_active"]
    db.commit()
    db.refresh(row)
    return row


def _delete_ws(
    db: Session, domain: str, stage_code: str, *, in_use_check: Callable[[Session, str], bool]
) -> None:
    row = _get_ws_by_code(db, domain, stage_code)
    if in_use_check(db, row.code):
        raise handle_validation_error("Cannot delete a stage that is still in use.")
    db.delete(row)
    db.commit()


def _tender_stage_in_use(db: Session, stage_code: str) -> bool:
    return (
        db.query(CommercialTender)
        .filter(func.lower(CommercialTender.pipeline_stage) == func.lower(stage_code))
        .first()
        is not None
    )


def _mq_stage_in_use(db: Session, stage_code: str) -> bool:
    return (
        db.query(CommercialMasterQuotation)
        .join(
            WorkflowStage,
            CommercialMasterQuotation.quotation_stage_id == WorkflowStage.id,
        )
        .filter(
            WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
            func.lower(WorkflowStage.code) == func.lower(stage_code),
        )
        .first()
        is not None
    )


def list_tender_stages(db: Session, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    return _list_ws_domain(db, WORKFLOW_DOMAIN_TENDER, page, limit)


def get_tender_stage_by_code(db: Session, stage_code: str) -> WorkflowStage:
    return _get_ws_by_code(db, WORKFLOW_DOMAIN_TENDER, stage_code)


def create_tender_stage(db: Session, data: CommercialConfigStageCreate) -> WorkflowStage:
    return _create_ws(db, WORKFLOW_DOMAIN_TENDER, data)


def update_tender_stage(db: Session, stage_code: str, data: CommercialConfigStageUpdate) -> WorkflowStage:
    return _update_ws(db, WORKFLOW_DOMAIN_TENDER, stage_code, data)


def delete_tender_stage(db: Session, stage_code: str) -> None:
    _delete_ws(
        db,
        WORKFLOW_DOMAIN_TENDER,
        stage_code,
        in_use_check=lambda db, code: _tender_stage_in_use(db, code),
    )


def list_master_quotation_stages(db: Session, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    return _list_ws_domain(db, WORKFLOW_DOMAIN_QUOTATION, page, limit)


def get_master_quotation_stage_by_code(db: Session, stage_code: str) -> WorkflowStage:
    return _get_ws_by_code(db, WORKFLOW_DOMAIN_QUOTATION, stage_code)


def create_master_quotation_stage(db: Session, data: CommercialConfigStageCreate) -> WorkflowStage:
    return _create_ws(db, WORKFLOW_DOMAIN_QUOTATION, data)


def update_master_quotation_stage(
    db: Session, stage_code: str, data: CommercialConfigStageUpdate
) -> WorkflowStage:
    return _update_ws(db, WORKFLOW_DOMAIN_QUOTATION, stage_code, data)


def delete_master_quotation_stage(db: Session, stage_code: str) -> None:
    _delete_ws(
        db,
        WORKFLOW_DOMAIN_QUOTATION,
        stage_code,
        in_use_check=lambda db, code: _mq_stage_in_use(db, code),
    )


def list_task_statuses(db: Session, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    return _list_ws_domain(db, WORKFLOW_DOMAIN_TASK, page, limit)


def get_task_status_by_code(db: Session, stage_code: str) -> WorkflowStage:
    return _get_ws_by_code(db, WORKFLOW_DOMAIN_TASK, stage_code)


def create_task_status(db: Session, data: CommercialConfigStageCreate) -> WorkflowStage:
    return _create_ws(db, WORKFLOW_DOMAIN_TASK, data)


def update_task_status(db: Session, stage_code: str, data: CommercialConfigStageUpdate) -> WorkflowStage:
    return _update_ws(db, WORKFLOW_DOMAIN_TASK, stage_code, data)


def delete_task_status(db: Session, stage_code: str) -> None:
    _delete_ws(db, WORKFLOW_DOMAIN_TASK, stage_code, in_use_check=lambda _db, _code: False)


# --- Activity templates ---
def list_activity_templates(db: Session, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    q = db.query(CommercialActivityTemplate).order_by(CommercialActivityTemplate.name)
    return _paginate(q, page, limit)


def get_activity_template_by_code(db: Session, template_code: str) -> CommercialActivityTemplate:
    row = (
        db.query(CommercialActivityTemplate)
        .filter(CommercialActivityTemplate.name == template_code)
        .one_or_none()
    )
    if row is None:
        raise handle_not_found("Activity template", template_code)
    return row


def create_activity_template(db: Session, data: CommercialActivityTemplateCreate) -> CommercialActivityTemplate:
    if db.query(CommercialActivityTemplate).filter(CommercialActivityTemplate.name == data.name).first():
        raise handle_conflict("Template name already exists.")
    row = CommercialActivityTemplate(
        name=data.name,
        description=data.description,
        is_active=data.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_activity_template(
    db: Session, template_code: str, data: CommercialActivityTemplateUpdate
) -> CommercialActivityTemplate:
    row = get_activity_template_by_code(db, template_code)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


def delete_activity_template(db: Session, template_code: str) -> None:
    row = get_activity_template_by_code(db, template_code)
    db.delete(row)
    db.commit()


# --- Reminder defaults ---
def list_reminder_defaults(db: Session, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    q = db.query(CommercialReminderDefault).order_by(
        CommercialReminderDefault.sort_order, CommercialReminderDefault.context
    )
    return _paginate(q, page, limit)


def get_reminder_default_by_context(db: Session, context: str) -> CommercialReminderDefault:
    row = db.query(CommercialReminderDefault).filter(CommercialReminderDefault.context == context).one_or_none()
    if row is None:
        raise handle_not_found("Reminder default", context)
    return row


def create_reminder_default(db: Session, data: CommercialReminderDefaultCreate) -> CommercialReminderDefault:
    if db.query(CommercialReminderDefault).filter(CommercialReminderDefault.context == data.context).first():
        raise handle_conflict("Context already exists.")
    row = CommercialReminderDefault(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_reminder_default(db: Session, context: str, data: CommercialReminderDefaultUpdate) -> CommercialReminderDefault:
    row = get_reminder_default_by_context(db, context)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


def delete_reminder_default(db: Session, context: str) -> None:
    row = get_reminder_default_by_context(db, context)
    db.delete(row)
    db.commit()


# --- Checkpoint templates ---
def list_checkpoint_templates(db: Session, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    q = db.query(CommercialTenderCheckpointTemplate).order_by(
        CommercialTenderCheckpointTemplate.sort_order, CommercialTenderCheckpointTemplate.checkpoint_code
    )
    return _paginate(q, page, limit)


def get_checkpoint_template_by_code(db: Session, checkpoint_code: str) -> CommercialTenderCheckpointTemplate:
    row = (
        db.query(CommercialTenderCheckpointTemplate)
        .filter(CommercialTenderCheckpointTemplate.checkpoint_code == checkpoint_code)
        .one_or_none()
    )
    if row is None:
        raise handle_not_found("Checkpoint template", checkpoint_code)
    return row


def create_checkpoint_template(
    db: Session, data: CommercialCheckpointTemplateCreate
) -> CommercialTenderCheckpointTemplate:
    if (
        db.query(CommercialTenderCheckpointTemplate)
        .filter(CommercialTenderCheckpointTemplate.checkpoint_code == data.checkpoint_code)
        .first()
    ):
        raise handle_conflict("Checkpoint code already exists.")
    row = CommercialTenderCheckpointTemplate(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_checkpoint_template(
    db: Session, checkpoint_code: str, data: CommercialCheckpointTemplateUpdate
) -> CommercialTenderCheckpointTemplate:
    row = get_checkpoint_template_by_code(db, checkpoint_code)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


def delete_checkpoint_template(db: Session, checkpoint_code: str) -> None:
    row = get_checkpoint_template_by_code(db, checkpoint_code)
    db.delete(row)
    db.commit()


# --- Process settings (singleton) ---
SETTINGS_ID = "default"


def get_process_settings(db: Session) -> CommercialProcessSettings:
    row = db.query(CommercialProcessSettings).filter(CommercialProcessSettings.id == SETTINGS_ID).one_or_none()
    if row is None:
        row = CommercialProcessSettings(id=SETTINGS_ID, assignment={}, reminders={}, pricing_controls={})
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_process_settings(db: Session, data: CommercialProcessSettingsUpdate) -> CommercialProcessSettings:
    row = get_process_settings(db)
    if data.assignment is not None:
        row.assignment = data.assignment
    if data.reminders is not None:
        row.reminders = data.reminders
    if data.pricing_controls is not None:
        row.pricing_controls = data.pricing_controls
    db.commit()
    db.refresh(row)
    return row

