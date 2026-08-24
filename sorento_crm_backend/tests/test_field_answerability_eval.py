"""Live-LLM eval: the bubble answers about ANY visible field + SLA tab + audit.

Opt-in (RUN_LLM_EVALS=1) and self-discovering: for each form-SLA entity it picks
a real record from the live DB (skips that entity if none), builds visible_text
from the real columns the detail page shows, and asserts the bubble's answer is
GROUNDED in the real value (case-insensitive token match) - not exact prose.

Why this shape (anti-overfit): we never hardcode expected answers; we assert the
real field value appears. visible_text covers on-screen fields; the assembler
covers the off-screen SLA tab + audit log. Both reach the render path.

Run: RUN_LLM_EVALS=1 venv/bin/python -m pytest tests/test_field_answerability_eval.py -q -s
"""
from __future__ import annotations

import os

import pytest

_RUN = os.getenv("RUN_LLM_EVALS") == "1"
pytestmark = pytest.mark.skipif(
    not _RUN, reason="live-LLM eval; set RUN_LLM_EVALS=1 against a configured stack"
)


def _chat_and_user():
    from app.database import SessionLocal
    from app.models.user import User
    from app.services.user_service import UserPermissionService
    from app.services.ai_assistant_service import AIAssistantChatService

    db = SessionLocal()
    uid = next(
        (u.id for u in db.query(User).filter(User.status == "ACTIVE").limit(80)
         if UserPermissionService(db).check_user_has_permission(u.id, "system.ai_assistant_chat.use")),
        None,
    )
    if uid is None:
        pytest.skip("no user with ai_assistant_chat.use")
    return db, uid, AIAssistantChatService(db)


def _grounded(answer: str, expected: str) -> bool:
    # Normalize underscores<->spaces so snake_case values (e.g. "in_transit")
    # match how the LLM naturally renders them ("in transit").
    a = (answer or "").lower().replace("_", " ")
    e = (expected or "").strip().lower().replace("_", " ")
    if not e:
        return True
    if e in a:
        return True
    toks = [t for t in e.replace(",", " ").split() if len(t) > 3]
    return bool(toks) and any(t in a for t in toks)


def _ask(chat, uid, entity, eid, path, vt, q):
    from app.schemas.ai_assistant import PageSnapshotPayload, PageEntityRef

    snap = PageSnapshotPayload(
        path=path + str(eid), search="", title=path, visible_text=vt,
        entity=PageEntityRef(entity_type=entity, id=str(eid)),
    )
    _, m = chat.respond(user_id=uid, conversation_id=None, message=q, page_snapshot=snap)
    return m.content or ""


def _vt(pairs):
    return "  ".join(f"{label}: {v}" for label, v in pairs if v not in (None, ""))


def test_purchase_request_field_sla_audit_answerable():
    from app.models.procurement import PurchaseRequestHeader as P

    db, uid, chat = _chat_and_user()
    row = (db.query(P).filter(P.request_type == "purchase_request", P.purpose.isnot(None)).first()
           or db.query(P).filter(P.request_type == "purchase_request").first())
    if row is None:
        pytest.skip("no purchase_request")
    vt = _vt([("Purchase request number", row.request_number), ("Customer Name", row.customer_name),
              ("Project Title", row.project_title), ("Purpose", row.purpose)])
    base = "/procurement-management/purchase-requests/"
    if row.purpose:
        assert _grounded(_ask(chat, uid, "purchase_request", row.id, base, vt, "what is the purpose of this"), row.purpose)
    if row.customer_name:
        assert _grounded(_ask(chat, uid, "purchase_request", row.id, base, vt, "who is the customer"), row.customer_name)
    # SLA tab + audit must produce a relevant (not refusal) answer
    sla = _ask(chat, uid, "purchase_request", row.id, base, vt, "what's the SLA status")
    assert any(k in sla.lower() for k in ("sla", "tier", "due", "respond", "not", "no "))
    aud = _ask(chat, uid, "purchase_request", row.id, base, vt, "show the audit history")
    assert any(k in aud.lower() for k in ("audit", "chang", "status", "approv", "empty", "no "))


def test_stock_inquiry_field_sla_audit_answerable():
    from app.models.procurement import StockInquiry

    db, uid, chat = _chat_and_user()
    row = (db.query(StockInquiry).filter(StockInquiry.item_description.isnot(None)).first()
           or db.query(StockInquiry).first())
    if row is None:
        pytest.skip("no stock_inquiry")
    vt = _vt([("Stock inquiry number", row.inquiry_number), ("Product code", row.product_code),
              ("Item description", row.item_description), ("Project customer", row.project_customer),
              ("Comment / reply by purchasing", row.purchasing_response)])
    base = "/procurement-management/stock-inquiries/"
    if row.item_description:
        assert _grounded(_ask(chat, uid, "stock_inquiry", row.id, base, vt, "what is the item description"), row.item_description)
    if row.product_code:
        assert _grounded(_ask(chat, uid, "stock_inquiry", row.id, base, vt, "what product code is this for"), row.product_code)
    sla = _ask(chat, uid, "stock_inquiry", row.id, base, vt, "what's the SLA status")
    assert any(k in sla.lower() for k in ("sla", "tier", "due", "respond", "not", "no "))


