"""Per-entity adapters for the skip-the-next-stage engine.

The engine is generic; the *meaning* of a skip is not. Config carries the data
(`skip_event`, `skip_terminal_status`, `skip_action_label`); an adapter carries the
behaviour that only the owning domain can know:

  * which model and status column hold the entity's state
  * which statuses may legally be skipped FROM
  * which permission authorises it - deliberately NOT in config, so inserting a
    config row can never mint authority
  * the consequence sentence shown in the confirm dialog (domain truth, never a
    config-authored string)
  * how to tell the contact, and which automation event to dispatch

Registering an adapter is the only code a second entity type needs. Today there is
one: complaint -> "Settled on site".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FormSkipAdapter:
    """Everything the generic skip endpoint cannot know about an entity type."""

    source_entity_type: str
    #: SQLAlchemy model class holding the entity.
    model: Any
    #: Statuses the entity may be skipped FROM. Empty tuple = any status.
    allowed_source_statuses: tuple[str, ...]
    #: Permission slug authorising the skip for this entity type.
    permission_slug: str
    #: Shown in the confirm dialog. What this means for the customer, in plain words.
    consequence_copy: str
    #: Attribute holding the entity's status.
    status_attr: str = "status"
    #: Attributes stamped with the resolution time / actor, when present on the model.
    resolved_at_attr: Optional[str] = "resolved_at"
    resolved_by_attr: Optional[str] = "resolved_by"
    #: Human label for error messages ("complaint").
    display_name: str = "record"
    #: Automation trigger dispatched after commit. None = no automation.
    automation_event: Optional[str] = None
    #: (db, entity) -> dict - the automation context. Required when automation_event set.
    build_automation_context: Optional[Callable[[Any, Any], dict]] = None
    #: (db, entity, note, actor_user_id) -> None - tell the contact. Best-effort.
    notify: Optional[Callable[[Any, Any, Optional[str], Optional[str]], None]] = None


_REGISTRY: dict[str, FormSkipAdapter] = {}


def register_skip_adapter(adapter: FormSkipAdapter) -> None:
    _REGISTRY[adapter.source_entity_type] = adapter


def get_skip_adapter(source_entity_type: Optional[str]) -> Optional[FormSkipAdapter]:
    if not source_entity_type:
        return None
    return _REGISTRY.get(str(source_entity_type).strip())


def registered_skip_types() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


# --------------------------------------------------------------------------- #
# Complaint - "Settled on site"
# --------------------------------------------------------------------------- #

COMPLAINT_SETTLED_STATUS = "settled_on_site"
COMPLAINT_SETTLED_LABEL = "Settled on site"


def _complaint_automation_context(db, complaint) -> dict:
    """Same shape as complaint_approved, but honest about the status.

    Reusing complaint_approved would emit "status": "approved" for a complaint that is
    not approved, poisoning the field automations branch on.
    """
    from datetime import date as _date

    from app.services.automation_triggers import _build_complaint_link

    rc = getattr(complaint, "root_cause", None)
    res = getattr(complaint, "resolution", None)
    return {
        "complaint": {
            "id": str(complaint.id),
            "complaint_number": getattr(complaint, "complaint_number", None),
            "delivery_order_number": getattr(complaint, "delivery_order_number", None),
            "customer_name": getattr(complaint, "customer_name", None),
            "salesperson": getattr(complaint, "salesperson", None),
            "product_code": getattr(complaint, "product_code", None),
            "complaint_type": getattr(complaint, "complaint_type", None),
            "status": COMPLAINT_SETTLED_STATUS,
            "link": _build_complaint_link(str(complaint.id)),
            "root_cause": getattr(rc, "name", None) if rc is not None else None,
            "resolution": getattr(res, "name", None) if res is not None else None,
        },
        "today": _date.today().isoformat(),
    }


def _notify_complaint_contact(db, complaint, note: Optional[str], actor_user_id: Optional[str]) -> None:
    """One Respond.io status message - never two.

    Mirrors _finalize_complaint's shape: a lean `update` core plus the portal/view
    links, with the optional note appended.
    """
    from app.services.complaints_service import ComplaintService

    svc = ComplaintService(db)
    complaint_id = str(complaint.id)
    identifier = svc._identifier_from_respond_inbox_url(
        getattr(complaint, "respond_inbox_url", None)
    )
    if not identifier:
        logger.info(
            "Complaint %s settled on site: no respond_inbox_url; status committed, "
            "no message queued.",
            complaint_id,
        )
        return

    do_number = (getattr(complaint, "delivery_order_number", None) or "").strip()
    do_spec = f" for delivery order {do_number}" if do_number else ""
    link_part = svc._complaint_status_link_part(complaint, complaint_id)
    note_clean = (note or "").strip()
    note_part = f" Note: {note_clean}" if note_clean else ""
    display_message = (
        f"There has been an update regarding your complaint{do_spec}: "
        f"status changed to settled on site by our technician.{note_part}{link_part}"
    )
    update_core = COMPLAINT_SETTLED_LABEL
    if note_clean:
        update_core += f". Note: {note_clean}"
    svc._enqueue_respond_message_for_complaint(
        complaint_id=complaint_id,
        identifier=identifier,
        display_message=display_message,
        respond_user_id=actor_user_id,
        crm_sender_user_id=actor_user_id,
        space_id=getattr(complaint, "space_id", None),
        extra_context_vars={
            "update": update_core,
            "portal_url": svc._complaint_portal_or_view_url(complaint, complaint_id),
            "view_url": (svc._build_complaint_view_url(complaint_id) or "").strip(),
        },
    )


def _register_builtin_adapters() -> None:
    from app.models.complaints import Complaint

    register_skip_adapter(
        FormSkipAdapter(
            source_entity_type="complaint",
            model=Complaint,
            # Same gate as approve/reject: the technician has attended and their
            # write-up is what moved the complaint to `responded`.
            allowed_source_statuses=("responded",),
            permission_slug="complaint_management.complaints.settle_on_site",
            consequence_copy=(
                "The technician settled this complaint during the site visit, so no "
                "replacement will be arranged and customer service will not be assigned."
            ),
            display_name="complaint",
            automation_event="complaint_settled_on_site",
            build_automation_context=_complaint_automation_context,
            notify=_notify_complaint_contact,
        )
    )


_register_builtin_adapters()
