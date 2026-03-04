"""Respond.io contact sync: list contacts missing backend_id, upsert local, set custom field."""
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.access import RespondContact
from app.models.scheduled_task import ScheduledTask
from app.schemas.integration import IntegrationLogCreate
from app.schemas.user import ContactAgentAccessCreate
from app.services.integration_service import RespondClient, IntegrationLogService
from app.services.user_service import AccessAgentService

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


def _user_type_from_contact(contact: dict) -> str | None:
    """Extract user_type from custom_fields where name is user_type."""
    custom = (
        contact.get("custom_fields")
        or contact.get("customFields")
        or contact.get("data", {}).get("custom_fields")
        or contact.get("data", {}).get("customFields")
        or []
    )
    if not isinstance(custom, list):
        return None
    for f in custom:
        if str(f.get("name", "")).strip().lower() == "user_type":
            v = f.get("value")
            return str(v).strip() if v is not None else None
    return None


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

    for contact in contacts:
        try:
            phone = _phone_from_contact(contact)
            if not phone:
                failed += 1
                continue

            # Upsert local respond_contacts
            existing = db.query(RespondContact).filter(RespondContact.phone_number == phone).first()
            if existing:
                local_id = existing.id
                name = _name_from_contact(contact)
                user_type = _user_type_from_contact(contact)
                if name is not None or user_type is not None:
                    if name is not None:
                        setattr(existing, "name", name)
                    if user_type is not None:
                        setattr(existing, "user_type", user_type)
                    db.commit()
                    db.refresh(existing)
            else:
                new_contact = RespondContact(
                    phone_number=phone,
                    name=_name_from_contact(contact),
                    user_type=_user_type_from_contact(contact),
                )
                db.add(new_contact)
                db.commit()
                db.refresh(new_contact)
                local_id = new_contact.id
                created_local += 1

                # Assign default access agents to this new internal contact
                try:
                    access_agent_service = AccessAgentService(db)
                    default_agents = access_agent_service.list_agents_assign_to_new_internal_contacts()
                    contact_name = (str(new_contact.name) if getattr(new_contact, "name", None) is not None else "") or ""
                    for agent in default_agents:
                        try:
                            access_agent_service.create_contact_access(
                                str(agent.id),
                                ContactAgentAccessCreate(
                                    respond_contact_phone=str(new_contact.phone_number),
                                    respond_contact_name=contact_name,
                                    agent_id=str(agent.id),
                                    is_allowed=True,
                                ),
                            )
                        except Exception as assign_err:
                            logger.warning(
                                "Assign default agent %s to new contact %s failed: %s",
                                agent.code,
                                new_contact.phone_number,
                                assign_err,
                            )
                except Exception as e:
                    logger.warning("Resolve default agents for new contact failed: %s", e)

            # PUT /v2/contact/{identifier} – Respond.io expects snake_case custom_fields, value = internal contact URL
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

    return {
        "scanned": scanned,
        "created_local": created_local,
        "updated_remote": updated_remote,
        "failed": failed,
        "request_method": "POST",
        "request_url": request_url,
        "request_body": request_body,
        "response_body": result,
        "backend_id_update_errors": backend_id_update_errors,
        "backend_id_update_attempts": backend_id_update_attempts,
    }
