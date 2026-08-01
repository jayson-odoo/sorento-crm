"""Who gets told about a workflow submission, and how (F2c).

Its own module, separate from the one that owns bytes and links, because a CONTACT and
a USER are reached by completely different machinery and folding the two together is how
"the upload failed because the customer's WhatsApp window is shut" becomes possible.

**The hole this closes.** ``_notify_submitter`` reads ``created_by_user_id``, which F2b
makes NULL for every portal filing, so it returns early. A customer's claim could be
approved or rejected and the only person told was nobody: the one origin with a real
person waiting for the answer was the one origin that got no message, and it failed
silently in both directions (AC-F2c-8).

**A contact is addressed by NOT writing a ``notifications`` row.** ``user_id`` is NOT
NULL, so there is no "no user" notification; and it carries NO foreign key, so a
``respond_contacts.id`` inserts cleanly, type-checks at every layer and produces a row
addressed to a principal who will never log in, that no query will ever surface. The
contact path therefore resolves ``respondent_contact_id`` to the contact's
``respond_io_id`` and sends (AC-F2c-12). ``PortalToken.contact_id`` and the internal
``respond_contacts.id`` are both text, so piping one into the send identifier would not
raise either: Respond.io would simply be handed an id it does not know.

**Every send writes an outbox row, on success AND on failure.** Local development runs
with deliberately wrong credentials, so the FAILURE path is the one a developer actually
exercises: a 401 that logs nothing makes the Respond outbox look healthy precisely when
nothing is being delivered. ``integration_log.business_id`` is a ``uuid`` COLUMN, so it
is one row's primary key and never a composite string; for a contact send there IS no
notification row to point at, so it is the submission (AC-F2c-9).

**Everything here is a post-commit side effect and nothing here raises.** The status has
moved, the file is stored. A notification that raises hands the caller a 500 for an
operation that succeeded, and the retry then takes an idempotent path that never
backfills the missed message (AC-F2c-6). Both public functions swallow, log and return.

See documentation/plans/forms-platform/forms-platform-acceptance-criteria.md, group F2c
and the "F2c corrections" section.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.integration import IntegrationLog
from app.models.sla import ConversationSLATracking
from app.models.workflow_forms import WorkflowFormDefinition, WorkflowSubmission
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
)

logger = logging.getLogger(__name__)

# The Respond.io template use case a submission's contact messages resolve against. Its
# own name, so an out-of-window submission message can be given its own template without
# rewording the complaint one. Until a default template row exists for it, an
# out-of-window send is skipped and lands in the outbox as a failure, which is the honest
# record: nothing was delivered.
RESPOND_USE_CASE = "workflow_submission"

# The table business_id is a primary key of. Read off the model so a rename cannot leave
# the outbox pointing at a table that no longer exists.
BUSINESS_TABLE = WorkflowSubmission.__tablename__


def _definition_name(db: Session, submission: WorkflowSubmission) -> str:
    row = (
        db.query(WorkflowFormDefinition)
        .filter(WorkflowFormDefinition.id == str(submission.definition_id))
        .first()
    )
    return str(getattr(row, "name", "") or "").strip() or "Form"


# ------------------------------------------------------------------ the contact path


def notify_submission_contact(
    db: Session,
    submission: WorkflowSubmission,
    *,
    title: str,
    body: str,
    event_type: Optional[str] = None,
) -> Optional[IntegrationLog]:
    """Message the contact a submission is about. Returns its outbox row, or None.

    None means nothing was ATTEMPTED, and there are exactly two honest reasons for it: a
    staff-filed submission legitimately has no respondent, and a contact synced without a
    ``respond_io_id`` has no address. Neither is an error - this runs on every header
    move - and neither may fall back to the internal ``respond_contacts.id``, which is a
    documented recurring bug here precisely because it does not raise.

    A send that was attempted always returns a row, ``success`` or ``failed``. It never
    raises: the caller has already committed whatever the message is about.
    """
    contact_id = str(getattr(submission, "respondent_contact_id", "") or "").strip()
    if not contact_id:
        return None

    contact = (
        db.query(RespondContact).filter(RespondContact.id == contact_id).first()
    )
    identifier = str(getattr(contact, "respond_io_id", "") or "").strip()
    if not identifier:
        # Deliberately quiet at warning level rather than an exception: on a workspace
        # that files forms for walk-in customers this is the normal case.
        logger.info(
            "Submission %s has no Respond.io identifier for contact %s; nothing sent.",
            getattr(submission, "id", None),
            contact_id,
        )
        return None

    text = "\n\n".join(part for part in (str(title or "").strip(), str(body or "").strip()) if part)
    return _send_and_log(
        db,
        submission=submission,
        identifier=identifier,
        text=text,
        event_type=event_type,
    )


def _send_and_log(
    db: Session,
    *,
    submission: WorkflowSubmission,
    identifier: str,
    text: str,
    event_type: Optional[str] = None,
) -> Optional[IntegrationLog]:
    """One window-aware send plus its outbox row. Mirrors ``respond_io_tasks._send_and_log``.

    Synchronous rather than queued: the message is the answer to something a person is
    waiting on, and a queued send would need a live worker to make the outbox row appear
    at all, which is exactly the observability this is here to provide.
    """
    from app.schemas.integration import IntegrationLogCreate
    from app.services.integration_service import IntegrationLogService
    from app.services.respond_messaging_service import send_text_or_template

    business_id = str(getattr(submission, "id", "") or "")
    endpoint = f"https://api.respond.io/v2/contact/id:{identifier}/message"
    request_payload: dict = {"message": {"type": "text", "text": text}}
    log_service = IntegrationLogService(db)

    context_vars: dict = {"message": text}
    if str(event_type or "").strip():
        # Omitted rather than passed as None when there is no event: a null in the
        # context renders as the literal "None" in a template slot.
        context_vars["event_type"] = str(event_type).strip()

    try:
        result = send_text_or_template(
            db,
            identifier=identifier,
            text=text,
            use_case=RESPOND_USE_CASE,
            context_vars=context_vars,
        )
        request_payload = result.get("request_payload") or request_payload
        response = result.get("response")
        return log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table=BUSINESS_TABLE,
                business_id=business_id,
                external_reference=identifier,
                direction="outbound",
                endpoint=endpoint,
                http_method="POST",
                status="success",
                response_payload=str(response)[:50000] if response else None,
            ),
            request_payload_dict=request_payload,
        )
    except Exception as exc:  # noqa: BLE001 - a failed send is a logged send
        logger.warning(
            "Respond.io send failed for submission %s: %s", business_id, exc
        )
        # What was ACTUALLY attempted: the window-aware send stamps the real payload on
        # the exception, so a closed-window failure logs as a TEMPLATE attempt rather
        # than the default text one.
        request_payload = getattr(exc, "request_payload", request_payload)
        status_code, response_body = _response_of(exc)
        try:
            return log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table=BUSINESS_TABLE,
                    business_id=business_id,
                    external_reference=identifier,
                    direction="outbound",
                    endpoint=endpoint,
                    http_method="POST",
                    status="failed",
                    status_code=status_code,
                    response_payload=response_body,
                    error_message=str(exc) or exc.__class__.__name__,
                ),
                request_payload_dict=request_payload,
            )
        except Exception as log_exc:  # noqa: BLE001
            # The outbox write itself failed. Roll back so the caller's next read does
            # not raise PendingRollbackError from inside a side effect it did not ask
            # for, and leave the trail in the application log instead.
            _rollback(db)
            logger.warning(
                "Respond outbox write failed for submission %s: %s",
                business_id,
                log_exc,
            )
            return None


def _response_of(exc: Exception) -> tuple[Optional[int], Optional[str]]:
    """Respond.io's own status + body when the exception carries one.

    A bare "403 Forbidden for url ..." cannot be diagnosed (WAF block, closed window and
    channel error all read alike), so the real body is worth the two defensive reads.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None, None
    try:
        status_code = int(response.status_code)
    except Exception:  # noqa: BLE001
        status_code = None
    try:
        body = (response.text or "")[:50000]
    except Exception:  # noqa: BLE001
        body = None
    return status_code, body


