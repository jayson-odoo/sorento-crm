"""The staff principal: who is asking when a panel message runs on the chatbot's brain.

AGENTIC-UNIFY PR 3 (`documentation/plans/chatbot/PLAN-agentic-unify-panel-31oct.md`). The engine,
lanes and router know a turn by one string, the contact's Respond id, and ask the contact row a
dozen questions about it. A staff member has no such row, and none is created: each of those seams
asks `current()` once, and a staff principal answers from the user instead.

**Server-side only.** `panel_service` puts it on the envelope with `ingress="panel"`, which
`/chat/turn` refuses (`api/v1/external/chat.py`), so `of_envelope` reads it from nowhere else, and
`run_turn` holds it in a ContextVar for the turn, because most seams hold only an id. A turn runs in
one thread (`offload=False`, no worker), and no seam reads it from the threads a turn starts.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any

from app.services.chatbot.contracts import PANEL_INGRESS
from app.services.respond_identifier import PANEL_KEY_PREFIX

#: The envelope extra that carries a principal. Honoured beside `ingress="panel"` only.
ENVELOPE_KEY = "staff_principal"

CUSTOMERS_VIEW = "order_management.customers.view"
SALES_AGENTS_VIEW = "master_data.sales_agents.view"
SUPPLIERS_VIEW = "procurement.suppliers.view"
#: `PROMOTION_LIST_READERS` of `api/v1/marketing/promotions.py`, the promotions read's own gate.
PROMOTION_READERS = ("marketing.promotions.view", "dealer_kit.page.view")

#: What a field-reveal key asks of a staff member: the slug of the screen that shows that data. A
#: contact holds these as grants (`contact_field_reveals`); a staff member's permissions answer them
#: instead (AC-5). A key not listed is not held, so a key added later stays hidden until it is listed.
_REVEAL_SLUGS: dict[str, str] = {
    "inventory.sellable": "inventory.stock.view",
    "purchase_orders.placed": "scm.purchase_orders.view",
    "purchase_orders.supplier": "procurement.suppliers.view",
    "purchase_orders.cost": "scm.purchase_orders.view",
    "sales_orders.outstanding": "order_management.orders.view",
    "sales_orders.sales_report": "sales.reports.view",
    "scm.low_stock_report": "scm.reorder.run",
    "chatbot.analytics": "chatbot.analytics.view",
    "sales.sales_target": "sales.targets.view",
}
#: Every `delivery_orders.*` key is one screen's fields.
_DELIVERY_ORDER_SLUG = "order_management.orders.view"


@dataclass(frozen=True)
class StaffPrincipal:
    user_id: str
    conversation_id: str
    active_company_id: str | None = None

    @property
    def key(self) -> str:
        """The turn's contact id: one per thread, so New chat starts clean. No colon, because the
        outbound check splits on one (`respond_identifier.contact_for_identifier`)."""
        return f"{PANEL_KEY_PREFIX}{self.conversation_id}"

    def may(self, db: Any, slug: str) -> bool:
        from app.services.user_service import UserPermissionService

        return UserPermissionService(db).check_user_has_permission(self.user_id, slug)

    def reveal_keys(self, db: Any) -> list[str]:
        """The field-reveal keys this user's permissions answer, in `ctx.access.attributes` form."""
        from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS

        needs = {
            key: _DELIVERY_ORDER_SLUG if key.startswith("delivery_orders.") else _REVEAL_SLUGS.get(key)
            for key, _label in FIELD_REVEAL_KEYS
        }
        held = {slug for slug in set(needs.values()) if slug and self.may(db, slug)}
        return sorted(key for key, slug in needs.items() if slug in held)


_CURRENT: ContextVar[StaffPrincipal | None] = ContextVar("chatbot_staff_principal", default=None)


def current() -> StaffPrincipal | None:
    """The principal this turn runs as; None on every contact's turn."""
    return _CURRENT.get()


@contextmanager
def acting_as(principal: StaffPrincipal | None) -> Iterator[None]:
    token = _CURRENT.set(principal)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def of_envelope(envelope: Any) -> StaffPrincipal | None:
    """The principal `panel_service` put on this envelope. None for any other ingress, whatever
    extras a caller sent."""
    if envelope.ingress != PANEL_INGRESS:
        return None
    raw = (envelope.model_extra or {}).get(ENVELOPE_KEY)
    return StaffPrincipal(**raw) if isinstance(raw, dict) else None


def envelope_extra(principal: StaffPrincipal) -> dict[str, Any]:
    return {ENVELOPE_KEY: asdict(principal)}


def lacks(db: Any, *slugs: str) -> bool:
    """A staff principal holding none of `slugs`: the gate on an in-process read (AC-6). False on a
    contact's turn, whose reads are scoped by the contact as before."""
    principal = current()
    return principal is not None and not any(principal.may(db, slug) for slug in slugs)
