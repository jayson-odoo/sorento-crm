"""Workflow submissions on the status engine: the registration and its default graph.

Before F1 a submission's state lived in a ``VARCHAR(64)`` state-code column fed by a
state machine embedded in ``workflow_form_versions.schema``. ADR-0001 puts the graph in
the status engine; this module is where the workflow-forms module joins it.

**Why FK-native, unlike complaints.** ``complaint`` registers with
``status_attr="status"`` because its column predates the engine and every branch site
reads the key by name (ADR-0013 rule 2). ``workflow_submissions`` has no such excuse:
rule 1 applies, so it carries a ``status_id`` FK and registers on it. That is also what
makes ``count_records`` exact once a definition forks: an id belongs to exactly one
graph, where a key is deliberately shared across all of them, so a key-based count
would attribute a forked definition's rows to the DEFAULT graph's status and let an
admin delete a status out from under live records.

**One graph per definition, not one entity type per form.** ``scope_resolver`` returns
the submission's ``definition_id`` (ADR-0013 rule 4), so an exchange request can grow an
``in_repair`` rung without a service complaint ever seeing it, on one engine. A
definition that never overrides keeps resolving the default graph, which is what lets a
brand new definition work with no configuration at all.

**The default graph is deliberately minimal.** It re-expresses exactly the four edges
the retired embedded state machine shipped -- submit, approve, reject, send back -- and
nothing more. Every real form is expected to FORK. Widening the default would push a
form-specific rung onto every other definition that inherits it, so ADR-0013 rule 4's
corollary applies: a default that grows to satisfy each new consumer becomes a union of
everything and describes nothing.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.status import TRIGGER_MANUAL, Status, StatusTransition
from app.models.workflow_forms import WorkflowSubmission
from app.status_engine.registry import StatusEntity, register_status_entity

WORKFLOW_SUBMISSION_ENTITY_TYPE = "workflow_submission"


@dataclass(frozen=True)
class StatusSeed:
    """One row of the default graph. ``sort_order`` comes from list position."""

    key: str
    label: str
    color_hex: str
    description: str
    is_initial: bool = False
    is_terminal: bool = False
    is_active: bool = True
    is_default: bool = False


@dataclass(frozen=True)
class TransitionSeed:
    from_key: str
    to_key: str
    label: str


# Colours take the base-500 hue of the same family the rest of the product uses for
# these rungs (lib/status-pill.ts), so a forked graph rendered in the editor is
# recognisable beside a complaint's.
WORKFLOW_SUBMISSION_STATUS_SEEDS: Tuple[StatusSeed, ...] = (
    StatusSeed(
        key="draft",
        label="Draft",
        color_hex="#6B7280",  # grey
        description="Being filled in and not submitted yet. The only entry point.",
        is_initial=True,
        is_default=True,
    ),
    StatusSeed(
        key="submitted",
        label="Submitted",
        color_hex="#0EA5E9",  # sky
        description="Submitted and awaiting a decision.",
    ),
    StatusSeed(
        key="approved",
        label="Approved",
        color_hex="#3B82F6",  # blue
        description="Final. The submission was accepted.",
        is_terminal=True,
    ),
    StatusSeed(
        key="rejected",
        label="Rejected",
        color_hex="#EF4444",  # red
        description="Final. The submission was turned down.",
        is_terminal=True,
    ),
)

# The four edges the retired embedded state machine performed, re-expressed as engine
# edges. Nothing is added for symmetry: an edge no code performs is false documentation
# and gets read as intent later (ADR-0013 rule 5).
#
# All manual. ``trigger_mode='auto'`` means the ENGINE fires the edge from a
# ``conditions_json`` tree, and a CHECK constraint requires those conditions -- nothing
# in a generic graph has a condition to evaluate.
WORKFLOW_SUBMISSION_TRANSITION_SEEDS: Tuple[TransitionSeed, ...] = (
    TransitionSeed("draft", "submitted", "Submit"),
    TransitionSeed("submitted", "approved", "Approve"),
    TransitionSeed("submitted", "rejected", "Reject"),
    TransitionSeed("submitted", "draft", "Send back"),
)

WORKFLOW_SUBMISSION_STATUS_KEYS: Tuple[str, ...] = tuple(
    s.key for s in WORKFLOW_SUBMISSION_STATUS_SEEDS
)


# ------------------------------------------------------- registry callables


def count_submissions_in_status(db: Session, status_id: str) -> int:
    """How many submissions hold this status row.

    By id, not by key: a forked definition's rows must count against the FORK, so an
    admin cannot delete a status out from under them (ADR-0013 rule 6).
    """
    if not status_id:
        return 0
    return (
        db.query(WorkflowSubmission)
        .filter(WorkflowSubmission.status_id == status_id)
        .count()
    )


def migrate_submissions_to_status(
    db: Session, from_status_id: str, to_status_id: str
) -> int:
    """Move every submission off one status onto another. Returns the row count.

    Row by row rather than a bulk UPDATE, so the audit listener sees each change: an
    admin retiring a status is rewriting live records and that belongs in the trail.
    """
    if not from_status_id or not to_status_id or from_status_id == to_status_id:
        return 0

    rows = (
        db.query(WorkflowSubmission)
        .filter(WorkflowSubmission.status_id == from_status_id)
        .all()
    )
    for row in rows:
        row.status_id = to_status_id
    db.flush()
    return len(rows)


def _scope_for_submission(submission: WorkflowSubmission) -> Optional[str]:
    """A submission's graph belongs to its DEFINITION, so forks are per form."""
    return getattr(submission, "definition_id", None)


