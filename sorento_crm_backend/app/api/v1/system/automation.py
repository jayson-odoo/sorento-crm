"""Automation CRUD + run-now + runs API."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.email_template import EmailTemplate
from app.schemas.automation import (
    AutomationCreate,
    AutomationResponse,
    AutomationRunNowResponse,
    AutomationRunResponse,
    AutomationToggleRequest,
    AutomationUpdate,
    TriggerCatalog,
    TriggerSpec,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT, SuccessResponse
from app.services import automation_triggers
from app.services.automation_service import AutomationService

router = APIRouter()


def _hydrate(row, db: Session) -> AutomationResponse:
    out = AutomationResponse.model_validate(row)
    template = (
        db.query(EmailTemplate).filter(EmailTemplate.id == row.email_template_id).first()
    )
    if template:
        out = out.model_copy(update={"email_template_name": str(getattr(template, "name", ""))})
    return out


@router.get("/automation/triggers/catalog", response_model=TriggerCatalog)
def get_trigger_catalog(
    current_user: dict = Depends(require_permission("automation.automations.view")),
):
    return TriggerCatalog(
        triggers=[
            TriggerSpec(
                type=spec.type,
                label=spec.label,
                description=spec.description,
                config_schema=spec.config_schema,
                fact_sources=list(spec.fact_sources),
                supports_grouping=spec.supports_grouping,
            )
            for spec in automation_triggers.list_specs()
        ]
    )


@router.get("/automation/automations", response_model=ListResponse[AutomationResponse])
def list_automations(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    current_user: dict = Depends(require_permission("automation.automations.view")),
    db: Session = Depends(get_db),
):
    rows, total = AutomationService(db).list(
        page=page, limit=limit, query=query, enabled=enabled
    )
    return {
        "data": [_hydrate(r, db) for r in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


@router.get("/automation/automations/{automation_id}", response_model=AutomationResponse)
def get_automation(
    automation_id: str,
    current_user: dict = Depends(require_permission("automation.automations.view")),
    db: Session = Depends(get_db),
):
    row = AutomationService(db).get(automation_id)
    if not row:
        from app.services.error_handler import AppException

        raise AppException(status_code=404, message="Automation not found")
    return _hydrate(row, db)


@router.post("/automation/automations", response_model=AutomationResponse, status_code=201)
def create_automation(
    payload: AutomationCreate,
    current_user: dict = Depends(require_permission("automation.automations.add")),
    db: Session = Depends(get_db),
):
    data = payload.model_dump()
    row = AutomationService(db).create(
        data,
        user_id=str(current_user.get("id")) if current_user else None,
    )
    return _hydrate(row, db)


@router.put("/automation/automations/{automation_id}", response_model=AutomationResponse)
def update_automation(
    automation_id: str,
    payload: AutomationUpdate,
    current_user: dict = Depends(require_permission("automation.automations.edit")),
    db: Session = Depends(get_db),
):
    row = AutomationService(db).update(
        automation_id, payload.model_dump(exclude_unset=True)
    )
    return _hydrate(row, db)


@router.post(
    "/automation/automations/{automation_id}/toggle",
    response_model=AutomationResponse,
)
def toggle_automation(
    automation_id: str,
    payload: AutomationToggleRequest,
    current_user: dict = Depends(require_permission("automation.automations.edit")),
    db: Session = Depends(get_db),
):
    row = AutomationService(db).toggle(automation_id, enabled=payload.enabled)
    return _hydrate(row, db)


@router.delete(
    "/automation/automations/{automation_id}",
    response_model=SuccessResponse,
)
def delete_automation(
    automation_id: str,
    current_user: dict = Depends(require_permission("automation.automations.delete")),
    db: Session = Depends(get_db),
):
    AutomationService(db).delete(automation_id)
    return {"message": "Automation deleted"}


@router.post(
    "/automation/automations/{automation_id}/run",
    response_model=AutomationRunNowResponse,
)
def run_automation_now(
    automation_id: str,
    current_user: dict = Depends(require_permission("automation.automations.run")),
    db: Session = Depends(get_db),
):
    result = AutomationService(db).run_now(automation_id)
    return AutomationRunNowResponse(
        run_id=str(result["run_id"]),
        status=str(result["status"]),
        recipients_attempted=int(result.get("recipients_attempted", 0)),
        summary=result.get("summary"),
    )


@router.get(
    "/automation/automations/{automation_id}/runs",
    response_model=ListResponse[AutomationRunResponse],
)
def list_automation_runs(
    automation_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    current_user: dict = Depends(require_permission("automation.automations.view")),
    db: Session = Depends(get_db),
):
    rows, total = AutomationService(db).list_runs(automation_id, page=page, limit=limit)
    return {
        "data": [AutomationRunResponse.model_validate(r) for r in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }
