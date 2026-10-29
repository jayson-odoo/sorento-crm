"""RQ task: re-embed the keep-set records with the configured embedder, then let the guard flip the search
model (LOOKUP-EMBED-CENTRAL). Runs on the `imports` queue; the worker has no reload, restart it after edits."""
from __future__ import annotations

import logging
import uuid

from app.database import SessionLocal
from app.models.base import set_company_scope

logger = logging.getLogger(__name__)


RECORDS_BACKFILL_STOP_KEY = "lec:records_backfill:stop"


def _stop_requested() -> bool:
    """The Stop button's flag (Redis); a Redis failure never stops or breaks the run."""
    try:
        from app.services import queue_service

        return bool(queue_service.redis_conn.get(RECORDS_BACKFILL_STOP_KEY))
    except Exception:  # noqa: BLE001
        return False


RECORDS_BACKFILL_RUNNING_KEY = "lec:records_backfill:running"
#: The running flag outlives a dead worker by at most this; each batch refreshes it.
RUNNING_TTL_SECONDS = 180
_RELEASE_IF_OURS = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


_NO_FLAG = ""  # Redis unavailable: the job runs without a flag rather than not at all


def _claim_running() -> str | None:
    """Raise the running flag if nobody else's is up; the token it carries is this job's. None when another job owns
    it (this one must not run); `_NO_FLAG` when Redis cannot say."""
    try:
        from app.services import queue_service

        token = uuid.uuid4().hex
        if queue_service.redis_conn.set(RECORDS_BACKFILL_RUNNING_KEY, token, nx=True, ex=RUNNING_TTL_SECONDS):
            return token
        return None
    except Exception:  # noqa: BLE001 - no Redis, no flag
        return _NO_FLAG


def _release_running(token: str | None) -> None:
    """Take the flag down only if this job owns it."""
    if not token:
        return
    try:
        from app.services import queue_service

        queue_service.redis_conn.eval(_RELEASE_IF_OURS, 1, RECORDS_BACKFILL_RUNNING_KEY, token)
    except Exception:  # noqa: BLE001
        pass


def _stop_or_refresh(token: str | None):
    def check() -> bool:
        if token:
            try:
                from app.services import queue_service

                queue_service.redis_conn.expire(RECORDS_BACKFILL_RUNNING_KEY, RUNNING_TTL_SECONDS)
            except Exception:  # noqa: BLE001
                pass
        return _stop_requested()

    return check


def run_records_backfill(model: str | None = None) -> dict:
    from app.models.embeddings import EmbeddingDocument  # noqa: F401  (mapper registration)
    from app.services.embedding_backfill_service import apply_search_model_guard, backfill_records
    from app.services.embedding_settings import resolve_embedder

    run_token = _claim_running()
    if run_token is None:
        logger.info("records backfill: another job holds the running flag; this one exits")
        return {"skipped": "another backfill is running"}
    db = SessionLocal()
    try:
        set_company_scope(db, None)  # a system job: products of every company
        if model is None:
            _provider, model = resolve_embedder(db)
        result = backfill_records(db, model, should_stop=_stop_or_refresh(run_token))
        flipped = apply_search_model_guard(db, model)
        logger.info(
            "records backfill %s: embedded=%s failed=%s remaining=%s flipped=%s",
            model, result.embedded, result.failed, result.remaining, flipped,
        )
        return {
            "model": model, "embedded": result.embedded, "failed": result.failed,
            "remaining": result.remaining, "flipped": flipped,
        }
    finally:
        _release_running(run_token)
        db.close()

