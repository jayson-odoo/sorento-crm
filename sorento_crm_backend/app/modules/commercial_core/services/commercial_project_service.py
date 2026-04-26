"""Commercial projects: list, detail, create from qualified lead, update."""
from __future__ import annotations

import copy
import html
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, func, inspect, or_
from sqlalchemy.orm import Session, aliased, joinedload

from app.modules.commercial_core.models import (
    CommercialLead,
    CommercialMasterQuotation,
    CommercialProject,
    CommercialProjectCustomer,
    CommercialProjectLead,
    CommercialTender,
)
from app.modules.commercial_activity.models import (
    CommercialActivityTaskStatus,
    CommercialActivityTemplate,
    CommercialActivityTemplateNode,
    CommercialProjectTask,
    CommercialProjectTaskCategory,
)
from app.models.workflow_stage import WORKFLOW_DOMAIN_LEAD, WORKFLOW_DOMAIN_PROJECT, WORKFLOW_DOMAIN_QUOTATION, WorkflowStage
from app.models.entity_attachment import EntityAttachmentLink
from app.models.order import Customer
from app.models.resources import Attachment
from app.models.user import User
from app.modules.commercial_core.schemas.commercial import (
    CommercialProjectCreate,
    CommercialProjectCustomerContactPatch,
    CommercialProjectMemberPatch,
    CommercialProjectUpdate,
)
from app.modules.commercial_activity.services.commercial_project_task_service import (
    CommercialProjectTaskError,
    CommercialProjectTaskService,
)
from app.services.audit_service import log_audit
from app.services.task_dependency_schedule_service import (
    TaskDependencyScheduleError,
    TaskDependencyScheduleService,
)

AUDIT_ENTITY_COMMERCIAL_PROJECT = "commercial_project"


def _uuid() -> str:
    return str(uuid.uuid4())