def _rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 - nothing left to salvage
        logger.warning("Rollback failed inside a submission notification")


def notify_submission_status_change(
    db: Session,
    submission: WorkflowSubmission,
    *,
    transition_label: Optional[str] = None,
    event_type: Optional[str] = None,
) -> Optional[IntegrationLog]:
    """Tell the submission's contact that it moved. The message is composed here.

    Beside the send rather than at the call site, so the staff notification and the
    customer's message cannot drift into describing the same move differently.
    """
    name = _definition_name(db, submission)
    status_label = str(getattr(submission, "status_label", "") or "").strip()
    title = f"{name}: {transition_label or 'Updated'}"
    body = (
        f'Your submission is now "{status_label}".'
        if status_label
        else "Your submission has been updated."
    )
    return notify_submission_contact(
        db, submission, title=title, body=body, event_type=event_type
    )


# -------------------------------------------------------------------- the staff path


def notify_attachment_added(
    db: Session,
    submission: WorkflowSubmission,
    *,
    attachment: Any,
    line: Any = None,
) -> None:
    """Tell whoever is handling a submission that a file arrived on it.

    The recipient is the ACTIVE form-SLA tracker's assignee, because that is the only
    definition of "who is handling this" the platform has (AC-F2c-15). A customer
    uploading the photo the adjudicator asked for is the event that unblocks the case,
    and nothing else surfaces it: the file lands on a detail page nobody has a reason to
    reopen.

    No tracker means NO recipient, and that is a silent no-op rather than an exception.
    It is the day-one state, not a fault: F2a's seed deliberately creates no teams (a
    migration cannot invent members), so ``_start_for_config`` raises, ``emit_event``
    swallows it, and nothing is assigned until ops configures the tier teams.

    Every active stage's assignee is told, de-duplicated, because a submission can carry
    more than one clock and the evidence is equally new to each of them.
    """
    submission_id = str(getattr(submission, "id", "") or "")
    if not submission_id:
        return

    recipients = _active_assignees(db, submission_id)
    if not recipients:
        return

    from app.services.form_sla_service import _form_detail_link
    from app.services.notification_service import NotificationService

    name = _definition_name(db, submission)
    filename = str(getattr(attachment, "original_filename", "") or "file")
    attachment_id = str(getattr(attachment, "id", "") or "")
    link = _form_detail_link(WORKFLOW_SUBMISSION_ENTITY_TYPE, submission_id)
    where = (
        f"line {int(getattr(line, 'sort_order', 0) or 0) + 1}"
        if line is not None
        else "the submission"
    )
    title = f"New file on {name}"
    body = f'"{filename}" was added to {where}.'

    for user_id in recipients:
        NotificationService(db).create_with_channel_preferences(
            user_id=user_id,
            type="workflow_forms.attachment",
            title=title,
            body=body,
            data={
                "submission_id": submission_id,
                "definition_id": str(getattr(submission, "definition_id", "") or ""),
                "attachment_id": attachment_id,
                "link": link,
            },
            source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
            source_entity_id=submission_id,
            # One notification per file per recipient: an upload retried after a
            # timeout must not arrive twice.
            event_type=f"workflow_forms.attachment.{attachment_id}",
            send_in_app=True,
            send_email=True,
            send_web_push=False,
            # No WhatsApp: there is no template for "a file arrived", and a per-file
            # template send is a per-file cost. In-app is the queue, email is the nudge.
            send_whatsapp=False,
            # The recipient IS an SLA assignee, so their assignment opt-in is the toggle
            # that governs mail about the thing they were assigned.
            email_pref_attr="notify_email_on_assignment",
        )


def _active_assignees(db: Session, submission_id: str) -> list[str]:
    """Distinct users with an unresolved form-SLA clock on this submission.

    Scoped to ``source_entity_type = 'workflow_submission'``, which is what keeps this
    off the conversation-SLA rows that share the table: a contact-keyed query with no
    type predicate matches whatever else that contact has open.
    """
    rows = (
        db.query(ConversationSLATracking.assigned_to_id)
        .filter(
            ConversationSLATracking.source_entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE,
            ConversationSLATracking.source_entity_id == str(submission_id),
            ConversationSLATracking.is_resolved.is_(False),
            ConversationSLATracking.assigned_to_id.isnot(None),
        )
        .all()
    )
    seen: list[str] = []
    for (assignee,) in rows:
        value = str(assignee or "").strip()
        if value and value not in seen:
            seen.append(value)
    return seen
