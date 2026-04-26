"""Commercial activity plan: templates, task trees on master quotations, list-query search."""
from __future__ import annotations

from datetime import datetime, timedelta
from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, asc, exists, func, or_
from sqlalchemy.orm import Session, joinedload

from app.modules.commercial_core.models import CommercialMasterQuotation
from app.models.order import Customer
from app.modules.commercial_core.models import CommercialLead, CommercialProject, CommercialTender
from app.modules.commercial_activity.models import (
    CommercialActivityPlanApplication,
    CommercialActivityTaskStatus,
    CommercialActivityTemplate,
    CommercialActivityTemplateNode,
    CommercialProjectTaskCategory,
    CommercialQuotationActivityTask,
)
from app.models.user import User


class CommercialActivityPlanError(Exception):
    """Domain error for activity plan operations."""

    def __init__(self, message: str, code: str = "activity_plan_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _uuid_str() -> str:
    import uuid

    return str(uuid.uuid4())


class CommercialActivityPlanService:
    def __init__(self, db: Session):
        self.db = db

    # --- statuses ---

    def list_statuses(self, *, active_only: bool = False) -> List[CommercialActivityTaskStatus]:
        q = self.db.query(CommercialActivityTaskStatus).order_by(CommercialActivityTaskStatus.sort_order.asc())
        if active_only:
            q = q.filter(CommercialActivityTaskStatus.is_active.is_(True))
        return q.all()

    def get_status(self, status_id: str) -> Optional[CommercialActivityTaskStatus]:
        return self.db.query(CommercialActivityTaskStatus).filter(CommercialActivityTaskStatus.id == status_id).first()

    def get_default_status_id(self) -> str:
        row = (
            self.db.query(CommercialActivityTaskStatus)
            .filter(
                CommercialActivityTaskStatus.is_default.is_(True),
                CommercialActivityTaskStatus.is_active.is_(True),
            )
            .order_by(CommercialActivityTaskStatus.sort_order.asc())
            .first()
        )
        if row:
            return str(row.id)
        row = (
            self.db.query(CommercialActivityTaskStatus)
            .filter(CommercialActivityTaskStatus.is_active.is_(True))
            .order_by(CommercialActivityTaskStatus.sort_order.asc())
            .first()
        )
        if not row:
            raise CommercialActivityPlanError("No activity task statuses configured.")
        return str(row.id)

    def create_status(self, *, code: str, label: str, sort_order: int = 0, is_default: bool = False, is_terminal: bool = False, is_active: bool = True, color_hex: Optional[str] = None) -> CommercialActivityTaskStatus:
        if self.db.query(CommercialActivityTaskStatus).filter(CommercialActivityTaskStatus.code == code).first():
            raise CommercialActivityPlanError(f"Status code already exists: {code}")
        if is_default:
            self.db.query(CommercialActivityTaskStatus).update({CommercialActivityTaskStatus.is_default: False})
        row = CommercialActivityTaskStatus(
            id=_uuid_str(),
            code=code.strip(),
            label=label.strip(),
            sort_order=sort_order,
            is_default=is_default,
            is_terminal=is_terminal,
            is_active=is_active,
            color_hex=(color_hex or "").strip() or None,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_status(self, status_id: str, **fields: Any) -> CommercialActivityTaskStatus:
        row = self.get_status(status_id)
        if not row:
            raise CommercialActivityPlanError("Status not found.")
        if "code" in fields and fields["code"] is not None:
            other = (
                self.db.query(CommercialActivityTaskStatus)
                .filter(
                    CommercialActivityTaskStatus.code == str(fields["code"]).strip(),
                    CommercialActivityTaskStatus.id != status_id,
                )
                .first()
            )
            if other:
                raise CommercialActivityPlanError("Status code already in use.")
            row.code = str(fields["code"]).strip()
        for k in ("label", "sort_order", "is_terminal", "is_active", "color_hex"):
            if k in fields and fields[k] is not None:
                setattr(row, k, fields[k])
        if fields.get("is_default") is True:
            self.db.query(CommercialActivityTaskStatus).filter(CommercialActivityTaskStatus.id != status_id).update(
                {CommercialActivityTaskStatus.is_default: False}
            )
            row.is_default = True
        elif fields.get("is_default") is False:
            row.is_default = False
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_status(self, status_id: str) -> None:
        row = self.get_status(status_id)
        if not row:
            raise CommercialActivityPlanError("Status not found.")
        if self.db.query(CommercialQuotationActivityTask).filter(CommercialQuotationActivityTask.status_id == status_id).first():
            row.is_active = False
            self.db.commit()
            return
        self.db.delete(row)
        self.db.commit()

    # --- templates ---

    def list_templates(self, *, active_only: bool = False, template_scope: Optional[str] = None) -> List[CommercialActivityTemplate]:
        q = self.db.query(CommercialActivityTemplate).order_by(CommercialActivityTemplate.name.asc())
        if active_only:
            q = q.filter(CommercialActivityTemplate.is_active.is_(True))
        if template_scope in ("project", "quotation"):
            q = q.filter(CommercialActivityTemplate.template_scope == template_scope)
        return q.all()

    def get_template(self, template_id: str) -> Optional[CommercialActivityTemplate]:
        return self.db.query(CommercialActivityTemplate).filter(CommercialActivityTemplate.id == template_id).first()

    def create_template(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        is_active: bool = True,
        template_scope: str = "project",
        created_by_user_id: Optional[str] = None,
    ) -> CommercialActivityTemplate:
        scope = (template_scope or "project").strip().lower()
        if scope not in ("project", "quotation"):
            scope = "project"
        row = CommercialActivityTemplate(
            id=_uuid_str(),
            name=name.strip(),
            description=(description or "").strip() or None,
            is_active=is_active,
            version_number=1,
            template_scope=scope,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_template(
        self,
        template_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        template_scope: Optional[str] = None,
    ) -> CommercialActivityTemplate:
        row = self.db.query(CommercialActivityTemplate).filter(CommercialActivityTemplate.id == template_id).first()
        if not row:
            raise CommercialActivityPlanError("Template not found.")
        if name is not None:
            row.name = name.strip()
        if description is not None:
            row.description = description.strip() or None
        if is_active is not None:
            row.is_active = is_active
        if template_scope is not None:
            ts = str(template_scope).strip().lower()
            if ts in ("project", "quotation"):
                row.template_scope = ts
        row.version_number = int(row.version_number or 1) + 1
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_template(self, template_id: str) -> None:
        row = self.db.query(CommercialActivityTemplate).filter(CommercialActivityTemplate.id == template_id).first()
        if not row:
            raise CommercialActivityPlanError("Template not found.")
        self.db.delete(row)
        self.db.commit()

    # --- project task categories (template node grouping) ---

    def _assert_task_category(self, category_code: Optional[str]) -> None:
        if not category_code or not str(category_code).strip():
            return
        code = str(category_code).strip()
        row = (
            self.db.query(CommercialProjectTaskCategory)
            .filter(CommercialProjectTaskCategory.code == code, CommercialProjectTaskCategory.is_active.is_(True))
            .first()
        )
        if not row:
            raise CommercialActivityPlanError("Task category not found or inactive.")

    def list_task_categories(self, *, active_only: bool = True) -> List[CommercialProjectTaskCategory]:
        q = self.db.query(CommercialProjectTaskCategory).order_by(CommercialProjectTaskCategory.sort_order.asc())
        if active_only:
            q = q.filter(CommercialProjectTaskCategory.is_active.is_(True))
        return q.all()

    def create_task_category(self, *, code: str, label: str, sort_order: int = 0) -> CommercialProjectTaskCategory:
        c = str(code).strip().lower().replace(" ", "_")
        if not c:
            raise CommercialActivityPlanError("Category code is required.")
        if self.db.query(CommercialProjectTaskCategory).filter(CommercialProjectTaskCategory.code == c).first():
            raise CommercialActivityPlanError("Task category code already exists.")
        row = CommercialProjectTaskCategory(
            code=c,
            label=str(label).strip(),
            sort_order=int(sort_order),
            is_active=True,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_task_category(
        self,
        code: str,
        *,
        label: Optional[str] = None,
        sort_order: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> CommercialProjectTaskCategory:
        row = self.db.query(CommercialProjectTaskCategory).filter(CommercialProjectTaskCategory.code == code).first()
        if not row:
            raise CommercialActivityPlanError("Task category not found.")
        if label is not None:
            row.label = str(label).strip()
        if sort_order is not None:
            row.sort_order = int(sort_order)
        if is_active is not None:
            row.is_active = bool(is_active)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_task_category(self, code: str) -> None:
        row = self.db.query(CommercialProjectTaskCategory).filter(CommercialProjectTaskCategory.code == code).first()
        if not row:
            raise CommercialActivityPlanError("Task category not found.")
        self.db.delete(row)
        self.db.commit()

    def create_template_node(self, template_id: str, body: Dict[str, Any]) -> CommercialActivityTemplateNode:
        self._get_template_or_raise(template_id)
        parent_id = body.get("parent_id")
        if parent_id:
            p = (
                self.db.query(CommercialActivityTemplateNode)
                .filter(
                    CommercialActivityTemplateNode.id == parent_id,
                    CommercialActivityTemplateNode.template_id == template_id,
                )
                .first()
            )
            if not p:
                raise CommercialActivityPlanError("Parent template node not found.")
        cat = body.get("category_code")
        if cat is not None and str(cat).strip():
            self._assert_task_category(str(cat))
        elif cat is not None:
            cat = None
        dep_node_ids = self._normalize_dependency_node_ids(body.get("dependency_node_ids"))
        self._assert_template_dependencies(template_id, dep_node_ids, node_id=None)
        row = CommercialActivityTemplateNode(
            id=_uuid_str(),
            template_id=template_id,
            parent_id=parent_id,
            sort_order=int(body.get("sort_order") or 0),
            title=str(body["title"]).strip(),
            category_code=(str(cat).strip() if cat else None),
            is_service_task=bool(body.get("is_service_task") or False),
            description=(body.get("description") or None),
            default_status_id=body.get("default_status_id"),
            default_offset_days=body.get("default_offset_days"),
            lead_time_days=max(1, int(body.get("lead_time_days") or 1)),
            dependency_node_ids=dep_node_ids,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_template_node(self, node_id: str, body: Dict[str, Any]) -> CommercialActivityTemplateNode:
        row = self.db.query(CommercialActivityTemplateNode).filter(CommercialActivityTemplateNode.id == node_id).first()
        if not row:
            raise CommercialActivityPlanError("Template node not found.")
        if "parent_id" in body:
            new_parent = body.get("parent_id")
            if new_parent == node_id:
                raise CommercialActivityPlanError("Node cannot be its own parent.")
            if new_parent:
                self._assert_template_node_no_cycle(str(row.template_id), node_id, str(new_parent))
                p = (
                    self.db.query(CommercialActivityTemplateNode)
                    .filter(
                        CommercialActivityTemplateNode.id == new_parent,
                        CommercialActivityTemplateNode.template_id == row.template_id,
                    )
                    .first()
                )
                if not p:
                    raise CommercialActivityPlanError("Parent template node not found.")
            row.parent_id = new_parent
        if "category_code" in body:
            cc = body.get("category_code")
            if cc is None or (isinstance(cc, str) and not cc.strip()):
                row.category_code = None
            else:
                self._assert_task_category(str(cc))
                row.category_code = str(cc).strip()
        if "is_service_task" in body and body["is_service_task"] is not None:
            row.is_service_task = bool(body["is_service_task"])
        for k in ("sort_order", "description", "default_status_id", "default_offset_days"):
            if k in body and body[k] is not None:
                setattr(row, k, body[k])
        if "lead_time_days" in body and body["lead_time_days"] is not None:
            row.lead_time_days = max(1, int(body["lead_time_days"]))
        if "dependency_node_ids" in body and body["dependency_node_ids"] is not None:
            dep_node_ids = self._normalize_dependency_node_ids(body.get("dependency_node_ids"))
            self._assert_template_dependencies(str(row.template_id), dep_node_ids, node_id=node_id)
            row.dependency_node_ids = dep_node_ids
        if "title" in body and body["title"] is not None:
            row.title = str(body["title"]).strip()
        tpl = self._get_template_or_raise(str(row.template_id))
        tpl.version_number = int(tpl.version_number or 1) + 1
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_template_node(self, node_id: str) -> None:
        row = self.db.query(CommercialActivityTemplateNode).filter(CommercialActivityTemplateNode.id == node_id).first()
        if not row:
            raise CommercialActivityPlanError("Template node not found.")
        self.db.delete(row)
        tpl = self._get_template_or_raise(str(row.template_id))
        tpl.version_number = int(tpl.version_number or 1) + 1
        self.db.commit()

    def _get_template_or_raise(self, template_id: str) -> CommercialActivityTemplate:
        t = self.db.query(CommercialActivityTemplate).filter(CommercialActivityTemplate.id == template_id).first()
        if not t:
            raise CommercialActivityPlanError("Template not found.")
        return t

    def _assert_template_node_no_cycle(self, template_id: str, node_id: str, new_parent_id: str) -> None:
        cur: Optional[str] = new_parent_id
        while cur:
            if cur == node_id:
                raise CommercialActivityPlanError("Template node cycle detected.")
            p = (
                self.db.query(CommercialActivityTemplateNode)
                .filter(
                    CommercialActivityTemplateNode.id == cur,
                    CommercialActivityTemplateNode.template_id == template_id,
                )
                .first()
            )
            if not p:
                break
            cur = str(p.parent_id) if p.parent_id else None

    def _normalize_dependency_node_ids(self, raw: Any) -> List[str]:
        if not isinstance(raw, list):
            return []
        out: List[str] = []
        seen = set()
        for item in raw:
            sid = str(item or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            out.append(sid)
        return out

    def _assert_template_dependencies(self, template_id: str, dependency_node_ids: List[str], *, node_id: Optional[str]) -> None:
        dep_set = set(dependency_node_ids)
        if node_id and node_id in dep_set:
            raise CommercialActivityPlanError("Template task cannot depend on itself.")
        for dep_id in dep_set:
            exists_dep = (
                self.db.query(CommercialActivityTemplateNode)
                .filter(
                    CommercialActivityTemplateNode.id == dep_id,
                    CommercialActivityTemplateNode.template_id == template_id,
                )
                .first()
            )
            if not exists_dep:
                raise CommercialActivityPlanError(f"Dependency task not found: {dep_id}")
        if not node_id:
            return
        nodes = (
            self.db.query(CommercialActivityTemplateNode)
            .filter(CommercialActivityTemplateNode.template_id == template_id)
            .all()
        )
        by_id: Dict[str, List[str]] = {}
        for n in nodes:
            deps = self._normalize_dependency_node_ids(getattr(n, "dependency_node_ids", []) or [])
            by_id[str(n.id)] = deps
        by_id[node_id] = dependency_node_ids
        indeg: Dict[str, int] = {nid: 0 for nid in by_id}
        succ: Dict[str, List[str]] = {nid: [] for nid in by_id}
        for nid, deps in by_id.items():
            for dep in deps:
                if dep not in by_id:
                    continue
                indeg[nid] += 1
                succ.setdefault(dep, []).append(nid)
        q = deque([nid for nid, deg in indeg.items() if deg == 0])
        visited = 0
        while q:
            cur = q.popleft()
            visited += 1
            for nxt in succ.get(cur, []):
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    q.append(nxt)
        if visited != len(indeg):
            raise CommercialActivityPlanError("Template dependency cycle detected.")

    def build_template_node_tree(self, template_id: str) -> List[Dict[str, Any]]:
        nodes = (
            self.db.query(CommercialActivityTemplateNode)
            .filter(CommercialActivityTemplateNode.template_id == template_id)
            .order_by(CommercialActivityTemplateNode.sort_order.asc())
            .all()
        )
        by_parent: Dict[Optional[str], List[CommercialActivityTemplateNode]] = {}
        for n in nodes:
            pid = str(n.parent_id) if n.parent_id else None
            by_parent.setdefault(pid, []).append(n)

        def walk(parent: Optional[str]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for n in by_parent.get(parent, []):
                d = {
                    "id": str(n.id),
                    "template_id": str(n.template_id),
                    "parent_id": str(n.parent_id) if n.parent_id else None,
                    "sort_order": n.sort_order,
                    "title": n.title,
                    "category_code": n.category_code,
                    "is_service_task": bool(getattr(n, "is_service_task", False)),
                    "description": n.description,
                    "default_status_id": str(n.default_status_id) if n.default_status_id else None,
                    "default_offset_days": n.default_offset_days,
                    "lead_time_days": int(getattr(n, "lead_time_days", 1) or 1),
                    "dependency_node_ids": self._normalize_dependency_node_ids(
                        getattr(n, "dependency_node_ids", []) or []
                    ),
                    "children": walk(str(n.id)),
                }
                out.append(d)
            return out

        return walk(None)

    # --- master quotation tasks ---

    def _get_master_or_raise(self, master_quotation_id: str) -> CommercialMasterQuotation:
        mq = self.db.query(CommercialMasterQuotation).filter(CommercialMasterQuotation.id == master_quotation_id).first()
        if not mq:
            raise CommercialActivityPlanError("Master quotation not found.")
        return mq

    def assert_user_exists(self, user_id: Optional[str]) -> None:
        if not user_id:
            return
        if not self.db.query(User).filter(User.id == user_id, User.is_trashed.is_(False)).first():
            raise CommercialActivityPlanError("Assignee user not found.")

    def apply_template(
        self,
        master_quotation_id: str,
        template_id: str,
        *,
        anchor_at: Optional[datetime] = None,
        applied_by_user_id: Optional[str] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        mq = self._get_master_or_raise(master_quotation_id)
        tpl = self.db.query(CommercialActivityTemplate).filter(CommercialActivityTemplate.id == template_id).first()
        if not tpl or not tpl.is_active:
            raise CommercialActivityPlanError("Template not found or inactive.")
        tpl_scope = getattr(tpl, "template_scope", None) or "project"
        if tpl_scope != "quotation":
            raise CommercialActivityPlanError("Only quotation-scoped task templates can be applied to a master quotation.")
        nodes = (
            self.db.query(CommercialActivityTemplateNode)
            .filter(CommercialActivityTemplateNode.template_id == template_id)
            .order_by(CommercialActivityTemplateNode.sort_order.asc())
            .all()
        )
        anchor = anchor_at or mq.created_at or datetime.utcnow()
        id_map: Dict[str, str] = {}

        def default_status_for(node: CommercialActivityTemplateNode) -> str:
            if node.default_status_id:
                st = self.get_status(str(node.default_status_id))
                if st and st.is_active:
                    return str(st.id)
            return self.get_default_status_id()

        children_by_parent: Dict[Optional[str], List[CommercialActivityTemplateNode]] = {}
        for n in nodes:
            pid = str(n.parent_id) if n.parent_id else None
            children_by_parent.setdefault(pid, []).append(n)

        def clone_subtree(node: CommercialActivityTemplateNode, parent_task_id: Optional[str]) -> str:
            due_at = None
            if node.default_offset_days is not None:
                due_at = anchor + timedelta(days=int(node.default_offset_days))
            task = CommercialQuotationActivityTask(
                id=_uuid_str(),
                master_quotation_id=master_quotation_id,
                parent_id=parent_task_id,
                source_template_node_id=str(node.id),
                sort_order=node.sort_order,
                title=node.title,
                status_id=default_status_for(node),
                assignee_user_id=None,
                due_at=due_at,
                remind_at=None,
                is_tender_level=False,
            )
            self.db.add(task)
            self.db.flush()
            id_map[str(node.id)] = str(task.id)
            for ch in sorted(children_by_parent.get(str(node.id), []), key=lambda x: x.sort_order):
                clone_subtree(ch, str(task.id))
            return str(task.id)

        for root in sorted(children_by_parent.get(None, []), key=lambda x: x.sort_order):
            clone_subtree(root, None)

        app = CommercialActivityPlanApplication(
            id=_uuid_str(),
            master_quotation_id=master_quotation_id,
            template_id=template_id,
            template_version=int(tpl.version_number or 1),
            applied_by_user_id=applied_by_user_id,
        )
        self.db.add(app)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return {"applied": True, "tasks_created": len(id_map), "application_id": str(app.id)}

    def list_tasks_flat(self, master_quotation_id: str, *, include_deleted: bool = False) -> List[CommercialQuotationActivityTask]:
        self._get_master_or_raise(master_quotation_id)
        q = (
            self.db.query(CommercialQuotationActivityTask)
            .options(joinedload(CommercialQuotationActivityTask.master_quotation), joinedload(CommercialQuotationActivityTask.status))
            .filter(CommercialQuotationActivityTask.master_quotation_id == master_quotation_id)
        )
        if not include_deleted:
            q = q.filter(CommercialQuotationActivityTask.deleted_at.is_(None))
        return q.order_by(CommercialQuotationActivityTask.sort_order.asc()).all()

    def build_task_tree(self, master_quotation_id: str) -> List[Dict[str, Any]]:
        rows = self.list_tasks_flat(master_quotation_id)
        by_parent: Dict[Optional[str], List[CommercialQuotationActivityTask]] = {}
        for t in rows:
            pid = str(t.parent_id) if t.parent_id else None
            by_parent.setdefault(pid, []).append(t)

        def enrich(t: CommercialQuotationActivityTask) -> Dict[str, Any]:
            mq = t.master_quotation
            st = t.status
            return {
                "id": str(t.id),
                "master_quotation_id": str(t.master_quotation_id),
                "parent_id": str(t.parent_id) if t.parent_id else None,
                "source_template_node_id": str(t.source_template_node_id) if t.source_template_node_id else None,
                "sort_order": t.sort_order,
                "title": t.title,
                "status_id": str(t.status_id),
                "assignee_user_id": t.assignee_user_id,
                "due_at": t.due_at,
                "remind_at": t.remind_at,
                "last_reminder_sent_at": t.last_reminder_sent_at,
                "is_tender_level": bool(t.is_tender_level),
                "deleted_at": t.deleted_at,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "quotation_code": mq.quotation_code if mq else None,
                "tender_code": mq.tender.tender_code if mq and mq.tender else None,
                "status_code": st.code if st else None,
                "status_label": st.label if st else None,
                "children": [],
            }

        def walk(parent: Optional[str]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for t in sorted(by_parent.get(parent, []), key=lambda x: (x.sort_order, x.id)):
                d = enrich(t)
                d["children"] = walk(str(t.id))
                out.append(d)
            return out

        return walk(None)

    def create_task(self, master_quotation_id: str, body: Dict[str, Any]) -> CommercialQuotationActivityTask:
        self._get_master_or_raise(master_quotation_id)
        parent_id = body.get("parent_id")
        if parent_id:
            p = (
                self.db.query(CommercialQuotationActivityTask)
                .filter(
                    CommercialQuotationActivityTask.id == parent_id,
                    CommercialQuotationActivityTask.master_quotation_id == master_quotation_id,
                    CommercialQuotationActivityTask.deleted_at.is_(None),
                )
                .first()
            )
            if not p:
                raise CommercialActivityPlanError("Parent task not found.")
        assignee = body.get("assignee_user_id")
        self.assert_user_exists(assignee)
        status_id = body.get("status_id") or self.get_default_status_id()
        st = self.get_status(status_id)
        if not st or not st.is_active:
            raise CommercialActivityPlanError("Invalid status.")
        sort_order = body.get("sort_order")
        if sort_order is None:
            q = self.db.query(func.max(CommercialQuotationActivityTask.sort_order)).filter(
                CommercialQuotationActivityTask.master_quotation_id == master_quotation_id,
                CommercialQuotationActivityTask.parent_id == parent_id,
                CommercialQuotationActivityTask.deleted_at.is_(None),
            )
            mx = q.scalar()
            sort_order = int(mx or -1) + 1
        row = CommercialQuotationActivityTask(
            id=_uuid_str(),
            master_quotation_id=master_quotation_id,
            parent_id=parent_id,
            sort_order=int(sort_order),
            title=str(body["title"]).strip(),
            status_id=status_id,
            assignee_user_id=assignee,
            due_at=body.get("due_at"),
            remind_at=body.get("remind_at"),
            start_date=body.get("start_date"),
            end_date=body.get("end_date"),
            is_tender_level=bool(body.get("is_tender_level") or False),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_task(self, task_id: str, body: Dict[str, Any]) -> CommercialQuotationActivityTask:
        row = (
            self.db.query(CommercialQuotationActivityTask)
            .filter(CommercialQuotationActivityTask.id == task_id, CommercialQuotationActivityTask.deleted_at.is_(None))
            .first()
        )
        if not row:
            raise CommercialActivityPlanError("Task not found.")
        if "parent_id" in body:
            new_parent = body.get("parent_id")
            if new_parent == task_id:
                raise CommercialActivityPlanError("Task cannot be its own parent.")
            if new_parent:
                self._assert_task_no_cycle(task_id, str(new_parent), str(row.master_quotation_id))
                p = (
                    self.db.query(CommercialQuotationActivityTask)
                    .filter(
                        CommercialQuotationActivityTask.id == new_parent,
                        CommercialQuotationActivityTask.master_quotation_id == row.master_quotation_id,
                        CommercialQuotationActivityTask.deleted_at.is_(None),
                    )
                    .first()
                )
                if not p:
                    raise CommercialActivityPlanError("Parent task not found.")
            row.parent_id = new_parent
        if "assignee_user_id" in body:
            self.assert_user_exists(body.get("assignee_user_id"))
            row.assignee_user_id = body.get("assignee_user_id")
        if "status_id" in body and body["status_id"] is not None:
            st = self.get_status(str(body["status_id"]))
            if not st or not st.is_active:
                raise CommercialActivityPlanError("Invalid status.")
            row.status_id = str(body["status_id"])
        for k in ("sort_order", "title", "due_at", "remind_at", "start_date", "end_date", "is_tender_level"):
            if k in body and body[k] is not None:
                setattr(row, k, body[k])
        if "title" in body and body["title"] is not None:
            row.title = str(body["title"]).strip()
        self.db.commit()
        self.db.refresh(row)
        return row

    def _assert_task_no_cycle(self, task_id: str, new_parent_id: str, master_quotation_id: str) -> None:
        cur: Optional[str] = new_parent_id
        while cur:
            if cur == task_id:
                raise CommercialActivityPlanError("Task cycle detected.")
            p = (
                self.db.query(CommercialQuotationActivityTask)
                .filter(
                    CommercialQuotationActivityTask.id == cur,
                    CommercialQuotationActivityTask.master_quotation_id == master_quotation_id,
                )
                .first()
            )
            if not p:
                break
            cur = str(p.parent_id) if p.parent_id else None

    def soft_delete_task(self, task_id: str, *, cascade_children: bool = True) -> None:
        row = self.db.query(CommercialQuotationActivityTask).filter(CommercialQuotationActivityTask.id == task_id).first()
        if not row or row.deleted_at:
            raise CommercialActivityPlanError("Task not found.")
        now = datetime.utcnow()
        row.deleted_at = now
        if cascade_children:
            ids = [task_id]
            i = 0
            while i < len(ids):
                cur = ids[i]
                for ch in (
                    self.db.query(CommercialQuotationActivityTask)
                    .filter(
                        CommercialQuotationActivityTask.parent_id == cur,
                        CommercialQuotationActivityTask.deleted_at.is_(None),
                    )
                    .all()
                ):
                    ids.append(str(ch.id))
                    ch.deleted_at = now
                i += 1
        self.db.commit()

    def reorder_tasks(self, master_quotation_id: str, parent_id: Optional[str], items: Sequence[Tuple[str, int]]) -> None:
        self._get_master_or_raise(master_quotation_id)
        for tid, so in items:
            row = (
                self.db.query(CommercialQuotationActivityTask)
                .filter(
                    CommercialQuotationActivityTask.id == tid,
                    CommercialQuotationActivityTask.master_quotation_id == master_quotation_id,
                    CommercialQuotationActivityTask.deleted_at.is_(None),
                )
                .first()
            )
            if not row:
                raise CommercialActivityPlanError(f"Task not found: {tid}")
            exp_parent = str(parent_id) if parent_id else None
            cur_parent = str(row.parent_id) if row.parent_id else None
            if cur_parent != exp_parent:
                raise CommercialActivityPlanError("Task parent does not match reorder scope.")
            row.sort_order = int(so)
        self.db.commit()

    # --- list-query ---

    def list_tasks_search(
        self,
        *,
        page: int,
        limit: int,
        quick_search: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "desc",
        advanced_filter_clause: Any = None,
        assignee_user_id: Optional[str] = None,
        master_quotation_id: Optional[str] = None,
        overdue_only: bool = False,
        upcoming_within_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        T = CommercialQuotationActivityTask
        q = self.db.query(T).filter(T.deleted_at.is_(None))
        if quick_search and (qs := quick_search.strip()):
            like = f"%{qs}%"
            mq_match = exists().where(
                and_(
                    CommercialMasterQuotation.id == T.master_quotation_id,
                    or_(
                        CommercialMasterQuotation.quotation_code.ilike(like),
                        CommercialMasterQuotation.title.ilike(like),
                    ),
                )
            )
            tender_match = exists().where(
                and_(
                    CommercialMasterQuotation.id == T.master_quotation_id,
                    CommercialTender.id == CommercialMasterQuotation.tender_id,
                    or_(
                        CommercialTender.tender_code.ilike(like),
                        CommercialTender.title.ilike(like),
                    ),
                )
            )
            customer_match = exists().where(
                and_(
                    CommercialMasterQuotation.id == T.master_quotation_id,
                    CommercialTender.id == CommercialMasterQuotation.tender_id,
                    CommercialProject.id == CommercialTender.project_id,
                    CommercialLead.id == CommercialProject.lead_id,
                    Customer.id == CommercialLead.customer_id,
                    Customer.customer_name.ilike(like),
                )
            )
            q = q.filter(or_(T.title.ilike(like), mq_match, tender_match, customer_match))
        if assignee_user_id:
            q = q.filter(T.assignee_user_id == assignee_user_id)
        if master_quotation_id:
            q = q.filter(T.master_quotation_id == master_quotation_id)
        non_terminal = exists().where(
            and_(
                CommercialActivityTaskStatus.id == T.status_id,
                CommercialActivityTaskStatus.is_terminal.is_(False),
            )
        )
        if overdue_only:
            now = datetime.utcnow()
            q = q.filter(T.due_at.isnot(None), T.due_at < now, non_terminal)
        elif upcoming_within_days is not None and upcoming_within_days >= 0:
            start = datetime.utcnow()
            end = start + timedelta(days=int(upcoming_within_days))
            q = q.filter(T.due_at.isnot(None), T.due_at >= start, T.due_at <= end, non_terminal)
        if advanced_filter_clause is not None:
            q = q.filter(advanced_filter_clause)

        total = int(q.count() or 0)

        sort_col = getattr(T, sort_field, None) if hasattr(T, sort_field) else T.created_at
        if sort_col is None:
            sort_col = T.created_at
        order_expr = asc(sort_col) if (sort_dir or "asc").lower() == "asc" else sort_col.desc()

        offset = (page - 1) * limit
        rows = (
            q.options(
                joinedload(T.master_quotation).joinedload(CommercialMasterQuotation.tender),
                joinedload(T.status),
            )
            .order_by(order_expr)
            .offset(offset)
            .limit(limit)
            .all()
        )

        data = []
        for t in rows:
            mq = t.master_quotation
            tender = mq.tender if mq else None
            st = t.status
            data.append(
                {
                    "id": str(t.id),
                    "master_quotation_id": str(t.master_quotation_id),
                    "parent_id": str(t.parent_id) if t.parent_id else None,
                    "sort_order": t.sort_order,
                    "title": t.title,
                    "status_id": str(t.status_id),
                    "assignee_user_id": t.assignee_user_id,
                    "due_at": t.due_at,
                    "remind_at": t.remind_at,
                    "start_date": t.start_date,
                    "end_date": t.end_date,
                    "is_tender_level": bool(t.is_tender_level),
                    "created_at": t.created_at,
                    "quotation_code": mq.quotation_code if mq else None,
                    "tender_id": str(tender.id) if tender else None,
                    "tender_code": tender.tender_code if tender else None,
                    "status_code": st.code if st else None,
                    "status_label": st.label if st else None,
                    "status_color_hex": st.color_hex if st else None,
                }
            )
        return {"data": data, "total": int(total), "page": page, "limit": limit}

    def list_tasks_kanban(
        self,
        *,
        quick_search: Optional[str] = None,
        advanced_filter_clause: Any = None,
        assignee_user_id: Optional[str] = None,
        master_quotation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        T = CommercialQuotationActivityTask
        q = self.db.query(T).filter(T.deleted_at.is_(None))
        if quick_search and (qs := quick_search.strip()):
            like = f"%{qs}%"
            mq_match = exists().where(
                and_(
                    CommercialMasterQuotation.id == T.master_quotation_id,
                    or_(
                        CommercialMasterQuotation.quotation_code.ilike(like),
                        CommercialMasterQuotation.title.ilike(like),
                    ),
                )
            )
            tender_match = exists().where(
                and_(
                    CommercialMasterQuotation.id == T.master_quotation_id,
                    CommercialTender.id == CommercialMasterQuotation.tender_id,
                    or_(
                        CommercialTender.tender_code.ilike(like),
                        CommercialTender.title.ilike(like),
                    ),
                )
            )
            customer_match = exists().where(
                and_(
                    CommercialMasterQuotation.id == T.master_quotation_id,
                    CommercialTender.id == CommercialMasterQuotation.tender_id,
                    CommercialProject.id == CommercialTender.project_id,
                    CommercialLead.id == CommercialProject.lead_id,
                    Customer.id == CommercialLead.customer_id,
                    Customer.customer_name.ilike(like),
                )
            )
            q = q.filter(or_(T.title.ilike(like), mq_match, tender_match, customer_match))
        if assignee_user_id:
            q = q.filter(T.assignee_user_id == assignee_user_id)
        if master_quotation_id:
            q = q.filter(T.master_quotation_id == master_quotation_id)
        if advanced_filter_clause is not None:
            q = q.filter(advanced_filter_clause)
        rows = (
            q.options(
                joinedload(T.master_quotation).joinedload(CommercialMasterQuotation.tender),
                joinedload(T.status),
            )
            .order_by(T.sort_order.asc(), T.created_at.asc())
            .all()
        )
        statuses = (
            self.db.query(CommercialActivityTaskStatus)
            .filter(CommercialActivityTaskStatus.is_active.is_(True))
            .order_by(CommercialActivityTaskStatus.sort_order.asc())
            .all()
        )
        cols: Dict[str, Dict[str, Any]] = {
            str(s.id): {
                "status_id": str(s.id),
                "status_code": s.code,
                "status_label": s.label,
                "color_hex": s.color_hex,
                "sort_order": int(s.sort_order or 0),
                "items": [],
            }
            for s in statuses
        }
        for t in rows:
            sid = str(t.status_id)
            if sid not in cols:
                continue
            mq = t.master_quotation
            tender = mq.tender if mq else None
            cols[sid]["items"].append(
                {
                    "id": str(t.id),
                    "master_quotation_id": str(t.master_quotation_id),
                    "title": t.title,
                    "status_code": t.status.code if t.status else None,
                    "status_color_hex": t.status.color_hex if t.status else None,
                    "assignee_user_id": t.assignee_user_id,
                    "due_at": t.due_at,
                    "start_date": t.start_date,
                    "end_date": t.end_date,
                    "is_tender_level": bool(t.is_tender_level),
                    "quotation_code": mq.quotation_code if mq else None,
                    "tender_id": str(tender.id) if tender else None,
                    "tender_code": tender.tender_code if tender else None,
                }
            )
        return {"columns": list(cols.values())}
