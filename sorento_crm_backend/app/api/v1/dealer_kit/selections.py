"""Selections: what somebody chose, the room they put it in, and reading it back.

**Ownership is the authorisation.** There is no ``selection.view`` permission
because a Selection is not shared administrative data - it is one person's
basket. A staff user reads their own; a contact reads their own. The check is
the same either way and it happens on every route, so a guessed id returns 404
rather than somebody else's design.

The viewer is built from the principal, exactly as page resolution does it, so
one stored Selection reads as staff pricing for staff and consumer pricing for a
consumer without a second row existing (AC-S5).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.dealer_kit import (
    RoomWrite,
    SelectionCreate,
    SelectionLineWrite,
    SelectionOut,
    SelectionRename,
)
from app.services.dealer_kit import selection_service
from app.services.dealer_kit.viewer import ViewerContext
from app.services.error_handler import AppException

router = APIRouter()


def _user_id(user: dict | None) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _owned(db: Session, selection_id: str, user: dict):
    """Fetch a Selection the caller owns, or 404.

    404 and not 403 on purpose: a 403 confirms the id exists, which turns a
    sequential guess into an enumeration of other people's designs.
    """
    selection = selection_service.get_selection(db, selection_id)
    if selection.user_id != _user_id(user):
        raise AppException(status_code=404, message="Selection not found")
    return selection


def _viewer(user: dict | None) -> ViewerContext:
    # Staff read their own selection with staff eyes. `show_invoice_price` is
    # the document-level toggle elsewhere; a selection has no document, so the
    # entitlement alone decides and the two gates still both exist.
    return ViewerContext(is_staff=bool(_user_id(user)), show_invoice_price=True)


def _out(db: Session, selection, user: dict | None) -> SelectionOut:
    resolved = selection_service.resolve_selection(db, selection, _viewer(user))
    return SelectionOut(
        **resolved,
        room=selection.room_json,
        room_area_sqm=selection_service.room_area_sqm(selection.room_json),
    )


@router.post("/selections", response_model=SelectionOut, status_code=status.HTTP_201_CREATED)
def create_selection(
    payload: SelectionCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    selection = selection_service.create_selection(
        db,
        user_id=_user_id(user),
        name=payload.name,
        source_page_id=payload.source_page_id,
    )
    db.commit()
    db.refresh(selection)
    return _out(db, selection, user)


@router.get("/selections/{selection_id}", response_model=SelectionOut)
def read_selection(
    selection_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    return _out(db, _owned(db, selection_id, user), user)


@router.put("/selections/{selection_id}", response_model=SelectionOut)
def rename_selection(
    selection_id: str,
    payload: SelectionRename,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    selection = _owned(db, selection_id, user)
    selection.name = payload.name
    db.commit()
    db.refresh(selection)
    return _out(db, selection, user)


@router.delete("/selections/{selection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_selection(
    selection_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    selection = _owned(db, selection_id, user)
    db.delete(selection)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/selections/{selection_id}/lines", response_model=SelectionOut)
def upsert_line(
    selection_id: str,
    payload: SelectionLineWrite,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Set a line to an absolute quantity. Zero removes it.

    Absolute rather than incremental so that a retried request cannot order two
    of something - the same reason the designer sends what it wants to be true
    rather than what changed.
    """
    selection = _owned(db, selection_id, user)
    selection_service.set_quantity(db, selection, payload.product_id, payload.quantity)
    db.commit()
    db.refresh(selection)
    return _out(db, selection, user)


@router.delete("/selections/{selection_id}/lines/{product_id}", response_model=SelectionOut)
def delete_line(
    selection_id: str,
    product_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    selection = _owned(db, selection_id, user)
    selection_service.remove_line(db, selection, product_id)
    db.commit()
    db.refresh(selection)
    return _out(db, selection, user)


@router.put("/selections/{selection_id}/room", response_model=SelectionOut)
def save_room(
    selection_id: str,
    payload: RoomWrite,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    selection = _owned(db, selection_id, user)
    selection_service.save_room(
        db, selection, {"outline": payload.outline, "placements": payload.placements}
    )
    db.commit()
    db.refresh(selection)
    return _out(db, selection, user)
