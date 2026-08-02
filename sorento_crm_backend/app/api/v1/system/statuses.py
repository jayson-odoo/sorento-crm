"""Status engine admin API (ADR-0001).

Configures the state machines other modules ride. Every write re-validates the
whole graph afterwards, because the invariants that matter -- exactly one starting
state, no outgoing edges from a final state -- are properties of the graph, not of
the row being saved.
"""
import logging
from contextlib import contextmanager
from typing import Iterator, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.status import Status, StatusTransition
from app.schemas.status import (
    StatusCreate,
    StatusEntityResponse,
    StatusGraphResponse,
    StatusMigrateRequest,
    StatusMigrateResponse,
    StatusResponse,
    StatusTransitionCreate,
    StatusTransitionResponse,
    StatusTransitionUpdate,
    StatusUpdate,
)
from app.services.error_handler import AppException
from app.services.status_service import (
    assert_edge_valid,
    assert_key_available,
    assert_status_deletable,
    count_records_in_status,
    migrate_records,
    resolve_graph,
    status_entities_payload,
    validate_graph,
)

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "system.statuses.view"
EDIT = "system.statuses.edit"


@contextmanager
def _translating_conflicts(db: Session) -> Iterator[None]:
    """Turn a unique-index violation into a 409 instead of an unhandled 500.

    Every duplicate the UI can cause is pre-checked in readable language before we
    get here; this covers the race between two admins saving at once, where the
    index is the only thing left holding the line.
    """
    try:
        yield
    except IntegrityError as exc:
        db.rollback()
        # The driver error is logged, never returned. The frontend's
        # extractApiError prefers `detail` over `message`, so putting it there
        # would show the user a raw Postgres constraint violation.
        logger.warning("status graph write hit a constraint: %s", getattr(exc, "orig", exc))
        raise AppException(
            status_code=409,
            message="That status graph was changed by someone else. Reload and try again.",
            code="status_conflict",
        ) from exc


def _get_status(db: Session, status_id: str) -> Status:
    row = db.query(Status).filter(Status.id == status_id).first()
    if row is None:
        raise AppException(status_code=404, message="Status not found.", code="status_not_found")
    return row


def _get_transition(db: Session, transition_id: str) -> StatusTransition:
    row = db.query(StatusTransition).filter(StatusTransition.id == transition_id).first()
    if row is None:
        raise AppException(
            status_code=404, message="Transition not found.", code="status_transition_not_found"
        )
    return row


def _serialize_status(db: Session, row: Status, *, with_count: bool = False) -> StatusResponse:
    payload = StatusResponse.model_validate(row)
    if with_count:
        payload.record_count = count_records_in_status(db, row)
    return payload


# ------------------------------------------------------------------ entities


@router.get("/status-entities", response_model=List[StatusEntityResponse])
async def list_status_entities_route(
    _user: dict = Depends(require_permission(VIEW)),
):
    """Entities registered on the engine. Empty until a module registers one."""
    return [StatusEntityResponse(**row) for row in status_entities_payload()]


# --------------------------------------------------------------------- graph


