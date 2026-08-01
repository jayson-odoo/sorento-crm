"""A CONTACT files a workflow submission from the portal (F2b).

F1/F1a/F2a built the submission for somebody with a CRM login: a ``users.id`` created
it, a ``users.id`` moved it, and F2a started a clock when it was created. This module
opens the same document to a contact arriving on the existing portal token, and it owns
two things that must not be spread out:

**The gate, beside the code that acts on the answer.** A definition is internal until
somebody opens it (``portal_submittable``, default closed) and may then be narrowed to
particular party kinds (``portal_party_kinds``, empty meaning no narrowing). The rule
that decides "may this contact file this form" lives next to the create that writes
their answer, so the two cannot drift.

**One creation path.** Everything here goes through
``WorkflowFormsService.create_submission`` rather than building a row directly, the way
``PortalService._instantiate`` does for the four bespoke forms. That constructor works
over flat-column models plus a setattr allow-list; a submission has JSONB answers
validated against a PUBLISHED version, a ``version_id`` and a status resolved from the
engine. Routing through it would mean skipping F0 validation and the publish gate, or
duplicating ``create_submission`` - and the submissions that skipped validation would be
precisely the ones nobody at Sorento typed. Going through it instead buys the F0
answer contract, the publish gate, the version pin and F2a's ``submission_created`` emit
for free.

Two invariants the tests pin, and the reasons they are pinned:

* ``respond_inbox_url`` is written in the creating INSERT and is unwritable from a
  contact payload. It is built by ``PortalService._build_respond_inbox_url``, reused
  verbatim: ``PortalToken.contact_id`` holds the INTERNAL ``respond_contacts.id`` while
  the inbox path needs ``respond_io_id``, both are text, and piping one into the other
  type-checks, persists, and yields a permanently dead link.
* The token IS the authorization. Every read and write is scoped by
  ``token.contact_id``, so one customer's claim is never protected by nothing more than
  the unguessability of its id - which is the bespoke-token design AC-F2b-5 refuses.

See documentation/plans/forms-platform/forms-platform-acceptance-criteria.md, group F2b
and the "F2b corrections" section.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.access import respond_contact_access_types
from app.models.portal import PortalToken
from app.models.workflow_forms import WorkflowFormDefinition, WorkflowSubmission
from app.services.error_handler import AppException
from app.services.status_service import initial_status
from app.services.workflow_forms_service import WorkflowFormsService
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
)

# One code for every refusal of the gate, whether the door is shut or the narrowing
# excludes this contact. Deliberately not two: telling a contact WHICH of the two
# refused them reports whether a form they may not file exists.
NOT_SUBMITTABLE_CODE = "portal_not_submittable"


def _party_kinds(definition: WorkflowFormDefinition) -> Set[str]:
    """The party kinds a definition narrows to, normalised, or an empty set.

    Normalised here as well as on save, because the column predates nothing: rows can be
    written by a migration, a fixture or a future importer, and a stray "Dealer" would
    narrow a form to nobody while reading correctly in the builder.
    """
    raw = getattr(definition, "portal_party_kinds", None) or []
    if not isinstance(raw, (list, tuple, set)):
        # JSONB accepts any document, so a hand-edited row can hold a string or an
        # object. Anything that is not a list narrows to nothing rather than being
        # iterated character by character, which would compare against single letters.
        return set()
    return {str(kind).strip().lower() for kind in raw if str(kind).strip()}


class WorkflowSubmissionPortalService:
    """The contact-scoped surface over workflow submissions.

    Its own service, never a flag on the user-scoped one: the internal path takes a
    ``users.id`` a contact does not have, and a shared entry point is how a create that
    forgot to apply the gate ends up reachable from the portal.
    """

    def __init__(self, db: Session):
        self.db = db
        self.forms = WorkflowFormsService(db)

    # ------------------------------------------------------------------ the gate

    def _contact_id(self, token: PortalToken) -> str:
        """The INTERNAL ``respond_contacts.id`` the token is scoped to.

        Not the Respond.io id, whatever the column name suggests elsewhere. Everything
        in this module compares against, filters on and stores this value; only the
        inbox URL resolves past it.
        """
        contact_id = str(getattr(token, "contact_id", "") or "").strip()
        if not contact_id:
            # A verified token always carries one (the column is NOT NULL), so this is a
            # corrupted credential rather than a missing feature. Refuse rather than
            # scope a query to the empty string, which would match nothing today and
            # every orphaned row the day somebody writes one.
            raise AppException(
                status_code=401,
                message="This portal link is not linked to a contact.",
                code="portal_token_invalid",
            )
        return contact_id

    def _contact_party_kinds(self, token: PortalToken) -> Set[str]:
        """The access-type codes assigned to this contact.

        Read straight off the association table rather than through the relationship:
        the gate needs the codes and nothing else, and the contact row itself may not be
        loaded on the write path at all.

        Commonly EMPTY. ``contact_access_types`` is admin-curated and most Respond.io
        synced contacts carry none, which is why a definition that declares kinds is
        correctly closed to them (AC-F2b-7) and why the default narrowing is no
        narrowing at all.
        """
        rows = self.db.execute(
            respond_contact_access_types.select().where(
                respond_contact_access_types.c.contact_id == self._contact_id(token)
            )
        ).fetchall()
        return {
            str(row.access_type_code).strip().lower()
            for row in rows
            if str(row.access_type_code or "").strip()
        }

    def _is_submittable(
        self, definition: WorkflowFormDefinition, contact_kinds: Set[str]
    ) -> bool:
        """Two columns, one meaning each.

        ``portal_submittable`` is the door and it is closed by default;
        ``portal_party_kinds`` narrows who may walk through it, where empty means no
        narrowing. The match is a set OVERLAP, not an equality: a ``PortalToken`` carries
        a contact id and a space id, so the only classification reachable for the asker
        is the many-to-many one, and a contact can hold several codes at once.
        """
        if not bool(getattr(definition, "portal_submittable", False)):
            return False
        wanted = _party_kinds(definition)
        if not wanted:
            return True
        return bool(wanted & contact_kinds)

    def _assert_submittable(
        self, token: PortalToken, definition: WorkflowFormDefinition
    ) -> None:
        """Refuse BEFORE anything is written.

        Order matters as much as the rule: a stage configured to start on
        ``submission_created`` would otherwise leave a live tracker pointing at a row the
        portal then refused to keep.
        """
        if self._is_submittable(definition, self._contact_party_kinds(token)):
            return
        raise AppException(
            status_code=403,
            message="This form cannot be submitted from the portal.",
            code=NOT_SUBMITTABLE_CODE,
        )

    # ------------------------------------------------------------------ reading

    def list_definitions(self, token: PortalToken) -> List[Dict[str, Any]]:
        """The forms this contact may file, for the portal's picker.

        The listing applies the SAME gate as the create, because the picker is its own
        exposure: refusing at submit still tells a customer the name of every internal
        form if the list names them.

        Active and published only, matching the internal runtime picker: an unpublished
        definition has no version to answer against, so offering it would be an error
        the contact could only discover by trying.
        """
        contact_kinds = self._contact_party_kinds(token)
        rows = (
            self.db.query(WorkflowFormDefinition)
            .filter(
                WorkflowFormDefinition.is_active.is_(True),
                WorkflowFormDefinition.published_version_id.isnot(None),
                WorkflowFormDefinition.portal_submittable.is_(True),
            )
            .order_by(WorkflowFormDefinition.name)
            .all()
        )
        return [
            {"id": d.id, "code": d.code, "name": d.name, "description": d.description}
            for d in rows
            if self._is_submittable(d, contact_kinds)
        ]

    def get_definition_schema(
        self, token: PortalToken, definition_id: str
    ) -> Dict[str, Any]:
        """The PUBLISHED document of one form this contact may file.

        Behind the same gate as the create, not merely behind a valid token: a
        definition's document names its fields, its lookups and its conditions, so
        handing it out for an internal form leaks the form's design to a customer who
        may not file it.

        Always the published snapshot. The draft is what somebody is halfway through
        editing, and a contact answering it would be answering a document no version
        pins.
        """
        definition = self.forms.get_definition(str(definition_id))
        self._assert_submittable(token, definition)
        schema, _source = self.forms.preview(str(definition.id), source="published")
        return {
            "id": definition.id,
            "code": definition.code,
            "name": definition.name,
            "description": definition.description,
            "schema": schema,
        }

    def _owned(self, token: PortalToken, submission_id: str) -> WorkflowSubmission:
        """One submission, or 404 - including for a submission somebody else filed.

        Scoped by ``respondent_contact_id`` in the QUERY rather than checked after the
        read, so another contact's row is never loaded, never partially serialized and
        never distinguishable from one that does not exist.
        """
        row = (
            self.db.query(WorkflowSubmission)
            .filter(
                WorkflowSubmission.id == str(submission_id),
                WorkflowSubmission.respondent_contact_id == self._contact_id(token),
            )
            .first()
        )
        if row is None:
            raise AppException(
                status_code=404, message="Submission not found.", code="not_found"
            )
        return row

    def get_submission(self, token: PortalToken, submission_id: str) -> Dict[str, Any]:
        """One of the contact's own submissions, serialized the way the CRM serializes it.

        Through ``_submission_out`` so the portal and the admin detail page cannot
        disagree about what a submission holds. The form schema travels with it because
        the portal has to render the document it is showing answers for.
        """
        row = self._owned(token, submission_id)
        return self.forms._submission_out(
            row, include_logs=False, include_form_schema=True
        )

    def list_submissions(
        self, token: PortalToken, definition_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Everything THIS contact filed, newest first.

        Scoped by contact, never by definition alone: a listing keyed to the form would
        show every customer the whole queue. ``definition_id`` only narrows within what
        the contact already owns.
        """
        q = self.db.query(WorkflowSubmission).filter(
            WorkflowSubmission.respondent_contact_id == self._contact_id(token)
        )
        if definition_id:
            q = q.filter(WorkflowSubmission.definition_id == str(definition_id))
        rows = q.order_by(WorkflowSubmission.created_at.desc()).all()
        return [
            self.forms._submission_out(row, include_logs=False, include_form_schema=False)
            for row in rows
        ]

    # ------------------------------------------------------------------ writing

    def create_submission(
        self,
        token: PortalToken,
        definition_id: str,
        header_data: Dict[str, Any],
        lines: Optional[List[Dict[str, Any]]] = None,
        *,
        source_entity_type: Optional[str] = None,
        source_entity_id: Optional[str] = None,
    ) -> WorkflowSubmission:
        """File a form as the token's contact.

        The gate first, then the ordinary creation path. ``created_by_user_id`` stays
        NULL: nobody logged in, and stamping a service account there would put a real
        person's name on every customer's filing, in the audit trail and on the detail
        page (AC-F1a-29).

        The inbox URL is resolved here and passed down, so it is present in the creating
        INSERT. ``PortalService._build_respond_inbox_url`` is reused rather than
        reimplemented: it already resolves the contact's ``respond_io_id`` and already
        returns None when there is none, which is the whole of AC-F2b-4. No link is
        honest; a link built from the internal contact id is a well-formed dead one.
        """
        definition = self.forms.get_definition(str(definition_id))
        self._assert_submittable(token, definition)
        return self.forms.create_submission(
            str(definition.id),
            header_data or {},
            list(lines or []),
            None,
            respondent_contact_id=self._contact_id(token),
            source_entity_type=(source_entity_type or "").strip() or None,
            source_entity_id=(source_entity_id or "").strip() or None,
            respond_inbox_url=self._inbox_url(token),
        )

    def _inbox_url(self, token: PortalToken) -> Optional[str]:
        """The admin's chat link for this contact, or None.

        Local import: ``portal_service`` imports most of the form services, so a
        module-level import here closes a cycle.
        """
        from app.services.portal_service import PortalService

        return PortalService(self.db)._build_respond_inbox_url(
            getattr(token, "contact_id", None), getattr(token, "space_id", None)
        )

    def update_submission(
        self,
        token: PortalToken,
        submission_id: str,
        header_data: Optional[Dict[str, Any]] = None,
        lines: Optional[List[Dict[str, Any]]] = None,
    ) -> WorkflowSubmission:
        """Edit one of the contact's own submissions, while it is still theirs to edit.

        A contact may edit only while the submission sits on its definition's INITIAL
        rung. No new column records that: once anyone at Sorento has moved it, the
        answers are what a decision was taken against, and letting the customer rewrite
        them afterwards changes the record under the decision.

        Nothing from the payload reaches a COLUMN. ``header_data`` is validated against
        the frozen schema and stored as answers, which drops unknown keys - so a payload
        naming ``respond_inbox_url`` can neither blank the admin's chat link nor park an
        admin-only URL inside the document the contact can read back.
        """
        row = self._owned(token, submission_id)
        self._assert_editable(row)
        return self.forms.update_submission(
            str(row.id), header_data, lines, None
        )

    # -------------------------------------------------------------- evidence (F2c)

    def upload_attachment(
        self,
        token: PortalToken,
        submission_id: str,
        *,
        contents: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        line_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attach one file to the contact's own submission, or to one of its lines.

        ``_owned`` first: without it the only thing protecting one customer's claim from
        another's is the unguessability of its id, and an upload is a WRITE onto somebody
        else's record.

        Attribution is passed as a CONTACT, never as a user. ``uploaded_by`` used to be
        the only attribution column, so a portal upload's NULL meant both "a contact sent
        it" and "we do not know" - and stamping a service account instead would put a
        staff member's name on a customer's photo in the Files page.

        A contact may upload after the submission locks. Editing the ANSWERS after a
        decision was taken against them rewrites the record under the decision; sending
        the photo the adjudicator just asked for is the opposite, and refusing it is how
        a case stalls.
        """
        submission = self._owned(token, submission_id)
        return self._attachments().upload(
            submission_id=str(submission.id),
            line_id=line_id,
            contents=contents,
            filename=filename,
            content_type=content_type,
            uploaded_by_contact_id=self._contact_id(token),
        )

    def list_attachments(
        self,
        token: PortalToken,
        submission_id: str,
        line_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """The files on the contact's own submission, or on one of its lines.

        Reading is the leak that matters here: a warranty claim's photos are the
        customer's own property damage. Scoped through ``_owned``, so another contact's
        submission is never loaded and never distinguishable from one that does not
        exist.
        """
        submission = self._owned(token, submission_id)
        return self._attachments().list_attachments(str(submission.id), line_id=line_id)

    def _attachments(self):
        """The one service that owns the link scopes, the key and the cap.

        Local import: the attachments service reaches the notification stack, and the
        portal is imported from it indirectly through the form services.
        """
        from app.services.workflow_submission_attachments import (
            WorkflowSubmissionAttachmentService,
        )

        return WorkflowSubmissionAttachmentService(self.db)

    def _assert_editable(self, submission: WorkflowSubmission) -> None:
        start = initial_status(
            self.db,
            WORKFLOW_SUBMISSION_ENTITY_TYPE,
            str(submission.definition_id),
        )
        if str(submission.status_id) == str(start.id):
            return
        raise AppException(
            status_code=403,
            message=(
                "This submission is already being handled and can no longer be edited "
                "here."
            ),
            code="portal_submission_locked",
        )
