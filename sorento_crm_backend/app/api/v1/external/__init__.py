"""External API routes."""
from fastapi import APIRouter
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
    work_calendar,
    conversation_assignee,
    conversation_sla_tracking,
    presigned_url,
    respond_contacts,
    chat_history,
    view_link,
    rag,
)

router = APIRouter()

router.include_router(packing_lists.router, prefix="/packing-lists", tags=["external"])
router.include_router(spo_allocations.router, prefix="/spo-allocations", tags=["external"])
router.include_router(grn.router, prefix="/grn", tags=["external"])
router.include_router(product_attachments.router, prefix="/product-attachments", tags=["external"])
router.include_router(promotions.router, prefix="/promotions", tags=["external"])
router.include_router(forms.router, prefix="/forms", tags=["external"])
router.include_router(complaint_attachments.router, prefix="/complaint-attachments", tags=["external"])
router.include_router(stock_inquiries.router, prefix="/stock-inquiries", tags=["external"])
router.include_router(stock_inquiry_attachments.router, prefix="/stock-inquiry-attachments", tags=["external"])
router.include_router(entity_attachments.router, prefix="/entity-attachments", tags=["external"])
router.include_router(purchase_requests.router, prefix="/purchase-requests", tags=["external"])
router.include_router(next_assignee.router, prefix="/next-assignee", tags=["external"])
router.include_router(work_calendar.router, prefix="/work-calendar", tags=["external"])
router.include_router(conversation_assignee.router, prefix="/conversation-assignee", tags=["external"])
router.include_router(conversation_sla_tracking.router, prefix="/conversation-sla-tracking", tags=["external"])
router.include_router(presigned_url.router, prefix="/presigned-url", tags=["external"])
router.include_router(respond_contacts.router, prefix="/respond-contacts", tags=["external"])
router.include_router(chat_history.router, prefix="/chat-history", tags=["external"])
router.include_router(view_link.router, prefix="/view-link", tags=["external"])
router.include_router(rag.router, prefix="/rag", tags=["external"])
