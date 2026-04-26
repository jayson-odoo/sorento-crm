"""Dependency-based task scheduling for JSON task boards (FS, working days)."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.services.calendar_service import CalendarService


class TaskDependencyScheduleError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TaskDependencyScheduleService:
    def __init__(self, db: Session):
        self.db = db
        self.calendar = CalendarService(db)

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            raise TaskDependencyScheduleError(f"Invalid date format: {value}")

    @staticmethod
    def _to_iso(value: Optional[date]) -> Optional[str]:
        return value.isoformat() if value else None

    @staticmethod
    def _normalize_task_dep_ids(raw: Any) -> List[str]:
        if not isinstance(raw, list):
            return []
        out: List[str] = []
        seen: Set[str] = set()
        for item in raw:
            tid = str(item or "").strip()
            if not tid or tid in seen:
                continue
            seen.add(tid)
            out.append(tid)
        return out

    @staticmethod
    def _normalize_lead_time(raw: Any) -> int:
        if raw is None:
            return 1
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise TaskDependencyScheduleError("lead_time_days must be an integer.")
        if val < 1:
            raise TaskDependencyScheduleError("lead_time_days must be at least 1.")
        return val

    def _is_working_day(self, value: date) -> bool:
        info = self.calendar.is_working_day(when=datetime.combine(value, datetime.min.time()))
        return bool(info.get("is_working_day"))

    def _next_working_day_on_or_after(self, value: date) -> date:
        current = value
        guard = 0
        while not self._is_working_day(current):
            current = current + timedelta(days=1)
            guard += 1
            if guard > 370:
                raise TaskDependencyScheduleError("Unable to resolve working day.")
        return current

    def _add_working_days(self, start: date, days: int) -> date:
        dt = self.calendar.add_business_days(datetime.combine(start, datetime.min.time()), days)
        if not dt:
            raise TaskDependencyScheduleError("Unable to compute working-day offset.")
        return dt.date()

    def _compute_end_date(self, start: date, lead_days: int) -> date:
        return self._add_working_days(start, max(0, lead_days - 1))

    @staticmethod
    def _shift_by_calendar_days(start: date, delta_days: int) -> date:
        return start + timedelta(days=delta_days)

    def _build_graph(
        self, tasks: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]], Dict[str, List[str]], List[str]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        for task in tasks:
            tid = str(task.get("id") or "").strip()
            if not tid:
                raise TaskDependencyScheduleError("Task id is required.")
            by_id[tid] = task

        preds: Dict[str, List[str]] = {}
        succs: Dict[str, List[str]] = {tid: [] for tid in by_id}
        for tid, task in by_id.items():
            dep_ids = self._normalize_task_dep_ids(task.get("dependency_task_ids"))
            for dep_id in dep_ids:
                if dep_id == tid:
                    raise TaskDependencyScheduleError("Task cannot depend on itself.")
                if dep_id not in by_id:
                    raise TaskDependencyScheduleError(f"Unknown dependency task id: {dep_id}")
            preds[tid] = dep_ids
            for dep_id in dep_ids:
                succs.setdefault(dep_id, []).append(tid)
        return by_id, preds, succs, list(by_id.keys())

    def _topological_order(
        self,
        node_ids: List[str],
        preds: Dict[str, List[str]],
        succs: Dict[str, List[str]],
    ) -> List[str]:
        in_degree: Dict[str, int] = {nid: len(preds.get(nid, [])) for nid in node_ids}
        queue = deque([nid for nid in node_ids if in_degree[nid] == 0])
        order: List[str] = []
        while queue:
            nid = queue.popleft()
            order.append(nid)
            for nxt in succs.get(nid, []):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(node_ids):
            raise TaskDependencyScheduleError("Task dependency cycle detected.")
        return order

    def recalculate(
        self,
        *,
        task_board: Dict[str, Any],
        baseline_start_date: Optional[date] = None,
        changed_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        tasks_raw = list(task_board.get("tasks") or [])
        if not tasks_raw:
            return {
                "task_board": {"tasks": []},
                "impacts": [],
            }

        board = deepcopy(task_board)
        tasks = list(board.get("tasks") or [])
        by_id, preds, succs, node_ids = self._build_graph(tasks)
        order = self._topological_order(node_ids, preds, succs)

        baseline = baseline_start_date or date.today()
        baseline = self._next_working_day_on_or_after(baseline)

        original_dates: Dict[str, Tuple[Optional[str], Optional[str]]] = {
            tid: (
                str(by_id[tid].get("start_date")) if by_id[tid].get("start_date") else None,
                str(by_id[tid].get("end_date")) if by_id[tid].get("end_date") else None,
            )
            for tid in node_ids
        }

        computed: Dict[str, Tuple[date, date]] = {}
        downstream_scope: Optional[Set[str]] = None
        changed_id = str(changed_task_id or "").strip() or None
        if changed_id:
            if changed_id not in by_id:
                raise TaskDependencyScheduleError("Changed task not found in task board.")
            downstream_scope = set()
            queue = deque([changed_id])
            while queue:
                cur = queue.popleft()
                if cur in downstream_scope:
                    continue
                downstream_scope.add(cur)
                for nxt in succs.get(cur, []):
                    queue.append(nxt)

        for tid in order:
            task = by_id[tid]
            lead_days = self._normalize_lead_time(task.get("lead_time_days"))
            task["lead_time_days"] = lead_days
            task["dependency_task_ids"] = self._normalize_task_dep_ids(task.get("dependency_task_ids"))

            pred_ids = preds.get(tid, [])
            existing_start = self._parse_date(task.get("start_date"))
            existing_end = self._parse_date(task.get("end_date"))
            has_existing_range = bool(existing_start and existing_end)

            if changed_id and tid == changed_id and has_existing_range:
                start = existing_start
                end = existing_end if existing_end >= existing_start else existing_start
            elif downstream_scope is not None and tid not in downstream_scope:
                if has_existing_range:
                    start = existing_start
                    end = existing_end if existing_end >= existing_start else existing_start
                else:
                    continue
            else:
                if not pred_ids and has_existing_range:
                    start = existing_start
                    end = existing_end if existing_end >= existing_start else existing_start
                elif pred_ids:
                    if not has_existing_range:
                        continue
                    latest_finish = max(computed[p][1] for p in pred_ids)
                    start = self._add_working_days(latest_finish, 1)
                    delta_days = max(0, (existing_end - existing_start).days)
                    end = self._shift_by_calendar_days(start, delta_days)
                else:
                    if not has_existing_range:
                        continue
                    start = existing_start
                    end = existing_end if existing_end >= existing_start else existing_start
            computed[tid] = (start, end)
            task["start_date"] = self._to_iso(start)
            task["end_date"] = self._to_iso(end)

        impacted_scope = downstream_scope

        impacts: List[Dict[str, Any]] = []
        for tid in node_ids:
            old_start, old_end = original_dates[tid]
            new_start = by_id[tid].get("start_date")
            new_end = by_id[tid].get("end_date")
            if old_start == new_start and old_end == new_end:
                continue
            if impacted_scope is not None and tid not in impacted_scope:
                continue
            impacts.append(
                {
                    "task_id": tid,
                    "title": str(by_id[tid].get("title") or "Task"),
                    "old_start_date": old_start,
                    "old_end_date": old_end,
                    "new_start_date": new_start,
                    "new_end_date": new_end,
                }
            )
        impacts.sort(key=lambda x: (x.get("new_start_date") or "", x.get("title") or ""))

        return {"task_board": board, "impacts": impacts}
