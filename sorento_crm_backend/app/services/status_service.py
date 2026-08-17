"""Status engine service — graph resolution, validation, transitions (ADR-0001).

The one rule that matters: **a transition not present in the graph is rejected
server-side**, whatever the client sends. A board that lets a card be dragged
anywhere is a UI convenience; this module is the authority.

Graph resolution is two-tier. ``scope_id IS NULL`` rows are the entity's default
graph. A scope that overrides owns a full forked copy. ``resolve_graph`` returns
the fork when the scope has any rows and the default otherwise, so a scope that
never overrides keeps inheriting and a later edit to the default does not silently
rewrite a tuned fork.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.status import TRIGGER_AUTO, TRIGGER_MANUAL, Status, StatusTransition
from app.services.error_handler import AppException
from app.status_engine.registry import get_status_entity, list_status_entities


def _uuid_str() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class StatusGraph:
    """A resolved graph: the statuses plus the legal edges between them."""

    entity_type: str
    # The scope these rows actually came from. None = the default graph. This is
    # NOT necessarily the scope that was asked for -- an un-forked scope resolves
    # to the default, and callers (the admin UI especially) need to know which.
    resolved_scope_id: Optional[str]
    is_fork: bool
    statuses: List[Status]
    transitions: List[StatusTransition]

    def by_id(self, status_id: str) -> Optional[Status]:
        return next((s for s in self.statuses if s.id == status_id), None)

    def by_key(self, key: str) -> Optional[Status]:
        return next((s for s in self.statuses if s.key == key), None)

    @property
    def initial(self) -> Optional[Status]:
        return next((s for s in self.statuses if s.is_initial), None)

    def outgoing(self, from_status_id: str) -> List[StatusTransition]:
        return [t for t in self.transitions if t.from_status_id == from_status_id]


# --------------------------------------------------------------- resolution


def _statuses_for(db: Session, entity_type: str, scope_id: Optional[str]) -> List[Status]:
    q = db.query(Status).filter(Status.entity_type == entity_type)
    q = q.filter(Status.scope_id == scope_id) if scope_id else q.filter(Status.scope_id.is_(None))
    return q.order_by(Status.sort_order, Status.label).all()


def resolve_graph(
    db: Session, entity_type: str, scope_id: Optional[str] = None
) -> StatusGraph:
    """The graph in force for this entity and scope: the fork if one exists, else
    the default."""
    statuses: List[Status] = []
    resolved_scope: Optional[str] = None
    is_fork = False

    if scope_id:
        statuses = _statuses_for(db, entity_type, scope_id)
        if statuses:
            resolved_scope, is_fork = scope_id, True

    if not statuses:
        statuses = _statuses_for(db, entity_type, None)

    status_ids = [s.id for s in statuses]
    transitions: List[StatusTransition] = []
    if status_ids:
        transitions = (
            db.query(StatusTransition)
            .filter(
                StatusTransition.entity_type == entity_type,
                StatusTransition.from_status_id.in_(status_ids),
            )
            .order_by(StatusTransition.sort_order, StatusTransition.label)
            .all()
        )
        # Defense in depth: never surface an edge pointing outside this graph.
        allowed = set(status_ids)
        transitions = [t for t in transitions if t.to_status_id in allowed]

    return StatusGraph(
        entity_type=entity_type,
        resolved_scope_id=resolved_scope,
        is_fork=is_fork,
        statuses=statuses,
        transitions=transitions,
    )


def graph_for_record(db: Session, entity_type: str, record: Any) -> StatusGraph:
    """The graph in force for one record, using its entity's scope resolver."""
    entity = get_status_entity(entity_type)
    scope_id = entity.scope_for(record) if entity else None
    return resolve_graph(db, entity_type, scope_id)


def initial_status(
    db: Session, entity_type: str, scope_id: Optional[str] = None
) -> Status:
    """The status a new record starts in. A graph with no initial status is a
    configuration error that would leave records status-less, so it raises."""
    graph = resolve_graph(db, entity_type, scope_id)
    if not graph.statuses:
        raise AppException(
            status_code=422,
            message=f"No status graph is configured for '{entity_type}'.",
            code="status_graph_missing",
        )
    if graph.initial is None:
        raise AppException(
            status_code=422,
            message=(
                f"The status graph for '{entity_type}' has no initial status. "
                "Mark exactly one status as the starting state."
            ),
            code="status_graph_no_initial",
        )
    return graph.initial


