"""Business logic for workflow form definitions, publishing, and submissions.

Two authorities, and neither is this module. The **document** (what a form asks) is
owned by ``app.form_engine``: ``validate_form_doc`` is the publish gate and
``validate_submission`` is the answer boundary. The **graph** (what a submission may do
next) is owned by the status engine: ``app.services.status_service`` decides whether a
move is legal, for the graph the submission's definition scopes.

Before F1 both lived here, in a state machine embedded in
``workflow_form_versions.schema`` alongside a second, disagreeing validator. Nothing in
this module reads ``states`` / ``transitions`` out of that JSON any more, and no release
ships with both validators.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.form_engine.schemas import FORM_SCHEMA_VERSION, FormDocument, validate_form_doc
from app.form_engine.validation import validate_submission
from app.models.status import Status
from app.models.user import UserRoleAssignment
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
    WorkflowSubmissionLine,
    WorkflowSubmissionTransitionLog,
)
from app.services.error_handler import AppException
from app.services.notification_service import NotificationService
from app.services.status_service import (
    assert_transition_allowed,
    available_transitions,
    initial_status,
    resolve_graph,
)
from app.services.workflow_form_field_defs import collect_field_defs
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
)

logger = logging.getLogger(__name__)

CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,98}$", re.I)


def _as_schema_dict(raw: Any) -> Dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


def default_form_document() -> Dict[str, Any]:
    """A new definition's starting draft: one page, one section, nothing asked yet.

    Shape-valid so the builder can load it, but deliberately NOT publishable -- an empty
    page fails the publish gate, which is the correct answer for a form nobody has
    authored yet.
    """
    return {
        "schemaVersion": FORM_SCHEMA_VERSION,
        "pages": [
            {
                "id": "page-1",
                "title": "Page 1",
                "sections": [{"id": "section-1", "title": "Details", "fields": []}],
            }
        ],
    }


def _assert_document_shape(document: Dict[str, Any]) -> None:
    """A draft save only has to be READABLE, not publishable.

    The publish gate (``validate_form_doc``) requires an answerable page; a draft in
    progress legitimately has none. But an unparseable draft must be rejected here,
    because everything downstream -- the builder, the dynamic list-query columns, the
    publish gate itself -- silently degrades to empty on a document it cannot read.
    """
    try:
        FormDocument.model_validate(document)
    except Exception as exc:  # pydantic ValidationError
        raise AppException(
            status_code=422,
            message=f"This form document cannot be read: {exc}",
            code="form_document_malformed",
        )


def _raise_problems(problems: Sequence[str], code: str, lead: str) -> None:
    """Surface every problem in one message, not just the first.

    ``AppException`` carries a single string, and the frontend's ``extractApiError``
    prefers ``detail`` over ``message`` -- so the whole list goes in ``message`` rather
    than being hidden behind a structured field the toast never shows.
    """
    if not problems:
        return
    count = len(problems)
    noun = "problem" if count == 1 else "problems"
    raise AppException(
        status_code=422,
        message=f"{lead} {count} {noun}: " + " | ".join(problems),
        code=code,
    )


# --------------------------------------------------------------- role gating
#
# Re-keyed from state ids to status KEYS, and from a transition id to
# ``<from_key>:<to_key>``, because keys are stable across a scope fork where ids are not
# -- the same reason reporting groups by key.
#
# **Default-open is preserved on purpose.** The retired gating failed open twice over: a
# missing state allowed, and an empty role list allowed. The status engine fails CLOSED.
# ADR-0013 rule 13 says not to change mechanism and policy in one commit, so F1 re-keys
# the mechanism and keeps the old policy. Which permission system should own a form
# definition is still ungrilled (AC-F1-13), so nothing here reaches into
# ``user_role_permissions``.
#
# There is deliberately no VIEW gate: the retired ``_can_view_state`` had zero callers
# repo-wide, so inventing one during a re-key would be a new authorization rule
# smuggled in as a refactor.


def user_role_ids(db: Session, user_id: str) -> Set[str]:
    rows = db.query(UserRoleAssignment.role_id).filter(UserRoleAssignment.user_id == user_id).all()
    return {r[0] for r in rows}


def _role_gating(schema: Dict[str, Any]) -> Dict[str, Any]:
    """The role map for a published snapshot, or empty.

    Empty for every document F0's builder produces: ``FormDocument`` forbids extra keys,
    so a published document cannot carry one. It is read rather than assumed absent so
    the default-open policy is expressed in code, and so F3 has one place to point at
    whatever storage the permissions decision lands on.
    """
    gating = schema.get("role_gating")
    return gating if isinstance(gating, dict) else {}


def _allows(allowed: Any, role_ids: Set[str]) -> bool:
    """Default-open: no entry, or an empty list, allows everyone."""
    if not isinstance(allowed, Iterable) or isinstance(allowed, (str, bytes)):
        return True
    ids = {str(x) for x in allowed}
    if not ids:
        return True
    return bool(role_ids & ids)


def can_edit_in_status(gating: Dict[str, Any], status_key: Optional[str], role_ids: Set[str]) -> bool:
    edit_roles = (gating.get("edit_role_ids") or {}) if gating else {}
    if not isinstance(edit_roles, dict) or not status_key:
        return True
    return _allows(edit_roles.get(status_key), role_ids)


def can_use_transition(
    gating: Dict[str, Any],
    from_key: Optional[str],
    to_key: Optional[str],
    role_ids: Set[str],
) -> bool:
    transition_roles = (gating.get("transition_role_ids") or {}) if gating else {}
    if not isinstance(transition_roles, dict) or not from_key or not to_key:
        return True
    return _allows(transition_roles.get(f"{from_key}:{to_key}"), role_ids)


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
        pvid = getattr(d, "published_version_id", None)
        if pvid is not None and str(pvid).strip() != "":
            pub_ver = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == pvid).first()
        return {
            "id": d.id,
            "code": d.code,
            "name": d.name,
            "description": d.description,
            "is_active": d.is_active,
            "draft_schema": _as_schema_dict(getattr(d, "draft_schema", None)),
            "published_version_id": d.published_version_id,
            "published_version_number": pub_ver.version_number if pub_ver else None,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        }

    def get_definition(self, definition_id: str) -> WorkflowFormDefinition:
        d = self.db.query(WorkflowFormDefinition).filter(WorkflowFormDefinition.id == definition_id).first()
        if not d:
            raise AppException(
                status_code=404, message="Workflow form not found.", code="not_found"
            )
        return d

    def create_definition(self, code: str, name: str, description: Optional[str], user_id: str) -> WorkflowFormDefinition:
        code = code.strip().lower()
        if not CODE_PATTERN.match(code):
            raise AppException(
                status_code=400,
                message=(
                    "Code must start with alphanumeric and use lowercase letters, "
                    "numbers, dashes, underscores."
                ),
                code="code_invalid",
            )
        if self.db.query(WorkflowFormDefinition).filter(WorkflowFormDefinition.code == code).first():
            raise AppException(
                status_code=409, message="Code already exists.", code="code_duplicate"
            )
        d = WorkflowFormDefinition(
            id=str(uuid.uuid4()),
            code=code,
            name=name.strip(),
            description=description,
            is_active=True,
            draft_schema=default_form_document(),
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
            setattr(d, "name", name.strip())
        if description is not None:
            setattr(d, "description", description)
        if is_active is not None:
            setattr(d, "is_active", is_active)
        if draft_schema is not None:
            _assert_document_shape(draft_schema)
            setattr(d, "draft_schema", draft_schema)
        setattr(d, "updated_at", datetime.utcnow())
        self.db.commit()
        self.db.refresh(d)
        return d

    def publish_definition(self, definition_id: str, user_id: str) -> WorkflowFormVersion:
        d = self.get_definition(definition_id)
        schema = _as_schema_dict(getattr(d, "draft_schema", None))
        _raise_problems(
            validate_form_doc(schema),
            "form_document_invalid",
            "This form cannot be published until you fix",
        )
        max_ver = (
            self.db.query(func.max(WorkflowFormVersion.version_number))
            .filter(WorkflowFormVersion.definition_id == d.id)
            .scalar()
        )
        next_ver = (max_ver or 0) + 1
        v = WorkflowFormVersion(
            id=str(uuid.uuid4()),
            definition_id=str(getattr(d, "id", "") or ""),
            version_number=next_ver,
            schema=schema,
            created_by_user_id=user_id,
        )
        self.db.add(v)
        self.db.flush()
        setattr(d, "published_version_id", getattr(v, "id", None))
        setattr(d, "updated_at", datetime.utcnow())
        self.db.commit()
        self.db.refresh(v)
        return v

    def preview(self, definition_id: str, source: str = "draft") -> Tuple[Dict[str, Any], str]:
        d = self.get_definition(definition_id)
        if source == "published":
            pvid = getattr(d, "published_version_id", None)
            if pvid is None or str(pvid).strip() == "":
                raise AppException(
                    status_code=400,
                    message="This form has no published version yet.",
                    code="not_published",
                )
            v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == pvid).first()
            if not v:
                raise AppException(
                    status_code=404,
                    message="The published version of this form is missing.",
                    code="version_missing",
                )
            return _as_schema_dict(getattr(v, "schema", None)), "published"
        return _as_schema_dict(getattr(d, "draft_schema", None)), "draft"

    def status_graph(self, definition_id: str) -> Dict[str, Any]:
        """The statuses and edges in force for one definition.

        What the builder draws instead of the retired embedded state machine. It reports
        whether the definition has forked, because that is the difference between
        editing this form's graph and editing every unforked form's graph.
        """
        d = self.get_definition(definition_id)
        graph = resolve_graph(self.db, WORKFLOW_SUBMISSION_ENTITY_TYPE, str(d.id))
        return {
            "definition_id": d.id,
            "is_fork": graph.is_fork,
            "nodes": [
                {
                    "id": s.id,
                    "key": s.key,
                    "label": s.label,
                    "color_hex": s.color_hex,
                    "sort_order": s.sort_order,
                    "is_initial": s.is_initial,
                    "is_terminal": s.is_terminal,
                    "is_active": s.is_active,
                }
                for s in graph.statuses
            ],
            "edges": [
                {
                    "id": t.id,
                    "from_status_id": t.from_status_id,
                    "to_status_id": t.to_status_id,
                    "label": t.label,
                    "trigger_mode": t.trigger_mode,
                }
                for t in graph.transitions
            ],
        }

    def delete_definition(self, definition_id: str) -> None:
        d = self.get_definition(definition_id)
        n = self.db.query(WorkflowSubmission).filter(WorkflowSubmission.definition_id == d.id).count()
        if n:
            raise AppException(
                status_code=409,
                message=f"Cannot delete: {n} submission(s) exist. Remove submissions first.",
                code="definition_in_use",
            )
        self.db.delete(d)
        self.db.commit()

    # --- submissions ---

    def list_submissions(
        self,
        page: int = 1,
        limit: int = 50,
        definition_id: Optional[str] = None,
        status_key: Optional[str] = None,
        query: Optional[str] = None,
        sort_field: str = "updated_at",
        sort_dir: str = "desc",
        advanced_filter_clause: Optional[Any] = None,
    ) -> Dict[str, Any]:
        q = self.db.query(WorkflowSubmission).options(
            joinedload(WorkflowSubmission.lines),
            joinedload(WorkflowSubmission.definition),
            joinedload(WorkflowSubmission.status),
        )
        wanted_key = (status_key or "").strip() or None
        # Filtering, quick search and sorting all reach the status row. Join once: a
        # second join to the same table would need an alias and silently multiply rows.
        needs_status = bool(wanted_key) or bool(query and query.strip()) or sort_field == "status_key"
        if needs_status:
            q = q.join(Status, WorkflowSubmission.status_id == Status.id)

        filters = []
        if definition_id:
            filters.append(WorkflowSubmission.definition_id == definition_id)
        if wanted_key:
            filters.append(Status.key == wanted_key)
        if query and query.strip():
            like = f"%{query.strip()}%"
            q = q.outerjoin(
                WorkflowFormDefinition,
                WorkflowSubmission.definition_id == WorkflowFormDefinition.id,
            )
            filters.append(
                or_(
                    Status.key.ilike(like),
                    Status.label.ilike(like),
                    WorkflowFormDefinition.name.ilike(like),
                    WorkflowFormDefinition.code.ilike(like),
                )
            )
        if advanced_filter_clause is not None:
            filters.append(advanced_filter_clause)
        if filters:
            q = q.filter(and_(*filters))

        sort_map = {
            "status_key": Status.key,
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
                    "from_status_id": lg.from_status_id,
                    "to_status_id": lg.to_status_id,
                    # Keys as well as ids: the frontend may not render a UUID.
                    "from_status_key": lg.from_status_key,
                    "to_status_key": lg.to_status_key,
                    "status_transition_id": lg.status_transition_id,
                    "remark": lg.remark,
                    "user_id": lg.user_id,
                    "created_at": lg.created_at,
                }
                for lg in sorted(s.transition_logs or [], key=lambda x: x.created_at or datetime.min)
            ]
        def_name: Optional[str] = None
        def_code: Optional[str] = None
        if getattr(s, "definition", None) is not None:
            defn = s.definition
            def_name = str(getattr(defn, "name", "") or "") or None
            def_code = str(getattr(defn, "code", "") or "") or None
        else:
            d = (
                self.db.query(WorkflowFormDefinition)
                .filter(WorkflowFormDefinition.id == s.definition_id)
                .first()
            )
            if d:
                def_name = str(getattr(d, "name", "") or "") or None
                def_code = str(getattr(d, "code", "") or "") or None

        form_schema: Optional[Dict[str, Any]] = None
        form_version_number: Optional[int] = None
        if include_form_schema:
            v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == s.version_id).first()
            if v:
                form_schema = _as_schema_dict(getattr(v, "schema", None))
                vn = getattr(v, "version_number", None)
                form_version_number = int(vn) if isinstance(vn, (int, float)) else None

        return {
            "id": s.id,
            "definition_id": s.definition_id,
            "version_id": s.version_id,
            "status_id": s.status_id,
            "status_key": s.status_key,
            "status_label": s.status_label,
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
            raise AppException(
                status_code=404, message="Submission not found.", code="not_found"
            )
        return s

    # --- answers ---

    def _published_version(self, definition: WorkflowFormDefinition) -> WorkflowFormVersion:
        pvid = getattr(definition, "published_version_id", None)
        if pvid is None or str(pvid).strip() == "":
            raise AppException(
                status_code=400,
                message="This form has no published version to submit against.",
                code="not_published",
            )
        v = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == pvid).first()
        if not v:
            raise AppException(
                status_code=400,
                message="The published version of this form is missing.",
                code="version_missing",
            )
        return v

    def _clean_answers(self, schema: Dict[str, Any], header_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validated answers, ready to store. Raises 422 listing every field problem."""
        clean, errors = validate_submission(schema, header_data or {})
        _raise_problems(
            [f"{key}: {message}" for key, message in errors.items()],
            "form_answers_invalid",
            "This submission cannot be saved until you fix",
        )
        return clean

    def _assert_known_line_groups(
        self, schema: Dict[str, Any], lines_payload: List[Dict[str, Any]]
    ) -> None:
        """Line rows must name a repeater or table that exists in the document.

        Preserved from the retired validator: a row filed under an unknown group is
        invisible to every grid and export, so it must be rejected rather than stored.
        """
        _header, line_groups = collect_field_defs(schema)
        known = {group_key for group_key, _fields in line_groups}
        unknown = sorted(
            {
                str(row.get("line_group_id"))
                for row in lines_payload
                if str(row.get("line_group_id") or "") not in known
            }
        )
        if unknown:
            raise AppException(
                status_code=422,
                message="These line groups do not exist on this form: " + ", ".join(unknown),
                code="line_group_unknown",
            )

    def create_submission(
        self,
        definition_id: str,
        header_data: Dict[str, Any],
        lines: List[Dict[str, Any]],
        user_id: str,
    ) -> WorkflowSubmission:
        d = self.get_definition(definition_id)
        v = self._published_version(d)
        schema = _as_schema_dict(getattr(v, "schema", None))
        lines_payload = [
            {"line_group_id": x["line_group_id"], "row_data": x.get("row_data") or {}}
            for x in lines
        ]
        clean = self._clean_answers(schema, header_data)
        self._assert_known_line_groups(schema, lines_payload)

        # Fail closed: status_id is NOT NULL, so an unseeded graph has no legal value to
        # write, and a 422 naming the missing graph beats an IntegrityError.
        status = initial_status(self.db, WORKFLOW_SUBMISSION_ENTITY_TYPE, str(d.id))

        sub = WorkflowSubmission(
            id=str(uuid.uuid4()),
            definition_id=d.id,
            version_id=v.id,
            status_id=status.id,
            header_data=clean,
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
            raise AppException(
                status_code=400,
                message="The version this submission was made against is missing.",
                code="version_missing",
            )
        schema = _as_schema_dict(getattr(v, "schema", None))

        # Terminality comes from the STATUS GRAPH now. Deriving it from a document that
        # no longer carries states would make it unconditionally false and quietly
        # re-enable editing on closed submissions.
        graph = resolve_graph(self.db, WORKFLOW_SUBMISSION_ENTITY_TYPE, str(s.definition_id))
        current = graph.by_id(str(s.status_id))
        if current is not None and bool(current.is_terminal):
            raise AppException(
                status_code=422,
                message=f"'{current.label}' is a final status; this submission cannot be edited.",
                code="status_terminal",
            )
        roles = user_role_ids(self.db, user_id)
        if not can_edit_in_status(_role_gating(schema), getattr(current, "key", None), roles):
            raise AppException(
                status_code=403,
                message="Your role cannot edit a submission in this status.",
                code="status_edit_forbidden",
            )

        new_header: Dict[str, Any] = _as_schema_dict(getattr(s, "header_data", None))
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
        clean = self._clean_answers(schema, new_header)
        self._assert_known_line_groups(schema, new_lines_payload)
        setattr(s, "header_data", clean)
        setattr(s, "updated_by_user_id", user_id)
        setattr(s, "updated_at", datetime.utcnow())
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
        to_status_id: str,
        remark: Optional[str],
        user_id: str,
    ) -> WorkflowSubmission:
        """Move a submission to another status, if the engine allows it.

        The engine is the authority, not the client and not the schema document: an
        unknown status, a status from another entity's or another definition's graph, a
        deactivated target, a move out of a final status and a move with no declared
        edge are all 422 with their own code.
        """
        s = self.get_submission(submission_id)
        scope_id = str(s.definition_id)
        from_status_id = str(s.status_id)

        edge = assert_transition_allowed(
            self.db,
            WORKFLOW_SUBMISSION_ENTITY_TYPE,
            from_status_id,
            to_status_id,
            scope_id,
        )

        graph = resolve_graph(self.db, WORKFLOW_SUBMISSION_ENTITY_TYPE, scope_id)
        from_status = graph.by_id(from_status_id) if from_status_id else None
        to_status = graph.by_id(to_status_id)
        roles = user_role_ids(self.db, user_id)
        version = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == s.version_id).first()
        gating = _role_gating(_as_schema_dict(getattr(version, "schema", None)))
        if not can_use_transition(
            gating,
            getattr(from_status, "key", None),
            getattr(to_status, "key", None),
            roles,
        ):
            raise AppException(
                status_code=403,
                message="Your role cannot perform this transition.",
                code="status_transition_forbidden",
            )

        setattr(s, "status_id", to_status_id)
        setattr(s, "updated_by_user_id", user_id)
        setattr(s, "updated_at", datetime.utcnow())
        # Written only for an ACCEPTED move: a rejected transition is not history, and
        # logging the attempt would put a status the submission never held into the trail.
        log = WorkflowSubmissionTransitionLog(
            id=str(uuid.uuid4()),
            submission_id=str(getattr(s, "id", "") or ""),
            from_status_id=from_status_id,
            to_status_id=to_status_id,
            status_transition_id=edge.id,
            remark=remark,
            user_id=user_id,
        )
        self.db.add(log)
        self.db.commit()

        # Post-commit and best-effort: the move has already succeeded, so a notification
        # failure must not surface as a 500 for an operation that worked.
        try:
            self._notify_submitter(s, edge, str(getattr(log, "id", "") or ""))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Workflow transition notification failed for %s: %s", s.id, exc)

        self.db.refresh(s)
        return s

    def _notify_submitter(
        self,
        submission: WorkflowSubmission,
        edge: Any,
        log_id: str,
    ) -> None:
        """Tell the person who submitted that their submission moved.

        The retired builder also fanned out to roles named in
        ``schema["notification_rules"]``. That config lived in the state machine this
        slice deletes, so there is nothing left to read; the submitter notification is
        unconditional and survives. Re-introducing a rules engine belongs with whatever
        owns form permissions (AC-F1-13), not here.
        """
        submitter_raw = getattr(submission, "created_by_user_id", None)
        submitter_id = str(submitter_raw) if submitter_raw is not None else ""
        if submitter_id.strip() == "":
            return

        definition = (
            self.db.query(WorkflowFormDefinition)
            .filter(WorkflowFormDefinition.id == submission.definition_id)
            .first()
        )
        sub_id = str(getattr(submission, "id", "") or "")
        def_title = str(getattr(definition, "name", "") or "") if definition is not None else ""
        status_label = submission.status_label or ""
        title = f"Workflow: {def_title or 'Form'} - {getattr(edge, 'label', None) or 'Updated'}"
        NotificationService(self.db).create(
            user_id=submitter_id,
            type="workflow_forms.transition",
            title=title,
            body=f'Your submission {sub_id[:8]}... is now "{status_label}".',
            data={"submission_id": sub_id, "definition_id": str(submission.definition_id)},
            source_entity_type="workflow_submission",
            source_entity_id=sub_id,
            # event_type must fit notifications.event_type (VARCHAR); the log id is
            # unique per accepted transition, so it is the natural idempotency key.
            event_type=f"workflow_forms.tr.{log_id}.submitter",
        )

    def allowed_transitions_for_user(self, submission_id: str, user_id: str) -> List[Dict[str, Any]]:
        """The moves to offer as buttons.

        Resolved through the same graph the guard uses, or a user is shown an action the
        server will refuse.
        """
        s = self.get_submission(submission_id)
        scope_id = str(s.definition_id)
        graph = resolve_graph(self.db, WORKFLOW_SUBMISSION_ENTITY_TYPE, scope_id)
        current = graph.by_id(str(s.status_id))
        edges = available_transitions(
            self.db, WORKFLOW_SUBMISSION_ENTITY_TYPE, str(s.status_id), scope_id
        )
        version = self.db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == s.version_id).first()
        gating = _role_gating(_as_schema_dict(getattr(version, "schema", None)))
        roles = user_role_ids(self.db, user_id)

        out: List[Dict[str, Any]] = []
        for edge in edges:
            target = graph.by_id(str(edge.to_status_id))
            if target is None:
                continue
            if not can_use_transition(
                gating, getattr(current, "key", None), str(target.key), roles
            ):
                continue
            out.append(
                {
                    "id": edge.id,
                    "label": edge.label,
                    "to_status_id": target.id,
                    "to_status_key": target.key,
                    "to_status_label": target.label,
                }
            )
        return out
