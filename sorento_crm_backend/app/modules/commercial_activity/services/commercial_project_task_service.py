"""SQL-backed project tasks: CRUD, list/kanban search, schedule application."""
from __future__ import annotations

import uuid
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, asc, exists, func, or_
from sqlalchemy.orm import Session, joinedload

from app.modules.commercial_activity.models import (
    CommercialActivityTaskStatus,
    CommercialActivityTemplate,
    CommercialActivityTemplateNode,
    CommercialProjectTask,
    CommercialProjectTaskCategory,
)
from app.modules.commercial_core.models import CommercialLead, CommercialProject
from app.models.order import Customer
from app.services.task_dependency_schedule_service import (
    TaskDependencyScheduleError,
    TaskDependencyScheduleService,
)


def _uuid_str() -> str:
    return str(uuid.uuid4())


def _to_iso(d: Any) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, (datetime, date)):
        return d.isoformat()
    return str(d)


class CommercialProjectTaskError(Exception):
    def __init__(self, message: str, code: str = "project_task_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class CommercialProjectTaskService:
    def __init__(self, db: Session):
        self.db = db

    def _default_status_id(self) -> str:
        row = (
            self.db.query(CommercialActivityTaskStatus)
            .filter(
                CommercialActivityTaskStatus.is_default.is_(True),
                CommercialActivityTaskStatus.is_active.is_(True),
            )
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
            raise CommercialProjectTaskError("No activity task statuses configured.")
        return str(row.id)

    def _category_label(self, code: Optional[str]) -> str:
        if not code:
            return "General"
        row = (
            self.db.query(CommercialProjectTaskCategory)
            .filter(CommercialProjectTaskCategory.code == code, CommercialProjectTaskCategory.is_active.is_(True))
            .first()
        )
        if row:
            return row.label
        return str(code).replace("_", " ").strip().title() or "General"

    def _status_by_code(self) -> Dict[str, str]:
        rows = (
            self.db.query(CommercialActivityTaskStatus)
            .filter(CommercialActivityTaskStatus.is_active.is_(True))
            .all()
        )
        return {r.code: str(r.id) for r in rows}

    def list_tasks_flat(
        self,
        project_id: str,
        *,
        include_deleted: bool = False,
    ) -> List[CommercialProjectTask]:
        q = self.db.query(CommercialProjectTask).filter(CommercialProjectTask.project_id == project_id)
        if not include_deleted:
            q = q.filter(CommercialProjectTask.deleted_at.is_(None))
        return q.order_by(CommercialProjectTask.sort_order.asc()).all()

    def serialize_board(self, project_id: str) -> Dict[str, Any]:
        rows = self.list_tasks_flat(project_id)
        project = self.db.query(CommercialProject).filter(CommercialProject.id == project_id).first()
        template_id = str(project.task_template_id) if project and project.task_template_id else None
        template_name = None
        template_version = None
        if template_id:
            tpl = (
                self.db.query(CommercialActivityTemplate)
                .filter(CommercialActivityTemplate.id == template_id)
                .first()
            )
            if tpl:
                template_name = tpl.name
                template_version = int(tpl.version_number or 1)
        out_tasks: List[Dict[str, Any]] = []
        for r in rows:
            status_code = r.status.code if r.status else None
            out_tasks.append(
                {
                    "id": str(r.id),
                    "parent_task_id": str(r.parent_id) if r.parent_id else None,
                    "template_node_id": str(r.template_node_id) if r.template_node_id else None,
                    "parent_template_node_id": str(r.parent_template_node_id) if r.parent_template_node_id else None,
                    "sort_order": int(r.sort_order or 0),
                    "title": r.title,
                    "description": r.description,
                    "category": self._category_label(r.category_code),
                    "category_code": r.category_code,
                    "status_code": status_code,
                    "is_service_task": bool(r.is_service_task),
                    "assignee_user_id": r.assignee_user_id,
                    "lead_time_days": int(r.lead_time_days or 1),
                    "dependency_task_ids": list(r.dependency_task_ids or []),
                    "start_date": _to_iso(r.start_date),
                    "end_date": _to_iso(r.end_date),
                }
            )
        out: Dict[str, Any] = {"tasks": out_tasks}
        if template_id:
            out["template_id"] = template_id
            out["template_name"] = template_name
            out["template_version"] = template_version
        return out

    def replace_board(
        self,
        project_id: str,
        task_board: Dict[str, Any],
    ) -> None:
        """Replace all tasks for a project with the given task_board dict (no schedule recompute)."""
        status_by_code = self._status_by_code()
        default_id = self._default_status_id()
        # Hard-delete existing rows to keep the JSONB-replace semantics the FE relies on.
        self.db.query(CommercialProjectTask).filter(CommercialProjectTask.project_id == project_id).delete()
        self.db.flush()
        tasks = list((task_board or {}).get("tasks") or [])
        for raw in tasks:
            if not isinstance(raw, dict):
                continue
            tid = str(raw.get("id") or _uuid_str())
            status_code = str(raw.get("status_code") or "").strip()
            status_id = status_by_code.get(status_code) or default_id
            row = CommercialProjectTask(
                id=tid,
                project_id=project_id,
                parent_id=(str(raw.get("parent_task_id")).strip() or None) if raw.get("parent_task_id") else None,
                template_node_id=(str(raw.get("template_node_id")).strip() or None) if raw.get("template_node_id") else None,
                parent_template_node_id=(str(raw.get("parent_template_node_id")).strip() or None)
                if raw.get("parent_template_node_id")
                else None,
                sort_order=int(raw.get("sort_order") or 0),
                title=str(raw.get("title") or "Task")[:512],
                description=raw.get("description") or None,
                category_code=(str(raw.get("category_code") or "").strip() or None),
                is_service_task=bool(raw.get("is_service_task") or False),
                status_id=status_id,
                assignee_user_id=(str(raw.get("assignee_user_id")).strip() or None)
                if raw.get("assignee_user_id")
                else None,
                lead_time_days=max(1, int(raw.get("lead_time_days") or 1)),
                dependency_task_ids=list(raw.get("dependency_task_ids") or []),
                start_date=_parse_dt(raw.get("start_date")),
                end_date=_parse_dt(raw.get("end_date")),
            )
            self.db.add(row)
        self.db.flush()

    def seed_tasks_from_template(self, project_id: str, template_id: Optional[str]) -> None:
        # Wipe and reseed from the template.
        self.db.query(CommercialProjectTask).filter(CommercialProjectTask.project_id == project_id).delete()
        self.db.flush()
        if not template_id:
            return
        tpl = (
            self.db.query(CommercialActivityTemplate)
            .options(
                joinedload(CommercialActivityTemplate.nodes).joinedload(
                    CommercialActivityTemplateNode.default_status
                )
            )
            .filter(CommercialActivityTemplate.id == template_id, CommercialActivityTemplate.is_active.is_(True))
            .first()
        )
        if not tpl:
            raise CommercialProjectTaskError("Task template not found")
        if getattr(tpl, "template_scope", None) and getattr(tpl, "template_scope", None) != "project":
            raise CommercialProjectTaskError("This task template is not scoped for projects.")
        default_id = self._default_status_id()
        node_to_task_id: Dict[str, str] = {}
        for node in sorted(tpl.nodes or [], key=lambda n: (n.sort_order or 0, n.title or "")):
            node_to_task_id[str(node.id)] = _uuid_str()
        for node in sorted(tpl.nodes or [], key=lambda n: (n.sort_order or 0, n.title or "")):
            status_id = (
                str(node.default_status.id) if node.default_status and node.default_status.is_active else default_id
            )
            dep_node_ids = getattr(node, "dependency_node_ids", []) or []
            dep_task_ids = [node_to_task_id[str(x)] for x in dep_node_ids if str(x) in node_to_task_id]
            row = CommercialProjectTask(
                id=node_to_task_id[str(node.id)],
                project_id=project_id,
                parent_id=node_to_task_id.get(str(node.parent_id)) if node.parent_id else None,
                template_node_id=str(node.id),
                parent_template_node_id=str(node.parent_id) if node.parent_id else None,
                sort_order=int(node.sort_order or 0),
                title=node.title,
                description=node.description,
                category_code=(node.category_code or "").strip() or None,
                is_service_task=bool(getattr(node, "is_service_task", False)),
                status_id=status_id,
                assignee_user_id=None,
                lead_time_days=int(getattr(node, "lead_time_days", 1) or 1),
                dependency_task_ids=dep_task_ids,
                start_date=None,
                end_date=None,
            )
            self.db.add(row)
        self.db.flush()

    def apply_schedule(
        self,
        project_id: str,
        *,
        baseline_start_date: Optional[str] = None,
        changed_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        board = self.serialize_board(project_id)
        scheduler = TaskDependencyScheduleService(self.db)
        try:
            out = scheduler.recalculate(
                task_board=board,
                baseline_start_date=scheduler._parse_date(baseline_start_date),
                changed_task_id=changed_task_id,
            )
        except TaskDependencyScheduleError as e:
            raise CommercialProjectTaskError(e.message)
        recomputed_tasks = list((out.get("task_board") or {}).get("tasks") or [])
        by_id = {str(t.get("id")): t for t in recomputed_tasks if isinstance(t, dict) and t.get("id")}
        rows = self.list_tasks_flat(project_id)
        for row in rows:
            t = by_id.get(str(row.id))
            if not t:
                continue
            row.start_date = _parse_dt(t.get("start_date"))
            row.end_date = _parse_dt(t.get("end_date"))
            row.lead_time_days = max(1, int(t.get("lead_time_days") or row.lead_time_days or 1))
            row.dependency_task_ids = list(t.get("dependency_task_ids") or [])
        self.db.flush()
        return {"task_board": self.serialize_board(project_id), "impacts": out.get("impacts") or []}

    def seed_schedule_from_baseline(
        self,
        project_id: str,
        *,
        baseline_start_date: Optional[str],
    ) -> None:
        """Initial schedule seed for a freshly-templated project.

        Walks tasks in topological order over ``dependency_task_ids`` and assigns
        start/end dates from the project's baseline using working-day math:
        - Root tasks (no deps) start on the baseline (next working day).
        - Each task's end = start + (lead_time_days - 1) working days (inclusive).
        - Dependent tasks start on the next working day after the latest predecessor's end.

        Subtasks (parent_id set) inherit the timing of their parent rather than
        getting their own slot, matching how the FE renders subtask rows under
        their parent's date range.
        """
        scheduler = TaskDependencyScheduleService(self.db)
        baseline = scheduler._parse_date(baseline_start_date) or date.today()
        baseline = scheduler._next_working_day_on_or_after(baseline)

        rows = self.list_tasks_flat(project_id)
        if not rows:
            return
        by_id = {str(r.id): r for r in rows}
        roots = [r for r in rows if not r.parent_id]
        if not roots:
            return

        preds: Dict[str, List[str]] = {}
        succs: Dict[str, List[str]] = {str(r.id): [] for r in roots}
        for r in roots:
            deps_raw = list(r.dependency_task_ids or [])
            deps = [str(d) for d in deps_raw if str(d) in {str(x.id) for x in roots}]
            preds[str(r.id)] = deps
            for d in deps:
                succs.setdefault(d, []).append(str(r.id))

        in_degree: Dict[str, int] = {str(r.id): len(preds.get(str(r.id), [])) for r in roots}
        queue = deque([rid for rid, deg in in_degree.items() if deg == 0])
        order: List[str] = []
        while queue:
            cur = queue.popleft()
            order.append(cur)
            for nxt in succs.get(cur, []):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(roots):
            # Cycle in dependencies — fall back to seeding roots only on baseline.
            order = [str(r.id) for r in roots]

        computed: Dict[str, tuple[date, date]] = {}
        for tid in order:
            row = by_id[tid]
            lead_days = max(1, int(row.lead_time_days or 1))
            pred_ids = preds.get(tid, [])
            if pred_ids:
                latest_end = max(computed[p][1] for p in pred_ids if p in computed)
                start = scheduler._add_working_days(latest_end, 1)
            else:
                start = baseline
            end = scheduler._compute_end_date(start, lead_days)
            computed[tid] = (start, end)
            row.start_date = datetime.combine(start, datetime.min.time())
            row.end_date = datetime.combine(end, datetime.min.time())

        # Subtasks inherit parent timing.
        for r in rows:
            if r.parent_id and str(r.parent_id) in computed:
                start, end = computed[str(r.parent_id)]
                r.start_date = datetime.combine(start, datetime.min.time())
                r.end_date = datetime.combine(end, datetime.min.time())
        self.db.flush()

    def update_task_status(
        self,
        task_id: str,
        status_code: str,
    ) -> CommercialProjectTask:
        row = (
            self.db.query(CommercialProjectTask)
            .filter(CommercialProjectTask.id == task_id, CommercialProjectTask.deleted_at.is_(None))
            .first()
        )
        if not row:
            raise CommercialProjectTaskError("Task not found")
        st = (
            self.db.query(CommercialActivityTaskStatus)
            .filter(
                CommercialActivityTaskStatus.code == status_code,
                CommercialActivityTaskStatus.is_active.is_(True),
            )
            .first()
        )
        if not st:
            raise CommercialProjectTaskError("Invalid status")
        row.status_id = str(st.id)
        self.db.commit()
        self.db.refresh(row)
        return row

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
        project_id: Optional[str] = None,
        overdue_only: bool = False,
        upcoming_within_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        T = CommercialProjectTask
        q = self.db.query(T).filter(T.deleted_at.is_(None))
        if quick_search and (qs := quick_search.strip()):
            like = f"%{qs}%"
            project_match = exists().where(
                and_(
                    CommercialProject.id == T.project_id,
                    CommercialProject.title.ilike(like),
                )
            )
            developer_match = exists().where(
                and_(
                    CommercialProject.id == T.project_id,
                    Customer.id == CommercialProject.developer_customer_id,
                    Customer.customer_name.ilike(like),
                )
            )
            customer_match = exists().where(
                and_(
                    CommercialProject.id == T.project_id,
                    CommercialLead.id == CommercialProject.lead_id,
                    Customer.id == CommercialLead.customer_id,
                    Customer.customer_name.ilike(like),
                )
            )
            q = q.filter(or_(T.title.ilike(like), project_match, developer_match, customer_match))
        if assignee_user_id:
            q = q.filter(T.assignee_user_id == assignee_user_id)
        if project_id:
            q = q.filter(T.project_id == project_id)
        non_terminal = exists().where(
            and_(
                CommercialActivityTaskStatus.id == T.status_id,
                CommercialActivityTaskStatus.is_terminal.is_(False),
            )
        )
        if overdue_only:
            today = datetime.utcnow()
            q = q.filter(T.end_date.isnot(None), T.end_date < today, non_terminal)
        elif upcoming_within_days is not None and upcoming_within_days >= 0:
            start = datetime.utcnow()
            end = start + timedelta(days=int(upcoming_within_days))
            q = q.filter(T.end_date.isnot(None), T.end_date >= start, T.end_date <= end, non_terminal)
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
                joinedload(T.project).joinedload(CommercialProject.lead).joinedload(CommercialLead.customer),
                joinedload(T.project).joinedload(CommercialProject.developer_customer),
                joinedload(T.status),
            )
            .order_by(order_expr)
            .offset(offset)
            .limit(limit)
            .all()
        )

        data = []
        for t in rows:
            project = t.project
            lead = project.lead if project else None
            customer = lead.customer if lead else None
            developer = project.developer_customer if project else None
            st = t.status
            data.append(
                {
                    "id": str(t.id),
                    "project_id": str(t.project_id),
                    "parent_id": str(t.parent_id) if t.parent_id else None,
                    "sort_order": t.sort_order,
                    "title": t.title,
                    "status_id": str(t.status_id),
                    "status_code": st.code if st else None,
                    "status_label": st.label if st else None,
                    "status_color_hex": st.color_hex if st else None,
                    "assignee_user_id": t.assignee_user_id,
                    "start_date": _to_iso(t.start_date),
                    "end_date": _to_iso(t.end_date),
                    "lead_time_days": int(t.lead_time_days or 1),
                    "is_service_task": bool(t.is_service_task),
                    "category_code": t.category_code,
                    "created_at": t.created_at,
                    "project_title": project.title if project else None,
                    "lead_code": lead.lead_code if lead else None,
                    "customer_id": str(customer.id) if customer else None,
                    "customer_name": customer.customer_name if customer else None,
                    "developer_id": str(developer.id) if developer else None,
                    "developer_name": developer.customer_name if developer else None,
                }
            )
        return {"data": data, "total": int(total), "page": page, "limit": limit}

    def list_tasks_kanban(
        self,
        *,
        quick_search: Optional[str] = None,
        advanced_filter_clause: Any = None,
        assignee_user_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        T = CommercialProjectTask
        q = self.db.query(T).filter(T.deleted_at.is_(None))
        if quick_search and (qs := quick_search.strip()):
            like = f"%{qs}%"
            project_match = exists().where(
                and_(
                    CommercialProject.id == T.project_id,
                    CommercialProject.title.ilike(like),
                )
            )
            developer_match = exists().where(
                and_(
                    CommercialProject.id == T.project_id,
                    Customer.id == CommercialProject.developer_customer_id,
                    Customer.customer_name.ilike(like),
                )
            )
            customer_match = exists().where(
                and_(
                    CommercialProject.id == T.project_id,
                    CommercialLead.id == CommercialProject.lead_id,
                    Customer.id == CommercialLead.customer_id,
                    Customer.customer_name.ilike(like),
                )
            )
            q = q.filter(or_(T.title.ilike(like), project_match, developer_match, customer_match))
        if assignee_user_id:
            q = q.filter(T.assignee_user_id == assignee_user_id)
        if project_id:
            q = q.filter(T.project_id == project_id)
        if advanced_filter_clause is not None:
            q = q.filter(advanced_filter_clause)
        rows = (
            q.options(
                joinedload(T.project).joinedload(CommercialProject.lead).joinedload(CommercialLead.customer),
                joinedload(T.project).joinedload(CommercialProject.developer_customer),
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
        cols: Dict[str, Dict[str, Any]] = {}
        for s in statuses:
            cols[str(s.id)] = {
                "status_id": str(s.id),
                "status_code": s.code,
                "status_label": s.label,
                "color_hex": s.color_hex,
                "sort_order": int(s.sort_order or 0),
                "items": [],
            }
        for t in rows:
            sid = str(t.status_id)
            if sid not in cols:
                continue
            project = t.project
            lead = project.lead if project else None
            customer = lead.customer if lead else None
            developer = project.developer_customer if project else None
            cols[sid]["items"].append(
                {
                    "id": str(t.id),
                    "project_id": str(t.project_id),
                    "title": t.title,
                    "status_code": t.status.code if t.status else None,
                    "status_color_hex": t.status.color_hex if t.status else None,
                    "assignee_user_id": t.assignee_user_id,
                    "start_date": _to_iso(t.start_date),
                    "end_date": _to_iso(t.end_date),
                    "project_title": project.title if project else None,
                    "lead_code": lead.lead_code if lead else None,
                    "customer_id": str(customer.id) if customer else None,
                    "customer_name": customer.customer_name if customer else None,
                    "developer_id": str(developer.id) if developer else None,
                    "developer_name": developer.customer_name if developer else None,
                }
            )
        return {"columns": list(cols.values())}


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    txt = str(value).strip()
    if not txt:
        return None
    try:
        return datetime.fromisoformat(txt[:19])
    except ValueError:
        try:
            return datetime.strptime(txt[:10], "%Y-%m-%d")
        except ValueError:
            return None
