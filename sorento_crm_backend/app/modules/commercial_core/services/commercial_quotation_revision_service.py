"""Master quotation revision workspace: create revisions, working/final pointers, attachments."""
from __future__ import annotations

import copy
import html
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, inspect
from sqlalchemy.orm import Session, joinedload

from app.modules.commercial_core.constants import COMMERCIAL_QUOTATION_REVISION_ENTITY_TYPE
from app.modules.commercial_core.models import (
    CommercialLead,
    CommercialMasterQuotation,
    CommercialProject,
    CommercialProjectCustomer,
    CommercialProjectLead,
    CommercialQuotationRevision,
    CommercialSalesOrder,
    CommercialSalesOrderStatus,
    CommercialTender,
)
from app.models.workflow_stage import WORKFLOW_DOMAIN_QUOTATION, WorkflowStage
from app.modules.commercial_core.services.commercial_hierarchy_service import (
    CommercialHierarchyError,
    ToleranceAdvanceConfirmationRequired,
    assert_revision_matches_master,
)
from app.modules.commercial_activity.services.commercial_activity_plan_service import CommercialActivityPlanService
from app.modules.commercial_core.services.commercial_quotation_package_templates import (
    build_pricing_snapshot_from_package_template,
    get_quotation_package_template_by_id,
)
from app.modules.commercial_core.services.commercial_quotation_price_policy import (
    apply_master_quotation_stage_change,
    ordered_active_quotation_stages,
    sync_master_from_working_revision,
    user_may_access_project_quotations,
)
from app.services.task_dependency_schedule_service import (
    TaskDependencyScheduleError,
    TaskDependencyScheduleService,
)
from app.services.error_handler import handle_not_found


