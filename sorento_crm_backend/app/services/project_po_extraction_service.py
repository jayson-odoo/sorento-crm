"""Customer PO intake: read the scan, then let a person agree to it (P4, P5).

The whole slice turns on one sentence: **the AI proposes, arithmetic decides.** A
vision model transcribes a page; nothing it says about a number is believed until
``qty * unit_price == amount`` is recomputed here, in ``Decimal``, from the values it
gave. The measured payoff is exact: the 52 transcribed amounts sum to 1,810,640.62,
and minus the handwritten cancellation of line 7 (4,733.60) that is the quotation
total of 1,805,907.02 to the cent. One number validates the transcription, the
cancellation reading and the cross-check together.

Four rules follow from that, and none of them is negotiable:

* **Handwriting is never applied** (D11). A strike-through becomes a ``cancel_line``
  annotation in ``proposed`` state and the printed line stays exactly as printed.
  ``is_cancelled`` is set by a person accepting the card, through this service, in one
  place. The cancellation of item 7 exists ONLY in pencil, so auto applying it would
  move 4,733.60 on a model's opinion.
* **A version is the record of what the paper said.** Extracted lines and
  ``extracted_json`` never change after confirmation; the CONFIRMED state is written
  onto phase 1's ``project_purchase_order_lines``, which already carries the quotation
  cross-check and its two mismatch flags. That check is reused, never copied.
* **A page that fails does not fail the document.** Nine good pages out of ten is a
  document a person can finish. Every exit path writes a terminal state and a sentence
  they can act on, because a version stuck on "queued" reads as a hung system.
* **The same pencil note on a re-scan is the same note.** ``dedup_key`` is
  ``(written_date, sorted refers_to_lines, sha1 of normalised raw_text)``, and an
  already-actioned card carries its state, its reading AND its consequence forward onto
  the new version. One physical PO accumulates annotations over months and gets
  re-scanned; re-proposing a decision somebody already made is how a review queue stops
  being read.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project_so import (
    ANNOTATION_ACCEPTED,
    ANNOTATION_EDITED,
    ANNOTATION_PROPOSED,
    ANNOTATION_REJECTED,
    PO_STATUS_APPROVED,
    ProjectPOAnnotation,
    ProjectPOLine,
    ProjectPOVersion,
)
from app.models.projects import Project, ProjectPurchaseOrder, ProjectPurchaseOrderLine
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"

INTERP_CANCEL = "cancel_line"
INTERP_AMEND_CODE = "amend_code"
INTERP_AMEND_DESCRIPTION = "amend_description"
INTERP_SUCCESSOR_PO = "successor_po"
INTERP_SIGNATURE = "signature"
INTERP_OTHER = "other"

INTERPRETATIONS = frozenset(
    {
        INTERP_CANCEL,
        INTERP_AMEND_CODE,
        INTERP_AMEND_DESCRIPTION,
        INTERP_SUCCESSOR_PO,
        INTERP_SIGNATURE,
        INTERP_OTHER,
    }
)

# Keys inside ``interpretation_json``. Named as constants because the review screen reads
# and writes the same four, and a mismatch here is invisible until a person clicks Accept
# and nothing happens.
KEY_LINE_NOS = "line_nos"  # which printed lines the note is about
KEY_CODE = "code"  # the stock code an amend-code note means
KEY_DESCRIPTION = "description"  # the description an amend-description note means
KEY_PO_NUMBER = "po_number"  # the purchase order a note points at
# Older spellings, read but never written. An edit posted with the previous key must not
# silently apply nothing.
_LEGACY_KEYS = {
    KEY_LINE_NOS: ("lines",),
    KEY_CODE: ("stock_code",),
    KEY_PO_NUMBER: ("successor_po_number",),
}

# A scan is the normal case; a PO photographed on a phone is the other one.
ALLOWED_MIMES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
}
_EXTENSION_MIMES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}

# One attachment type for every project document, so the Files screens group them
# instead of growing a type per document kind.
ATTACHMENT_TYPE_CODE = "project_document"
ATTACHMENT_TYPE_NAME = "Project Document"
ATTACHMENT_ENTITY_TYPE = "project_po_version"

# Only ever visible for the moment between phase 1's "a PO needs its number" guard and
# the blanking below. The contract says an un-numbered upload creates the PO with an
# empty number and lets the confirm screen agree to the extracted one.
_PENDING_NUMBER = "(pending extraction)"

_CENTS = Decimal("0.01")

# A code-shaped token. Used to recover the real stock code from the description,
# because the customer's own code COLUMN is truncated by their printing (`SRTWC86`,
# `2155-BLUE`) and trusting that column alone yields a PO that resolves to nothing
# (AC-M1b, measured).
_CODE_TOKEN = re.compile(r"[A-Z0-9]{2,}(?:-[A-Z0-9]+)*")

# A PO number in the client's house style: three or more slash-separated segments, e.g.
# HQ/26/05/087. Deliberately not two, so the literal "P/O" in a pencil note is not read
# as a document number.
_PO_NUMBER_IN_TEXT = re.compile(
    r"\b[A-Z0-9]{1,10}(?:/[A-Z0-9]{1,10}){2,}\b", re.IGNORECASE
)

# How the note announces the number it is pointing at. Needed because these notes open
# with the date they were written -- "15/5/26 - Cancel item (7) ... Refer to New P/O
# HQ/26/05/087" -- and `15/5/26` is itself three slash-separated segments. Taking the
# first match would file the DATE as the successor purchase order.
_PO_NUMBER_TRIGGER = re.compile(
    r"(?:p\s*/\s*o|purchase\s+order|order\s+no|\bpo\b)", re.IGNORECASE
)

# Words a reader would use for each act, matched against the model's own "meaning"
# together with the verbatim text. The meaning is paraphrased differently page to page;
# the text is the thing that does not move.
_CANCEL_WORDS = ("cancel", "void", "delete", "struck", "strike", "cross out")
_SIGNATURE_WORDS = ("signature", "signed", "chop", "initial")
_AMEND_WORDS = ("amend", "change", "revise", "correct", "replace", "update")

_HEADER_TOTAL_KEYS = ("total", "grand_total", "total_amount", "po_total", "amount_total")

# Where the extractor's header keys land on our own header block.
_HEADER_ALIASES = {
    "po_number": ("po_number", "purchase_order_no", "po_no"),
    "po_date": ("po_date", "date"),
    "term": ("term", "terms", "term_days", "payment_term"),
    "sales_person": ("sales_person", "salesperson", "sales"),
    "customer_order_ref": ("cust_order_no", "customer_order_ref", "customer_order_no"),
    "remark": ("remark", "remarks", "note", "notes"),
}


# --------------------------------------------------------------- number handling


def _to_decimal(value: Any) -> Optional[Decimal]:
    """A model number to Decimal, via ``str``, never via ``float``.

    ``Decimal(392.85)`` is 392.85000000000000852651282912120223045349121093750 and a
    total built from 52 of those disagrees with the paper by cents. ``Decimal("392.85")``
    does not, and the cent is the whole proof.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _money(value: Optional[Decimal]) -> Decimal:
    return (value or Decimal("0")).quantize(_CENTS)


def _payload_value(payload: Dict[str, Any], key: str) -> Any:
    """Read one ``interpretation_json`` key, tolerating its older spelling."""
    if payload.get(key) not in (None, "", []):
        return payload[key]
    for legacy in _LEGACY_KEYS.get(key, ()):
        if payload.get(legacy) not in (None, "", []):
            return payload[legacy]
    return None


def _reason(exc: AppException) -> str:
    """``AppException`` stuffs its sentence into ``HTTPException.detail`` as a dict, so
    there is no ``.message`` attribute to read."""
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("message") or "")
    return str(detail or "")


