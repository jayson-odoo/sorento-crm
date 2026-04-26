"""Commercial leads, stages, notes, and lead-to-project conversion."""
from __future__ import annotations

import copy
import html
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.modules.commercial_core.models import (
    CommercialLead,
    CommercialLeadNote,
    CommercialLeadRespondContact,
    CommercialMasterQuotation,
    CommercialProject,
    CommercialSalesOrder,
    CommercialTender,
)
from app.models.workflow_stage import WORKFLOW_DOMAIN_LEAD, WorkflowStage
from app.models.numbering import DocumentNumberingRule
from app.models.order import Customer
from app.models.respond_workspace import RespondWorkspace
from app.models.user import User
from app.modules.commercial_core.schemas.commercial import (
    CommercialLeadConvertRequest,
    CommercialLeadCreate,
    CommercialLeadNoteCreate,
    CommercialLeadStageCreate,
    CommercialLeadStageUpdate,
    CommercialLeadUpdate,
)
from app.services.audit_service import log_audit
from app.modules.commercial_core.services.customer_lead_contact_sync import upsert_lead_primary_contact, validate_customer_required_for_commercial_lead
from app.modules.commercial_core.services.lead_respond_contact_service import LeadRespondContactService
from app.services.numbering_service import NumberingService

AUDIT_ENTITY_COMMERCIAL_LEAD = "commercial_lead"


def _uuid() -> str:
    return str(uuid.uuid4())


def _gen_code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


