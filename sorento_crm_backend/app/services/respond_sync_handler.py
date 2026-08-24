"""Respond.io contact sync: list contacts missing backend_id, upsert local, set custom field.

Also runs a second pass over local rows missing first_name/last_name/respond_io_id so that
contacts whose Respond.io row already has backend_id (and therefore is excluded from the list
filter) still get their canonical fields filled in.
"""
import logging
from typing import Any

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.access import RespondContact
from app.models.scheduled_task import ScheduledTask
from app.schemas.integration import IntegrationLogCreate
from app.schemas.user import RespondContactCreate
from app.services.contact_service import ContactService, parse_respond_contact_payload
from app.services.integration_service import RespondClient, IntegrationLogService

logger = logging.getLogger(__name__)

# Request body for Respond.io POST /v2/contact/list: contacts where custom field backend_id does not exist
LIST_CONTACTS_BODY_MISSING_BACKEND_ID = {
    "search": "",
    "filter": {
        "$and": [
            {
                "category": "contactField",
                "field": "backend_id",
                "operator": "doesNotExist",
                "value": "",
            }
        ]
    },
    "timezone": "Asia/Kuala_Lumpur",
}


def _phone_from_contact(contact: dict) -> str | None:
    """Extract phone number from Respond contact payload."""
    phone = (
        contact.get("phone")
        or contact.get("phoneNumber")
        or (contact.get("channel", {}) or {}).get("phone")
    )
    if not phone:
        return None
    if isinstance(phone, str) and phone.startswith("phone:"):
        return phone.replace("phone:", "").strip()
    return str(phone).strip()


def _name_from_contact(contact: dict) -> str | None:
    """Extract display name from Respond contact payload."""
    name = (
        contact.get("name")
        or contact.get("displayName")
        or contact.get("data", {}).get("name")
        or contact.get("contact", {}).get("name")
    )
    if name:
        return str(name).strip()
    first = contact.get("firstName") or contact.get("first_name") or ""
    last = contact.get("lastName") or contact.get("last_name") or ""
    if first or last:
        return f"{first} {last}".strip()
    return None


def _first_last_from_contact(contact: dict) -> tuple[str | None, str | None]:
    """Extract first/last name fields from Respond contact payload."""
    fn = contact.get("firstName") or contact.get("first_name")
    ln = contact.get("lastName") or contact.get("last_name")
    fn_s = str(fn).strip() if fn is not None and str(fn).strip() else None
    ln_s = str(ln).strip() if ln is not None and str(ln).strip() else None
    return fn_s, ln_s


def _respond_io_id_from_contact(contact: dict) -> str | None:
    """Extract Respond.io contact id from payload (for inbox URL)."""
    cid = contact.get("contactId") or contact.get("id")
    if cid is None:
        return None
    return str(cid).strip() or None


def _contact_identifier(contact: dict, prefer_phone: bool = True) -> str:
    """API identifier for contact. Prefer phone: when available (avoids 403 on update with id:)."""
    phone = _phone_from_contact(contact)
    if prefer_phone and phone:
        return f"phone:{phone}"
    cid = contact.get("contactId") or contact.get("id")
    if cid:
        return f"id:{cid}" if ":" not in str(cid) else str(cid)
    if phone:
        return f"phone:{phone}"
    return f"id:{contact.get('id', 'unknown')}"


def _internal_contact_url(local_id: str) -> str:
    """URL of the internal contact in the CRM (for Respond.io backend_id custom field)."""
    base = (settings.frontend_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}/user-management/contacts/{local_id}"
    logger.warning("FRONTEND_BASE_URL not set; using local_id as backend_id value")
    return str(local_id)


