"""Kanban columns, filters, and pipeline dashboard for commercial_core."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from app.modules.commercial_core.models import (
    CommercialLead,
    CommercialMasterQuotation,
    CommercialProject,
    CommercialTask,
    CommercialTender,
    CommercialTenderOutcome,
    CommercialTenderLifecycle,
)
from app.models.order import Customer
from app.modules.commercial_activity.models import (
    CommercialActivityTaskStatus,
    CommercialQuotationActivityTask,
)
from app.models.user import User
from app.models.workflow_stage import (
    WORKFLOW_DOMAIN_LEAD,
    WORKFLOW_DOMAIN_QUOTATION,
    WORKFLOW_DOMAIN_TASK,
    WORKFLOW_DOMAIN_TENDER,
    WorkflowStage,
)


def _norm_key(v: Optional[str]) -> str:
    s = (v or "").strip()
    return s if s else "__none__"


class CommercialPipelineService:
    def __init__(self, db: Session):
        self.db = db

    def get_stage_config(self) -> Dict[str, Any]:
        lead_rows = (
            self.db.query(WorkflowStage)
            .filter(WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD)
            .order_by(WorkflowStage.sort_order, WorkflowStage.code)
            .all()
        )
        tender_rows = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_TENDER,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order, WorkflowStage.code)
            .all()
        )
        mq_rows = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order, WorkflowStage.code)
            .all()
        )
        pt_rows = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_TASK,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order, WorkflowStage.code)
            .all()
        )
        at_rows = (
            self.db.query(CommercialActivityTaskStatus)
            .filter(CommercialActivityTaskStatus.is_active.is_(True))
            .order_by(CommercialActivityTaskStatus.sort_order, CommercialActivityTaskStatus.code)
            .all()
        )

        def _lead_s(r: WorkflowStage) -> Dict[str, Any]:
            return {
                "code": r.code,
                "label": r.label,
                "sort_order": r.sort_order,
                "is_terminal": r.is_terminal,
            }

        def _cfg_tender(r: WorkflowStage) -> Dict[str, Any]:
            return {
                "code": r.code,
                "label": r.label,
                "sort_order": r.sort_order,
                "is_terminal": r.is_terminal,
            }

        def _cfg_mq(r: WorkflowStage) -> Dict[str, Any]:
            return {
                "code": r.code,
                "label": r.label,
                "sort_order": r.sort_order,
                "is_terminal": r.is_terminal,
            }

        def _cfg_pt(r: WorkflowStage) -> Dict[str, Any]:
            return {
                "code": r.code,
                "label": r.label,
                "sort_order": r.sort_order,
                "is_terminal": r.is_terminal,
            }

        def _cfg_at(r: CommercialActivityTaskStatus) -> Dict[str, Any]:
            return {
                "code": r.code,
                "label": r.label,
                "sort_order": r.sort_order,
                "is_terminal": r.is_terminal,
            }

        return {
            "lead_stages": [_lead_s(x) for x in lead_rows],
            "tender_stages": [_cfg_tender(x) for x in tender_rows],
            "mq_execution_states": [_cfg_mq(x) for x in mq_rows],
            "pipeline_task_statuses": [_cfg_pt(x) for x in pt_rows],
            "activity_task_statuses": [_cfg_at(x) for x in at_rows],
        }

    def _mine_scope_tender(self, uid: str):
        return or_(CommercialTender.owner_user_id == uid, CommercialProject.owner_user_id == uid)

    def list_leads_kanban(
        self,
        *,
        user_id: str,
        scope: str,
        stage_code: Optional[str] = None,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
        stages = (
            self.db.query(WorkflowStage)
            .filter(WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD)
            .order_by(WorkflowStage.sort_order, WorkflowStage.code)
            .all()
        )
        order = [s.code for s in stages]
        cols: Dict[str, List[Dict[str, Any]]] = {c: [] for c in order}

        q = self.db.query(CommercialLead).options(
            joinedload(CommercialLead.lead_stage),
            joinedload(CommercialLead.owner),
        )
        if scope == "mine":
            q = q.filter(CommercialLead.owner_user_id == user_id)
        if stage_code:
            ls = aliased(WorkflowStage)
            q = q.join(ls, ls.id == CommercialLead.lead_stage_id).filter(
                ls.domain == WORKFLOW_DOMAIN_LEAD,
                ls.code == stage_code,
            )

        for lead in q.order_by(CommercialLead.updated_at.desc()).limit(500):
            code = lead.lead_stage.code if lead.lead_stage else "__none__"
            if code not in cols:
                cols[code] = []
                if code not in order:
                    order.append(code)
            cols[code].append(
                {
                    "lead_code": lead.lead_code,
                    "title": lead.title,
                    "stage_code": code,
                    "owner_name": lead.owner.name if lead.owner else None,
                }
            )
        return cols, order

    def list_tenders_kanban(
        self,
        *,
        user_id: str,
        scope: str,
        pipeline_stage: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
        tender_stage_rows = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_TENDER,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order, WorkflowStage.code)
            .all()
        )
        order = [r.code for r in tender_stage_rows] if tender_stage_rows else []
        cols: Dict[str, List[Dict[str, Any]]] = {c: [] for c in order}

        q = (
            self.db.query(CommercialTender)
            .options(
                joinedload(CommercialTender.owner),
                joinedload(CommercialTender.project).joinedload(CommercialProject.owner),
            )
            .join(CommercialProject, CommercialProject.id == CommercialTender.project_id)
        )
        if scope == "mine":
            q = q.filter(self._mine_scope_tender(user_id))
        if pipeline_stage:
            q = q.filter(CommercialTender.pipeline_stage == pipeline_stage)
        if outcome:
            q = q.filter(CommercialTender.tender_outcome == outcome)

        for t in q.order_by(CommercialTender.updated_at.desc()).limit(500):
            key = _norm_key(t.pipeline_stage)
            if key not in cols:
                cols[key] = []
                if key not in order:
                    order.append(key)
            owner = t.owner
            if owner is None and t.project and t.project.owner:
                owner = t.project.owner
            cols[key].append(
                {
                    "tender_code": t.tender_code,
                    "title": t.title,
                    "pipeline_stage": t.pipeline_stage,
                    "forecast_amount": t.forecast_amount,
                    "forecast_currency": t.forecast_currency,
                    "expected_close_on": t.expected_close_on,
                    "tender_outcome": t.tender_outcome,
                    "owner_name": owner.name if owner else None,
                }
            )
        return cols, order

    def list_master_quotations_kanban(
        self,
        *,
        user_id: str,
        scope: str,
        execution_state: Optional[str] = None,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
        mq_stage_rows = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order, WorkflowStage.code)
            .all()
        )
        order = [r.code for r in mq_stage_rows] if mq_stage_rows else []
        cols: Dict[str, List[Dict[str, Any]]] = {c: [] for c in order}

        q = (
            self.db.query(CommercialMasterQuotation)
            .options(
                joinedload(CommercialMasterQuotation.tender).joinedload(CommercialTender.project),
                joinedload(CommercialMasterQuotation.quotation_stage),
                joinedload(CommercialMasterQuotation.current_working_revision),
            )
            .join(CommercialTender, CommercialTender.id == CommercialMasterQuotation.tender_id)
            .join(CommercialProject, CommercialProject.id == CommercialTender.project_id)
        )
        if scope == "mine":
            q = q.filter(self._mine_scope_tender(user_id))
        if execution_state:
            mqs = aliased(WorkflowStage)
            q = q.join(mqs, mqs.id == CommercialMasterQuotation.quotation_stage_id).filter(
                mqs.domain == WORKFLOW_DOMAIN_QUOTATION,
                mqs.code == execution_state,
            )

        for mq in q.order_by(CommercialMasterQuotation.updated_at.desc()).limit(800):
            st = mq.quotation_stage
            stage_code = st.code if st else ""
            key = _norm_key(stage_code)
            if key not in cols:
                cols[key] = []
                if key not in order:
                    order.append(key)
            tender = mq.tender
            salesperson_name = None
            rev = mq.current_working_revision
            if rev and isinstance(rev.pricing_snapshot, dict):
                meta = rev.pricing_snapshot.get("quotation_meta")
                if isinstance(meta, dict):
                    sid = meta.get("salesperson_user_id")
                    if sid:
                        u = self.db.query(User).filter(User.id == str(sid)).first()
                        if u:
                            salesperson_name = ((u.name or "").strip() or u.email) or None
            wr_num = (
                int(rev.revision_number)
                if rev is not None and getattr(rev, "revision_number", None) is not None
                else None
            )
            cols[key].append(
                {
                    "tender_code": tender.tender_code if tender else "",
                    "quotation_code": mq.quotation_code,
                    "current_working_revision_number": wr_num,
                    "title": mq.title,
                    "execution_state": stage_code,
                    "path_role": mq.path_role,
                    "salesperson_name": salesperson_name,
                }
            )
        return cols, order

    def list_master_quotations_table(
        self,
        *,
        user_id: str,
        scope: str,
        page: int = 1,
        limit: int = 50,
        search: Optional[str] = None,
        owner_user_id: Optional[str] = None,
        quotation_stage_code: Optional[str] = None,
    ) -> Tuple[List[CommercialMasterQuotation], int]:
        """Paginated master quotations joined to project / lead / customer for list screens."""
        page = max(1, page)
        limit = min(max(1, limit), 200)

        q = (
            self.db.query(CommercialMasterQuotation)
            .join(CommercialTender, CommercialTender.id == CommercialMasterQuotation.tender_id)
            .join(CommercialProject, CommercialProject.id == CommercialTender.project_id)
            .outerjoin(CommercialLead, CommercialLead.id == CommercialProject.lead_id)
            .outerjoin(Customer, Customer.id == CommercialLead.customer_id)
        )

        if scope == "mine":
            q = q.filter(self._mine_scope_tender(user_id))

        if owner_user_id and owner_user_id.strip():
            q = q.filter(CommercialMasterQuotation.owner_user_id == owner_user_id.strip())

        if quotation_stage_code and quotation_stage_code.strip():
            mq_st = aliased(WorkflowStage)
            q = (
                q.join(mq_st, mq_st.id == CommercialMasterQuotation.quotation_stage_id)
                .filter(
                    mq_st.domain == WORKFLOW_DOMAIN_QUOTATION,
                    mq_st.code == quotation_stage_code.strip(),
                )
            )

        term = (search or "").strip()
        if term:
            like = f"%{term}%"
            q = q.filter(
                or_(
                    CommercialMasterQuotation.quotation_code.ilike(like),
                    CommercialMasterQuotation.title.ilike(like),
                    CommercialTender.tender_code.ilike(like),
                    CommercialProject.title.ilike(like),
                    CommercialLead.lead_code.ilike(like),
                    Customer.customer_name.ilike(like),
                )
            )

        total = int(q.count())

        rows = (
            q            .options(
                joinedload(CommercialMasterQuotation.tender)
                .joinedload(CommercialTender.project)
                .joinedload(CommercialProject.lead)
                .joinedload(CommercialLead.customer),
                joinedload(CommercialMasterQuotation.quotation_stage),
                joinedload(CommercialMasterQuotation.owner),
                joinedload(CommercialMasterQuotation.current_working_revision),
            )
            .order_by(CommercialMasterQuotation.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return rows, int(total)

    def list_tasks_kanban(
        self,
        *,
        user_id: str,
        scope: str,
        overdue_only: bool = False,
        due_soon_only: bool = False,
        due_soon_days: int = 7,
        include_activity: bool = True,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
        pt_rows = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_TASK,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order, WorkflowStage.code)
            .all()
        )
        order = [r.code for r in pt_rows] if pt_rows else ["open", "in_progress", "blocked", "done"]
        cols: Dict[str, List[Dict[str, Any]]] = {c: [] for c in order}

        today = date.today()
        soon = today + timedelta(days=due_soon_days)

        q = self.db.query(CommercialTask).options(
            joinedload(CommercialTask.tender),
            joinedload(CommercialTask.lead),
        )
        if scope == "mine":
            q = q.filter(CommercialTask.owner_user_id == user_id)
        if overdue_only:
            q = q.filter(CommercialTask.due_on.isnot(None), CommercialTask.due_on < today)
        elif due_soon_only:
            q = q.filter(CommercialTask.due_on.isnot(None), CommercialTask.due_on >= today, CommercialTask.due_on <= soon)

        for row in q.order_by(CommercialTask.due_on.asc().nullslast(), CommercialTask.updated_at.desc()).limit(500):
            key = _norm_key(row.status)
            if key not in cols:
                cols[key] = []
                if key not in order:
                    order.append(key)
            cols[key].append(
                {
                    "kind": "crm",
                    "id": str(row.id),
                    "title": row.title,
                    "status_code": row.status,
                    "due_on": row.due_on,
                    "due_at": None,
                    "tender_code": row.tender.tender_code if row.tender else None,
                    "quotation_code": None,
                    "lead_code": row.lead.lead_code if row.lead else None,
                }
            )

        if include_activity:
            aq = (
                self.db.query(CommercialQuotationActivityTask)
                .options(
                    joinedload(CommercialQuotationActivityTask.status),
                    joinedload(CommercialQuotationActivityTask.master_quotation).joinedload(
                        CommercialMasterQuotation.tender
                    ),
                )
                .join(CommercialMasterQuotation, CommercialMasterQuotation.id == CommercialQuotationActivityTask.master_quotation_id)
                .join(CommercialTender, CommercialTender.id == CommercialMasterQuotation.tender_id)
                .join(CommercialProject, CommercialProject.id == CommercialTender.project_id)
                .filter(CommercialQuotationActivityTask.deleted_at.is_(None))
            )
            if scope == "mine":
                aq = aq.filter(
                    or_(
                        CommercialQuotationActivityTask.assignee_user_id == user_id,
                        self._mine_scope_tender(user_id),
                    )
                )
            if overdue_only:
                aq = aq.filter(
                    CommercialQuotationActivityTask.due_at.isnot(None),
                    CommercialQuotationActivityTask.due_at < datetime.combine(today, datetime.max.time()),
                )
            for row in aq.order_by(CommercialQuotationActivityTask.due_at.asc().nullslast()).limit(500):
                code = row.status.code if row.status else "__none__"
                if code not in cols:
                    cols[code] = []
                    if code not in order:
                        order.append(code)
                mq = row.master_quotation
                tender = mq.tender if mq else None
                cols[code].append(
                    {
                        "kind": "activity",
                        "id": str(row.id),
                        "title": row.title,
                        "status_code": code,
                        "due_on": row.due_at.date() if row.due_at else None,
                        "due_at": row.due_at,
                        "tender_code": tender.tender_code if tender else None,
                        "quotation_code": mq.quotation_code if mq else None,
                        "lead_code": None,
                    }
                )

        return cols, order

    def _allowed_lead_stage_codes(self) -> set:
        return {
            r[0]
            for r in self.db.query(WorkflowStage.code)
            .filter(WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD)
            .all()
        }

    def _allowed_tender_pipeline_stages(self) -> set:
        rows = (
            self.db.query(WorkflowStage.code)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_TENDER,
                WorkflowStage.is_active.is_(True),
            )
            .all()
        )
        return {r[0] for r in rows}

    def _allowed_mq_execution(self) -> set:
        rows = (
            self.db.query(WorkflowStage.code)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
                WorkflowStage.is_active.is_(True),
            )
            .all()
        )
        return {r[0] for r in rows}

    def _allowed_pipeline_task_status(self) -> set:
        rows = (
            self.db.query(WorkflowStage.code)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_TASK,
                WorkflowStage.is_active.is_(True),
            )
            .all()
        )
        return {r[0] for r in rows}

    def patch_lead_stage(self, *, lead_code: str, stage_code: str) -> None:
        allowed = self._allowed_lead_stage_codes()
        if allowed and stage_code not in allowed:
            raise ValueError(f"Invalid lead stage code: {stage_code}")
        stage = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                WorkflowStage.code == stage_code,
            )
            .one_or_none()
        )
        if not stage:
            raise ValueError("Lead stage not found.")
        lead = self.db.query(CommercialLead).filter(CommercialLead.lead_code == lead_code).one_or_none()
        if not lead:
            raise ValueError("Lead not found.")
        lead.lead_stage_id = stage.id
        self.db.commit()

    def patch_tender_pipeline(self, *, tender_code: str, pipeline_stage: Optional[str]) -> None:
        allowed = self._allowed_tender_pipeline_stages()
        if pipeline_stage is not None and allowed and pipeline_stage not in allowed:
            raise ValueError(f"Invalid tender pipeline stage: {pipeline_stage}")
        t = self.db.query(CommercialTender).filter(CommercialTender.tender_code == tender_code).one_or_none()
        if not t:
            raise ValueError("Tender not found.")
        t.pipeline_stage = pipeline_stage
        self.db.commit()

    def patch_master_quotation_execution(
        self, *, tender_code: str, quotation_code: str, execution_state: str, actor_user_id: str
    ) -> Dict[str, Any]:
        """execution_state is the master quotation stage_code (configurable catalogue)."""
        allowed = self._allowed_mq_execution()
        if allowed and execution_state not in allowed:
            raise ValueError(f"Invalid quotation stage code: {execution_state}")
        mq = (
            self.db.query(CommercialMasterQuotation)
            .options(joinedload(CommercialMasterQuotation.tender))
            .join(CommercialTender, CommercialTender.id == CommercialMasterQuotation.tender_id)
            .filter(
                CommercialTender.tender_code == tender_code,
                CommercialMasterQuotation.quotation_code == quotation_code,
            )
            .one_or_none()
        )
        if not mq:
            raise ValueError("Master quotation not found.")
        from app.modules.commercial_core.services.commercial_quotation_price_policy import apply_master_quotation_stage_change

        result = apply_master_quotation_stage_change(self.db, mq, execution_state, actor_user_id)
        if result.get("rerouted_for_approval") and mq.pricing_approver_user_id:
            self._notify_pricing_approval_request(mq)
        self.db.commit()
        return result

    def _notify_pricing_approval_request(self, mq: CommercialMasterQuotation) -> None:
        uid = (mq.pricing_approver_user_id or "").strip()
        if not uid:
            return
        try:
            from app.config import settings
            from app.services.notification_service import NotificationService
            from app.services.pricing_approval_token import mint_mq_pricing_approval_token

            t = mq.tender
            tc = t.tender_code if t else ""
            base = (getattr(settings, "public_api_base_url", None) or "http://127.0.0.1:8000").rstrip("/")
            try:
                tok = mint_mq_pricing_approval_token(str(mq.id), uid)
                approve_url = f"{base}/api/v1/commercial/public/master-quotations/pricing-approval/email-consume?token={tok}&approve=true"
                reject_url = f"{base}/api/v1/commercial/public/master-quotations/pricing-approval/email-consume?token={tok}&approve=false"
                link_block = f"\n\nApprove: {approve_url}\nDecline: {reject_url}"
            except Exception:
                link_block = ""
            body = (
                f"{tc} / {mq.quotation_code}: prices are outside tolerance. Review and approve."
                f"{link_block}"
            )
            NotificationService(self.db).create_with_channel_preferences(
                uid,
                "commercial_quotation_pricing",
                "Quotation pricing approval required",
                body=body,
                data={"tender_code": tc, "quotation_code": mq.quotation_code, "master_quotation_id": str(mq.id)},
                source_entity_type="commercial_master_quotation",
                source_entity_id=str(mq.id),
                event_type="pricing_approval_requested",
                send_in_app=True,
                send_email=True,
                send_web_push=False,
            )
        except Exception:
            pass

    def patch_pipeline_task_status(self, *, task_id: str, status: str) -> None:
        allowed = self._allowed_pipeline_task_status()
        if allowed and status not in allowed:
            raise ValueError(f"Invalid task status: {status}")
        row = self.db.query(CommercialTask).filter(CommercialTask.id == task_id).one_or_none()
        if not row:
            raise ValueError("Task not found.")
        row.status = status
        self.db.commit()

    def get_dashboard_metrics(
        self,
        *,
        user_id: Optional[str] = None,
        scope: str = "all",
    ) -> Dict[str, Any]:
        today = date.today()
        soon = today + timedelta(days=7)

        tq = self.db.query(CommercialTender).filter(
            CommercialTender.tender_lifecycle == CommercialTenderLifecycle.OPEN,
            CommercialTender.tender_outcome == CommercialTenderOutcome.PENDING,
        )
        if scope == "mine" and user_id:
            tq = tq.join(CommercialProject, CommercialProject.id == CommercialTender.project_id).filter(
                self._mine_scope_tender(user_id)
            )

        tenders = tq.all()
        value_by_stage: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        count_by_stage: Dict[str, int] = defaultdict(int)
        currency: Optional[str] = None
        for t in tenders:
            key = _norm_key(t.pipeline_stage)
            amt = t.forecast_amount or Decimal("0")
            value_by_stage[key] += amt
            count_by_stage[key] += 1
            if t.forecast_currency and currency is None:
                currency = t.forecast_currency

        multi_mq = len(
            self.db.query(CommercialMasterQuotation.tender_id)
            .group_by(CommercialMasterQuotation.tender_id)
            .having(func.count(CommercialMasterQuotation.id) > 1)
            .all()
        )

        mq_st = aliased(WorkflowStage)
        mq_exec = (
            self.db.query(mq_st.code, func.count(CommercialMasterQuotation.id))
            .join(
                CommercialMasterQuotation,
                CommercialMasterQuotation.quotation_stage_id == mq_st.id,
            )
            .filter(mq_st.domain == WORKFLOW_DOMAIN_QUOTATION)
            .group_by(mq_st.code)
            .all()
        )
        mq_exec_map = {str(r[0]): int(r[1]) for r in mq_exec}

        win_loss = (
            self.db.query(CommercialTender.tender_outcome, func.count())
            .filter(CommercialTender.tender_lifecycle == CommercialTenderLifecycle.CLOSED)
            .group_by(CommercialTender.tender_outcome)
            .all()
        )
        win_loss_map = {str(r[0]): int(r[1]) for r in win_loss}

        crm_overdue = (
            self.db.query(func.count())
            .select_from(CommercialTask)
            .filter(CommercialTask.due_on.isnot(None), CommercialTask.due_on < today)
            .scalar()
            or 0
        )
        crm_soon = (
            self.db.query(func.count())
            .select_from(CommercialTask)
            .filter(
                CommercialTask.due_on.isnot(None),
                CommercialTask.due_on >= today,
                CommercialTask.due_on <= soon,
            )
            .scalar()
            or 0
        )

        act_overdue = (
            self.db.query(func.count())
            .select_from(CommercialQuotationActivityTask)
            .filter(
                CommercialQuotationActivityTask.deleted_at.is_(None),
                CommercialQuotationActivityTask.due_at.isnot(None),
                CommercialQuotationActivityTask.due_at < datetime.utcnow(),
            )
            .scalar()
            or 0
        )
        act_soon = (
            self.db.query(func.count())
            .select_from(CommercialQuotationActivityTask)
            .filter(
                CommercialQuotationActivityTask.deleted_at.is_(None),
                CommercialQuotationActivityTask.due_at.isnot(None),
                CommercialQuotationActivityTask.due_at >= datetime.utcnow(),
                CommercialQuotationActivityTask.due_at
                <= datetime.combine(soon, datetime.max.time()),
            )
            .scalar()
            or 0
        )

        closest = (
            self.db.query(CommercialTender)
            .options(joinedload(CommercialTender.owner))
            .filter(
                CommercialTender.tender_outcome == CommercialTenderOutcome.PENDING,
                CommercialTender.expected_close_on.isnot(None),
            )
            .order_by(CommercialTender.expected_close_on.asc())
            .limit(10)
            .all()
        )
        closest_cards = [
            {
                "tender_code": t.tender_code,
                "title": t.title,
                "pipeline_stage": t.pipeline_stage,
                "forecast_amount": t.forecast_amount,
                "forecast_currency": t.forecast_currency,
                "expected_close_on": t.expected_close_on,
                "tender_outcome": t.tender_outcome,
                "owner_name": t.owner.name if t.owner else None,
            }
            for t in closest
        ]

        bottleneck = None
        if count_by_stage:
            bottleneck = max(count_by_stage, key=lambda k: count_by_stage[k])

        return {
            "active_pipeline_value_by_stage": {k: str(value_by_stage[k]) for k in value_by_stage},
            "active_pipeline_currency": currency,
            "tender_count_by_stage": dict(count_by_stage),
            "tenders_with_multiple_quotations": int(multi_mq),
            "master_quotation_count_by_execution": mq_exec_map,
            "win_loss_counts": win_loss_map,
            "crm_tasks_overdue": int(crm_overdue),
            "crm_tasks_due_soon": int(crm_soon),
            "activity_tasks_overdue": int(act_overdue),
            "activity_tasks_due_soon": int(act_soon),
            "closest_to_closure": closest_cards,
            "bottleneck_stage": bottleneck,
        }
