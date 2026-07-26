"""Seeds the Project Sales module's configurable defaults.

Everything here is configuration the user can change afterwards, not code. It exists
because a module whose first screen is empty cannot be evaluated: a fresh install must
show a working funnel and a usable set of project types on day one.

Idempotent and additive. It never updates or deletes an existing row, so a team that
renames "Identified" to "Sighted" or deletes a type they do not use keeps their change
across every restart. That is the difference between a seed and a reset.
"""
from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.numbering import DocumentNumberingRule
from app.models.projects import ProjectTemplate, ProjectTemplateRole, ProjectType
from app.models.status import Status, StatusTransition
from app.services.project_reference_service import DEFAULT_TEMPLATE_ROLES

logger = logging.getLogger(__name__)

PROJECT_ENTITY = "project"

# The funnel from the client's process-flow PDF. The terminal rung is "PO Received",
# not "Won": status says what happened, while the commercial outcome is derived, so a
# project with a PO on one scope and a live quotation on another does not read as
# finished (grill finding G1).
DEFAULT_FUNNEL = (
    # (key, label, initial, terminal, stale_after_days)
    ("identified", "Identified", True, False),
    ("registered", "Registered", False, False),
    ("specified", "Specified", False, False),
    ("quoted", "Quoted", False, False),
    ("tendering", "Tendering", False, False),
    ("po_received", "PO Received", False, True),
    ("lost", "Lost", False, True),
    ("dormant", "Dormant", False, True),
)

# Forward edges, plus Lost/Dormant reachable from every live rung. Deliberately NOT a
# fully-connected graph: the point of a configurable funnel is that illegal moves are
# rejected, and "anything to anything" makes the engine decorative.
_LIVE = ("identified", "registered", "specified", "quoted", "tendering")
DEFAULT_EDGES = (
    ("identified", "registered", "Register with developer"),
    ("registered", "specified", "Specified in"),
    ("specified", "quoted", "Quotation sent"),
    ("quoted", "tendering", "Tendering"),
    ("tendering", "po_received", "PO received"),
    ("quoted", "po_received", "PO received"),
    # Backwards, because real pursuits move backwards: a re-spec after losing a
    # tender round is normal and must not require an admin to fix the data.
    ("quoted", "specified", "Re-specify"),
    ("tendering", "quoted", "Re-quote"),
    ("registered", "identified", "Back to identified"),
)

DEFAULT_TYPES = (
    # (code, name, derives_delivery_from_launch, templates)
    ("property_development", "Property Development", True, ("High Rise", "Landed")),
    ("hotel", "Hotel", False, ("New Build", "Refurbishment")),
    ("commercial_fitout", "Commercial Fitout", False, ("Office", "Retail")),
    ("renovation", "Renovation", False, ("Renovation",)),
    ("institutional", "Institutional", False, ("Institutional",)),
)

PROJECT_NUMBERING = {
    "doc_type": "project",
    "prefix_template": "PRJ-",
    "number_digits": 6,
    "start_value": 1,
}


def _uid() -> str:
    return str(uuid.uuid4())


def seed_numbering_rule(db: Session) -> bool:
    """``PRJ-000001`` upward. Prefix, padding and any date segment stay editable.

    ``doc_type`` is unique with no company column, so the sequence is shared across
    companies and codes are globally unique -- Mocha's first project may be PRJ-000247
    (AC-C8, accepted).
    """
    existing = (
        db.query(DocumentNumberingRule)
        .filter(DocumentNumberingRule.doc_type == PROJECT_NUMBERING["doc_type"])
        .first()
    )
    if existing:
        return False
    db.add(
        DocumentNumberingRule(
            id=_uid(),
            doc_type=PROJECT_NUMBERING["doc_type"],
            enabled=True,
            prefix_template=PROJECT_NUMBERING["prefix_template"],
            number_digits=PROJECT_NUMBERING["number_digits"],
            next_value=PROJECT_NUMBERING["start_value"],
            start_value=PROJECT_NUMBERING["start_value"],
            reset_policy="none",
        )
    )
    db.flush()
    return True


