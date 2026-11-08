"""Files a staff member attaches to a message to the AI side panel (AGENT-PANEL-COMPOSER).

Images, Excel, CSV and PDF, uploaded as drafts (`ai_assistant_draft` link, one per file, owned by the
uploader) and moved onto the conversation (`ai_assistant_conversation`) when the message is sent.
This module validates and stores an upload, reads a sheet into the table the agent is shown, builds the
agent's input for a turn with files, and sweeps abandoned drafts.

Workbooks open values only (`data_only`, never `keep_vba`): no macro, formula or external link is run.
"""
from __future__ import annotations

import base64
import csv
import io
import itertools
import logging
import math
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment, AttachmentType
from app.services.chatbot.agent import batch
from app.services.entity_attachment_service import EntityAttachmentService, create_response_attachment
from app.services.error_handler import AppException
from app.services.llm_provider import ImagePart
from app.services.xlsx_guard import inspect_xlsx_zip

logger = logging.getLogger(__name__)

ATTACHMENT_TYPE_CODE = "ai_assistant_attachment"
ATTACHMENT_TYPE_NAME = "AI assistant attachment"
ATTACHMENT_EXTENSIONS = "png,jpg,jpeg,webp,xlsx,xls,csv,pdf"
DRAFT_ENTITY = "ai_assistant_draft"
CONVERSATION_ENTITY = "ai_assistant_conversation"
#: Rows of a sheet the agent is shown (the bulk confirm table's own cap, not a copy).
ROW_CAP = batch.MAX_ROWS
MAX_PDF_PAGES = 20
PDF_TEXT_CHARS = 20_000
UPLOADS_PER_MINUTE = 20

MACRO_MESSAGE = "Macro workbooks are not read; save as .xlsx"
MISMATCH_MESSAGE = "The file's content does not match its type."
UNREADABLE_MESSAGE = "This file cannot be read."
PDF_TOO_LONG_MESSAGE = "PDFs over 20 pages are not read."

_HEADER_SCAN_ROWS = 20
_CELL_CHARS = 200
#: Rows scanned in one sheet, and across the sheets of one workbook, so a sheet of a million styled rows (or
#: twenty of them) cannot hold a request. A sheet past its budget reports what was counted.
MAX_SCAN_ROWS_PER_SHEET = 10_000
MAX_SCAN_ROWS_TOTAL = 20_000
#: Columns and sheets read, whatever a workbook declares about itself (R2).
_MAX_COLUMNS = 100
_MAX_SHEETS = 20
#: Ceilings in code that an edit of the type row cannot lift (R6).
MAX_FILE_MB = 10
MAX_DRAFTS = 5

_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
}
_KIND = {"png": "image", "jpg": "image", "jpeg": "image", "webp": "image", "pdf": "pdf",
         "xlsx": "sheet", "xls": "sheet", "csv": "sheet"}


def _refuse(message: str, code: str = "attachment_refused") -> AppException:
    return AppException(422, message, code=code)


def _unreadable() -> AppException:
    return _refuse(UNREADABLE_MESSAGE, "file_unreadable")


def extension_of(filename: str | None) -> str:
    name = filename or ""
    return name.rsplit(".", 1)[-1].lower().strip() if "." in name else ""


def kind_of(filename: str | None) -> str:
    return _KIND.get(extension_of(filename), "sheet")


# --------------------------------------------------------------------------- #
# The attachment type
# --------------------------------------------------------------------------- #


def ensure_attachment_type(db: Session) -> AttachmentType:
    """The `ai_assistant_attachment` type, created with the contract values when the migration has not
    seeded it (a blank schema). An existing row is returned as the admin left it."""
    row = db.query(AttachmentType).filter(AttachmentType.code == ATTACHMENT_TYPE_CODE).first()
    if row is None:
        row = AttachmentType(
            code=ATTACHMENT_TYPE_CODE,
            type_name=ATTACHMENT_TYPE_NAME,
            description="Files staff attach to a message to the AI assistant.",
            allowed_extensions=ATTACHMENT_EXTENSIONS,
            max_file_size_mb=10,
            max_count_per_entity=5,
            triggers_n8n_webhook=False,
        )
        db.add(row)
        db.flush()
    return row


# --------------------------------------------------------------------------- #
# Reading a sheet
# --------------------------------------------------------------------------- #