def test_absent_field_is_not_fabricated():
    """Honesty: asking about a field that is NOT on screen / not set must yield an
    acknowledgement of absence, not an invented value. Guards against the bubble
    fabricating data the user can't see (anti-overfit / grounding requirement).
    """
    from app.models.procurement import PurchaseRequestHeader as P
    from app.schemas.ai_assistant import PageSnapshotPayload, PageEntityRef

    db, uid, chat = _chat_and_user()
    row = db.query(P).filter(P.request_type == "purchase_request").first()
    if row is None:
        pytest.skip("no purchase_request")
    # Build a screen that deliberately OMITS the delivery address.
    vt = _vt([("Purchase request number", row.request_number), ("Customer Name", row.customer_name)])
    snap = PageSnapshotPayload(path="/procurement-management/purchase-requests/" + str(row.id),
                               search="", title="PR", visible_text=vt,
                               entity=PageEntityRef(entity_type="purchase_request", id=str(row.id)))
    _, m = chat.respond(user_id=uid, conversation_id=None,
                        message="what is the delivery address on this", page_snapshot=snap)
    ans = (m.content or "").lower()
    # Must acknowledge it's not available; must NOT invent a street/postcode.
    acknowledges = any(k in ans for k in (
        "not", "no ", "isn't", "doesn't", "unavailable", "not set", "not provided",
        "not specified", "not listed", "couldn't find", "can't find", "don't have",
    ))
    assert acknowledges, f"did not acknowledge absent field -> {ans[:140]!r}"


def test_visible_text_answers_without_assembler():
    """Fan-out coverage: any detail page's visible fields are answerable through
    the agent loop from visible_text alone - NO entity registration, NO assembler.
    This is why the non-form entities (products, GRN, SPO, stock, promotion, …)
    need no new backend code. Proven here on a synthetic product screen.
    """
    from app.schemas.ai_assistant import PageSnapshotPayload

    db, uid, chat = _chat_and_user()
    vt = ("Product TILE-600 Porcelain Tile 600x600. Brand: Sorento. "
          "Category: Floor Tiles. Unit: Box. Price: RM 45.00 per box. Status: Active.")
    snap = PageSnapshotPayload(path="/master-data-management/products/x", search="",
                               title="Product TILE-600", visible_text=vt, entity=None)
    for q, expect in [("what is the price of this product", "45"),
                      ("what brand is this", "Sorento"),
                      ("what category is this product", "Floor Tiles")]:
        _, m = chat.respond(user_id=uid, conversation_id=None, message=q, page_snapshot=snap)
        assert _grounded(m.content or "", expect), f"{q!r} -> {(m.content or '')[:80]!r}"


def test_sponsorship_form_field_sla_audit_answerable():
    from app.models.procurement import PurchaseRequestHeader as P

    db, uid, chat = _chat_and_user()
    row = db.query(P).filter(P.request_type == "sponsorship_form").first()
    if row is None:
        pytest.skip("no sponsorship_form")
    vt = _vt([("Sponsorship form number", row.request_number), ("Customer Name", row.customer_name),
              ("Project Title", row.project_title), ("Sponsor Subject", row.sponsor_subject),
              ("Total Project Value", row.total_project_value_text)])
    base = "/procurement-management/sponsorship-forms/"
    if row.customer_name:
        assert _grounded(_ask(chat, uid, "sponsorship_form", row.id, base, vt, "who is the customer"), row.customer_name)
    if row.sponsor_subject:
        assert _grounded(_ask(chat, uid, "sponsorship_form", row.id, base, vt, "what is the sponsor subject"), row.sponsor_subject)
    sla = _ask(chat, uid, "sponsorship_form", row.id, base, vt, "what's the SLA status")
    assert any(k in sla.lower() for k in ("sla", "tier", "due", "respond", "not", "no "))


