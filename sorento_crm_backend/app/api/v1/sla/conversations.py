"""The Conversations inbox: contact-keyed reads and one contact-keyed send.

UAC AC-N1 / AC-N2 / AC-N3 / AC-N4, PLAN slice S4.9.

Everything under here is keyed by a CONTACT, not by a ticket, and gated by a
PERMISSION, not by ticket assignment. That separation is the whole slice: today
a thread is readable only by whoever can act on the ticket, so a reassigned-away
previous assignee, a mentioned colleague and a manager are all locked out of a
conversation they have a legitimate reason to read.

- read  -> ``sla_management.conversations.view``
- reply -> ``sla_management.conversations.reply``

The ticket-keyed twins under ``/conversation-sla-tracking/{tracking_id}/...``
stay exactly as they are (assignee-or-manager) and serve the drawer. Both sides
call the SAME service cores, so the response shapes cannot drift.

``contact_ref`` is a Respond.io contact id, a ``respond_contacts.id`` or a phone
number - whatever the caller happens to hold. It resolves through the same
helper the rest of the SLA service uses.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.ticket_comment import TicketCommentCreate, TicketCommentResponse
from app.services.conversation_inbox_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    TAB_ALL,
    list_conversations,
)
from app.services.error_handler import handle_internal_error
from app.services.sla_service import ConversationSLATrackingService
from app.services.ticket_comment_service import TicketCommentService

router = APIRouter()

VIEW = "sla_management.conversations.view"
REPLY = "sla_management.conversations.reply"


@router.get("")
@router.get("/")
async def list_inbox_conversations(
    tab: str = Query(TAB_ALL, description="mine | mentioned | unassigned | all"),
    q: Optional[str] = Query(None, description="Contact name or phone fragment"),
    cursor: Optional[str] = Query(None, description="Opaque keyset cursor from next_cursor"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """One keyset page of the inbox list (AC-N1).

    Server-paginated, newest conversation first, never a thread fetch. See
    ``conversation_inbox_service`` for why the cursor is a pair and why the
    Mentioned tab sorts on a different clock.
    """
    from starlette.concurrency import run_in_threadpool

    try:
        return await run_in_threadpool(
            lambda: list_conversations(
                db,
                viewer_user_id=current_user["id"],
                tab=tab,
                q=q,
                cursor=cursor,
                limit=limit,
            )
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))


@router.get("/{contact_ref}/page")
async def get_contact_thread_page(
    contact_ref: str,
    before: Optional[str] = Query(None, description="Message id to page OLDER than (exclusive)"),
    after: Optional[str] = Query(None, description="Message id to page NEWER than (exclusive)"),
    around: Optional[str] = Query(
        None, description="Message id to centre the window on (jump to a search match)"
    ),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """One scroll-back window of a contact's thread (AC-N3).

    Byte-identical response shape to
    ``GET .../conversation-sla-tracking/{tracking_id}/conversation/page`` - the
    same service core answers both.
    """
    from starlette.concurrency import run_in_threadpool

    cursors = [c for c in (before, after, around) if c]
    if len(cursors) > 1:
        raise HTTPException(status_code=422, detail="Pass at most one of before, after, around.")

    try:
        service = ConversationSLATrackingService(db)
        return await run_in_threadpool(
            lambda: service.fetch_contact_thread_page(
                contact_ref, before=before, after=after, around=around, limit=limit
            )
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))


@router.get("/{contact_ref}/search")
async def search_contact_thread(
    contact_ref: str,
    q: str = Query("", description="Free text searched inside this contact's messages"),
    limit: int = Query(100, ge=1, le=200),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """In-thread message search for a contact (AC-N3), same shape as the
    ticket-keyed twin."""
    from starlette.concurrency import run_in_threadpool

    try:
        service = ConversationSLATrackingService(db)
        return await run_in_threadpool(
            lambda: service.search_contact_thread(contact_ref, q=q, limit=limit)
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))


@router.get("/{contact_ref}/comments")
async def list_contact_comments(
    contact_ref: str,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Every internal note on this contact, oldest first (AC-N3).

    Both scopes render: the contact-scoped notes ingested from Respond's own
    inbox AND the ticket-scoped notes written in a drawer. A note is internal
    staff context, not ticket-private, and the inbox thread is not looking at
    one ticket.
    """
    return TicketCommentService(db).list_for_contact(contact_ref)