@dataclass
class SheetRead:
    name: Optional[str]
    header: list[str]
    rows: list[list[str]]
    total_rows: int
    header_found: bool
    #: Rows read from the stream, blank ones included: what the scan budget is charged.
    scanned: int = 0


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        text = str(int(value)) if value == int(value) else repr(value)
    elif isinstance(value, datetime):
        text = value.strftime("%Y-%m-%d") if value.time() == time(0) else value.strftime("%Y-%m-%d %H:%M")
    elif isinstance(value, date):
        text = value.isoformat()
    else:
        text = str(value)
    text = text.strip().replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("|", "/")
    return text[:_CELL_CHARS]


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_text(value: Any) -> bool:
    """A text cell: a string that is not a number (a number is not text, even typed into a csv)."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        float(value.strip().replace(",", ""))
    except ValueError:
        return True
    return False


def _parse(
    raw_rows: Iterable[Iterable[Any]], name: Optional[str], limit: int = MAX_SCAN_ROWS_PER_SHEET
) -> SheetRead:
    """S1 to S3 over a stream of raw rows. Only the first `ROW_CAP` data rows are kept; all are counted."""
    it = iter(raw_rows)
    head = [list(r) for r in itertools.islice(it, _HEADER_SCAN_ROWS)]
    header_at = next((i for i, r in enumerate(head) if sum(1 for c in r if _is_text(c)) >= 2), None)
    header_raw: list[Any] | None = head[header_at] if header_at is not None else None
    body = itertools.chain(head[header_at + 1 :] if header_at is not None else head, it)

    kept: list[list[Any]] = []
    total = 0
    prefix = header_at + 1 if header_at is not None else 0  # rows above and including the header
    body_rows = 0
    for row in body:
        if body_rows >= limit:
            break
        body_rows += 1
        cells = list(row)
        if all(_blank(c) for c in cells):
            continue
        total += 1
        if len(kept) < ROW_CAP:
            kept.append(cells)

    def last_filled(cells: list[Any]) -> int:
        return max((i for i, c in enumerate(cells) if not _blank(c)), default=-1) + 1

    width = max([last_filled(r) for r in kept] + [last_filled(header_raw) if header_raw is not None else 0], default=0)
    rows = [[_clean(c) for c in (r + [None] * width)[:width]] for r in kept]
    if header_raw is not None:
        padded = (header_raw + [None] * width)[:width]
        header = [_clean(c) or f"Column {i + 1}" for i, c in enumerate(padded)]
    else:
        header = [f"Column {i + 1}" for i in range(width)]
    return SheetRead(
        name=name, header=header, rows=rows, total_rows=total, header_found=header_raw is not None,
        # Every row pulled from the stream: the header scan reads `len(head)` whatever the limit.
        scanned=max(len(head), prefix + body_rows),
    )


def _decode_csv(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _csv_rows(data: bytes) -> Iterable[list[str]]:
    text = _decode_csv(data)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    delimiter = max((",", ";", "\t"), key=lambda d: (first.count(d), d == ","))
    return csv.reader(io.StringIO(text), delimiter=delimiter)


def _xls_rows(book, sheet) -> Iterable[list[Any]]:
    import xlrd

    for r in range(sheet.nrows):
        out: list[Any] = []
        for cell in sheet.row(r):
            if cell.ctype == xlrd.XL_CELL_DATE:
                out.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
            elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                out.append(bool(cell.value))
            elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
                out.append(None)
            else:
                out.append(cell.value)
        yield out


def _narrow(rows: Iterable[Iterable[Any]]) -> Iterable[list[Any]]:
    for row in rows:
        yield list(row)[:_MAX_COLUMNS]


def _sheets(data: bytes, ext: str):
    """`(name, rows iterator)` per sheet in workbook order (the first `_MAX_SHEETS`), opened lazily, each
    row at most `_MAX_COLUMNS` wide; a csv is one unnamed sheet."""
    if ext == "csv":
        yield None, _narrow(_csv_rows(data))
        return
    if ext == "xls":
        import xlrd

        book = xlrd.open_workbook(file_contents=data, on_demand=True)
        try:
            for sheet in book.sheets()[:_MAX_SHEETS]:
                yield sheet.name, _narrow(_xls_rows(book, sheet))
        finally:
            book.release_resources()
        return
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        for ws in wb.worksheets[:_MAX_SHEETS]:
            # A read-only sheet trusts its declared `<dimension>`; a forged A1:XFD1048576 would pad every row.
            if hasattr(ws, "reset_dimensions"):
                ws.reset_dimensions()
            yield ws.title, _narrow(ws.iter_rows(max_col=_MAX_COLUMNS, values_only=True))
    finally:
        wb.close()


def read_sheet(data: bytes, ext: str, sheet: Optional[str] = None) -> SheetRead:
    """The named sheet, or the first non-empty one when `sheet` is None or unknown (S6)."""
    ext = ext.lstrip(".").lower()
    first_name: Optional[str] = None
    seen_any = False
    if sheet is not None and ext != "csv":
        for name, rows in _sheets(data, ext):
            if name == sheet:
                return _parse(rows, name)
    budget = MAX_SCAN_ROWS_TOTAL
    for name, rows in _sheets(data, ext):
        if not seen_any:
            first_name, seen_any = name, True
        if budget <= 0:
            break
        got = _parse(rows, name, min(MAX_SCAN_ROWS_PER_SHEET, budget))
        if got.total_rows:
            return got
        budget -= got.scanned
    return SheetRead(name=first_name, header=[], rows=[], total_rows=0, header_found=False)


def list_sheets(data: bytes, ext: str) -> list[dict[str, Any]]:
    """The non-empty sheets in workbook order with their data-row counts (a csv is one)."""
    out = []
    budget = MAX_SCAN_ROWS_TOTAL
    for name, rows in _sheets(data, ext.lstrip(".").lower()):
        if budget <= 0:
            break
        got = _parse(rows, name, min(MAX_SCAN_ROWS_PER_SHEET, budget))
        budget -= got.scanned
        if got.total_rows:
            out.append({"name": name if name is not None else "Sheet 1", "rows": got.total_rows})
    return out


def render_sheet_block(filename: str, read: SheetRead, *, is_csv: bool) -> str:
    shown = len(read.rows)
    count = f"first {shown} of {read.total_rows} rows" if read.total_rows > shown else f"{read.total_rows} rows"
    where = "" if is_csv else f', sheet "{_one_line(read.name or "")}"'
    first = f'Attached file "{_one_line(filename)}"{where}: {count}.'
    if not read.header_found and read.total_rows:
        first += " Note: no header row found, columns are numbered."
    lines = [first]
    if read.header:
        lines.append("| " + " | ".join(read.header) + " |")
        lines.append("| " + " | ".join("---" for _ in read.header) + " |")
        lines.extend("| " + " | ".join(r) + " |" for r in read.rows)
    return "\n".join(lines)


def _one_line(text: str) -> str:
    """A name flattened to one line with no double quote, so it cannot break out of a block header."""
    return " ".join(str(text or "").split()).replace('"', "'")


# --------------------------------------------------------------------------- #
# Validating an upload
# --------------------------------------------------------------------------- #


def _matches_type(ext: str, data: bytes) -> bool:
    if ext == "png":
        return data.startswith(b"\x89PNG")
    if ext in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if ext == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if ext == "pdf":
        return data.startswith(b"%PDF-")
    if ext == "xls":
        return data.startswith(b"\xd0\xcf\x11\xe0")
    if ext == "xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                return "xl/workbook.xml" in zf.namelist()
        except zipfile.BadZipFile:
            return False
    if ext == "csv":
        if b"\x00" in data:
            return False
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                data.decode(encoding)
                return True
            except UnicodeDecodeError:
                continue
        return False
    return False


def pdf_pages(data: bytes) -> int:
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise _unreadable() from exc
    try:
        if doc.needs_pass or doc.is_encrypted or doc.page_count < 1:
            raise _unreadable()
        return int(doc.page_count)
    finally:
        doc.close()


def pdf_text(data: bytes) -> str:
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        parts: list[str] = []
        used = 0
        for page in itertools.islice(doc, MAX_PDF_PAGES):
            text = page.get_text().strip()
            parts.append(text)
            used += len(text)
            if used >= PDF_TEXT_CHARS:
                break
        return "\n".join(parts)[:PDF_TEXT_CHARS]
    finally:
        doc.close()


def inspect_upload(ext: str, data: bytes) -> dict[str, Any]:
    """C3 to C7: the content matches its extension, a workbook carries no macro and is no bomb, and the file
    opens. Returns the facts the upload response carries (`sheets`, `pages`)."""
    if not _matches_type(ext, data):
        raise _refuse(MISMATCH_MESSAGE, "content_mismatch")
    facts: dict[str, Any] = {"sheets": [], "pages": None}
    if ext in ("png", "jpg", "jpeg", "webp"):
        from app.services.image_thumbnailer import RENDITION_FORMATS, RENDITION_MAX_PIXELS, downscale

        if downscale(data, 32, formats=RENDITION_FORMATS, max_pixels=RENDITION_MAX_PIXELS, label="panel upload") is None:
            raise _unreadable()
    elif ext == "pdf":
        pages = pdf_pages(data)
        if pages > MAX_PDF_PAGES:
            raise _refuse(PDF_TOO_LONG_MESSAGE, "pdf_too_long")
        facts["pages"] = pages
    else:
        if ext == "xlsx":
            try:
                inspect_xlsx_zip(data)
            except AppException as exc:
                if (exc.message or "").startswith("Macro"):
                    raise _refuse(MACRO_MESSAGE, "macro_workbook") from exc
                raise
        try:
            facts["sheets"] = list_sheets(data, ext)
        except AppException:
            raise
        except Exception as exc:  # noqa: BLE001 - corrupt, password protected, or not a workbook
            logger.info("panel upload: unreadable %s workbook: %s", ext, exc)
            raise _unreadable() from exc
    return facts


# --------------------------------------------------------------------------- #
# Upload, delete, purge
# --------------------------------------------------------------------------- #


def _signed(key: str, provider: str | None) -> str | None:
    from app.services import storage_router

    try:
        return storage_router.resolve_signed_url(key, provider=provider)
    except Exception:  # noqa: BLE001
        logger.warning("panel files: could not sign %s", key[:80], exc_info=True)
        return None


def thumb_url_of(att: Attachment) -> str | None:
    from app.services.image_thumbnailer import rendition_key

    if not att.thumbnail_path:
        return None
    return _signed(rendition_key(att.file_path, "thumb"), att.storage_provider)


def size_limit_bytes(atype: AttachmentType) -> int:
    """The type row's size limit, never above the 10 MB ceiling and never off (R6)."""
    mb = atype.max_file_size_mb
    return (min(mb, MAX_FILE_MB) if mb and mb > 0 else MAX_FILE_MB) * 1024 * 1024