def _int_or_none(value: Any) -> Optional[int]:
    """First integer in the value. ``"60 DAYS"`` is a term of 60."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else None


def arithmetic_ok(
    qty: Optional[Decimal], unit_price: Optional[Decimal], amount: Optional[Decimal]
) -> Optional[bool]:
    """``qty * unit_price == amount`` to two decimals, computed here.

    ``None`` when the page did not yield all three numbers. That is a different problem
    from a wrong one and must never count as a pass: a missing number is something a
    person types, a mismatch is something they reconcile.
    """
    if qty is None or unit_price is None or amount is None:
        return None
    return (qty * unit_price).quantize(_CENTS) == amount.quantize(_CENTS)


def _computed_amount(line: ProjectPOLine) -> Decimal:
    """Our own figure for a line: ``qty * unit_price``, falling back to the printed
    amount when the page did not yield both factors, so a short page understates
    nothing."""
    qty = _to_decimal(line.qty)
    unit_price = _to_decimal(line.unit_price)
    if qty is not None and unit_price is not None:
        return (qty * unit_price).quantize(_CENTS)
    return _money(_to_decimal(line.amount))


def _parse_date(value: Any) -> Optional[date]:
    """ISO first, then day-first, which is how every document here is written."""
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


# ----------------------------------------------------------------- text handling


def normalise_annotation_text(text: Optional[str]) -> str:
    """Alphanumerics only, lowercased.

    Punctuation is dropped rather than kept because one pencil note reads as
    "cancel - refer to New P/O HQ/26/05/087" on the first scan and
    "cancel , refer to new P/O HQ/26/05/087." on the second. Keeping punctuation would
    make those two different notes and re-propose a decision somebody already made.
    """
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _int_list(values: Optional[Iterable[Any]]) -> List[int]:
    out: List[int] = []
    for value in values or []:
        try:
            out.append(int(str(value).strip()))
        except (TypeError, ValueError):
            continue
    return out


def dedup_key(
    written_date: Optional[str],
    refers_to_lines: Optional[Sequence[Any]],
    raw_text: Optional[str],
) -> str:
    """Identity of a handwritten note across re-scans (D11, AC-D5)."""
    digest = hashlib.sha1(normalise_annotation_text(raw_text).encode()).hexdigest()
    lines = ",".join(str(n) for n in sorted(_int_list(refers_to_lines)))
    return f"{(written_date or '').strip()}|{lines}|{digest}"[:180]


def successor_po_number(text: Optional[str]) -> Optional[str]:
    """The PO a pencil note points forward to: `refer to New P/O HQ/26/05/087`.

    Read from the phrase that announces it rather than from the first slash-separated
    token, because these notes open with the date they were written and a date looks
    exactly like a PO number to a regex. Failing that, a candidate carrying a letter is
    taken, since a bare `26/1/26` is a date and nothing else.
    """
    body = text or ""
    candidates = [(match.start(), match.group(0).upper()) for match in _PO_NUMBER_IN_TEXT.finditer(body)]
    if not candidates:
        return None
    for trigger in _PO_NUMBER_TRIGGER.finditer(body):
        for start, candidate in candidates:
            if start >= trigger.end():
                return candidate
    for _start, candidate in candidates:
        if any(character.isalpha() for character in candidate):
            return candidate
    return None


def _looks_like_code(token: str) -> bool:
    """Long enough, and mixing letters with digits. Filters the English out: `CANCEL`
    and `NEW` are code-shaped to a regex and are not codes."""
    return (
        len(token) >= 4
        and any(character.isdigit() for character in token)
        and any(character.isalpha() for character in token)
    )


def _proposed_code(text: Optional[str]) -> Optional[str]:
    """The code an amend-code note seems to be naming.

    The LAST code-shaped token, because these notes are written as "change SRTWC8613-RL
    to SRTWC8608-RL" and the replacement comes second. A guess is acceptable here and
    only here: the card is a proposal, and a person either accepts it or edits it.
    """
    tokens = [
        token
        for token in _CODE_TOKEN.findall((text or "").upper())
        if _looks_like_code(token)
    ]
    return tokens[-1] if tokens else None


def classify_annotation(
    text: Optional[str],
    meaning: Optional[str],
    refers_to_lines: Optional[Sequence[Any]],
) -> Tuple[str, Dict[str, Any]]:
    """Read a note into one of the six interpretations, plus what applying it needs.

    Cancellation is tested first because it is the only reading that removes money, and
    a note that both cancels and names a successor ("cancel - refer to New P/O
    HQ/26/05/087") is ONE act by one hand: two cards for it would ask the reader the
    same question twice, so the successor rides along in ``interpretation_json`` and is
    applied by the same accept.
    """
    blob = f"{meaning or ''} {text or ''}".lower()
    lines = _int_list(refers_to_lines)
    successor = successor_po_number(text)
    payload: Dict[str, Any] = {KEY_LINE_NOS: lines}
    if successor:
        # One key for "the PO this note points at", whether the note cancels and
        # redirects or only redirects. Two keys meaning the same thing is how the screen
        # and the service end up disagreeing about which one to read.
        payload[KEY_PO_NUMBER] = successor

    if any(word in blob for word in _CANCEL_WORDS):
        return INTERP_CANCEL, payload
    if any(word in blob for word in _SIGNATURE_WORDS):
        return INTERP_SIGNATURE, payload
    if successor:
        return INTERP_SUCCESSOR_PO, payload

    amending = any(word in blob for word in _AMEND_WORDS)
    if amending and "code" in blob:
        proposed = _proposed_code(text)
        if proposed:
            payload[KEY_CODE] = proposed
        return INTERP_AMEND_CODE, payload
    if amending and "desc" in blob:
        return INTERP_AMEND_DESCRIPTION, payload
    return INTERP_OTHER, payload


# --------------------------------------------------------------------- the service


class ProjectPOExtractionService:
    """Everything the customer-PO document does, from upload to countersignature.

    One class rather than a module of functions because the worker entry point is fixed
    (``app.tasks.project_document_tasks`` calls ``run_extraction``) and because the
    read, the edit and the confirm all have to agree about the same four totals.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ lookups

    def get_version(self, po_version_id: str) -> ProjectPOVersion:
        version = (
            self.db.query(ProjectPOVersion)
            .filter(ProjectPOVersion.id == po_version_id)
            .first()
        )
        if version is None:
            raise AppException(
                status_code=404,
                message="That uploaded PO document could not be found.",
                code="po_version_not_found",
            )
        return version

    def get_po(self, po_id: str) -> ProjectPurchaseOrder:
        po = (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == po_id)
            .first()
        )
        if po is None:
            raise AppException(
                status_code=404,
                message="Purchase order not found.",
                code="po_not_found",
            )
        return po

    def get_annotation(self, annotation_id: str) -> ProjectPOAnnotation:
        annotation = (
            self.db.query(ProjectPOAnnotation)
            .filter(ProjectPOAnnotation.id == annotation_id)
            .first()
        )
        if annotation is None:
            raise AppException(
                status_code=404,
                message="That handwriting review card could not be found.",
                code="po_annotation_not_found",
            )
        return annotation

    def get_line(self, po_version_id: str, line_id: str) -> ProjectPOLine:
        line = (
            self.db.query(ProjectPOLine)
            .filter(
                ProjectPOLine.id == line_id,
                # Scoped to the version in the URL: without it a line id from another
                # document would be edited through a path that claims otherwise.
                ProjectPOLine.po_version_id == po_version_id,
            )
            .first()
        )
        if line is None:
            raise AppException(
                status_code=404,
                message="That extracted line could not be found on this document.",
                code="po_version_line_not_found",
            )
        return line

    def _lines(self, po_version_id: str) -> List[ProjectPOLine]:
        return (
            self.db.query(ProjectPOLine)
            .filter(ProjectPOLine.po_version_id == po_version_id)
            .order_by(ProjectPOLine.line_no.asc())
            .all()
        )

    def _annotations(self, po_version_id: str) -> List[ProjectPOAnnotation]:
        return (
            self.db.query(ProjectPOAnnotation)
            .filter(ProjectPOAnnotation.po_version_id == po_version_id)
            .order_by(
                ProjectPOAnnotation.page_no.asc().nulls_last(),
                ProjectPOAnnotation.created_at.asc(),
            )
            .all()
        )

    # ------------------------------------------------------------------- upload

    def create_version_from_upload(
        self,
        *,
        project: Project,
        actor_user_id: str,
        filename: Optional[str],
        mime: Optional[str],
        content: bytes,
        po_number: Optional[str] = None,
        purchase_order_id: Optional[str] = None,
    ) -> ProjectPOVersion:
        """Store the document and open a version row. Reading it happens on the worker.

        Synchronous only up to the point where the bytes are safe and a row exists: ten
        scanned pages take about two minutes to read, and an upload that holds the
        browser open for two minutes is an upload people stop doing.
        """
        if not content:
            raise AppException(
                status_code=422,
                message="The uploaded file was empty.",
                code="po_upload_empty",
            )
        resolved_mime = self._assert_supported(filename, mime)
        pages = self._page_count(content, resolved_mime)

        po = self._target_po(
            project=project,
            actor_user_id=actor_user_id,
            po_number=po_number,
            purchase_order_id=purchase_order_id,
        )

        next_no = (
            self.db.query(func.coalesce(func.max(ProjectPOVersion.version_no), 0))
            .filter(ProjectPOVersion.purchase_order_id == po.id)
            .scalar()
            or 0
        ) + 1

        version = ProjectPOVersion(
            company_id=po.company_id,
            purchase_order_id=po.id,
            version_no=next_no,
            source_filename=(filename or "").strip() or None,
            page_count=pages,
            extraction_state=STATE_QUEUED,
        )
        self.db.add(version)
        self.db.flush()

        version.attachment_id = self._store_document(
            version=version,
            filename=filename,
            mime=resolved_mime,
            content=content,
            actor_user_id=actor_user_id,
        )
        self.db.flush()
        return version

    def enqueue_extraction(self, version: ProjectPOVersion) -> Optional[str]:
        """Hand the version to the project-documents queue. Call AFTER the commit.

        A job that starts before the row is committed reads nothing and marks a
        perfectly good document as failed. Enqueued through the task module's own
        helper so the queue name lives in one place: every checkout of this repository
        shares one Redis, and a worker from another tree would claim a job whose task
        module it does not have. A failure to enqueue is reported on the row for the
        same reason every other exit path is -- the alternative is a version that says
        "queued" for ever.
        """
        from app.tasks.project_document_tasks import enqueue_po_extraction

        try:
            job = enqueue_po_extraction(str(version.id))
            return getattr(job, "id", None)
        except Exception as exc:  # noqa: BLE001 - the document is stored either way
            logger.exception("could not enqueue PO extraction for version %s", version.id)
            version.extraction_state = STATE_FAILED
            version.extraction_error = (
                "The document is stored but the reader could not be started "
                f"({str(exc)[:200]}). Retry the upload or fill the lines in by hand."
            )
            self.db.commit()
            return None

    def _assert_supported(self, filename: Optional[str], mime: Optional[str]) -> str:
        """Trust the extension over the browser's content type.

        A PDF dragged out of some mail clients arrives as ``application/octet-stream``,
        and refusing it would refuse the commonest way this document reaches us.
        """
        extension = ""
        if filename and "." in filename:
            extension = filename.rsplit(".", 1)[-1].strip().lower()
        if extension in _EXTENSION_MIMES:
            return _EXTENSION_MIMES[extension]
        normalised = (mime or "").split(";")[0].strip().lower()
        if normalised in ALLOWED_MIMES:
            return normalised
        raise AppException(
            status_code=422,
            message="A customer PO must be a PDF, a JPEG or a PNG.",
            code="po_upload_unsupported_type",
        )

    def _page_count(self, content: bytes, mime: str) -> Optional[int]:
        from app.services.document_extraction import page_count as document_page_count

        try:
            return document_page_count(content, mime)
        except Exception as exc:  # noqa: BLE001
            raise AppException(
                status_code=422,
                message=(
                    "That file could not be opened as a document. Re-export it and try "
                    f"again ({str(exc)[:120]})."
                ),
                code="po_upload_unreadable",
            ) from exc

    def _target_po(
        self,
        *,
        project: Project,
        actor_user_id: str,
        po_number: Optional[str],
        purchase_order_id: Optional[str],
    ) -> ProjectPurchaseOrder:
        """Which PO row this document is a version OF.

        A revision is never a second PO: one physical commitment is one row with one
        number, so an upload naming a number we already hold on this project joins that
        row (contract 2, AC-D5's sibling rule for documents).
        """
        from app.services import project_po_service as po_svc

        if purchase_order_id:
            po = self.get_po(purchase_order_id)
            if po.project_id != project.id:
                raise AppException(
                    status_code=422,
                    message="That purchase order belongs to a different project.",
                    code="po_foreign_project",
                )
            return po

        number = (po_number or "").strip()
        if number:
            existing = self._po_by_number(project.id, number)
            if existing is not None:
                return existing
            return po_svc.create_po(
                self.db,
                project=project,
                actor_user_id=actor_user_id,
                payload={"po_number": number, "po_source": "contractor_direct"},
            )

        # Nothing named it, so extraction proposes the number and the confirm screen is
        # where a human agrees to it. Only one un-numbered PO can be in flight per
        # project: the number is the only thing that tells two of them apart.
        pending = (
            self.db.query(ProjectPurchaseOrder)
            .filter(
                ProjectPurchaseOrder.project_id == project.id,
                func.coalesce(ProjectPurchaseOrder.po_number, "") == "",
            )
            .first()
        )
        if pending is not None:
            raise AppException(
                status_code=409,
                message=(
                    "An un-numbered purchase order on this project is already waiting "
                    "to be confirmed. Confirm it first, or give this upload its PO "
                    "number so the two can be told apart."
                ),
                code="po_unnumbered_already_pending",
            )
        po = po_svc.create_po(
            self.db,
            project=project,
            actor_user_id=actor_user_id,
            # Phase 1 refuses a PO with no number, correctly: one keyed in by hand
            # always has one. Written and then blanked rather than reaching around that
            # guard, so the auto status edge and the activity event still fire.
            payload={"po_number": _PENDING_NUMBER, "po_source": "contractor_direct"},
        )
        po.po_number = ""
        self.db.flush()
        return po

    def _po_by_number(
        self, project_id: str, number: str, *, exclude_id: Optional[str] = None
    ) -> Optional[ProjectPurchaseOrder]:
        query = self.db.query(ProjectPurchaseOrder).filter(
            ProjectPurchaseOrder.project_id == project_id,
            func.upper(func.trim(ProjectPurchaseOrder.po_number)) == number.strip().upper(),
        )
        if exclude_id:
            query = query.filter(ProjectPurchaseOrder.id != exclude_id)
        return query.first()

    def _attachment_type_id(self) -> str:
        """Get or create the project-document attachment type.

        ``attachment_types`` is a lookup table with no company scope and no migration of
        its own for this slice, so the type is ensured on first use rather than assumed.
        """
        from app.models.resources import AttachmentType

        row = (
            self.db.query(AttachmentType)
            .filter(AttachmentType.code == ATTACHMENT_TYPE_CODE)
            .first()
        )
        if row is not None:
            return row.id
        row = AttachmentType(
            code=ATTACHMENT_TYPE_CODE,
            type_name=ATTACHMENT_TYPE_NAME,
            description="Customer purchase orders and delivery schedules for project sales.",
            allowed_extensions="pdf,jpg,jpeg,png",
            max_file_size_mb=25,
        )
        self.db.add(row)
        self.db.flush()
        return row.id

    def _store_document(
        self,
        *,
        version: ProjectPOVersion,
        filename: Optional[str],
        mime: str,
        content: bytes,
        actor_user_id: Optional[str],
    ) -> Optional[str]:
        from app.services.entity_attachment_service import EntityAttachmentService
        from app.services.storage_router import (
            cdn_base_url,
            default_provider,
            get_backend,
            sanitize_storage_filename,
        )

        self._attachment_type_id()
        basename = (
            sanitize_storage_filename(filename) or f"customer-po.{ALLOWED_MIMES[mime]}"
        )
        # Keyed by the version id, never by name alone: two scans of the same PO are
        # routinely both called "PO.pdf" and a flat key would silently clobber one.
        key = f"{ATTACHMENT_ENTITY_TYPE}/{version.id}/{basename}"
        provider = default_provider()
        stored_key, _ = get_backend(provider).upload_file(
            file_content=content, file_path=key, content_type=mime
        )
        link = EntityAttachmentService(self.db).create_attachment_and_link(
            entity_type=ATTACHMENT_ENTITY_TYPE,
            entity_id=str(version.id),
            file_url=cdn_base_url(provider, stored_key),
            file_name=basename,
            file_size_bytes=len(content),
            attachment_type_code=ATTACHMENT_TYPE_CODE,
            created_by=actor_user_id,
            storage_provider=provider,
        )
        attachment = link.attachment
        if attachment is not None and not attachment.mime_type:
            attachment.mime_type = mime
        return link.attachment_id

    # --------------------------------------------------------------- extraction

    def run_extraction(self, po_version_id: str) -> Dict[str, Any]:
        """Worker entry point. Always leaves the row in a terminal state."""
        version = self.get_version(po_version_id)
        if version.confirmed_at is not None:
            # Confirmed means a person has already agreed to what this document said.
            # Re-reading it would rewrite the record, so the job is a no-op rather than
            # an error: an error would have the task mark a good version as failed.
            logger.info("PO version %s is already confirmed; skipping extraction", version.id)
            return {"status": "skipped", "reason": "already confirmed"}

        version.extraction_state = STATE_RUNNING
        version.extraction_error = None
        self.db.commit()

        from app.services.document_extraction import ExtractionUnavailable, extract_document

        try:
            content, mime = self._document_bytes(version)
        except AppException as exc:
            return self._fail(version, _reason(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("could not fetch the document for PO version %s", version.id)
            return self._fail(
                version, f"The stored document could not be read back ({str(exc)[:200]})."
            )

        try:
            result = extract_document(self.db, content, mime, prompt_key="po_extractor")
        except ExtractionUnavailable as exc:
            return self._fail(version, str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("PO extraction failed for version %s", version.id)
            return self._fail(
                version,
                f"The document reader failed ({str(exc)[:200]}). The document is stored "
                "and the lines can be filled in by hand.",
            )

        summary = self.persist_pages(
            version,
            result.pages,
            model=result.model,
            page_count=result.page_count,
            tokens_in=result.prompt_tokens,
            tokens_out=result.completion_tokens,
        )
        self.db.commit()
        return summary

    def _document_bytes(self, version: ProjectPOVersion) -> Tuple[bytes, str]:
        from app.models.resources import Attachment
        from app.services.storage_router import extract_key, get_backend

        attachment = (
            self.db.query(Attachment).filter(Attachment.id == version.attachment_id).first()
            if version.attachment_id
            else None
        )
        if attachment is None:
            raise AppException(
                status_code=422,
                message=(
                    "The uploaded file is no longer attached to this version. Upload the "
                    "document again."
                ),
                code="po_version_document_missing",
            )
        key = extract_key(attachment.file_path)
        if not key:
            raise AppException(
                status_code=422,
                message="The stored document has no readable location.",
                code="po_version_document_unlocatable",
            )
        content = get_backend(attachment.storage_provider).download_file(key)
        mime = attachment.mime_type or self._assert_supported(
            attachment.original_filename, None
        )
        return content, mime

    def _fail(self, version: ProjectPOVersion, message: str) -> Dict[str, Any]:
        """Terminal failure with a sentence somebody can act on."""
        self.db.rollback()
        version = self.get_version(str(version.id))
        version.extraction_state = STATE_FAILED
        version.extraction_error = (message or "Extraction failed.")[:500]
        self.db.commit()
        return {"status": "failed", "error": version.extraction_error}

    def persist_pages(
        self,
        version: ProjectPOVersion,
        pages: Sequence[Any],
        *,
        model: Optional[str] = None,
        page_count: Optional[int] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> Dict[str, Any]:
        """Turn per-page extractor output into lines, cards and four totals.

        ``pages`` is the extractor's own ``PageResult`` sequence, in page order, which
        is also the only thing a test needs to construct: everything decided below is
        decided from the payload, never from the model.
        """
        purchase_order = self.get_po(version.purchase_order_id)
        carried = self._carried_annotation_states(version)

        self.db.query(ProjectPOLine).filter(
            ProjectPOLine.po_version_id == version.id
        ).delete(synchronize_session=False)
        self.db.query(ProjectPOAnnotation).filter(
            ProjectPOAnnotation.po_version_id == version.id
        ).delete(synchronize_session=False)
        self.db.flush()

        header: Dict[str, Any] = {}
        printed_total: Optional[Decimal] = None
        page_blobs: List[Dict[str, Any]] = []
        failed_pages: List[int] = []
        used_line_nos: set[int] = set()
        struck_line_nos: List[int] = []
        annotation_specs: List[Dict[str, Any]] = []
        # Which page each line was printed on. Kept in ``extracted_json`` rather than on
        # the line row: the side-by-side viewer has to turn to the right page when a line
        # is selected, and a lookup that silently returns nothing leaves a screen that
        # still looks correct.
        line_pages: Dict[str, Optional[int]] = {}

        for page in pages:
            page_no = getattr(page, "page_no", None)
            data = getattr(page, "data", None) or {}
            error = getattr(page, "error", None)
            page_blobs.append({"page_no": page_no, "data": data or None, "error": error})
            if error or not data:
                if page_no is not None:
                    failed_pages.append(page_no)
                continue

            raw_header = data.get("header") or {}
            if isinstance(raw_header, dict):
                # First non-empty value wins. A header the model re-invented on page 7
                # must not overwrite the one it actually read on page 1.
                for target, aliases in _HEADER_ALIASES.items():
                    if header.get(target) not in (None, ""):
                        continue
                    for alias in aliases:
                        value = raw_header.get(alias)
                        if value not in (None, ""):
                            header[target] = value
                            break
                if printed_total is None:
                    for key in _HEADER_TOTAL_KEYS:
                        printed_total = _to_decimal(raw_header.get(key))
                        if printed_total is not None:
                            break

            for item in data.get("lines") or []:
                if not isinstance(item, dict):
                    continue
                line = self._line_from_payload(
                    version, item, used_line_nos=used_line_nos
                )
                if line is None:
                    continue
                line_pages[str(line.line_no)] = page_no
                if bool(item.get("struck_through")):
                    struck_line_nos.append(line.line_no)

            for note in data.get("annotations") or []:
                if not isinstance(note, dict):
                    continue
                text = str(note.get("text") or "").strip()
                if not text:
                    continue
                refers = note.get("refers_to_items")
                if refers is None:
                    refers = note.get("refers_to_lines")
                interpretation, payload = classify_annotation(
                    text, note.get("meaning"), refers
                )
                annotation_specs.append(
                    {
                        "page_no": page_no,
                        "raw_text": text,
                        "written_date": (str(note.get("date") or "").strip() or None),
                        "refers_to_lines": _int_list(refers),
                        "interpretation": interpretation,
                        "interpretation_json": payload,
                    }
                )

        # A strike-through with no note beside it is still an act somebody performed by
        # hand, so it gets its own card. Skipped when a note already cancels that line:
        # the pencil "cancel - refer to New P/O ..." and the line crossed out beneath it
        # are ONE decision, and two cards would ask for it twice.
        cancelled_by_note = {
            line_no
            for spec in annotation_specs
            if spec["interpretation"] == INTERP_CANCEL
            for line_no in _int_list(spec["interpretation_json"].get(KEY_LINE_NOS))
        }
        for line_no in sorted(set(struck_line_nos) - cancelled_by_note):
            annotation_specs.append(
                {
                    "page_no": line_pages.get(str(line_no)),
                    "raw_text": f"Line {line_no} is crossed out on the scan.",
                    "written_date": None,
                    "refers_to_lines": [line_no],
                    "interpretation": INTERP_CANCEL,
                    "interpretation_json": {
                        KEY_LINE_NOS: [line_no],
                        "source": "strike_through",
                    },
                }
            )

        seen_keys: set[str] = set()
        for spec in annotation_specs:
            key = dedup_key(spec["written_date"], spec["refers_to_lines"], spec["raw_text"])
            if key in seen_keys:
                continue  # the same note transcribed twice off two pages
            seen_keys.add(key)
            annotation = ProjectPOAnnotation(
                company_id=version.company_id,
                po_version_id=version.id,
                dedup_key=key,
                page_no=spec["page_no"],
                raw_text=spec["raw_text"],
                written_date=spec["written_date"],
                refers_to_lines=spec["refers_to_lines"],
                interpretation=spec["interpretation"],
                interpretation_json=spec["interpretation_json"],
                state=ANNOTATION_PROPOSED,
            )
            previous = carried.get(key)
            if previous is not None:
                # The decision AND the reading carry forward. Carrying the state alone
                # would show a card marked "edited" that still holds the model's
                # rejected reading.
                annotation.state = previous["state"]
                annotation.actioned_by = previous["actioned_by"]
                annotation.actioned_at = previous["actioned_at"]
                annotation.action_note = previous["action_note"]
                if previous["interpretation"]:
                    annotation.interpretation = previous["interpretation"]
                    annotation.interpretation_json = previous["interpretation_json"] or {}
            self.db.add(annotation)
        self.db.flush()

        # An accepted cancellation has to bite on the new version's lines too, or a
        # re-scan quietly resurrects 4,733.60 that somebody cancelled months ago.
        for annotation in self._annotations(version.id):
            if annotation.state in (ANNOTATION_ACCEPTED, ANNOTATION_EDITED):
                try:
                    self._apply_annotation(annotation, purchase_order)
                except AppException as exc:
                    logger.warning(
                        "carried annotation %s could not be re-applied to version %s: %s",
                        annotation.id,
                        version.id,
                        _reason(exc),
                    )

        version.extracted_json = {
            "header": header,
            "pages": page_blobs,
            "line_pages": line_pages,
        }
        if printed_total is not None:
            version.extracted_json["printed_total"] = str(printed_total)
        version.extraction_model = model
        version.extraction_tokens_in = tokens_in or None
        version.extraction_tokens_out = tokens_out or None
        if page_count:
            version.page_count = page_count

        purchase_order = self._reconcile_po_number(version, purchase_order, header)
        totals = self.recompute_totals(version)

        read_pages = [blob for blob in page_blobs if blob["data"]]
        if not read_pages:
            version.extraction_state = STATE_FAILED
            version.extraction_error = (
                "No page of this document could be read. The file is stored; the lines "
                "can be filled in by hand."
            )
        else:
            version.extraction_state = STATE_DONE
            version.extraction_error = (
                "Pages " + ", ".join(str(n) for n in failed_pages) + " could not be read; "
                "everything else on the document stands."
                if failed_pages
                else None
            )
        self.db.flush()

        return {
            "status": version.extraction_state,
            "po_version_id": str(version.id),
            "purchase_order_id": str(purchase_order.id),
            "po_number": purchase_order.po_number,
            "line_count": len(self._lines(version.id)),
            "annotation_count": len(self._annotations(version.id)),
            "failed_pages": failed_pages,
            "arithmetic_passed": totals["arithmetic_passed"],
            "arithmetic_total": totals["arithmetic_total"],
            "extracted_total": str(totals["extracted_total"])
            if totals["extracted_total"] is not None
            else None,
            "lines_total": str(totals["lines_total"]),
        }

    def _line_from_payload(
        self,
        version: ProjectPOVersion,
        item: Dict[str, Any],
        *,
        used_line_nos: set[int],
    ) -> Optional[ProjectPOLine]:
        stock_code = str(item.get("stock_code") or "").strip() or None
        description = str(item.get("description") or "").strip() or None
        qty = _to_decimal(item.get("qty"))
        unit_price = _to_decimal(item.get("unit_price"))
        amount = _to_decimal(item.get("amount"))
        if not any((stock_code, description, qty, unit_price, amount)):
            return None  # a blank table row at the tail of a page

        # Line numbering runs continuously across pages and follows the printed item
        # number wherever the document has one, because every handwritten note refers
        # to lines by THAT number ("cancel item 7").
        printed = _int_or_none(item.get("no"))
        if printed is not None and printed > 0 and printed not in used_line_nos:
            line_no = printed
        else:
            line_no = (max(used_line_nos) if used_line_nos else 0) + 1
        used_line_nos.add(line_no)

        product_id, source = self._resolve_product(stock_code, description)
        line = ProjectPOLine(
            company_id=version.company_id,
            po_version_id=version.id,
            line_no=line_no,
            stock_code_raw=(stock_code or "")[:180] or None,
            description_raw=description,
            qty=qty,
            uom_raw=(str(item.get("uom") or "").strip() or None),
            unit_price=unit_price,
            amount=amount,
            arithmetic_ok=arithmetic_ok(qty, unit_price, amount),
            resolved_product_id=product_id,
            resolution_source=source,
            # Never set here. A strike-through is a proposal until a person accepts the
            # card (D11); this is the one place that rule could be broken silently.
            is_cancelled=False,
        )
        self.db.add(line)
        self.db.flush()
        return line

    def _line_pages(self, version: ProjectPOVersion) -> Dict[str, Optional[int]]:
        pages = (version.extracted_json or {}).get("line_pages") or {}
        return pages if isinstance(pages, dict) else {}

    def _resolve_product(
        self, stock_code: Optional[str], description: Optional[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Recover our product from what the paper printed.

        The customer's stock-code COLUMN is truncated by their own printing, so the
        column is tried first and the DESCRIPTION second, where the full code survives
        (AC-M1b). Nothing is guessed: only an exact match on a catalogue code counts,
        and an unresolved line is left for a person rather than resolved approximately.
        """
        from app.models.product import Product

        code = (stock_code or "").strip().upper()
        if code:
            product = (
                self.db.query(Product)
                .filter(func.upper(Product.product_code) == code)
                .first()
            )
            if product is not None:
                return product.id, "code"

        candidates = [
            token
            for token in _CODE_TOKEN.findall((description or "").upper())
            if _looks_like_code(token)
        ]
        if candidates:
            # Longest first: `SRTWC8613-RL` is the code and `SRTWC8613` is a prefix of
            # it that may also exist as a different product.
            candidates.sort(key=len, reverse=True)
            matches = {
                str(product.product_code or "").upper(): product.id
                for product in self.db.query(Product)
                .filter(func.upper(Product.product_code).in_(candidates))
                .all()
            }
            for candidate in candidates:
                if candidate in matches:
                    return matches[candidate], "description"
        return None, None

    def _carried_annotation_states(
        self, version: ProjectPOVersion
    ) -> Dict[str, Dict[str, Any]]:
        """Decisions already taken on this PO's handwriting, keyed by ``dedup_key``.

        Across every version of the same PO, including this one, so a re-extraction of
        an unconfirmed version does not lose what a person already did. Later versions
        overwrite earlier ones because the later decision is the current one.
        """
        rows = (
            self.db.query(ProjectPOAnnotation, ProjectPOVersion.version_no)
            .join(ProjectPOVersion, ProjectPOAnnotation.po_version_id == ProjectPOVersion.id)
            .filter(ProjectPOVersion.purchase_order_id == version.purchase_order_id)
            .order_by(ProjectPOVersion.version_no.asc())
            .all()
        )
        carried: Dict[str, Dict[str, Any]] = {}
        for annotation, _version_no in rows:
            if annotation.state == ANNOTATION_PROPOSED:
                continue
            carried[annotation.dedup_key] = {
                "state": annotation.state,
                "actioned_by": annotation.actioned_by,
                "actioned_at": annotation.actioned_at,
                "action_note": annotation.action_note,
                "interpretation": annotation.interpretation,
                "interpretation_json": dict(annotation.interpretation_json or {}),
            }
        return carried

    def _reconcile_po_number(
        self,
        version: ProjectPOVersion,
        purchase_order: ProjectPurchaseOrder,
        header: Dict[str, Any],
    ) -> ProjectPurchaseOrder:
        """Adopt the extracted number, and re-parent when we already hold that PO.

        An un-numbered upload whose extracted number matches a PO already on this
        project is a REVISION of that PO, not a second one (contract 2). Two rows for
        one physical commitment would mean two answers to "what did the customer commit
        to", which is the thing the version table exists to prevent.
        """
        if (purchase_order.po_number or "").strip():
            return purchase_order  # the number was known before the upload
        number = str(header.get("po_number") or "").strip()
        if not number:
            return purchase_order

        match = self._po_by_number(
            purchase_order.project_id, number, exclude_id=str(purchase_order.id)
        )
        if match is None:
            purchase_order.po_number = number[:100]
            self.db.flush()
            self._adopt_pending_successors(purchase_order)
            return purchase_order

        # The next number is read BEFORE the re-parent is staged. Reversing the two lets
        # autoflush push a pending purchase_order_id with the OLD version_no still on it,
        # which collides with that PO's existing version 1.
        next_no = (
            self.db.query(func.coalesce(func.max(ProjectPOVersion.version_no), 0))
            .filter(
                ProjectPOVersion.purchase_order_id == match.id,
                ProjectPOVersion.id != version.id,
            )
            .scalar()
            or 0
        ) + 1
        version.purchase_order_id = match.id
        version.version_no = next_no
        self.db.flush()

        # The shell row existed only to hold this upload. Left behind it would show on
        # the project as an empty PO nobody can explain.
        siblings = (
            self.db.query(func.count(ProjectPOVersion.id))
            .filter(ProjectPOVersion.purchase_order_id == purchase_order.id)
            .scalar()
            or 0
        )
        lines = (
            self.db.query(func.count(ProjectPurchaseOrderLine.id))
            .filter(ProjectPurchaseOrderLine.po_id == purchase_order.id)
            .scalar()
            or 0
        )
        if siblings == 0 and lines == 0:
            self.db.delete(purchase_order)
            self.db.flush()
        return match

    # ------------------------------------------------------------------- totals

    def recompute_totals(self, version: ProjectPOVersion) -> Dict[str, Any]:
        """The four numbers the confirm screen leads with, recomputed from the lines.

        ``extracted_total`` is what the DOCUMENT says: its printed total where it has
        one, otherwise the sum of the amounts transcribed off it. ``lines_total`` is OUR
        sum of ``qty * unit_price`` over the lines that still stand. They agree exactly
        when every line's arithmetic holds and nothing is cancelled, which is why the
        difference is the best single signal that a page was misread, and why the
        cancelled amount is reported beside it instead of hidden inside it.
        """
        lines = self._lines(version.id)
        reported = sum((_money(_to_decimal(line.amount)) for line in lines), Decimal("0"))
        lines_total = Decimal("0")
        cancelled_total = Decimal("0")
        passed = 0
        for line in lines:
            computed = _computed_amount(line)
            if line.is_cancelled:
                cancelled_total += computed
            else:
                lines_total += computed
            if line.arithmetic_ok is True:
                passed += 1

        printed = _to_decimal((version.extracted_json or {}).get("printed_total"))
        extracted_total = printed if printed is not None else (reported if lines else None)

        version.arithmetic_passed = passed
        version.arithmetic_total = len(lines)
        version.extracted_total = extracted_total
        self.db.flush()

        lines_total = lines_total.quantize(_CENTS)
        cancelled_total = cancelled_total.quantize(_CENTS)
        # A gap that is EXACTLY the cancelled amount is a fact, not an alarm. Compared
        # exactly rather than with a tolerance, because on the client's own PO the gap is
        # 4,733.60 to the cent and a "close enough" rule would either pass a real misread
        # or block a publish for ever on a PO that is correct.
        reconciles = (
            extracted_total is None
            or (lines_total + cancelled_total) == extracted_total.quantize(_CENTS)
        )
        return {
            "extracted_total": extracted_total,
            "lines_total": lines_total,
            "cancelled_total": cancelled_total,
            "arithmetic_passed": passed,
            "arithmetic_total": len(lines),
            "reconciles": reconciles,
        }

    # --------------------------------------------------------------- line edits

    def update_line(
        self,
        *,
        version: ProjectPOVersion,
        line: ProjectPOLine,
        payload: Dict[str, Any],
    ) -> ProjectPOLine:
        """Correct a transcribed line. Recomputes its arithmetic and the version totals."""
        self._assert_unconfirmed(version)

        for field in (
            "stock_code_raw",
            "description_raw",
            "qty",
            "uom_raw",
            "unit_price",
            "amount",
            "is_cancelled",
        ):
            if field in payload:
                setattr(line, field, payload[field])

        if "resolved_product_id" in payload:
            product_id = payload["resolved_product_id"]
            if product_id:
                from app.models.product import Product

                product = (
                    self.db.query(Product).filter(Product.id == product_id).first()
                )
                if product is None:
                    raise AppException(
                        status_code=404,
                        message="That product could not be found.",
                        code="product_not_found",
                    )
                line.resolved_product_id = product.id
                line.resolution_source = "manual"
            else:
                line.resolved_product_id = None
                line.resolution_source = None
        elif ("stock_code_raw" in payload or "description_raw" in payload) and (
            line.resolution_source != "manual"
        ):
            # Re-resolve off the corrected text, but never over a person's own pick:
            # they chose it BECAUSE the automatic reading was wrong.
            product_id, source = self._resolve_product(
                line.stock_code_raw, line.description_raw
            )
            line.resolved_product_id = product_id
            line.resolution_source = source

        line.arithmetic_ok = arithmetic_ok(
            _to_decimal(line.qty), _to_decimal(line.unit_price), _to_decimal(line.amount)
        )
        self.db.flush()
        self.recompute_totals(version)
        return line

    # ------------------------------------------------------------- header editing

    HEADER_FIELDS = (
        "po_number",
        "po_date",
        "term_days",
        "sales_person",
        "customer_order_ref",
        "remark",
    )

    def update_header(
        self, *, version: ProjectPOVersion, payload: Dict[str, Any]
    ) -> ProjectPOVersion:
        """Correct the extracted header before it is confirmed (AC-D3).

        The corrections land in ``extracted_json['header']``, which is what the confirm
        then adopts onto the PO row, so there is exactly one path by which a header value
        reaches the purchase order. ``admin_ref`` is the exception and goes straight to
        the PO: the PS filing reference is OURS (D24), never something printed on the
        customer's paper, so it does not belong in a record of what the paper said.
        """
        self._assert_unconfirmed(version)
        po = self.get_po(version.purchase_order_id)

        if "admin_ref" in payload:
            value = str(payload["admin_ref"] or "").strip()
            po.admin_ref = value[:64] or None

        extracted = dict(version.extracted_json or {})
        header = dict(extracted.get("header") or {})
        for field in self.HEADER_FIELDS:
            if field not in payload:
                continue
            value = payload[field]
            if field == "po_number":
                number = str(value or "").strip()
                if number:
                    clash = self._po_by_number(po.project_id, number, exclude_id=str(po.id))
                    if clash is not None:
                        raise AppException(
                            status_code=409,
                            message=(
                                f"PO {clash.po_number} on this project already carries "
                                "that number. Upload this document as a new version of "
                                "it rather than as a second purchase order."
                            ),
                            code="po_number_already_on_project",
                        )
                header["po_number"] = number or None
            elif field == "po_date":
                header["po_date"] = value.isoformat() if isinstance(value, date) else (
                    str(value or "").strip() or None
                )
            elif field == "term_days":
                # Stored under the extractor's own key so confirm reads one place. The
                # value is already an integer here, and `_int_or_none` tolerates both.
                header["term"] = _int_or_none(value)
            else:
                header[field] = str(value or "").strip() or None

        extracted["header"] = header
        version.extracted_json = extracted
        self.db.flush()
        return version

    # ------------------------------------------------------------------ confirm

    def confirm_version(
        self, *, version: ProjectPOVersion, actor_user_id: str
    ) -> Dict[str, Any]:
        """Write the confirmed state onto the phase-1 PO row and its lines.

        The version keeps its extracted JSON and lines untouched for ever: they are the
        record of what the document said. What a person agreed to lands on
        ``project_purchase_order_lines``, where the quotation cross-check and its two
        mismatch flags already live, so that comparison is reused rather than rebuilt.
        """
        from app.services import project_po_service as po_svc

        self._assert_unconfirmed(version)
        if version.extraction_state != STATE_DONE:
            raise AppException(
                status_code=409,
                message=(
                    "This document is still being read."
                    if version.extraction_state in (STATE_QUEUED, STATE_RUNNING)
                    else "This document could not be read, so there is nothing to confirm."
                ),
                code="po_version_not_extracted",
            )

        pending = [
            annotation
            for annotation in self._annotations(version.id)
            if annotation.state == ANNOTATION_PROPOSED
        ]
        if pending:
            raise AppException(
                status_code=409,
                message=(
                    f"{len(pending)} handwritten note"
                    f"{'s' if len(pending) > 1 else ''} on this document still need a "
                    "decision. Accept, edit or reject each card first -- a cancellation "
                    "written in pencil is the only place some of these lines exist."
                ),
                code="po_version_annotations_pending",
            )

        lines = self._lines(version.id)
        live = [line for line in lines if not line.is_cancelled]
        if not live:
            raise AppException(
                status_code=409,
                message="Every line on this document is cancelled, so there is nothing to confirm.",
                code="po_version_no_live_lines",
            )

        po = self.get_po(version.purchase_order_id)
        header = (version.extracted_json or {}).get("header") or {}

        number = str(header.get("po_number") or "").strip()
        if number and number.upper() != (po.po_number or "").strip().upper():
            clash = self._po_by_number(po.project_id, number, exclude_id=str(po.id))
            if clash is not None:
                raise AppException(
                    status_code=409,
                    message=(
                        f"PO {clash.po_number} on this project already carries that "
                        "number. Upload this document as a new version of it rather "
                        "than as a second purchase order."
                    ),
                    code="po_number_already_on_project",
                )
            po.po_number = number[:100]

        po_date = _parse_date(header.get("po_date"))
        if po_date is not None:
            po.po_date = po_date
        term_days = _int_or_none(header.get("term"))
        if term_days is not None:
            po.term_days = term_days
        for source_key, attribute, limit in (
            ("sales_person", "sales_person", 120),
            ("customer_order_ref", "customer_order_ref", 180),
        ):
            value = str(header.get(source_key) or "").strip()
            if value:
                setattr(po, attribute, value[:limit])
        remark = str(header.get("remark") or "").strip()
        if remark:
            po.notes = remark

        # Rewritten, not merged: the confirmed version IS the current statement of what
        # the customer committed to, and a merge would leave lines from a superseded
        # reading standing beside it.
        for existing in po_svc.list_lines(self.db, po_id=po.id):
            po_svc.delete_line(self.db, line=existing)

        written: List[ProjectPurchaseOrderLine] = []
        for line in live:
            code = (line.stock_code_raw or "").strip()
            if not code and line.resolved_product_id is None:
                raise AppException(
                    status_code=422,
                    message=(
                        f"Line {line.line_no} has no stock code and no product. Enter one "
                        "before confirming -- a PO line with neither cannot be checked "
                        "against the quotation."
                    ),
                    code="po_version_line_unidentified",
                )
            written.append(
                po_svc.upsert_line(
                    self.db,
                    po=po,
                    payload={
                        "product_id": line.resolved_product_id,
                        "product_code": code or None,
                        "description": line.description_raw,
                        "unit_price": _money(_to_decimal(line.unit_price)),
                        "quantity": _to_decimal(line.qty) or Decimal("1"),
                        "uom": line.uom_raw,
                        "sort_order": line.line_no,
                    },
                )
            )

        totals = self.recompute_totals(version)
        po.po_amount = totals["lines_total"]
        version.confirmed_by = actor_user_id
        version.confirmed_at = datetime.utcnow()
        self.db.flush()

        self._adopt_pending_successors(po)

        return {
            "purchase_order_id": str(po.id),
            "po_number": po.po_number,
            "po_version_id": str(version.id),
            "version_no": version.version_no,
            "confirmed_at": version.confirmed_at,
            "line_count": len(written),
            "po_amount": po.po_amount,
            "model_mismatch_count": sum(1 for line in written if line.model_mismatch),
            "price_mismatch_count": sum(1 for line in written if line.price_mismatch),
        }

    # -------------------------------------------------------- approval handshake

    def approve_po(
        self, *, po: ProjectPurchaseOrder, actor_user_id: str
    ) -> ProjectPurchaseOrder:
        """AC-D8. CS cannot open the SO draft until this has happened (D21)."""
        if po.approved_at is not None:
            raise AppException(
                status_code=409,
                message=(
                    "This purchase order was already approved by "
                    f"{self._user_name(po.approved_by) or 'another user'}."
                ),
                code="po_already_approved",
            )
        # A PO that arrived as a document is approved only once somebody has agreed to
        # what the document said. A PO keyed in by hand has no versions and keeps working
        # on its lines alone, which is the phase-1 path and still legitimate.
        versions = (
            self.db.query(func.count(ProjectPOVersion.id))
            .filter(ProjectPOVersion.purchase_order_id == po.id)
            .scalar()
            or 0
        )
        if versions:
            confirmed = (
                self.db.query(func.count(ProjectPOVersion.id))
                .filter(
                    ProjectPOVersion.purchase_order_id == po.id,
                    ProjectPOVersion.confirmed_at.isnot(None),
                )
                .scalar()
                or 0
            )
            if not confirmed:
                raise AppException(
                    status_code=409,
                    message=(
                        "Confirm the uploaded document first. Approving a purchase order "
                        "nobody has checked against the scan is exactly what the confirm "
                        "screen exists to prevent."
                    ),
                    code="po_version_not_confirmed",
                )
        has_lines = (
            self.db.query(func.count(ProjectPurchaseOrderLine.id))
            .filter(ProjectPurchaseOrderLine.po_id == po.id)
            .scalar()
            or 0
        ) > 0
        if not has_lines:
            raise AppException(
                status_code=409,
                message=(
                    "This purchase order has no lines yet. Confirm an uploaded document "
                    "or enter the lines before approving it."
                ),
                code="po_nothing_to_approve",
            )
        po.approved_by = actor_user_id
        po.approved_at = datetime.utcnow()
        po.status = PO_STATUS_APPROVED
        self.db.flush()
        return po

    def countersign_po(
        self, *, po: ProjectPurchaseOrder, actor_user_id: str
    ) -> ProjectPurchaseOrder:
        if po.approved_at is None:
            raise AppException(
                status_code=409,
                message="A purchase order has to be approved before it can be countersigned.",
                code="po_not_approved",
            )
        if po.countersigned_at is not None:
            raise AppException(
                status_code=409,
                message=(
                    "This purchase order was already countersigned by "
                    f"{self._user_name(po.countersigned_by) or 'another user'}."
                ),
                code="po_already_countersigned",
            )
        if po.approved_by and str(po.approved_by) == str(actor_user_id):
            raise AppException(
                status_code=409,
                message=(
                    "A countersignature has to come from a second person -- that is the "
                    "whole point of it."
                ),
                code="po_countersign_same_user",
            )
        po.countersigned_by = actor_user_id
        po.countersigned_at = datetime.utcnow()
        self.db.flush()
        return po

    # -------------------------------------------------------- annotation actions

    def accept_annotation(
        self,
        *,
        annotation: ProjectPOAnnotation,
        actor_user_id: str,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        version = self.get_version(annotation.po_version_id)
        self._assert_actionable(version, annotation)
        purchase_order = self.get_po(version.purchase_order_id)
        applied = self._apply_annotation(annotation, purchase_order)
        self._stamp_action(annotation, ANNOTATION_ACCEPTED, actor_user_id, note)
        return {
            "annotation": annotation,
            "applied": applied,
            "totals": self.recompute_totals(version),
        }

    def edit_annotation(
        self,
        *,
        annotation: ProjectPOAnnotation,
        actor_user_id: str,
        interpretation: str,
        interpretation_json: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The human's reading wins, then applies exactly as an accept does."""
        version = self.get_version(annotation.po_version_id)
        self._assert_actionable(version, annotation)
        reading = (interpretation or "").strip()
        if reading not in INTERPRETATIONS:
            raise AppException(
                status_code=422,
                message=(
                    "Unknown reading. Use one of: "
                    + ", ".join(sorted(INTERPRETATIONS))
                    + "."
                ),
                code="po_annotation_interpretation_unknown",
            )
        # Merged, not replaced: the screen sends the fields it has an input for, and a
        # key it does not render (the strike-through marker, say) must survive an edit.
        merged = dict(annotation.interpretation_json or {})
        merged.update(interpretation_json or {})
        if _payload_value(merged, KEY_LINE_NOS) is None:
            merged[KEY_LINE_NOS] = _int_list(annotation.refers_to_lines)
        annotation.interpretation = reading
        annotation.interpretation_json = merged
        if reading in (INTERP_CANCEL, INTERP_AMEND_CODE, INTERP_AMEND_DESCRIPTION):
            # The lines the reader named are also the lines the card now refers to, so
            # the card and its effect can never disagree on screen.
            annotation.refers_to_lines = _int_list(_payload_value(merged, KEY_LINE_NOS))

        purchase_order = self.get_po(version.purchase_order_id)
        applied = self._apply_annotation(annotation, purchase_order)
        self._stamp_action(annotation, ANNOTATION_EDITED, actor_user_id, note)
        return {
            "annotation": annotation,
            "applied": applied,
            "totals": self.recompute_totals(version),
        }

    def reject_annotation(
        self, *, annotation: ProjectPOAnnotation, actor_user_id: str, note: str
    ) -> Dict[str, Any]:
        """Recorded as rejected, never deleted (AC-D4). Nothing is applied."""
        version = self.get_version(annotation.po_version_id)
        self._assert_actionable(version, annotation)
        if not (note or "").strip():
            raise AppException(
                status_code=422,
                message=(
                    "A rejection needs a reason: it is the only thing that explains "
                    "later why the pencil was ignored."
                ),
                code="po_annotation_reason_required",
            )
        self._stamp_action(annotation, ANNOTATION_REJECTED, actor_user_id, note)
        return {
            "annotation": annotation,
            "applied": {
                "cancelled_line_nos": [],
                "amended_line_nos": [],
                "successor_po_number": None,
                "successor_po_linked": False,
            },
            "totals": self.recompute_totals(version),
        }

    def _assert_actionable(
        self, version: ProjectPOVersion, annotation: ProjectPOAnnotation
    ) -> None:
        self._assert_unconfirmed(version)
        if annotation.state != ANNOTATION_PROPOSED:
            raise AppException(
                status_code=409,
                message=(
                    f"This card was already {annotation.state} by "
                    f"{self._user_name(annotation.actioned_by) or 'another user'}. Correct "
                    "the line itself if the decision needs changing."
                ),
                code="po_annotation_already_actioned",
            )

    def _stamp_action(
        self,
        annotation: ProjectPOAnnotation,
        state: str,
        actor_user_id: str,
        note: Optional[str],
    ) -> None:
        annotation.state = state
        annotation.actioned_by = actor_user_id
        annotation.actioned_at = datetime.utcnow()
        annotation.action_note = (note or "").strip() or None
        self.db.flush()

    def _apply_annotation(
        self, annotation: ProjectPOAnnotation, purchase_order: ProjectPurchaseOrder
    ) -> Dict[str, Any]:
        """The only place a handwritten note changes anything (D11)."""
        payload = dict(annotation.interpretation_json or {})
        interpretation = annotation.interpretation or INTERP_OTHER
        line_nos = _int_list(_payload_value(payload, KEY_LINE_NOS)) or _int_list(
            annotation.refers_to_lines
        )
        wanted = set(line_nos)
        lines = [
            line for line in self._lines(annotation.po_version_id) if line.line_no in wanted
        ]
        applied: Dict[str, Any] = {
            "cancelled_line_nos": [],
            "amended_line_nos": [],
            "successor_po_number": None,
            "successor_po_linked": False,
        }

        if interpretation in (INTERP_CANCEL, INTERP_AMEND_CODE, INTERP_AMEND_DESCRIPTION):
            if not lines:
                raise AppException(
                    status_code=422,
                    message=(
                        "This card does not name a line that exists on the document. Edit "
                        "it to say which printed line the note is about."
                    ),
                    code="po_annotation_lines_unknown",
                )

        if interpretation == INTERP_CANCEL:
            for line in lines:
                line.is_cancelled = True
                applied["cancelled_line_nos"].append(line.line_no)
        elif interpretation == INTERP_AMEND_CODE:
            code = str(_payload_value(payload, KEY_CODE) or "").strip()
            if not code:
                raise AppException(
                    status_code=422,
                    message=(
                        "This note amends a stock code but does not say which code. Edit "
                        "the card and enter it."
                    ),
                    code="po_annotation_code_required",
                )
            for line in lines:
                line.stock_code_raw = code[:180]
                if line.resolution_source != "manual":
                    line.resolved_product_id, line.resolution_source = self._resolve_product(
                        line.stock_code_raw, line.description_raw
                    )
                applied["amended_line_nos"].append(line.line_no)
        elif interpretation == INTERP_AMEND_DESCRIPTION:
            description = str(_payload_value(payload, KEY_DESCRIPTION) or "").strip()
            if not description:
                raise AppException(
                    status_code=422,
                    message=(
                        "This note amends a description but does not say what to. Edit the "
                        "card and enter it."
                    ),
                    code="po_annotation_description_required",
                )
            for line in lines:
                line.description_raw = description
                applied["amended_line_nos"].append(line.line_no)

        # A successor pointer can ride on a cancellation ("cancel - refer to New P/O
        # HQ/26/05/087"), which is how the client actually writes it.
        successor = str(_payload_value(payload, KEY_PO_NUMBER) or "").strip()
        if interpretation == INTERP_SUCCESSOR_PO and not successor:
            raise AppException(
                status_code=422,
                message=(
                    "This note points at another purchase order but does not name it. Edit "
                    "the card and enter the PO number."
                ),
                code="po_annotation_successor_required",
            )
        if successor:
            applied["successor_po_number"] = successor
            applied["successor_po_linked"] = self._link_successor(purchase_order, successor)
        self.db.flush()
        return applied

    def _link_successor(self, po: ProjectPurchaseOrder, number: str) -> bool:
        """Wire the supersede pointer, if the successor document has arrived (AC-D7).

        A pencil note names the successor months before that PO is uploaded, so the
        text pointer stands alone on the card until then and this returns False. The
        link is made from the other direction as well, by ``_adopt_pending_successors``
        when the named PO finally appears.
        """
        successor = self._po_by_number(po.project_id, number, exclude_id=str(po.id))
        if successor is None:
            return False
        po.superseded_by_po_id = successor.id
        successor.supersedes_po_number = (po.po_number or None)
        self.db.flush()
        return True

    def _adopt_pending_successors(self, po: ProjectPurchaseOrder) -> None:
        """Close the loop when a PO named in an earlier pencil note finally arrives."""
        number = (po.po_number or "").strip()
        if not number:
            return
        rows = (
            self.db.query(ProjectPOAnnotation, ProjectPurchaseOrder)
            .join(ProjectPOVersion, ProjectPOAnnotation.po_version_id == ProjectPOVersion.id)
            .join(
                ProjectPurchaseOrder,
                ProjectPOVersion.purchase_order_id == ProjectPurchaseOrder.id,
            )
            .filter(
                ProjectPurchaseOrder.project_id == po.project_id,
                ProjectPurchaseOrder.id != po.id,
                ProjectPOAnnotation.state.in_([ANNOTATION_ACCEPTED, ANNOTATION_EDITED]),
            )
            .all()
        )
        for annotation, predecessor in rows:
            payload = dict(annotation.interpretation_json or {})
            named = str(_payload_value(payload, KEY_PO_NUMBER) or "").strip()
            if named and named.upper() == number.upper():
                predecessor.superseded_by_po_id = po.id
                po.supersedes_po_number = predecessor.po_number or None
        self.db.flush()

    # --------------------------------------------------------------- serialising

    def serialize_version(self, version: ProjectPOVersion) -> Dict[str, Any]:
        from app.models.resources import Attachment
        from app.services.storage_router import resolve_signed_url

        po = self.get_po(version.purchase_order_id)
        project = self.db.query(Project).filter(Project.id == po.project_id).first()
        header = (version.extracted_json or {}).get("header") or {}
        totals = self.recompute_totals(version)

        attachment = (
            self.db.query(Attachment).filter(Attachment.id == version.attachment_id).first()
            if version.attachment_id
            else None
        )
        document_url = (
            resolve_signed_url(
                attachment.file_path, provider=attachment.storage_provider
            )
            if attachment is not None
            else None
        )

        # How much of the document was actually read. "Only 7 of 10 pages were read" is
        # the first thing the screen has to say, and it cannot say it from a state of
        # "done" plus a sentence.
        blobs = (version.extracted_json or {}).get("pages") or []
        pages_extracted = sum(1 for blob in blobs if isinstance(blob, dict) and blob.get("data"))
        failed_pages = [
            blob.get("page_no")
            for blob in blobs
            if isinstance(blob, dict) and not blob.get("data") and blob.get("page_no")
        ]
        line_pages = self._line_pages(version)

        return {
            "id": str(version.id),
            "purchase_order_id": str(po.id),
            "po_number": po.po_number or "",
            "project_id": str(po.project_id),
            "project_title": getattr(project, "title", None),
            "version_no": version.version_no,
            "extraction_state": version.extraction_state,
            "extraction_error": version.extraction_error,
            "extraction_model": version.extraction_model,
            "page_count": version.page_count,
            "pages_extracted": pages_extracted,
            "failed_pages": failed_pages,
            "document_url": document_url,
            "source_filename": version.source_filename,
            "header": {
                "po_number": header.get("po_number") or po.po_number or None,
                "po_date": _parse_date(header.get("po_date")) or po.po_date,
                "term_days": _int_or_none(header.get("term")) or po.term_days,
                "sales_person": header.get("sales_person") or po.sales_person,
                "customer_order_ref": (
                    header.get("customer_order_ref") or po.customer_order_ref
                ),
                # D24: the PS filing reference is ours, not something printed on their
                # paper, so it comes off the PO row and never out of the scan.
                "admin_ref": po.admin_ref,
                "remark": header.get("remark") or po.notes,
            },
            "totals": totals,
            "lines": [
                self.serialize_line(line, page_no=line_pages.get(str(line.line_no)))
                for line in self._lines(version.id)
            ],
            "annotations": [
                self.serialize_annotation(annotation)
                for annotation in self._annotations(version.id)
            ],
            # The approval stamps live on the PO, not the version, but the confirm screen
            # is where they are read and shown, so they travel with the version.
            "purchase_order": {
                "po_number": po.po_number or "",
                "status": po.status,
                "approved_by_name": self._user_name(po.approved_by),
                "approved_at": po.approved_at,
                "countersigned_by_name": self._user_name(po.countersigned_by),
                "countersigned_at": po.countersigned_at,
            },
            "confirmed_at": version.confirmed_at,
            "confirmed_by_name": self._user_name(version.confirmed_by),
            "created_at": version.created_at,
        }

    def serialize_line(
        self, line: ProjectPOLine, *, page_no: Optional[int] = None
    ) -> Dict[str, Any]:
        product_code = None
        product_name = None
        if line.resolved_product_id:
            from app.models.product import Product

            product = (
                self.db.query(Product).filter(Product.id == line.resolved_product_id).first()
            )
            if product is not None:
                product_code = product.product_code
                product_name = product.product_name
        return {
            "id": str(line.id),
            "line_no": line.line_no,
            # Which page it was printed on, so selecting a line turns the viewer to it.
            "page_no": page_no,
            "stock_code_raw": line.stock_code_raw,
            "description_raw": line.description_raw,
            "qty": line.qty,
            "uom_raw": line.uom_raw,
            "unit_price": line.unit_price,
            "amount": line.amount,
            "arithmetic_ok": line.arithmetic_ok,
            "is_cancelled": bool(line.is_cancelled),
            "resolved_product_id": line.resolved_product_id,
            "resolved_product_code": product_code,
            "resolved_product_name": product_name,
            "resolution_source": line.resolution_source,
        }

    def serialize_annotation(self, annotation: ProjectPOAnnotation) -> Dict[str, Any]:
        from app.services.storage_router import resolve_signed_url

        crop_url = None
        if annotation.crop_attachment_id:
            from app.models.resources import Attachment

            crop = (
                self.db.query(Attachment)
                .filter(Attachment.id == annotation.crop_attachment_id)
                .first()
            )
            if crop is not None:
                crop_url = resolve_signed_url(
                    crop.file_path, provider=crop.storage_provider
                )
        return {
            "id": str(annotation.id),
            "page_no": annotation.page_no,
            "crop_url": crop_url,
            "raw_text": annotation.raw_text,
            "written_date": annotation.written_date,
            "refers_to_lines": _int_list(annotation.refers_to_lines),
            "interpretation": annotation.interpretation,
            "interpretation_json": dict(annotation.interpretation_json or {}),
            "state": annotation.state,
            "actioned_by_name": self._user_name(annotation.actioned_by),
            "actioned_at": annotation.actioned_at,
            "action_note": annotation.action_note,
        }

    def serialize_po_approval(self, po: ProjectPurchaseOrder) -> Dict[str, Any]:
        return {
            "id": str(po.id),
            "po_number": po.po_number or "",
            "project_id": str(po.project_id),
            "status": po.status,
            "approved_by_name": self._user_name(po.approved_by),
            "approved_at": po.approved_at,
            "countersigned_by_name": self._user_name(po.countersigned_by),
            "countersigned_at": po.countersigned_at,
        }

    # ------------------------------------------------------------------- guards

    def _assert_unconfirmed(self, version: ProjectPOVersion) -> None:
        if version.confirmed_at is not None:
            raise AppException(
                status_code=409,
                message=(
                    "This version is confirmed. It is the record of what the document "
                    "said and cannot be edited -- upload the revised document as a new "
                    "version instead."
                ),
                code="po_version_confirmed",
            )

    def _user_name(self, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        from app.models.user import User

        row = self.db.query(User.name, User.email).filter(User.id == user_id).first()
        if row is None:
            return None
        return row[0] or row[1]