# --------------------------------------------------------------- transitions


def available_transitions(
    db: Session,
    entity_type: str,
    from_status_id: Optional[str],
    scope_id: Optional[str] = None,
) -> List[StatusTransition]:
    """Manual edges a user may fire from here.

    Auto edges are excluded: they belong to the engine, so offering them as
    buttons would let a user bypass their conditions. Edges into a deactivated
    status are excluded too -- existing records keep such a status, but nothing
    new moves into it.
    """
    if from_status_id is None:
        return []
    graph = resolve_graph(db, entity_type, scope_id)
    current = graph.by_id(from_status_id)
    if current is None or current.is_terminal:
        return []
    inactive = {s.id for s in graph.statuses if not s.is_active}
    return [
        t
        for t in graph.outgoing(from_status_id)
        if t.trigger_mode == TRIGGER_MANUAL and t.to_status_id not in inactive
    ]


def assert_transition_allowed(
    db: Session,
    entity_type: str,
    from_status_id: Optional[str],
    to_status_id: str,
    scope_id: Optional[str] = None,
) -> StatusTransition:
    """Raise 422 unless a manual edge exists. Returns the edge that authorised it.

    This is the server-side authority behind AC-B4: dragging a board card to an
    illegal column fails here, not in the browser.
    """
    graph = resolve_graph(db, entity_type, scope_id)
    target = graph.by_id(to_status_id)
    if target is None:
        raise AppException(
            status_code=422,
            message="That status does not belong to this record's status graph.",
            code="status_not_in_graph",
        )
    if not target.is_active:
        raise AppException(
            status_code=422,
            message=f"'{target.label}' is deactivated and cannot be assigned.",
            code="status_inactive",
        )

    current = graph.by_id(from_status_id) if from_status_id else None
    if current is not None and current.is_terminal:
        raise AppException(
            status_code=422,
            message=f"'{current.label}' is a final status; this record cannot move on.",
            code="status_terminal",
        )

    edge = next(
        (
            t
            for t in graph.outgoing(from_status_id or "")
            if t.to_status_id == to_status_id and t.trigger_mode == TRIGGER_MANUAL
        ),
        None,
    )
    if edge is None:
        current_label = current.label if current else "its current state"
        raise AppException(
            status_code=422,
            message=f"Moving from {current_label} to '{target.label}' is not allowed.",
            code="status_transition_not_allowed",
        )
    return edge


# ---------------------------------------------------------------- forking


def fork_graph(db: Session, entity_type: str, scope_id: str) -> StatusGraph:
    """Copy the default graph onto ``scope_id`` (copy-on-write).

    Called the moment a scope first overrides. Idempotent: a scope that already
    has rows is returned as-is rather than duplicated.
    """
    existing = _statuses_for(db, entity_type, scope_id)
    if existing:
        return resolve_graph(db, entity_type, scope_id)

    default = resolve_graph(db, entity_type, None)
    if not default.statuses:
        raise AppException(
            status_code=422,
            message=(
                f"'{entity_type}' has no default status graph to fork. "
                "Configure the default first."
            ),
            code="status_graph_missing",
        )

    id_map: Dict[str, str] = {}
    for source in default.statuses:
        clone_id = _uuid_str()
        id_map[source.id] = clone_id
        db.add(
            Status(
                id=clone_id,
                entity_type=source.entity_type,
                key=source.key,
                category=source.category,
                label=source.label,
                color_hex=source.color_hex,
                description=source.description,
                sort_order=source.sort_order,
                is_initial=source.is_initial,
                is_terminal=source.is_terminal,
                is_active=source.is_active,
                is_archived=source.is_archived,
                is_default=source.is_default,
                # A fork is admin-owned config, never a protected system row --
                # the whole point of forking is that it can be edited.
                is_system=False,
                position_x=source.position_x,
                position_y=source.position_y,
                # The per-rung dials come across with the rung (AC-H4, AC-I2). A fork that
                # started with them NULL would silently have no staleness ladder and would
                # contribute nothing to the weighted forecast, which reads as a bug in
                # those features rather than as an unconfigured template.
                win_probability=source.win_probability,
                stale_after_days=source.stale_after_days,
                tenant_id=source.tenant_id,
                scope_id=scope_id,
            )
        )
    db.flush()

    for edge in default.transitions:
        db.add(
            StatusTransition(
                id=_uuid_str(),
                entity_type=edge.entity_type,
                tenant_id=edge.tenant_id,
                scope_id=scope_id,
                from_status_id=id_map[edge.from_status_id],
                to_status_id=id_map[edge.to_status_id],
                label=edge.label,
                sort_order=edge.sort_order,
                trigger_mode=edge.trigger_mode,
                conditions_json=edge.conditions_json,
            )
        )
    db.flush()
    return resolve_graph(db, entity_type, scope_id)