def register_workflow_submission_status_entity() -> None:
    """Join the engine. Idempotent, so it is safe on every process start.

    No ``fact_attrs`` / ``aggregatable_relations``: those register rule-engine fact
    sources for auto edges, and this graph has none.
    """
    register_status_entity(
        StatusEntity(
            entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
            label="Form submission",
            module="workflow_forms",
            count_records=count_submissions_in_status,
            migrate_records=migrate_submissions_to_status,
            model=WorkflowSubmission,
            # FK-native (ADR-0013 rule 1), unlike complaint's key-valued adapter.
            status_attr="status_id",
            record_label_attr="id",
            scope_resolver=_scope_for_submission,
            # The admin graph editor decides whether to offer a per-definition fork
            # from the presence of the resolver, and needs a noun for its owner.
            scope_label="Form",
        )
    )


# ------------------------------------------------------------------- seeding


def _apply(row: object, values: Dict[str, object]) -> bool:
    """Set only the attributes that differ. True when something changed."""
    changed = False
    for field, value in values.items():
        if getattr(row, field, None) != value:
            setattr(row, field, value)
            changed = True
    return changed


def seed_workflow_submission_status_graph(db: Session) -> Dict[str, int]:
    """Create or CORRECT the default submission graph. Returns a change summary.

    Idempotent in the "set where mismatch" sense, not "insert where absent" (ADR-0013
    rule 10): a re-run repairs a drifted label, colour or flag IN PLACE, keeping the
    row's id so every submission pointing at it follows the repair. Insert-if-absent
    could never fix a prior bad run, which is the whole reason a seed gets re-run.

    Only the DEFAULT scope is touched. A fork is admin-owned configuration, and a seed
    that reached into forks would silently undo a tuned graph on every deploy.
    Undeclared statuses and edges are left alone for the same reason.
    """
    summary = {
        "statuses_created": 0,
        "statuses_updated": 0,
        "transitions_created": 0,
        "transitions_updated": 0,
    }

    existing: Dict[str, Status] = {
        row.key: row
        for row in db.query(Status)
        .filter(
            Status.entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE,
            Status.scope_id.is_(None),
        )
        .all()
    }

    by_key: Dict[str, Status] = {}
    for index, seed in enumerate(WORKFLOW_SUBMISSION_STATUS_SEEDS):
        values = {
            "label": seed.label,
            "color_hex": seed.color_hex,
            "description": seed.description,
            # Gaps of 10 so an admin can slot a rung between two others.
            "sort_order": index * 10,
            "is_initial": seed.is_initial,
            "is_terminal": seed.is_terminal,
            "is_active": seed.is_active,
            "is_archived": False,
            "is_default": seed.is_default,
            "is_system": True,
        }
        row = existing.get(seed.key)
        if row is None:
            row = Status(
                id=str(uuid.uuid4()),
                entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
                key=seed.key,
                scope_id=None,
                tenant_id=None,
                **values,
            )
            db.add(row)
            summary["statuses_created"] += 1
        elif _apply(row, values):
            summary["statuses_updated"] += 1
        by_key[seed.key] = row
    db.flush()  # ids must exist before edges reference them

    edges: Dict[Tuple[str, str], StatusTransition] = {
        (row.from_status_id, row.to_status_id): row
        for row in db.query(StatusTransition)
        .filter(
            StatusTransition.entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE,
            StatusTransition.scope_id.is_(None),
        )
        .all()
    }

    for index, seed in enumerate(WORKFLOW_SUBMISSION_TRANSITION_SEEDS):
        source, target = by_key[seed.from_key], by_key[seed.to_key]
        values = {
            "label": seed.label,
            "sort_order": index * 10,
            "trigger_mode": TRIGGER_MANUAL,
            "conditions_json": None,
        }
        row = edges.get((source.id, target.id))
        if row is None:
            db.add(
                StatusTransition(
                    id=str(uuid.uuid4()),
                    entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
                    scope_id=None,
                    tenant_id=None,
                    from_status_id=source.id,
                    to_status_id=target.id,
                    **values,
                )
            )
            summary["transitions_created"] += 1
        elif _apply(row, values):
            summary["transitions_updated"] += 1
    db.flush()

    return summary
