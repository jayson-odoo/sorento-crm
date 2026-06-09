"""Service for user downloads (async-generated exports surfaced in My Downloads)."""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.download import DownloadStatus, UserDownload


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

    def list_for_user(self, user_id: str, limit: int = 50) -> List[UserDownload]:
        return (
            self.db.query(UserDownload)
            .filter(UserDownload.user_id == str(user_id))
            .order_by(UserDownload.created_at.desc())
            .limit(limit)
            .all()
        )

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