def run_respond_contacts_sync(db: Session, task: ScheduledTask) -> dict[str, Any]:
    """
    Sync Respond.io contacts missing backend_id: list, upsert local, set custom field.
    Returns summary: scanned, created_local, updated_remote, failed.
    """
    scanned = 0
    created_local = 0
    updated_remote = 0
    failed = 0

    try:
        client = RespondClient()
    except Exception as e:
        logger.warning("Respond client init failed (no API key?): %s", e)
        return {"scanned": 0, "created_local": 0, "updated_remote": 0, "failed": 0, "error": str(e)}

    log_service = IntegrationLogService(db)

    # POST /v2/contact/list with filter: backend_id does not exist
    request_body = {**LIST_CONTACTS_BODY_MISSING_BACKEND_ID}
    base_url = (settings.respond_base_url or "https://api.respond.io").rstrip("/")
    request_url = f"{base_url}/v2/contact/list"
    try:
        result = client.list_contacts(body=request_body)
    except httpx.HTTPStatusError as e:
        response_body = (e.response.text if e.response else None) or None
        logger.exception("Respond list_contacts failed: %s", e)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="scheduled_task",
                business_id=str(task.id),
                direction="outbound",
                endpoint="/v2/contact/list",
                http_method="POST",
                status="failed",
                error_message=str(e),
            ),
            request_payload_dict=request_body,
        )
        return {
            "scanned": 0,
            "created_local": 0,
            "updated_remote": 0,
            "failed": 1,
            "error": str(e),
            "request_method": "POST",
            "request_url": request_url,
            "request_body": request_body,
            "response_body": response_body,
        }
    except Exception as e:
        logger.exception("Respond list_contacts failed: %s", e)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="scheduled_task",
                business_id=str(task.id),
                direction="outbound",
                endpoint="/v2/contact/list",
                http_method="POST",
                status="failed",
                error_message=str(e),
            ),
            request_payload_dict=request_body,
        )
        return {
            "scanned": 0,
            "created_local": 0,
            "updated_remote": 0,
            "failed": 1,
            "error": str(e),
            "request_method": "POST",
            "request_url": request_url,
            "request_body": request_body,
        }

    # Response shape: { "data" | "items" | "contacts": [ ... ], "pagination": ... }
    contacts = (
        result.get("data")
        or result.get("items")
        or result.get("contacts")
        or result.get("result")
        or []
    )
    if isinstance(contacts, dict):
        contacts = (
            contacts.get("data")
            or contacts.get("items")
            or contacts.get("contacts")
            or []
        ) or []
    scanned = len(contacts)
    backend_id_update_errors: list[dict[str, Any]] = []
    backend_id_update_attempts: list[dict[str, Any]] = []

    contact_service = ContactService(db)
    processed_local_ids: set[str] = set()

    for contact in contacts:
        try:
            phone = _phone_from_contact(contact)
            if not phone:
                failed += 1
                continue

            # Fetch full single-contact payload - same shape that manual sync parses correctly.
            # The list endpoint payload is unreliable for firstName/lastName/id extraction.
            try:
                full_payload = client.get_contact_by_phone(phone)
                parsed = parse_respond_contact_payload(full_payload)
            except Exception as fetch_err:
                logger.warning(
                    "Respond get_contact_by_phone failed for %s, falling back to list payload: %s",
                    phone,
                    fetch_err,
                )
                parsed = {}

            list_fn, list_ln = _first_last_from_contact(contact)
            list_name = _name_from_contact(contact)
            list_respond_io_id = _respond_io_id_from_contact(contact)

            # parsed (from single GET) wins; list values backfill anything still missing.
            first_name = parsed.get("first_name") if parsed.get("first_name") is not None else list_fn
            last_name = parsed.get("last_name") if parsed.get("last_name") is not None else list_ln
            name = parsed.get("name") if parsed.get("name") is not None else list_name
            respond_io_id = parsed.get("respond_io_id") if parsed.get("respond_io_id") is not None else list_respond_io_id

            # Upsert local respond_contacts
            existing = db.query(RespondContact).filter(RespondContact.phone_number == phone).first()
            if existing:
                local_id = existing.id
                if (
                    name is not None
                    or respond_io_id is not None
                    or first_name is not None
                    or last_name is not None
                ):
                    if name is not None:
                        setattr(existing, "name", name)
                    if first_name is not None:
                        setattr(existing, "first_name", first_name)
                    if last_name is not None:
                        setattr(existing, "last_name", last_name)
                    if respond_io_id is not None:
                        setattr(existing, "respond_io_id", respond_io_id)
                    db.commit()
                    db.refresh(existing)
            else:
                new_contact = contact_service.create_contact(
                    RespondContactCreate(
                        phone_number=phone,
                        name=name,
                        first_name=first_name,
                        last_name=last_name,
                        respond_io_id=respond_io_id,
                    )
                )
                local_id = new_contact.id
                created_local += 1
            processed_local_ids.add(str(local_id))

            # PUT /v2/contact/{identifier} - Respond.io expects snake_case custom_fields, value = internal contact URL
            identifier = _contact_identifier(contact)
            backend_id_value = _internal_contact_url(str(local_id))
            request_body_put = {
                "custom_fields": [
                    {"name": "backend_id", "value": backend_id_value},
                ]
            }
            try:
                response_put = client.update_contact(identifier, request_body_put)
                updated_remote += 1
                backend_id_update_attempts.append({
                    "identifier": identifier,
                    "phone": phone,
                    "local_id": str(local_id),
                    "request_body": request_body_put,
                    "success": True,
                    "response_body": response_put,
                })
            except httpx.HTTPStatusError as put_err:
                response_body = (put_err.response.text if put_err.response else None) or None
                error_msg = str(put_err)
                if response_body:
                    error_msg = f"{error_msg} | Response: {response_body[:2000]}"
                logger.exception(
                    "Respond backend_id update failed: identifier=%s local_id=%s status=%s response=%s",
                    identifier,
                    local_id,
                    put_err.response.status_code if put_err.response else None,
                    response_body[:500] if response_body else None,
                )
                log_service.create_integration_log(
                    IntegrationLogCreate(
                        integration_channel="respond_io",
                        business_table="respond_contacts",
                        business_id=str(local_id),
                        direction="outbound",
                        endpoint=f"/v2/contact/{identifier}",
                        http_method="PUT",
                        status="failed",
                        error_message=error_msg[:10000],
                    ),
                    request_payload_dict=request_body_put,
                )
                backend_id_update_errors.append({
                    "identifier": identifier,
                    "local_id": str(local_id),
                    "phone": phone,
                    "error": str(put_err),
                    "status_code": put_err.response.status_code if put_err.response else None,
                    "response_body": response_body,
                })
                backend_id_update_attempts.append({
                    "identifier": identifier,
                    "phone": phone,
                    "local_id": str(local_id),
                    "request_body": request_body_put,
                    "success": False,
                    "error": str(put_err),
                    "status_code": put_err.response.status_code if put_err.response else None,
                    "response_body": response_body,
                })
                failed += 1
            except Exception as put_err:
                logger.exception(
                    "Respond backend_id update failed: identifier=%s local_id=%s error=%s",
                    identifier,
                    local_id,
                    put_err,
                )
                log_service.create_integration_log(
                    IntegrationLogCreate(
                        integration_channel="respond_io",
                        business_table="respond_contacts",
                        business_id=str(local_id),
                        direction="outbound",
                        endpoint=f"/v2/contact/{identifier}",
                        http_method="PUT",
                        status="failed",
                        error_message=str(put_err),
                    ),
                    request_payload_dict=request_body_put,
                )
                backend_id_update_errors.append({
                    "identifier": identifier,
                    "local_id": str(local_id),
                    "phone": phone,
                    "error": str(put_err),
                    "response_body": None,
                })
                backend_id_update_attempts.append({
                    "identifier": identifier,
                    "phone": phone,
                    "local_id": str(local_id),
                    "request_body": request_body_put,
                    "success": False,
                    "error": str(put_err),
                    "response_body": None,
                })
                failed += 1
        except Exception as e:
            logger.exception("Error syncing contact: %s", e)
            failed += 1

    # Second pass: backfill local contacts whose Respond.io row already has backend_id
    # (so they're excluded from the list filter) but are missing first_name/last_name/respond_io_id.
    backfilled_local = 0
    backfill_failed = 0
    backfill_attempts: list[dict[str, Any]] = []
    incomplete_rows = (
        db.query(RespondContact)
        .filter(
            or_(
                RespondContact.first_name.is_(None),
                RespondContact.last_name.is_(None),
                RespondContact.respond_io_id.is_(None),
            )
        )
        .all()
    )
    for row in incomplete_rows:
        if str(row.id) in processed_local_ids:
            continue
        try:
            contact_service.sync_contact_name(str(row.id))
            backfilled_local += 1
            backfill_attempts.append({
                "local_id": str(row.id),
                "phone": str(row.phone_number),
                "success": True,
            })
        except Exception as bf_err:
            backfill_failed += 1
            backfill_attempts.append({
                "local_id": str(row.id),
                "phone": str(row.phone_number),
                "success": False,
                "error": str(bf_err),
            })
            logger.warning(
                "Backfill sync_contact_name failed for local_id=%s phone=%s: %s",
                row.id,
                row.phone_number,
                bf_err,
            )

    return {
        "scanned": scanned,
        "created_local": created_local,
        "updated_remote": updated_remote,
        "failed": failed,
        "backfilled_local": backfilled_local,
        "backfill_failed": backfill_failed,
        "backfill_attempts": backfill_attempts,
        "request_method": "POST",
        "request_url": request_url,
        "request_body": request_body,
        "response_body": result,
        "backend_id_update_errors": backend_id_update_errors,
        "backend_id_update_attempts": backend_id_update_attempts,
    }