def reapply_default_dials(db: Session, entity_type: str, scope_id: str) -> int:
    """Copy the DEFAULT graph's per-rung dials back onto a fork (AC-H4). Returns rows changed.

    The explicit way back. A fork deliberately stops receiving default changes, which is
    right -- silent propagation is indistinguishable from data loss to whoever tuned the
    fork -- but an admin who has decided the defaults are better needs one action rather
    than editing eight rungs by hand.

    Matched on ``key``, never on ``sort_order`` or position: key is the documented stable
    identity per entity_type (grill finding G3), so a fork that re-ordered its board or
    deleted a rung it does not use is still matched correctly, and a rung that exists only
    on the fork is left alone.
    """
    defaults = {
        row.key: row
        for row in _statuses_for(db, entity_type, None)
    }
    if not defaults:
        raise AppException(
            status_code=422,
            message=(
                f"'{entity_type}' has no default status graph to copy from. "
                "Configure the default first."
            ),
            code="status_graph_missing",
        )

    changed = 0
    for row in _statuses_for(db, entity_type, scope_id):
        source = defaults.get(row.key)
        if source is None:
            continue
        if (
            row.win_probability == source.win_probability
            and row.stale_after_days == source.stale_after_days
        ):
            continue
        row.win_probability = source.win_probability
        row.stale_after_days = source.stale_after_days
        changed += 1
    if changed:
        db.flush()
    return changed


# -------------------------------------------------------------- validation


def validate_graph(db: Session, entity_type: str, scope_id: Optional[str] = None) -> None:
    """Structural checks that a single-row write cannot see. Raises 422.

    Called after any status or transition write, so an admin cannot save a graph
    into a state that would strand records.
    """
    graph = resolve_graph(db, entity_type, scope_id)
    if not graph.statuses:
        return

    initials = [s for s in graph.statuses if s.is_initial]
    if len(initials) > 1:
        names = ", ".join(sorted(s.label for s in initials))
        raise AppException(
            status_code=422,
            message=f"Only one status can be the starting state. Found: {names}.",
            code="status_graph_multiple_initial",
        )
    if not initials:
        raise AppException(
            status_code=422,
            message="One status must be marked as the starting state.",
            code="status_graph_no_initial",
        )

    terminal_ids = {s.id: s.label for s in graph.statuses if s.is_terminal}
    stranded = [terminal_ids[t.from_status_id] for t in graph.transitions if t.from_status_id in terminal_ids]
    if stranded:
        raise AppException(
            status_code=422,
            message=(
                f"'{stranded[0]}' is a final status, so it cannot have outgoing "
                "transitions. Remove them or clear the final flag."
            ),
            code="status_terminal_has_outgoing",
        )


def assert_key_available(
    db: Session,
    entity_type: str,
    scope_id: Optional[str],
    key: str,
    exclude_id: Optional[str] = None,
) -> None:
    """Reject a duplicate ``key`` within one graph, in readable language.

    The ``NULLS NOT DISTINCT`` unique index is the real guarantee, but on its own it
    surfaces to the admin as a 500 quoting a Postgres constraint name. This check
    runs first so the common case gets a sentence instead; the index stays as the
    race backstop.
    """
    q = db.query(Status.id).filter(
        Status.entity_type == entity_type,
        Status.key == key,
    )
    q = q.filter(Status.scope_id == scope_id) if scope_id else q.filter(Status.scope_id.is_(None))
    if exclude_id:
        q = q.filter(Status.id != exclude_id)
    if q.first() is not None:
        where = "this template's graph" if scope_id else "the default graph"
        raise AppException(
            status_code=422,
            message=f"A status with the key '{key}' already exists in {where}.",
            code="status_key_duplicate",
        )


