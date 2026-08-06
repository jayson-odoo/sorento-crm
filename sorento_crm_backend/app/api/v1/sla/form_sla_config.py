"""Form SLA configuration CRUD routes.

Configures, per form type and stage, which symbolic transition starts an SLA
tracker, marks it responded, and marks it resolved. Multi-stage chains link
via next_config_id.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import (
    get_current_user_or_api_key,
    require_permission,
)
from app.models.sla import FormSLAConfig, SLAPolicy
from app.services.uuid_path_param import validate_uuid_path
from app.schemas.sla import (
    FormSLAConfigCreate,
    FormSLAConfigUpdate,
    FormSLAConfigResponse,
)
from app.services.error_handler import (
    handle_internal_error,
    handle_not_found,
    handle_validation_error,
    handle_conflict,
)


router = APIRouter()


def _serialize(config: FormSLAConfig) -> dict:
    policy_code = None
    policy_name = None
    if config.policy is not None:
        policy_code = config.policy.code
        policy_name = config.policy.name
    next_stage_code = None
    if config.next_config is not None:
        next_stage_code = config.next_config.stage_code
    return {
        "id": str(config.id),
        "source_entity_type": config.source_entity_type,
        "stage_code": config.stage_code,
        "policy_id": str(config.policy_id),
        "agent_code": config.agent_code,
        "team_set_code": config.team_set_code,
        "start_event": config.start_event,
        "respond_event": config.respond_event,
        "resolve_event": config.resolve_event,
        "next_config_id": (
            str(config.next_config_id) if config.next_config_id is not None else None
        ),
        "advance_on_event": getattr(config, "advance_on_event", None),
        "is_active": bool(config.is_active),
        "created_at": config.created_at,
        "updated_at": config.updated_at,
        "policy_code": policy_code,
        "policy_name": policy_name,
        "next_stage_code": next_stage_code,
    }


@router.get("", response_model=list[FormSLAConfigResponse])
def list_form_sla_configs(
    source_entity_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(
        require_permission("sla_management.form_sla_config.view")
    ),
    db: Session = Depends(get_db),
):
    """List form SLA configs (filterable by form type / active state)."""
    try:
        q = db.query(FormSLAConfig)
        if source_entity_type:
            q = q.filter(FormSLAConfig.source_entity_type == source_entity_type)
        if is_active is not None:
            q = q.filter(FormSLAConfig.is_active.is_(is_active))
        rows = q.order_by(
            FormSLAConfig.source_entity_type.asc(),
            FormSLAConfig.stage_code.asc(),
        ).all()
        return [_serialize(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{config_id}", response_model=FormSLAConfigResponse)
def get_form_sla_config(
    config_id: str,
    current_user: dict = Depends(
        require_permission("sla_management.form_sla_config.view")
    ),
    db: Session = Depends(get_db),
):
    validate_uuid_path(config_id, resource="Form SLA Config")
    config = db.query(FormSLAConfig).filter(FormSLAConfig.id == config_id).first()
    if not config:
        raise handle_not_found("Form SLA Config", config_id)
    return _serialize(config)


def _validate_policy(db: Session, policy_id: str) -> None:
    policy = db.query(SLAPolicy).filter(SLAPolicy.id == policy_id).first()
    if not policy:
        raise handle_validation_error(f"SLA Policy not found: {policy_id}")


def _validate_next(db: Session, next_id: Optional[str], self_id: Optional[str]) -> None:
    if not next_id:
        return
    if self_id and next_id == self_id:
        raise handle_validation_error("next_config_id cannot reference itself.")
    nxt = db.query(FormSLAConfig).filter(FormSLAConfig.id == next_id).first()
    if not nxt:
        raise handle_validation_error(f"next_config_id not found: {next_id}")


@router.post("", response_model=FormSLAConfigResponse, status_code=201)
def create_form_sla_config(
    payload: FormSLAConfigCreate,
    current_user: dict = Depends(
        require_permission("sla_management.form_sla_config.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        _validate_policy(db, payload.policy_id)
        _validate_next(db, payload.next_config_id, None)
        if payload.is_active:
            existing = (
                db.query(FormSLAConfig)
                .filter(
                    FormSLAConfig.source_entity_type == payload.source_entity_type,
                    FormSLAConfig.stage_code == payload.stage_code,
                    FormSLAConfig.is_active.is_(True),
                )
                .first()
            )
            if existing:
                raise handle_conflict(
                    f"Active config already exists for {payload.source_entity_type}/"
                    f"{payload.stage_code}. Deactivate the existing one first."
                )
        config = FormSLAConfig(**payload.model_dump())
        db.add(config)
        db.commit()
        db.refresh(config)
        return _serialize(config)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.put("/{config_id}", response_model=FormSLAConfigResponse)
def update_form_sla_config(
    config_id: str,
    payload: FormSLAConfigUpdate,
    current_user: dict = Depends(
        require_permission("sla_management.form_sla_config.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(config_id, resource="Form SLA Config")
        config = (
            db.query(FormSLAConfig).filter(FormSLAConfig.id == config_id).first()
        )
        if not config:
            raise handle_not_found("Form SLA Config", config_id)
        update_data = payload.model_dump(exclude_unset=True)
        if "policy_id" in update_data:
            _validate_policy(db, update_data["policy_id"])
        if "next_config_id" in update_data:
            _validate_next(db, update_data["next_config_id"], config_id)
        # uniqueness on (source_entity_type, stage_code) when active
        new_active = update_data.get("is_active", config.is_active)
        new_type = update_data.get("source_entity_type", config.source_entity_type)
        new_stage = update_data.get("stage_code", config.stage_code)
        if new_active:
            collision = (
                db.query(FormSLAConfig)
                .filter(
                    FormSLAConfig.source_entity_type == new_type,
                    FormSLAConfig.stage_code == new_stage,
                    FormSLAConfig.is_active.is_(True),
                    FormSLAConfig.id != config_id,
                )
                .first()
            )
            if collision:
                raise handle_conflict(
                    f"Another active config already exists for {new_type}/{new_stage}."
                )
        for k, v in update_data.items():
            setattr(config, k, v)
        db.commit()
        db.refresh(config)
        return _serialize(config)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.delete("/{config_id}")
def delete_form_sla_config(
    config_id: str,
    current_user: dict = Depends(
        require_permission("sla_management.form_sla_config.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(config_id, resource="Form SLA Config")
        config = (
            db.query(FormSLAConfig).filter(FormSLAConfig.id == config_id).first()
        )
        if not config:
            raise handle_not_found("Form SLA Config", config_id)
        # Clear back-references so SET NULL fires
        db.query(FormSLAConfig).filter(
            FormSLAConfig.next_config_id == config_id
        ).update({"next_config_id": None})
        db.delete(config)
        db.commit()
        return {"message": "Form SLA config deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
