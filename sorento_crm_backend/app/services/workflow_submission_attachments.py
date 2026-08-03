"""Files hang off a workflow submission, or off ONE LINE of it (F2c).

F1 gave a submission a status, F1a gave its lines one, F2a gave it a clock and F2b let
a contact file it. This module is the last piece after-sales S1 needs on the write side:
the customer photographs the cracked unit and the bytes land somewhere that can say
which unit they are of.

Four decisions shape it, and each one is a place where the obvious implementation is
wrong:

**The proof belongs to the LINE, not only to the case.** An RMA lists five items and two
of them are damaged. A submission-only linkage cannot express "photo of the cracked unit
on line 2" at all, and it is also the difference between a 10-file cap meaning ten photos
per claim and ten photos per item. Both scopes ride the EXISTING polymorphic
``entity_attachment_links`` table under two entity types declared here, once. A bespoke
``workflow_submission_attachments`` table would be this repo's THIRD linkage pattern, on
the one feature whose whole premise is that a new form is configuration rather than code
(AC-F2c-1).

**``entity_attachment_links`` has no foreign key on ``entity_id``.** A line id belonging
to somebody else's claim inserts perfectly happily and the file then appears under their
item. The parent/child check is made here because the database will not make it, and it
is made in the SERVICE rather than at a route so every caller inherits it: a guard on the
action routes is not a guard (ADR-0013 rule 7).

**The key is ``{type}/{attachment id}/{sanitized filename}``.** The middle segment is the
ATTACHMENT id, not the entity id: two files with the same name on one line would still
collide under an entity id, and 120 keys in this repo were already shared between records
before uuid segregation (AC-F2c-14). The basename goes through
``sanitize_storage_filename`` because ``original_filename`` is raw client input and
``"../../etc/passwd.png"`` would otherwise add a segment and land the object outside its
own id folder, re-opening that collision through the customer's own file picker
(AC-F2c-13). The raw name is still stored on the row: it is what the customer sent.

**Order of operations is the feature.** Quota is checked BEFORE bytes are stored (a
refused upload that already wrote leaves an orphan object, billed, undeletable through
the UI and invisible to the storage audit), and the ``attachments`` row is written AFTER
the bytes land (a row whose bytes were never written renders as a permanently broken link
while the customer believes the photo was received). The id is generated up front so both
can be true at once.

The per-type cap counts per LINKED ROW, so a line file counts against the LINE and a
case-level file has its own budget (AC-F2c-11). ``company_id`` stays NULL: ``Attachment``
is ``__company_shared__`` and ``workflow_submissions`` has no company at all, so stamping
a scope on the child of an unscoped parent would leave a submission visible under a scope
where its own evidence had vanished (AC-F2c-10).

See documentation/plans/forms-platform/forms-platform-acceptance-criteria.md, group F2c
and the "F2c corrections" section.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment, AttachmentType
from app.models.workflow_forms import WorkflowSubmission, WorkflowSubmissionLine
from app.services.attachment_validation_service import (
    apply_outcome,
    normalize_coordinates,
    validate_upload,
)
from app.services.entity_attachment_service import EntityAttachmentService
from app.services.error_handler import AppException, handle_not_found
from app.services.workflow_submission_line_status_graph import (
    WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
)
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
)

# The extension helper the neighbouring upload paths use. Imported rather than copied:
# a third private spelling of "what is this file's extension" is how the quota check and
# the storage key start disagreeing about what was uploaded.
from app.services.entity_attachment_service import (
    _response_attachment_ext as _extension,
)

logger = logging.getLogger(__name__)


# The two link scopes, declared once each. Aliases of the status-engine entity types on
# purpose: a submission is one entity across the platform, and a second hand-written
# copy of "workflow_submission_line" is how the writer and the reader drift until a
# stored photo can never be listed again. Both fit
# entity_attachment_links.entity_type (VARCHAR(50)).
SUBMISSION_ENTITY_TYPE = WORKFLOW_SUBMISSION_ENTITY_TYPE
SUBMISSION_LINE_ENTITY_TYPE = WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE

# The attachment_types row that carries the configurable cap, the allowed extensions and
# the size limit. Its own type, never a shared one: sharing portal_submission's row would
# make a submission's evidence budget move whenever somebody retunes the four bespoke
# portal forms.
ATTACHMENT_TYPE_CODE = "workflow_submission_file"
ATTACHMENT_TYPE_NAME = "Workflow Submission File"

# What the seed writes. max_count_per_entity mirrors the portal_submission type (10 per
# linked row); it is configuration, so an admin changes it without a deploy and a blank
# means unlimited.
_SEED_VALUES: Dict[str, Any] = {
    "type_name": ATTACHMENT_TYPE_NAME,
    "description": (
        "Files attached to a workflow form submission, or to one line of it. Uploaded "
        "by staff in the CRM or by the contact from the portal."
    ),
    "allowed_extensions": "jpg,jpeg,png,heic,webp,gif,pdf,doc,docx,xls,xlsx,csv,txt",
    "max_file_size_mb": 10,
    "max_count_per_entity": 10,
}


def seed_workflow_submission_attachment_type(db: Session) -> AttachmentType:
    """Create or CORRECT the submission attachment type. Flushes, never commits.

    Converge rather than insert-if-absent (ADR-0013 rule 10): a re-run repairs a drifted
    extension list or size limit IN PLACE, keeping the row's id, so every attachment
    already pointing at it follows the repair. ``max_count_per_entity`` is deliberately
    part of the converged set - it is the cap, and a seed that could not correct it could
    not fix a bad one either.

    Called from the migration rather than restated as SQL there, so the code under test
    and the deploy cannot disagree about the code string.
    """
    row = (
        db.query(AttachmentType)
        .filter(AttachmentType.code == ATTACHMENT_TYPE_CODE)
        .first()
    )
    if row is None:
        row = AttachmentType(
            id=str(uuid.uuid4()), code=ATTACHMENT_TYPE_CODE, **_SEED_VALUES
        )
        db.add(row)
    else:
        for field, value in _SEED_VALUES.items():
            if getattr(row, field, None) != value:
                setattr(row, field, value)
    db.flush()
    return row


class WorkflowSubmissionAttachmentService:
    """Upload, link and list the files of one submission.

    One service for both scopes and both origins. The rule that decides WHERE bytes land
    and the rule that decides HOW MANY of them a record may hold live beside each other
    because they are the same rule seen twice: the cap is per linked row, and the linked
    row is what the key's id segment de-duplicates.
    """

    def __init__(self, db: Session):
        self.db = db
        self.links = EntityAttachmentService(db)

    # ------------------------------------------------------------------- resolving

    def _submission(self, submission_id: str) -> WorkflowSubmission:
        row = (
            self.db.query(WorkflowSubmission)
            .filter(WorkflowSubmission.id == str(submission_id or "").strip())
            .first()
        )
        if row is None:
            raise handle_not_found("Submission", submission_id)
        return row

    def _line(self, submission: WorkflowSubmission, line_id: str) -> WorkflowSubmissionLine:
        """One line OF THIS SUBMISSION, or 404.

        Scoped by ``submission_id`` in the QUERY, not checked after the read: a line from
        another claim is then never loaded and never distinguishable from one that does
        not exist, which is the same shape as the portal's ownership scoping.
        """
        row = (
            self.db.query(WorkflowSubmissionLine)
            .filter(
                WorkflowSubmissionLine.id == str(line_id or "").strip(),
                WorkflowSubmissionLine.submission_id == str(submission.id),
            )
            .first()
        )
        if row is None:
            raise AppException(
                status_code=404,
                message="That line does not belong to this submission.",
                code="submission_line_not_found",
            )
        return row

    def _target(
        self, submission_id: str, line_id: Optional[str]
    ) -> Tuple[WorkflowSubmission, Optional[WorkflowSubmissionLine], str, str]:
        """The (submission, line, entity_type, entity_id) one file is about.

        The line wins when it is named, and the header is NOT also linked: a header
        listing that absorbed every line's file would disagree with the cap, the UI and
        the customer's own view about how many files the case holds, and the adjudicator
        could no longer tell which photo is of which item.
        """
        submission = self._submission(submission_id)
        if str(line_id or "").strip():
            line = self._line(submission, str(line_id))
            return submission, line, SUBMISSION_LINE_ENTITY_TYPE, str(line.id)
        return submission, None, SUBMISSION_ENTITY_TYPE, str(submission.id)

    @staticmethod
    def _uploader(
        uploaded_by: Optional[str], uploaded_by_contact_id: Optional[str]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """(uploaded_by, uploaded_by_contact_id, uploader_kind) for one upload.

        A contact wins when both are given, because only the portal passes a contact and
        it never has a ``users.id`` to pass.

        The staff id is dropped unless it is uuid-shaped: ``attachments.uploaded_by`` is
        a ``uuid`` column while ``users.id`` is ``String(64)`` (the API-key principal is
        literally ``system``), so passing one through unchecked raises "invalid input
        syntax for type uuid" and the upload 500s. Every neighbouring call site drops it
        and keeps the file. The KIND is still recorded, so the row degrades to "a staff
        member we cannot name" rather than to "unknown origin".
        """
        contact_id = str(uploaded_by_contact_id or "").strip()
        if contact_id:
            return None, contact_id, "contact"
        user_id = str(uploaded_by or "").strip()
        if not user_id:
            return None, None, None
        return (user_id if len(user_id) == 36 else None), None, "user"

    # ---------------------------------------------------------------------- writing

    def upload(
        self,
        *,
        submission_id: str,
        contents: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        line_id: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        uploaded_by_contact_id: Optional[str] = None,
        notify: bool = True,
        latitude: Any = None,
        longitude: Any = None,
    ) -> Dict[str, Any]:
        """Store one file and link it to the submission or to one of its lines.

        Returns the fixed upload-and-link shape every other upload path in this repo
        returns, so an FE panel can render a submission's files with the component it
        already has.

        The sequence is load-bearing:

        1. resolve the target and REFUSE a line that belongs to another submission,
        2. check the cap for THAT row, before anything is stored,
        3. judge the bytes, if this type asked to be judged,
        4. store the bytes under a key carrying the new attachment's own id,
        5. only then write the row, so a storage failure leaves nothing behind,
        6. commit, and only then tell anybody.

        ``notify=False`` exists for a bulk/import caller that wants one message rather
        than one per file. It is not a way to skip the guard above it.

        Step 3 is the S2a wiring, and it is here rather than per domain because this
        one path already routes BOTH submission and line attachments through the one
        link table, so wiring it once reaches every consuming slice without any of
        them growing its own scorer (AC-M21).

        The score NEVER decides whether the file is kept. A validator that discards
        the bytes it judged makes Retake free but the failure unobservable, and it
        means a timeout loses a photo somebody already took, in the rain, once
        (AC-M23c). The verdict rides back in the response instead: the FE cannot work
        out whether 35 is a pass, because it does not know the type's threshold, and
        the comparison has already been made here.

        ``latitude`` / ``longitude`` arrive WITH the upload because that is the only
        moment the device knows where it is - a later PATCH records where the person
        happened to be when they got round to it. A denied, absent or impossible fix
        is dropped and the upload proceeds (AC-M27: never blocking).
        """
        submission, line, entity_type, entity_id = self._target(submission_id, line_id)

        attachment_type = self.links.get_attachment_type_by_code(ATTACHMENT_TYPE_CODE)
        payload = contents or b""
        size = len(payload)
        extension = _extension(filename, content_type)
        # Before the object is stored. Uploading first and checking after leaves an
        # orphan object per refused attempt, which nothing in the product can then see
        # or delete.
        self.links.check_quota(attachment_type, entity_type, entity_id, size, extension)

        # Before anything is written, so a validator that has to roll a failed prompt
        # lookup back cannot take a half-built attachment row with it. It never
        # raises, whatever the model does.
        outcome = validate_upload(
            self.db,
            attachment_type=attachment_type,
            data=payload,
            filename=filename,
            content_type=content_type,
        )
        capture_latitude, capture_longitude = normalize_coordinates(latitude, longitude)

        # Generated here, not read back from the row, so the key can carry it while the
        # row is still unwritten. That is what lets the quota check precede the upload
        # AND the upload precede the row.
        attachment_id = str(uuid.uuid4())
        raw_name = (filename or "file").strip()[:255]
        from app.services.storage_router import (
            default_provider,
            get_backend,
            sanitize_storage_filename,
        )

        key = f"{ATTACHMENT_TYPE_CODE}/{attachment_id}/{sanitize_storage_filename(raw_name)}"
        provider = default_provider()
        backend = get_backend(provider)
        try:
            backend.upload_file(payload, key, content_type=content_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Submission attachment upload failed (provider=%s, submission=%s): %s",
                provider,
                submission.id,
                exc,
            )
            raise AppException(
                status_code=502,
                message="File upload failed. Please try again.",
                code="UPLOAD_FAILED",
            ) from exc

        # Grid thumbnail (images only). Best-effort by contract: a failed thumbnail must
        # never fail the upload it decorates.
        from app.services.image_thumbnailer import store_thumbnail

        thumbnail_path = store_thumbnail(backend, provider, key, payload, content_type)

        user_id, contact_id, uploader_kind = self._uploader(
            uploaded_by, uploaded_by_contact_id
        )
        attachment = Attachment(
            id=attachment_id,
            attachment_type_id=str(attachment_type.id),
            # Raw, exactly as the customer's device named it: this is the immutable
            # upload name and the thing the key basename is derived FROM. Only the
            # derivation is sanitized.
            original_filename=raw_name,
            # The editable display name, seeded from the same value. Two columns, two
            # jobs: renaming a file in the Files page must not move its bytes.
            stored_filename=raw_name,
            file_path=key,
            thumbnail_path=thumbnail_path,
            file_size_bytes=size,
            mime_type=content_type,
            storage_provider=provider,
            uploaded_by=user_id,
            uploaded_by_contact_id=contact_id,
            uploader_kind=uploader_kind,
            # NULL on purpose, and NOT merely left to the default: a submission has no
            # company, so scoping its evidence would hide the evidence from the scope
            # that can still see the submission (AC-F2c-10).
            company_id=None,
        )
        self.db.add(attachment)
        self.db.flush()
        link = self.links.link_existing_attachment(
            entity_type=entity_type,
            entity_id=entity_id,
            attachment_id=attachment_id,
            created_by=user_id,
        )
        # A `skipped` outcome writes NOTHING here, so a type that never opted in is
        # indistinguishable from every row written before this slice landed.
        apply_outcome(link, outcome)
        link.latitude = capture_latitude
        link.longitude = capture_longitude
        self.db.commit()
        self.db.refresh(link)
        self.db.refresh(attachment)

        if notify:
            self._notify(submission, attachment, line)

        return {
            "link_id": str(link.id),
            "attachment_id": str(attachment.id),
            "filename": attachment.original_filename,
            "size": size,
            "url": self.links._resolve_attachment_url(str(attachment.file_path)),
            "content_type": attachment.mime_type,
            # `validation_passed` is three-valued and the FE must treat it that way:
            # False is "judged and short of the bar" (show the suggestion and a
            # prominent Retake), None is "no claim made" and must never render as a
            # failure. `ai_validation_state` says which kind of None it is.
            "ai_validation_state": link.ai_validation_state,
            "ai_validation_reason": link.ai_validation_reason,
            "ai_score": link.ai_score,
            "ai_suggestion": link.ai_suggestion,
            "validation_passed": outcome.passed,
        }

    def _notify(
        self,
        submission: WorkflowSubmission,
        attachment: Attachment,
        line: Optional[WorkflowSubmissionLine],
    ) -> None:
        """Tell whoever is handling the case that evidence arrived. Never raises.

        Post-commit: the bytes are in the bucket and the row is committed by the time
        anyone is told, so raising here would hand the caller a 502 for an upload that
        worked and the customer's retry would upload the file a second time.

        The rollback matters as much as the catch. A failure mid-flush leaves the session
        unusable, and the caller's very next read would then raise PendingRollbackError:
        a 500 for the same successful operation, one line later, with a stack trace
        pointing somewhere innocent.
        """
        try:
            from app.services.workflow_submission_notify import notify_attachment_added

            notify_attachment_added(
                self.db, submission, attachment=attachment, line=line
            )
        except Exception as exc:  # noqa: BLE001
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001 - nothing left to salvage
                logger.warning("Session rollback failed after attachment notify")
            logger.warning(
                "Attachment notification failed for submission %s: %s",
                submission.id,
                exc,
            )

    # ---------------------------------------------------------------------- reading

    def list_attachments(
        self, submission_id: str, line_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """The files of the header, or of ONE line. Never both.

        Same resolution as the write path, so a listing can never show a file the upload
        would have refused to put there, and a line id from another claim 404s here too.
        """
        _submission, _line, entity_type, entity_id = self._target(submission_id, line_id)
        entity_key = "line_id" if entity_type == SUBMISSION_LINE_ENTITY_TYPE else "submission_id"
        return [
            self.links.serialize_link(link, entity_key, link_type=entity_type)
            for link in self.links.list_links(entity_type, entity_id)
        ]

    def list_links(
        self, submission_id: str, line_id: Optional[str] = None
    ) -> List[EntityAttachmentLink]:
        """The raw link rows, for a caller that needs the ORM objects (unlink, export)."""
        _submission, _line, entity_type, entity_id = self._target(submission_id, line_id)
        return self.links.list_links(entity_type, entity_id)
