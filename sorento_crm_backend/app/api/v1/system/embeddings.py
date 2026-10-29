"""Embedding operations and observability endpoints."""
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
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
    if item is None:
        return {"id": None, "status": "skipped"}  # not a source the platform embeds any more
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


# ---------------------------------------------------------------------------------------------------------------
# LOOKUP-EMBED-CENTRAL: the Embeddings screen's record side (the lookup-word side lives on the chatbot doorway).
# ---------------------------------------------------------------------------------------------------------------
from app.tasks.embedding_backfill import RECORDS_BACKFILL_RUNNING_KEY, RECORDS_BACKFILL_STOP_KEY  # noqa: E402
STOP_FLAG_SECONDS = 3600


def _backfill_running() -> bool:
    from app.services import queue_service

    try:
        return bool(queue_service.redis_conn.get(RECORDS_BACKFILL_RUNNING_KEY))
    except Exception:  # noqa: BLE001 - no Redis, no running job to show
        return False


@router.get("/overview", dependencies=[Depends(require_permission("master_data.lookup_sets.view"))])
def embeddings_overview(db: Session = Depends(get_db)):
    from sqlalchemy import func, text

    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.models.user import SystemSetting
    from app.services import embedding_backfill_service as backfill
    from app.services.embedding_settings import RECORD_KEEP_SET, records_search_model, resolve_embedder

    provider, model = resolve_embedder(db)
    row = db.query(SystemSetting.embedding_backfill_rpm).first()
    rpm = (row[0] if row else None) or backfill.DEFAULT_BACKFILL_RPM

    total = db.execute(
        text(
            "SELECT COALESCE(SUM(array_length(string_to_array(body_text, E'\\n'), 1)), 0) "
            "FROM embedding_documents WHERE source_type = 'lookup_word' AND is_active"
        )
    ).scalar()
    with_vector = (
        db.query(func.count(EmbeddingChunk.id))
        .filter(
            EmbeddingChunk.source_type == "lookup_word",
            EmbeddingChunk.model_name == model,
            EmbeddingChunk.is_current.is_(True),
        )
        .scalar()
    )
    documents = dict(
        db.query(EmbeddingDocument.source_type, func.count(EmbeddingDocument.id))
        .filter(EmbeddingDocument.is_active.is_(True), EmbeddingDocument.source_type.in_(sorted(RECORD_KEEP_SET)))
        .group_by(EmbeddingDocument.source_type)
        .all()
    )
    chunks: dict[str, dict[str, int]] = {}
    for source_type, model_name, n in (
        db.query(EmbeddingChunk.source_type, EmbeddingChunk.model_name, func.count(EmbeddingChunk.id))
        .filter(EmbeddingChunk.is_current.is_(True), EmbeddingChunk.source_type.in_(sorted(RECORD_KEEP_SET)))
        .group_by(EmbeddingChunk.source_type, EmbeddingChunk.model_name)
        .all()
    ):
        chunks.setdefault(source_type, {})[model_name] = int(n)
    remaining = backfill._count_remaining(db, model)
    failed = backfill.count_failed(db, model)
    return {
        "setting": {"provider": provider, "model": model, "backfill_rpm": int(rpm)},
        "records_search_model": records_search_model(db),
        "lookup": {"texts_total": int(total or 0), "texts_with_vector": int(with_vector or 0)},
        "records": [
            {"source_type": s, "documents": int(documents.get(s, 0)), "chunks_by_model": chunks.get(s, {})}
            for s in sorted(RECORD_KEEP_SET)
        ],
        "guard": {
            "target_model": model,
            "ready": remaining == 0,
            "remaining": remaining,
            "failed": failed,
            "running": _backfill_running(),
        },
    }


class RecordsBackfillBody(BaseModel):
    action: Literal["start", "stop"]


@router.post(
    "/records-backfill",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("system.settings.update"))],
)
def records_backfill(body: RecordsBackfillBody, db: Session = Depends(get_db)):
    # Looked up at call time: the queue and its Redis connection are patched in tests and never bound here.
    from app.services import queue_service
    from app.tasks.embedding_backfill import run_records_backfill

    if body.action == "stop":
        queue_service.redis_conn.set(RECORDS_BACKFILL_STOP_KEY, "1", ex=STOP_FLAG_SECONDS)
        return {"job_id": None}
    try:
        queue_service.redis_conn.delete(RECORDS_BACKFILL_STOP_KEY)
    except Exception:  # noqa: BLE001 - a stale flag only stops the run early; the job also clears it
        pass
    job = queue_service.enqueue_job(run_records_backfill, queue_name="imports")
    return {"job_id": getattr(job, "id", None)}
