"""Make one CRM contact known to Respond.io (DEALER-ACCESS-PORTAL B2, DEALER-ACCESS-NAMES N5.1-N5.3).

The ONE shared function: the worker task `respond_io_tasks.ensure_respond_contact` (the agent's grant enqueues it)
and the Dealer access screen (inside the request, after a grant commits, and its "Try again") both call
`ensure_in_respond`. Looks the phone up (normalised to +601..., the form the sync sends); a 404 creates the contact
there (phone and first name, no message is ever sent). Stores the Respond.io id (and the name parts the CRM row
lacks), then writes the `backend_id` custom field the sync writes. A contact that already has its id (a retry) only
gets `backend_id`. No usable phone or no resolvable API key (dev, CI): returns without any HTTP call.

Every Respond.io call writes one `integration_logs` row (success or failed, both terminal: the webhook retry sweep
replays only pending/processing rows) through `integration_service.log_respond_send`.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

OK_STATUSES = frozenset({"found", "created", "backend_id"})
BUSINESS_TABLE = "respond_contacts"

NO_CONTACT = "This contact no longer exists."
NO_PHONE = "The phone is not a Malaysian mobile number."
NO_KEY = "Respond.io is not set up."
DUPLICATE = "Another contact in the CRM already is this person in Respond.io."
NO_ID = "Respond.io gave no contact id back."


def plain_error(exc: BaseException) -> str:
    """What went wrong, in words a salesperson reads (never the exception's own text, host or class)."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else None
        if code in (401, 403):
            return "Respond.io refused the key it was given."
        if code == 429:
            return "Respond.io is busy; try again in a minute."
        return f"Respond.io answered with an error ({code})." if code else "Respond.io answered with an error."
    if isinstance(exc, httpx.TimeoutException):
        return "Respond.io did not answer in time."
    if isinstance(exc, httpx.RequestError):
        return "Respond.io could not be reached."
    if isinstance(exc, ValueError):
        return NO_KEY
    if isinstance(exc, RuntimeError) and str(exc) == NO_ID:
        return NO_ID
    return "Respond.io gave an unexpected answer."


def _log(db: Session, contact_id: str, identifier: str, method: str, endpoint: str, payload: dict, **kw) -> None:
    from app.services.integration_service import log_respond_send

    log_respond_send(
        db, business_table=BUSINESS_TABLE, business_id=str(contact_id), identifier=identifier,
        request_payload=payload, endpoint=endpoint, http_method=method, **kw,
    )


def ensure_in_respond(db: Session, contact_id: str, *, raise_errors: bool = False) -> dict:
    """`{status, error, respond_io_id}`. `status` is `found` / `created` / `backend_id` (in Respond.io, `error`
    None), a `skipped_*` reason, or `failed`. A failed HTTP call is logged, then returned as `failed` with a plain
    `error`, or re-raised with `raise_errors` (the worker, so RQ retries)."""
    import httpx

    from app.models.access import RespondContact
    from app.models.base import company_scope
    from app.services.contact_service import parse_respond_contact_payload
    from app.services.contact_setup_engine import normalise_phone
    from app.services.integration_service import RespondClient
    from app.services.respond_sync_handler import _internal_contact_url

    def out(status: str, error: str | None = None, respond_io_id: str | None = None) -> dict:
        return {"status": status, "error": error, "respond_io_id": respond_io_id}

    with company_scope(db, None):
        contact = db.query(RespondContact).filter(RespondContact.id == str(contact_id)).first()
        if contact is None:
            return out("skipped_no_contact", NO_CONTACT)
        phone = normalise_phone(contact.phone_number)
        if phone is None:
            logger.warning("ensure_in_respond: contact %s has no Malaysian mobile number; left as is", contact_id)
            return out("skipped_no_phone", NO_PHONE)
        try:
            client = RespondClient.for_contact_id(db, str(contact.id))
        except ValueError:
            client = None
        if client is None or not client.api_key:
            logger.info("ensure_in_respond: no Respond.io API key; contact %s left to the sync", contact_id)
            return out("skipped_no_key", NO_KEY)

        respond_id = contact.respond_io_id
        status = "backend_id"
        by_phone = f"{client.base_url}/v2/contact/phone:{phone}"
        step = ("GET", by_phone, {"phone": phone})
        try:
            if not respond_id:
                try:
                    payload = client.get_contact_by_phone(phone)
                    _log(db, contact_id, phone, *step, response=payload)
                    status = "found"
                except httpx.HTTPStatusError as exc:
                    if exc.response is None or exc.response.status_code != 404:
                        raise
                    _log(db, contact_id, phone, *step, exc=exc)  # the 404 that leads to the create
                    step = ("POST", by_phone, {"phone": phone, "firstName": contact.first_name or contact.name or None})
                    payload = client.create_contact(phone, contact.first_name or contact.name or None)
                    _log(db, contact_id, phone, *step, response=payload)
                    status = "created"
                parsed = parse_respond_contact_payload(payload or {})
                respond_id = parsed.get("respond_io_id")
                if not respond_id:
                    raise RuntimeError(NO_ID)
                holder = db.query(RespondContact.id).filter(
                    RespondContact.respond_io_id == respond_id, RespondContact.id != contact.id
                ).first()
                if holder is not None:
                    # Another CRM row already is this Respond.io contact: a duplicate for the office, never overwritten.
                    logger.warning(
                        "ensure_in_respond: Respond.io id %s already belongs to contact %s; %s left as is",
                        respond_id, holder[0], contact_id,
                    )
                    return out("skipped_duplicate", DUPLICATE)
                contact.respond_io_id = respond_id
                for key in ("first_name", "last_name"):
                    if not getattr(contact, key) and parsed.get(key):
                        setattr(contact, key, parsed[key])
                db.commit()
            body = {"custom_fields": [{"name": "backend_id", "value": _internal_contact_url(str(contact_id))}]}
            step = ("PUT", f"{client.base_url}/v2/contact/id:{respond_id}", body)
            response = client.update_contact(f"id:{respond_id}", body)
            _log(db, contact_id, str(respond_id), *step, response=response)
        except Exception as exc:  # noqa: BLE001 - logged, then reported (screen) or re-raised (worker)
            logger.warning("ensure_in_respond: %s %s failed for contact %s", step[0], step[1], contact_id)
            db.rollback()
            _log(db, contact_id, str(respond_id or phone), *step, exc=exc)
            if raise_errors:
                raise
            return out("failed", plain_error(exc), respond_id)
    return out(status, None, str(respond_id))
