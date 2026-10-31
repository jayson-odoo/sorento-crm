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
OPPORTUNITIES_ADD = "sales.opportunities.add"
#: `PROMOTION_LIST_READERS` of `api/v1/marketing/promotions.py`, the promotions read's own gate.
PROMOTION_READERS = ("marketing.promotions.view", "dealer_kit.page.view")


@dataclass(frozen=True)
class StaffPrincipal:
    user_id: str
    conversation_id: str
    active_company_id: str | None = None
    #: What the user's screen is on: `title`, `path` and, only when the record may be read,
    #: `record_kind` and `record_ref`. No visible text and no facts (they ride the agent's message).
    page: dict[str, Any] | None = None

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
        from app.services.contact_field_reveal_service import staff_reveal_keys

        return staff_reveal_keys(db, self.user_id)


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
