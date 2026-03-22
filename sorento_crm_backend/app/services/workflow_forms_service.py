"""Business logic for workflow form definitions, publishing, and submissions."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.user import UserRoleAssignment
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
    WorkflowSubmissionLine,
    WorkflowSubmissionTransitionLog,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,98}$", re.I)

ALLOWED_FIELD_TYPES = frozenset(
    {
        "text",
        "textarea",
        "number",
        "email",
        "date",
        "datetime",
        "date_range",
        "select",
        "multi_select",
        "checkbox",
        "radio",
        "url",
        "phone",
    }
)


def default_draft_schema() -> Dict[str, Any]:
    return {
        "header_fields": [],
        "line_groups": [],
        "states": [
            {
                "id": "s_draft",
                "name": "Draft",
                "code": "draft",
                "is_initial": True,
                "is_terminal": False,
                "view_role_ids": [],
                "edit_role_ids": [],
            },
            {
                "id": "s_submitted",
                "name": "Submitted",
                "code": "submitted",
                "is_initial": False,
                "is_terminal": False,
                "view_role_ids": [],
                "edit_role_ids": [],
            },
            {
                "id": "s_approved",
                "name": "Approved",
                "code": "approved",
                "is_initial": False,
                "is_terminal": True,
                "view_role_ids": [],
                "edit_role_ids": [],
            },
            {
                "id": "s_rejected",
                "name": "Rejected",
                "code": "rejected",
                "is_initial": False,
                "is_terminal": True,
                "view_role_ids": [],
                "edit_role_ids": [],
            },
        ],
        "transitions": [
            {
                "id": "tr_submit",
                "from_state_id": "s_draft",
                "to_state_id": "s_submitted",
                "label": "Submit",
                "direction": "forward",
                "allowed_role_ids": [],
            },
            {
                "id": "tr_approve",
                "from_state_id": "s_submitted",
                "to_state_id": "s_approved",
                "label": "Approve",
                "direction": "forward",
                "allowed_role_ids": [],
            },
            {
                "id": "tr_reject",
                "from_state_id": "s_submitted",
                "to_state_id": "s_rejected",
                "label": "Reject",
                "direction": "forward",
                "allowed_role_ids": [],
            },
            {
                "id": "tr_send_back",
                "from_state_id": "s_submitted",
                "to_state_id": "s_draft",
                "label": "Send back",
                "direction": "back",
                "allowed_role_ids": [],
            },
        ],
        "notification_rules": [],
    }


def validate_schema(schema: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(schema, dict):
        return ["Schema must be an object."]
    states = schema.get("states") or []
    transitions = schema.get("transitions") or []
    header_fields = _header_fields_flat(schema)
    line_groups = schema.get("line_groups") or []

    if not isinstance(states, list) or len(states) < 1:
        errors.append("At least one state is required.")
    state_ids: Set[str] = set()
    initial_count = 0
    for s in states:
        if not isinstance(s, dict):
            errors.append("Each state must be an object.")
            continue
        sid = s.get("id")
        code = s.get("code")
        if not sid or not isinstance(sid, str):
            errors.append("Each state needs a string id.")
        else:
            state_ids.add(sid)
        if not code or not isinstance(code, str):
            errors.append(f"State {sid} needs a string code.")
        if s.get("is_initial"):
            initial_count += 1
    if initial_count != 1:
        errors.append("Exactly one state must have is_initial=true.")

    for i, f in enumerate(header_fields):
        if not isinstance(f, dict):
            errors.append(f"Header field {i} invalid.")
            continue
        fid = f.get("id")
        ftype = f.get("type")
        if not fid or not isinstance(fid, str):
            errors.append(f"Header field {i} needs id.")
        if not ftype or ftype not in ALLOWED_FIELD_TYPES:
            errors.append(f"Header field {fid or i} has unsupported type.")

    for gi, g in enumerate(line_groups):
        if not isinstance(g, dict):
            errors.append(f"Line group {gi} invalid.")
            continue
        gid = g.get("id")
        if not gid or not isinstance(gid, str):
            errors.append(f"Line group {gi} needs id.")
        for fi, lf in enumerate(g.get("fields") or []):
            if not isinstance(lf, dict):
                errors.append(f"Line group {gid} field {fi} invalid.")
                continue
            if not lf.get("id"):
                errors.append(f"Line group {gid} field {fi} needs id.")
            t = lf.get("type")
            if not t or t not in ALLOWED_FIELD_TYPES:
                errors.append(f"Line group {gid} field {lf.get('id')} unsupported type.")

    for t in transitions:
        if not isinstance(t, dict):
            errors.append("Each transition must be an object.")
            continue
        tid = t.get("id")
        fs = t.get("from_state_id")
        ts = t.get("to_state_id")
        if not tid:
            errors.append("Transition missing id.")
        if fs not in state_ids or ts not in state_ids:
            errors.append(f"Transition {tid} references unknown state.")
        direction = t.get("direction") or "forward"
        if direction not in ("forward", "back"):
            errors.append(f"Transition {tid} direction must be forward or back.")

    return errors


def _state_id_to_code(schema: Dict[str, Any], state_id: str) -> Optional[str]:
    for s in schema.get("states") or []:
        if isinstance(s, dict) and s.get("id") == state_id:
            return s.get("code")
    return None


def _state_by_code(schema: Dict[str, Any], code: str) -> Optional[Dict[str, Any]]:
    for s in schema.get("states") or []:
        if isinstance(s, dict) and s.get("code") == code:
            return s
    return None


def _initial_state_code(schema: Dict[str, Any]) -> str:
    for s in schema.get("states") or []:
        if isinstance(s, dict) and s.get("is_initial"):
            return str(s.get("code") or "draft")
    raise ValueError("No initial state")


def _header_fields_flat(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten header fields from header_sections (preferred) or legacy header_fields."""
    secs = schema.get("header_sections")
    if isinstance(secs, list) and len(secs) > 0:
        out: List[Dict[str, Any]] = []
        for s in secs:
            if isinstance(s, dict):
                for f in s.get("fields") or []:
                    if isinstance(f, dict):
                        out.append(f)
        return out
    return [f for f in (schema.get("header_fields") or []) if isinstance(f, dict)]


