"""Publish the imported Container Status workbook as a retrievable document.

The import already retains the original upload (`import_jobs.source_file_key`), but
that copy is a tracing side-channel: it is reachable only through Import Job Details,
owner-only, and invisible to every tool that serves documents. So "send me the
container status" had no answer - the file existed and nothing could hand it over.

This registers the SAME stored object as an `attachments` row of type
`Container Status`. Deliberately not a second upload: one set of bytes, one storage
key, two references. A re-upload would double the storage and let the two copies
diverge the moment one of them is replaced.

Why an attachment rather than a bespoke endpoint plus a bespoke MCP tool: the
document surface already exists (`crm_resource_attachments_list`, the file library,
access levels, keyword aliases). Attaching to it means every future operational
workbook is an upload plus a type, not another tool to write and register.

`access_levels` is `["sorento_office"]` - the workbook carries costs, forwarders and
CIDB dates across every container. Dealers get container answers through
`crm_incoming_stock_list`, field by field; the raw sheet is internal.

Newest-wins: every import adds a row, and the newest by `uploaded_at` is the current
one. History is kept rather than overwritten, because "what did the sheet say last
Tuesday" is a real question when a date is disputed.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TYPE_NAME = "Container Status"
TYPE_CODE = "container_status"

#: What the sheet is called in the wild. Consumed by the attachment-type keyword
#: resolution so "container status", "shipping schedule", "eta list" all land here
#: without anyone knowing the exact filename.
KEYWORDS = [
    "container status",
    "container status list",
    "container list",
    "shipping schedule",
    "shipment schedule",
    "eta list",
    "container tracking sheet",
    "clearance list",
]

ACCESS_LEVELS = ["sorento_office"]


def ensure_attachment_type(db: Session) -> Optional[str]:
    """Return the Container Status attachment type id, creating it if absent.

    Idempotent, and never raises: a missing type means the workbook is not published
    this run, which is recoverable on the next import. Failing the import itself
    because a document could not be catalogued would be the wrong trade.
    """
    try:
        row = db.execute(
            text("SELECT id FROM attachment_types WHERE code = :code OR type_name = :name LIMIT 1"),
            {"code": TYPE_CODE, "name": TYPE_NAME},
        ).fetchone()
        if row:
            return str(row[0])

        new_id = str(uuid.uuid4())
        db.execute(
            text(
                """
                INSERT INTO attachment_types
                    (id, type_name, code, description, allowed_extensions, max_file_size_mb)
                VALUES (:id, :name, :code, :desc, :ext, :size)
                """
            ),
            {
                "id": new_id,
                "name": TYPE_NAME,
                "code": TYPE_CODE,
                "desc": (
                    "The hand-maintained container clearance workbook, as uploaded. "
                    "Internal: it carries costs and forwarders across every container."
                ),
                "ext": "xlsx,xlsm",
                "size": 25,
            },
        )
        logger.info("Created attachment type %s", TYPE_NAME)
        return new_id
    except Exception:  # noqa: BLE001 - cataloguing must not break an import
        logger.warning("Could not resolve the %s attachment type", TYPE_NAME, exc_info=True)
        return None


def publish_import_source(db: Session, job) -> Optional[str]:
    """Register a finished import's retained workbook as an attachment.

    Returns the attachment id, or None when there is nothing to publish (no retained
    file) or the attempt failed. Never raises - the import has already succeeded by
    the time this runs, and a 500 here would report that success as a failure.
    """
    key = getattr(job, "source_file_key", None)
    if not key:
        return None

    try:
        # Same storage key => same bytes. A row already pointing at it means this job
        # was published before (a retry, or a re-run of the backfill).
        existing = db.execute(
            text("SELECT id FROM attachments WHERE file_path = :key AND is_deleted = false LIMIT 1"),
            {"key": key},
        ).fetchone()
        if existing:
            return str(existing[0])

        type_id = ensure_attachment_type(db)
        if not type_id:
            return None

        attachment_id = str(uuid.uuid4())
        filename = getattr(job, "source_filename", None) or getattr(job, "filename", None) or "Container Status.xlsx"
        db.execute(
            text(
                """
                INSERT INTO attachments (
                    id, attachment_type_id, original_filename, stored_filename,
                    file_path, file_size_bytes, mime_type, uploaded_by, uploaded_at,
                    description, is_deleted, access_levels, storage_provider, company_id
                ) VALUES (
                    :id, :type_id, :orig, :stored,
                    :key, :size, :mime, :uploaded_by, now(),
                    :desc, false, CAST(:levels AS jsonb), :provider,
                    (SELECT company_id FROM import_jobs WHERE id = :job_id)
                )
                """
            ),
            {
                "id": attachment_id,
                "type_id": type_id,
                "orig": filename,
                "stored": filename,
                "key": key,
                "size": getattr(job, "source_file_size", None),
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "uploaded_by": getattr(job, "user_id", None),
                "desc": f"Container Status workbook imported on {getattr(job, 'created_at', '')}".strip(),
                "levels": __import__("json").dumps(ACCESS_LEVELS),
                "provider": getattr(job, "source_file_provider", None) or "s3",
                "job_id": str(job.id),
            },
        )
        db.commit()
        logger.info("Published container status workbook as attachment %s", attachment_id)
        return attachment_id
    except Exception:  # noqa: BLE001 - the import already succeeded
        db.rollback()
        logger.warning("Could not publish the container status workbook", exc_info=True)
        return None


def latest_document(db: Session) -> Optional[dict]:
    """The most recently imported workbook, or None when none has been published.

    Newest by `uploaded_at`: every import adds a row and the latest is the current
    sheet, so "the container status list" always means the freshest one.
    """
    try:
        row = db.execute(
            text(
                """
                SELECT a.id, a.original_filename, a.file_path, a.file_size_bytes,
                       a.storage_provider, a.uploaded_at
                FROM attachments a
                JOIN attachment_types t ON t.id = a.attachment_type_id
                WHERE (t.code = :code OR t.type_name = :name) AND a.is_deleted = false
                ORDER BY a.uploaded_at DESC
                LIMIT 1
                """
            ),
            {"code": TYPE_CODE, "name": TYPE_NAME},
        ).fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "filename": row[1],
            "key": row[2],
            "size": row[3],
            "provider": row[4],
            "uploaded_at": row[5],
        }
    except Exception:  # noqa: BLE001
        logger.warning("Could not resolve the latest container status document", exc_info=True)
        return None
