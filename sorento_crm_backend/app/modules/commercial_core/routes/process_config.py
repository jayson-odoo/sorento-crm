"""Commercial process configuration (admin) API."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_optional, require_permission, require_permission_with_api_key
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
)
from app.modules.commercial_core.schemas.commercial_process_config import (
    CommercialActivityTemplateCreate,
    CommercialActivityTemplateResponse,
    CommercialActivityTemplateUpdate,
    CommercialCheckpointTemplateCreate,
    CommercialCheckpointTemplateResponse,
    CommercialCheckpointTemplateUpdate,
    CommercialConfigStageCreate,
    CommercialConfigStageResponse,
    CommercialConfigStageUpdate,
    commercial_config_stage_response_from_workflow,
    CommercialProcessSettingsResponse,
    CommercialProcessSettingsUpdate,
    CommercialReminderDefaultCreate,
    CommercialReminderDefaultResponse,
    CommercialReminderDefaultUpdate,
    SelectOption,
)
from app.schemas.common import ListResponse
from app.modules.commercial_core.services import commercial_process_config_service as svc
from app.services.error_handler import AppException, handle_internal_error

logger = logging.getLogger(__name__)

router = APIRouter()


def _safe_select_empty():
    return {"data": [], "pagination": {"total": 0, "page": 1, "limit": 0}, "empty": True}


def _assignment_key_select(db: Session, key: str) -> list[dict]:
    row = db.query(CommercialProcessSettings).filter(CommercialProcessSettings.id == "default").first()
    ass = dict(row.assignment or {}) if row and isinstance(row.assignment, dict) else {}
    raw = ass.get(key)
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        label = str(item.get("label") or code).strip()
        if not code:
            continue
        out.append(SelectOption(code=code, label=label or code).model_dump())
    return out


def _select_rows(db: Session, model, code_attr: str, label_attr: str, *, active_only: bool = False):
    q = db.query(model)
    if active_only and hasattr(model, "is_active"):
        q = q.filter(model.is_active.is_(True))
    sort_col = getattr(model, "sort_order", None)
    code_col = getattr(model, code_attr)
    if sort_col is not None:
        q = q.order_by(sort_col, code_col)
    else:
        q = q.order_by(code_col)
    rows = q.all()
    return [SelectOption(code=getattr(r, code_attr), label=getattr(r, label_attr)).model_dump() for r in rows]


def _select_workflow_domain(db: Session, domain: str, *, active_only: bool = False):
    from app.models.workflow_stage import WorkflowStage

    q = db.query(WorkflowStage).filter(WorkflowStage.domain == domain)
    if active_only:
        q = q.filter(WorkflowStage.is_active.is_(True))
    rows = q.order_by(WorkflowStage.sort_order, WorkflowStage.code).all()
    return [SelectOption(code=r.code, label=r.label).model_dump() for r in rows]


def _workflow_stage_list_response(raw: dict) -> dict:
    """Map paginated WorkflowStage rows to CommercialConfigStageResponse payloads."""
    return {
        **raw,
        "data": [commercial_config_stage_response_from_workflow(r) for r in raw["data"]],
    }


# --- Tender stages ---
tender_router = APIRouter(prefix="/tender-stages", tags=["commercial-tender-stages"])


@tender_router.get("/", response_model=ListResponse[CommercialConfigStageResponse])
def list_tender_stages(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.tender_stages.view")),
    db: Session = Depends(get_db),
):
    try:
        return _workflow_stage_list_response(svc.list_tender_stages(db, page=page, limit=limit))
    except Exception as e:
        raise handle_internal_error(str(e))


@tender_router.get("/select")
def select_tender_stages(
    current_user: dict | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        data = _select_workflow_domain(db, WORKFLOW_DOMAIN_TENDER, active_only=True)
        return {"data": data, "pagination": {"total": len(data), "page": 1, "limit": len(data)}, "empty": len(data) == 0}
    except Exception as e:
        logger.exception("tender-stages/select: %s", e)
        return _safe_select_empty()


@tender_router.get("/by-code/{stage_code}", response_model=CommercialConfigStageResponse)
def get_tender_stage(
    stage_code: str,
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.tender_stages.view")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.get_tender_stage_by_code(db, stage_code))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@tender_router.post("/", response_model=CommercialConfigStageResponse, status_code=status.HTTP_201_CREATED)
def create_tender_stage(
    body: CommercialConfigStageCreate,
    _user: dict = Depends(require_permission("commercial_process_config.tender_stages.add")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.create_tender_stage(db, body))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@tender_router.put("/by-code/{stage_code}", response_model=CommercialConfigStageResponse)
def update_tender_stage(
    stage_code: str,
    body: CommercialConfigStageUpdate,
    _user: dict = Depends(require_permission("commercial_process_config.tender_stages.edit")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.update_tender_stage(db, stage_code, body))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@tender_router.delete("/by-code/{stage_code}", status_code=status.HTTP_200_OK)
def delete_tender_stage(
    stage_code: str,
    _user: dict = Depends(require_permission("commercial_process_config.tender_stages.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc.delete_tender_stage(db, stage_code)
        return {"message": "Tender stage deleted"}
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# --- Master quotation stages ---
mq_router = APIRouter(prefix="/master-quotation-stages", tags=["commercial-mq-stages"])


@mq_router.get("/", response_model=ListResponse[CommercialConfigStageResponse])
def list_mq_stages(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.master_quotation_stages.view")),
    db: Session = Depends(get_db),
):
    try:
        return _workflow_stage_list_response(svc.list_master_quotation_stages(db, page=page, limit=limit))
    except Exception as e:
        raise handle_internal_error(str(e))


@mq_router.get("/select")
def select_mq_stages(
    current_user: dict | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        data = _select_workflow_domain(db, WORKFLOW_DOMAIN_QUOTATION, active_only=True)
        return {"data": data, "pagination": {"total": len(data), "page": 1, "limit": len(data)}, "empty": len(data) == 0}
    except Exception as e:
        logger.exception("mq-stages/select: %s", e)
        return _safe_select_empty()


@mq_router.get("/by-code/{stage_code}", response_model=CommercialConfigStageResponse)
def get_mq_stage(
    stage_code: str,
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.master_quotation_stages.view")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.get_master_quotation_stage_by_code(db, stage_code))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@mq_router.post("/", response_model=CommercialConfigStageResponse, status_code=status.HTTP_201_CREATED)
def create_mq_stage(
    body: CommercialConfigStageCreate,
    _user: dict = Depends(require_permission("commercial_process_config.master_quotation_stages.add")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.create_master_quotation_stage(db, body))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@mq_router.put("/by-code/{stage_code}", response_model=CommercialConfigStageResponse)
def update_mq_stage(
    stage_code: str,
    body: CommercialConfigStageUpdate,
    _user: dict = Depends(require_permission("commercial_process_config.master_quotation_stages.edit")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.update_master_quotation_stage(db, stage_code, body))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@mq_router.delete("/by-code/{stage_code}", status_code=status.HTTP_200_OK)
def delete_mq_stage(
    stage_code: str,
    _user: dict = Depends(require_permission("commercial_process_config.master_quotation_stages.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc.delete_master_quotation_stage(db, stage_code)
        return {"message": "Master quotation stage deleted"}
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# --- Task statuses ---
task_router = APIRouter(prefix="/task-statuses", tags=["commercial-task-statuses"])


@task_router.get("/", response_model=ListResponse[CommercialConfigStageResponse])
def list_task_statuses(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.task_statuses.view")),
    db: Session = Depends(get_db),
):
    try:
        return _workflow_stage_list_response(svc.list_task_statuses(db, page=page, limit=limit))
    except Exception as e:
        raise handle_internal_error(str(e))


@task_router.get("/select")
def select_task_statuses(
    current_user: dict | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        data = _select_workflow_domain(db, WORKFLOW_DOMAIN_TASK, active_only=True)
        return {"data": data, "pagination": {"total": len(data), "page": 1, "limit": len(data)}, "empty": len(data) == 0}
    except Exception as e:
        logger.exception("task-statuses/select: %s", e)
        return _safe_select_empty()


@task_router.get("/by-code/{stage_code}", response_model=CommercialConfigStageResponse)
def get_task_status(
    stage_code: str,
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.task_statuses.view")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.get_task_status_by_code(db, stage_code))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@task_router.post("/", response_model=CommercialConfigStageResponse, status_code=status.HTTP_201_CREATED)
def create_task_status(
    body: CommercialConfigStageCreate,
    _user: dict = Depends(require_permission("commercial_process_config.task_statuses.add")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.create_task_status(db, body))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@task_router.put("/by-code/{stage_code}", response_model=CommercialConfigStageResponse)
def update_task_status(
    stage_code: str,
    body: CommercialConfigStageUpdate,
    _user: dict = Depends(require_permission("commercial_process_config.task_statuses.edit")),
    db: Session = Depends(get_db),
):
    try:
        return commercial_config_stage_response_from_workflow(svc.update_task_status(db, stage_code, body))
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@task_router.delete("/by-code/{stage_code}", status_code=status.HTTP_200_OK)
def delete_task_status(
    stage_code: str,
    _user: dict = Depends(require_permission("commercial_process_config.task_statuses.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc.delete_task_status(db, stage_code)
        return {"message": "Task status deleted"}
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# --- Activity templates ---
act_router = APIRouter(prefix="/activity-templates", tags=["commercial-activity-templates"])


@act_router.get("/", response_model=ListResponse[CommercialActivityTemplateResponse])
def list_activity_templates(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.activity_templates.view")),
    db: Session = Depends(get_db),
):
    try:
        return svc.list_activity_templates(db, page=page, limit=limit)
    except Exception as e:
        raise handle_internal_error(str(e))


@act_router.get("/select")
def select_activity_templates(
    current_user: dict | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        q = (
            db.query(CommercialActivityTemplate)
            .filter(CommercialActivityTemplate.is_active.is_(True))
            .order_by(CommercialActivityTemplate.name)
        )
        data = [
            SelectOption(code=r.name, label=r.name).model_dump()
            for r in q.all()
        ]
        return {"data": data, "pagination": {"total": len(data), "page": 1, "limit": len(data)}, "empty": len(data) == 0}
    except Exception as e:
        logger.exception("activity-templates/select: %s", e)
        return _safe_select_empty()


@act_router.get("/by-code/{template_code}", response_model=CommercialActivityTemplateResponse)
def get_activity_template(
    template_code: str,
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.activity_templates.view")),
    db: Session = Depends(get_db),
):
    try:
        return svc.get_activity_template_by_code(db, template_code)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@act_router.post("/", response_model=CommercialActivityTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_activity_template(
    body: CommercialActivityTemplateCreate,
    _user: dict = Depends(require_permission("commercial_process_config.activity_templates.add")),
    db: Session = Depends(get_db),
):
    try:
        return svc.create_activity_template(db, body)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@act_router.put("/by-code/{template_code}", response_model=CommercialActivityTemplateResponse)
def update_activity_template(
    template_code: str,
    body: CommercialActivityTemplateUpdate,
    _user: dict = Depends(require_permission("commercial_process_config.activity_templates.edit")),
    db: Session = Depends(get_db),
):
    try:
        return svc.update_activity_template(db, template_code, body)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@act_router.delete("/by-code/{template_code}", status_code=status.HTTP_200_OK)
def delete_activity_template(
    template_code: str,
    _user: dict = Depends(require_permission("commercial_process_config.activity_templates.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc.delete_activity_template(db, template_code)
        return {"message": "Activity template deleted"}
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# --- Reminder defaults ---
rem_router = APIRouter(prefix="/reminder-defaults", tags=["commercial-reminder-defaults"])


@rem_router.get("/", response_model=ListResponse[CommercialReminderDefaultResponse])
def list_reminder_defaults(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.reminder_defaults.view")),
    db: Session = Depends(get_db),
):
    try:
        return svc.list_reminder_defaults(db, page=page, limit=limit)
    except Exception as e:
        raise handle_internal_error(str(e))


@rem_router.get("/select")
def select_reminder_defaults(
    current_user: dict | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        q = db.query(CommercialReminderDefault).order_by(
            CommercialReminderDefault.sort_order, CommercialReminderDefault.context
        )
        data = [SelectOption(code=r.context, label=r.display_name).model_dump() for r in q.all()]
        return {"data": data, "pagination": {"total": len(data), "page": 1, "limit": len(data)}, "empty": len(data) == 0}
    except Exception as e:
        logger.exception("reminder-defaults/select: %s", e)
        return _safe_select_empty()


@rem_router.get("/by-context/{context}", response_model=CommercialReminderDefaultResponse)
def get_reminder_default(
    context: str,
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.reminder_defaults.view")),
    db: Session = Depends(get_db),
):
    try:
        return svc.get_reminder_default_by_context(db, context)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@rem_router.post("/", response_model=CommercialReminderDefaultResponse, status_code=status.HTTP_201_CREATED)
def create_reminder_default(
    body: CommercialReminderDefaultCreate,
    _user: dict = Depends(require_permission("commercial_process_config.reminder_defaults.add")),
    db: Session = Depends(get_db),
):
    try:
        return svc.create_reminder_default(db, body)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@rem_router.put("/by-context/{context}", response_model=CommercialReminderDefaultResponse)
def update_reminder_default(
    context: str,
    body: CommercialReminderDefaultUpdate,
    _user: dict = Depends(require_permission("commercial_process_config.reminder_defaults.edit")),
    db: Session = Depends(get_db),
):
    try:
        return svc.update_reminder_default(db, context, body)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@rem_router.delete("/by-context/{context}", status_code=status.HTTP_200_OK)
def delete_reminder_default(
    context: str,
    _user: dict = Depends(require_permission("commercial_process_config.reminder_defaults.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc.delete_reminder_default(db, context)
        return {"message": "Reminder default deleted"}
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# --- Checkpoint templates ---
ck_router = APIRouter(prefix="/tender-checkpoint-templates", tags=["commercial-checkpoint-templates"])


@ck_router.get("/", response_model=ListResponse[CommercialCheckpointTemplateResponse])
def list_checkpoints(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.tender_checkpoint_templates.view")),
    db: Session = Depends(get_db),
):
    try:
        return svc.list_checkpoint_templates(db, page=page, limit=limit)
    except Exception as e:
        raise handle_internal_error(str(e))


@ck_router.get("/select")
def select_checkpoints(
    current_user: dict | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        data = _select_rows(db, CommercialTenderCheckpointTemplate, "checkpoint_code", "name", active_only=True)
        return {"data": data, "pagination": {"total": len(data), "page": 1, "limit": len(data)}, "empty": len(data) == 0}
    except Exception as e:
        logger.exception("checkpoint-templates/select: %s", e)
        return _safe_select_empty()


@ck_router.get("/by-code/{checkpoint_code}", response_model=CommercialCheckpointTemplateResponse)
def get_checkpoint(
    checkpoint_code: str,
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.tender_checkpoint_templates.view")),
    db: Session = Depends(get_db),
):
    try:
        return svc.get_checkpoint_template_by_code(db, checkpoint_code)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@ck_router.post("/", response_model=CommercialCheckpointTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_checkpoint(
    body: CommercialCheckpointTemplateCreate,
    _user: dict = Depends(require_permission("commercial_process_config.tender_checkpoint_templates.add")),
    db: Session = Depends(get_db),
):
    try:
        return svc.create_checkpoint_template(db, body)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@ck_router.put("/by-code/{checkpoint_code}", response_model=CommercialCheckpointTemplateResponse)
def update_checkpoint(
    checkpoint_code: str,
    body: CommercialCheckpointTemplateUpdate,
    _user: dict = Depends(require_permission("commercial_process_config.tender_checkpoint_templates.edit")),
    db: Session = Depends(get_db),
):
    try:
        return svc.update_checkpoint_template(db, checkpoint_code, body)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@ck_router.delete("/by-code/{checkpoint_code}", status_code=status.HTTP_200_OK)
def delete_checkpoint(
    checkpoint_code: str,
    _user: dict = Depends(require_permission("commercial_process_config.tender_checkpoint_templates.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc.delete_checkpoint_template(db, checkpoint_code)
        return {"message": "Checkpoint template deleted"}
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# --- Process settings ---
settings_router = APIRouter(prefix="/settings", tags=["commercial-process-settings"])


@settings_router.get("/", response_model=CommercialProcessSettingsResponse)
def get_settings(
    _user: dict = Depends(require_permission_with_api_key("commercial_process_config.settings.view")),
    db: Session = Depends(get_db),
):
    try:
        return svc.get_process_settings(db)
    except Exception as e:
        raise handle_internal_error(str(e))


@settings_router.patch("/", response_model=CommercialProcessSettingsResponse)
def patch_settings(
    body: CommercialProcessSettingsUpdate,
    _user: dict = Depends(require_permission("commercial_process_config.settings.edit")),
    db: Session = Depends(get_db),
):
    try:
        return svc.update_process_settings(db, body)
    except AppException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@settings_router.get("/payment-terms/select")
def select_payment_terms(
    _user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        data = _assignment_key_select(db, "payment_terms")
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": len(data)},
            "empty": len(data) == 0,
        }
    except Exception as e:
        logger.exception("payment-terms/select: %s", e)
        return _safe_select_empty()


@settings_router.get("/tax-rates/select")
def select_tax_rates(
    _user: dict = Depends(require_permission("commercial_core.master_quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        data = _assignment_key_select(db, "tax_rates")
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": len(data)},
            "empty": len(data) == 0,
        }
    except Exception as e:
        logger.exception("tax-rates/select: %s", e)
        return _safe_select_empty()


_LEAD_QUALIFICATION_ASSIGNMENT_KEYS = frozenset(
    {
        "lead_states",
        "lead_countries",
        "lead_property_types",
        "lead_budget_ranges",
        "lead_sales_closure_confidence",
        "lead_sources",
        "lead_industries",
        "lead_contact_methods",
    }
)


@settings_router.get("/assignment-select/{key}")
def select_lead_qualification_assignment(
    key: str,
    _user: dict = Depends(require_permission("commercial_core.leads.view")),
    db: Session = Depends(get_db),
):
    """Code/label lists from process settings assignment (maintained on Process settings page)."""
    if key not in _LEAD_QUALIFICATION_ASSIGNMENT_KEYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid assignment key")
    try:
        data = _assignment_key_select(db, key)
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": len(data)},
            "empty": len(data) == 0,
        }
    except Exception as e:
        logger.exception("assignment-select/%s: %s", key, e)
        return _safe_select_empty()


router.include_router(tender_router)
router.include_router(mq_router)
router.include_router(task_router)
router.include_router(act_router)
router.include_router(rem_router)
router.include_router(ck_router)
router.include_router(settings_router)