@router.post(
    "/{contact_ref}/comments",
    response_model=TicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contact_comment(
    contact_ref: str,
    payload: TicketCommentCreate,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Write an internal note on this CONTACT (AC-N3).

    The view permission is the gate, not a ticket assignment: a note is
    internal staff context, and the inbox thread is not looking at one ticket.
    Anyone who may read the conversation may annotate it.

    NEVER reaches the contact - this path touches no Respond send route. The
    only outbound call is the AC-L2 comment mirror, post-commit and
    best-effort. Mentioned users get an in-app notification deep-linking back
    to this conversation.
    """
    return TicketCommentService(db).create_for_contact(
        contact_ref,
        author_user_id=current_user["id"],
        body=payload.body,
        mentioned_user_ids=payload.mentioned_user_ids,
    )


@router.get("/{contact_ref}/media")
async def proxy_contact_media(
    contact_ref: str,
    url: str = Query(..., description="Attachment URL on an allowlisted host"),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Viewer-scoped byte proxy for a thread attachment (AC-N4).

    Storage and Respond media hosts send no CORS headers, so an inline
    spreadsheet/csv preview cannot fetch them from the browser. The host
    allowlist is what keeps this from being an open URL fetcher.
    """
    from app.services import media_proxy_service

    ConversationSLATrackingService(db).require_contact(contact_ref)
    return await media_proxy_service.stream(url)


@router.post("/{contact_ref}/reply")
async def reply_to_contact(
    contact_ref: str,
    request: Request,
    current_user: dict = Depends(require_permission(REPLY)),
    db: Session = Depends(get_db),
):
    """Send a WhatsApp reply to a contact from the inbox (AC-N2).

    Stamped onto the sender's OWN open ticket for this contact when they hold
    exactly one - that is the only case where "which enquiry does this answer"
    has an unambiguous answer. Otherwise it is an unstamped human send: the
    contact still gets the message, the Respond outbox is still written, and the
    AC-J human-intervention signal still fires so the bot stands down.

    Accepts JSON (``{text, reply_to_message_id?, reply_to_excerpt?}``) or
    ``multipart/form-data`` (``text``, ``reply_to_message_id``,
    ``reply_to_excerpt``, ``files[]``), exactly like the ticket drawer's send.
    ``text`` is expected to already carry the composer's ">"-quote prefix when
    replying to a message and is sent verbatim; the ``reply_to_*`` fields are
    audit-only and never reach Respond (it has no reply-to parameter).
    """
    from starlette.concurrency import run_in_threadpool

    content_type = (request.headers.get("content-type") or "").lower()
    files: list[tuple[bytes, str, str]] = []
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        text = str(form.get("text") or "")
        reply_to_message_id = str(form.get("reply_to_message_id") or "") or None
        reply_to_excerpt = str(form.get("reply_to_excerpt") or "") or None
        for item in form.getlist("files"):
            # StarletteUploadFile, NOT fastapi.UploadFile: request.form() yields
            # the starlette class and the FastAPI one is a strict subclass, so an
            # isinstance check against FastAPI's never matches and every
            # attachment silently degrades to a text-only send.
            if isinstance(item, StarletteUploadFile) and item.filename:
                files.append((await item.read(), item.filename, item.content_type or ""))
    else:
        try:
            raw = await request.json()
        except Exception:  # noqa: BLE001
            raw = {}
        text = str((raw or {}).get("text") or "")
        reply_to_message_id = (raw or {}).get("reply_to_message_id")
        reply_to_excerpt = (raw or {}).get("reply_to_excerpt")

    sender_name = (current_user.get("name") or "").strip() or "Customer Service"
    service = ConversationSLATrackingService(db)
    return await run_in_threadpool(
        service.send_contact_message,
        contact_ref,
        text=text,
        files=files,
        reply_to_message_id=reply_to_message_id,
        reply_to_excerpt=reply_to_excerpt,
        sender_user_id=current_user.get("id"),
        sender_name=sender_name,
    )