def _check_limits(db: Session, atype: AttachmentType, user_id: str, size: int, ext: str) -> None:
    """C1, C2, C8 against the type row and the ceilings in code, answering 422."""
    allowed = {
        e.strip().lower().lstrip(".") for e in (atype.allowed_extensions or ATTACHMENT_EXTENSIONS).split(",") if e.strip()
    }
    if ext not in allowed:
        raise _refuse(f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}.", "VALIDATION_ERROR")
    limit = size_limit_bytes(atype)
    if size > limit:
        raise _refuse(f"File exceeds {limit // (1024 * 1024)} MB limit.", "VALIDATION_ERROR")
    cap = min(atype.max_count_per_entity, MAX_DRAFTS) if atype.max_count_per_entity is not None else MAX_DRAFTS
    held = (
        db.query(EntityAttachmentLink)
        .join(Attachment, Attachment.id == EntityAttachmentLink.attachment_id)
        .filter(
            EntityAttachmentLink.entity_type == DRAFT_ENTITY,
            EntityAttachmentLink.entity_id == str(user_id),
            Attachment.attachment_type_id == atype.id,
        )
        .count()
    )
    if held >= cap:
        raise _refuse(f"Attachment limit reached ({cap}).", "VALIDATION_ERROR")


def create_draft(
    db: Session, *, user_id: str, filename: str, data: bytes, atype: AttachmentType | None = None
) -> dict[str, Any]:
    """C1 to C8 and the store. `data` is at most the size limit + 1 bytes (the route bounds the read)."""
    name = (filename or "").strip()
    ext = extension_of(name)
    if ext == "xlsm":
        raise _refuse(MACRO_MESSAGE, "macro_workbook")
    _check_limits(db, atype or ensure_attachment_type(db), str(user_id), len(data), ext)
    facts = inspect_upload(ext, data)
    mime = _MIME[ext]
    created = create_response_attachment(
        db,
        entity_type=DRAFT_ENTITY,
        entity_id=str(user_id),
        contents=data,
        filename=name,
        content_type=mime,
        uploaded_by=str(user_id),
        attachment_type_code=ATTACHMENT_TYPE_CODE,
        key_prefix=f"ai_assistant/{user_id}",
        check_quota=False,
    )
    att = db.get(Attachment, created["attachment_id"])
    return {
        "id": str(att.id),
        "filename": att.original_filename,
        "size": len(data),
        "mime_type": mime,
        "kind": _KIND[ext],
        "thumb_url": thumb_url_of(att) if _KIND[ext] == "image" else None,
        "sheets": facts["sheets"],
        "pages": facts["pages"],
    }


