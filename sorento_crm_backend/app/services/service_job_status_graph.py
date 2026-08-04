"""S6 - the Service Job on the status engine, and why it has a state machine at all.

A date column would have been cheaper. The reason there is a graph is one sentence from
the discovery study: **"Service Date: TBA"**. A job carrying a date nobody agreed to has
told CS it is handled, so nobody chases it, and the office finds out when the consumer
calls back. *Proposed* and *Confirmed* are different facts about the world and the system
has to be able to tell them apart.

**FK-based, unlike complaints.** ``complaints.status`` is a key-valued VARCHAR that half
the codebase branches on by name, so that entity registers with ``status_attr="status"``.
``service_jobs.status_id`` is a real FK from the first migration, so this one takes the
engine's default and gets referential integrity for free. New tables should look like this
one; the complaint shape is a compatibility decision, not a pattern.

**Six states, and the ones deliberately absent.** There is no ``scheduled`` distinct from
``confirmed`` (the confirmation IS the schedule), no ``parts_ordered`` (that is a waiting
attribution, S4a's, not a state, or the graph forks on every reason a job pauses), and no
per-technician state (an assignment row already carries that, and duplicating it means two
answers to "was this rejected"). ``cancelled`` is terminal and grey: cancelling is
administrative, not a failure, and colouring it red would read as the technician's fault
on every board.

The edges back to *Proposed* are the ones that matter. A rejected visit is not a dead job,
it is a job needing a new date, and the graph has to permit that without an admin editing
the record - otherwise CS works around it by cancelling and re-raising, and the case loses
its history exactly where the history is most interesting.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from app.models.service_jobs import ServiceJob
from app.models.status import TRIGGER_MANUAL, Status, StatusTransition
from app.status_engine.registry import StatusEntity, register_status_entity

SERVICE_JOB_ENTITY_TYPE = "service_job"

_GREY = "#6B7280"


@dataclass(frozen=True)
class StatusSeed:
    key: str
    label: str
    color_hex: str
    description: str
    is_initial: bool = False
    is_terminal: bool = False
    is_default: bool = False


@dataclass(frozen=True)
class TransitionSeed:
    from_key: str
    to_key: str
    label: str


SERVICE_JOB_STATUS_SEEDS: Tuple[StatusSeed, ...] = (
    StatusSeed(
        key="proposed",
        label="Proposed",
        color_hex=_GREY,
        description=(
            "Raised, with no agreed date. A job sits here until the consumer has actually "
            "agreed a time - 'Service Date: TBA' is this state, not Confirmed."
        ),
        is_initial=True,
        is_default=True,
    ),
    StatusSeed(
        key="confirmed",
        label="Confirmed",
        color_hex="#0EA5E9",  # sky
        description=(
            "A date the consumer agreed to, recorded with who agreed it. The technician's "
            "attend-time clock starts here."
        ),
    ),
    StatusSeed(
        key="on_the_way",
        label="On the way",
        color_hex="#6366F1",  # indigo
        description="The technician has left for the site. Set from the technician portal.",
    ),
    StatusSeed(
        key="arrived",
        label="Arrived",
        color_hex="#8B5CF6",  # violet
        description="On site. Attend time stops here; the work has not been done yet.",
    ),
    StatusSeed(
        key="completed",
        label="Completed",
        color_hex="#10B981",  # emerald
        description="The technician finished on site. Awaiting whatever verification CS does.",
    ),
    StatusSeed(
        key="verified",
        label="Verified",
        color_hex="#059669",  # emerald-600
        description="CS accepted the work. Terminal.",
        is_terminal=True,
    ),
    StatusSeed(
        key="cancelled",
        label="Cancelled",
        color_hex=_GREY,
        description=(
            "The visit is not happening at all. Terminal, and grey rather than red: "
            "cancelling is administrative, not a failure by anybody."
        ),
        is_terminal=True,
    ),
)


SERVICE_JOB_TRANSITION_SEEDS: Tuple[TransitionSeed, ...] = (
    TransitionSeed("proposed", "confirmed", "Confirm date"),
    TransitionSeed("confirmed", "on_the_way", "On my way"),
    TransitionSeed("on_the_way", "arrived", "Arrived"),
    # A technician who forgot to press "On my way" must not be blocked at the gate. The
    # portal is used one-handed on a doorstep; a missing intermediate tap is not a reason
    # to make somebody phone the office.
    TransitionSeed("confirmed", "arrived", "Arrived"),
    TransitionSeed("arrived", "completed", "Complete"),
    TransitionSeed("completed", "verified", "Verify"),
    # The edges that keep a rejected visit inside its own case. Without them CS cancels
    # and re-raises, and the history is lost exactly where it is most interesting.
    TransitionSeed("confirmed", "proposed", "Customer rejected the visit"),
    TransitionSeed("on_the_way", "proposed", "Customer rejected the visit"),
    TransitionSeed("arrived", "proposed", "Revisit needed"),
    TransitionSeed("proposed", "cancelled", "Cancel"),
    TransitionSeed("confirmed", "cancelled", "Cancel"),
    TransitionSeed("completed", "arrived", "Reopen: work not accepted"),
)


# ------------------------------------------------------- engine registration


def count_service_jobs_in_status(db: Session, status_id: str) -> int:
    return db.query(ServiceJob).filter(ServiceJob.status_id == status_id).count()


def migrate_service_jobs_to_status(db: Session, from_status_id: str, to_status_id: str) -> int:
    rows = db.query(ServiceJob).filter(ServiceJob.status_id == from_status_id).all()
    for row in rows:
        row.status_id = to_status_id
    db.flush()
    return len(rows)


def register_service_job_status_entity() -> None:
    """Join the engine. Idempotent, so it is safe on every process start."""
    register_status_entity(
        StatusEntity(
            entity_type=SERVICE_JOB_ENTITY_TYPE,
            label="Service Job",
            module="complaints",
            count_records=count_service_jobs_in_status,
            migrate_records=migrate_service_jobs_to_status,
            model=ServiceJob,
            # The engine's default FK column. See the module docstring for why this
            # entity gets it and complaints does not.
            status_attr="status_id",
            record_label_attr="job_number",
            # No scope_resolver: one graph, never forked per anything.
        )
    )


# ------------------------------------------------------------------ seeding


def _apply(row: object, values: Dict[str, object]) -> bool:
    changed = False
    for field, value in values.items():
        if getattr(row, field, None) != value:
            setattr(row, field, value)
            changed = True
    return changed


def seed_service_job_status_graph(db: Session) -> Dict[str, int]:
    """Create or CORRECT the default graph. Converging, not insert-if-absent.

    A seed that only inserts can never repair a prior bad run, which is the whole reason
    a seed gets re-run. Undeclared statuses and edges are left alone: deleting an admin's
    configuration from a seeder would be worse than leaving a stray row.
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
        .filter(Status.entity_type == SERVICE_JOB_ENTITY_TYPE, Status.scope_id.is_(None))
        .all()
    }

    by_key: Dict[str, Status] = {}
    for index, seed in enumerate(SERVICE_JOB_STATUS_SEEDS):
        values = {
            "label": seed.label,
            "color_hex": seed.color_hex,
            "description": seed.description,
            # Gaps of 10 so an admin can slot a status between two rungs.
            "sort_order": index * 10,
            "is_initial": seed.is_initial,
            "is_terminal": seed.is_terminal,
            "is_active": True,
            "is_archived": False,
            "is_default": seed.is_default,
            "is_system": True,
        }
        row = existing.get(seed.key)
        if row is None:
            row = Status(
                id=str(uuid.uuid4()),
                entity_type=SERVICE_JOB_ENTITY_TYPE,
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
            StatusTransition.entity_type == SERVICE_JOB_ENTITY_TYPE,
            StatusTransition.scope_id.is_(None),
        )
        .all()
    }

    for index, seed in enumerate(SERVICE_JOB_TRANSITION_SEEDS):
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
                    entity_type=SERVICE_JOB_ENTITY_TYPE,
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