def _collect_field_defs(schema: Dict[str, Any]) -> Tuple[List[Dict], List[Tuple[str, List[Dict]]]]:
    header = _header_fields_flat(schema)
    line_groups: List[Tuple[str, List[Dict]]] = []
    for g in schema.get("line_groups") or []:
        if isinstance(g, dict) and g.get("id"):
            line_groups.append((g["id"], [f for f in (g.get("fields") or []) if isinstance(f, dict)]))
    return header, line_groups


def _parse_iso_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _validate_data_against_fields(fields: List[Dict[str, Any]], data: Dict[str, Any], path: str) -> List[str]:
    errs: List[str] = []
    for f in fields:
        fid = f.get("id")
        if not fid:
            continue
        val = data.get(fid)
        required = bool(f.get("required"))
        ft = f.get("type")

        if required:
            missing = False
            if val is None or val == "":
                missing = True
            elif isinstance(val, list) and len(val) == 0:
                missing = True
            elif ft == "date_range":
                if not isinstance(val, dict):
                    missing = True
                else:
                    start_s = str(val.get("start") or "").strip()
                    end_s = str(val.get("end") or "").strip()
                    if not start_s or not end_s:
                        missing = True
            if missing:
                errs.append(f"{path}: field '{f.get('label') or fid}' is required.")

        # light type checks
        if val is not None and val != "" and ft == "number":
            try:
                float(val)
            except (TypeError, ValueError):
                errs.append(f"{path}: '{fid}' must be a number.")
        if val is not None and val != "" and ft == "email" and isinstance(val, str) and "@" not in val:
            errs.append(f"{path}: '{fid}' must look like an email.")

        if ft == "date_range" and val is not None and val != "":
            if not isinstance(val, dict):
                errs.append(f"{path}: '{fid}' must be an object with start and end dates.")
            else:
                start_s = str(val.get("start") or "").strip()
                end_s = str(val.get("end") or "").strip()
                if (start_s and not end_s) or (end_s and not start_s):
                    errs.append(f"{path}: '{fid}' date range must include both start and end.")
                if start_s and end_s:
                    d0 = _parse_iso_date(start_s)
                    d1 = _parse_iso_date(end_s)
                    if d0 is None or d1 is None:
                        errs.append(f"{path}: '{fid}' dates must be valid ISO dates (YYYY-MM-DD).")
                    elif d1 < d0:
                        errs.append(f"{path}: '{fid}' end date must be on or after start date.")
    return errs