def _as_uuid(value: str) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError):
        return None


def _draft_rows(db: Session, user_id: str, ids: list[str]) -> list[tuple[Attachment, EntityAttachmentLink]]:
    return (
        db.query(Attachment, EntityAttachmentLink)
        .join(EntityAttachmentLink, EntityAttachmentLink.attachment_id == Attachment.id)
        .filter(
            Attachment.id.in_(ids),
            EntityAttachmentLink.entity_type == DRAFT_ENTITY,
            EntityAttachmentLink.entity_id == str(user_id),
            Attachment.uploaded_by == str(user_id),
        )
        .all()
    )


def _remove_stored(att: Attachment) -> bool:
    """Delete the object and, for an image, its renditions (best effort). False when the ORIGINAL stays."""
    from app.services import storage_router
    from app.services.image_thumbnailer import RENDITIONS, rendition_key

    backend = storage_router.get_backend(att.storage_provider)
    try:
        backend.delete_file(att.file_path)
    except Exception:  # noqa: BLE001
        logger.warning("panel files: storage delete failed for %s", att.file_path[:80], exc_info=True)
        return False
    if (att.mime_type or "").startswith("image/"):
        for size in RENDITIONS:
            try:
                backend.delete_file(rendition_key(att.file_path, size))
            except Exception:  # noqa: BLE001
                logger.warning("panel files: rendition delete failed for %s", att.file_path[:80], exc_info=True)
    return True


