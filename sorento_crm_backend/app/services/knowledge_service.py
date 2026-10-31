"""AGENTIC-KNOWLEDGE P1: read uploaded documents so the AI can answer from them.

Three halves in one module, because they share the constants:

* reading: a PDF (text layer, OCR for scanned pages) or a DOCX (heading sections) becomes
  page-aware chunks written as embedding source ``knowledge`` with the Gemini model only;
* asking: ``search`` joins each chunk to its attachment and that attachment's type AT QUERY TIME,
  so switching a type to ``off``, deleting a file or moving company takes effect at once;
* the prompt paragraph both surfaces append (``with_knowledge_protocol``).

``knowledge`` is deliberately NOT in ``RECORD_KEEP_SET``: ``/external/rag/search`` serves every
keep-set source with no audience filter, so a knowledge chunk must never be reachable there.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import zipfile
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from app.models.base import company_scope

logger = logging.getLogger(__name__)

KNOWLEDGE_SOURCE = "knowledge"
KNOWLEDGE_MODEL = "gemini-embedding-001"
KNOWLEDGE_PROVIDER = "gemini"
KNOWLEDGE_MODEL_VERSION = "1"
KNOWLEDGE_TOOL = "crm_knowledge_search"
KNOWLEDGE_PROTOCOL_HEADER = "KNOWLEDGE PROTOCOL"
READ_PERMISSION = "resource.attachments.view"
AI_AUDIENCES = ("off", "staff", "dealer", "public")
#: Audiences a staff caller may read in P1 (everything that is not off).
READABLE_AUDIENCES = ("staff", "dealer", "public")
MAX_REQUEUE_PER_SAVE = 500
#: Most chunks one document may produce; a longer one fails with a readable error and writes nothing.
MAX_CHUNKS = 2000
FETCH_ERROR = "The file could not be downloaded from storage."

#: A PDF page with fewer stripped characters than this has no usable text layer and is read by OCR.
OCR_TEXT_MIN_CHARS = 40
#: Estimate of one vision-read page in USD, shown as "est." and to be tuned by the eval.
OCR_COST_PER_PAGE_USD = Decimal("0.002")
#: Passages less similar to the question than this are dropped. An estimate, to be tuned by the eval.
KNOWLEDGE_SIMILARITY_FLOOR = 0.5

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
EMBED_BATCH = 100
#: Its own queue (batch role in worker.QUEUES): a 300-page OCR read must not sit in front of a
#: chatbot media turn on `media`, which a customer is waiting on.
QUEUE = "knowledge"
JOB_TIMEOUT = 1800
#: A queued/processing read older than this is treated as lost (a bit above JOB_TIMEOUT), so Read again may retry it.
STALE_AFTER_SECONDS = 1900
#: Hard limits on one file, so a huge or hostile upload cannot pin the worker or run up the OCR bill.
MAX_PAGES = 300
MAX_OCR_PAGES = 100
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
#: Largest page (width x height in pt^2) rendered for OCR; about A1. A bigger page is treated as having no text.
MAX_PAGE_AREA_PT2 = 4_000_000
QUERY_EMBED_TIMEOUT_SECONDS = 10
MAX_TOP_K = 20
ERROR_MAX_CHARS = 500
READ_QUEUED_ERROR = "The read could not be queued. Try Read again."

_DOCX_HEADINGS = frozenset({"heading1", "heading2"})
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class Page:
    """One page of a PDF, or one heading section of a DOCX (its "page")."""

    page: int
    heading: Optional[str]
    text: str
    ocr: bool = False


@dataclass
class Chunk:
    index: int
    page: int
    heading: Optional[str]
    text: str


# ---------------------------------------------------------------- extraction


def extract_pdf_pages(content: bytes, *, ocr: Callable[[bytes, int], str]) -> list[Page]:
    """One Page per PDF page. A page whose text layer is under OCR_TEXT_MIN_CHARS goes to `ocr`
    as a PNG (page number, 1-based) and is flagged. Raises on bytes that are not a readable PDF."""
    import fitz  # PyMuPDF; imported here so the module stays cheap to import

    document = fitz.open(stream=content, filetype="pdf")
    try:
        if document.needs_pass:
            raise ValueError("The PDF is password protected.")
        if len(document) > MAX_PAGES:
            raise ValueError(f"This PDF has more than {MAX_PAGES} pages, which is the maximum the AI reads.")
        texts: list[str] = []
        needs_ocr: list[bool] = []
        for page in document:
            text = (page.get_text() or "").strip()
            texts.append(text)
            small_enough = page.rect.width * page.rect.height <= MAX_PAGE_AREA_PT2
            needs_ocr.append(len(text) < OCR_TEXT_MIN_CHARS and small_enough)
        if sum(needs_ocr) > MAX_OCR_PAGES:
            raise ValueError(
                f"This PDF has more than {MAX_OCR_PAGES} scanned pages, which is the maximum the AI reads."
            )
        pages: list[Page] = []
        for index, text in enumerate(texts):
            number = index + 1
            if not needs_ocr[index]:
                pages.append(Page(number, None, text))
                continue
            png = document[index].get_pixmap(dpi=150).tobytes("png")
            read = (ocr(png, number) or "").strip()
            pages.append(Page(number, None, read or text, ocr=True))
        return pages
    finally:
        document.close()


def extract_docx_sections(content: bytes) -> list[Page]:
    """Paragraphs of word/document.xml in order. Each Heading 1 / Heading 2 starts a new section;
    the section number is the page and the heading is kept. Text before the first heading is section 1."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        with z.open("word/document.xml") as part:
            xml = part.read(MAX_DOCX_XML_BYTES + 1)  # bounded read: the declared size can lie
    if len(xml) > MAX_DOCX_XML_BYTES:
        raise ValueError("This document is too large for the AI to read.")
    root = ET.fromstring(xml)
    sections: list[Page] = []
    current: Optional[Page] = None
    for para in root.iter(f"{_W}p"):
        text = "".join(t.text or "" for t in para.iter(f"{_W}t")).strip()
        style = para.find(f"{_W}pPr/{_W}pStyle")
        style_id = (style.get(f"{_W}val") if style is not None else "") or ""
        is_heading = style_id.replace(" ", "").lower() in _DOCX_HEADINGS
        if is_heading and text:
            current = Page(len(sections) + 1, text, text)
            sections.append(current)
        elif text:
            if current is None:
                current = Page(len(sections) + 1, None, text)
                sections.append(current)
            else:
                current.text = f"{current.text}\n{text}"
    return sections


