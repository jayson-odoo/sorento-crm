"""Service for generic import logs."""
from typing import Optional, Any
from sqlalchemy.orm import Session
from app.models.import_log import ImportLog
from app.schemas.common import ListResponse
from app.schemas.import_log import ImportLogResponse
from app.services.error_handler import handle_not_found


class ImportLogService:
    """Service for import log operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_import_logs(self, page: int = 1, limit: int = 50, entity_type: Optional[str] = None):
        """List import logs with pagination and optional entity filter."""
        q = self.db.query(ImportLog)
        if entity_type:
            q = q.filter(ImportLog.entity_type == entity_type)

        total = q.count()
        offset = (page - 1) * limit
        entries = q.order_by(ImportLog.imported_at.desc()).offset(offset).limit(limit).all()

        return ListResponse(
            data=[ImportLogResponse.model_validate(entry) for entry in entries],
            pagination={"total": total, "page": page, "limit": limit},
            empty=total == 0
        )

    def get_import_log(self, log_id: str):
        """Get a single import log by ID."""
        log = self.db.query(ImportLog).filter(ImportLog.id == log_id).first()
        if not log:
            raise handle_not_found("Import Log", log_id)
        return ImportLogResponse.model_validate(log)

    def create_import_log(
        self,
        entity_type: str,
        entity_table: str,
        import_session_id: str,
        filename: Optional[str],
        import_type: str,
        total_rows: int,
        successful_rows: int,
        created_rows: int,
        updated_rows: int,
        failed_rows: int,
        skipped_rows: int,
        warnings: Optional[Any],
        errors: Optional[Any],
        summary: Optional[Any],
        imported_by: Optional[str],
        duration_ms: Optional[int],
    ):
        """Create an import log entry."""
        log = ImportLog(
            import_session_id=import_session_id,
            entity_type=entity_type,
            entity_table=entity_table,
            filename=filename,
            import_type=import_type,
            total_rows=total_rows,
            successful_rows=successful_rows,
            created_rows=created_rows,
            updated_rows=updated_rows,
            failed_rows=failed_rows,
            skipped_rows=skipped_rows,
            warnings=warnings,
            errors=errors,
            summary=summary,
            imported_by=imported_by,
            duration_ms=duration_ms,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return ImportLogResponse.model_validate(log)
