"""Complaints on the status engine: the entity registration and its default graph.

ADR-0012 adopted the engine that already shipped with project-sales, so this module
is purely additive: it declares the complaint graph and registers the entity. It
changes nothing about how a complaint moves today.

**Why the column stays a VARCHAR.** The engine is FK-based (``status_attr`` defaults
to ``status_id``), but ``complaints.status`` is ``VARCHAR(50) NOT NULL DEFAULT 'new'``
holding the key itself, with no FK and no CHECK constraint, across 51 live rows -- and
``complaint_fulfilment_service`` branches on ``processed_by_cs`` / ``fulfilled`` **by
name**. Adding a ``status_id`` FK means a data migration plus a rewrite of every branch
site, which is exactly the churn this slice promised to avoid. So the entity registers
with ``status_attr="status"`` and the two required callables count/migrate **by the key
the status row carries**, never by its id. An entity that reported 0 records because it
counted the wrong column would let an admin delete a status out from under live rows.

**Two entry points, one ``is_initial``.** ``draft`` is the portal entry
(``portal_service.py:1064``); ``new`` is the in-system and n8n entry, from the column
default. The engine cannot flag both: ``validate_graph`` raises
``status_graph_multiple_initial`` for a second flagged row, and it runs after every
admin write, so two flagged rows would 422 the first edit an admin made to any
complaint status. ``is_initial`` therefore goes to ``new`` -- the state a bare create
actually lands in, so ``initial_status()`` can never disagree with the column default --
and ``is_default`` marks the same row as the pre-selected pick. ``draft`` is declared in
``COMPLAINT_ENTRY_POINT_KEYS`` and, like ``new``, has no incoming edge. There is
deliberately no ``draft -> new`` edge: nothing in the codebase performs it.

Every status, edge and flag below is cited line by line in
``documentation/plans/after-sales/status-graph-evidence.md``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.complaints import Complaint
from app.models.status import TRIGGER_MANUAL, Status, StatusTransition
from app.status_engine.registry import StatusEntity, register_status_entity

COMPLAINT_ENTITY_TYPE = "complaint"

# The states a complaint can be CREATED in. Only one of them can carry the engine's
# ``is_initial`` flag (see the module docstring), so this is where the second entry
# point is recorded.
COMPLAINT_ENTRY_POINT_KEYS: Tuple[str, ...] = ("draft", "new")

# Neutral grey for the muted states. `voided` shares it deliberately:
# lib/status-pill.ts:23-25 -- "voiding is administrative, not an error/rejection", so
# it must NOT be red.
_GREY = "#6B7280"


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


# Labels and colours mirror ``sorento_crm_frontend/lib/complaint-status.ts``, the
# presentation source of truth. That file speaks Tailwind pastel pairs, which have no
# single hex, so each status takes the base-500 hue of the SAME family -- the graph
# editor renders a recognisable node and the family mapping survives.
#
# No status is ``is_archived``: that flag drops records out of the default list view,
# and nothing does that to complaints today.
COMPLAINT_STATUS_SEEDS: Tuple[StatusSeed, ...] = (
    StatusSeed(
        key="draft",
        label="Draft",
        color_hex=_GREY,
        description="Started in the submission portal and not submitted yet. Entry point; no parent state.",
    ),
    StatusSeed(
        key="new",
        label="New",
        color_hex=_GREY,
        description="Logged in the system or by n8n. Entry point: the complaints.status column default.",
        is_initial=True,
        is_default=True,
    ),
    StatusSeed(
        key="submitted",
        label="Submitted",
        color_hex="#0EA5E9",  # sky
        description="Submitted from the portal and awaiting a technical response.",
    ),
    StatusSeed(
        key="updated",
        label="Updated",
        color_hex="#F59E0B",  # amber
        description=(
            "Legacy state from an auto-flip on save that was removed on purpose. "
            "Nothing writes it; one live row still holds it, and it can still be responded to."
        ),
    ),
    StatusSeed(
        key="responded",
        label="Responded",
        color_hex="#6366F1",  # indigo
        description="The technical team response has been sent to the customer.",
    ),
    StatusSeed(
        key="approved",
        label="Approved",
        color_hex="#3B82F6",  # blue
        description="Decision made: the complaint is accepted and waiting on CS.",
    ),
    StatusSeed(
        key="rejected",
        label="Rejected",
        color_hex="#EF4444",  # red
        description="Decision made: rejected. NOT terminal - the portal resubmits from here.",
    ),
    StatusSeed(
        key="processed_by_cs",
        label="Processed by CS",
        color_hex="#10B981",  # emerald
        description="Customer service has processed the complaint; replacement delivery pending.",
    ),
    StatusSeed(
        key="resolved",
        label="Resolved",
        color_hex="#10B981",  # emerald, same rung as processed_by_cs
        description=(
            "The pre-rename spelling of 'Processed by CS'. No writer, no live rows, one "
            "audit row from 2026-06-09 - but still a live comparison target in "
            "_VOID_BLOCKED_STATUSES and in both frontend pill maps, so the key is kept. "
            "Deactivated: existing records could hold it, nothing new moves into it."
        ),
        is_active=False,
    ),
    StatusSeed(
        key="fulfilled",
        label="Fulfilled",
        color_hex="#8B5CF6",  # violet
        description="Every linked replacement delivery order was delivered. Reopens if one is undelivered.",
    ),
    StatusSeed(
        key="closed",
        label="Closed",
        color_hex="#64748B",  # slate
        description="Final. Closed from approved without a CS replacement.",
        is_terminal=True,
    ),
    StatusSeed(
        key="voided",
        label="Voided",
        color_hex=_GREY,
        description="Final and irreversible. Administrative annulment, which is why it is grey and not red.",
        is_terminal=True,
    ),
)

# Reachable-by-void states are the complement of ``_VOID_BLOCKED_STATUSES``
# (complaints_service.py:2303). ``fulfilled`` is absent from that tuple, so it IS
# voidable; ``rejected`` and ``processed_by_cs`` are not.
_VOIDABLE_FROM: Tuple[str, ...] = (
    "draft",
    "new",
    "submitted",
    "updated",
    "responded",
    "approved",
    "fulfilled",
)

# Every edge below is performed by live code; nothing is added for symmetry. Two
# edges the first port invented are deliberately absent: ``draft -> new`` (nothing
# performs it, it existed only to force a single entry point) and
# ``submitted -> updated`` (an auto-flip that was deliberately removed,
# complaints_service.py:1707-1711).
#
# All edges are ``manual``. ``trigger_mode='auto'`` means the ENGINE fires the edge
# from a ``conditions_json`` tree, and a CHECK constraint requires those conditions.
# The two fulfilment edges are fired by ``complaint_fulfilment_service`` in Python
# from a fact the rule engine cannot see ("every linked DO is delivered"), so
# declaring them auto would mean inventing a condition nothing can evaluate.
COMPLAINT_TRANSITION_SEEDS: Tuple[TransitionSeed, ...] = (
    # portal_service.py:874-879
    TransitionSeed("draft", "submitted", "Submit"),
    TransitionSeed("rejected", "submitted", "Resubmit"),
    # complaints_service.py:1686 (_RESPONSE_STAGE_STATUSES) + :1881
    TransitionSeed("new", "responded", "Send response"),
    TransitionSeed("submitted", "responded", "Send response"),
    TransitionSeed("updated", "responded", "Send response"),
    # complaints_service.py:1974-1977 (_DECIDE_ALLOWED_*) + :2045
    TransitionSeed("responded", "approved", "Approve"),
    TransitionSeed("responded", "rejected", "Reject"),
    # complaints_service.py:2133-2134 (_RESOLVE_ALLOWED_FROM / _FINALIZE_STATUSES) + :2252
    TransitionSeed("approved", "processed_by_cs", "Process"),
    TransitionSeed("approved", "closed", "Close"),
    # complaint_fulfilment_service.py:313-322
    TransitionSeed("processed_by_cs", "fulfilled", "Replacement delivered"),
    TransitionSeed("fulfilled", "processed_by_cs", "Reopen"),
) + tuple(TransitionSeed(key, "voided", "Void") for key in _VOIDABLE_FROM)

COMPLAINT_STATUS_KEYS: Tuple[str, ...] = tuple(s.key for s in COMPLAINT_STATUS_SEEDS)


# ------------------------------------------------------- registry callables


def _key_for(db: Session, status_id: str) -> Optional[str]:
    return (
        db.query(Status.key)
        .filter(Status.id == status_id, Status.entity_type == COMPLAINT_ENTITY_TYPE)
        .scalar()
    )


def count_complaints_in_status(db: Session, status_id: str) -> int:
    """How many complaints hold this status.

    By KEY, not by id: the column stores the key. A forked graph reuses keys for the
    same rung, but complaints declare no ``scope_resolver`` so only the default graph
    exists and the count is exact.
    """
    key = _key_for(db, status_id)
    if not key:
        return 0
    return db.query(Complaint).filter(Complaint.status == key).count()


def migrate_complaints_to_status(db: Session, from_status_id: str, to_status_id: str) -> int:
    """Move every complaint off one status key onto another. Returns the row count.

    Row by row rather than a bulk UPDATE, so the audit listener sees each change:
    an admin retiring a status is rewriting live records and that belongs in the
    trail. The table is small (51 rows today), so the cost is irrelevant.
    """
    from_key = _key_for(db, from_status_id)
    to_key = _key_for(db, to_status_id)
    if not from_key or not to_key or from_key == to_key:
        return 0

    rows = db.query(Complaint).filter(Complaint.status == from_key).all()
    for row in rows:
        row.status = to_key
    db.flush()
    return len(rows)


def register_complaint_status_entity() -> None:
    """Join the engine. Idempotent, so it is safe on every process start.

    No ``fact_attrs`` / ``aggregatable_relations``: those register rule-engine fact
    sources for auto edges, and the complaint graph has none.
    """
    register_status_entity(
        StatusEntity(
            entity_type=COMPLAINT_ENTITY_TYPE,
            label="Complaint",
            module="complaints",
            count_records=count_complaints_in_status,
            migrate_records=migrate_complaints_to_status,
            model=Complaint,
            # The key-valued column, NOT the engine's default status_id FK.
            status_attr="status",
            record_label_attr="complaint_number",
            # No scope_resolver: complaints have exactly one graph, never a fork.
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


def seed_complaint_status_graph(db: Session) -> Dict[str, int]:
    """Create or CORRECT the complaint default graph. Returns a change summary.

    Idempotent in the "set where mismatch" sense, not "insert where absent": a
    re-run repairs a drifted label, colour or flag. Insert-if-absent could never fix
    a prior bad run, which is the whole reason a seed gets re-run.

    That makes the declaration authoritative over admin cosmetics for these rows.
    It is the right trade here: they are ``is_system`` rows whose key and machine
    flags the admin API already freezes, because code reads them by name.

    Undeclared statuses and edges in the graph are left alone -- deleting admin
    configuration from a seed would be worse than leaving a stray row.
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
        .filter(Status.entity_type == COMPLAINT_ENTITY_TYPE, Status.scope_id.is_(None))
        .all()
    }

    by_key: Dict[str, Status] = {}
    for index, seed in enumerate(COMPLAINT_STATUS_SEEDS):
        values = {
            "label": seed.label,
            "color_hex": seed.color_hex,
            "description": seed.description,
            # Gaps of 10 so an admin can slot a status between two rungs.
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
                entity_type=COMPLAINT_ENTITY_TYPE,
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
            StatusTransition.entity_type == COMPLAINT_ENTITY_TYPE,
            StatusTransition.scope_id.is_(None),
        )
        .all()
    }

    for index, seed in enumerate(COMPLAINT_TRANSITION_SEEDS):
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
                    entity_type=COMPLAINT_ENTITY_TYPE,
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
