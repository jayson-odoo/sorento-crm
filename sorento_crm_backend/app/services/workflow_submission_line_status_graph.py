"""Submission LINES on the status engine: the registration and its default graph.

The line-level twin of ``workflow_submission_status_graph``, and it exists for one
requirement: Customer Service approves some lines and rejects others, so a decision is
per item rather than per submission.

**Its own entity type, not the submission's graph.** A line's lifecycle is a per-item
decision (approve, reject, withdraw) and the header's is a case lifecycle. One shared
graph would force every header rung onto every line and every line rung onto every
header, and no fork could separate them again, because the entity type is what a graph
hangs off.

**FK-native** (ADR-0013 rule 1): a new table has no legacy excuse. That is also what
makes ``count_records`` exact under a fork, since an id belongs to exactly one graph
where a key is deliberately shared across all of them.

**Scoped to the DEFINITION, one hop through the submission.** A line has no
``definition_id`` of its own, so a column name could not express this at all; the
callable ``scope_resolver`` was designed for exactly this case (ADR-0013 rule 4). Without
it every definition would share one line graph and forking one would re-cut the rungs
for all.

**The trait flags are the contract.** ``cancelled`` is ``is_archived`` because that is
the engine's flag for "not part of the live population", which is what excluding a
withdrawn line from the derived header means (see
``workflow_submission_derived_status``). Nothing else in this graph may carry that flag,
and derivation reads the flags rather than these key strings, so a definition may rename
or re-cut its rungs without touching derivation code.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.status import TRIGGER_MANUAL, Status, StatusTransition
from app.models.workflow_forms import WorkflowSubmission, WorkflowSubmissionLine
from app.services.error_handler import AppException
from app.services.status_service import resolve_graph
from app.services.workflow_submission_status_graph import StatusSeed, TransitionSeed
from app.status_engine.registry import StatusEntity, register_status_entity

WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE = "workflow_submission_line"


@dataclass(frozen=True)
class LineStatusSeed(StatusSeed):
    """A line rung. Adds ``is_archived``, which the header graph never needs."""

    is_archived: bool = False


# Deliberately minimal: undecided, the two decisions, and excluded. Widening the default
# pushes a form-specific rung onto every definition that inherits it (ADR-0013 rule 4's
# corollary), so every real variation is expected to FORK instead.
WORKFLOW_SUBMISSION_LINE_STATUS_SEEDS: Tuple[LineStatusSeed, ...] = (
    LineStatusSeed(
        key="pending",
        label="Pending",
        color_hex="#F59E0B",  # amber
        description="No decision has been made on this line yet. The only entry point.",
        is_initial=True,
        is_default=True,
    ),
    LineStatusSeed(
        key="approved",
        label="Approved",
        color_hex="#22C55E",  # green
        description="Final. This line was accepted.",
        is_terminal=True,
    ),
    LineStatusSeed(
        key="rejected",
        label="Rejected",
        color_hex="#EF4444",  # red
        description="Final. This line was turned down.",
        is_terminal=True,
    ),
    LineStatusSeed(
        key="cancelled",
        label="Cancelled",
        color_hex="#64748B",  # slate
        description=(
            "Final, and excluded from the submission's derived status: this line was "
            "withdrawn, so its work never has to happen."
        ),
        is_terminal=True,
        # Load-bearing. This is the flag derivation reads to drop a line out of the
        # population, so no other rung of this graph may carry it.
        is_archived=True,
    ),
)

# Every edge leaves the one undecided rung. Nothing is added for symmetry: an edge no
# code performs is false documentation and gets read as intent later (ADR-0013 rule 5).
# All manual -- ``trigger_mode='auto'`` means the ENGINE fires the edge from a
# ``conditions_json`` tree, and a per-item decision has no condition to evaluate.
WORKFLOW_SUBMISSION_LINE_TRANSITION_SEEDS: Tuple[TransitionSeed, ...] = (
    TransitionSeed("pending", "approved", "Approve"),
    TransitionSeed("pending", "rejected", "Reject"),
    TransitionSeed("pending", "cancelled", "Cancel"),
)

WORKFLOW_SUBMISSION_LINE_STATUS_KEYS: Tuple[str, ...] = tuple(
    s.key for s in WORKFLOW_SUBMISSION_LINE_STATUS_SEEDS
)


# ------------------------------------------------------- registry callables


def count_lines_in_status(db: Session, status_id: str) -> int:
    """How many lines hold this status row.

    By id, not by key: a forked definition's lines must count against the FORK, so an
    admin cannot delete a status out from under them (ADR-0013 rule 6).
    """
    if not status_id:
        return 0
    return (
        db.query(WorkflowSubmissionLine)
        .filter(WorkflowSubmissionLine.status_id == status_id)
        .count()
    )


def migrate_lines_to_status(db: Session, from_status_id: str, to_status_id: str) -> int:
    """Move every line off one status onto another. Returns the row count.

    Row by row rather than a bulk UPDATE, so the audit listener sees each change.
    """
    if not from_status_id or not to_status_id or from_status_id == to_status_id:
        return 0

    rows = (
        db.query(WorkflowSubmissionLine)
        .filter(WorkflowSubmissionLine.status_id == from_status_id)
        .all()
    )
    for row in rows:
        row.status_id = to_status_id
    db.flush()
    return len(rows)


def _scope_for_line(line: WorkflowSubmissionLine) -> Optional[str]:
    """A line's graph belongs to its submission's DEFINITION, one hop away.

    None-safe at both hops: a detached or half-built row resolves the default graph
    rather than raising inside the engine.
    """
    submission = getattr(line, "submission", None)
    if submission is None:
        return None
    return getattr(submission, "definition_id", None)


def register_workflow_submission_line_status_entity() -> None:
    """Join the engine. Idempotent, so it is safe on every process start."""
    register_status_entity(
        StatusEntity(
            entity_type=WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
            label="Form submission line",
            module="workflow_forms",
            count_records=count_lines_in_status,
            migrate_records=migrate_lines_to_status,
            model=WorkflowSubmissionLine,
            status_attr="status_id",
            record_label_attr="id",
            scope_resolver=_scope_for_line,
            # The admin graph editor decides whether to offer a per-definition fork from
            # the presence of the resolver, and needs a noun for its owner.
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


def seed_workflow_submission_line_status_graph(db: Session) -> Dict[str, int]:
    """Create or CORRECT the default line graph. Returns a change summary.

    Idempotent in the "set where mismatch" sense, not "insert where absent" (ADR-0013
    rule 10): a re-run repairs a drifted label, colour or flag IN PLACE, keeping the
    row's id so every line pointing at it follows the repair.

    Only the DEFAULT scope is touched. A fork is admin-owned configuration, and a seed
    that reached into forks would silently undo a tuned graph on every deploy.
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
            Status.entity_type == WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
            Status.scope_id.is_(None),
        )
        .all()
    }

    by_key: Dict[str, Status] = {}
    for index, seed in enumerate(WORKFLOW_SUBMISSION_LINE_STATUS_SEEDS):
        values = {
            "label": seed.label,
            "color_hex": seed.color_hex,
            "description": seed.description,
            # Gaps of 10 so an admin can slot a rung between two others.
            "sort_order": index * 10,
            "is_initial": seed.is_initial,
            "is_terminal": seed.is_terminal,
            "is_active": seed.is_active,
            "is_archived": seed.is_archived,
            "is_default": seed.is_default,
            "is_system": True,
        }
        row = existing.get(seed.key)
        if row is None:
            row = Status(
                id=str(uuid.uuid4()),
                entity_type=WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
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
            StatusTransition.entity_type == WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
            StatusTransition.scope_id.is_(None),
        )
        .all()
    }

    for index, seed in enumerate(WORKFLOW_SUBMISSION_LINE_TRANSITION_SEEDS):
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
                    entity_type=WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
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