def _delete_rows(db: Session, att: Attachment, link: EntityAttachmentLink) -> None:
    db.delete(link)
    db.flush()
    db.delete(att)
    db.commit()


def delete_draft(db: Session, *, user_id: str, attachment_id: str) -> bool:
    """C10, C11. False when it is not the caller's unsent draft (the route answers 404). A storage failure
    on the original raises 502 and leaves the draft for the purge."""
    aid = _as_uuid(attachment_id)
    if aid is None:
        return False
    found = _draft_rows(db, str(user_id), [aid])
    if not found:
        return False
    att, link = found[0]
    if not _remove_stored(att):
        raise AppException(502, "The file could not be removed. Try again.", code="DELETE_FAILED")
    _delete_rows(db, att, link)
    return True


def purge_drafts(db: Session, *, older_than: timedelta = timedelta(hours=24)) -> int:
    """P1: hard-delete draft files uploaded more than `older_than` ago. A file whose storage delete fails
    stays for the next sweep. Returns how many were removed."""
    cutoff = datetime.now(timezone.utc) - older_than
    rows = (
        db.query(Attachment, EntityAttachmentLink)
        .join(EntityAttachmentLink, EntityAttachmentLink.attachment_id == Attachment.id)
        .filter(EntityAttachmentLink.entity_type == DRAFT_ENTITY, Attachment.uploaded_at < cutoff)
        .all()
    )
    removed = 0
    for att, link in rows:
        try:
            if not _remove_stored(att):
                continue
            _delete_rows(db, att, link)
            removed += 1
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.warning("panel files: purge of one draft failed", exc_info=True)
    return removed


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #


@dataclass
class Draft:
    attachment: Attachment
    link: EntityAttachmentLink
    sheet: Optional[str]


@dataclass
class PreparedFiles:
    """What a message's files become: the stored fields, the agent's text blocks and the model's images."""

    drafts: list[Draft] = field(default_factory=list)
    meta: list[dict[str, Any]] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    images: list[ImagePart] = field(default_factory=list)
    envelope_files: list[dict[str, Any]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.drafts)

    @property
    def file_text(self) -> str:
        """One block per file in order, a blank line between: quoted data for the model (R3)."""
        return "\n\n".join(self.blocks)

    @property
    def first_name(self) -> str:
        return self.drafts[0].attachment.original_filename if self.drafts else ""