class CommercialProjectService:
    def __init__(self, db: Session):
        self.db = db

    def _parse_date(self, value: Optional[str], field_name: str) -> Optional[date]:
        if value is None or not str(value).strip():
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name}") from exc

    def _owner_display(self, user: Optional[User]) -> Optional[str]:
        if not user:
            return None
        return (user.name or "").strip() or user.email

    def _project_customer_ids(self, project: CommercialProject) -> List[str]:
        linked: List[str] = []
        if self._project_customer_links_enabled():
            linked = [
                str(link.customer_id)
                for link in (getattr(project, "project_customers", None) or [])
                if getattr(link, "customer_id", None)
            ]
        lead_customer_id = None
        lead = getattr(project, "lead", None)
        if lead and getattr(lead, "customer_id", None):
            lead_customer_id = str(lead.customer_id)
        out = list(dict.fromkeys([*(linked or []), *( [lead_customer_id] if lead_customer_id else [])]))
        return out

    def _project_customer_links_enabled(self) -> bool:
        bind = self.db.get_bind()
        if bind is None:
            return False
        try:
            return bool(inspect(bind).has_table("commercial_project_customers"))
        except Exception:
            return False

    def _project_lead_links_enabled(self) -> bool:
        bind = self.db.get_bind()
        if bind is None:
            return False
        try:
            return bool(inspect(bind).has_table("commercial_project_leads"))
        except Exception:
            return False

    def _project_lead_ids(self, project: CommercialProject) -> List[str]:
        linked: List[str] = []
        if self._project_lead_links_enabled():
            linked = [
                str(link.lead_id)
                for link in (getattr(project, "project_leads", None) or [])
                if getattr(link, "lead_id", None)
            ]
        if getattr(project, "lead_id", None):
            linked.insert(0, str(project.lead_id))
        return list(dict.fromkeys(linked))

    def _sync_project_customer_links(self, project_id: str, customer_ids: List[str]) -> None:
        if not self._project_customer_links_enabled():
            return
        normalized: List[str] = []
        for raw in customer_ids:
            txt = (raw or "").strip()
            if not txt:
                continue
            try:
                normalized.append(str(uuid.UUID(txt)))
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid customer id") from exc
        deduped = list(dict.fromkeys(normalized))
        if not deduped:
            self.db.query(CommercialProjectCustomer).filter(CommercialProjectCustomer.project_id == project_id).delete()
            return
        existing_customers = {
            str(row[0])
            for row in self.db.query(Customer.id).filter(Customer.id.in_(deduped)).all()
            if row and row[0]
        }
        if len(existing_customers) != len(deduped):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more customers were not found")
        self.db.query(CommercialProjectCustomer).filter(CommercialProjectCustomer.project_id == project_id).delete()
        for cid in deduped:
            self.db.add(
                CommercialProjectCustomer(
                    project_id=project_id,
                    customer_id=cid,
                )
            )

    def _sync_project_lead_links(self, project_id: str, lead_ids: List[str]) -> None:
        if not self._project_lead_links_enabled():
            return
        normalized: List[str] = []
        for raw in lead_ids:
            txt = (raw or "").strip()
            if not txt:
                continue
            try:
                normalized.append(str(uuid.UUID(txt)))
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid lead id") from exc
        deduped = list(dict.fromkeys(normalized))
        if not deduped:
            self.db.query(CommercialProjectLead).filter(CommercialProjectLead.project_id == project_id).delete()
            return
        existing = {
            str(row[0])
            for row in self.db.query(CommercialLead.id).filter(CommercialLead.id.in_(deduped)).all()
            if row and row[0]
        }
        if len(existing) != len(deduped):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more leads were not found")
        self.db.query(CommercialProjectLead).filter(CommercialProjectLead.project_id == project_id).delete()
        for lid in deduped:
            self.db.add(CommercialProjectLead(project_id=project_id, lead_id=lid))

    def _project_customers_payload(self, project: CommercialProject) -> List[Dict[str, Any]]:
        ids = self._project_customer_ids(project)
        if not ids:
            return []
        rows = self.db.query(Customer).filter(Customer.id.in_(ids)).all()
        by_id = {str(c.id): c for c in rows}
        out: List[Dict[str, Any]] = []
        for cid in ids:
            cust = by_id.get(cid)
            if not cust:
                continue
            out.append(
                {
                    "id": str(cust.id),
                    "customer_code": cust.customer_code,
                    "customer_name": cust.customer_name,
                }
            )
        return out

    def _project_leads_payload(self, project: CommercialProject) -> List[Dict[str, Any]]:
        lead_ids = self._project_lead_ids(project)
        if not lead_ids:
            return []
        rows = (
            self.db.query(CommercialLead, Customer)
            .outerjoin(Customer, CommercialLead.customer_id == Customer.id)
            .filter(CommercialLead.id.in_(lead_ids))
            .all()
        )
        by_id = {str(lead.id): (lead, cust) for lead, cust in rows}
        out: List[Dict[str, Any]] = []
        for lid in lead_ids:
            pair = by_id.get(lid)
            if not pair:
                continue
            lead, cust = pair
            out.append(
                {
                    "id": str(lead.id),
                    "lead_code": lead.lead_code,
                    "lead_title": lead.title,
                    "customer_id": str(cust.id) if cust else None,
                    "customer_name": cust.customer_name if cust else None,
                }
            )
        return out

    def _default_project_stage(self) -> WorkflowStage:
        row = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_PROJECT,
                WorkflowStage.code == "active",
                WorkflowStage.is_active.is_(True),
            )
            .first()
        )
        if not row:
            row = (
                self.db.query(WorkflowStage)
                .filter(WorkflowStage.domain == WORKFLOW_DOMAIN_PROJECT, WorkflowStage.is_active.is_(True))
                .order_by(WorkflowStage.sort_order.asc())
                .first()
            )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Project workflow stages are not configured",
            )
        return row

    def _require_project_stage_id(self, stage_id: str) -> WorkflowStage:
        row = (
            self.db.query(WorkflowStage)
            .filter(WorkflowStage.id == stage_id.strip(), WorkflowStage.domain == WORKFLOW_DOMAIN_PROJECT)
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project workflow stage")
        return row

    def _workflow_stage_from_legacy_status(self, status_str: str) -> WorkflowStage:
        raw = (status_str or "active").strip().lower().replace(" ", "_")
        if raw not in ("planning", "active", "on_hold", "completed", "cancelled"):
            raw = "active"
        row = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_PROJECT,
                WorkflowStage.code == raw,
                WorkflowStage.is_active.is_(True),
            )
            .first()
        )
        return row or self._default_project_stage()

    def _coerce_owner_ids(self, owner_user_id: str, owner_ids: Any) -> List[str]:
        items: List[str] = []
        if isinstance(owner_ids, list):
            for x in owner_ids:
                if x is None:
                    continue
                txt = str(x).strip()
                if txt:
                    items.append(txt)
        primary = (owner_user_id or "").strip()
        if primary:
            items.insert(0, primary)
        deduped: List[str] = []
        seen: set[str] = set()
        for item in items:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    def _coerce_project_members(self, members: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not isinstance(members, list):
            return out
        for item in members:
            if isinstance(item, CommercialProjectMemberPatch):
                payload = item.model_dump()
            elif isinstance(item, dict):
                payload = dict(item)
            else:
                continue
            name = str(payload.get("name") or "").strip()
            if not name:
                continue
            tags_raw = payload.get("tags")
            tags: List[str] = []
            if isinstance(tags_raw, list):
                for t in tags_raw:
                    txt = str(t or "").strip()
                    if txt:
                        tags.append(txt)
            out.append({"name": name, "tags": list(dict.fromkeys(tags))})
        return out

    def _owner_names_for_ids(self, owner_ids: List[str]) -> List[str]:
        if not owner_ids:
            return []
        users = self.db.query(User).filter(User.id.in_(owner_ids)).all()
        by_id = {str(u.id): u for u in users}
        names: List[str] = []
        for owner_id in owner_ids:
            u = by_id.get(owner_id)
            if not u:
                continue
            display = self._owner_display(u)
            if display:
                names.append(display)
        return names

    def _serialize_customer_contacts(self, p: CommercialProject) -> List[Dict[str, Any]]:
        raw = p.project_customer_contacts if isinstance(p.project_customer_contacts, list) else []
        out: List[Dict[str, Any]] = []
        for x in raw:
            if not isinstance(x, dict):
                continue
            cid = x.get("id")
            out.append(
                {
                    "id": str(cid) if cid else None,
                    "name": str(x.get("name") or ""),
                    "phone": x.get("phone"),
                    "email": x.get("email"),
                }
            )
        return out

    def _sanitize_contacts(self, rows: Optional[List[Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return []
        out: List[Dict[str, Any]] = []
        for c in rows:
            if isinstance(c, CommercialProjectCustomerContactPatch):
                d = c.model_dump(exclude_none=False)
            elif isinstance(c, dict):
                d = dict(c)
            else:
                continue
            name = str(d.get("name") or "").strip()
            out.append(
                {
                    "id": str(d["id"]).strip() if d.get("id") else None,
                    "name": name,
                    "phone": (str(d["phone"]).strip() if d.get("phone") else None),
                    "email": (str(d["email"]).strip() if d.get("email") else None),
                }
            )
        return out

    def _serialize_attachment(self, att: Attachment) -> Dict[str, Any]:
        return {
            "id": str(att.id),
            "name": att.original_filename,
            "size_bytes": att.file_size_bytes,
            "uploaded_by": att.uploaded_by,
            "uploaded_at": att.uploaded_at,
            "file_path": att.file_path,
        }

    def _default_task_status_code(self) -> str:
        row = (
            self.db.query(CommercialActivityTaskStatus)
            .filter(
                CommercialActivityTaskStatus.is_default.is_(True),
                CommercialActivityTaskStatus.is_active.is_(True),
            )
            .first()
        )
        return row.code if row else "not_started"

    def _category_label(self, code: Optional[str]) -> str:
        if not code:
            return "General"
        cat = (
            self.db.query(CommercialProjectTaskCategory)
            .filter(CommercialProjectTaskCategory.code == code, CommercialProjectTaskCategory.is_active.is_(True))
            .first()
        )
        if cat:
            return cat.label
        return str(code).replace("_", " ").strip().title() or "General"

    def _project_task_service(self) -> CommercialProjectTaskService:
        return CommercialProjectTaskService(self.db)

    def _duplicate_project_tasks(self, source_project_id: str, target_project_id: str) -> None:
        rows = (
            self.db.query(CommercialProjectTask)
            .filter(CommercialProjectTask.project_id == source_project_id)
            .order_by(CommercialProjectTask.sort_order.asc(), CommercialProjectTask.created_at.asc())
            .all()
        )
        if not rows:
            return
        old_to_new: Dict[str, str] = {str(r.id): _uuid() for r in rows}
        for r in rows:
            new_id = old_to_new[str(r.id)]
            new_parent_id = old_to_new.get(str(r.parent_id)) if r.parent_id else None
            dep_ids = [old_to_new[str(x)] for x in (r.dependency_task_ids or []) if str(x) in old_to_new]
            clone = CommercialProjectTask(
                id=new_id,
                project_id=target_project_id,
                parent_id=new_parent_id,
                template_node_id=r.template_node_id,
                parent_template_node_id=r.parent_template_node_id,
                sort_order=r.sort_order,
                title=r.title,
                description=r.description,
                category_code=r.category_code,
                is_service_task=r.is_service_task,
                status_id=r.status_id,
                assignee_user_id=r.assignee_user_id,
                lead_time_days=r.lead_time_days,
                dependency_task_ids=dep_ids,
                start_date=r.start_date,
                end_date=r.end_date,
                deleted_at=r.deleted_at,
            )
            self.db.add(clone)
        self.db.flush()

    def _serialize_task_board(self, project_id: str) -> Dict[str, Any]:
        return self._project_task_service().serialize_board(project_id)

    def _seed_tasks_from_template(self, project_id: str, template_id: Optional[str]) -> None:
        try:
            self._project_task_service().seed_tasks_from_template(project_id, template_id)
        except CommercialProjectTaskError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    def list_task_templates(self) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(CommercialActivityTemplate)
            .filter(
                CommercialActivityTemplate.is_active.is_(True),
                CommercialActivityTemplate.template_scope == "project",
            )
            .order_by(CommercialActivityTemplate.name.asc())
            .all()
        )
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "description": r.description,
                "version_number": int(r.version_number or 1),
                "template_scope": getattr(r, "template_scope", None) or "project",
            }
            for r in rows
        ]

    def preview_task_board_schedule(
        self,
        *,
        task_board: Dict[str, Any],
        baseline_start_date: Optional[str] = None,
        changed_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        scheduler = TaskDependencyScheduleService(self.db)
        try:
            return scheduler.recalculate(
                task_board=task_board,
                baseline_start_date=scheduler._parse_date(baseline_start_date),
                changed_task_id=changed_task_id,
            )
        except TaskDependencyScheduleError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    def apply_task_board_schedule(
        self,
        project_id: str,
        *,
        task_board: Dict[str, Any],
        baseline_start_date: Optional[str] = None,
        changed_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = self.db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
        if not p:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        baseline = baseline_start_date or (p.start_date.isoformat() if p.start_date else None)
        out = self.preview_task_board_schedule(
            task_board=task_board,
            baseline_start_date=baseline,
            changed_task_id=changed_task_id,
        )
        scheduled_board = dict(out.get("task_board") or {})
        try:
            self._project_task_service().replace_board(project_id, scheduled_board)
        except CommercialProjectTaskError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
        self.db.commit()
        return {"task_board": self._serialize_task_board(project_id), "impacts": out.get("impacts") or []}

    def list_projects_select(self, search_query: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        q = self.db.query(CommercialProject, CommercialLead).join(
            CommercialLead, CommercialProject.lead_id == CommercialLead.id
        )
        if search_query and search_query.strip():
            like = f"%{search_query.strip()}%"
            q = q.filter(
                or_(
                    CommercialProject.title.ilike(like),
                    CommercialLead.lead_code.ilike(like),
                    CommercialLead.title.ilike(like),
                )
            )
        cap = max(1, min(int(limit or 100), 300))
        rows = q.order_by(CommercialProject.title.asc()).limit(cap).all()
        return [
            {"id": str(p.id), "title": p.title, "lead_code": (lead.lead_code or "") if lead else ""}
            for p, lead in rows
        ]

    def _serialize_list_row(self, p: CommercialProject) -> Dict[str, Any]:
        lead = p.lead
        cust = lead.customer if lead else None
        owner = p.owner
        owner_ids = self._coerce_owner_ids(p.owner_user_id, p.project_owner_user_ids)
        owner_names = self._owner_names_for_ids(owner_ids)
        lead_pc = (
            self.db.query(func.count(CommercialProject.id))
            .filter(CommercialProject.lead_id == (lead.id if lead else None))
            .scalar()
            if lead
            else 0
        )
        ps = getattr(p, "project_stage", None)
        return {
            "id": str(p.id),
            "title": p.title,
            "brief": p.brief,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "status": p.status,
            "project_stage_id": str(p.project_stage_id) if p.project_stage_id else "",
            "project_stage_code": ps.code if ps else None,
            "project_stage_name": ps.label if ps else None,
            "lead_id": str(lead.id) if lead else "",
            "lead_code": lead.lead_code if lead else "",
            "customer_code": cust.customer_code if cust else None,
            "customer_name": cust.customer_name if cust else None,
            "customer_ids": self._project_customer_ids(p),
            "project_lead_count": len(self._project_lead_ids(p)),
            "project_leads": self._project_leads_payload(p),
            "lead_project_count": int(lead_pc or 0),
            "owner_user_id": p.owner_user_id,
            "owner_user_ids": owner_ids,
            "owner_name": self._owner_display(owner),
            "owner_names": owner_names,
            "developer_customer_id": str(p.developer_customer_id) if p.developer_customer_id else "",
            "developer_customer_name": p.developer_customer.customer_name if getattr(p, "developer_customer", None) else None,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }

    def list_projects(
        self,
        page: int = 1,
        limit: int = 50,
        owner_user_id: Optional[str] = None,
        status: Optional[str] = None,
        search_query: Optional[str] = None,
        lead_id: Optional[str] = None,
        project_stage_id: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        q = (
            self.db.query(CommercialProject)
            .options(
                joinedload(CommercialProject.lead).joinedload(CommercialLead.customer),
                joinedload(CommercialProject.owner),
                joinedload(CommercialProject.project_stage),
                joinedload(CommercialProject.developer_customer),
            )
            .outerjoin(CommercialLead, CommercialProject.lead_id == CommercialLead.id)
            .outerjoin(Customer, CommercialLead.customer_id == Customer.id)
        )
        if self._project_customer_links_enabled():
            q = q.options(joinedload(CommercialProject.project_customers))
        if self._project_lead_links_enabled():
            q = q.options(joinedload(CommercialProject.project_leads).joinedload(CommercialProjectLead.lead))
        filters = []
        if owner_user_id and owner_user_id.strip():
            uid = owner_user_id.strip()
            filters.append(
                or_(
                    CommercialProject.owner_user_id == uid,
                    CommercialProject.project_owner_user_ids.contains([uid]),
                )
            )
        if lead_id and lead_id.strip():
            filters.append(CommercialProject.lead_id == lead_id.strip())
        if customer_id and customer_id.strip():
            cid = customer_id.strip()
            if self._project_customer_links_enabled():
                linked_project_ids = (
                    self.db.query(CommercialProjectCustomer.project_id)
                    .filter(CommercialProjectCustomer.customer_id == cid)
                    .subquery()
                )
                filters.append(
                    or_(
                        CommercialLead.customer_id == cid,
                        CommercialProject.id.in_(linked_project_ids),
                    )
                )
            else:
                filters.append(CommercialLead.customer_id == cid)
        if project_stage_id and project_stage_id.strip():
            filters.append(CommercialProject.project_stage_id == project_stage_id.strip())
        if status and status.strip():
            filters.append(CommercialProject.status == status.strip())
        if search_query and (qstr := search_query.strip()):
            like = f"%{qstr}%"
            filters.append(
                or_(
                    CommercialProject.title.ilike(like),
                    CommercialLead.lead_code.ilike(like),
                    CommercialLead.title.ilike(like),
                    Customer.customer_name.ilike(like),
                    Customer.customer_code.ilike(like),
                )
            )
        if filters:
            q = q.filter(and_(*filters))
        total = q.count()
        offset = (page - 1) * limit
        rows = (
            q.order_by(CommercialProject.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_list_row(p) for p in rows], total

    def _quotation_state_counts(self, project_id: str) -> Dict[str, int]:
        mq_ws = aliased(WorkflowStage)
        q = (
            self.db.query(mq_ws.code, func.count(CommercialMasterQuotation.id))
            .join(CommercialTender, CommercialMasterQuotation.tender_id == CommercialTender.id)
            .join(
                mq_ws,
                CommercialMasterQuotation.quotation_stage_id == mq_ws.id,
            )
            .filter(
                CommercialTender.project_id == project_id,
                mq_ws.domain == WORKFLOW_DOMAIN_QUOTATION,
            )
            .group_by(mq_ws.code)
        )
        return {str(code or "unknown"): int(cnt) for code, cnt in q.all()}

    def _quotation_open_vs_terminal_amounts(
        self, project_id: str
    ) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
        """Split master quotation quoted_amount by quotation workflow stage terminal flag."""
        mq_ws = aliased(WorkflowStage)
        rows = (
            self.db.query(
                CommercialMasterQuotation.quoted_amount,
                CommercialMasterQuotation.quoted_currency,
                mq_ws.is_terminal,
            )
            .join(CommercialTender, CommercialMasterQuotation.tender_id == CommercialTender.id)
            .join(mq_ws, CommercialMasterQuotation.quotation_stage_id == mq_ws.id)
            .filter(
                CommercialTender.project_id == project_id,
                mq_ws.domain == WORKFLOW_DOMAIN_QUOTATION,
            )
            .all()
        )
        open_by: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        terminal_by: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for amt, ccy, is_terminal in rows:
            if amt is None or not (ccy and str(ccy).strip()):
                continue
            cur = str(ccy).strip().upper()
            if is_terminal:
                terminal_by[cur] += amt
            else:
                open_by[cur] += amt
        return dict(open_by), dict(terminal_by)

    def get_project(self, project_id: str) -> Dict[str, Any]:
        q = (
            self.db.query(CommercialProject)
            .options(
                joinedload(CommercialProject.lead).joinedload(CommercialLead.customer),
                joinedload(CommercialProject.lead).joinedload(CommercialLead.lead_stage),
                joinedload(CommercialProject.owner),
                joinedload(CommercialProject.project_stage),
                joinedload(CommercialProject.developer_customer),
                joinedload(CommercialProject.tenders),
            )
            .filter(CommercialProject.id == project_id)
        )
        if self._project_customer_links_enabled():
            q = q.options(joinedload(CommercialProject.project_customers))
        if self._project_lead_links_enabled():
            q = q.options(joinedload(CommercialProject.project_leads).joinedload(CommercialProjectLead.lead))
        p = q.first()
        if not p:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        lead = p.lead
        cust = lead.customer if lead else None
        owner = p.owner
        owner_ids = self._coerce_owner_ids(p.owner_user_id, p.project_owner_user_ids)
        owner_names = self._owner_names_for_ids(owner_ids)
        tenders_out: List[Dict[str, Any]] = []
        forecast_by_currency: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for t in p.tenders or []:
            mq_count = (
                self.db.query(func.count(CommercialMasterQuotation.id))
                .filter(CommercialMasterQuotation.tender_id == t.id)
                .scalar()
            )
            tenders_out.append(
                {
                    "id": str(t.id),
                    "tender_code": t.tender_code,
                    "title": t.title,
                    "forecast_amount": t.forecast_amount,
                    "forecast_currency": t.forecast_currency,
                    "pipeline_stage": t.pipeline_stage,
                    "expected_close_on": t.expected_close_on.isoformat() if t.expected_close_on else None,
                    "master_quotation_count": int(mq_count or 0),
                }
            )
            if t.forecast_amount is not None and t.forecast_currency:
                forecast_by_currency[t.forecast_currency] += t.forecast_amount
        st = lead.lead_stage if lead else None
        lead_pc = (
            int(
                self.db.query(func.count(CommercialProject.id))
                .filter(CommercialProject.lead_id == lead.id)
                .scalar()
                or 0
            )
            if lead
            else 0
        )
        link_rows = (
            self.db.query(EntityAttachmentLink, Attachment)
            .join(Attachment, EntityAttachmentLink.attachment_id == Attachment.id)
            .filter(
                EntityAttachmentLink.entity_type == AUDIT_ENTITY_COMMERCIAL_PROJECT,
                EntityAttachmentLink.entity_id == project_id,
                Attachment.is_deleted.is_(False),
            )
            .order_by(EntityAttachmentLink.sort_order.nullslast(), EntityAttachmentLink.created_at)
            .all()
        )
        docs = [self._serialize_attachment(att) for _lnk, att in link_rows]
        pst = p.project_stage
        stage_summary: Optional[Dict[str, Any]] = None
        if pst:
            stage_summary = {
                "id": str(pst.id),
                "code": pst.code,
                "label": pst.label,
                "sort_order": int(pst.sort_order or 0),
                "is_terminal": bool(pst.is_terminal),
                "can_go_back": bool(getattr(pst, "can_go_back", False)),
            }
        open_amt, term_amt = self._quotation_open_vs_terminal_amounts(str(p.id))
        return {
            "id": str(p.id),
            "title": p.title,
            "brief": p.brief,
            "notes": p.notes,
            "address_line_1": (p.address_line_1 or "").strip() or None,
            "address_line_2": (p.address_line_2 or "").strip() or None,
            "postcode": (p.postcode or "").strip() or None,
            "city": (p.city or "").strip() or None,
            "state": (p.state or "").strip() or None,
            "country": (p.country or "").strip() or None,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "task_template_id": str(p.task_template_id) if p.task_template_id else None,
            "task_board": self._serialize_task_board(str(p.id)),
            "status": p.status,
            "project_stage_id": str(p.project_stage_id),
            "project_stage": stage_summary,
            "owner_user_id": p.owner_user_id,
            "owner_user_ids": owner_ids,
            "owner_name": self._owner_display(owner),
            "owner_names": owner_names,
            "developer_customer_id": str(p.developer_customer_id) if p.developer_customer_id else "",
            "developer_customer_name": p.developer_customer.customer_name if getattr(p, "developer_customer", None) else None,
            "lead_id": str(lead.id) if lead else "",
            "lead_code": lead.lead_code if lead else "",
            "lead_title": lead.title if lead else "",
            "lead_stage_code": st.code if st else None,
            "lead_stage_name": st.label if st else None,
            "lead_project_count": lead_pc,
            "customer_id": str(cust.id) if cust else None,
            "customer_code": cust.customer_code if cust else None,
            "customer_name": cust.customer_name if cust else None,
            "customer_ids": self._project_customer_ids(p),
            "project_customers": self._project_customers_payload(p),
            "project_leads": self._project_leads_payload(p),
            "tenders": tenders_out,
            "tender_count": len(tenders_out),
            "forecast_by_currency": {k: str(v) for k, v in forecast_by_currency.items()},
            "quotation_execution_state_counts": self._quotation_state_counts(str(p.id)),
            "open_quotation_amount_by_currency": {k: str(v) for k, v in open_amt.items()},
            "sales_order_amount_by_currency": {k: str(v) for k, v in term_amt.items()},
            "documents": docs,
            "project_members": self._coerce_project_members(p.project_members),
            "project_customer_contacts": self._serialize_customer_contacts(p),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }

    def create_from_lead(
        self,
        data: CommercialProjectCreate,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        lead = None
        lead_id_raw = (data.lead_id or "").strip() if data.lead_id else ""
        if lead_id_raw:
            lead = (
                self.db.query(CommercialLead)
                .options(joinedload(CommercialLead.lead_stage))
                .filter(CommercialLead.id == lead_id_raw)
                .first()
            )
            if not lead:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        developer_customer_id = (data.developer_customer_id or "").strip()
        developer_customer = self.db.query(Customer).filter(Customer.id == developer_customer_id).first()
        if not developer_customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Developer customer not found")
        owner_id = (data.owner_user_id or "").strip() or actor_user_id
        owner = self.db.query(User).filter(User.id == owner_id).first()
        if not owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project owner user not found")
        owner_ids = self._coerce_owner_ids(owner_id, data.project_owner_user_ids or [])
        title = (data.title or "").strip() or (lead.title if lead else "")
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project title is required")
        proj_status = (data.status or "").strip() or "active"
        stage = self._workflow_stage_from_legacy_status(proj_status)
        if data.project_stage_id and str(data.project_stage_id).strip():
            stage = self._require_project_stage_id(str(data.project_stage_id))
        tid = (data.task_template_id or "").strip() or None
        start_date = self._parse_date(data.start_date, "start_date")
        project_members = self._coerce_project_members([])
        contacts = self._sanitize_contacts(
            list(data.project_customer_contacts) if data.project_customer_contacts else None
        )
        project = CommercialProject(
            id=_uuid(),
            lead_id=str(lead.id) if lead else None,
            owner_user_id=owner_id,
            project_owner_user_ids=owner_ids,
            developer_customer_id=developer_customer_id,
            project_stage_id=str(stage.id),
            title=title,
            brief=(data.brief or "").strip() or None,
            notes=(data.notes or "").strip() or None,
            address_line_1=(data.address_line_1 or "").strip() or None,
            address_line_2=(data.address_line_2 or "").strip() or None,
            postcode=(data.postcode or "").strip() or None,
            city=(data.city or "").strip() or None,
            state=(data.state or "").strip() or None,
            country=(data.country or "").strip() or None,
            start_date=start_date,
            end_date=self._parse_date(data.end_date, "end_date"),
            task_template_id=tid,
            project_members=project_members,
            project_customer_contacts=contacts,
            status=stage.code,
        )
        self.db.add(project)
        self.db.flush()
        if tid:
            self._seed_tasks_from_template(str(project.id), tid)
            try:
                svc = self._project_task_service()
                # Seed initial start/end from the project's baseline, then run the
                # dependency cascade so changes propagate as the user edits later.
                svc.seed_schedule_from_baseline(
                    str(project.id),
                    baseline_start_date=start_date.isoformat() if start_date else None,
                )
                svc.apply_schedule(
                    str(project.id),
                    baseline_start_date=start_date.isoformat() if start_date else None,
                )
            except CommercialProjectTaskError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
        if lead:
            self._sync_project_lead_links(str(project.id), [str(lead.id)])
        customer_ids = list(data.customer_ids or [])
        if lead and getattr(lead, "customer_id", None):
            customer_ids.insert(0, str(lead.customer_id))
        self._sync_project_customer_links(str(project.id), customer_ids)
        if lead:
            existing_count = (
                self.db.query(func.count(CommercialProject.id))
                .filter(CommercialProject.lead_id == lead.id)
                .scalar()
                or 0
            )
            if int(existing_count) <= 1:
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
            AUDIT_ENTITY_COMMERCIAL_PROJECT,
            str(project.id),
            "INSERT",
            new_values={
                "title": project.title,
                "lead_id": str(lead.id) if lead else None,
                "owner_user_id": owner_id,
            },
            user_id=actor_user_id,
            ip_address=ip_address,
        )
        from app.modules.commercial_core.services.entity_conversation_service import ENTITY_PROJECT, append_system_message

        append_system_message(
            self.db,
            entity_type=ENTITY_PROJECT,
            entity_id=str(project.id),
            body_html=f"<p>{html.escape(project.title or '')} is created.</p>",
        )
        self.db.commit()
        return self.get_project(str(project.id))

    def duplicate_project(
        self,
        project_id: str,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = (
            self.db.query(CommercialProject)
            .options(joinedload(CommercialProject.lead), joinedload(CommercialProject.project_stage))
            .filter(CommercialProject.id == project_id)
            .first()
        )
        if not p:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        st0 = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_PROJECT,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order.asc(), WorkflowStage.code.asc())
            .first()
        )
        if not st0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Project workflow stages are not configured",
            )
        suffix = " (Copy)"
        base_title = (p.title or "").strip() or "Project"
        new_title = (base_title + suffix).strip()
        owner_id = (p.owner_user_id or "").strip() or actor_user_id
        owner = self.db.query(User).filter(User.id == owner_id).first()
        if not owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project owner user not found")
        owner_ids_raw = copy.deepcopy(list(p.project_owner_user_ids)) if isinstance(p.project_owner_user_ids, list) else []
        members_raw = copy.deepcopy(list(p.project_members)) if isinstance(p.project_members, list) else []
        contacts_raw = copy.deepcopy(list(p.project_customer_contacts)) if isinstance(p.project_customer_contacts, list) else []
        dup = CommercialProject(
            id=_uuid(),
            lead_id=str(p.lead_id) if p.lead_id else None,
            owner_user_id=owner_id,
            project_owner_user_ids=self._coerce_owner_ids(owner_id, owner_ids_raw),
            developer_customer_id=p.developer_customer_id,
            project_stage_id=str(st0.id),
            title=new_title,
            brief=(p.brief or "").strip() or None,
            notes=(p.notes or "").strip() or None,
            address_line_1=(p.address_line_1 or "").strip() or None,
            address_line_2=(p.address_line_2 or "").strip() or None,
            postcode=(p.postcode or "").strip() or None,
            city=(p.city or "").strip() or None,
            state=(p.state or "").strip() or None,
            country=(p.country or "").strip() or None,
            start_date=p.start_date,
            end_date=p.end_date,
            task_template_id=p.task_template_id,
            project_members=self._coerce_project_members(members_raw),
            project_customer_contacts=contacts_raw,
            status=st0.code,
        )
        self.db.add(dup)
        self.db.flush()
        self._duplicate_project_tasks(str(p.id), str(dup.id))
        self._sync_project_lead_links(str(dup.id), self._project_lead_ids(p))
        self._sync_project_customer_links(str(dup.id), self._project_customer_ids(p))
        log_audit(
            self.db,
            AUDIT_ENTITY_COMMERCIAL_PROJECT,
            str(dup.id),
            "INSERT",
            new_values={
                "title": dup.title,
                "lead_id": str(dup.lead_id) if dup.lead_id else None,
                "owner_user_id": owner_id,
            },
            user_id=actor_user_id,
            ip_address=ip_address,
        )
        from app.modules.commercial_core.services.entity_conversation_service import ENTITY_PROJECT, append_system_message

        append_system_message(
            self.db,
            entity_type=ENTITY_PROJECT,
            entity_id=str(dup.id),
            body_html=f"<p>{html.escape(dup.title or '')} is created.</p>",
        )
        self.db.commit()
        return self.get_project(str(dup.id))

    def update_project(
        self,
        project_id: str,
        data: CommercialProjectUpdate,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = self.db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
        if not p:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        prev_project_stage_id = str(p.project_stage_id) if p.project_stage_id else ""
        old = {
            "title": p.title,
            "brief": p.brief,
            "status": p.status,
            "project_stage_id": str(p.project_stage_id),
            "owner_user_id": p.owner_user_id,
            "project_owner_user_ids": self._coerce_owner_ids(p.owner_user_id, p.project_owner_user_ids),
            "developer_customer_id": str(p.developer_customer_id) if p.developer_customer_id else None,
            "task_template_id": str(p.task_template_id) if p.task_template_id else None,
            "project_members": self._coerce_project_members(p.project_members),
        }
        if data.lead_id is not None and str(data.lead_id).strip():
            lead = self.db.query(CommercialLead).filter(CommercialLead.id == str(data.lead_id).strip()).first()
            if not lead:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
            p.lead_id = str(lead.id)
        if data.title is not None:
            p.title = (data.title or "").strip()
        if data.notes is not None:
            p.notes = (data.notes or "").strip() or None
        if data.brief is not None:
            p.brief = (data.brief or "").strip() or None
        if data.start_date is not None:
            p.start_date = self._parse_date(data.start_date, "start_date")
            existing_tasks = (
                self.db.query(func.count(CommercialProjectTask.id))
                .filter(
                    CommercialProjectTask.project_id == p.id,
                    CommercialProjectTask.deleted_at.is_(None),
                )
                .scalar()
            )
            if int(existing_tasks or 0) > 0:
                try:
                    self._project_task_service().apply_schedule(
                        str(p.id),
                        baseline_start_date=p.start_date.isoformat() if p.start_date else None,
                    )
                except CommercialProjectTaskError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
        if data.end_date is not None:
            p.end_date = self._parse_date(data.end_date, "end_date")
        if data.address_line_1 is not None:
            p.address_line_1 = (data.address_line_1 or "").strip() or None
        if data.address_line_2 is not None:
            p.address_line_2 = (data.address_line_2 or "").strip() or None
        if data.postcode is not None:
            p.postcode = (data.postcode or "").strip() or None
        if data.city is not None:
            p.city = (data.city or "").strip() or None
        if data.state is not None:
            p.state = (data.state or "").strip() or None
        if data.country is not None:
            p.country = (data.country or "").strip() or None
        if data.project_stage_id is not None and str(data.project_stage_id).strip():
            st = self._require_project_stage_id(str(data.project_stage_id))
            p.project_stage_id = str(st.id)
            p.status = st.code
        elif data.status is not None:
            st = self._workflow_stage_from_legacy_status(data.status.strip())
            p.project_stage_id = str(st.id)
            p.status = st.code
        if data.owner_user_id is not None:
            u = self.db.query(User).filter(User.id == data.owner_user_id).first()
            if not u:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner user not found")
            p.owner_user_id = data.owner_user_id
            p.project_owner_user_ids = self._coerce_owner_ids(p.owner_user_id, p.project_owner_user_ids)
        if data.project_owner_user_ids is not None:
            candidate_ids = self._coerce_owner_ids(p.owner_user_id, data.project_owner_user_ids)
            existing_users = {
                str(row[0])
                for row in self.db.query(User.id).filter(User.id.in_(candidate_ids)).all()
                if row and row[0]
            }
            if len(existing_users) != len(candidate_ids):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more owners were not found")
            p.project_owner_user_ids = candidate_ids
            p.owner_user_id = candidate_ids[0]
        if data.developer_customer_id is not None:
            dev_id = str(data.developer_customer_id).strip()
            dev = self.db.query(Customer).filter(Customer.id == dev_id).first()
            if not dev:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Developer customer not found")
            p.developer_customer_id = dev_id
        if data.task_template_id is not None:
            tid = (data.task_template_id or "").strip() or None
            p.task_template_id = tid
            self._seed_tasks_from_template(str(p.id), tid)
            try:
                svc = self._project_task_service()
                svc.seed_schedule_from_baseline(
                    str(p.id),
                    baseline_start_date=p.start_date.isoformat() if p.start_date else None,
                )
                svc.apply_schedule(
                    str(p.id),
                    baseline_start_date=p.start_date.isoformat() if p.start_date else None,
                )
            except CommercialProjectTaskError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
        if data.task_board is not None:
            try:
                self._project_task_service().replace_board(str(p.id), dict(data.task_board or {}))
            except CommercialProjectTaskError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
        if data.project_members is not None:
            payload = [m.model_dump() for m in data.project_members]
            p.project_members = self._coerce_project_members(payload)
        if data.project_customer_contacts is not None:
            p.project_customer_contacts = self._sanitize_contacts(list(data.project_customer_contacts))
        if data.customer_ids is not None:
            customer_ids = list(data.customer_ids or [])
            lead = getattr(p, "lead", None)
            if lead and getattr(lead, "customer_id", None):
                customer_ids.insert(0, str(lead.customer_id))
            self._sync_project_customer_links(str(p.id), customer_ids)
        if data.lead_id is not None and str(data.lead_id).strip():
            ids = [str(data.lead_id).strip()]
            if p.lead_id:
                ids.append(str(p.lead_id))
            self._sync_project_lead_links(str(p.id), ids)
        new = {
            "title": p.title,
            "brief": p.brief,
            "status": p.status,
            "project_stage_id": str(p.project_stage_id),
            "owner_user_id": p.owner_user_id,
            "project_owner_user_ids": self._coerce_owner_ids(p.owner_user_id, p.project_owner_user_ids),
            "developer_customer_id": str(p.developer_customer_id) if p.developer_customer_id else None,
            "task_template_id": str(p.task_template_id) if p.task_template_id else None,
            "project_members": self._coerce_project_members(p.project_members),
        }
        if old != new:
            log_audit(
                self.db,
                AUDIT_ENTITY_COMMERCIAL_PROJECT,
                str(p.id),
                "UPDATE",
                old_values=old,
                new_values=new,
                user_id=actor_user_id,
                ip_address=ip_address,
            )
        stage_changed = prev_project_stage_id != (str(p.project_stage_id) if p.project_stage_id else "")
        if stage_changed:
            from app.modules.commercial_core.services.entity_conversation_service import ENTITY_PROJECT, append_system_message

            st_row = (
                self.db.query(WorkflowStage).filter(WorkflowStage.id == p.project_stage_id).first()
            )
            label = (st_row.label or "").strip() if st_row else (p.status or "")
            append_system_message(
                self.db,
                entity_type=ENTITY_PROJECT,
                entity_id=str(p.id),
                body_html=f"<p>{html.escape(p.title or '')} moved to {html.escape(label)}.</p>",
            )
        self.db.commit()
        return self.get_project(project_id)

    def share_ownership(
        self,
        project_id: str,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = self.db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
        if not p:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        owner_ids = self._coerce_owner_ids(p.owner_user_id, p.project_owner_user_ids)
        actor_id = (actor_user_id or "").strip()
        if actor_id and actor_id not in owner_ids:
            owner_ids.append(actor_id)
            p.project_owner_user_ids = owner_ids
            log_audit(
                self.db,
                AUDIT_ENTITY_COMMERCIAL_PROJECT,
                str(p.id),
                "UPDATE",
                old_values={"project_owner_user_ids": owner_ids[:-1]},
                new_values={"project_owner_user_ids": owner_ids},
                user_id=actor_user_id,
                ip_address=ip_address,
            )
            self.db.commit()
        return self.get_project(project_id)

    def disown(
        self,
        project_id: str,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = self.db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
        if not p:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        actor_id = (actor_user_id or "").strip()
        owner_ids = self._coerce_owner_ids(p.owner_user_id, p.project_owner_user_ids)
        if actor_id not in owner_ids:
            return self.get_project(project_id)
        if len(owner_ids) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A project must have at least one owner")
        next_owner_ids = [x for x in owner_ids if x != actor_id]
        p.project_owner_user_ids = next_owner_ids
        if p.owner_user_id == actor_id:
            p.owner_user_id = next_owner_ids[0]
        log_audit(
            self.db,
            AUDIT_ENTITY_COMMERCIAL_PROJECT,
            str(p.id),
            "UPDATE",
            old_values={"project_owner_user_ids": owner_ids},
            new_values={"project_owner_user_ids": next_owner_ids, "owner_user_id": p.owner_user_id},
            user_id=actor_user_id,
            ip_address=ip_address,
        )
        self.db.commit()
        return self.get_project(project_id)

    def delete_project(
        self,
        project_id: str,
        *,
        actor_user_id: str,
        ip_address: Optional[str] = None,
    ) -> None:
        p = self.db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
        if not p:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        log_audit(
            self.db,
            AUDIT_ENTITY_COMMERCIAL_PROJECT,
            str(p.id),
            "DELETE",
            old_values={
                "title": p.title,
                "lead_id": str(p.lead_id) if p.lead_id else None,
            },
            user_id=actor_user_id,
            ip_address=ip_address,
        )
        self.db.delete(p)
        self.db.commit()