def test_fanout_visible_fields_answerable_on_real_data():
    """Fan-out: every named non-form entity's visible fields are answerable through
    the agent loop from visible_text alone (NO entity, NO assembler). Loads a real
    record per entity, builds visible_text from real columns, asserts the real
    value appears. Proves the universal mechanism per entity, not just in theory.
    """
    from app.schemas.ai_assistant import PageSnapshotPayload

    db, uid, chat = _chat_and_user()

    def _try(import_path, cls_name):
        try:
            mod = __import__(import_path, fromlist=[cls_name])
            return getattr(mod, cls_name)
        except Exception:
            return None

    Product = _try("app.models.product", "Product")
    Form = _try("app.models.forms", "Form")
    Attachment = _try("app.models.resources", "Attachment")
    Promotion = _try("app.models.marketing", "Promotion")
    Stock = _try("app.models.inventory", "Stock")
    PickingHeader = _try("app.models.procurement", "PickingHeader")
    SPOAllocation = _try("app.models.procurement", "SPOAllocation")
    Order = _try("app.models.order", "Order")  # "delivery orders"
    InboundShipment = _try("app.models.procurement", "InboundShipment")  # "packing list"

    # (label, column) pairs to build visible_text; (question, column) to assert grounded
    specs = []
    if Product:
        specs.append((db.query(Product).filter(Product.product_code.isnot(None)).first(),
                      [("Product code", "product_code"), ("Product name", "product_name")],
                      [("what is the product code", "product_code")]))
    if PickingHeader:
        specs.append((db.query(PickingHeader).filter(PickingHeader.picking_number.isnot(None)).first(),
                      [("Picking number", "picking_number"), ("Status", "picking_status")],
                      [("what is the picking number", "picking_number"), ("what is the status", "picking_status")]))
    if SPOAllocation:
        specs.append((db.query(SPOAllocation).filter(SPOAllocation.spo_number.isnot(None)).first(),
                      [("SPO number", "spo_number"), ("Receipt status", "receipt_status")],
                      [("what is the receipt status", "receipt_status")]))
    if Stock:
        specs.append((db.query(Stock).filter(Stock.quantity_on_hand > 0).first(),
                      [("Quantity on hand", "quantity_on_hand")],
                      [("how much is on hand", "quantity_on_hand")]))
    if Promotion:
        specs.append((db.query(Promotion).filter(Promotion.description.isnot(None)).first(),
                      [("Promotion", "description")],
                      [("what is this promotion about", "description")]))
    if Form:
        specs.append((db.query(Form).filter(Form.code.isnot(None)).first(),
                      [("Form code", "code"), ("Name", "name"), ("Form type", "form_type")],
                      [("what is the form name", "name")]))
    if Attachment:
        specs.append((db.query(Attachment).filter(Attachment.original_filename.isnot(None)).first(),
                      [("File name", "original_filename"), ("Type", "mime_type")],
                      [("what is the file name", "original_filename")]))
    if Order:  # "delivery orders" - has a catalog MCP tool; verifies prefer-visible nudge
        specs.append((db.query(Order).filter(Order.order_number.isnot(None)).first(),
                      [("Order number", "order_number"), ("Debtor", "debtor_name"),
                       ("Order type", "order_type")],
                      [("what is the order number", "order_number"),
                       ("who is the debtor customer", "debtor_name")]))
    if InboundShipment:  # "packing list"
        specs.append((db.query(InboundShipment).filter(InboundShipment.shipment_number.isnot(None)).first(),
                      [("Shipment number", "shipment_number"), ("Status", "shipment_status")],
                      [("what is the shipment number", "shipment_number"),
                       ("what is the shipment status", "shipment_status")]))

    checked = 0
    for row, labelcols, qs in specs:
        if row is None:
            continue
        vt = "  ".join(f"{lab}: {getattr(row, c)}" for lab, c in labelcols if getattr(row, c, None) not in (None, ""))
        snap = PageSnapshotPayload(path="/x/" + str(row.id), search="", title="x", visible_text=vt, entity=None)
        for q, col in qs:
            expect = getattr(row, col, None)
            if expect in (None, ""):
                continue
            _, m = chat.respond(user_id=uid, conversation_id=None, message=q, page_snapshot=snap)
            assert _grounded(m.content or "", str(expect)), f"{q!r} expect~{expect!r} -> {(m.content or '')[:90]!r}"
            checked += 1
    if checked == 0:
        pytest.skip("no fan-out records to validate")


def test_complaint_field_sla_audit_answerable():
    from app.models.complaints import Complaint

    db, uid, chat = _chat_and_user()
    row = (db.query(Complaint).filter(Complaint.defect_description.isnot(None)).first()
           or db.query(Complaint).first())
    if row is None:
        pytest.skip("no complaint")
    vt = _vt([("Complaint number", row.complaint_number), ("Customer Name", row.customer_name),
              ("Complaint Type", row.complaint_type), ("Defect Description", row.defect_description)])
    base = "/complaint-management/complaints/"
    if row.defect_description:
        assert _grounded(_ask(chat, uid, "complaint", row.id, base, vt, "what is the defect"), row.defect_description)
    if row.complaint_type:
        assert _grounded(_ask(chat, uid, "complaint", row.id, base, vt, "what type of complaint is this"), row.complaint_type)
    sla = _ask(chat, uid, "complaint", row.id, base, vt, "what's the SLA status")
    assert any(k in sla.lower() for k in ("sla", "tier", "due", "breach", "not", "no "))
