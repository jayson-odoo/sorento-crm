"""Tenders, milestones, pipeline stage validation, close/reopen, summary."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.commercial_core.models import (
    CommercialMasterQuotation,
    CommercialProject,
    CommercialTender,
    CommercialTenderLifecycle,
    CommercialTenderMilestone,
    CommercialTenderOutcome,
)
from app.models.workflow_stage import WORKFLOW_DOMAIN_TENDER, WorkflowStage
from app.models.user import User

def _normalize_close_outcome(raw: str) -> str:
    key = (raw or "").strip().lower()
    mapping = {
        "won": CommercialTenderOutcome.WON,
        "lost": CommercialTenderOutcome.LOST,
        "withdrawn": CommercialTenderOutcome.WITHDRAWN,
        "no_award": CommercialTenderOutcome.NO_AWARD,
        "cancelled": CommercialTenderOutcome.WITHDRAWN,
        "no_bid": CommercialTenderOutcome.NO_AWARD,
    }
    if key not in mapping:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid outcome; use won, lost, cancelled, no_bid, withdrawn, or no_award.",
        )
    return mapping[key]


def get_tender_by_code(db: Session, tender_code: str) -> CommercialTender:
    t = (
        db.query(CommercialTender)
        .filter(CommercialTender.tender_code == tender_code.strip())
        .options(joinedload(CommercialTender.project).joinedload(CommercialProject.lead))
        .first()
    )
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    return t


def list_tender_process_stages(db: Session, *, active_only: bool = True) -> List[WorkflowStage]:
    q = (
        db.query(WorkflowStage)
        .filter(WorkflowStage.domain == WORKFLOW_DOMAIN_TENDER)
        .order_by(WorkflowStage.sort_order.asc(), WorkflowStage.code.asc())
    )
    if active_only:
        q = q.filter(WorkflowStage.is_active.is_(True))
    return q.all()


def validate_pipeline_stage_code(db: Session, stage_code: Optional[str]) -> None:
    if not stage_code or not str(stage_code).strip():
        return
    code = str(stage_code).strip()
    row = (
        db.query(WorkflowStage)
        .filter(
            WorkflowStage.domain == WORKFLOW_DOMAIN_TENDER,
            WorkflowStage.code == code,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown tender pipeline stage code")
    if not row.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tender pipeline stage is inactive")


def list_tenders(
    db: Session,
    *,
    project_id: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Tuple[List[CommercialTender], int]:
    q = db.query(CommercialTender)
    if project_id:
        q = q.filter(CommercialTender.project_id == project_id)
    total = q.count()
    rows = (
        q.order_by(CommercialTender.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return rows, total


def create_tender(
    db: Session,
    *,
    project_id: str,
    tender_code: str,
    title: str,
    owner_user_id: Optional[str] = None,
    forecast_amount: Optional[Decimal] = None,
    forecast_currency: Optional[str] = None,
    pipeline_stage: Optional[str] = None,
    expected_close_on: Optional[date] = None,
) -> CommercialTender:
    exists = db.query(CommercialTender).filter(CommercialTender.tender_code == tender_code.strip()).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tender code already exists")
    pj = db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
    if not pj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if owner_user_id:
        u = db.query(User).filter(User.id == owner_user_id).first()
        if not u:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner user not found")
    if pipeline_stage:
        validate_pipeline_stage_code(db, pipeline_stage)
    t = CommercialTender(
        project_id=project_id,
        tender_code=tender_code.strip(),
        title=title.strip(),
        owner_user_id=owner_user_id.strip() if owner_user_id else None,
        forecast_amount=forecast_amount,
        forecast_currency=forecast_currency.strip()[:3] if forecast_currency else None,
        pipeline_stage=pipeline_stage.strip() if pipeline_stage else None,
        expected_close_on=expected_close_on,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def update_tender(db: Session, tender_code: str, fields: Dict[str, Any]) -> CommercialTender:
    t = get_tender_by_code(db, tender_code)
    if t.tender_lifecycle == CommercialTenderLifecycle.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a closed tender")
    if "title" in fields and fields["title"] is not None:
        t.title = str(fields["title"]).strip()
    if "owner_user_id" in fields:
        ou = fields["owner_user_id"]
        if ou:
            u = db.query(User).filter(User.id == ou).first()
            if not u:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner user not found")
            t.owner_user_id = ou
        else:
            t.owner_user_id = None
    if "forecast_amount" in fields:
        t.forecast_amount = fields["forecast_amount"]
    if "forecast_currency" in fields:
        fc = fields["forecast_currency"]
        t.forecast_currency = str(fc).strip()[:3] if fc else None
    if "pipeline_stage" in fields:
        ps = fields["pipeline_stage"]
        if ps:
            validate_pipeline_stage_code(db, str(ps))
        t.pipeline_stage = str(ps).strip() if ps else None
    if "expected_close_on" in fields:
        t.expected_close_on = fields["expected_close_on"]
    db.commit()
    db.refresh(t)
    return t


def delete_tender(db: Session, tender_code: str) -> None:
    t = get_tender_by_code(db, tender_code)
    db.delete(t)
    db.commit()


def close_tender(
    db: Session,
    tender_code: str,
    *,
    outcome: str,
    winning_master_quotation_id: Optional[str] = None,
    outcome_notes: Optional[str] = None,
) -> CommercialTender:
    t = get_tender_by_code(db, tender_code)
    if t.tender_lifecycle == CommercialTenderLifecycle.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tender is already closed")
    norm = _normalize_close_outcome(outcome)
    if norm == CommercialTenderOutcome.WON:
        if not winning_master_quotation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="winning_master_quotation_id is required when outcome is won",
            )
        mq = (
            db.query(CommercialMasterQuotation)
            .filter(
                CommercialMasterQuotation.id == winning_master_quotation_id,
                CommercialMasterQuotation.tender_id == t.id,
            )
            .first()
        )
        if not mq:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Winning quotation not found on this tender")
        t.winning_master_quotation_id = winning_master_quotation_id
    else:
        t.winning_master_quotation_id = None
    t.tender_outcome = norm
    t.tender_lifecycle = CommercialTenderLifecycle.CLOSED
    t.closed_at = datetime.utcnow()
    if outcome_notes is not None:
        t.outcome_notes = outcome_notes
    db.commit()
    db.refresh(t)
    return t


def reopen_tender(db: Session, tender_code: str) -> CommercialTender:
    t = get_tender_by_code(db, tender_code)
    if t.tender_lifecycle != CommercialTenderLifecycle.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tender is not closed")
    t.tender_lifecycle = CommercialTenderLifecycle.OPEN
    t.tender_outcome = CommercialTenderOutcome.PENDING
    t.closed_at = None
    t.winning_master_quotation_id = None
    t.outcome_notes = None
    db.commit()
    db.refresh(t)
    return t


def tender_summary(db: Session, tender_code: str) -> Dict[str, Any]:
    t = get_tender_by_code(db, tender_code)
    milestones = db.query(CommercialTenderMilestone).filter(CommercialTenderMilestone.tender_id == t.id).all()
    achieved = sum(1 for m in milestones if m.achieved_at)
    mqs = db.query(CommercialMasterQuotation).filter(CommercialMasterQuotation.tender_id == t.id).all()
    path_counts = Counter(m.path_role for m in mqs)
    stage_rows = (
        db.query(CommercialMasterQuotation.quotation_stage_id, func.count())
        .filter(CommercialMasterQuotation.tender_id == t.id)
        .group_by(CommercialMasterQuotation.quotation_stage_id)
        .all()
    )
    return {
        "tender_code": t.tender_code,
        "title": t.title,
        "tender_lifecycle": t.tender_lifecycle,
        "tender_outcome": t.tender_outcome,
        "pipeline_value_amount": str(t.forecast_amount) if t.forecast_amount is not None else None,
        "pipeline_value_currency": t.forecast_currency,
        "in_open_pipeline": t.tender_lifecycle == CommercialTenderLifecycle.OPEN,
        "milestone_total": len(milestones),
        "milestone_achieved": achieved,
        "master_quotation_count": len(mqs),
        "master_quotation_path_roles": dict(path_counts),
        "master_quotation_stage_id_counts": {str(sid): c for sid, c in stage_rows},
    }


def list_milestones(db: Session, tender_code: str) -> List[CommercialTenderMilestone]:
    t = get_tender_by_code(db, tender_code)
    return (
        db.query(CommercialTenderMilestone)
        .filter(CommercialTenderMilestone.tender_id == t.id)
        .order_by(CommercialTenderMilestone.sort_order.asc(), CommercialTenderMilestone.milestone_code.asc())
        .all()
    )


def create_milestone(
    db: Session,
    tender_code: str,
    *,
    milestone_code: str,
    due_on: Optional[date] = None,
    sort_order: int = 0,
) -> CommercialTenderMilestone:
    t = get_tender_by_code(db, tender_code)
    if t.tender_lifecycle == CommercialTenderLifecycle.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot add milestones to a closed tender")
    m = CommercialTenderMilestone(
        tender_id=t.id,
        milestone_code=milestone_code.strip(),
        due_on=due_on,
        sort_order=sort_order,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def update_milestone(
    db: Session,
    milestone_id: str,
    *,
    milestone_code: Optional[str] = None,
    due_on: Optional[date] = None,
    achieved_at: Optional[datetime] = None,
    sort_order: Optional[int] = None,
) -> CommercialTenderMilestone:
    m = db.query(CommercialTenderMilestone).filter(CommercialTenderMilestone.id == milestone_id).first()
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    tender = db.query(CommercialTender).filter(CommercialTender.id == m.tender_id).first()
    if tender and tender.tender_lifecycle == CommercialTenderLifecycle.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit milestones on a closed tender")
    if milestone_code is not None:
        m.milestone_code = milestone_code.strip()
    if due_on is not None:
        m.due_on = due_on
    if achieved_at is not None:
        m.achieved_at = achieved_at
    if sort_order is not None:
        m.sort_order = sort_order
    db.commit()
    db.refresh(m)
    return m


def delete_milestone(db: Session, milestone_id: str) -> None:
    m = db.query(CommercialTenderMilestone).filter(CommercialTenderMilestone.id == milestone_id).first()
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found")
    tender = db.query(CommercialTender).filter(CommercialTender.id == m.tender_id).first()
    if tender and tender.tender_lifecycle == CommercialTenderLifecycle.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete milestones on a closed tender")
    db.delete(m)
    db.commit()


def get_project_brief(db: Session, project_id: str) -> CommercialProject:
    p = db.query(CommercialProject).filter(CommercialProject.id == project_id).options(joinedload(CommercialProject.lead)).first()
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return p


def owner_display(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        return None
    return (u.name and u.name.strip()) or (u.email and u.email.strip()) or None