def user_role_ids(db: Session, user_id: str) -> Set[str]:
    rows = db.query(UserRoleAssignment.role_id).filter(UserRoleAssignment.user_id == user_id).all()
    return {r[0] for r in rows}


def _can_view_state(schema: Dict[str, Any], state_code: str, role_ids: Set[str]) -> bool:
    st = _state_by_code(schema, state_code)
    if not st:
        return True
    allowed = st.get("view_role_ids") or []
    if not allowed:
        return True
    return bool(role_ids.intersection(set(allowed)))


def _can_edit_state(schema: Dict[str, Any], state_code: str, role_ids: Set[str]) -> bool:
    st = _state_by_code(schema, state_code)
    if not st:
        return True
    allowed = st.get("edit_role_ids") or []
    if not allowed:
        return True
    return bool(role_ids.intersection(set(allowed)))


def _can_use_transition(trans: Dict[str, Any], role_ids: Set[str]) -> bool:
    allowed = trans.get("allowed_role_ids") or []
    if not allowed:
        return True
    return bool(role_ids.intersection(set(allowed)))


def _find_transition(schema: Dict[str, Any], transition_id: str, from_code: str) -> Optional[Dict[str, Any]]:
    from_id = None
    for s in schema.get("states") or []:
        if isinstance(s, dict) and s.get("code") == from_code:
            from_id = s.get("id")
            break
    if not from_id:
        return None
    for t in schema.get("transitions") or []:
        if not isinstance(t, dict):
            continue
        if t.get("id") == transition_id and t.get("from_state_id") == from_id:
            return t
    return None


def validate_submission_payload(schema: Dict[str, Any], header_data: Dict[str, Any], lines_payload: List[Dict[str, Any]]) -> List[str]:
    errs: List[str] = []
    header_fields, line_groups = _collect_field_defs(schema)
    errs.extend(_validate_data_against_fields(header_fields, header_data, "Header"))
    group_fields = {gid: flds for gid, flds in line_groups}
    for i, row in enumerate(lines_payload):
        gid = row.get("line_group_id")
        rd = row.get("row_data") or {}
        if not gid or gid not in group_fields:
            errs.append(f"Line {i}: unknown line_group_id.")
            continue
        errs.extend(_validate_data_against_fields(group_fields[gid], rd, f"Line {i}"))
    return errs


