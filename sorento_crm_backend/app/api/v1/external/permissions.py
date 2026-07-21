"""Permission enforcement for ``/api/v1/external/*`` (AC-AC-05).

Until Group A, ``get_external_api_user`` applied **no permission check at all**:
any holder of the single shared key could reach every endpoint here. This module
closes that, using the same RBAC slugs the rest of the application uses rather
than a parallel scope vocabulary -- integrations act as real users, so ordinary
permission checks simply work.

``EXTERNAL_ENDPOINT_PERMISSIONS`` below is the authoritative map of external
router to required permission. It is deliberately explicit and in one place: the
answer to "what can an integration actually reach?" should be readable without
tracing 28 routers.

Some endpoints here support integrations and have no human-facing counterpart,
so no slug existed for them. Those get new ``integration.*`` slugs, registered in
``permission_registry`` and granted to existing roles by migration -- a
permission with no grant path silently 403s the feature it was meant to protect.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_external_api_user
from app.services.user_service import UserPermissionService


def require_external_permission(permission_slug: str):
    """Authenticate the integration key, then require ``permission_slug``.

    401 for an unusable key, 403 for a usable key whose principal lacks the
    grant. Keeping those distinct matters: collapsing them makes a
    misconfigured integration role indistinguishable from a bad key.

    Returns the resolved principal so endpoints can keep reading
    ``current_user`` for attribution.
    """

    def _require(
        current_user: dict = Depends(get_external_api_user),
        db: Session = Depends(get_db),
    ) -> dict:
        service = UserPermissionService(db)
        if not service.check_user_has_permission(current_user["id"], permission_slug):
            # Name the missing slug: an operator seeing this needs to know which
            # grant to add, and it reveals nothing an attacker could use -- they
            # already hold a valid key at this point.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_denied",
                    "message": f"Permission required: {permission_slug}",
                    "permission": permission_slug,
                },
            )
        return current_user

    return _require


# --------------------------------------------------------------------------- #
# Router -> required permission.
#
# Read endpoints take .view; endpoints that create or mutate take .add/.edit.
# Where a router mixes both, the stricter slug is applied per endpoint in that
# router rather than at mount time.
# --------------------------------------------------------------------------- #
EXTERNAL_ENDPOINT_PERMISSIONS: dict[str, str] = {
    # Procurement / inventory documents
    "packing-lists": "procurement.packing_lists.add",
    "spo-allocations": "procurement.spo_allocations.add",
    "grn": "procurement.grn.add",
    "purchase-requests": "procurement.purchase_requests.add",
    "stock-inquiries": "procurement.stock_inquiries.add",
    # Attachments and files
    "product-attachments": "resource.attachments.upload",
    "complaint-attachments": "resource.attachments.upload",
    "stock-inquiry-attachments": "resource.attachments.upload",
    "entity-attachments": "resource.attachments.upload",
    "presigned-url": "integration.storage.presign",
    "view-link": "integration.storage.presign",
    # Marketing / forms / tickets
    "promotions": "marketing.promotions.add",
    "forms": "forms.forms.add",
    "it-support/tickets": "tickets.tickets.add",
    # Conversation, assignment and SLA support
    "next-assignee": "integration.assignment.resolve",
    "team-members": "user_management.teams.view",
    "work-calendar": "system.work_calendar.view",
    "conversation-assignee": "sla_management.conversation_sla_tracking.reassign",
    "conversation-sla-tracking": "sla_management.conversation_sla_tracking.view",
    "conversation-variables": "integration.conversation_context.edit",
    "contact-access-types": "user_management.access_agents.view",
    "access-agent": "user_management.access_agents.view",
    "respond-contacts": "integration.contacts.sync",
    "portal-tokens": "user_management.contacts.portal_link",
    # AI-adjacent surfaces
    "chat-history": "system.chat_history.view",
    "rag": "integration.semantic_search.use",
    "memory": "integration.conversation_context.edit",
    "ideation": "integration.ideation.submit",
}

# Slugs invented for this surface because no human-facing equivalent existed.
# Registered in permission_registry and granted by migration 298.
NEW_INTEGRATION_PERMISSIONS: list[dict] = [
    {
        "slug": "integration.storage.presign",
        "name": "Presign storage URLs",
        "description": "Generate presigned upload/download URLs and view links for stored files.",
    },
    {
        "slug": "integration.assignment.resolve",
        "name": "Resolve next assignee",
        "description": "Ask Sorento which team member should handle a conversation next.",
    },
    {
        "slug": "integration.conversation_context.edit",
        "name": "Read and write conversation context",
        "description": "Read or update conversation variables and assistant memory frames.",
    },
    {
        "slug": "integration.contacts.sync",
        "name": "Sync contacts",
        "description": "Create or update Respond.io contact records from an external system.",
    },
    {
        "slug": "integration.semantic_search.use",
        "name": "Use semantic search",
        "description": "Run embedding and tool retrieval searches.",
    },
    {
        "slug": "integration.ideation.submit",
        "name": "Submit ideation turns",
        "description": "Post ideation capture turns from an external channel.",
    },
]
