"""Stock inquiries and New Product Applications, with the product code lineage (NPA-FROM-SI).

So the assistant answers "why does this code exist", "which codes was it made from" and "was a code already made
from these codes" from the same rows the screens read (card `CARD-npa-from-si-07nov.md` rule 8):

- `new_product_application`: `new_product` is the ONE new code purchasing linked (owner, mock v3).
- `new_product_application_source`: one CURRENT code the application is built from (one or many).
- `new_product_application_line`: one product row of the request (product type, dimension, qty).

`StockInquiry` is not company scoped, and neither is its list screen. The line and source tables carry no
`company_id`: their `scope` states the company predicate through the application explicitly, because the session's
automatic criterion is not attached to a subquery the tool builds (`query._company_clause`).
"""
from __future__ import annotations

from sqlalchemy import or_, select

from app.models.new_product_application import (
    NewProductApplication,
    NewProductApplicationLine,
    NewProductApplicationSource,
)
from app.models.procurement import StockInquiry
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef

SI_VIEW = "procurement.stock_inquiries.view"
SI_VIEW_OWN = "procurement.stock_inquiries.view_own"
NPA_VIEW = "procurement.new_product_applications.view"
NPA_VIEW_OWN = "procurement.new_product_applications.view_own"


def _si_own(me):
    from app.services.own_scope import request_clause

    return request_clause(StockInquiry, me)


def _npa_mine(me):
    """The screen's rule (`new_product_application_service._visible`): applicant, or raised by their contact."""
    clauses = [NewProductApplication.applicant_id == me.user_id]
    if me.contact_id:
        clauses.append(NewProductApplication.contact_id == me.contact_id)
    return or_(*clauses)


def _visible_application_ids(db):
    from app.models.base import get_company_scope
    from app.services.company_scope import build_company_predicate

    stmt = select(NewProductApplication.id)
    predicate = build_company_predicate(NewProductApplication, get_company_scope(db))
    return stmt if predicate is None else stmt.where(predicate)


def _line_scope(db) -> list:
    return [NewProductApplicationLine.application_id.in_(_visible_application_ids(db))]


def _line_own(me):
    return NewProductApplicationLine.application_id.in_(select(NewProductApplication.id).where(_npa_mine(me)))


def _source_scope(db) -> list:
    return [NewProductApplicationSource.application_id.in_(_visible_application_ids(db))]


def _source_own(me):
    return NewProductApplicationSource.application_id.in_(select(NewProductApplication.id).where(_npa_mine(me)))


register(
    EntityDef(
        key="stock_inquiry",
        label="Stock inquiries",
        module="procurement",
        model=StockInquiry,
        view_permission=SI_VIEW,
        own_permission=SI_VIEW_OWN,
        own_clause=_si_own,
        fields={
            "inquiry_number": FieldDef("Inquiry number"),
            "status": FieldDef("Status"),
            "salesperson": FieldDef("Salesperson"),
            "product_code": FieldDef("Product code", note="The code text the salesperson typed (not linked)."),
            "item_description": FieldDef("Item description"),
            "project_customer": FieldDef("Project / customer"),
            "project_name": FieldDef("Project name"),
            "quantity": FieldDef("Quantity"),
            "delivery_date": FieldDef("Delivery date"),
            "purchasing_response": FieldDef("Purchasing response"),
            "npa_requested": FieldDef(
                "Purchasing asks for an NPA", note="Purchasing ticked: salesperson must create a New Product Application."
            ),
            "last_responded_at": FieldDef("Responded at"),
            "created_at": FieldDef("Created at"),
        },
        hint="stock inquiries salespeople raise to purchasing",
        name_by=("inquiry_number",),
        screen_path="/procurement-management/stock-inquiries/{id}",
        pages=("/procurement-management/stock-inquiries",),
        routes=("GET /api/v1/procurement/stock-inquiries/",),
    ),
    EntityDef(
        key="new_product_application",
        label="New product applications",
        module="procurement",
        model=NewProductApplication,
        view_permission=NPA_VIEW,
        own_permission=NPA_VIEW_OWN,
        own_clause=_npa_mine,
        fields={
            "application_no": FieldDef("Application number"),
            "status": FieldDef("Status"),
            "source": FieldDef("Raised from", note="staff or portal"),
            "customer_name": FieldDef("Customer"),
            "project_name": FieldDef("Project"),
            "needed_by": FieldDef("Target delivery"),
            "remark": FieldDef("Remark"),
            "submitted_at": FieldDef("Submitted at"),
            "completed_at": FieldDef("Completed at"),
            "created_at": FieldDef("Created at"),
            "new_code_text": FieldDef(
                "New product code (typed)",
                note="The code purchasing typed for a new item it opens in AutoCount; new_product stays empty "
                "for it, so match products by this exact code.",
            ),
            "new_code_closed_reason": FieldDef("New code not opened reason"),
            "new_code_at": FieldDef("New code linked at", note="When purchasing linked the new code (or closed it)."),
        },
        # No relation to stock_inquiry: the query engine joins a relation without the target's
        # view slug, and an inquiry's customer / salesperson need procurement.stock_inquiries.view.
        relations={"new_product": ("product", "new_product_id")},
        hint="NPA; new code = new_product, or new_code_text when typed, not linked",
        name_by=("application_no",),
        screen_path="/procurement-management/new-product-applications/{id}",
        pages=("/procurement-management/new-product-applications",),
        routes=("GET /api/v1/procurement/new-product-applications",),
    ),
    EntityDef(
        key="new_product_application_line",
        label="New product application products",
        module="procurement",
        model=NewProductApplicationLine,
        view_permission=NPA_VIEW,
        own_permission=NPA_VIEW_OWN,
        own_clause=_line_own,
        fields={
            "line_no": FieldDef("Product number"),
            "description": FieldDef("Product type", note="What was asked for (the request text, the why of the new code)."),
            "dimension": FieldDef("Dimension"),
            "material": FieldDef("Material"),
            "thickness": FieldDef("Thickness"),
            "packing": FieldDef("Packing"),
            "expected_qty": FieldDef("Qty"),
        },
        relations={"application": ("new_product_application", "application_id")},
        hint="one product asked for on an NPA",
        name_by=("line_no",),
        scope=_line_scope,
    ),
    EntityDef(
        key="new_product_application_source",
        label="New product application current codes",
        module="procurement",
        model=NewProductApplicationSource,
        view_permission=NPA_VIEW,
        own_permission=NPA_VIEW_OWN,
        own_clause=_source_own,
        fields={"position": FieldDef("Order picked")},
        relations={
            "application": ("new_product_application", "application_id"),
            "product": ("product", "product_id"),
        },
        hint="one CURRENT code an NPA's new code is built from",
        name_by=("position",),
        scope=_source_scope,
    ),
)