class WorkflowFormsService:
    def __init__(self, db: Session):
        self.db = db

    def list_definitions(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_field: str = "updated_at",
        sort_dir: str = "desc",
        advanced_filter_clause: Optional[Any] = None,
    ) -> Dict[str, Any]:
        q = self.db.query(WorkflowFormDefinition)
        filters = []
        if query:
            like = f"%{query.strip()}%"
            filters.append(
                or_(
                    WorkflowFormDefinition.name.ilike(like),
                    WorkflowFormDefinition.code.ilike(like),
                )
            )
        if is_active is not None:
            filters.append(WorkflowFormDefinition.is_active.is_(is_active))
        if advanced_filter_clause is not None:
            filters.append(advanced_filter_clause)
        if filters:
            q = q.filter(and_(*filters))

        sort_map = {
            "code": WorkflowFormDefinition.code,
            "name": WorkflowFormDefinition.name,
            "is_active": WorkflowFormDefinition.is_active,
            "created_at": WorkflowFormDefinition.created_at,
            "updated_at": WorkflowFormDefinition.updated_at,
        }
        col = sort_map.get(sort_field, WorkflowFormDefinition.updated_at)
        if sort_dir == "desc":
            q = q.order_by(col.desc())
        else:
            q = q.order_by(col.asc())

        total = q.count()
        items = q.offset((page - 1) * limit).limit(limit).all()
        return {"data": [self._def_out(d) for d in items], "total": total, "page": page, "limit": limit}

    def list_published_definitions_for_submission(self) -> List[Dict[str, Any]]:
        """Active definitions that have a published version (for menus and submitters without definitions.view)."""
        items = (
            self.db.query(WorkflowFormDefinition)
            .filter(
                WorkflowFormDefinition.is_active.is_(True),
                WorkflowFormDefinition.published_version_id.isnot(None),
            )
            .order_by(WorkflowFormDefinition.name)
            .all()
        )
        return [{"id": d.id, "code": d.code, "name": d.name} for d in items]

    def _def_out(self, d: WorkflowFormDefinition) -> Dict[str, Any]:
        pub_ver = None
        if d.published_version_id:
            pub_ver = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == d.published_version_id).first()
        return {
            "id": d.id,
            "code": d.code,
            "name": d.name,
            "description": d.description,
            "is_active": d.is_active,
            "draft_schema": d.draft_schema or {},
            "published_version_id": d.published_version_id,
            "published_version_number": pub_ver.version_number if pub_ver else None,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        }

    def get_definition(self, definition_id: str) -> WorkflowFormDefinition:
        d = self.db.query(WorkflowFormDefinition).filter(WorkflowFormDefinition.id == definition_id).first()
        if not d:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow form not found.")
        return d

    def create_definition(self, code: str, name: str, description: Optional[str], user_id: str) -> WorkflowFormDefinition:
        code = code.strip().lower()
        if not CODE_PATTERN.match(code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code must start with alphanumeric and use lowercase letters, numbers, dashes, underscores.",
            )
        if self.db.query(WorkflowFormDefinition).filter(WorkflowFormDefinition.code == code).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Code already exists.")
        d = WorkflowFormDefinition(
            id=str(uuid.uuid4()),
            code=code,
            name=name.strip(),
            description=description,
            is_active=True,
            draft_schema=default_draft_schema(),
            created_by_user_id=user_id,
        )
        self.db.add(d)
        self.db.commit()
        self.db.refresh(d)
        return d

    def update_definition(
        self,
        definition_id: str,
        name: Optional[str],
        description: Optional[str],
        is_active: Optional[bool],
        draft_schema: Optional[Dict[str, Any]],
    ) -> WorkflowFormDefinition:
        d = self.get_definition(definition_id)
        if name is not None:
            d.name = name.strip()
        if description is not None:
            d.description = description
        if is_active is not None:
            d.is_active = is_active
        if draft_schema is not None:
            errs = validate_schema(draft_schema)
            if errs:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errs})
            d.draft_schema = draft_schema
        d.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(d)
        return d

    def publish_definition(self, definition_id: str, user_id: str) -> WorkflowFormVersion:
        d = self.get_definition(definition_id)
        schema = d.draft_schema or {}
        errs = validate_schema(schema)
        if errs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errs})
        max_ver = (
            self.db.query(func.max(WorkflowFormVersion.version_number))
            .filter(WorkflowFormVersion.definition_id == d.id)
            .scalar()
        )
        next_ver = (max_ver or 0) + 1
        v = WorkflowFormVersion(
            id=str(uuid.uuid4()),
            definition_id=d.id,
            version_number=next_ver,
            schema=schema,
            created_by_user_id=user_id,
        )
        self.db.add(v)
        self.db.flush()
        d.published_version_id = v.id
        d.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(v)
        return v

    def preview(self, definition_id: str, source: str = "draft") -> Tuple[Dict[str, Any], str]:
        d = self.get_definition(definition_id)
        if source == "published":
            if not d.published_version_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No published version.")
            v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == d.published_version_id).first()
            if not v:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published version missing.")
            return v.schema, "published"
        return d.draft_schema or {}, "draft"

    def delete_definition(self, definition_id: str) -> None:
        d = self.get_definition(definition_id)
        n = self.db.query(WorkflowSubmission).filter(WorkflowSubmission.definition_id == d.id).count()
        if n:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete: {n} submission(s) exist. Remove submissions first.",
            )
        self.db.delete(d)
        self.db.commit()

    # --- submissions ---

    def list_submissions(
        self,
        page: int = 1,
        limit: int = 50,
        definition_id: Optional[str] = None,
        state_code: Optional[str] = None,
        query: Optional[str] = None,
        sort_field: str = "updated_at",
        sort_dir: str = "desc",
        advanced_filter_clause: Optional[Any] = None,
    ) -> Dict[str, Any]:
        q = self.db.query(WorkflowSubmission).options(
            joinedload(WorkflowSubmission.lines),
            joinedload(WorkflowSubmission.definition),
        )
        filters = []
        if definition_id:
            filters.append(WorkflowSubmission.definition_id == definition_id)
        if state_code and state_code.strip():
            filters.append(WorkflowSubmission.current_state_code == state_code.strip())
        if query and query.strip():
            like = f"%{query.strip()}%"
            q = q.outerjoin(
                WorkflowFormDefinition,
                WorkflowSubmission.definition_id == WorkflowFormDefinition.id,
            )
            filters.append(
                or_(
                    WorkflowSubmission.current_state_code.ilike(like),
                    WorkflowFormDefinition.name.ilike(like),
                    WorkflowFormDefinition.code.ilike(like),
                )
            )
        if advanced_filter_clause is not None:
            filters.append(advanced_filter_clause)
        if filters:
            q = q.filter(and_(*filters))

        sort_map = {
            "current_state_code": WorkflowSubmission.current_state_code,
            "created_at": WorkflowSubmission.created_at,
            "updated_at": WorkflowSubmission.updated_at,
            "definition_id": WorkflowSubmission.definition_id,
        }
        col = sort_map.get(sort_field, WorkflowSubmission.updated_at)
        if sort_dir == "desc":
            q = q.order_by(col.desc())
        else:
            q = q.order_by(col.asc())

        total = q.count()
        rows = q.offset((page - 1) * limit).limit(limit).all()
        return {
            "data": [
                self._submission_out(s, include_logs=False, include_form_schema=False) for s in rows
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }

    def _submission_out(
        self,
        s: WorkflowSubmission,
        include_logs: bool = True,
        include_form_schema: bool = False,
    ) -> Dict[str, Any]:
        lines = [
            {
                "id": ln.id,
                "line_group_id": ln.line_group_id,
                "sort_order": ln.sort_order,
                "row_data": ln.row_data or {},
            }
            for ln in (s.lines or [])
        ]
        logs = []
        if include_logs:
            logs = [
                {
                    "id": lg.id,
                    "from_state_code": lg.from_state_code,
                    "to_state_code": lg.to_state_code,
                    "transition_id": lg.transition_id,
                    "remark": lg.remark,
                    "user_id": lg.user_id,
                    "created_at": lg.created_at,
                }
                for lg in sorted(s.transition_logs or [], key=lambda x: x.created_at or datetime.min)
            ]
        def_name: Optional[str] = None
        def_code: Optional[str] = None
        if getattr(s, "definition", None) is not None:
            def_name = s.definition.name
            def_code = s.definition.code
        else:
            d = (
                self.db.query(WorkflowFormDefinition)
                .filter(WorkflowFormDefinition.id == s.definition_id)
                .first()
            )
            if d:
                def_name = d.name
                def_code = d.code

        form_schema: Optional[Dict[str, Any]] = None
        form_version_number: Optional[int] = None
        if include_form_schema:
            v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == s.version_id).first()
            if v:
                form_schema = v.schema if isinstance(v.schema, dict) else {}
                form_version_number = v.version_number

        return {
            "id": s.id,
            "definition_id": s.definition_id,
            "version_id": s.version_id,
            "current_state_code": s.current_state_code,
            "header_data": s.header_data or {},
            "lines": lines,
            "transition_logs": logs,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "created_by_user_id": s.created_by_user_id,
            "definition_name": def_name,
            "definition_code": def_code,
            "form_version_number": form_version_number,
            "form_schema": form_schema,
        }

    def get_submission(self, submission_id: str) -> WorkflowSubmission:
        s = (
            self.db.query(WorkflowSubmission)
            .filter(WorkflowSubmission.id == submission_id)
            .first()
        )
        if not s:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found.")
        return s

    def create_submission(
        self,
        definition_id: str,
        header_data: Dict[str, Any],
        lines: List[Dict[str, Any]],
        user_id: str,
    ) -> WorkflowSubmission:
        d = self.get_definition(definition_id)
        if not d.published_version_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Form has no published version.")
        v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == d.published_version_id).first()
        if not v:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Published version missing.")
        schema = v.schema or {}
        lines_payload = [{"line_group_id": x["line_group_id"], "row_data": x.get("row_data") or {}} for x in lines]
        errs = validate_submission_payload(schema, header_data, lines_payload)
        if errs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errs})
        try:
            initial = _initial_state_code(schema)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid form schema.")
        sub = WorkflowSubmission(
            id=str(uuid.uuid4()),
            definition_id=d.id,
            version_id=v.id,
            current_state_code=initial,
            header_data=header_data or {},
            created_by_user_id=user_id,
        )
        self.db.add(sub)
        self.db.flush()
        for i, row in enumerate(lines):
            self.db.add(
                WorkflowSubmissionLine(
                    id=str(uuid.uuid4()),
                    submission_id=sub.id,
                    line_group_id=row["line_group_id"],
                    sort_order=row.get("sort_order", i),
                    row_data=row.get("row_data") or {},
                )
            )
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def update_submission(
        self,
        submission_id: str,
        header_data: Optional[Dict[str, Any]],
        lines: Optional[List[Dict[str, Any]]],
        user_id: str,
    ) -> WorkflowSubmission:
        s = self.get_submission(submission_id)
        v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == s.version_id).first()
        if not v:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Version missing.")
        schema = v.schema or {}
        st = _state_by_code(schema, s.current_state_code)
        if st and st.get("is_terminal"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a terminal state.")
        roles = user_role_ids(self.db, user_id)
        if not _can_edit_state(schema, s.current_state_code, roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit in this state.")
        new_header = s.header_data or {}
        if header_data is not None:
            new_header = header_data
        new_lines_payload: List[Dict[str, Any]] = []
        if lines is not None:
            self.db.query(WorkflowSubmissionLine).filter(WorkflowSubmissionLine.submission_id == s.id).delete(
                synchronize_session=False
            )
            for i, row in enumerate(lines):
                new_lines_payload.append(
                    {
                        "line_group_id": row["line_group_id"],
                        "sort_order": row.get("sort_order", i),
                        "row_data": row.get("row_data") or {},
                    }
                )
                self.db.add(
                    WorkflowSubmissionLine(
                        id=str(uuid.uuid4()),
                        submission_id=s.id,
                        line_group_id=row["line_group_id"],
                        sort_order=row.get("sort_order", i),
                        row_data=row.get("row_data") or {},
                    )
                )
        else:
            new_lines_payload = [
                {"line_group_id": ln.line_group_id, "row_data": ln.row_data or {}} for ln in s.lines
            ]
        errs = validate_submission_payload(schema, new_header, new_lines_payload)
        if errs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errs})
        s.header_data = new_header
        s.updated_by_user_id = user_id
        s.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(s)
        return s

    def delete_submission(self, submission_id: str) -> None:
        s = self.get_submission(submission_id)
        self.db.delete(s)
        self.db.commit()

    def apply_transition(
        self,
        submission_id: str,
        transition_id: str,
        remark: Optional[str],
        user_id: str,
    ) -> WorkflowSubmission:
        s = self.get_submission(submission_id)
        v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == s.version_id).first()
        if not v:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Version missing.")
        schema = v.schema or {}
        trans = _find_transition(schema, transition_id, s.current_state_code)
        if not trans:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid transition for current state.")
        roles = user_role_ids(self.db, user_id)
        if not _can_use_transition(trans, roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to use this transition.")
        to_code = _state_id_to_code(schema, trans.get("to_state_id"))
        if not to_code:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Broken schema.")
        from_code = s.current_state_code
        s.current_state_code = to_code
        s.updated_by_user_id = user_id
        s.updated_at = datetime.utcnow()
        log = WorkflowSubmissionTransitionLog(
            id=str(uuid.uuid4()),
            submission_id=s.id,
            from_state_code=from_code,
            to_state_code=to_code,
            transition_id=transition_id,
            remark=remark,
            user_id=user_id,
        )
        self.db.add(log)
        self.db.flush()
        self._fire_notifications(schema, s, trans, log.id, user_id)
        self.db.commit()
        self.db.refresh(s)
        return s

    def _fire_notifications(
        self,
        schema: Dict[str, Any],
        submission: WorkflowSubmission,
        transition: Dict[str, Any],
        log_id: str,
        actor_user_id: str,
    ) -> None:
        definition = (
            self.db.query(WorkflowFormDefinition)
            .filter(WorkflowFormDefinition.id == submission.definition_id)
            .first()
        )
        title = f"Workflow: {definition.name if definition else 'Form'} — {transition.get('label') or 'Updated'}"
        body = f"Submission {submission.id[:8]}… moved to {submission.current_state_code}."
        submitter_body = (
            f'Your submission {submission.id[:8]}… is now in state "{submission.current_state_code}".'
        )
        svc = NotificationService(self.db)
        # event_type must fit notifications.event_type (VARCHAR); log_id is unique per transition log
        event_type = f"workflow_forms.tr.{log_id}"
        submitter_event_type = f"{event_type}.submitter"

        # Always notify the original submitter when the workflow state changes (even if no builder rules).
        submitter_id = submission.created_by_user_id
        if submitter_id:
            try:
                svc.create(
                    user_id=str(submitter_id),
                    type="workflow_forms.transition",
                    title=title,
                    body=submitter_body,
                    data={"submission_id": submission.id, "definition_id": submission.definition_id},
                    source_entity_type="workflow_submission",
                    source_entity_id=str(submission.id),
                    event_type=submitter_event_type,
                )
            except Exception as e:
                logger.warning("Submitter notification failed for user %s: %s", submitter_id, e)

        tid = transition.get("id")
        rules = [r for r in (schema.get("notification_rules") or []) if isinstance(r, dict) and r.get("transition_id") == tid]
        if not rules:
            return
        recipient_role_ids: Set[str] = set()
        channels: Set[str] = set()
        for rule in rules:
            for rid in rule.get("recipient_role_ids") or []:
                recipient_role_ids.add(str(rid))
            for ch in rule.get("channels") or ["in_app"]:
                channels.add(str(ch))
        if not recipient_role_ids:
            return
        user_ids = (
            self.db.query(UserRoleAssignment.user_id)
            .filter(UserRoleAssignment.role_id.in_(list(recipient_role_ids)))
            .distinct()
            .all()
        )
        for (uid,) in user_ids:
            if str(uid) == str(actor_user_id):
                continue
            # Submitter already received workflow_forms.tr.{log_id}.submitter
            if submitter_id and str(uid) == str(submitter_id):
                continue
            try:
                want_email = "email" in channels
                want_in_app = "in_app" in channels
                if want_email and want_in_app:
                    svc.create(
                        user_id=str(uid),
                        type="workflow_forms.transition",
                        title=title,
                        body=body,
                        data={"submission_id": submission.id, "definition_id": submission.definition_id},
                        source_entity_type="workflow_submission",
                        source_entity_id=str(submission.id),
                        event_type=event_type,
                    )
                elif want_in_app:
                    svc.create_in_app_only(
                        user_id=str(uid),
                        type="workflow_forms.transition",
                        title=title,
                        body=body,
                        source_entity_type="workflow_submission",
                        source_entity_id=str(submission.id),
                        event_type=event_type,
                    )
                elif want_email:
                    svc.create(
                        user_id=str(uid),
                        type="workflow_forms.transition",
                        title=title,
                        body=body,
                        data={"submission_id": submission.id},
                        source_entity_type="workflow_submission",
                        source_entity_id=str(submission.id),
                        event_type=event_type,
                    )
            except Exception as e:
                logger.warning("Notification failed for user %s: %s", uid, e)

    def allowed_transitions_for_user(self, submission_id: str, user_id: str) -> List[Dict[str, Any]]:
        s = self.get_submission(submission_id)
        v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == s.version_id).first()
        if not v:
            return []
        schema = v.schema or {}
        roles = user_role_ids(self.db, user_id)
        from_id = None
        for st in schema.get("states") or []:
            if isinstance(st, dict) and st.get("code") == s.current_state_code:
                from_id = st.get("id")
                break
        if not from_id:
            return []
        out: List[Dict[str, Any]] = []
        for t in schema.get("transitions") or []:
            if not isinstance(t, dict):
                continue
            if t.get("from_state_id") != from_id:
                continue
            if _can_use_transition(t, roles):
                to_code = _state_id_to_code(schema, t.get("to_state_id"))
                out.append(
                    {
                        "id": t.get("id"),
                        "label": t.get("label"),
                        "direction": t.get("direction") or "forward",
                        "to_state_code": to_code,
                    }
                )
        return [x for x in out if x.get("id")]

