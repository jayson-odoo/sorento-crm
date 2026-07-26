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
from app.models.lookup import LookupOption, LookupSet
from app.models.status import Status, StatusTransition
from app.models.projects import LEAD_DISQUALIFY_REASON_SET_KEY
from app.services.project_reference_service import DEFAULT_TEMPLATE_ROLES

logger = logging.getLogger(__name__)

PROJECT_ENTITY = "project"
PROJECT_TASK_ENTITY = "project_task"
PROJECT_LEAD_ENTITY = "project_lead"

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

# Ecohub's five task rungs, ported as-is. Escalate was missing from the first draft of
# this plan entirely, which is exactly the kind of gap a reference pass catches: without
# it, a blocked task can only be "Stuck", and the difference between "I cannot proceed"
# and "I have handed this to someone senior" is lost.
DEFAULT_TASK_STATUSES = (
    # (key, label, initial, terminal)
    ("not_started", "Not Started", True, False),
    ("in_progress", "In Progress", False, False),
    ("escalate", "Escalate", False, False),
    ("stuck", "Stuck", False, False),
    ("done", "Done", False, True),
)

# A task gets escalated or stuck at ANY point, not at one designated moment, so both are
# reachable from every live rung and both lead back. Done is terminal: reopening is an
# admin choice (clear the terminal flag, add the edge), not the default.
_TASK_LIVE = ("not_started", "in_progress", "escalate", "stuck")
DEFAULT_TASK_EDGES = (
    ("not_started", "in_progress", "Start"),
    ("in_progress", "done", "Mark done"),
    ("escalate", "in_progress", "Taken back"),
    ("stuck", "in_progress", "Unblocked"),
    ("escalate", "done", "Resolved by escalation"),
    ("stuck", "done", "Resolved while stuck"),
    ("not_started", "done", "Not needed after all"),
)

# The lead funnel (AC-O7). Deliberately SHORT: a lead is a rumour being firmed up, and
# a five-rung qualification pipeline for hearsay is ceremony nobody maintains. Both
# terminal rungs are real endings -- qualified leads do not come back, they become
# projects, and one lead may become several (AC-O5).
DEFAULT_LEAD_STATUSES = (
    # (key, label, initial, terminal)
    ("new", "New", True, False),
    ("contacted", "Contacted", False, False),
    ("qualifying", "Qualifying", False, False),
    ("qualified", "Qualified", False, True),
    ("disqualified", "Disqualified", False, True),
)

_LEAD_LIVE = ("new", "contacted", "qualifying")
DEFAULT_LEAD_EDGES = (
    ("new", "contacted", "Contacted"),
    ("contacted", "qualifying", "Start qualifying"),
    ("new", "qualifying", "Start qualifying"),
    ("qualifying", "qualified", "Qualified"),
    ("contacted", "qualified", "Qualified"),
)

# Seeded starting points for the disqualification reason lookup (AC-O6). A free-text
# reason cannot be reported on: "not interested" typed nine ways is nine buckets.
DEFAULT_LEAD_DISQUALIFY_REASONS = (
    ("no_project", "No such project"),
    ("wrong_segment", "Not our segment"),
    ("competitor_locked", "Competitor already specified"),
    ("budget", "Budget too low"),
    ("duplicate", "Duplicate of an existing lead or project"),
    ("no_response", "No response from the contact"),
)

LEAD_NUMBERING = {
    "doc_type": "project_lead",
    "prefix_template": "LEAD-",
    "number_digits": 6,
    "start_value": 1,
}

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