def chunk_pages(pages: list[Page], size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    """Chunks of at most `size` characters with `overlap` characters repeated between neighbours,
    cut on word boundaries and never across a page. `index` runs 0.. over the whole document."""
    chunks: list[Chunk] = []
    for page in pages:
        words: list[str] = []
        for word in (page.text or "").split():
            while len(word) > size:  # one unbroken string longer than a chunk
                words.append(word[:size])
                word = word[size:]
            words.append(word)
        start = 0
        while start < len(words):
            end, length = start, 0
            while end < len(words):
                add = len(words[end]) + (1 if end > start else 0)
                if length + add > size:
                    break
                length += add
                end += 1
            chunks.append(Chunk(len(chunks), page.page, page.heading, " ".join(words[start:end])))
            if end >= len(words):
                break
            back, tail = end, 0
            while back > start + 1 and tail + len(words[back - 1]) + 1 <= overlap:
                tail += len(words[back - 1]) + 1
                back -= 1
            start = back if back > start else end
    return chunks


# ---------------------------------------------------------------- default seams (network, storage)


def _default_fetch(attachment) -> bytes:
    from app.services.storage_router import extract_key, get_backend

    key = extract_key(attachment.file_path)
    if not key:
        raise ValueError("The file has no stored location.")
    return get_backend(attachment.storage_provider).download_file(key)


def _default_ocr(db: Session) -> Callable[[bytes, int], str]:
    """The existing vision reader (document_extraction) asked for a plain transcription."""
    from app.services import document_extraction as de
    from app.services.llm_provider import ImagePart, get_provider, resolve_api_key

    state: dict[str, Any] = {}

    def read(png: bytes, page_no: int) -> str:
        if "provider" not in state:
            provider_name, model = de._reader_model(db)
            api_key = resolve_api_key(de._assistant_config(db), provider_name)
            if not api_key:
                raise RuntimeError(f"No key is configured for the '{provider_name}' document reader.")
            state["provider"] = get_provider(provider_name, api_key, model)
        import base64

        answer = state["provider"].chat(
            [
                {
                    "role": "user",
                    "content": (
                        "Transcribe all the text on this page exactly as written, in reading order. "
                        "Return only the text, with no commentary."
                    ),
                }
            ],
            images=[ImagePart(mime="image/png", data_b64=base64.b64encode(png).decode())],
            temperature=0,
        )
        return answer.content or ""

    return read


def _default_embed(db: Session, timeout: Optional[float] = None) -> Callable[[list[str]], list[list[float]]]:
    from app.services.embedding_settings import embed_search_texts

    return lambda texts: embed_search_texts(texts, KNOWLEDGE_MODEL, db=db, timeout=timeout)


def _job_id(attachment_id: str) -> str:
    return f"knowledge-read-{attachment_id}"


def _enqueue(attachment_id: str) -> None:
    """Put one read job on the worker's `knowledge` queue (looked up at call time so tests stub it).
    The job id is deterministic, so a route can ask whether the job is still alive."""
    from app.services import queue_service
    from app.tasks.knowledge_tasks import read_attachment_job

    queue_service.enqueue_job(
        read_attachment_job,
        str(attachment_id),
        queue_name="knowledge",
        job_timeout=JOB_TIMEOUT,
        job_id=_job_id(attachment_id),
    )


def _job_pending(attachment_id: str) -> bool:
    """Is the RQ job for this file still waiting or running? False when it is gone or Redis fails."""
    try:
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        from app.services import queue_service

        try:
            job = Job.fetch(_job_id(attachment_id), connection=queue_service.redis_conn)
        except NoSuchJobError:
            return False
        return job.get_status(refresh=True) in ("queued", "started", "deferred", "scheduled")
    except Exception:  # noqa: BLE001 - an unreachable Redis means no known live job
        return False


# ---------------------------------------------------------------- reading a file


def _log_text(exc: Exception) -> str:
    from app.services.document_extraction import redact_key_fragments

    return redact_key_fragments(str(exc))[:ERROR_MAX_CHARS]


class _FetchFailed(Exception):
    """The file's bytes could not be read from storage; the message is safe to show staff."""


def _readable_error(exc: Exception) -> str:
    from app.services.document_extraction import redact_key_fragments

    if isinstance(exc, _FetchFailed):
        return str(exc)
    text = redact_key_fragments(str(exc)).strip() or exc.__class__.__name__
    return text[:ERROR_MAX_CHARS]


def _now() -> datetime:
    return datetime.utcnow()


def _finish(db: Session, attachment, status: str, **fields: Any) -> None:
    attachment.ai_read_status = status
    attachment.ai_read_at = _now()
    attachment.ai_read_pages = fields.get("pages")
    attachment.ai_read_ocr_pages = fields.get("ocr_pages")
    attachment.ai_read_cost_usd = fields.get("cost")
    attachment.ai_read_error = fields.get("error")
    db.commit()


def read_attachment(
    db: Session,
    attachment_id: str,
    *,
    fetch: Optional[Callable[[Any], bytes]] = None,
    ocr: Optional[Callable[[bytes, int], str]] = None,
    embed: Optional[Callable[[list[str]], list[list[float]]]] = None,
) -> None:
    """Read one file and replace its knowledge chunks. Never raises for a file problem: the row
    ends `done`, `failed` (readable error, nothing written) or `unsupported`.

    Extraction and embedding happen before any chunk is touched, so a failure leaves the
    previous reading (if any) exactly as it was."""
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.models.resources import Attachment

    with company_scope(db, None):  # a worker has no request scope
        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if attachment is None:
            return
        ext = os.path.splitext(attachment.original_filename or "")[1].lower().lstrip(".")
        if ext not in ("pdf", "docx"):
            _finish(db, attachment, "unsupported")
            return
        started_hash = attachment.file_hash
        attachment.ai_read_status = "processing"
        attachment.ai_read_at = _now()
        db.commit()
        try:
            try:
                content = (fetch or _default_fetch)(attachment)
            except Exception as fetch_exc:  # noqa: BLE001 - raw storage config text stays in the log only
                logger.warning("knowledge fetch failed for %s: %s", attachment_id, _log_text(fetch_exc))
                raise _FetchFailed(FETCH_ERROR) from None
            if ext == "pdf":
                pages = extract_pdf_pages(content, ocr=ocr or _default_ocr(db))
            else:
                pages = extract_docx_sections(content)
            chunks = chunk_pages(pages)
            if not chunks:
                raise ValueError("No text could be read from this file.")
            if len(chunks) > MAX_CHUNKS:
                raise ValueError("This document is too long for the AI to read.")
            embedder = embed or _default_embed(db)
            texts = [c.text for c in chunks]
            vectors: list[list[float]] = []
            for i in range(0, len(texts), EMBED_BATCH):
                vectors.extend(embedder(texts[i : i + EMBED_BATCH]))
            if len(vectors) != len(texts):
                raise ValueError("The embedding service returned the wrong number of vectors.")
        except Exception as exc:  # noqa: BLE001 - the row records it, the queue survives
            error = _readable_error(exc)
            logger.warning("knowledge read failed for %s: %s", attachment_id, error)
            _finish(db, attachment, "failed", error=error)
            return

        if db.query(Attachment.id).filter(Attachment.id == attachment_id).first() is None:
            logger.info("knowledge read for %s dropped: the file was deleted while it was read", attachment_id)
            return
        # A replace upload during the read changed the file: what was read is stale, so write nothing.
        # The replace queued its own read.
        db.refresh(attachment)
        if attachment.file_hash != started_hash:
            logger.info("knowledge read for %s dropped: the file changed while it was read", attachment_id)
            return

        ocr_pages = sum(1 for p in pages if p.ocr)
        source_id = str(attachment.id)
        # The file's own hash, so Read again can tell an unchanged file; the text hash when it has none.
        source_hash = started_hash or hashlib.sha256("\n".join(texts).encode()).hexdigest()
        company_id = attachment.company_id
        written = False
        error = ""
        for _attempt in range(2):  # a second read racing us may add its document first: replace it once
            try:
                _replace_rows(db, source_id, attachment.original_filename, company_id, source_hash, chunks, vectors)
                written = True
                break
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                error = _readable_error(exc)
        if not written:
            logger.error("knowledge write failed for %s: %s", attachment_id, error)
            attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
            if attachment is not None:
                _finish(db, attachment, "failed", error="The reading could not be saved. Try Read again.")
            return
        _finish(
            db,
            attachment,
            "done",
            pages=len(pages),
            ocr_pages=ocr_pages,
            cost=OCR_COST_PER_PAGE_USD * ocr_pages,
        )


def _replace_rows(db: Session, source_id: str, filename: Optional[str], company_id, source_hash: str, chunks, vectors) -> None:
    """Delete the file's knowledge document (and chunks) and write the new ones, in the open transaction."""
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument

    for old in db.query(EmbeddingDocument).filter(
        EmbeddingDocument.source_type == KNOWLEDGE_SOURCE, EmbeddingDocument.source_id == source_id
    ):
        db.delete(old)
    db.flush()  # the unique (source_type, source_id) index needs the delete first
    doc = EmbeddingDocument(
        source_type=KNOWLEDGE_SOURCE,
        source_id=source_id,
        title=(filename or "")[:255],
        body_text="\n\n".join(c.text for c in chunks),
        metadata_json={"attachment_id": source_id},
        source_hash=source_hash,
        company_id=company_id,
        is_active=True,
    )
    db.add(doc)
    db.flush()
    for chunk, vector in zip(chunks, vectors):
        db.add(
            EmbeddingChunk(
                document_id=doc.id,
                source_type=KNOWLEDGE_SOURCE,
                source_id=source_id,
                chunk_index=chunk.index,
                chunk_text=chunk.text,
                chunk_hash=hashlib.sha256(f"{source_id}:{chunk.index}:{chunk.text}".encode()).hexdigest(),
                embedding=vector,
                model_name=KNOWLEDGE_MODEL,
                model_version=KNOWLEDGE_MODEL_VERSION,
                embedding_provider=KNOWLEDGE_PROVIDER,
                source_hash=source_hash,
                metadata_json={"attachment_id": source_id, "page": chunk.page, "heading": chunk.heading},
                company_id=company_id,
                is_current=True,
            )
        )
    db.flush()


def drop_knowledge(db: Session, attachment_ids: list[str]) -> None:
    """Remove what the AI read of these files (document and chunks). The caller commits."""
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument

    ids = [str(i) for i in attachment_ids if i]
    if not ids:
        return
    db.query(EmbeddingChunk).filter(
        EmbeddingChunk.source_type == KNOWLEDGE_SOURCE, EmbeddingChunk.source_id.in_(ids)
    ).delete(synchronize_session=False)
    db.query(EmbeddingDocument).filter(
        EmbeddingDocument.source_type == KNOWLEDGE_SOURCE, EmbeddingDocument.source_id.in_(ids)
    ).delete(synchronize_session=False)


def move_company(db: Session, attachment_ids: list[str], company_id: Optional[str]) -> None:
    """A file changed company: its knowledge document and chunks follow. The caller commits."""
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument

    ids = [str(i) for i in attachment_ids if i]
    if not ids:
        return
    db.query(EmbeddingChunk).filter(
        EmbeddingChunk.source_type == KNOWLEDGE_SOURCE, EmbeddingChunk.source_id.in_(ids)
    ).update({EmbeddingChunk.company_id: company_id}, synchronize_session=False)
    db.query(EmbeddingDocument).filter(
        EmbeddingDocument.source_type == KNOWLEDGE_SOURCE, EmbeddingDocument.source_id.in_(ids)
    ).update({EmbeddingDocument.company_id: company_id}, synchronize_session=False)


# ---------------------------------------------------------------- queueing


def queue_read(db: Session, attachment, *, check_pending: bool = True) -> bool:
    """Queue one read when the file's type is AI readable. True when a job was queued."""
    from app.models.resources import AttachmentType

    type_id = getattr(attachment, "attachment_type_id", None)
    if not type_id:
        return False
    audience = db.query(AttachmentType.ai_audience).filter(AttachmentType.id == type_id).scalar()
    if audience not in READABLE_AUDIENCES:
        return False
    attachment.ai_read_status = "queued"
    attachment.ai_read_error = None
    attachment.ai_read_at = _now()
    db.commit()
    return _enqueue_or_fail(db, attachment, check_pending)


def read_block_reason(db: Session, attachment) -> Optional[str]:
    """Why Read again must not queue this file now (a sentence for the user), or None."""
    from app.models.resources import AttachmentType

    audience = None
    if getattr(attachment, "attachment_type_id", None):
        audience = db.query(AttachmentType.ai_audience).filter(AttachmentType.id == attachment.attachment_type_id).scalar()
    if audience not in READABLE_AUDIENCES:
        return "The AI does not read files of this type."
    status = attachment.ai_read_status
    if status == "queued":
        # A queued row follows its RQ job: alive means wait, gone means the job was lost.
        if _job_pending(str(attachment.id)):
            return "This file is already being read."
    elif status == "processing":
        at = attachment.ai_read_at
        if at is not None and (_now() - at).total_seconds() < STALE_AFTER_SECONDS:
            return "This file is already being read."
    elif status == "done" and attachment.file_hash:
        from app.models.embeddings import EmbeddingDocument

        read_hash = (
            db.query(EmbeddingDocument.source_hash)
            .filter(EmbeddingDocument.source_type == KNOWLEDGE_SOURCE, EmbeddingDocument.source_id == str(attachment.id))
            .scalar()
        )
        if read_hash == attachment.file_hash:
            return "This file is already read and has not changed."
    return None


def queue_type_files(db: Session, attachment_type_id: str) -> int:
    """A type just turned on: queue its files never read or failed, at most MAX_REQUEUE_PER_SAVE."""
    from app.models.resources import Attachment

    with company_scope(db, None):  # the type is company-less: its files in every company are read
        rows = (
            db.query(Attachment)
            .filter(
                Attachment.attachment_type_id == attachment_type_id,
                Attachment.is_deleted.is_(False),
                (Attachment.ai_read_status.is_(None)) | (Attachment.ai_read_status == "failed"),
            )
            .order_by(Attachment.created_at)
            .limit(MAX_REQUEUE_PER_SAVE)
            .all()
        )
        for row in rows:
            row.ai_read_status = "queued"
            row.ai_read_error = None
            row.ai_read_at = _now()
        db.commit()
        return sum(1 for row in rows if _enqueue_or_fail(db, row))


def _enqueue_or_fail(db: Session, attachment, check_pending: bool = True) -> bool:
    if check_pending and _job_pending(str(attachment.id)):
        return True  # the job with this id is still live; it will read the file
    try:
        _enqueue(str(attachment.id))
    except Exception:  # noqa: BLE001 - Redis down: the row says so, the save still stands
        logger.exception("knowledge read for %s could not be queued", attachment.id)
        attachment.ai_read_status = "failed"
        attachment.ai_read_error = READ_QUEUED_ERROR
        db.commit()
        return False
    return True


# ---------------------------------------------------------------- asking


def search(
    db: Session,
    *,
    user_id: str,
    query: str,
    top_k: int = 5,
    embed: Optional[Callable[[list[str]], list[list[float]]]] = None,
) -> dict:
    """Passages the caller may read, best first. Staff see every readable audience in P1.

    `{"status": "ok" | "denied" | "error", "passages": [...], "handoff_teams": [...]}`."""
    from app.models.access import Team
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.models.resources import Attachment, AttachmentType
    from app.services.embedding_service import _embedding_company_filter
    from app.services.user_service import UserPermissionService

    try:
        allowed = bool(UserPermissionService(db).check_user_has_permission(user_id, READ_PERMISSION))
    except Exception:  # noqa: BLE001 - a failed check is a refusal
        logger.warning("knowledge: permission check failed", exc_info=True)
        allowed = False
    if not allowed:
        return {"status": "denied", "passages": [], "handoff_teams": []}

    top_k = max(1, min(int(top_k or 5), MAX_TOP_K))
    try:
        vector = (embed or _default_embed(db, QUERY_EMBED_TIMEOUT_SECONDS))([query])[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge: query embedding failed: %s", _readable_error(exc))
        return {"status": "error", "passages": [], "handoff_teams": []}

    distance = EmbeddingChunk.embedding.cosine_distance(vector)
    similarity = (1 - distance).label("similarity")
    filters = [
        EmbeddingChunk.source_type == KNOWLEDGE_SOURCE,
        EmbeddingChunk.model_name == KNOWLEDGE_MODEL,
        EmbeddingChunk.is_current.is_(True),
        EmbeddingDocument.is_active.is_(True),
        Attachment.is_deleted.is_(False),
        AttachmentType.ai_audience.in_(READABLE_AUDIENCES),
        (1 - distance) >= KNOWLEDGE_SIMILARITY_FLOOR,
    ]
    company_filter = _embedding_company_filter(db)
    if company_filter is not None:
        filters.append(company_filter)
    rows = (
        db.query(EmbeddingChunk, Attachment.original_filename, similarity)
        .join(EmbeddingDocument, EmbeddingDocument.id == EmbeddingChunk.document_id)
        .join(Attachment, cast(Attachment.id, String) == EmbeddingChunk.source_id)
        .join(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(*filters)
        .order_by(distance)
        .limit(top_k)
        .all()
    )
    passages = []
    for chunk, filename, sim in rows:
        meta = chunk.metadata_json or {}
        passages.append(
            {
                "document": os.path.splitext(filename or "")[0] or (filename or ""),
                "page": meta.get("page"),
                "heading": meta.get("heading"),
                "text": chunk.chunk_text,
                "similarity": round(float(sim), 4),
            }
        )
    with company_scope(db, None):  # types are not company scoped, so neither is their hand-off team
        teams = (
            db.query(Team.name)
            .join(AttachmentType, AttachmentType.ai_escalate_team_id == Team.id)
            .filter(AttachmentType.ai_audience.in_(READABLE_AUDIENCES))
            .distinct()
            .all()
        )
    return {"status": "ok", "passages": passages, "handoff_teams": sorted(name for (name,) in teams)}


def search_for_contact(
    db: Session,
    *,
    access_codes,
    query: str,
    top_k: int = 5,
    embed: Optional[Callable[[list[str]], list[list[float]]]] = None,
) -> dict:
    """Passages a WhatsApp contact may read, best first (AGENTIC-KNOWLEDGE W1 S2).

    The same query as `search`, but the gate is the contact's ACTIVE access codes against the file's
    `access_levels`, by the type's audience: `dealer` needs an overlap with the codes other than
    `end_user`, `public` needs an overlap with any code, `staff` and `off` are never read. Company
    scope is the session's. No hand-off teams (team names are staff data).

    `{"status": "ok" | "error", "passages": [...]}`."""
    from sqlalchemy import and_, or_
    from sqlalchemy.dialects.postgresql import ARRAY

    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.models.resources import Attachment, AttachmentType
    from app.services.embedding_service import _embedding_company_filter

    codes = sorted({str(c) for c in (access_codes or ()) if c})
    if not codes:
        return {"status": "ok", "passages": []}
    dealer_codes = [c for c in codes if c != "end_user"]

    def overlaps(values: list[str]):
        # jsonb `?|`: the file's levels hold at least one of the codes.
        return Attachment.access_levels.op("?|")(cast(values, ARRAY(String)))

    audience = [and_(AttachmentType.ai_audience == "public", overlaps(codes))]
    if dealer_codes:
        audience.append(and_(AttachmentType.ai_audience == "dealer", overlaps(dealer_codes)))

    top_k = max(1, min(int(top_k or 5), MAX_TOP_K))
    try:
        vector = (embed or _default_embed(db, QUERY_EMBED_TIMEOUT_SECONDS))([query])[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge: query embedding failed: %s", _readable_error(exc))
        return {"status": "error", "passages": []}

    distance = EmbeddingChunk.embedding.cosine_distance(vector)
    similarity = (1 - distance).label("similarity")
    filters = [
        EmbeddingChunk.source_type == KNOWLEDGE_SOURCE,
        EmbeddingChunk.model_name == KNOWLEDGE_MODEL,
        EmbeddingChunk.is_current.is_(True),
        EmbeddingDocument.is_active.is_(True),
        Attachment.is_deleted.is_(False),
        or_(*audience),
        (1 - distance) >= KNOWLEDGE_SIMILARITY_FLOOR,
    ]
    company_filter = _embedding_company_filter(db)
    if company_filter is not None:
        filters.append(company_filter)
    rows = (
        db.query(EmbeddingChunk, Attachment.original_filename, similarity)
        .join(EmbeddingDocument, EmbeddingDocument.id == EmbeddingChunk.document_id)
        .join(Attachment, cast(Attachment.id, String) == EmbeddingChunk.source_id)
        .join(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(*filters)
        .order_by(distance)
        .limit(top_k)
        .all()
    )
    passages = []
    for chunk, filename, sim in rows:
        meta = chunk.metadata_json or {}
        passages.append(
            {
                "document": os.path.splitext(filename or "")[0] or (filename or ""),
                "page": meta.get("page"),
                "heading": meta.get("heading"),
                "text": chunk.chunk_text,
                "similarity": round(float(sim), 4),
            }
        )
    return {"status": "ok", "passages": passages}


# ---------------------------------------------------------------- the prompt paragraph

KNOWLEDGE_PROTOCOL = (
    f"{KNOWLEDGE_PROTOCOL_HEADER} (applies to `{KNOWLEDGE_TOOL}` and `user_guides_read`)\n"
    "Pick the tool by the kind of question. A question about company policy, HR rules, product "
    "documents or any uploaded document goes to `crm_knowledge_search` with the question as `query`. "
    "A question about how to use the CRM itself goes to `user_guides_read`.\n"
    "Answer ONLY from the passages `crm_knowledge_search` returns, and cite each fact as "
    "(document, p.N) using the passage's document and page. Never fill a gap from general knowledge.\n"
    "If it returns no passage, say the answer is not in the documents, and name the team in "
    "`handoff_teams` to ask (for example: please ask HR). If `handoff_teams` is empty, just say it is "
    "not in the documents. Do not open a ticket and do not promise one.\n"
)


def with_knowledge_protocol(system: str) -> str:
    """`system` with the KNOWLEDGE PROTOCOL appended once (idempotent on its header)."""
    if KNOWLEDGE_PROTOCOL_HEADER in (system or ""):
        return system
    return (system or "").rstrip() + "\n\n" + KNOWLEDGE_PROTOCOL
