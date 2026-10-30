"""The permission layer of the agent (AGENTIC-P1 card section 3).

`AgentContext` is built server-side per turn and is immutable; nothing in it comes from the
model. A tool is exposed only when the linked user holds its slug, and `tools.dispatch`
checks the same again at call time.
"""
from __future__ import annotations

import dataclasses
import hashlib
import logging
from dataclasses import dataclass

from app.services.chatbot.agent.tools import REGISTRY, ToolDef

logger = logging.getLogger(__name__)


class AgentRefused(Exception):
    """The agent may not run for this contact. `reason` is one of contact_not_found,
    ai_replies_off, switch_off, no_linked_user."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AgentContext:
    contact_pk: str
    contact_respond_id: str
    space_id: str | None
    user_id: str
    user_name: str
    grants: frozenset[str]
    #: `respond_contacts.chatbot_stock_allowed`: may this contact check stock (today's bot gate).
    stock_allowed: bool = True
    #: Names of the tools this user and contact may use, and the contact's brand scope
    #: (None = unscoped): both go into `grants_hash`, so a lost permission or a narrower scope
    #: starts a new conversation.
    tool_names: tuple[str, ...] = ()
    brand_scope: frozenset[str] | None = None
    #: The argument-level slugs (`tools.ARG_PERMISSIONS`) the user holds, sorted; also hashed.
    arg_permissions: tuple[str, ...] = ()


def build_context(db, contact_respond_id: str) -> AgentContext:
    # Scope note for P1: reads are limited by the contact's brand scope, its reveal grants and
    # what the routes allow for the contact id. Company scope of the linked user is not applied
    # here, because the routes scope by contact id and the call itself runs as the integration.
    from app.models.access import RespondContact
    from app.models.base import company_scope, set_brand_scope, set_company_scope
    from app.models.user import User, UserStatus
    from app.services.chatbot.head.access import default_space_id
    from app.services.contact_brand_scope import NO_BRAND_ID, contact_brand_scope
    from app.services.contact_field_reveal_service import granted_keys

    # Company scope off for the lookup, as the brand scope resolver does: a contact row must
    # not read as missing because of the caller's scope.
    with company_scope(db, None):
        contact = (
            db.query(RespondContact)
            .filter(RespondContact.respond_io_id == contact_respond_id)
            .order_by(RespondContact.created_at, RespondContact.id)
            .first()
        )
        if contact is None:
            raise AgentRefused("contact_not_found")
        if not contact.chatbot_allowed:
            raise AgentRefused("ai_replies_off")
        if not contact.chatbot_agent_enabled:
            raise AgentRefused("switch_off")
        user = (
            db.query(User)
            .filter(User.respond_contact_id == contact.id, User.status == UserStatus.ACTIVE.value)
            .order_by(User.created_at, User.id)
            .first()
        )
        if user is None:
            raise AgentRefused("no_linked_user")
        pk = str(contact.id)
        user_id = str(user.id)
        user_name = user.name or ""

    space_id = default_space_id(db)
    try:
        grants = frozenset(str(k) for k in granted_keys(db, pk))
    except Exception:  # noqa: BLE001 - fail closed: no grant means no restricted field
        logger.warning("agent: field-reveal lookup failed for %s", contact_respond_id, exc_info=True)
        grants = frozenset()
    # Today's turn stamps the contact's brand scope on the session; `_mcp_call` guards on it.
    try:
        brand_scope = contact_brand_scope(db, contact_respond_id, space_id)
    except Exception:  # noqa: BLE001 - fail closed: a scope no brand matches
        logger.warning("agent: brand scope lookup failed for %s", contact_respond_id, exc_info=True)
        brand_scope = frozenset({NO_BRAND_ID})
    set_brand_scope(db, brand_scope)
    # The company scope too (engine.py `_contact_company_scope`): the resolver and the routes
    # called in process read the session, and an unstamped one reads nothing.
    try:
        from app.services import company_scope_resolver

        company = company_scope_resolver.resolve_contact_company_scope(db, contact_respond_id, space_id)
    except Exception:  # noqa: BLE001 - fail closed: an empty set owns no rows
        logger.warning("agent: company scope lookup failed for %s", contact_respond_id, exc_info=True)
        company = frozenset()
    set_company_scope(db, company)

    ctx = AgentContext(
        contact_pk=pk,
        contact_respond_id=str(contact.respond_io_id),
        space_id=space_id,
        user_id=user_id,
        user_name=user_name,
        grants=grants,
        stock_allowed=getattr(contact, "chatbot_stock_allowed", True) is not False,
        brand_scope=None if brand_scope is None else frozenset(str(b) for b in brand_scope),
    )
    from app.services.chatbot.agent.tools import ARG_PERMISSIONS, _permitted

    held = sorted({slug for slug in ARG_PERMISSIONS.values() if _permitted(db, user_id, slug)})
    return dataclasses.replace(
        ctx, tool_names=tuple(t.name for t in permitted_tools(db, ctx)), arg_permissions=tuple(held)
    )


def permitted_tools(db, ctx: AgentContext) -> list[ToolDef]:
    """REGISTRY entries the linked user and the contact may use, in registry order."""
    from app.services.chatbot.agent.tools import contact_allows, user_may_use

    return [t for t in REGISTRY.values() if user_may_use(db, ctx, t) and contact_allows(ctx, t)]


def grants_hash(ctx: AgentContext) -> str:
    """Stable digest of the contact's grants, the tools open to the user, the brand scope and the
    argument-level slugs the user holds; a change in any of them starts a new conversation."""
    scope = "none" if ctx.brand_scope is None else ",".join(sorted(ctx.brand_scope))
    parts = [
        ",".join(sorted(ctx.grants)),
        ",".join(sorted(ctx.tool_names)),
        scope,
        ",".join(sorted(ctx.arg_permissions)),
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()
