"""Showroom walkthroughs: panoramic stops built from video or photos.

PLAN-showroom-walkthrough-28oct.md. Permissions reuse the page split, the same
call the flyer routes made: reads carry ``dealer_kit.page.view``, writes carry
``dealer_kit.page.edit``. A new slug would need a grant sweep before any role
held it, and a walkthrough is catalogue material like a page.

Adding a stop answers **202** with the stop in ``processing``: stitching is
tens of CPU seconds and runs on the ``walkthrough`` queue.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.dealer_kit import (
    WalkthroughIn,
    WalkthroughOut,
    WalkthroughStopOut,
    WalkthroughSummary,
)
from app.services.dealer_kit import walkthrough_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("dealer_kit.page.view")
_EDIT = require_permission("dealer_kit.page.edit")

_CHUNK_BYTES = 1024 * 1024


def _user_id(user: dict | None) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _stop_out(stop) -> WalkthroughStopOut:
    return WalkthroughStopOut(
        id=stop.id,
        position=stop.position,
        title=stop.title,
        status=stop.status,
        error_message=stop.error_message,
        h_fov_deg=float(stop.h_fov_deg) if stop.h_fov_deg is not None else None,
        v_fov_deg=float(stop.v_fov_deg) if stop.v_fov_deg is not None else None,
        created_at=stop.created_at,
        finished_at=stop.finished_at,
    )


def _summary(walkthrough) -> WalkthroughSummary:
    return WalkthroughSummary(
        id=walkthrough.id,
        name=walkthrough.name,
        stop_count=len(walkthrough.stops),
        processing_count=sum(
            1 for stop in walkthrough.stops if stop.status == svc.StopStatus.PROCESSING
        ),
        created_at=walkthrough.created_at,
        updated_at=walkthrough.updated_at,
    )


def _detail(walkthrough) -> WalkthroughOut:
    return WalkthroughOut(
        **_summary(walkthrough).model_dump(),
        stops=[_stop_out(stop) for stop in walkthrough.stops],
    )


@router.get("/walkthroughs", response_model=list[WalkthroughSummary])
def list_walkthroughs(db: Session = Depends(get_db), _user: dict = Depends(_VIEW)):
    return [_summary(w) for w in svc.list_walkthroughs(db)]


@router.post(
    "/walkthroughs", response_model=WalkthroughOut, status_code=status.HTTP_201_CREATED
)
def create_walkthrough(
    payload: WalkthroughIn, db: Session = Depends(get_db), user: dict = Depends(_EDIT)
):
    return _detail(svc.create_walkthrough(db, name=payload.name, user_id=_user_id(user)))


@router.get("/walkthroughs/{walkthrough_id}", response_model=WalkthroughOut)
def get_walkthrough(
    walkthrough_id: str, db: Session = Depends(get_db), _user: dict = Depends(_VIEW)
):
    return _detail(svc.get_walkthrough(db, walkthrough_id))


@router.patch("/walkthroughs/{walkthrough_id}", response_model=WalkthroughOut)
def rename_walkthrough(
    walkthrough_id: str,
    payload: WalkthroughIn,
    db: Session = Depends(get_db),
    _user: dict = Depends(_EDIT),
):
    return _detail(svc.rename_walkthrough(db, walkthrough_id, name=payload.name))


@router.delete("/walkthroughs/{walkthrough_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_walkthrough(
    walkthrough_id: str, db: Session = Depends(get_db), _user: dict = Depends(_EDIT)
):
    svc.delete_walkthrough(db, walkthrough_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/walkthroughs/{walkthrough_id}/stops",
    response_model=WalkthroughStopOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_stop(
    walkthrough_id: str,
    files: list[UploadFile] = File(...),
    title: str = Form(""),
    db: Session = Depends(get_db),
    _user: dict = Depends(_EDIT),
):
    """One video of a slow turn on the spot, or overlapping photos, or one 360 photo.

    ``async def`` only for the chunked read, which refuses an oversized upload
    as the bytes arrive; the staging PUTs and the INSERT run in the threadpool.
    """
    svc.assert_upload_acceptable([(f.filename or "", 0) for f in files])
    loaded: list[tuple[str, bytes]] = []
    total = 0
    for upload in files:
        chunks: list[bytes] = []
        while chunk := await upload.read(_CHUNK_BYTES):
            total += len(chunk)
            svc.assert_within_limit(total)
            chunks.append(chunk)
        loaded.append((upload.filename or "upload", b"".join(chunks)))

    stop = await run_in_threadpool(
        svc.add_stop, db, walkthrough_id, title=title, files=loaded
    )
    return _stop_out(stop)


@router.get("/walkthroughs/{walkthrough_id}/stops/{stop_id}/panorama")
def get_panorama(
    walkthrough_id: str,
    stop_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The panorama JPEG, through the backend so WebGL never needs bucket CORS."""
    return Response(
        content=svc.panorama_bytes(db, walkthrough_id, stop_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete(
    "/walkthroughs/{walkthrough_id}/stops/{stop_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_stop(
    walkthrough_id: str,
    stop_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_EDIT),
):
    svc.get_stop(db, walkthrough_id, stop_id)
    svc.delete_stop(db, stop_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
