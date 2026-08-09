"""External API routes.

Every router here is mounted behind a permission guard (AC-AC-05). Before
Group A, any holder of the single shared EXTERNAL_API_KEY could reach every
one of these endpoints with no permission check whatsoever.

The router -> slug map lives in ``permissions.py`` so the answer to "what can
an integration actually reach?" is readable in one place. Mounting the guard
here rather than decorating 37 handlers means a newly added router cannot be
left unguarded by omission -- a completeness test asserts every mounted
prefix has an entry.
"""
from fastapi import APIRouter, Depends

from app.api.v1.external.permissions import (
    EXTERNAL_ENDPOINT_PERMISSIONS,
    require_external_permission,
    require_external_permission_for_path,
)
from app.api.v1.external import (
    packing_lists,
    spo_allocations,
    grn,
    product_attachments,
    promotions,
    forms,
    complaint_attachments,
    stock_inquiries,
    stock_inquiry_attachments,
    entity_attachments,
    purchase_requests,
    next_assignee,
    team_members,
    work_calendar,
    conversation_assignee,
    conversation_sla_tracking,
    presigned_url,
    respond_contacts,
    chat_history,
    conversation_variables,
    view_link,
    rag,
    portal_tokens,
    it_support_tickets,
    contact_access_types,
    access_agent,
    memory,
    ideation,
    ingest,
    complaint_intake,
)

router = APIRouter()

# Ingest and current-state reads for the ESB. One route serves several
# entities, each carrying a different permission, so the guard resolves the
# slug from the path rather than being fixed at mount (see permissions.py).
# S5: the one write call n8n makes when a dealer's WhatsApp burst closes. Wrapped as the
# MCP tool `complaint_intake_submit`; the `*_submit` suffix is load-bearing, because
# `_is_write_tool` keys off it to strip the tool from prompt dry-runs (AC-C0b).
router.include_router(
    complaint_intake.router,
    prefix="/complaint-intake",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["complaint-intake"]))],
)
router.include_router(
    ingest.ingest_router,
    prefix="/ingest",
    tags=["external"],
    dependencies=[
        Depends(require_external_permission_for_path(ingest.INGEST_PERMISSIONS))
    ],
)
router.include_router(
    ingest.read_router,
    prefix="/read",
    tags=["external"],
    dependencies=[
        Depends(require_external_permission_for_path(ingest.READ_PERMISSIONS))
    ],
)

router.include_router(
    packing_lists.router,
    prefix="/packing-lists",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["packing-lists"]))],
)
router.include_router(
    spo_allocations.router,
    prefix="/spo-allocations",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["spo-allocations"]))],
)
router.include_router(
    grn.router,
    prefix="/grn",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["grn"]))],
)
router.include_router(
    product_attachments.router,
    prefix="/product-attachments",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["product-attachments"]))],
)
router.include_router(
    promotions.router,
    prefix="/promotions",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["promotions"]))],
)
router.include_router(
    forms.router,
    prefix="/forms",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["forms"]))],
)
router.include_router(
    complaint_attachments.router,
    prefix="/complaint-attachments",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["complaint-attachments"]))],
)
router.include_router(
    stock_inquiries.router,
    prefix="/stock-inquiries",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["stock-inquiries"]))],
)
router.include_router(
    stock_inquiry_attachments.router,
    prefix="/stock-inquiry-attachments",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["stock-inquiry-attachments"]))],
)
router.include_router(
    entity_attachments.router,
    prefix="/entity-attachments",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["entity-attachments"]))],
)
router.include_router(
    purchase_requests.router,
    prefix="/purchase-requests",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["purchase-requests"]))],
)
router.include_router(
    next_assignee.router,
    prefix="/next-assignee",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["next-assignee"]))],
)
router.include_router(
    team_members.router,
    prefix="/team-members",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["team-members"]))],
)
router.include_router(
    work_calendar.router,
    prefix="/work-calendar",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["work-calendar"]))],
)
router.include_router(
    conversation_assignee.router,
    prefix="/conversation-assignee",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["conversation-assignee"]))],
)
router.include_router(
    conversation_sla_tracking.router,
    prefix="/conversation-sla-tracking",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["conversation-sla-tracking"]))],
)
router.include_router(
    presigned_url.router,
    prefix="/presigned-url",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["presigned-url"]))],
)
router.include_router(
    respond_contacts.router,
    prefix="/respond-contacts",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["respond-contacts"]))],
)
router.include_router(
    chat_history.router,
    prefix="/chat-history",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["chat-history"]))],
)
router.include_router(
    conversation_variables.router,
    prefix="/conversation-variables",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["conversation-variables"]))],
)
router.include_router(
    view_link.router,
    prefix="/view-link",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["view-link"]))],
)
router.include_router(
    rag.router,
    prefix="/rag",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["rag"]))],
)
router.include_router(
    portal_tokens.router,
    prefix="/portal-tokens",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["portal-tokens"]))],
)
router.include_router(
    it_support_tickets.router,
    prefix="/it-support/tickets",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["it-support/tickets"]))],
)
router.include_router(
    contact_access_types.router,
    prefix="/contact-access-types",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["contact-access-types"]))],
)
router.include_router(
    access_agent.router,
    prefix="/access-agent",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["access-agent"]))],
)
router.include_router(
    memory.router,
    prefix="/memory",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["memory"]))],
)
router.include_router(
    ideation.router,
    prefix="/ideation",
    tags=["external"],
    dependencies=[Depends(require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["ideation"]))],
)