# ---------------------------------------------------------------- reporting


def line_status_counts_by_key(
    db: Session, submission_ids: Sequence[str]
) -> Dict[str, int]:
    """How many lines of these submissions sit on each status KEY.

    By key, never by id: a fork re-keys the ids for the same rungs, so grouping by id
    would split one pipeline rung into a column per definition and the roll-up would
    stop being a roll-up (ADR-0013 rule 3). Lines with no status contribute nothing --
    they are on no rung of any graph.
    """
    ids = [str(x) for x in (submission_ids or []) if str(x or "").strip()]
    if not ids:
        return {}
    rows = (
        db.query(Status.key, func.count(WorkflowSubmissionLine.id))
        .join(Status, WorkflowSubmissionLine.status_id == Status.id)
        .filter(WorkflowSubmissionLine.submission_id.in_(ids))
        .group_by(Status.key)
        .all()
    )
    return {key: int(count) for key, count in rows}


# ------------------------------------------------------- decided-line guard


def line_is_decided(line: WorkflowSubmissionLine, initial_status_id: Optional[str]) -> bool:
    """Whether someone has already ruled on this line.

    Two independent signals, because they are two independent decisions: a status other
    than the graph's initial rung, or a disposition. A line with no status at all belongs
    to a definition that never opted in, so it is data rather than a decision.

    A status the resolved graph does not contain counts as decided. It cannot be PROVEN
    to be the initial rung, and treating an unrecognised value as undecided would throw
    away exactly what this guard protects.
    """
    if (line.disposition or "").strip():
        return True
    status_id = getattr(line, "status_id", None)
    if status_id is None:
        return False
    return str(status_id) != str(initial_status_id or "")


def assert_lines_replaceable(db: Session, submission: WorkflowSubmission) -> None:
    """Refuse to blow away lines that carry decisions.

    ``update_submission`` replaces lines by deleting every row and re-inserting with
    fresh UUIDs, which would silently destroy every line status and disposition. Refusing
    rather than merging is deliberate: a merge needs a stable per-row identity and the
    document supplies none (``row_data`` is free-form and the id is server-generated), so
    any matching rule would be a heuristic that mis-attributes a decision to the wrong
    row. Losing a decision quietly is worse than refusing an edit loudly.
    """
    lines: List[WorkflowSubmissionLine] = (
        db.query(WorkflowSubmissionLine)
        .filter(WorkflowSubmissionLine.submission_id == submission.id)
        .all()
    )
    if not lines:
        return

    graph = resolve_graph(
        db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, str(submission.definition_id)
    )
    initial = graph.initial
    decided = [
        line
        for line in lines
        if line_is_decided(line, getattr(initial, "id", None))
    ]
    if not decided:
        return
    count = len(decided)
    raise AppException(
        status_code=422,
        message=(
            f"{count} line{'' if count == 1 else 's'} on this submission "
            f"{'has' if count == 1 else 'have'} already been decided, so the lines "
            "cannot be replaced. Edit the answers without sending lines, or reverse the "
            "decisions first."
        ),
        code="line_decided_not_replaceable",
    )
