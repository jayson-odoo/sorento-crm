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
from app.services.workflow_submission_derived_status import (
    assert_derivation_config,
    assert_manual_header_move_allowed,
    definition_derives_status,
    derived_pair_ids,
    recompute_submission_status,
)
from app.services.workflow_submission_line_disposition import (
    assert_disposition_allowed,
)
from app.services.workflow_submission_line_status_graph import (
    WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
    assert_lines_replaceable,
)
from app.services.workflow_submission_sla import (
    SUBMISSION_CREATED_EVENT,
    emit_submission_event,
    submission_status_event,
)
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


def user_role_ids(db: Session, user_id: Optional[str]) -> Set[str]:
    """The roles a mover holds, or none at all when there is no mover.

    None is a real caller now: a portal edit is made by a contact, who holds no roles.
    Returned early rather than queried, because ``user_id == None`` compiles to
    ``user_id IS NULL`` and would match every assignment row an orphaned import left
    behind.
    """
    if not user_id:
        return set()
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
            # The builder has to be able to READ the derivation config it just saved, and
            # this dict is built by hand: a field the response model merely inherits never
            # reaches the frontend, which reads as a toggle that refuses to stay on.
            "derives_status_from_lines": bool(
                getattr(d, "derives_status_from_lines", False)
            ),
            "derived_open_status_key": getattr(d, "derived_open_status_key", None),
            "derived_resolved_status_key": getattr(
                d, "derived_resolved_status_key", None
            ),
            # Same reason as the derivation trio: this dict is built by hand, so the
            # builder's portal toggle would read as off however it was saved if the two
            # columns were merely inherited by the response model.
            "portal_submittable": bool(getattr(d, "portal_submittable", False)),
            "portal_party_kinds": list(getattr(d, "portal_party_kinds", None) or []),
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
        derives_status_from_lines: Optional[bool] = None,
        derived_open_status_key: Optional[str] = None,
        derived_resolved_status_key: Optional[str] = None,
        portal_submittable: Optional[bool] = None,
        portal_party_kinds: Optional[List[str]] = None,
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
        if portal_submittable is not None:
            setattr(d, "portal_submittable", bool(portal_submittable))
        if portal_party_kinds is not None:
            # Normalised on the way in so the overlap the gate performs is a plain set
            # intersection: contact_access_types.code is lowercase, and a stray "Dealer"
            # here would narrow the form to nobody while looking correct in the builder.
            setattr(
                d,
                "portal_party_kinds",
                sorted(
                    {
                        str(kind).strip().lower()
                        for kind in portal_party_kinds
                        if str(kind).strip()
                    }
                ),
            )
        derivation_fields = (
            "derives_status_from_lines",
            "derived_open_status_key",
            "derived_resolved_status_key",
        )
        previous = {field: getattr(d, field, None) for field in derivation_fields}
        if derives_status_from_lines is not None:
            setattr(d, "derives_status_from_lines", derives_status_from_lines)
        if derived_open_status_key is not None:
            setattr(d, "derived_open_status_key", derived_open_status_key.strip() or None)
        if derived_resolved_status_key is not None:
            setattr(
                d, "derived_resolved_status_key", derived_resolved_status_key.strip() or None
            )
        # Validated at SAVE, where the admin can still fix it. Both rules are permanent
        # once a submission exists: an open key that is not the graph's starting state
        # strands every submission outside the derived pair, and a terminal resolved key
        # makes reopening unreachable.
        try:
            assert_derivation_config(self.db, d)
        except AppException:
            # Put the row back as it was, and FLUSH it back: the validation itself runs a
            # query, so autoflush has already written the refused values. Restoring only
            # in memory would leave the database holding them until the caller happened to
            # roll back. Rolling the whole transaction back here is not an option either,
            # since it would discard unrelated work the caller has not committed.
            for field, value in previous.items():
                setattr(d, field, value)
            self.db.flush()
            raise
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

    def _line_out(self, ln: WorkflowSubmissionLine) -> Dict[str, Any]:
        """One line row, as both the submission payload and the line routes report it.

        One serializer, so a line read and the same line inside its submission can never
        disagree about what it holds.
        """
        return {
            "id": ln.id,
            "line_group_id": ln.line_group_id,
            "sort_order": ln.sort_order,
            "row_data": ln.row_data or {},
            # NULL on every line of a form that does not use line statuses, which is
            # every form today. Keys as well as the id: the frontend may not render a
            # UUID.
            "status_id": ln.status_id,
            "status_key": ln.status_key,
            "status_label": ln.status_label,
            "disposition": ln.disposition,
            "disposition_reason": ln.disposition_reason,
        }

    def _submission_out(
        self,
        s: WorkflowSubmission,
        include_logs: bool = True,
        include_form_schema: bool = False,
    ) -> Dict[str, Any]:
        lines = [self._line_out(ln) for ln in (s.lines or [])]
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
        user_id: Optional[str] = None,
        *,
        respondent_contact_id: Optional[str] = None,
        source_entity_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
        respond_inbox_url: Optional[str] = None,
    ) -> WorkflowSubmission:
        """Create a submission against the definition's PUBLISHED version.

        One creation path for both origins. ``user_id`` is None for a portal filing and
        the four keyword arguments are None for an internal one, and neither may be
        inferred from the other: stamping a service account on a customer's filing would
        put a real person's name on it in the audit trail, and stamping a contact on a
        staff filing would attribute it to whoever the form happens to be about.

        The portal goes through here rather than building its row directly, which is
        what buys it F0 answer validation, the publish gate, the version pin and the
        ``submission_created`` SLA emit - all of which a hand-rolled insert skips, for
        exactly the submissions nobody at Sorento typed.
        """
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
            respondent_contact_id=respondent_contact_id,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
            # In the creating INSERT, so the admin chat panel has a link the first time
            # anyone opens the row. Never backfilled and never taken from the payload.
            respond_inbox_url=respond_inbox_url,
        )
        self.db.add(sub)
        self.db.flush()
        line_status_id = self._initial_line_status_id(d)
        for i, row in enumerate(lines):
            self.db.add(
                WorkflowSubmissionLine(
                    id=str(uuid.uuid4()),
                    submission_id=sub.id,
                    line_group_id=row["line_group_id"],
                    sort_order=row.get("sort_order", i),
                    row_data=row.get("row_data") or {},
                    status_id=line_status_id,
                )
            )
        self.db.flush()
        derived = recompute_submission_status(self.db, sub)
        self.db.commit()
        self.db.refresh(sub)

        # Post-commit, because ``_start_for_config`` commits unconditionally: emitting
        # before this line would commit a half-built submission.
        #
        # A deriving definition has no other reachable start event -- every manual move
        # into its derived pair is refused, and a submission is created on the open rung
        # with no transition -- so creation is where its clock begins.
        emit_submission_event(
            self.db, sub, SUBMISSION_CREATED_EVENT, actor_user_id=user_id
        )
        if derived:
            # Only when the header ACTUALLY moved. Reachable when every line arrives
            # already decided; a recompute that changed nothing must fire nothing, or a
            # stage resolves on the strength of a submission nobody has worked on.
            self._emit_derived_status_event(sub)
        return sub

    def _emit_derived_status_event(self, submission: WorkflowSubmission) -> None:
        """Fire the SLA event for a header move DERIVATION made.

        ``actor_user_id`` is None on purpose. Somebody decided a LINE, and nobody moved
        the header -- the transition log records the same absence -- so passing the line
        decider through would credit them with a move they did not make (AC-F1a-29).
        """
        emit_submission_event(
            self.db,
            submission,
            submission_status_event(submission.status_key),
            actor_user_id=None,
        )

    def _initial_line_status_id(
        self, definition: Optional[WorkflowFormDefinition]
    ) -> Optional[str]:
        """The status a new line starts on, or None for a definition that never opted in.

        None keeps today's behaviour bit for bit: most forms have lines that are just
        data, so stamping them would mean seeding a line graph for every form with a
        repeater. A DERIVING definition is the opposite case -- lines that arrive with no
        status could never resolve its header -- and the value comes from the LINE graph
        resolved for this definition, never from the header's.
        """
        if definition is None or not definition_derives_status(definition):
            return None
        return str(
            initial_status(
                self.db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, str(definition.id)
            ).id
        )

    def update_submission(
        self,
        submission_id: str,
        header_data: Optional[Dict[str, Any]],
        lines: Optional[List[Dict[str, Any]]],
        user_id: Optional[str] = None,
    ) -> WorkflowSubmission:
        """Replace a submission's answers, and optionally its lines.

        ``user_id`` is None for a portal edit: nobody logged in, so
        ``updated_by_user_id`` stays NULL rather than naming a service account, and the
        role gate reads an empty role set (which the default-open policy allows).
        """
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
            # Replacing lines is a DELETE plus re-insert with fresh UUIDs, so it would
            # silently destroy every line status and disposition. Refused while any line
            # carries a decision; a header-only edit (lines is None) is untouched by this.
            assert_lines_replaceable(self.db, s)
            line_status_id = self._initial_line_status_id(
                self.db.query(WorkflowFormDefinition)
                .filter(WorkflowFormDefinition.id == s.definition_id)
                .first()
            )
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
                        status_id=line_status_id,
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
        self.db.flush()
        derived = False
        if lines is not None:
            # Replaced lines are a new population, which is one of the reachable ways a
            # resolved submission reopens (a decided line can never leave its terminal
            # rung). Derivation recomputes from whatever it finds rather than assuming
            # which API produced it.
            derived = recompute_submission_status(self.db, s)
        self.db.commit()
        self.db.refresh(s)
        # Post-commit and only on an ACTUAL header move: a line replacement that leaves
        # the header where it was must not touch its clock.
        if derived:
            self._emit_derived_status_event(s)
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

        A deriving definition adds one more refusal, and only one: a move INTO either of
        the two rungs derivation owns. A move back out is permitted, which is precisely
        what lets a resolved submission still be closed by hand.
        """
        s = self.get_submission(submission_id)
        scope_id = str(s.definition_id)
        from_status_id = str(s.status_id)

        assert_manual_header_move_allowed(
            self.db,
            self.get_definition(scope_id),
            from_status_id,
            to_status_id,
        )

        edge = assert_transition_allowed(
            self.db,
            WORKFLOW_SUBMISSION_ENTITY_TYPE,
            from_status_id,
            to_status_id,
            scope_id,
        )

        graph = resolve_graph(self.db, WORKFLOW_SUBMISSION_ENTITY_TYPE, scope_id)

        # S4a AC-M4, same reasoning as the complaint path: the resolve rides
        # emit_form_event, which swallows twice and after the commit, so the only place
        # an unattributed overdue stage can be refused is here, before anything moves.
        # Form-SLA resolve_event names status KEYS, so the id has to be resolved first.
        from app.services.sla_waiting_service import assert_case_transition_attributed

        _target_status = graph.by_id(to_status_id)
        assert_case_transition_attributed(
            self.db,
            WORKFLOW_SUBMISSION_ENTITY_TYPE,
            str(submission_id),
            getattr(_target_status, "key", None),
        )
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
        # Read before the commit expires the row; the emit below needs the key, and
        # re-reading it would reload a status the SLA emit may have committed over.
        to_status_key = str(getattr(to_status, "key", "") or "")
        self.db.commit()

        # Post-commit and best-effort: the move has already succeeded, so a notification
        # failure must not surface as a 500 for an operation that worked.
        log_id = str(getattr(log, "id", "") or "")
        try:
            self._notify_submitter(s, edge, log_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Workflow transition notification failed for %s: %s", s.id, exc)

        # The OTHER origin, and the one with a person waiting. ``_notify_submitter``
        # reads created_by_user_id, which is NULL for every portal filing, so it returns
        # early: without this line a customer's claim can be approved or rejected and the
        # only party told is nobody (AC-F2c-8). A contact is reached by a different path
        # entirely, because notifications.user_id is NOT NULL and has no foreign key, so
        # writing a contact id there succeeds and addresses nobody.
        self._notify_respondent_contact(s, edge, log_id)

        # The SLA event for a MANUAL move, so it carries its mover: a human decided
        # this, and the tracker's responded_by / resolved_by must say who.
        emit_submission_event(
            self.db,
            s,
            submission_status_event(to_status_key),
            actor_user_id=user_id,
        )

        self.db.refresh(s)
        return s

    def _notify_respondent_contact(
        self,
        submission: WorkflowSubmission,
        edge: Any,
        log_id: str,
    ) -> None:
        """Tell the contact a portal-filed submission is about that it moved.

        Best-effort, and the rollback is part of that: a notification that fails
        mid-flush leaves the session unusable, so the ``db.refresh`` two lines below
        would raise PendingRollbackError - a 500 for a move that was already committed.
        A submission that cannot be approved because a customer's WhatsApp window is
        shut is the least acceptable failure this can produce.

        Local import so the notification stack is not pulled in at module import time,
        mirroring every other side-effect call site in this service.
        """
        try:
            from app.services.workflow_submission_notify import (
                notify_submission_status_change,
            )

            notify_submission_status_change(
                self.db,
                submission,
                transition_label=getattr(edge, "label", None),
                event_type=f"workflow_forms.tr.{log_id}.contact",
            )
        except Exception as exc:  # noqa: BLE001
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001 - nothing left to salvage
                logger.warning("Session rollback failed after contact notification")
            logger.warning(
                "Workflow transition contact notification failed for %s: %s",
                submission.id,
                exc,
            )

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
        server will refuse. That includes the derived pair: offering a move the derivation
        guard rejects is how a user learns the product is broken.
        """
        s = self.get_submission(submission_id)
        scope_id = str(s.definition_id)
        definition = self.get_definition(scope_id)
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
            if not self._manual_header_move_offerable(
                definition, str(s.status_id), str(target.id)
            ):
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

    def _manual_header_move_offerable(
        self,
        definition: WorkflowFormDefinition,
        from_status_id: str,
        to_status_id: str,
    ) -> bool:
        """False for a move ``apply_transition`` would refuse as derived.

        A misconfigured definition still raises out of here rather than quietly showing
        no buttons, which would read as a form whose workflow simply ended.
        """
        pair = derived_pair_ids(self.db, definition)
        if pair is None:
            return True
        return from_status_id not in pair and to_status_id not in pair

    # --- lines ---

    def get_line(self, line_id: str) -> WorkflowSubmissionLine:
        line = (
            self.db.query(WorkflowSubmissionLine)
            .filter(WorkflowSubmissionLine.id == line_id)
            .first()
        )
        if not line:
            raise AppException(
                status_code=404, message="Submission line not found.", code="not_found"
            )
        return line

    def allowed_line_transitions(self, line_id: str) -> List[Dict[str, Any]]:
        """The decisions to offer as buttons on one line.

        Resolved through the same graph ``apply_line_transition`` guards with, or a user
        is shown a decision the server will refuse.

        No user parameter and no role gate, unlike the header's twin: the retired role
        gating is keyed to HEADER statuses, and inventing a per-line rule here would be a
        new authorization rule smuggled in as a list endpoint.

        Empty for a line with no status (a form that never opted in) and for a line
        stranded off its graph. Both are "no decision is available", which is what the
        caller has to render, and neither is an error to read.
        """
        line = self.get_line(line_id)
        submission = line.submission
        status_id = getattr(line, "status_id", None)
        if submission is None or status_id is None:
            return []
        scope_id = str(submission.definition_id)
        graph = resolve_graph(self.db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, scope_id)
        out: List[Dict[str, Any]] = []
        for edge in available_transitions(
            self.db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, str(status_id), scope_id
        ):
            target = graph.by_id(str(edge.to_status_id))
            if target is None:
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

    def apply_line_transition(
        self,
        line_id: str,
        to_status_id: str,
        user_id: str,
    ) -> WorkflowSubmissionLine:
        """Decide one line, if the engine allows it, then re-derive the header.

        The same authority as a header move: one engine, not a second per-line rule set,
        so a line's legal moves are configuration rather than code. The graph is the LINE
        graph resolved for the submission's definition, which is why a status from the
        header's graph is rejected even though the two share keys.

        ``user_id`` is the mover. It is not recorded on the line: the table has no
        attribution column, and the derived header move that may follow deliberately
        carries no user at all (nobody made that move). See AC-F1a-29.

        No line-level role gate. The retired role gating is keyed to HEADER statuses, and
        inventing a per-line rule during this slice would be a new authorization rule
        smuggled in as a feature.
        """
        line = self.get_line(line_id)
        submission = line.submission
        if submission is None:
            raise AppException(
                status_code=404, message="Submission line not found.", code="not_found"
            )
        from_status_id = getattr(line, "status_id", None)
        if from_status_id is None:
            # NULL is not a rung of any graph, so there is nothing to move from. Failing
            # closed with the same code as a stranded line keeps one answer for one
            # question: this record is not on the graph you are moving it through.
            raise AppException(
                status_code=422,
                message=(
                    "This line has no status, so it cannot be moved. Its form does not "
                    "use line-level statuses."
                ),
                code="status_not_in_graph",
            )

        assert_transition_allowed(
            self.db,
            WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
            str(from_status_id),
            to_status_id,
            str(submission.definition_id),
        )

        setattr(line, "status_id", to_status_id)
        self.db.flush()
        # The header follows its lines. No row is written here for the line itself:
        # workflow_submission_transition_logs is the HEADER's companion log, and a line
        # move logged there would put a status the submission never held into its trail.
        derived = recompute_submission_status(self.db, submission)
        self.db.commit()
        self.db.refresh(line)
        # Post-commit, and only when the header MOVED. ``recompute_submission_status``
        # runs on every line decision and returns False when the answer is unchanged, so
        # emitting per recompute would resolve a submission on the strength of its first
        # decided line.
        if derived:
            self._emit_derived_status_event(submission)
        return line

    def set_line_disposition(
        self,
        line_id: str,
        disposition: Optional[str],
        user_id: str,
        disposition_reason: Optional[str] = None,
    ) -> WorkflowSubmissionLine:
        """Record how a line will be settled, or clear it.

        Validated against the ACTIVE options of the bound lookup set. Called explicitly
        rather than left to the flush listener, which only ``app.main`` installs.

        Recording a disposition is NOT a decision: it must not move the line, so it
        cannot move the header either. If it did, a submission could resolve on lines
        nobody ever approved.
        """
        line = self.get_line(line_id)
        value = (disposition or "").strip() or None
        assert_disposition_allowed(self.db, value)
        setattr(line, "disposition", value)
        if disposition_reason is not None:
            setattr(line, "disposition_reason", disposition_reason.strip() or None)
        if value is None:
            # A cleared disposition has no reason to explain.
            setattr(line, "disposition_reason", None)
        self.db.commit()
        self.db.refresh(line)
        return line