class CommercialLeadStageService:
    def __init__(self, db: Session):
        self.db = db

    def list_stages(self) -> List[WorkflowStage]:
        return (
            self.db.query(WorkflowStage)
            .filter(WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD)
            .order_by(WorkflowStage.sort_order.asc(), WorkflowStage.code.asc())
            .all()
        )

    def get_stage(self, stage_id: str) -> Optional[WorkflowStage]:
        return (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.id == stage_id,
                WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
            )
            .first()
        )

    def get_stage_by_code(self, code: str) -> Optional[WorkflowStage]:
        c = (code or "").strip().lower()
        if not c:
            return None
        return (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                func.lower(WorkflowStage.code) == c,
            )
            .first()
        )

    def create_stage(self, data: CommercialLeadStageCreate) -> WorkflowStage:
        if self.get_stage_by_code(data.stage_code):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stage code already exists")
        row = WorkflowStage(
            id=_uuid(),
            domain=WORKFLOW_DOMAIN_LEAD,
            code=data.stage_code.strip(),
            label=data.stage_name.strip(),
            description=None,
            sort_order=data.sort_order,
            is_terminal=data.is_terminal,
            allows_conversion=data.allows_conversion,
            can_go_back=False,
            is_active=True,
            is_cancelled=False,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_stage(self, stage_id: str, data: CommercialLeadStageUpdate) -> WorkflowStage:
        row = self.get_stage(stage_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead stage not found")
        if data.stage_name is not None:
            row.label = data.stage_name.strip()
        if data.sort_order is not None:
            row.sort_order = data.sort_order
        if data.is_terminal is not None:
            row.is_terminal = data.is_terminal
        if data.allows_conversion is not None:
            row.allows_conversion = data.allows_conversion
        if data.can_go_back is not None:
            row.can_go_back = data.can_go_back
        if data.is_active is not None:
            row.is_active = data.is_active
        if data.is_cancelled is not None:
            row.is_cancelled = data.is_cancelled
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_stage(self, stage_id: str) -> None:
        row = self.get_stage(stage_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead stage not found")
        n = self.db.query(CommercialLead).filter(CommercialLead.lead_stage_id == stage_id).count()
        if n > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete a stage that is assigned to leads",
            )
        self.db.delete(row)
        self.db.commit()

    def update_stage_by_code(self, stage_code: str, data: CommercialLeadStageUpdate) -> WorkflowStage:
        row = self.get_stage_by_code(stage_code)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead stage not found")
        return self.update_stage(str(row.id), data)

    def delete_stage_by_code(self, stage_code: str) -> None:
        row = self.get_stage_by_code(stage_code)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead stage not found")
        self.delete_stage(str(row.id))


class CommercialLeadService:
    def __init__(self, db: Session):
        self.db = db

    def _ensure_commercial_lead_numbering_rule(self) -> None:
        if self.db.query(DocumentNumberingRule.id).filter(DocumentNumberingRule.doc_type == "commercial_lead").first():
            return
        row = DocumentNumberingRule(
            doc_type="commercial_lead",
            enabled=True,
            prefix_template="LD-{year}-",
            number_digits=4,
            next_value=1,
            start_value=1,
            reset_policy="yearly",
        )
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def _default_new_stage_id(self) -> str:
        st = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                func.lower(WorkflowStage.code) == "new",
            )
            .first()
        )
        if st:
            return str(st.id)
        row = WorkflowStage(
            id=_uuid(),
            domain=WORKFLOW_DOMAIN_LEAD,
            code="new",
            label="New",
            description=None,
            sort_order=0,
            is_terminal=False,
            allows_conversion=False,
            can_go_back=False,
            is_active=True,
            is_cancelled=False,
        )
        self.db.add(row)
        try:
            self.db.commit()
            self.db.refresh(row)
            return str(row.id)
        except IntegrityError:
            self.db.rollback()
            st2 = (
                self.db.query(WorkflowStage)
                .filter(
                    WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                    func.lower(WorkflowStage.code) == "new",
                )
                .first()
            )
            if st2:
                return str(st2.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default lead stage 'new' could not be created",
            ) from None

    def _merge_qualification_with_customer(self, cust: Customer, qual: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(qual or {})
        name = (cust.customer_name or "").strip()
        phone = (cust.phone_number or "").strip()
        email = (cust.email or "").strip()
        if name and not (out.get("client_name") or "").strip():
            out["client_name"] = name
        if phone and not (out.get("client_phone") or "").strip():
            out["client_phone"] = phone
        if email and not (out.get("client_email") or "").strip():
            out["client_email"] = email
        contacts = list(out.get("contacts") or [])
        has_main_phone = any(
            (isinstance(c, dict) and (c.get("role") or c.get("contact_role")) == "main" and (c.get("phone") or ""))
            for c in contacts
        )
        if phone and not has_main_phone:
            main_name = name or "Main contact"
            contacts.append(
                {
                    "role": "main",
                    "name": main_name,
                    "phone": phone,
                    "email": email or None,
                }
            )
            out["contacts"] = contacts
        return out

    def _resolve_lead_code(self, requested: Optional[str]) -> str:
        if requested and requested.strip():
            code = requested.strip()
            exists = self.db.query(CommercialLead.id).filter(CommercialLead.lead_code == code).first()
            if exists:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lead code already exists")
            return code
        self._ensure_commercial_lead_numbering_rule()
        ns = NumberingService(self.db)
        num = ns.get_next_number("commercial_lead", date.today())
        if num:
            exists = self.db.query(CommercialLead.id).filter(CommercialLead.lead_code == num).first()
            if not exists:
                return num
        return _gen_code("LD")

    def _resolve_tender_code(self, requested: Optional[str]) -> str:
        if requested and requested.strip():
            code = requested.strip()
            exists = self.db.query(CommercialTender.id).filter(CommercialTender.tender_code == code).first()
            if exists:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tender code already exists")
            return code
        ns = NumberingService(self.db)
        num = ns.get_next_number("commercial_tender", date.today())
        if num:
            exists = self.db.query(CommercialTender.id).filter(CommercialTender.tender_code == num).first()
            if not exists:
                return num
        return _gen_code("TND")

    def _serialize_lead(self, lead: CommercialLead) -> Dict[str, Any]:
        cust = lead.customer
        owner = lead.owner
        st = lead.lead_stage
        projects_list = list(lead.projects or [])
        proj = projects_list[0] if projects_list else None
        owner_name = None
        if owner:
            owner_name = (owner.name or "").strip() or owner.email
        creator = getattr(lead, "created_by", None)
        created_by_name = None
        if creator:
            created_by_name = (creator.name or "").strip() or creator.email
        return {
            "id": str(lead.id),
            "lead_code": lead.lead_code,
            "title": lead.title,
            "customer_id": str(lead.customer_id),
            "customer_code": cust.customer_code if cust else None,
            "customer_name": cust.customer_name if cust else None,
            "customer_phone": (cust.phone_number or "").strip() or None if cust else None,
            "customer_email": (cust.email or "").strip() or None if cust else None,
            "owner_user_id": lead.owner_user_id,
            "owner_name": owner_name,
            "created_by_user_id": lead.created_by_user_id,
            "created_by_name": created_by_name,
            "lead_stage_id": str(lead.lead_stage_id),
            "stage_code": st.code if st else None,
            "stage_name": st.label if st else None,
            "allows_conversion": st.allows_conversion is True if st else False,
            "is_terminal": bool(st.is_terminal) if st else False,
            "qualification": dict(lead.qualification or {}),
            "qualification_summary": lead.qualification_summary,
            "respond_workspace_id": str(lead.respond_workspace_id) if getattr(lead, "respond_workspace_id", None) else None,
            "has_project": len(projects_list) > 0,
            "project_id": str(proj.id) if proj else None,
            "lead_project_count": len(projects_list),
            "created_at": lead.created_at,
            "updated_at": lead.updated_at,
        }

    def list_leads(
        self,
        page: int = 1,
        limit: int = 50,
        customer_id: Optional[str] = None,
        owner_user_id: Optional[str] = None,
        lead_stage_id: Optional[str] = None,
        stage_code: Optional[str] = None,
        without_project: bool = False,
        search_query: Optional[str] = None,
        sort_field: Optional[str] = None,
        sort_dir: Optional[str] = None,
        open_pipeline_only: bool = False,
        terminal_pipeline_only: bool = False,
        terminal_conversion_eligible_only: bool = False,
        customer_active_only: bool = False,
        created_from: Optional[date] = None,
        created_to: Optional[date] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        filters = []
        if customer_id:
            filters.append(CommercialLead.customer_id == customer_id)
        if owner_user_id:
            filters.append(CommercialLead.owner_user_id == owner_user_id)
        if lead_stage_id:
            filters.append(CommercialLead.lead_stage_id == lead_stage_id)
        if stage_code and (sc := stage_code.strip()):
            st = (
                self.db.query(WorkflowStage)
                .filter(
                    WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                    func.lower(WorkflowStage.code) == sc.lower(),
                )
                .first()
            )
            if st:
                filters.append(CommercialLead.lead_stage_id == st.id)
        if without_project:
            filters.append(~exists().where(CommercialProject.lead_id == CommercialLead.id))
        if search_query and (qstr := search_query.strip()):
            like = f"%{qstr}%"
            filters.append(
                or_(
                    CommercialLead.lead_code.ilike(like),
                    CommercialLead.title.ilike(like),
                    CommercialLead.customer.has(Customer.customer_name.ilike(like)),
                    CommercialLead.customer.has(Customer.customer_code.ilike(like)),
                )
            )
        if open_pipeline_only:
            open_ids = [
                r[0]
                for r in self.db.query(WorkflowStage.id)
                .filter(
                    WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                    WorkflowStage.is_terminal.is_(False),
                )
                .all()
            ]
            if not open_ids:
                return [], 0
            filters.append(CommercialLead.lead_stage_id.in_(open_ids))
        if terminal_pipeline_only:
            term_ids = [
                r[0]
                for r in self.db.query(WorkflowStage.id)
                .filter(
                    WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                    WorkflowStage.is_terminal.is_(True),
                )
                .all()
            ]
            if not term_ids:
                return [], 0
            filters.append(CommercialLead.lead_stage_id.in_(term_ids))
        if terminal_conversion_eligible_only:
            elig_ids = [
                r[0]
                for r in self.db.query(WorkflowStage.id)
                .filter(
                    WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                    WorkflowStage.is_terminal.is_(True),
                    WorkflowStage.allows_conversion.is_(True),
                )
                .all()
            ]
            if not elig_ids:
                return [], 0
            filters.append(CommercialLead.lead_stage_id.in_(elig_ids))
        if customer_active_only:
            filters.append(CommercialLead.customer.has(Customer.is_active.is_(True)))
        if created_from is not None:
            filters.append(CommercialLead.created_at >= datetime.combine(created_from, datetime.min.time()))
        if created_to is not None:
            filters.append(CommercialLead.created_at <= datetime.combine(created_to, datetime.max.time()))

        count_q = self.db.query(CommercialLead)
        if filters:
            count_q = count_q.filter(and_(*filters))
        total = count_q.count()

        sf = (sort_field or "created_at").strip()
        sd = (sort_dir or "desc").strip().lower()
        ascending = sd == "asc"

        data_q = (
            self.db.query(CommercialLead)
            .options(
                joinedload(CommercialLead.customer),
                joinedload(CommercialLead.owner),
                joinedload(CommercialLead.created_by),
                joinedload(CommercialLead.lead_stage),
                joinedload(CommercialLead.projects),
            )
        )
        if filters:
            data_q = data_q.filter(and_(*filters))

        if sf == "customer_name":
            data_q = data_q.join(Customer, CommercialLead.customer_id == Customer.id)
            order_expr = Customer.customer_name.asc() if ascending else Customer.customer_name.desc()
            data_q = data_q.order_by(order_expr, CommercialLead.id.asc())
        elif sf == "stage_name":
            data_q = data_q.join(WorkflowStage, CommercialLead.lead_stage_id == WorkflowStage.id)
            order_expr = WorkflowStage.label.asc() if ascending else WorkflowStage.label.desc()
            data_q = data_q.order_by(order_expr, CommercialLead.id.asc())
        elif sf in ("lead_code", "title", "created_at", "updated_at"):
            col = getattr(CommercialLead, sf)
            order_expr = col.asc() if ascending else col.desc()
            data_q = data_q.order_by(order_expr, CommercialLead.id.asc())
        else:
            data_q = data_q.order_by(
                CommercialLead.created_at.desc() if not ascending else CommercialLead.created_at.asc(),
                CommercialLead.id.asc(),
            )

        offset = (page - 1) * limit
        rows = data_q.offset(offset).limit(limit).all()
        return [self._serialize_lead(r) for r in rows], total

    def get_lead(self, lead_id: str) -> Dict[str, Any]:
        lead = (
            self.db.query(CommercialLead)
            .options(
                joinedload(CommercialLead.customer),
                joinedload(CommercialLead.owner),
                joinedload(CommercialLead.created_by),
                joinedload(CommercialLead.lead_stage),
                joinedload(CommercialLead.projects),
            )
            .filter(CommercialLead.id == lead_id)
            .first()
        )
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return self._serialize_lead(lead)

    def get_lead_related(self, lead_id: str) -> Dict[str, Any]:
        lead = self.db.query(CommercialLead).filter(CommercialLead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        # Include BOTH:
        # 1) quotations explicitly tagged with this lead in commercial_details.lead_id
        # 2) quotations under projects linked to this lead (project.lead_id legacy path)
        matched_mqs = (
            self.db.query(CommercialMasterQuotation)
            .options(
                joinedload(CommercialMasterQuotation.quotation_stage),
                joinedload(CommercialMasterQuotation.tender).joinedload(CommercialTender.project),
            )
            .join(CommercialTender, CommercialMasterQuotation.tender_id == CommercialTender.id)
            .join(CommercialProject, CommercialTender.project_id == CommercialProject.id)
            .filter(
                or_(
                    CommercialMasterQuotation.commercial_details["lead_id"].astext == lead_id,
                    CommercialProject.lead_id == lead_id,
                )
            )
            .order_by(CommercialMasterQuotation.created_at.desc())
            .all()
        )
        project_rows: List[Dict[str, Any]] = []
        quotations_out: List[Dict[str, Any]] = []
        project_seen: Set[str] = set()
        mq_seen: Set[str] = set()
        mq_ids: List[str] = []
        tender_id_to_code: Dict[str, str] = {}

        for mq in matched_mqs:
            t = mq.tender
            p = t.project if t else None
            if not t or not p:
                continue
            if str(mq.id) in mq_seen:
                continue
            mq_seen.add(str(mq.id))
            mq_ids.append(str(mq.id))
            tender_id_to_code[str(t.id)] = t.tender_code
            if str(p.id) not in project_seen:
                project_seen.add(str(p.id))
                project_rows.append(
                    {
                        "id": str(p.id),
                        "title": p.title,
                        "status": p.status,
                        "created_at": p.created_at,
                        "updated_at": p.updated_at,
                    }
                )
            st = mq.quotation_stage
            quotations_out.append(
                {
                    "project_title": p.title,
                    "tender_code": t.tender_code,
                    "quotation_code": mq.quotation_code,
                    "title": mq.title,
                    "path_role": mq.path_role,
                    "stage_name": st.label if st else None,
                }
            )

        sales_orders_out: List[Dict[str, Any]] = []
        if mq_ids:
            sos = (
                self.db.query(CommercialSalesOrder)
                .options(joinedload(CommercialSalesOrder.master_quotation))
                .filter(CommercialSalesOrder.master_quotation_id.in_(mq_ids))
                .order_by(CommercialSalesOrder.created_at.desc())
                .all()
            )
            for so in sos:
                mq = so.master_quotation
                sales_orders_out.append(
                    {
                        "sales_order_number": so.sales_order_number,
                        "status": so.status,
                        "tender_code": tender_id_to_code.get(str(so.tender_id), ""),
                        "quotation_code": mq.quotation_code if mq else "",
                    }
                )

        return {
            "projects": project_rows,
            "quotations": quotations_out,
            "sales_orders": sales_orders_out,
        }

    def create_lead(
        self,
        data: CommercialLeadCreate,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        cust = self.db.query(Customer).filter(Customer.id == data.customer_id).first()
        if not cust:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
        validate_customer_required_for_commercial_lead(cust)
        owner = self.db.query(User).filter(User.id == data.owner_user_id).first()
        if not owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner user not found")
        stage_id = data.lead_stage_id or self._default_new_stage_id()
        st = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                WorkflowStage.id == stage_id,
            )
            .first()
        )
        if not st:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead stage not found")
        if data.respond_workspace_id:
            ws = self.db.query(RespondWorkspace).filter(RespondWorkspace.id == data.respond_workspace_id).first()
            if not ws:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Respond workspace not found")
        lead_code = self._resolve_lead_code(data.lead_code)
        qual = data.qualification if data.qualification is not None else {}
        lead = CommercialLead(
            id=_uuid(),
            customer_id=data.customer_id,
            lead_code=lead_code,
            title=data.title.strip(),
            owner_user_id=data.owner_user_id,
            lead_stage_id=stage_id,
            qualification=qual,
            qualification_summary=data.qualification_summary,
            created_by_user_id=actor_user_id,
            respond_workspace_id=data.respond_workspace_id,
        )
        self.db.add(lead)
        self.db.flush()
        upsert_lead_primary_contact(self.db, cust)
        LeadRespondContactService(self.db).sync_primary_from_lead_creation(lead, cust)
        log_audit(
            self.db,
            AUDIT_ENTITY_COMMERCIAL_LEAD,
            str(lead.id),
            "INSERT",
            new_values={"lead_code": lead.lead_code, "title": lead.title, "customer_id": str(lead.customer_id)},
            user_id=actor_user_id,
            ip_address=ip_address,
        )
        from app.modules.commercial_core.services.entity_conversation_service import ENTITY_COMMERCIAL_LEAD, append_system_message

        append_system_message(
            self.db,
            entity_type=ENTITY_COMMERCIAL_LEAD,
            entity_id=str(lead.id),
            body_html=f"<p>{html.escape(lead.lead_code or '')} is created.</p>",
        )
        self.db.commit()
        self.db.refresh(lead)
        return self.get_lead(str(lead.id))

    def duplicate_lead(
        self,
        lead_id: str,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        lead = (
            self.db.query(CommercialLead)
            .options(joinedload(CommercialLead.lead_stage))
            .filter(CommercialLead.id == lead_id)
            .first()
        )
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        cust = self.db.query(Customer).filter(Customer.id == lead.customer_id).first()
        if not cust:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
        validate_customer_required_for_commercial_lead(cust)
        stage_id = self._default_new_stage_id()
        st = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                WorkflowStage.id == stage_id,
            )
            .first()
        )
        if not st:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead stage not found")
        lead_code = self._resolve_lead_code(None)
        qual = copy.deepcopy(dict(lead.qualification or {}))
        suffix = " (Copy)"
        base = (lead.title or "").strip() or lead_code
        max_base = max(0, 255 - len(suffix))
        title = (base[:max_base] + suffix).strip()
        dup = CommercialLead(
            id=_uuid(),
            customer_id=lead.customer_id,
            lead_code=lead_code,
            title=title,
            owner_user_id=lead.owner_user_id,
            lead_stage_id=stage_id,
            qualification=qual,
            qualification_summary=lead.qualification_summary,
            created_by_user_id=actor_user_id,
            respond_workspace_id=getattr(lead, "respond_workspace_id", None),
        )
        self.db.add(dup)
        self.db.flush()
        upsert_lead_primary_contact(self.db, cust)
        LeadRespondContactService(self.db).sync_primary_from_lead_creation(dup, cust)
        log_audit(
            self.db,
            AUDIT_ENTITY_COMMERCIAL_LEAD,
            str(dup.id),
            "INSERT",
            new_values={"lead_code": dup.lead_code, "title": dup.title, "customer_id": str(dup.customer_id)},
            user_id=actor_user_id,
            ip_address=ip_address,
        )
        from app.modules.commercial_core.services.entity_conversation_service import ENTITY_COMMERCIAL_LEAD, append_system_message

        append_system_message(
            self.db,
            entity_type=ENTITY_COMMERCIAL_LEAD,
            entity_id=str(dup.id),
            body_html=f"<p>{html.escape(dup.lead_code or '')} is created.</p>",
        )
        self.db.commit()
        self.db.refresh(dup)
        return self.get_lead(str(dup.id))

    def update_lead(
        self,
        lead_id: str,
        data: CommercialLeadUpdate,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        lead = (
            self.db.query(CommercialLead)
            .options(joinedload(CommercialLead.lead_stage))
            .filter(CommercialLead.id == lead_id)
            .first()
        )
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        prev_lead_stage_id = str(lead.lead_stage_id) if lead.lead_stage_id else ""
        prev_owner = lead.owner_user_id
        old = {
            "title": lead.title,
            "owner_user_id": lead.owner_user_id,
            "lead_stage_id": str(lead.lead_stage_id),
            "qualification_summary": lead.qualification_summary,
        }
        if data.title is not None:
            lead.title = data.title.strip()
        patch_fields = data.model_dump(exclude_unset=True)
        if "respond_workspace_id" in patch_fields:
            new_ws = patch_fields["respond_workspace_id"] or None
            old_ws = lead.respond_workspace_id
            if str(old_ws or "") != str(new_ws or ""):
                n_links = (
                    self.db.query(CommercialLeadRespondContact)
                    .filter(CommercialLeadRespondContact.lead_id == lead.id)
                    .count()
                )
                if n_links > 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Cannot change Respond workspace while contacts are linked; remove links first.",
                    )
                if new_ws:
                    ws = self.db.query(RespondWorkspace).filter(RespondWorkspace.id == new_ws).first()
                    if not ws:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Respond workspace not found")
                lead.respond_workspace_id = new_ws
        if data.owner_user_id is not None:
            u = self.db.query(User).filter(User.id == data.owner_user_id).first()
            if not u:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner user not found")
            lead.owner_user_id = data.owner_user_id
            if data.owner_user_id != prev_owner:
                q = dict(lead.qualification or {})
                q["assigned_at"] = datetime.now(timezone.utc).isoformat()
                lead.qualification = q
        if data.lead_stage_id is not None:
            st = (
                self.db.query(WorkflowStage)
                .filter(
                    WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                    WorkflowStage.id == data.lead_stage_id,
                )
                .first()
            )
            if not st:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead stage not found")
            lead.lead_stage_id = data.lead_stage_id
        if data.qualification is not None:
            cust = self.db.query(Customer).filter(Customer.id == lead.customer_id).first()
            merged = self._merge_qualification_with_customer(cust, dict(data.qualification)) if cust else dict(data.qualification)
            prev_q = dict(lead.qualification or {})
            if prev_q.get("assigned_at"):
                merged.setdefault("assigned_at", prev_q.get("assigned_at"))
            lead.qualification = merged
        if data.qualification_summary is not None:
            lead.qualification_summary = data.qualification_summary
        new = {
            "title": lead.title,
            "owner_user_id": lead.owner_user_id,
            "lead_stage_id": str(lead.lead_stage_id),
            "qualification_summary": lead.qualification_summary,
        }
        if old != new:
            log_audit(
                self.db,
                AUDIT_ENTITY_COMMERCIAL_LEAD,
                str(lead.id),
                "UPDATE",
                old_values=old,
                new_values=new,
                user_id=actor_user_id,
                ip_address=ip_address,
            )
        stage_changed = prev_lead_stage_id != (str(lead.lead_stage_id) if lead.lead_stage_id else "")
        if stage_changed:
            st_row = (
                self.db.query(WorkflowStage).filter(WorkflowStage.id == lead.lead_stage_id).first()
            )
            label = (st_row.label or "").strip() if st_row else ""
            from app.modules.commercial_core.services.entity_conversation_service import ENTITY_COMMERCIAL_LEAD, append_system_message

            append_system_message(
                self.db,
                entity_type=ENTITY_COMMERCIAL_LEAD,
                entity_id=str(lead.id),
                body_html=f"<p>{html.escape(lead.lead_code or '')} moved to {html.escape(label)}.</p>",
            )
        cust2 = self.db.query(Customer).filter(Customer.id == lead.customer_id).first()
        if cust2:
            LeadRespondContactService(self.db).sync_primary_from_lead_creation(lead, cust2)
        self.db.commit()
        return self.get_lead(lead_id)

    def delete_lead(self, lead_id: str, *, actor_user_id: str, ip_address: Optional[str] = None) -> None:
        lead = self.db.query(CommercialLead).filter(CommercialLead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        log_audit(
            self.db,
            AUDIT_ENTITY_COMMERCIAL_LEAD,
            str(lead.id),
            "DELETE",
            old_values={"lead_code": lead.lead_code, "title": lead.title},
            user_id=actor_user_id,
            ip_address=ip_address,
        )
        self.db.delete(lead)
        self.db.commit()

    def list_notes(self, lead_id: str) -> List[CommercialLeadNote]:
        lead = self.db.query(CommercialLead).filter(CommercialLead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return (
            self.db.query(CommercialLeadNote)
            .options(joinedload(CommercialLeadNote.created_by))
            .filter(CommercialLeadNote.lead_id == lead_id)
            .order_by(CommercialLeadNote.created_at.desc())
            .all()
        )

    def add_note(
        self,
        lead_id: str,
        data: CommercialLeadNoteCreate,
        *,
        actor_user_id: str,
    ) -> CommercialLeadNote:
        lead = self.db.query(CommercialLead).filter(CommercialLead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        note = CommercialLeadNote(
            id=_uuid(),
            lead_id=lead_id,
            body=data.body.strip(),
            created_by_user_id=actor_user_id,
        )
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note

    def convert_lead(
        self,
        lead_id: str,
        data: CommercialLeadConvertRequest,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        lead = (
            self.db.query(CommercialLead)
            .options(joinedload(CommercialLead.lead_stage), joinedload(CommercialLead.projects))
            .filter(CommercialLead.id == lead_id)
            .first()
        )
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        st = lead.lead_stage
        if not st or st.allows_conversion is not True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead stage does not allow conversion to project and tender",
            )
        exp_close = None
        if data.expected_close_on:
            try:
                exp_close = date.fromisoformat(data.expected_close_on[:10])
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid expected_close_on date")

        project = CommercialProject(
            id=_uuid(),
            lead_id=lead_id,
            owner_user_id=actor_user_id,
            title=data.project_title.strip(),
        )
        self.db.add(project)
        self.db.flush()
        tender_code = self._resolve_tender_code(data.tender_code)
        tender = CommercialTender(
            id=_uuid(),
            project_id=str(project.id),
            tender_code=tender_code,
            title=data.tender_title.strip(),
            forecast_amount=data.forecast_amount,
            forecast_currency=data.forecast_currency.strip() if data.forecast_currency else None,
            pipeline_stage=data.pipeline_stage,
            expected_close_on=exp_close,
        )
        self.db.add(tender)
        self.db.flush()
        eng = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_LEAD,
                WorkflowStage.code == "engaging",
            )
            .first()
        )
        if eng:
            lead.lead_stage_id = str(eng.id)
        log_audit(
            self.db,
            AUDIT_ENTITY_COMMERCIAL_LEAD,
            str(lead.id),
            "UPDATE",
            old_values={"converted": False},
            new_values={"converted": True, "project_id": str(project.id), "tender_id": str(tender.id)},
            user_id=actor_user_id,
            description="Converted lead to project and tender",
            ip_address=ip_address,
        )
        self.db.commit()
        return str(project.id), str(tender.id), tender_code