def claim_drafts(db: Session, user_id: str, refs: list[Any]) -> list[Draft]:
    """T1: every ref must be the caller's own unsent draft, else 404 and nothing is touched."""
    ids: list[str] = []
    sheets: dict[str, Optional[str]] = {}
    for ref in refs:
        aid = _as_uuid(ref.id)
        if aid is None:
            raise AppException(404, "File not found", code="file_not_found")
        if aid not in sheets:
            ids.append(aid)
            sheets[aid] = ref.sheet
    by_id = {str(a.id): (a, link) for a, link in _draft_rows(db, str(user_id), ids)} if ids else {}
    if len(by_id) != len(ids):
        raise AppException(404, "File not found", code="file_not_found")
    return [Draft(by_id[i][0], by_id[i][1], sheets[i]) for i in ids]


def _download(att: Attachment, key: str | None = None) -> bytes:
    from app.services import storage_router

    return storage_router.get_backend(att.storage_provider).download_file(key or att.file_path)


def _image_part(att: Attachment) -> ImagePart:
    from app.services.image_thumbnailer import downscale, rendition_key

    raw: bytes | None = None
    try:
        raw = _download(att, rendition_key(att.file_path, "medium"))
    except Exception:  # noqa: BLE001 - no medium rendition (an older file or a failed write)
        raw = None
    if not raw:
        made = downscale(_download(att), 1024, label="panel image")
        if made is None:
            raise _unreadable()
        raw = made.data
    return ImagePart(mime="image/jpeg", data_b64=base64.b64encode(raw).decode())


def prepare(drafts: list[Draft], *, provider_name: str) -> PreparedFiles:
    """T4, T6, T8, T9, T10 for a validated set of drafts."""
    out = PreparedFiles(drafts=drafts)
    for d in drafts:
        att = d.attachment
        ext = extension_of(att.original_filename)
        kind = _KIND.get(ext, "sheet")
        meta: dict[str, Any] = {
            "id": str(att.id), "filename": att.original_filename, "size": att.file_size_bytes,
            "mime_type": att.mime_type, "kind": kind, "sheet": None,
            "rows_read": None, "rows_total": None, "pages": None,
        }
        name = _one_line(att.original_filename)
        if kind == "sheet":
            read = read_sheet(_download(att), ext, d.sheet)
            meta.update(
                sheet=None if ext == "csv" else read.name, rows_read=len(read.rows), rows_total=read.total_rows
            )
            out.blocks.append(render_sheet_block(att.original_filename, read, is_csv=ext == "csv"))
        elif kind == "image":
            out.images.append(_image_part(att))
            out.blocks.append(f"[image: {name}]")
        else:
            data = _download(att)
            pages = pdf_pages(data)
            meta["pages"] = pages
            label = f"[pdf: {name}, {pages} pages]"
            if provider_name == "gemini":
                out.images.append(ImagePart(mime="application/pdf", data_b64=base64.b64encode(data).decode()))
                out.blocks.append(label)
            else:
                out.blocks.append(f"{label}\n{pdf_text(data)}")
        out.meta.append(meta)
        out.envelope_files.append({"id": str(att.id), "filename": att.original_filename, "kind": kind})
    return out


def move_to_conversation(db: Session, prepared: PreparedFiles, conversation_id: str) -> None:
    """T5: the files stop being drafts and belong to the thread."""
    for d in prepared.drafts:
        d.link.entity_type = CONVERSATION_ENTITY
        d.link.entity_id = str(conversation_id)
    db.commit()


def with_urls(db: Session, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """T11: each stored file field plus a fresh `url` (and `thumb_url` for an image). Never written back."""
    ids = [i for i in (_as_uuid(f.get("id")) for f in files if isinstance(f, dict)) if i]
    atts = {str(a.id): a for a in db.query(Attachment).filter(Attachment.id.in_(ids)).all()} if ids else {}
    atts = {i: a for i, a in atts.items() if not a.is_deleted}
    out = []
    for f in files:
        item = dict(f) if isinstance(f, dict) else {}
        att = atts.get(str(item.get("id")))
        if att is not None:
            item["url"] = _signed(att.file_path, att.storage_provider)
            if item.get("kind") == "image":
                item["thumb_url"] = thumb_url_of(att)
        out.append(item)
    return out
