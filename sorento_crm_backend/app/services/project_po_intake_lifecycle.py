"""The PO document's LIFECYCLE: upload, extraction, persistence, edits, totals.

One of the three mixins ``ProjectPOExtractionService`` is assembled from (2026-08-12
audit split). This one owns everything between "a file arrived" and "a person can
read it": storage, the worker entry point, page persistence with the arithmetic
check, product resolution, and the line/header edits made while reconciling.
Methods are verbatim from the original service; only the module boundary is new.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
from app.models.projects import (
    QUOTATION_OUTCOME_LOST,
    QUOTATION_OUTCOME_OPEN,
    QUOTATION_OUTCOME_WON,
    Project,
    ProjectPurchaseOrder,
    ProjectPurchaseOrderLine,
    ProjectQuotation,
    ProjectQuotationVersion,
)
from app.services.error_handler import AppException
from app.services.project_po_reading import (  # noqa: F401 - shared vocabulary
    STATE_QUEUED,
    STATE_RUNNING,
    STATE_DONE,
    STATE_FAILED,
    INTERP_CANCEL,
    INTERP_AMEND_CODE,
    INTERP_AMEND_DESCRIPTION,
    INTERP_SUCCESSOR_PO,
    INTERP_SIGNATURE,
    INTERP_OTHER,
    INTERPRETATIONS,
    KEY_LINE_NOS,
    KEY_CODE,
    KEY_DESCRIPTION,
    KEY_PO_NUMBER,
    _LEGACY_KEYS,
    ALLOWED_MIMES,
    _EXTENSION_MIMES,
    ATTACHMENT_TYPE_CODE,
    ATTACHMENT_TYPE_NAME,
    ATTACHMENT_ENTITY_TYPE,
    _PENDING_NUMBER,
    _CENTS,
    _CODE_TOKEN,
    _PO_NUMBER_IN_TEXT,
    _PO_NUMBER_TRIGGER,
    _CANCEL_WORDS,
    _SIGNATURE_WORDS,
    _AMEND_WORDS,
    _HEADER_ALIASES,
    _HEADER_TOTAL_KEYS,
    _to_decimal,
    _money,
    _payload_value,
    _reason,
    _int_or_none,
    _is_description_fragment,
    arithmetic_ok,
    _computed_amount,
    _parse_date,
    normalise_annotation_text,
    _int_list,
    dedup_key,
    successor_po_number,
    _looks_like_code,
    _squash,
    _code_tokens,
    _proposed_code,
    classify_annotation,
)

logger = logging.getLogger(__name__)


class POIntakeLifecycleMixin:
    """Requires ``self.db``. The facade class supplies it."""

    db: Session

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
        perfectly good document as failed. Enqueued through the recovery service, which
        owns the queue name in one place AND records which job is reading this version:
        a work-horse that is killed does not run the task's own error handling, so the
        only way to tell a dead read from a slow one afterwards is to ask RQ about that
        job. A failure to enqueue is reported on the row for the same reason every other
        exit path is -- the alternative is a version that says "queued" for ever.
        """
        from app.services import project_extraction_recovery_service as recovery

        return recovery.start_job(self.db, version)

    def reconcile_stranded(self, versions) -> int:
        """Give a verdict to any of these reads whose worker died. See S20.

        Called from the read path, which is where somebody is actually waiting to be
        told. Silent and cheap when there is nothing wrong.
        """
        from app.services import project_extraction_recovery_service as recovery

        return recovery.reconcile(self.db, versions)

    def retry_extraction(self, version: ProjectPOVersion) -> ProjectPOVersion:
        """Read this document again, on the same version. 409 when there is nothing to
        retry: still in flight, already read, or confirmed."""
        from app.services import project_extraction_recovery_service as recovery

        return recovery.retry(self.db, version)

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

        from app.services import project_extraction_recovery_service as recovery

        version.extraction_state = STATE_RUNNING
        version.extraction_error = None
        # The reader is the only thing that knows when it actually picked the document up,
        # and that stamp is what lets a wait be reported as a length rather than as an
        # unbounded spinner - and what the reconciler falls back on for a row carrying no
        # job id.
        recovery.mark_started(self.db, version)
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
            elapsed_ms=result.elapsed_ms,
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
        elapsed_ms: Optional[int] = None,
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
        # The most recent real line, so a wrapped description can find its way home even
        # when the wrap happens across a page boundary.
        last_line: Optional[ProjectPOLine] = None

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
                # A description with no item number, no code and no money on it is the
                # tail of the row above wrapping onto the next row or the next page, not
                # a row of its own. Rejoining it here rather than trusting the model to
                # never split keeps the line count equal to the printed item count.
                if last_line is not None and _is_description_fragment(item):
                    fragment = str(item.get("description") or "").strip()
                    last_line.description_raw = (
                        f"{last_line.description_raw} {fragment}".strip()
                        if last_line.description_raw
                        else fragment
                    )
                    self.db.flush()
                    continue
                line = self._line_from_payload(
                    version, item, used_line_nos=used_line_nos
                )
                if line is None:
                    continue
                last_line = line
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
                    text,
                    note.get("meaning"),
                    refers,
                    # The model classifies the note it just read; the keywords inside are
                    # only the fallback for prompt versions that predate these fields.
                    model_kind=note.get("kind"),
                    model_payload=note,
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
        version.extraction_elapsed_ms = elapsed_ms or None
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

        product_id, source = self._resolve_product(
            stock_code, description, company_id=version.company_id
        )
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
        self,
        stock_code: Optional[str],
        description: Optional[str],
        *,
        company_id: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Recover our product from what the paper printed.

        ``company_id`` is not optional in spirit. One product code exists once per
        company, so a lookup that spans companies can attach a Mocha row to a Sorento
        purchase order: the code is right and the row belongs to somebody else. That
        really happened, and it surfaced two screens away, as a delivery schedule
        failing to reconcile against its own PO because the two had resolved the same
        code to different rows. Callers pass the PO's company.

        The customer's stock-code COLUMN is truncated by their own printing, so the
        column is tried first and the DESCRIPTION second, where the full code survives
        (AC-M1b). Nothing is guessed: only an exact match on a catalogue code counts,
        and an unresolved line is left for a person rather than resolved approximately.
        """
        from app.models.product import Product

        def _scoped(query):
            return query.filter(Product.company_id == company_id) if company_id else query

        code = (stock_code or "").strip().upper()
        if code:
            product = (
                _scoped(self.db.query(Product))
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
                for product in _scoped(self.db.query(Product))
                .filter(func.upper(Product.product_code).in_(candidates))
                .all()
            }
            for candidate in candidates:
                if candidate in matches:
                    return matches[candidate], "description"

        # Nothing matched CHARACTER FOR CHARACTER, which on real paper is the common
        # case rather than the exception. Measured on the client's own PO: of 14 lines
        # that got this far, half name a product we genuinely stock and half name one
        # that is not in the item master at all. Telling those two apart is the whole
        # job, so the tiers below relax the comparison in ways that cannot change WHICH
        # product is meant, and stop rather than guess when more than one could be.
        return self._resolve_product_loosely(code, candidates, company_id=company_id)

    def _resolve_product_loosely(
        self, code: str, description_codes: List[str], *, company_id: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Match the way a person reads a code, not the way a string comparison does.

        Three things the customer's paper does that an equality test cannot survive,
        all taken from their real purchase order:

        * punctuation drifts. They write `SRTFH15CR`, the catalogue says `SRTFH15-CR`.
        * the tokens get reordered. They write `B2155-BLUE-NL`, we stock `B2155-NL-BLUE`.
        * their stock-code column is narrow and TRUNCATES, so `SRTWC8613-RL` prints as
          `SRTWC86` and the rest of the code survives only in the description.

        None of these is ambiguity, they are the same product spelled differently, and a
        person resolves them in a second. What IS ambiguity is a relaxed form matching
        more than one catalogue code, and every tier below refuses in that case rather
        than picking a winner. On a 1.8 million ringgit order the cost of quietly
        attaching the wrong product is far higher than the cost of asking.
        """
        from app.models.product import Product

        wanted = [c for c in ([code] if code else []) + list(description_codes) if c]
        if not wanted:
            return None, None

        # One pass over the catalogue's shapes. `product_code` is indexed but none of
        # these comparisons can use that index, so the work is done in Python against a
        # projection rather than as several LIKE scans per line.
        catalogue = self.db.query(Product.id, Product.product_code)
        if company_id:
            catalogue = catalogue.filter(Product.company_id == company_id)
        rows = catalogue.all()
        # Keyed by CODE, not by row. This catalogue holds several rows under one code
        # (`C-FH12` appears twice), and counting rows made every such product look
        # ambiguous and refuse itself. The real question is whether more than one
        # DISTINCT code fits, so the first row of each code is what a code resolves to.
        by_squashed: Dict[str, Dict[str, str]] = {}
        by_tokens: Dict[frozenset, Dict[str, str]] = {}
        for product_id, product_code in rows:
            raw = str(product_code or "").upper()
            if not raw:
                continue
            by_squashed.setdefault(_squash(raw), {}).setdefault(raw, product_id)
            by_tokens.setdefault(frozenset(_code_tokens(raw)), {}).setdefault(raw, product_id)

        def _only(bucket: Optional[Dict[str, str]]) -> Optional[str]:
            """One code is an answer. Two different codes is a question for a person."""
            if not bucket or len(bucket) != 1:
                return None
            return next(iter(bucket.values()))

        # Tier 1: same characters once punctuation is dropped.
        for candidate in sorted(wanted, key=len, reverse=True):
            hit = _only(by_squashed.get(_squash(candidate)))
            if hit:
                return hit, "code_normalised"

        # Tier 2: same tokens in a different order.
        for candidate in sorted(wanted, key=len, reverse=True):
            hit = _only(by_tokens.get(frozenset(_code_tokens(candidate))))
            if hit:
                return hit, "code_reordered"

        # Tier 3: the truncated column names the start of a code, and something in the
        # description confirms which one. Neither half is enough alone: a short prefix
        # matches dozens of products, and the description often carries the customer's
        # own spelling rather than ours. Together they identify one product.
        prefix = _squash(code)
        if len(prefix) >= 4 and description_codes:
            confirmed: Dict[str, str] = {}
            for squashed, codes in by_squashed.items():
                if not squashed.startswith(prefix):
                    continue
                # The description's spelling need not equal ours; it needs to agree
                # about the distinctive tail. `SRTW8613RL` confirms `SRTWC8613RL`
                # because both end the same way, and the column already agreed about
                # the start.
                if any(
                    squashed.endswith(_squash(d)[-6:])
                    for d in description_codes
                    if len(_squash(d)) >= 6
                ):
                    confirmed.update(codes)
            hit = _only(confirmed)
            if hit:
                return hit, "code_truncated"

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
                line.stock_code_raw, line.description_raw, company_id=line.company_id
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