def assert_edge_valid(
    db: Session,
    entity_type: str,
    from_status_id: str,
    to_status_id: str,
    trigger_mode: str,
    conditions_json: Optional[dict],
) -> None:
    """Validate one edge before it is written."""
    if trigger_mode not in (TRIGGER_MANUAL, TRIGGER_AUTO):
        raise AppException(
            status_code=422,
            message=f"Unknown trigger mode '{trigger_mode}'.",
            code="status_trigger_mode_invalid",
        )
    if trigger_mode == TRIGGER_AUTO and not conditions_json:
        raise AppException(
            status_code=422,
            message=(
                "An automatic transition needs conditions, otherwise it would fire "
                "immediately and unconditionally."
            ),
            code="status_auto_needs_conditions",
        )
    if from_status_id == to_status_id:
        raise AppException(
            status_code=422,
            message="A transition cannot start and end at the same status.",
            code="status_self_loop",
        )

    rows = (
        db.query(Status)
        .filter(Status.id.in_([from_status_id, to_status_id]))
        .all()
    )
    found = {r.id: r for r in rows}
    missing = [i for i in (from_status_id, to_status_id) if i not in found]
    if missing:
        raise AppException(
            status_code=422,
            message="Both ends of a transition must be existing statuses.",
            code="status_not_found",
        )
    source, target = found[from_status_id], found[to_status_id]
    if source.entity_type != entity_type or target.entity_type != entity_type:
        raise AppException(
            status_code=422,
            message="A transition cannot cross entity types.",
            code="status_entity_mismatch",
        )
    if source.scope_id != target.scope_id:
        raise AppException(
            status_code=422,
            message="A transition cannot cross status graphs.",
            code="status_scope_mismatch",
        )


# --------------------------------------------------- deletion and migration


def count_records_in_status(db: Session, status: Status) -> int:
    """How many live records hold this status, across every registered entity of
    its type. Zero when no module has registered that entity."""
    entity = get_status_entity(status.entity_type)
    if entity is None:
        return 0
    return entity.count_records(db, status.id)


def assert_status_deletable(db: Session, status: Status) -> None:
    if status.is_system:
        raise AppException(
            status_code=422,
            message=f"'{status.label}' is a system status and cannot be deleted.",
            code="status_is_system",
        )
    used = count_records_in_status(db, status)
    if used:
        # No `detail=` here on purpose. The frontend's extractApiError returns
        # `detail` in preference to `message`, so anything put there REPLACES the
        # sentence the user should read -- here it would have hidden the record
        # count behind an internal hint about the migrate endpoint.
        raise AppException(
            status_code=422,
            message=(
                f"{used} record{'' if used == 1 else 's'} still use "
                f"'{status.label}'. Move them to another status first."
            ),
            code="status_in_use",
        )


def migrate_records(db: Session, source: Status, target: Status) -> int:
    """Move every record off ``source`` onto ``target``. Returns the row count."""
    if source.id == target.id:
        raise AppException(
            status_code=422,
            message="Pick a different status to move records into.",
            code="status_migrate_same",
        )
    if source.entity_type != target.entity_type:
        raise AppException(
            status_code=422,
            message="Records can only move to a status of the same entity.",
            code="status_entity_mismatch",
        )
    entity = get_status_entity(source.entity_type)
    if entity is None:
        return 0
    return entity.migrate_records(db, source.id, target.id)


# -------------------------------------------------------------- entity list


def status_entities_payload() -> List[Dict[str, Any]]:
    """What ``GET /status-entities`` returns: the engine's registered entities,
    without the engine knowing any domain table."""
    return [
        {
            "entity_type": e.entity_type,
            "label": e.label,
            "module": e.module,
            "supports_scoped_graphs": e.scope_resolver is not None,
            "scope_label": e.scope_label,
            "required_flags": list(e.required_flags),
        }
        for e in list_status_entities()
    ]


def keys_by_entity(db: Session, entity_type: str) -> Sequence[str]:
    """Distinct status keys across every graph of this entity.

    This is the roll-up axis (AC-B2): a forked graph reuses the same ``key`` for
    the same rung, so grouping by key aggregates across forks. Grouping by id
    never would.
    """
    rows = (
        db.query(Status.key)
        .filter(Status.entity_type == entity_type)
        .distinct()
        .order_by(Status.key)
        .all()
    )
    return [r[0] for r in rows]
