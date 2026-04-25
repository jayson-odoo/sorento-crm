"""Drain embedding jobs: Redis RQ queue + pending embedding_queue rows.

Runs process_embedding_queue_item so embedding_documents / embedding_chunks are written
and embedding_queue rows move to completed/skipped/dead_letter.

Usage:
  cd sorento_crm_backend && source venv/bin/activate
  python -m app.scripts.drain_embedding_queue

  python -m app.scripts.drain_embedding_queue --redis-batch 100 --db-batch 100

Env: REDIS_URL must match where jobs were enqueued. OPENAI_API_KEY required for embedding API.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import func

from app.database import SessionLocal
from app.models.embeddings import EmbeddingQueue
from app.config import settings
from app.services.queue_service import run_sync_rq_jobs
from app.services.embedding_worker import process_embedding_queue_item


def _drain_redis_batch(queue_name: str, max_jobs: int) -> tuple[int, int]:
    """Execute up to max_jobs queued RQ jobs (same pattern as task_scheduler)."""
    r = run_sync_rq_jobs(queue_name, max_jobs)
    return int(r["processed"]), int(r["queued_remaining"])


def _drain_db_batch(max_jobs: int) -> tuple[int, int]:
    """process_embedding_queue_item for pending rows with available_at <= now."""
    db = SessionLocal()
    try:
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        pending_before = (
            db.query(func.count(EmbeddingQueue.id))
            .filter(EmbeddingQueue.status == "pending", EmbeddingQueue.available_at <= now_naive)
            .scalar()
            or 0
        )
        ids = (
            db.query(EmbeddingQueue.id)
            .filter(EmbeddingQueue.status == "pending", EmbeddingQueue.available_at <= now_naive)
            .order_by(EmbeddingQueue.created_at.asc())
            .limit(max_jobs)
            .all()
        )
        ids = [str(row[0]) for row in ids]
    finally:
        db.close()

    processed = 0
    for qid in ids:
        try:
            process_embedding_queue_item(qid)
            processed += 1
        except Exception as e:
            print(f"[db] queue id {qid} error: {e}", flush=True)
    return processed, int(pending_before)


def _queue_status_counts() -> dict[str, int]:
    db = SessionLocal()
    try:
        rows = db.query(EmbeddingQueue.status, func.count(EmbeddingQueue.id)).group_by(EmbeddingQueue.status).all()
        return {str(k): int(v) for k, v in rows}
    finally:
        db.close()


def drain_embedding_queue_until_idle(
    *,
    queue_name: str | None = None,
    redis_batch: int = 50,
    db_batch: int = 50,
    max_rounds: int = 500_000,
    idle_exit_rounds: int = 2,
    log: bool = True,
) -> dict:
    """Run Redis RQ workers and DB fallback until no pending work. Callable from other scripts (e.g. seed)."""
    qname = queue_name or settings.embedding_queue_name
    total_redis = 0
    total_db = 0
    idle_streak = 0
    round_no = 0

    if log:
        print(
            json.dumps(
                {"redis_url": settings.redis_url, "queue": qname, "embedding_queue_before": _queue_status_counts()},
                indent=2,
            ),
            flush=True,
        )

    while round_no < max_rounds:
        round_no += 1
        step_redis, _ = _drain_redis_batch(qname, redis_batch)
        total_redis += step_redis
        if step_redis and log:
            idle_streak = 0
            print(
                json.dumps(
                    {
                        "round": round_no,
                        "phase": "redis",
                        "step_redis": step_redis,
                        "step_db": 0,
                        "total_redis": total_redis,
                        "total_db": total_db,
                        "embedding_queue": _queue_status_counts(),
                    }
                ),
                flush=True,
            )
        elif step_redis:
            idle_streak = 0

        step_db, _ = _drain_db_batch(db_batch)
        total_db += step_db
        if step_db and log:
            idle_streak = 0
            print(
                json.dumps(
                    {
                        "round": round_no,
                        "phase": "db",
                        "step_redis": 0,
                        "step_db": step_db,
                        "total_redis": total_redis,
                        "total_db": total_db,
                        "embedding_queue": _queue_status_counts(),
                    }
                ),
                flush=True,
            )
        elif step_db:
            idle_streak = 0

        if step_redis == 0 and step_db == 0:
            idle_streak += 1
            if idle_streak >= idle_exit_rounds:
                break

    out = {
        "done": True,
        "rounds": round_no,
        "total_redis": total_redis,
        "total_db": total_db,
        "embedding_queue_after": _queue_status_counts(),
    }
    if log:
        print(json.dumps(out, indent=2), flush=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Drain embedding Redis + DB queue until idle")
    parser.add_argument("--queue-name", default=None, help="RQ queue name (default: settings.embedding_queue_name)")
    parser.add_argument("--redis-batch", type=int, default=50, help="Max RQ jobs per inner step")
    parser.add_argument("--db-batch", type=int, default=50, help="Max DB pending rows per inner step")
    parser.add_argument("--max-rounds", type=int, default=500_000, help="Safety cap on outer iterations")
    parser.add_argument("--idle-exit-rounds", type=int, default=2, help="Stop after N consecutive rounds with no work")
    args = parser.parse_args()

    drain_embedding_queue_until_idle(
        queue_name=args.queue_name,
        redis_batch=args.redis_batch,
        db_batch=args.db_batch,
        max_rounds=args.max_rounds,
        idle_exit_rounds=args.idle_exit_rounds,
        log=True,
    )


if __name__ == "__main__":
    main()