def _normalize_snapshot(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not data:
        return {}
    if not isinstance(data, dict):
        raise CommercialHierarchyError("pricing_snapshot must be a JSON object.")
    return copy.deepcopy(data)


class CommercialQuotationRevisionService:
    def __init__(self, db: Session):
        self.db = db

    def _require_working_revision_editable(self, mq: CommercialMasterQuotation) -> None:
        ap = (getattr(mq, "pricing_approval_status", None) or "").strip().lower()
        if ap == "pending":
            raise CommercialHierarchyError(
                "Quotation is awaiting pricing approval; revision content cannot be changed."
            )
        stages = ordered_active_quotation_stages(self.db)
        if not mq.quotation_stage_id:
            raise CommercialHierarchyError("Quotation has no workflow stage.")
        if not stages:
            raise CommercialHierarchyError("No quotation workflow stages configured.")
        if str(mq.quotation_stage_id) != str(stages[0].id):
            raise CommercialHierarchyError("Quotations can only be edited in the first workflow stage.")

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

    def get_tender_by_code(self, tender_code: str) -> CommercialTender:
        t = (
            self.db.query(CommercialTender)
            .filter(CommercialTender.tender_code == (tender_code or "").strip())
            .first()
        )
        if not t:
            raise handle_not_found("Tender", tender_code)
        return t

    def list_masters_for_tender_code(self, tender_code: str) -> List[CommercialMasterQuotation]:
        t = self.get_tender_by_code(tender_code)
        return (
            self.db.query(CommercialMasterQuotation)
            .options(
                joinedload(CommercialMasterQuotation.tender),
                joinedload(CommercialMasterQuotation.customer),
                joinedload(CommercialMasterQuotation.quotation_stage),
                joinedload(CommercialMasterQuotation.owner),
                joinedload(CommercialMasterQuotation.current_working_revision),
                joinedload(CommercialMasterQuotation.final_selected_revision),
            )
            .filter(CommercialMasterQuotation.tender_id == t.id)
            .order_by(CommercialMasterQuotation.quotation_code.asc())
            .all()
        )

    def get_master_by_tender_and_quotation_codes(
        self, tender_code: str, quotation_code: str
    ) -> CommercialMasterQuotation:
        t = self.get_tender_by_code(tender_code)
        mq = (
            self.db.query(CommercialMasterQuotation)
            .options(
                joinedload(CommercialMasterQuotation.quotation_stage),
                joinedload(CommercialMasterQuotation.tender),
                joinedload(CommercialMasterQuotation.customer),
                joinedload(CommercialMasterQuotation.current_working_revision),
                joinedload(CommercialMasterQuotation.final_selected_revision),
            )
            .filter(
                CommercialMasterQuotation.tender_id == t.id,
                CommercialMasterQuotation.quotation_code == (quotation_code or "").strip(),
            )
            .first()
        )
        if not mq:
            raise handle_not_found("Master quotation", f"{tender_code}/{quotation_code}")
        return mq

    def _require_mq_actor_membership(self, mq: CommercialMasterQuotation, actor_user_id: str) -> None:
        t = mq.tender
        if not t:
            raise CommercialHierarchyError("Tender not loaded for master quotation.")
        if not user_may_access_project_quotations(self.db, str(t.project_id), actor_user_id):
            raise CommercialHierarchyError("Only project owners may modify this quotation.")

    def get_master_by_id(self, master_id: str) -> CommercialMasterQuotation:
        mq = (
            self.db.query(CommercialMasterQuotation)
            .options(
                joinedload(CommercialMasterQuotation.quotation_stage),
                joinedload(CommercialMasterQuotation.tender),
                joinedload(CommercialMasterQuotation.customer),
                joinedload(CommercialMasterQuotation.current_working_revision),
                joinedload(CommercialMasterQuotation.final_selected_revision),
            )
            .filter(CommercialMasterQuotation.id == master_id)
            .first()
        )
        if not mq:
            raise handle_not_found("Master quotation", master_id)
        return mq

    def list_revisions(self, master_quotation_id: str) -> List[CommercialQuotationRevision]:
        self.get_master_by_id(master_quotation_id)
        return (
            self.db.query(CommercialQuotationRevision)
            .filter(CommercialQuotationRevision.master_quotation_id == master_quotation_id)
            .order_by(CommercialQuotationRevision.revision_number.asc())
            .all()
        )

    def get_revision(self, revision_id: str) -> CommercialQuotationRevision:
        rev = self.db.query(CommercialQuotationRevision).filter(CommercialQuotationRevision.id == revision_id).first()
        if not rev:
            raise handle_not_found("Quotation revision", revision_id)
        return rev

    def _next_revision_number(self, master_quotation_id: str) -> int:
        n = (
            self.db.query(func.max(CommercialQuotationRevision.revision_number))
            .filter(CommercialQuotationRevision.master_quotation_id == master_quotation_id)
            .scalar()
        )
        return int(n or 0) + 1

    def _active_sales_order(self, master_quotation_id: str) -> Optional[CommercialSalesOrder]:
        return (
            self.db.query(CommercialSalesOrder)
            .filter(
                CommercialSalesOrder.master_quotation_id == master_quotation_id,
                CommercialSalesOrder.status.in_(CommercialSalesOrderStatus.ACTIVE_FOR_TENDER_UNIQUE),
            )
            .first()
        )

    def create_revision(
        self,
        master_quotation_id: str,
        *,
        actor_user_id: str,
        copy_from_revision_id: Optional[str] = None,
        revision_notes: Optional[str] = None,
        pricing_snapshot: Optional[Dict[str, Any]] = None,
    ) -> CommercialQuotationRevision:
        mq = self.get_master_by_id(master_quotation_id)
        self._require_mq_actor_membership(mq, actor_user_id)
        self._require_working_revision_editable(mq)
        snap = _normalize_snapshot(pricing_snapshot)
        if copy_from_revision_id:
            src = self.get_revision(copy_from_revision_id)
            assert_revision_matches_master(self.db, src.id, master_quotation_id)
            if not snap:
                snap = _normalize_snapshot(src.pricing_snapshot)  # type: ignore[arg-type]
        rev = CommercialQuotationRevision(
            master_quotation_id=master_quotation_id,
            revision_number=self._next_revision_number(master_quotation_id),
            pricing_snapshot=snap or {},
            revision_notes=(revision_notes or "").strip() or None,
        )
        self.db.add(rev)
        self.db.flush()
        # New revision becomes the current working copy (Revise / add revision).
        mq.current_working_revision_id = rev.id
        self.db.flush()
        sync_master_from_working_revision(self.db, mq)
        self.db.flush()
        self.db.refresh(rev)
        return rev

    def update_revision(
        self,
        revision_id: str,
        *,
        actor_user_id: str,
        pricing_snapshot: Optional[Dict[str, Any]] = None,
        revision_notes: Optional[str] = None,
    ) -> CommercialQuotationRevision:
        rev = self.get_revision(revision_id)
        mq0 = self.get_master_by_id(str(rev.master_quotation_id))
        self._require_mq_actor_membership(mq0, actor_user_id)
        self._require_working_revision_editable(mq0)
        if pricing_snapshot is not None:
            rev.pricing_snapshot = _normalize_snapshot(pricing_snapshot)
        if revision_notes is not None:
            rev.revision_notes = (revision_notes or "").strip() or None
        self.db.flush()
        mq = self.get_master_by_id(str(rev.master_quotation_id))
        if str(mq.current_working_revision_id or "") == str(rev.id):
            sync_master_from_working_revision(self.db, mq)
            self.db.flush()
        self.db.refresh(rev)
        return rev

    def set_current_working_revision(
        self, master_quotation_id: str, revision_id: Optional[str], *, actor_user_id: str
    ) -> CommercialMasterQuotation:
        mq = self.get_master_by_id(master_quotation_id)
        self._require_mq_actor_membership(mq, actor_user_id)
        self._require_working_revision_editable(mq)
        if revision_id:
            assert_revision_matches_master(self.db, revision_id, master_quotation_id)
            mq.current_working_revision_id = revision_id
        else:
            mq.current_working_revision_id = None
        self.db.flush()
        sync_master_from_working_revision(self.db, mq)
        self.db.flush()
        self.db.refresh(mq)
        return mq

    def set_final_selected_revision(
        self, master_quotation_id: str, revision_id: Optional[str], *, actor_user_id: str
    ) -> CommercialMasterQuotation:
        mq = self.get_master_by_id(master_quotation_id)
        self._require_mq_actor_membership(mq, actor_user_id)
        so = self._active_sales_order(master_quotation_id)
        if revision_id:
            assert_revision_matches_master(self.db, revision_id, master_quotation_id)
            if so is not None and str(so.quotation_revision_id) != str(revision_id):
                raise CommercialHierarchyError(
                    "Cannot change final selected revision while a draft or confirmed sales order "
                    "exists for another revision."
                )
            mq.final_selected_revision_id = revision_id
        else:
            if so is not None:
                raise CommercialHierarchyError(
                    "Cannot clear final selected revision while a draft or confirmed sales order exists."
                )
            mq.final_selected_revision_id = None
        self.db.flush()
        self.db.refresh(mq)
        return mq

    def revision_attachment_entity(self, revision_id: str) -> Tuple[str, str]:
        self.get_revision(revision_id)
        return COMMERCIAL_QUOTATION_REVISION_ENTITY_TYPE, str(revision_id)

    def _ensure_project_workspace_tender(self, project: CommercialProject) -> CommercialTender:
        existing = (
            self.db.query(CommercialTender)
            .filter(CommercialTender.project_id == project.id)
            .order_by(CommercialTender.created_at.asc())
            .first()
        )
        if existing:
            return existing
        raw = re.sub(r"[^A-Za-z0-9]", "", str(project.id))
        base = (raw[:8] or "PROJ").upper()
        code = f"T-PJ-{base}"
        n = 0
        while self.db.query(CommercialTender).filter(CommercialTender.tender_code == code).first():
            n += 1
            code = f"T-PJ-{base}-{n}"
        t = CommercialTender(
            project_id=project.id,
            tender_code=code,
            title=f"{project.title} — quotations",
            owner_user_id=project.owner_user_id,
        )
        self.db.add(t)
        self.db.flush()
        return t

    def _next_qt_quotation_code(self, tender_id: str, year: int) -> str:
        prefix = f"QT-{year}-"
        pat = re.compile(rf"^QT-{year}-(\d+)$")
        rows = self.db.query(CommercialMasterQuotation.quotation_code).filter(CommercialMasterQuotation.tender_id == tender_id).all()
        max_n = 0
        for (qc,) in rows:
            m = pat.match((qc or "").strip())
            if m:
                max_n = max(max_n, int(m.group(1)))
        return f"{prefix}{max_n + 1:03d}"

    def _default_mq_stage(self) -> WorkflowStage:
        st = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order.asc(), WorkflowStage.code.asc())
            .first()
        )
        if not st:
            raise CommercialHierarchyError("No active master quotation stage configured.")
        return st

    def list_masters_for_project(self, project_id: str) -> List[CommercialMasterQuotation]:
        tids_subq = self.db.query(CommercialTender.id).filter(CommercialTender.project_id == project_id)
        tids = [str(r[0]) for r in tids_subq.all()]
        if not tids:
            return []
        return (
            self.db.query(CommercialMasterQuotation)
            .options(
                joinedload(CommercialMasterQuotation.tender),
                joinedload(CommercialMasterQuotation.customer),
                joinedload(CommercialMasterQuotation.quotation_stage),
                joinedload(CommercialMasterQuotation.owner),
                joinedload(CommercialMasterQuotation.current_working_revision),
                joinedload(CommercialMasterQuotation.final_selected_revision),
            )
            .filter(CommercialMasterQuotation.tender_id.in_(tids))
            .order_by(CommercialMasterQuotation.created_at.desc())
            .all()
        )

    def create_master_quotation_for_project(
        self,
        project_id: str,
        *,
        actor_user_id: str,
        title: str,
        customer_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        valid_until: Optional[date] = None,
        description: Optional[str] = None,
        remark: Optional[str] = None,
        owner_user_id: Optional[str] = None,
        task_template_id: Optional[str] = None,
        quotation_package_template_id: Optional[str] = None,
    ) -> CommercialMasterQuotation:
        def _normalize_uuid_opt(raw: Optional[str], field_label: str) -> Optional[str]:
            val = (raw or "").strip()
            if not val:
                return None
            try:
                return str(uuid.UUID(val))
            except (TypeError, ValueError):
                raise CommercialHierarchyError(f"Invalid {field_label}.")

        if not user_may_access_project_quotations(self.db, project_id, actor_user_id):
            raise CommercialHierarchyError("Only project owners may create quotations for this project.")
        p = self.db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
        if not p:
            raise handle_not_found("Project", project_id)
        normalized_lead_id = (lead_id or "").strip() or None
        lead_code_for_details: Optional[str] = None
        if normalized_lead_id:
            try:
                normalized_lead_id = str(uuid.UUID(normalized_lead_id))
            except ValueError:
                raise CommercialHierarchyError("Invalid lead.")
            lead_row = self.db.query(CommercialLead).filter(CommercialLead.id == normalized_lead_id).first()
            if not lead_row:
                raise CommercialHierarchyError("Lead not found.")
            lead_code_for_details = (lead_row.lead_code or "").strip() or None
            if self._project_lead_links_enabled():
                exists = (
                    self.db.query(CommercialProjectLead.id)
                    .filter(
                        CommercialProjectLead.project_id == p.id,
                        CommercialProjectLead.lead_id == normalized_lead_id,
                    )
                    .first()
                )
                if not exists:
                    self.db.add(CommercialProjectLead(project_id=p.id, lead_id=normalized_lead_id))
                    self.db.flush()
        explicit_customer_id = (customer_id or "").strip() or None
        project_customer_ids = set()
        if self._project_customer_links_enabled():
            project_customer_ids = {
                str(row[0])
                for row in self.db.query(CommercialProjectCustomer.customer_id)
                .filter(CommercialProjectCustomer.project_id == p.id)
                .all()
                if row and row[0]
            }
        if p.lead_id:
            lead_customer = (
                self.db.query(CommercialLead.customer_id)
                .filter(CommercialLead.id == p.lead_id)
                .first()
            )
            if lead_customer and lead_customer[0]:
                project_customer_ids.add(str(lead_customer[0]))
        if normalized_lead_id:
            linked_lead_customer = (
                self.db.query(CommercialLead.customer_id)
                .filter(CommercialLead.id == normalized_lead_id)
                .first()
            )
            if linked_lead_customer and linked_lead_customer[0]:
                linked_customer_id = str(linked_lead_customer[0])
                project_customer_ids.add(linked_customer_id)
                if self._project_customer_links_enabled():
                    has_link = (
                        self.db.query(CommercialProjectCustomer.id)
                        .filter(
                            CommercialProjectCustomer.project_id == p.id,
                            CommercialProjectCustomer.customer_id == linked_customer_id,
                        )
                        .first()
                    )
                    if not has_link:
                        self.db.add(CommercialProjectCustomer(project_id=p.id, customer_id=linked_customer_id))
                        self.db.flush()
        resolved_customer_id = explicit_customer_id
        if not normalized_lead_id and p.lead_id:
            normalized_lead_id = str(p.lead_id)
            lead_fallback = self.db.query(CommercialLead).filter(CommercialLead.id == normalized_lead_id).first()
            if lead_fallback:
                lead_code_for_details = (lead_fallback.lead_code or "").strip() or None

        if resolved_customer_id and resolved_customer_id not in project_customer_ids:
            raise CommercialHierarchyError("Selected customer does not belong to the selected project.")
        if not resolved_customer_id:
            resolved_customer_id = next(iter(project_customer_ids), None)
        tender = self._ensure_project_workspace_tender(p)
        stage = self._default_mq_stage()
        year = datetime.utcnow().year
        qcode = self._next_qt_quotation_code(str(tender.id), year)
        details: Dict[str, Any] = {}
        details["project_title"] = (p.title or "").strip() or None
        if normalized_lead_id:
            details["lead_id"] = normalized_lead_id
        if lead_code_for_details:
            details["lead_code"] = lead_code_for_details
        if description is not None and str(description).strip():
            details["description"] = str(description).strip()
        if remark is not None and str(remark).strip():
            details["remark"] = str(remark).strip()

        snap: Dict[str, Any] = {"order_items": [], "quotation_meta": {}}
        if quotation_package_template_id and str(quotation_package_template_id).strip():
            pkg = get_quotation_package_template_by_id(self.db, str(quotation_package_template_id).strip())
            if not pkg:
                raise CommercialHierarchyError("Quotation package template not found.")
            snap = build_pricing_snapshot_from_package_template(pkg)
            details["quotation_package_template_id"] = str(pkg.get("id") or "")
            details["quotation_package_template_name"] = str(pkg.get("name") or "")

        normalized_owner_user_id = _normalize_uuid_opt(owner_user_id, "owner user")
        normalized_task_template_id = _normalize_uuid_opt(task_template_id, "task template")

        mq = CommercialMasterQuotation(
            tender_id=tender.id,
            customer_id=resolved_customer_id,
            quotation_code=qcode,
            title=(title or "").strip() or qcode,
            owner_user_id=normalized_owner_user_id,
            quotation_stage_id=stage.id,
            valid_until=valid_until,
            commercial_details=details,
        )
        self.db.add(mq)
        self.db.flush()
        rev = CommercialQuotationRevision(
            master_quotation_id=mq.id,
            revision_number=1,
            pricing_snapshot=snap,
            revision_notes=None,
        )
        self.db.add(rev)
        self.db.flush()
        mq.current_working_revision_id = rev.id
        self.db.flush()
        sync_master_from_working_revision(self.db, mq)
        self.db.flush()

        if normalized_task_template_id:
            plan = CommercialActivityPlanService(self.db)
            tt = plan.get_template(normalized_task_template_id)
            if not tt or not tt.is_active:
                raise CommercialHierarchyError("Task template not found or inactive.")
            if (getattr(tt, "template_scope", None) or "project") != "quotation":
                raise CommercialHierarchyError("Task template must be scoped for quotations.")
            plan.apply_template(str(mq.id), str(tt.id), applied_by_user_id=actor_user_id, commit=False)
            merged = dict(mq.commercial_details or {})
            merged["task_template_id"] = str(tt.id)
            merged["task_template_name"] = tt.name
            mq.commercial_details = merged
            self.db.flush()
            sync_master_from_working_revision(self.db, mq)
            self.db.flush()

        self.db.refresh(mq)
        from app.models.order import Customer
        from app.models.user import User
        from app.modules.commercial_core.services.entity_conversation_service import ENTITY_MASTER_QUOTATION, ENTITY_PROJECT, append_system_message

        actor = self.db.query(User).filter(User.id == actor_user_id).first() if actor_user_id else None
        actor_name = ((actor.name or "").strip() or actor.email) if actor else "system"
        cust = (
            self.db.query(Customer).filter(Customer.id == mq.customer_id).first()
            if mq.customer_id
            else None
        )
        client_name = (cust.customer_name or "").strip() if cust else ""
        details = mq.commercial_details if isinstance(mq.commercial_details, dict) else {}
        pic_name = (details.get("customer_pic_name") or "").strip() if isinstance(details.get("customer_pic_name"), str) else ""

        append_system_message(
            self.db,
            entity_type=ENTITY_MASTER_QUOTATION,
            entity_id=str(mq.id),
            body_html=f"<p>{html.escape(mq.quotation_code or '')} created by {html.escape(actor_name)}.</p>",
        )
        bits = [f"Quotation {html.escape(mq.quotation_code or '')} created by {html.escape(actor_name)}"]
        if client_name:
            bits.append(f"for {html.escape(client_name)}")
        if pic_name:
            bits.append(f"(PIC: {html.escape(pic_name)})")
        append_system_message(
            self.db,
            entity_type=ENTITY_PROJECT,
            entity_id=project_id,
            body_html=f"<p>{' '.join(bits)}.</p>",
        )
        return self.get_master_by_id(str(mq.id))

    def duplicate_master_quotation(self, master_id: str, *, actor_user_id: str) -> CommercialMasterQuotation:
        mq_src = self.get_master_by_id(master_id)
        self._require_mq_actor_membership(mq_src, actor_user_id)
        wid = mq_src.current_working_revision_id
        if not wid:
            raise CommercialHierarchyError("Cannot duplicate a quotation without a working revision.")
        rev_src = self.get_revision(str(wid))
        t_src = mq_src.tender
        if not t_src:
            raise CommercialHierarchyError("Tender not loaded for master quotation.")
        proj = self.db.query(CommercialProject).filter(CommercialProject.id == t_src.project_id).first()
        if not proj:
            raise handle_not_found("Project", str(t_src.project_id))
        tender_target = self._ensure_project_workspace_tender(proj)
        year = datetime.utcnow().year
        qcode = self._next_qt_quotation_code(str(tender_target.id), year)
        stage = self._default_mq_stage()
        details = copy.deepcopy(dict(mq_src.commercial_details or {}))
        details.pop("pricing_intended_execution_state", None)
        suffix = " (Copy)"
        base_title = (mq_src.title or "").strip() or qcode
        max_bt = max(0, 255 - len(suffix))
        title = (base_title[:max_bt] + suffix).strip()
        snap = copy.deepcopy(dict(rev_src.pricing_snapshot or {}))
        mq = CommercialMasterQuotation(
            tender_id=tender_target.id,
            customer_id=mq_src.customer_id,
            quotation_code=qcode,
            title=title,
            owner_user_id=mq_src.owner_user_id,
            quotation_stage_id=stage.id,
            quoted_amount=None,
            quoted_currency=None,
            valid_until=mq_src.valid_until,
            payment_terms=mq_src.payment_terms,
            commercial_details=details,
            pricing_approval_status="not_required",
            pricing_approver_user_id=None,
            pricing_approval_action_at=None,
            pricing_approval_action_by_user_id=None,
            path_role="open",
            task_board={},
            final_selected_revision_id=None,
        )
        self.db.add(mq)
        self.db.flush()
        rev = CommercialQuotationRevision(
            master_quotation_id=mq.id,
            revision_number=1,
            pricing_snapshot=snap,
            revision_notes=None,
        )
        self.db.add(rev)
        self.db.flush()
        mq.current_working_revision_id = rev.id
        self.db.flush()
        sync_master_from_working_revision(self.db, mq)
        self.db.flush()
        self.db.refresh(mq)
        return self.get_master_by_id(str(mq.id))

    def replace_working_revision_from_quotation_package_template(
        self,
        master_id: str,
        *,
        quotation_package_template_id: str,
        actor_user_id: str,
    ) -> CommercialQuotationRevision:
        mq = self.get_master_by_id(master_id)
        self._require_mq_actor_membership(mq, actor_user_id)
        self._require_working_revision_editable(mq)
        pkg = get_quotation_package_template_by_id(self.db, quotation_package_template_id)
        if not pkg:
            raise CommercialHierarchyError("Quotation package template not found.")
        wid = mq.current_working_revision_id
        if not wid:
            raise CommercialHierarchyError("No working revision.")
        rev = self.get_revision(str(wid))
        rev.pricing_snapshot = build_pricing_snapshot_from_package_template(pkg)
        merged = copy.deepcopy(dict(mq.commercial_details or {}))
        merged["quotation_package_template_id"] = str(pkg.get("id") or "")
        merged["quotation_package_template_name"] = str(pkg.get("name") or "")
        mq.commercial_details = merged
        self.db.flush()
        sync_master_from_working_revision(self.db, mq)
        self.db.flush()
        self.db.refresh(rev)
        return rev

    def update_master_quotation(self, master_id: str, patch: Dict[str, Any], *, actor_user_id: str) -> CommercialMasterQuotation:
        mq = self.get_master_by_id(master_id)
        self._require_mq_actor_membership(mq, actor_user_id)
        if "title" in patch:
            t = str(patch["title"] or "").strip()
            if not t:
                raise CommercialHierarchyError("Title cannot be empty.")
            mq.title = t
        if "valid_until" in patch:
            mq.valid_until = patch["valid_until"]
        if "payment_terms" in patch:
            pt = patch["payment_terms"]
            mq.payment_terms = str(pt).strip() if pt is not None and str(pt).strip() else None
        if "owner_user_id" in patch:
            ou = patch["owner_user_id"]
            mq.owner_user_id = str(ou).strip() if ou is not None and str(ou).strip() else None
        if "quoted_amount" in patch:
            mq.quoted_amount = patch["quoted_amount"]
        if "quoted_currency" in patch:
            qc = patch["quoted_currency"]
            mq.quoted_currency = str(qc).strip()[:3] if qc is not None and str(qc).strip() else None
        details = copy.deepcopy(dict(mq.commercial_details or {})) if isinstance(mq.commercial_details, dict) else {}
        if "description" in patch:
            d = patch["description"]
            if d is not None and str(d).strip():
                details["description"] = str(d).strip()
            else:
                details.pop("description", None)
        if "remark" in patch:
            r = patch["remark"]
            if r is not None and str(r).strip():
                details["remark"] = str(r).strip()
            else:
                details.pop("remark", None)
        mq.commercial_details = details
        if "task_board" in patch:
            tb = patch.get("task_board")
            mq.task_board = dict(tb) if isinstance(tb, dict) else {}
        self.db.flush()
        self.db.refresh(mq)
        return mq

    def preview_master_task_board_schedule(
        self,
        master_id: str,
        *,
        task_board: Dict[str, Any],
        baseline_start_date: Optional[str] = None,
        changed_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        mq = self.get_master_by_id(master_id)
        scheduler = TaskDependencyScheduleService(self.db)
        try:
            effective_baseline = baseline_start_date
            if not effective_baseline:
                proj_start = (
                    mq.tender.project.start_date.isoformat()
                    if mq.tender and mq.tender.project and mq.tender.project.start_date
                    else None
                )
                effective_baseline = proj_start
            return scheduler.recalculate(
                task_board=task_board,
                baseline_start_date=scheduler._parse_date(effective_baseline),
                changed_task_id=changed_task_id,
            )
        except TaskDependencyScheduleError as e:
            raise CommercialHierarchyError(e.message)

    def apply_master_task_board_schedule(
        self,
        master_id: str,
        *,
        actor_user_id: str,
        task_board: Dict[str, Any],
        baseline_start_date: Optional[str] = None,
        changed_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        mq = self.get_master_by_id(master_id)
        self._require_mq_actor_membership(mq, actor_user_id)
        out = self.preview_master_task_board_schedule(
            master_id,
            task_board=task_board,
            baseline_start_date=baseline_start_date,
            changed_task_id=changed_task_id,
        )
        mq.task_board = dict(out.get("task_board") or {})
        self.db.flush()
        return out

    def advance_master_quotation_stage(
        self,
        master_id: str,
        *,
        actor_user_id: str,
        confirm_tolerance_breach: bool = False,
    ) -> CommercialMasterQuotation:
        mq = self.get_master_by_id(master_id)
        t = mq.tender
        if not t:
            raise CommercialHierarchyError("Tender not loaded for master quotation.")
        if not user_may_access_project_quotations(self.db, str(t.project_id), actor_user_id):
            raise CommercialHierarchyError("Only project owners may change quotation stage.")
        if (getattr(mq, "pricing_approval_status", None) or "").strip().lower() == "pending":
            raise CommercialHierarchyError("Cannot advance while pricing approval is pending.")
        stages = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order.asc(), WorkflowStage.code.asc())
            .all()
        )
        if not stages:
            raise CommercialHierarchyError("No next quotation stage configured.")
        cur_id = str(mq.quotation_stage_id)
        idx = next((i for i, s in enumerate(stages) if str(s.id) == cur_id), -1)
        if idx < 0:
            raise CommercialHierarchyError("Current quotation stage is not in the active stage list.")
        cur_st = stages[idx]
        if cur_st.is_terminal:
            raise CommercialHierarchyError("No next quotation stage configured.")
        if idx >= len(stages) - 1:
            raise CommercialHierarchyError("No next quotation stage configured.")
        nxt = stages[idx + 1]
        try:
            apply_master_quotation_stage_change(
                self.db,
                mq,
                nxt.code,
                actor_user_id,
                confirm_tolerance_breach=confirm_tolerance_breach,
            )
        except ToleranceAdvanceConfirmationRequired:
            raise
        except ValueError as e:
            raise CommercialHierarchyError(str(e)) from e
        self.db.flush()
        self.db.refresh(mq)
        return self.get_master_by_id(master_id)

    def retreat_master_quotation_stage(self, master_id: str, *, actor_user_id: str) -> CommercialMasterQuotation:
        mq = self.get_master_by_id(master_id)
        t = mq.tender
        if not t:
            raise CommercialHierarchyError("Tender not loaded for master quotation.")
        if not user_may_access_project_quotations(self.db, str(t.project_id), actor_user_id):
            raise CommercialHierarchyError("Only project owners may change quotation stage.")
        if (getattr(mq, "pricing_approval_status", None) or "").strip().lower() == "pending":
            raise CommercialHierarchyError("Cannot retreat while pricing approval is pending.")
        stages = (
            self.db.query(WorkflowStage)
            .filter(
                WorkflowStage.domain == WORKFLOW_DOMAIN_QUOTATION,
                WorkflowStage.is_active.is_(True),
            )
            .order_by(WorkflowStage.sort_order.asc(), WorkflowStage.code.asc())
            .all()
        )
        if not stages:
            raise CommercialHierarchyError("No quotation stage list configured.")
        cur_id = str(mq.quotation_stage_id)
        idx = next((i for i, s in enumerate(stages) if str(s.id) == cur_id), -1)
        if idx < 0:
            raise CommercialHierarchyError("Current quotation stage is not in the active stage list.")
        if idx <= 0:
            raise CommercialHierarchyError("Already at the first quotation stage.")
        prev = stages[idx - 1]
        try:
            apply_master_quotation_stage_change(self.db, mq, prev.code, actor_user_id)
        except ValueError as e:
            raise CommercialHierarchyError(str(e)) from e
        self.db.flush()
        self.db.refresh(mq)
        return self.get_master_by_id(master_id)