def seed_default_funnel(db: Session) -> int:
    """The DEFAULT graph for ``project``. Templates fork it if they need to differ.

    Skipped entirely once any default-scope project status exists, rather than
    per-status: adding back a rung the team deliberately deleted every time the app
    restarts would be worse than not seeding at all.
    """
    already = (
        db.query(func.count(Status.id))
        .filter(Status.entity_type == PROJECT_ENTITY, Status.scope_id.is_(None))
        .scalar()
    )
    if already:
        return 0

    by_key: Dict[str, Status] = {}
    for index, (key, label, initial, terminal) in enumerate(DEFAULT_FUNNEL):
        row = Status(
            id=_uid(),
            entity_type=PROJECT_ENTITY,
            scope_id=None,
            key=key,
            label=label,
            sort_order=index,
            is_initial=initial,
            is_terminal=terminal,
            is_default=initial,
        )
        db.add(row)
        by_key[key] = row
    db.flush()

    created = len(by_key)
    for from_key, to_key, label in DEFAULT_EDGES:
        db.add(
            StatusTransition(
                id=_uid(),
                entity_type=PROJECT_ENTITY,
                scope_id=None,
                from_status_id=by_key[from_key].id,
                to_status_id=by_key[to_key].id,
                label=label,
                trigger_mode="manual",
            )
        )
    # Every live rung can end in Lost or Dormant. Losing at the identified stage is
    # as real as losing at tender.
    for from_key in _LIVE:
        for terminal_key, label in (("lost", "Mark lost"), ("dormant", "Mark dormant")):
            db.add(
                StatusTransition(
                    id=_uid(),
                    entity_type=PROJECT_ENTITY,
                    scope_id=None,
                    from_status_id=by_key[from_key].id,
                    to_status_id=by_key[terminal_key].id,
                    label=label,
                    trigger_mode="manual",
                )
            )
    db.flush()
    return created


def seed_types_and_templates(db: Session, company_id: str) -> int:
    """Per company, because types are company-scoped configuration.

    Half the project names already in the system are hotels, fitouts and renovations,
    which is why type is configurable rather than assumed to be a property
    development (AC-C2 deviation).

    Skipped wholesale once the company has ANY project type, not per type. A
    create-if-missing loop would bring back "Institutional" on every restart after
    someone deliberately deleted it, and nobody would connect the reappearance to a
    deploy. Same guard shape as the funnel, for the same reason.
    """
    if (
        db.query(func.count(ProjectType.id))
        .filter(ProjectType.company_id == company_id)
        .scalar()
    ):
        return 0

    created = 0
    for code, name, derives, template_names in DEFAULT_TYPES:
        project_type = (
            db.query(ProjectType)
            .filter(
                ProjectType.company_id == company_id,
                func.lower(ProjectType.code) == code,
            )
            .first()
        )
        if project_type is None:
            project_type = ProjectType(
                id=_uid(),
                company_id=company_id,
                name=name,
                code=code,
                derives_delivery_from_launch=derives,
                sort_order=created,
            )
            db.add(project_type)
            db.flush()
            created += 1

        for template_name in template_names:
            template = (
                db.query(ProjectTemplate)
                .filter(
                    ProjectTemplate.company_id == company_id,
                    ProjectTemplate.type_id == project_type.id,
                    func.lower(ProjectTemplate.name) == template_name.lower(),
                )
                .first()
            )
            if template is None:
                template = ProjectTemplate(
                    id=_uid(),
                    company_id=company_id,
                    type_id=project_type.id,
                    name=template_name,
                )
                db.add(template)
                db.flush()

            # The four roles the client named: decision maker, influencer, info
            # provider (the "whistle blower"), and architect.
            existing_roles = {
                r.name.lower()
                for r in db.query(ProjectTemplateRole)
                .filter(ProjectTemplateRole.template_id == template.id)
                .all()
            }
            for order, role_name in enumerate(DEFAULT_TEMPLATE_ROLES):
                if role_name.lower() in existing_roles:
                    continue
                db.add(
                    ProjectTemplateRole(
                        id=_uid(),
                        company_id=company_id,
                        template_id=template.id,
                        name=role_name,
                        sort_order=order,
                    )
                )
            db.flush()
    return created


def _company_ids(db: Session) -> List[str]:
    from app.models.company import Company

    return [row[0] for row in db.query(Company.id).filter(Company.is_active.is_(True)).all()]


def run(db: Session, company_id: Optional[str] = None) -> Dict[str, int]:
    """Seed everything. Safe to call on every boot."""
    summary = {"numbering": 0, "statuses": 0, "types": 0}
    summary["numbering"] = 1 if seed_numbering_rule(db) else 0
    summary["statuses"] = seed_default_funnel(db)

    companies = [company_id] if company_id else _company_ids(db)
    for cid in companies:
        # Types are company-scoped and the auto-filter would hide another company's
        # rows from this query, making the seeder re-create them on every boot.
        from app.models.base import company_scope

        with company_scope(db, frozenset({cid})):
            summary["types"] += seed_types_and_templates(db, cid)

    db.commit()
    if any(summary.values()):
        logger.info("Project Sales seed: %s", summary)
    return summary
