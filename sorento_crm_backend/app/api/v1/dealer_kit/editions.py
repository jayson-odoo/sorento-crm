"""Edition routes (S2.5.2).

Three permissions, and the split is the point of the whole slice:

* ``dealer_kit.page.edit`` - the Designer. Starts an Edition, submits it,
  picks a rejected one back up.
* ``dealer_kit.edition.approve`` - the Approver. Approves or rejects. NOT
  implied by ``page.edit`` (AC-A9), so a Designer attempting to approve gets a
  403 including on their own Edition (AC-L3).
* ``dealer_kit.page.publish`` - whoever may move the published label. Marking
  an Edition ``done`` is what publishes it (AC-L7), and that slug's own
  description is "move the published label", so it is the one that guards it.
  Approving says the catalogue reads well; publishing decides when readers see
  it, and they are deliberately different rights.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.dealer_kit import Page
from app.schemas.dealer_kit import EditionCreateIn, EditionOut, EditionRejectIn
from app.services import status_service
from app.modules.dealer_kit.bootstrap import EDITION_ENTITY
from app.services.dealer_kit import edition_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("dealer_kit.page.view")
_EDIT = require_permission("dealer_kit.page.edit")
_APPROVE = require_permission("dealer_kit.edition.approve")
_PUBLISH = require_permission("dealer_kit.page.publish")


def _user_id(user: dict | None) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _out(db: Session, edition) -> EditionOut:
    """One Edition, with its status resolved to a human label.

    The label comes from the graph rather than a dict in here: the graph is
    where somebody renames a state, and a second copy of the vocabulary would
    disagree with the admin screen the first time they did.
    """
    graph = status_service.resolve_graph(db, EDITION_ENTITY, None)
    status_row = graph.by_key(edition.status_key)
    page_name = db.query(Page.name).filter(Page.id == edition.page_id).scalar()

    return EditionOut(
        id=edition.id,
        page_id=edition.page_id,
        page_name=page_name,
        name=edition.name,
        status=edition.status_key,
        status_label=status_row.label if status_row else edition.status_key,
        approved_version_id=edition.approved_version_id,
        done_version_id=edition.done_version_id,
        previous_edition_id=edition.previous_edition_id,
        submitted_at=edition.submitted_at,
        approved_at=edition.approved_at,
        rejection_reason=edition.rejection_reason,
        created_at=edition.created_at,
    )


@router.get("/editions", response_model=list[EditionOut])
def list_editions(
    page_id: Optional[UUID] = Query(None, alias="pageId"),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Every Edition, newest first. ``pageId`` narrows to one catalogue.

    Typed as a UUID at the edge so a malformed value is a 422 and never reaches
    a WHERE clause - the same rule the rest of this router follows.
    """
    return [
        _out(db, edition)
        for edition in svc.list_editions(db, page_id=str(page_id) if page_id else None)
    ]


@router.get("/editions/{edition_id}", response_model=EditionOut)
def get_edition(
    edition_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    return _out(db, svc.get_edition(db, edition_id))


@router.post("/editions", response_model=EditionOut, status_code=status.HTTP_201_CREATED)
def create_edition(
    payload: EditionCreateIn,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    """Start a revision cycle. 409 when the page already has one open."""
    edition = svc.create_edition(
        db,
        page_id=str(payload.page_id),
        name=payload.name,
        previous_edition_id=(
            str(payload.previous_edition_id) if payload.previous_edition_id else None
        ),
        user_id=_user_id(user),
    )
    return _out(db, edition)


@router.post("/editions/{edition_id}/submit", response_model=EditionOut)
def submit_edition(
    edition_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    """Designer: ready for somebody to look at."""
    return _out(db, svc.submit(db, edition_id, user_id=_user_id(user)))


@router.post("/editions/{edition_id}/approve", response_model=EditionOut)
def approve_edition(
    edition_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_APPROVE),
):
    """Approver: I have read this. Publishes NOTHING (AC-L7)."""
    return _out(db, svc.approve(db, edition_id, user_id=_user_id(user)))


@router.post("/editions/{edition_id}/reject", response_model=EditionOut)
def reject_edition(
    edition_id: str,
    payload: EditionRejectIn,
    db: Session = Depends(get_db),
    user: dict = Depends(_APPROVE),
):
    """Approver: no, and here is why. The reason is required."""
    return _out(
        db, svc.reject(db, edition_id, reason=payload.reason, user_id=_user_id(user))
    )


@router.post("/editions/{edition_id}/reopen", response_model=EditionOut)
def reopen_edition(
    edition_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_EDIT),
):
    """Designer picking rejected work back up. The reason stays on screen."""
    return _out(db, svc.reopen(db, edition_id, user_id=_user_id(user)))


@router.post("/editions/{edition_id}/publish", response_model=EditionOut)
def publish_edition(
    edition_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(_PUBLISH),
):
    """Move the published label and finish the Edition.

    The only transition that publishes anything, and the only one behind
    ``page.publish``.
    """
    return _out(db, svc.publish(db, edition_id, user_id=_user_id(user)))