@router.get("/statuses/graph/{entity_type}", response_model=StatusGraphResponse)
async def get_status_graph(
    entity_type: str,
    scope_id: Optional[str] = Query(
        default=None,
        description="Resolve a scope's forked graph. Falls back to the default when that scope has not forked.",
    ),
    with_counts: bool = Query(default=False, description="Include live record counts per status."),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    graph = resolve_graph(db, entity_type, scope_id)
    return StatusGraphResponse(
        entity_type=entity_type,
        requested_scope_id=scope_id,
        resolved_scope_id=graph.resolved_scope_id,
        is_fork=graph.is_fork,
        statuses=[_serialize_status(db, s, with_count=with_counts) for s in graph.statuses],
        transitions=[StatusTransitionResponse.model_validate(t) for t in graph.transitions],
    )


# ------------------------------------------------------------------ statuses


@router.post("/statuses", response_model=StatusResponse, status_code=201)
async def create_status(
    payload: StatusCreate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    assert_key_available(db, payload.entity_type, payload.scope_id, payload.key)
    row = Status(**payload.model_dump())
    db.add(row)
    with _translating_conflicts(db):
        db.flush()
    validate_graph(db, row.entity_type, row.scope_id)
    db.commit()
    db.refresh(row)
    return _serialize_status(db, row)


@router.patch("/statuses/{status_id}", response_model=StatusResponse)
async def update_status(
    status_id: str,
    payload: StatusUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    row = _get_status(db, status_id)
    data = payload.model_dump(exclude_unset=True)

    # System rows are seeded machine contracts: code reads them by key and
    # branches on their flags, so both are frozen. Cosmetics stay editable.
    if row.is_system:
        frozen = {"key", "is_initial", "is_terminal"} & set(data)
        if frozen:
            raise AppException(
                status_code=422,
                message=(
                    f"'{row.label}' is a system status; "
                    f"{', '.join(sorted(frozen))} cannot be changed."
                ),
                code="status_is_system",
            )

    if "key" in data and data["key"] != row.key:
        assert_key_available(db, row.entity_type, row.scope_id, data["key"], exclude_id=row.id)

    for field, value in data.items():
        setattr(row, field, value)
    with _translating_conflicts(db):
        db.flush()
    validate_graph(db, row.entity_type, row.scope_id)
    db.commit()
    db.refresh(row)
    return _serialize_status(db, row)


@router.delete("/statuses/{status_id}", status_code=204)
async def delete_status(
    status_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Hard delete, blocked while records still hold it (AC-B5)."""
    row = _get_status(db, status_id)
    assert_status_deletable(db, row)
    entity_type, scope_id = row.entity_type, row.scope_id
    db.delete(row)  # edges cascade
    db.flush()
    # A graph that still has statuses must remain structurally valid; an emptied
    # graph is allowed, since that is how an entity is decommissioned.
    validate_graph(db, entity_type, scope_id)
    db.commit()
    return None


@router.post("/statuses/{status_id}/migrate-records", response_model=StatusMigrateResponse)
async def migrate_status_records(
    status_id: str,
    payload: StatusMigrateRequest,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Move every record off this status, so it can then be deleted."""
    source = _get_status(db, status_id)
    target = _get_status(db, payload.to_status_id)
    moved = migrate_records(db, source, target)
    db.commit()
    return StatusMigrateResponse(
        migrated=moved, from_status_id=source.id, to_status_id=target.id
    )


# --------------------------------------------------------------- transitions


@router.post("/status-transitions", response_model=StatusTransitionResponse, status_code=201)
async def create_transition(
    payload: StatusTransitionCreate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    assert_edge_valid(
        db,
        payload.entity_type,
        payload.from_status_id,
        payload.to_status_id,
        payload.trigger_mode,
        payload.conditions_json,
    )
    source = _get_status(db, payload.from_status_id)
    row = StatusTransition(**payload.model_dump(), scope_id=source.scope_id)
    db.add(row)
    with _translating_conflicts(db):
        db.flush()
    validate_graph(db, row.entity_type, row.scope_id)
    db.commit()
    db.refresh(row)
    return StatusTransitionResponse.model_validate(row)


@router.patch("/status-transitions/{transition_id}", response_model=StatusTransitionResponse)
async def update_transition(
    transition_id: str,
    payload: StatusTransitionUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    row = _get_transition(db, transition_id)
    data = payload.model_dump(exclude_unset=True)
    merged_mode = data.get("trigger_mode", row.trigger_mode)
    merged_conditions = data.get("conditions_json", row.conditions_json)
    assert_edge_valid(
        db,
        row.entity_type,
        row.from_status_id,
        row.to_status_id,
        merged_mode,
        merged_conditions,
    )
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    validate_graph(db, row.entity_type, row.scope_id)
    db.commit()
    db.refresh(row)
    return StatusTransitionResponse.model_validate(row)


@router.delete("/status-transitions/{transition_id}", status_code=204)
async def delete_transition(
    transition_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    row = _get_transition(db, transition_id)
    entity_type, scope_id = row.entity_type, row.scope_id
    db.delete(row)
    db.flush()
    validate_graph(db, entity_type, scope_id)
    db.commit()
    return None
