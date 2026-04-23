"""Embedding operations and observability endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.services.embedding_service import EmbeddingReadService, EmbeddingEventService
from app.services.embedding_backfill_service import EmbeddingBackfillService
from app.models.embeddings import EmbeddingQueue

router = APIRouter(prefix="/embeddings")


@router.get("/metrics", dependencies=[Depends(require_permission("system.settings.read"))])
def get_embedding_metrics(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = EmbeddingReadService(db)
    return {"queue": svc.queue_metrics()}


@router.get("/dead-letters", dependencies=[Depends(require_permission("system.settings.read"))])
def list_dead_letters(
    limit: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(EmbeddingQueue)
        .filter(EmbeddingQueue.status == "dead_letter")
        .order_by(EmbeddingQueue.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "data": [
            {
                "id": str(r.id),
                "source_type": r.source_type,
                "source_id": r.source_id,
                "event_type": r.event_type,
                "status": r.status,
                "retry_count": r.retry_count,
                "last_error": r.last_error,
                "created_at": r.created_at,
                "processed_at": r.processed_at,
            }
            for r in rows
        ]
    }


@router.post("/replay-dead-letters", dependencies=[Depends(require_permission("system.settings.update"))])
def replay_dead_letters(
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    replayed = EmbeddingReadService(db).replay_dead_letters(limit=limit)
    return {"replayed": replayed}


@router.post("/rebuild/{source_type}/{source_id}", dependencies=[Depends(require_permission("system.settings.update"))])
def request_rebuild(
    source_type: str,
    source_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = EmbeddingEventService(db).request_rebuild(source_type=source_type, source_id=source_id, triggered_by=current_user.get("id"))
    return {"id": str(item.id), "status": item.status}


@router.post("/backfill", dependencies=[Depends(require_permission("system.settings.update"))])
def backfill_embeddings(
    source: str = Query(
        "all",
        pattern="^(all|product|promotion|promotion_product|inbound_shipment|inbound_shipment_line|spo_allocation|picking_header|picking_line|product_attachment|promotion_attachment|attachment|form|schema_doc|order|order_status|order_line|mcp_tool)$",
    ),
    batch_size: int = Query(500, ge=1, le=5000),
    max_rows: int | None = Query(None, ge=1, le=1_000_000),
    dry_run: bool = Query(False),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return EmbeddingBackfillService(db).run(
        source=source,  # type: ignore[arg-type]
        batch_size=batch_size,
        max_rows=max_rows,
        dry_run=dry_run,
        triggered_by=current_user.get("id"),
    )
