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

Exactly one live row PER COMPANY. Each import publishes the new sheet and TRASHES
that company's previous ones (`enforce_single_current`), because the workbook is
re-uploaded whole: an older copy is not history, it is a stale answer with a
current-looking name. Six identical "Container Status 2026.xlsx" rows gave entity
resolution nothing to choose between. Sorento and Mocha each keep their own current
sheet, so one company's import can never trash the other's. Trashed rows are
soft-deleted, so a superseded sheet is still recoverable and its import job still
holds its own retained copy.

Every published row is OWNED by a company: `publish_import_source` coalesces a
missing import-job company snapshot onto the incumbent company rather than writing
NULL. A NULL-company workbook would be visible to every company at once (the
`Attachment.__company_shared__` predicate treats NULL as shared) and, being ranked
only against other NULLs, could never be superseded by anyone's import - exactly the
two-indistinguishable-currents ambiguity this module exists to remove. The NULL
partition in `enforce_single_current` and the NULL ordering in `latest_document` are
now defensive leftovers, not an expected steady state: publication cannot create one
and migration 323 stamped the existing ones.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope import DEFAULT_COMPANY_ID

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


def enforce_single_current(db: Session) -> int:
    """Trash every Container Status workbook except each company's newest.

    Returns how many were trashed.

    A company only ever has ONE current container status list: the sheet is
    re-uploaded in full each time, so an older copy is not history, it is a wrong
    answer that still looks right. Six of them sat in the library after six
    imports, all named "Container Status 2026.xlsx" and indistinguishable, so an
    entity resolve had no way to choose - it returned six rows, or the wrong one.

    The invariant is PER COMPANY, not global. Rows are ranked inside their own
    `company_id` partition and rank 1 survives, so a Mocha import trashes Mocha's
    older sheets and leaves Sorento's current one live.

    `PARTITION BY` groups all NULLs together. That is defensive leftover, not an
    expected steady state: `publish_import_source` coalesces a missing company onto
    the incumbent company so it cannot write a NULL, and migration 323 stamped the
    NULL rows that already existed. The partition stays because a NULL row is
    ranked only against other NULLs, so should one ever appear it is contained
    instead of colliding with a real company's current sheet.

    Keyed on "newest by uploaded_at survives", NOT on an id the caller passes in.
    Re-publishing an older job (a retry, a backfill re-run) would otherwise name a
    stale sheet as the keeper and trash the current one - the exact inversion this
    exists to prevent. Stated as an invariant, it is also idempotent: run it any
    number of times and every company still holds exactly one live workbook, and
    the repeat run trashes nothing.

    No session-scope filter here, on purpose. This is a global invariant sweep,
    not a read. It runs post-commit in the RQ worker under the single importing
    company's scope, and it has to hold as a global invariant whoever runs it:
    partitioning gives the right answer under every scope, whereas a
    scope-filtered variant would silently stop being idempotent for the other
    companies. `company_sql_predicate` is for reads that must respect the caller;
    this is not one.

    One read DOES change shape because of the per-company rule: an all-companies
    caller (an `X-API-Key` request with no `contact_id` / `space_id`, which
    resolves to scope `None`) now sees one current workbook per company where it
    used to see exactly one globally, so it must pass contact identity to get a
    single answer.

    Soft delete, the same trash the UI writes. The bytes and rows stay recoverable
    and the import jobs are untouched; the copies just leave the library, the MCP
    tool and entity resolution.
    """
    from datetime import datetime

    try:
        result = db.execute(
            text(
                """
                UPDATE attachments
                SET is_deleted = true, deleted_at = :now
                WHERE id IN (
                    SELECT id FROM (
                        SELECT a.id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY a.company_id
                                   -- id as tie-breaker: two workbooks published
                                   -- in the same transaction share `now()` to the
                                   -- microsecond, and without it the "newest" is
                                   -- whichever the planner happens to emit first.
                                   ORDER BY a.uploaded_at DESC, a.id DESC
                               ) AS rn
                        FROM attachments a
                        JOIN attachment_types t ON t.id = a.attachment_type_id
                        WHERE (t.code = :code OR t.type_name = :name)
                          AND a.is_deleted = false
                    ) ranked
                    WHERE ranked.rn > 1
                )
                """
            ),
            {"now": datetime.utcnow(), "code": TYPE_CODE, "name": TYPE_NAME},
        )
        db.commit()
        count = result.rowcount or 0
        if count:
            logger.info("Trashed %s superseded container status workbook(s)", count)
        return count
    except Exception:  # noqa: BLE001 - the new row is already published
        db.rollback()
        logger.warning("Could not trash superseded container status workbooks", exc_info=True)
        return 0


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
        # Match on the key as a SUFFIX: rows written before this stored the bare
        # key, rows written now store the CDN URL, and both point at the same
        # object. Comparing the raw key only would republish every old one as a
        # duplicate the first time this runs after the change.
        # Deliberately NOT filtered on `is_deleted = false`. A live-only probe
        # misses a row that `enforce_single_current` already trashed, so
        # re-running that job falls through to the INSERT and writes a SECOND row
        # for the same key with `uploaded_at = now()` - which then ranks as the
        # company's newest and trashes its genuine current workbook. That is the
        # exact inversion `enforce_single_current` documents as impossible.
        existing = db.execute(
            text(
                """
                SELECT id FROM attachments
                WHERE file_path = :key OR file_path LIKE :suffix
                LIMIT 1
                """
            ),
            {"key": key, "suffix": f"%/{key}"},
        ).fetchone()
        if existing:
            # Re-run of an already-published job. Return the row it produced,
            # whatever state it is in.
            # A TRASHED match STAYS TRASHED - it is not restored here. It was
            # soft-deleted either because a newer workbook superseded it inside
            # its own company partition or because someone trashed it on purpose,
            # and re-running an old import job must undo neither. Restoring it
            # would also just put two live rows in one partition for
            # `enforce_single_current` to collapse again on the next line.
            # Re-assert the invariant anyway - it keeps the newest, so a retry
            # cannot promote this older sheet.
            enforce_single_current(db)
            return str(existing[0])

        type_id = ensure_attachment_type(db)
        if not type_id:
            return None

        provider = getattr(job, "source_file_provider", None) or "s3"
        # Store the CDN URL, not the raw storage key. `import_jobs.source_file_key`
        # is a key, but every other attachment row holds the full
        # "https://<cdn>/<key>" that the upload path writes - and consumers read
        # `file_path` as an address, not as something to resolve. A bare key here
        # reached the MCP envelope as a domain-less string that no client can
        # fetch, and looked like a signing bug rather than a shape mismatch.
        # Falls back to the key if the CDN is unconfigured: a wrong-looking path
        # is recoverable, a failed publish loses the document.
        try:
            from app.services.storage_router import cdn_base_url

            file_path = cdn_base_url(provider, key) or key
        except Exception:  # noqa: BLE001
            logger.warning("Could not build a CDN URL for %s", key, exc_info=True)
            file_path = key

        attachment_id = str(uuid.uuid4())
        filename = getattr(job, "source_filename", None) or getattr(job, "filename", None) or "Container Status.xlsx"
        # The import job's company snapshot can be NULL: `JobService.
        # active_company_id_from_scope` snapshots NULL whenever the enqueue had no
        # single-company scope (the n8n / X-API-Key path). A NULL here would be
        # actively wrong for THIS document. A container status workbook is an OWNED
        # operational document, not a shared form attachment, and
        # `Attachment.__company_shared__` makes a NULL row visible to every company
        # at once while `enforce_single_current` ranks NULLs only against each other
        # - so no company's future import could ever supersede it, and a
        # single-company caller would resolve two workbooks. The codebase already
        # answers "a None-scope owned write belongs to the incumbent company"
        # (`resolve_write_company_id`, and migration 306's DB DEFAULT on the owned
        # tables); this follows that rule rather than inventing a new one.
        #
        # Read the snapshot first so the fallback is DIAGNOSABLE. It is right for a
        # genuine system write, but `active_company_id_from_scope` also snapshots
        # NULL for UNSET / empty / multi-company scopes and on any scope-resolution
        # error, where `resolve_write_company_id` would have raised. So a
        # Mocha-only user whose scope failed to resolve can enqueue an import and
        # have the workbook publish as Sorento's. Fixing that belongs at enqueue;
        # until then the warning is what makes the mis-attribution visible.
        job_company_id = db.execute(
            text("SELECT company_id FROM import_jobs WHERE id = :job_id"),
            {"job_id": str(job.id)},
        ).scalar()
        if job_company_id is None:
            logger.warning(
                "Import job %s carried no company snapshot; attributing container "
                "status workbook %s to the incumbent company %s",
                job.id,
                attachment_id,
                DEFAULT_COMPANY_ID,
            )
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
                    COALESCE(
                        (SELECT company_id FROM import_jobs WHERE id = :job_id),
                        CAST(:default_company_id AS uuid)
                    )
                )
                """
            ),
            {
                "id": attachment_id,
                "type_id": type_id,
                "orig": filename,
                "stored": filename,
                "key": file_path,
                "size": getattr(job, "source_file_size", None),
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "uploaded_by": getattr(job, "user_id", None),
                "desc": f"Container Status workbook imported on {getattr(job, 'created_at', '')}".strip(),
                "levels": __import__("json").dumps(ACCESS_LEVELS),
                "provider": provider,
                "job_id": str(job.id),
                "default_company_id": DEFAULT_COMPANY_ID,
            },
        )
        db.commit()
        logger.info(
            "Published container status workbook as attachment %s for company %s",
            attachment_id,
            job_company_id or DEFAULT_COMPANY_ID,
        )
        # Only one workbook is ever current per company. Runs AFTER the commit so a
        # failure here leaves the new row published rather than rolling it back.
        enforce_single_current(db)
        return attachment_id
    except Exception:  # noqa: BLE001 - the import already succeeded
        db.rollback()
        logger.warning("Could not publish the container status workbook", exc_info=True)
        return None


def latest_document(db: Session) -> Optional[dict]:
    """The caller's most recently imported workbook, or None when there is none.

    Newest by `uploaded_at`: every import adds a row and the latest is the current
    sheet, so "the container status list" always means the freshest one.

    Company-aware, because each company keeps its own current workbook now. This is
    raw SQL, so the `do_orm_execute` scope filter never sees it: the caller's scope
    is spliced in by hand with `company_sql_predicate` (the sanctioned escape
    hatch), `shared=True` mirroring `Attachment.__company_shared__` so a legacy
    unstamped row stays reachable.

    A row the caller's company actually OWNS beats a legacy unstamped one whatever
    the dates say - hence `(a.company_id IS NULL) ASC` first in the ORDER BY.
    Without it the shared-NULL branch of the predicate lets an old company-less
    sheet outrank the company's own current workbook. Defensive only now:
    publication cannot write a NULL company and migration 323 stamped the existing
    NULL rows.

    Under a MULTI-company scope this returns one of N (`LIMIT 1`). Not reachable
    from the current route, whose callers are JWT sessions pinned to a single
    active company, but a future multi-company caller wanting all of them needs a
    different query, not this one.
    """
    try:
        from app.services.company_scope_sql import company_sql_predicate

        scope_sql, scope_params = company_sql_predicate(db, "a.company_id", shared=True)
        scope_clause = f"AND {scope_sql}" if scope_sql else ""
        params = {"code": TYPE_CODE, "name": TYPE_NAME, **scope_params}
        row = db.execute(
            text(
                f"""
                SELECT a.id, a.original_filename, a.file_path, a.file_size_bytes,
                       a.storage_provider, a.uploaded_at, a.company_id, c.name
                FROM attachments a
                JOIN attachment_types t ON t.id = a.attachment_type_id
                LEFT JOIN companies c ON c.id = a.company_id
                WHERE (t.code = :code OR t.type_name = :name) AND a.is_deleted = false
                  {scope_clause}
                ORDER BY (a.company_id IS NULL) ASC, a.uploaded_at DESC, a.id DESC
                LIMIT 1
                """  # noqa: S608 - scope_sql is built from bind params only
            ),
            params,
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
            "company_id": str(row[6]) if row[6] else None,
            "company_name": row[7],
        }
    except Exception:  # noqa: BLE001
        logger.warning("Could not resolve the latest container status document", exc_info=True)
        return None
