"""Service for user downloads (async-generated exports surfaced in My Downloads)."""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.download import DownloadStatus, UserDownload

# How long a row may sit pending/processing before the drawer calls it failed.
# Export enqueues use job_timeout=600s, so this leaves ample headroom.
_STALE_AFTER = timedelta(minutes=20)


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DownloadService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: str,
        kind: str,
        filename: Optional[str] = None,
        source_entity_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
    ) -> UserDownload:
        row = UserDownload(
            user_id=str(user_id),
            kind=kind,
            filename=filename,
            source_entity_type=source_entity_type,
            source_entity_id=str(source_entity_id) if source_entity_id is not None else None,
            status=DownloadStatus.PENDING.value,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, download_id: str) -> Optional[UserDownload]:
        return self.db.query(UserDownload).filter(UserDownload.id == str(download_id)).first()

    def get_for_user(self, download_id: str, user_id: str) -> Optional[UserDownload]:
        return (
            self.db.query(UserDownload)
            .filter(UserDownload.id == str(download_id), UserDownload.user_id == str(user_id))
            .first()
        )

    def fail_stale(self, user_id: str) -> int:
        """Flip the user's long-stuck pending/processing rows to 'failed'.

        A row is only moved off 'pending' by the RQ task itself, so a job that
        never reaches the task body leaves the drawer spinning "Queued" forever.
        That is not hypothetical: a worker booted from a different worktree drained
        this stack's queues and died in ``import_attribute`` before the task ran,
        stranding every row it touched.

        The cutoff is comfortably past the 600s ``job_timeout`` used by the export
        enqueues, so a slow-but-alive job is never killed by this. Best-effort:
        a failure here must not break listing the downloads.
        """
        cutoff = _utc_naive_now() - _STALE_AFTER
        try:
            stale = (
                self.db.query(UserDownload)
                .filter(
                    UserDownload.user_id == str(user_id),
                    UserDownload.status.in_(
                        [DownloadStatus.PENDING.value, DownloadStatus.PROCESSING.value]
                    ),
                    UserDownload.created_at < cutoff,
                )
                .all()
            )
            for row in stale:
                row.status = DownloadStatus.FAILED.value
                row.error = (
                    "Generation never completed - the job did not run to completion. "
                    "Please try again."
                )
            if stale:
                self.db.commit()
            return len(stale)
        except Exception:  # noqa: BLE001 - never break the drawer over a sweep
            self.db.rollback()
            return 0

    def list_for_user(self, user_id: str, limit: int = 50) -> List[UserDownload]:
        # Sweep on read: the drawer polls this, so a dead job surfaces as failed
        # instead of spinning indefinitely.
        self.fail_stale(user_id)
        return (
            self.db.query(UserDownload)
            .filter(UserDownload.user_id == str(user_id))
            .order_by(UserDownload.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_for_user_by_source(
        self,
        user_id: str,
        source_entity_type: str,
        source_entity_id: str,
        limit: int = 50,
    ) -> List[UserDownload]:
        """The current user's downloads tied to one source entity (newest first)."""
        self.fail_stale(user_id)
        return (
            self.db.query(UserDownload)
            .filter(
                UserDownload.user_id == str(user_id),
                UserDownload.source_entity_type == source_entity_type,
                UserDownload.source_entity_id == str(source_entity_id),
            )
            .order_by(UserDownload.created_at.desc())
            .limit(limit)
            .all()
        )

    def count_map_for_user(
        self,
        user_id: str,
        source_entity_type: str,
        source_entity_ids: Sequence[str],
    ) -> Dict[str, int]:
        """{source_entity_id: count} of the user's downloads for the given ids.

        One grouped query for the whole page - avoids an N+1 count per row.
        """
        ids = [str(i) for i in source_entity_ids if i is not None]
        if not user_id or not ids:
            return {}
        rows = (
            self.db.query(UserDownload.source_entity_id, func.count(UserDownload.id))
            .filter(
                UserDownload.user_id == str(user_id),
                UserDownload.source_entity_type == source_entity_type,
                UserDownload.source_entity_id.in_(ids),
            )
            .group_by(UserDownload.source_entity_id)
            .all()
        )
        return {str(k): int(v) for k, v in rows}

    def mark_processing(self, download_id: str) -> Optional[UserDownload]:
        row = self.get(download_id)
        if row is None:
            return None
        row.status = DownloadStatus.PROCESSING.value
        self.db.commit()
        self.db.refresh(row)
        return row

    def mark_ready(
        self, download_id: str, *, storage_provider: str, storage_key: str, filename: Optional[str] = None
    ) -> Optional[UserDownload]:
        row = self.get(download_id)
        if row is None:
            return None
        row.status = DownloadStatus.READY.value
        row.storage_provider = storage_provider
        row.storage_key = storage_key
        if filename:
            row.filename = filename
        row.error = None
        row.ready_at = _utc_naive_now()
        self.db.commit()
        self.db.refresh(row)
        return row

    def mark_failed(self, download_id: str, error: str) -> Optional[UserDownload]:
        row = self.get(download_id)
        if row is None:
            return None
        row.status = DownloadStatus.FAILED.value
        row.error = (error or "")[:2000]
        self.db.commit()
        self.db.refresh(row)
        return row


def purge_expired_downloads(db, retention_days: int = 30, now=None) -> dict:
    """Delete download rows and their stored objects past the retention window.

    Nothing has ever purged `user_downloads`. With `complaint_pdf` as the only producer
    that went unnoticed; adding a chat-history CSV export - the largest artifact the
    system produces - makes it a real cost. Applies to every `kind`, not just the new one.

    Storage deletion is best-effort per row: an object that is already gone, or a
    provider hiccup, must not block reclaiming the rest.
    """
    import logging
    from datetime import datetime, timedelta

    from app.models.download import UserDownload
    from app.services.storage_router import get_backend

    log = logging.getLogger(__name__)
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=max(1, int(retention_days)))

    rows = db.query(UserDownload).filter(UserDownload.created_at < cutoff).all()
    deleted = objects_removed = errors = 0

    for row in rows:
        if row.storage_key:
            try:
                get_backend(row.storage_provider or "s3").delete_file(row.storage_key)
                objects_removed += 1
            except Exception as e:  # noqa: BLE001 - reclaim the row regardless
                errors += 1
                log.warning(
                    "purge_expired_downloads: could not delete %s (%s): %s",
                    row.storage_key, row.storage_provider, e,
                )
        db.delete(row)
        deleted += 1

    db.commit()
    return {
        "cutoff": cutoff.isoformat(),
        "rows_deleted": deleted,
        "objects_removed": objects_removed,
        "storage_errors": errors,
    }
