"""`/api/v1/ideation/*`: the Ideas gateway (PLAN-ideation-in-crm section 10, AC-A-01..A-08).

Each route checks the CRM permission, then forwards to the ss embed route of the same shape as
the calling user (`ideation_gateway_service`). View = `ideation.board.view`, manage =
`ideation.ideas.manage`. Archive, Delete and comment delete are not here: they are pending
actions (`record_actions`).
"""
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.services.error_handler import AppException
from app.services.ideation_gateway_service import call_ss, relay

VIEW = "ideation.board.view"
MANAGE = "ideation.ideas.manage"

router = APIRouter()

_view = Depends(require_permission_with_api_key(VIEW))
_manage = Depends(require_permission_with_api_key(MANAGE))


def _forward(db: Session, user: dict, method: str, path: str, **kw: Any) -> Response:
    return relay(call_ss(db, user, method, path, **kw))


def _non_empty_body(payload: dict) -> dict:
    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        raise AppException(422, "Comment cannot be empty.", code="VALIDATION_ERROR")
    return payload


# ---- reads (the literal paths come before `/ideas/{id}`) --------------------------------------


@router.get("/ideas")
def list_ideas(request: Request, user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "GET", "/embed/ideas", params=dict(request.query_params))


@router.get("/ideas/board")
def get_board(user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "GET", "/embed/board")


@router.get("/ideas/{idea_id}")
def get_idea(idea_id: str, user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "GET", f"/embed/ideas/{idea_id}")


@router.get("/ideas/{idea_id}/merged")
def get_merged(idea_id: str, user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "GET", f"/embed/ideas/{idea_id}/merged")


# ---- capture and vote (view) ------------------------------------------------------------------


@router.post("/ideas", status_code=201)
def create_idea(payload: dict = Body(...), user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "POST", "/embed/ideas", json=payload)


@router.post("/ideas/{idea_id}/vote")
def vote(idea_id: str, user: dict = _view, db: Session = Depends(get_db)):
    # Upvote only: whatever the client sent, the direction is always up.
    return _forward(db, user, "POST", f"/embed/ideas/{idea_id}/vote", json={"dir": "up"})


# ---- triage (manage) --------------------------------------------------------------------------


@router.patch("/ideas/{idea_id}")
def update_idea(idea_id: str, payload: dict = Body(...), user: dict = _manage, db: Session = Depends(get_db)):
    return _forward(db, user, "PATCH", f"/embed/ideas/{idea_id}", json=payload)


@router.post("/ideas/{idea_id}/status")
def move_status(idea_id: str, payload: dict = Body(...), user: dict = _manage, db: Session = Depends(get_db)):
    return _forward(db, user, "POST", f"/embed/ideas/{idea_id}/status", json=payload)


@router.put("/ideas/reorder")
def reorder(payload: dict = Body(...), user: dict = _manage, db: Session = Depends(get_db)):
    return _forward(db, user, "PUT", "/embed/ideas/reorder", json=payload)


@router.post("/ideas/merge")
def merge(payload: dict = Body(...), user: dict = _manage, db: Session = Depends(get_db)):
    return _forward(db, user, "POST", "/embed/ideas/merge", json=payload)


@router.post("/ideas/promote", status_code=201)
def promote(payload: dict = Body(...), user: dict = _manage, db: Session = Depends(get_db)):
    return _forward(db, user, "POST", "/embed/ideas/promote", json=payload)


@router.post("/ideas/{idea_id}/unmerge")
def unmerge(idea_id: str, user: dict = _manage, db: Session = Depends(get_db)):
    return _forward(db, user, "POST", f"/embed/ideas/{idea_id}/unmerge")


# ---- attachments (view: capture lets every viewer attach) -------------------------------------


@router.post("/ideas/{idea_id}/attachments", status_code=201)
def upload_attachment(
    idea_id: str,
    file: UploadFile = File(...),
    user: dict = _view,
    db: Session = Depends(get_db),
):
    content = file.file.read()
    files = {"file": (file.filename or "file", content, file.content_type or "application/octet-stream")}
    return _forward(db, user, "POST", f"/embed/ideas/{idea_id}/attachments", files=files)


@router.get("/ideas/{idea_id}/attachments/{attachment_id}/content")
def attachment_content(idea_id: str, attachment_id: str, user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "GET", f"/embed/ideas/{idea_id}/attachments/{attachment_id}/content")


# ---- comments (view; ss decides own-or-moderator) ---------------------------------------------


@router.get("/ideas/{idea_id}/comments")
def list_comments(idea_id: str, user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "GET", f"/embed/ideas/{idea_id}/comments")


@router.post("/ideas/{idea_id}/comments", status_code=201)
def post_comment(idea_id: str, payload: dict = Body(...), user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "POST", f"/embed/ideas/{idea_id}/comments", json=_non_empty_body(payload))


@router.patch("/ideas/{idea_id}/comments/{comment_id}")
def edit_comment(
    idea_id: str, comment_id: str, payload: dict = Body(...), user: dict = _view, db: Session = Depends(get_db)
):
    return _forward(
        db, user, "PATCH", f"/embed/ideas/{idea_id}/comments/{comment_id}", json=_non_empty_body(payload)
    )


@router.delete("/ideas/{idea_id}/comments/{comment_id}", status_code=204)
def delete_comment(idea_id: str, comment_id: str, user: dict = _view, db: Session = Depends(get_db)):
    return _forward(db, user, "DELETE", f"/embed/ideas/{idea_id}/comments/{comment_id}")