def seed_default_task_graph(db: Session) -> int:
    """The DEFAULT graph for ``project_task`` (AC-N4).

    Same wholesale guard as the project funnel: skipped once any default-scope task
    status exists, so a team that renamed or pruned a rung keeps their change.
    """
    already = (
        db.query(func.count(Status.id))
        .filter(Status.entity_type == PROJECT_TASK_ENTITY, Status.scope_id.is_(None))
        .scalar()
    )
    if already:
        return 0

    by_key: Dict[str, Status] = {}
    for index, (key, label, initial, terminal) in enumerate(DEFAULT_TASK_STATUSES):
        row = Status(
            id=_uid(),
            entity_type=PROJECT_TASK_ENTITY,
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

    for from_key, to_key, label in DEFAULT_TASK_EDGES:
        db.add(
            StatusTransition(
                id=_uid(),
                entity_type=PROJECT_TASK_ENTITY,
                scope_id=None,
                from_status_id=by_key[from_key].id,
                to_status_id=by_key[to_key].id,
                label=label,
                trigger_mode="manual",
            )
        )
    # Escalate and Stuck reachable from every live rung, and from each other: a task
    # that has been stuck a fortnight is exactly what gets escalated.
    for from_key in _TASK_LIVE:
        for to_key, label in (("escalate", "Escalate"), ("stuck", "Mark stuck")):
            if from_key == to_key:
                continue
            db.add(
                StatusTransition(
                    id=_uid(),
                    entity_type=PROJECT_TASK_ENTITY,
                    scope_id=None,
                    from_status_id=by_key[from_key].id,
                    to_status_id=by_key[to_key].id,
                    label=label,
                    trigger_mode="manual",
                )
            )
    db.flush()
    return len(by_key)


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


def seed_lead_numbering_rule(db: Session) -> bool:
    """``LEAD-000001`` upward, its own sequence separate from ``PRJ-``.

    Same global-sequence caveat as the project rule: ``doc_type`` is unique with no
    company column, so lead codes are globally unique across companies.
    """
    existing = (
        db.query(DocumentNumberingRule)
        .filter(DocumentNumberingRule.doc_type == LEAD_NUMBERING["doc_type"])
        .first()
    )
    if existing:
        return False
    db.add(
        DocumentNumberingRule(
            id=_uid(),
            doc_type=LEAD_NUMBERING["doc_type"],
            enabled=True,
            prefix_template=LEAD_NUMBERING["prefix_template"],
            number_digits=LEAD_NUMBERING["number_digits"],
            next_value=LEAD_NUMBERING["start_value"],
            start_value=LEAD_NUMBERING["start_value"],
            reset_policy="none",
        )
    )
    db.flush()
    return True


def seed_default_lead_graph(db: Session) -> int:
    """The graph for ``project_lead`` (AC-O7). No scoped variants: leads have no template.

    Same wholesale guard as the other two graphs.
    """
    already = (
        db.query(func.count(Status.id))
        .filter(Status.entity_type == PROJECT_LEAD_ENTITY, Status.scope_id.is_(None))
        .scalar()
    )
    if already:
        return 0

    by_key: Dict[str, Status] = {}
    for index, (key, label, initial, terminal) in enumerate(DEFAULT_LEAD_STATUSES):
        row = Status(
            id=_uid(),
            entity_type=PROJECT_LEAD_ENTITY,
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

    for from_key, to_key, label in DEFAULT_LEAD_EDGES:
        db.add(
            StatusTransition(
                id=_uid(),
                entity_type=PROJECT_LEAD_ENTITY,
                scope_id=None,
                from_status_id=by_key[from_key].id,
                to_status_id=by_key[to_key].id,
                label=label,
                trigger_mode="manual",
            )
        )
    # Disqualifiable from every live rung. A rumour that dies on the first phone call
    # is the common case, not an exception reachable only from the last stage.
    for from_key in _LEAD_LIVE:
        db.add(
            StatusTransition(
                id=_uid(),
                entity_type=PROJECT_LEAD_ENTITY,
                scope_id=None,
                from_status_id=by_key[from_key].id,
                to_status_id=by_key["disqualified"].id,
                label="Disqualify",
                trigger_mode="manual",
            )
        )
    db.flush()
    return len(by_key)


def seed_lead_disqualify_reasons(db: Session) -> int:
    """The reason lookup set (AC-O6), created empty-safe and never re-asserted.

    Uses the existing generic lookup machinery rather than a bespoke table: an admin
    already has a screen for editing lookup options, and a second reason table would
    need a second screen.
    """
    existing = (
        db.query(LookupSet)
        .filter(LookupSet.set_key == LEAD_DISQUALIFY_REASON_SET_KEY)
        .first()
    )
    if existing:
        return 0

    lookup_set = LookupSet(
        id=_uid(),
        set_key=LEAD_DISQUALIFY_REASON_SET_KEY,
        name="Lead disqualification reasons",
        description=(
            "Why a project lead was disqualified. Read by the lead disqualify action; "
            "the conversion report groups by these."
        ),
    )
    db.add(lookup_set)
    db.flush()
    for order, (value, label) in enumerate(DEFAULT_LEAD_DISQUALIFY_REASONS):
        db.add(
            LookupOption(
                id=_uid(),
                set_id=lookup_set.id,
                value=value,
                label=label,
                sort_order=order,
            )
        )
    db.flush()
    return len(DEFAULT_LEAD_DISQUALIFY_REASONS)


def _company_ids(db: Session) -> List[str]:
    from app.models.company import Company

    return [row[0] for row in db.query(Company.id).filter(Company.is_active.is_(True)).all()]


def run(db: Session, company_id: Optional[str] = None) -> Dict[str, int]:
    """Seed everything. Safe to call on every boot."""
    summary = {
        "numbering": 0,
        "statuses": 0,
        "task_statuses": 0,
        "lead_numbering": 0,
        "lead_statuses": 0,
        "lead_reasons": 0,
        "types": 0,
    }
    summary["numbering"] = 1 if seed_numbering_rule(db) else 0
    summary["statuses"] = seed_default_funnel(db)
    summary["task_statuses"] = seed_default_task_graph(db)
    summary["lead_numbering"] = 1 if seed_lead_numbering_rule(db) else 0
    summary["lead_statuses"] = seed_default_lead_graph(db)
    summary["lead_reasons"] = seed_lead_disqualify_reasons(db)

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
