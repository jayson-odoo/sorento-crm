"""The one sales calculation (SALES-UNIFIED, `documentation/plans/sales/PLAN-sales-unified-27oct.md`
2.1 to 2.4; owner ruling 27 Oct 16:12: "all using a shared function to calculation").

**Sales = Invoices + Cash sales + Debit notes - Credit notes**, on AutoCount's `LocalNetTotal`
(MYR, net of tax), filed by the document's own date, cancelled documents excluded. Item figures
come from the lines the same way, a credit note line negative in quantity and amount.

Every invoiced figure in the CRM is built from these expressions: the reports kernel's billing
datasets (`reports/datasets/billing_documents.py`, `billing_document_lines.py`), and through
them the reports, the chatbot's `crm_sales_analysis`, `crm_report_ask` (invoiced basis) and the
top selling route. The sign is applied here and nowhere else.

Each builder returns a SQL expression over `BillingDocument` (and `BillingDocumentLine` for the
line figures); every other table is read through an ALIASED correlated subquery, so an
expression drops into any query that has `finance.billing_documents` in its FROM, whatever else
that query has joined.

**The sales type** (owner ruling Q1 (b), 27 Oct 16:2x: "the sales type should depend on sales
order") is derived at read time from the sales orders a document traces to, by the rules of
DOC-RELATIONS (`app/services/document_relations.py`, #1912): a billing line resolved onto an SO
line, transferred from an SO by number, or transferred from a DO by number and that DO's SOs; a
note with no traced line inherits its invoice's orders. It never reads the stored
`billing_documents.demand_class`, an agent's class or a customer's segment: a document that
traces to no sales order is "No sales order", visible and never guessed. A customer on the
set-apart list for the document's month is "Set apart" whatever its orders say.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.orm import aliased

from app.models.company import Company
from app.models.finance import CREDIT_NOTE, DOCUMENT_TYPES, POSTED, BillingDocument, BillingDocumentLine
from app.models.order import Customer, Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.sales import SetApartCustomer
from app.models.sales_agent import SalesAgent
from app.services.error_handler import AppException

AGENT_FROM_DOCUMENT = "document"
AGENT_FROM_CUSTOMER = "customer"
AGENT_SOURCES = (AGENT_FROM_DOCUMENT, AGENT_FROM_CUSTOMER)

#: The label of a sale with no agent, as the order datasets print it.
NO_AGENT = "(no agent)"

DEALER = "dealer"
PROJECT = "project"
OTHER = "other"
SET_APART = "set_apart"
MIXED = "mixed"
TYPE_NOT_SET = "type_not_set"
NO_SALES_ORDER = "no_sales_order"

#: The sales types, in block order. With every one ticked the blocks add up to all sales.
SALES_TYPES: Tuple[Tuple[str, str], ...] = (
    (DEALER, "Dealer"),
    (PROJECT, "Project team"),
    (OTHER, "Other"),
    (SET_APART, "Set apart"),
    (MIXED, "Mixed sales order types"),
    (TYPE_NOT_SET, "Sales order type not set"),
    (NO_SALES_ORDER, "No sales order"),
)
SALES_TYPE_LABELS = dict(SALES_TYPES)

#: A sales order's `demand_class` -> the sales type it gives an invoice.
_CLASS_TYPES = {"retail": DEALER, "project": PROJECT, "other": OTHER}

#: The words the order-based callers use for a channel, read as the sales type they mean.
CHANNEL_ALIASES = {"retail": DEALER, "dealer": DEALER, "project": PROJECT}
# (`other` is its own value in both vocabularies.)


# ------------------------------------------------------------------------------ the figure


def posted() -> Any:
    """A document that counts: posted (not cancelled) and one of the four sales types."""
    return sa.and_(
        BillingDocument.status == POSTED,
        BillingDocument.document_type.in_(DOCUMENT_TYPES),
    )


def _sign(value: Any) -> Any:
    return sa.case((BillingDocument.document_type == CREDIT_NOTE, -value), else_=value)


def signed_amount() -> Any:
    """The document's sales value in RM: `local_net_total`, negative on a credit note."""
    return _sign(BillingDocument.local_net_total)


def signed_line_amount() -> Any:
    """A line's sales value in RM: net of tax times the document's rate (a line carries no
    local amount), negative on a credit note."""
    return _sign(BillingDocumentLine.net_amount * BillingDocument.currency_rate)


def signed_line_quantity() -> Any:
    """A line's quantity, negative on a credit note."""
    return _sign(BillingDocumentLine.quantity)


# ------------------------------------------------------------------------- who and what


def _agent_source() -> Any:
    company = aliased(Company)
    return (
        sa.select(company.sales_agent_source)
        .where(company.id == BillingDocument.company_id)
        .correlate(BillingDocument).scalar_subquery()
    )


def agent_id() -> Any:
    """The agent a sale belongs to: the document's own, or the customer's current agent when
    the document's company says so (`companies.sales_agent_source`, plan 2.2)."""
    customer = aliased(Customer)
    customer_agent = (
        sa.select(customer.sales_agent_id)
        .where(customer.id == BillingDocument.customer_id)
        .correlate(BillingDocument).scalar_subquery()
    )
    return sa.case(
        (_agent_source() == AGENT_FROM_CUSTOMER, customer_agent),
        else_=BillingDocument.sales_agent_id,
    )


def agent_label() -> Any:
    """The agent's code; on the document setting an unresolved code shows as AutoCount sent it;
    NULL (the pivot's blank) when there is none."""
    agent = aliased(SalesAgent)
    code = sa.select(agent.sales_agent).where(agent.id == agent_id()).correlate(BillingDocument).scalar_subquery()
    as_sent = sa.case(
        (_agent_source() == AGENT_FROM_CUSTOMER, sa.null()),
        else_=sa.func.nullif(sa.func.btrim(BillingDocument.agent_code), ""),
    )
    return sa.func.coalesce(code, as_sent)


def uuid_values(values: List[str], name: str) -> List[str]:
    """`values` when every one is a UUID, else 422 (never a 500 from the uuid cast)."""
    import uuid as _uuid

    for value in values:
        try:
            _uuid.UUID(str(value))
        except ValueError:
            raise AppException(
                status_code=422, message=f"'{name}' takes ids", code="REPORT_INVALID_PARAMS"
            )
    return list(values)


def agent_condition(values: List[str]) -> Any:
    """The sale's agent among `values` (agent ids); `none` means a sale with no agent."""
    ids = uuid_values([v for v in values if v != "none"], "agent")
    parts = [agent_id().in_(ids)] if ids else []
    if "none" in values:
        parts.append(agent_id().is_(None))
    return sa.or_(*parts) if parts else sa.false()


def debtor_type() -> Any:
    """The customer's AutoCount debtor type, as stored now (owner ruling Q2 (a)); NULL when none."""
    customer = aliased(Customer)
    return (
        sa.select(customer.autocount_debtor_type)
        .where(customer.id == BillingDocument.customer_id)
        .correlate(BillingDocument).scalar_subquery()
    )


# --------------------------------------------------------------------- the sales order chain


def _traced_sales_order_ids(document_id: Any, company_id: Any) -> Any:
    """SELECT of the ids of the sales orders the billing document `document_id` traces to by its
    own lines, matched on `company_id` (DOC-RELATIONS' rules; see the module docstring)."""
    line = aliased(BillingDocumentLine)
    so_line = aliased(SalesOrderLine)
    so = aliased(SalesOrder)
    do = aliased(Order)
    do_line = aliased(OrderLine)
    do_so_line = aliased(SalesOrderLine)
    do_so = aliased(SalesOrder)

    via_line = (
        sa.select(so_line.sales_order_id)
        .join(line, line.sales_order_line_id == so_line.id)
        .where(line.document_id == document_id)
    )
    via_so_number = (
        sa.select(so.id)
        .join(line, sa.and_(line.from_doc_type == "SO", line.from_doc_no == so.so_number))
        .where(line.document_id == document_id, so.company_id == company_id)
    )
    # A DO named by number (not deleted; a cancelled DO still links on this side, as
    # `relations_for_billing_document` resolves it), then that DO's own sales orders.
    do_ids = (
        sa.select(do.id)
        .correlate(BillingDocument)
        .join(line, sa.and_(line.from_doc_type == "DO", line.from_doc_no == do.order_number))
        .where(
            line.document_id == document_id,
            do.company_id == company_id,
            do.deleted_at.is_(None),
        )
    )
    via_do_line = (
        sa.select(do_so_line.sales_order_id)
        .join(do_line, do_line.sales_order_line_id == do_so_line.id)
        .where(do_line.order_id.in_(do_ids))
    )
    via_do_number = (
        sa.select(do_so.id)
        .join(
            do_line,
            sa.and_(
                do_line.from_doc_no == do_so.so_number,
                sa.or_(do_line.from_doc_type.is_(None), do_line.from_doc_type == "SO"),
            ),
        )
        .where(do_line.order_id.in_(do_ids), do_so.company_id == company_id)
    )
    via_do_header = sa.select(do.sales_order_id).where(
        do.id.in_(do_ids), do.sales_order_id.isnot(None)
    )
    return sa.union(
        *(
            part.correlate(BillingDocument)
            for part in (via_line, via_so_number, via_do_line, via_do_number, via_do_header)
        )
    )


def _sales_order_class_kind(in_traced: Any) -> Any:
    """The sales type the traced sales orders give (`in_traced(so_id_column)` says which):
    none -> no sales order; two or more classes -> mixed; no class at all -> type not set;
    else the one class's type."""
    so = aliased(SalesOrder)
    classes = sa.func.count(sa.distinct(so.demand_class))
    one = sa.func.max(so.demand_class)
    return (
        sa.select(
            sa.case(
                (sa.func.count(so.id) == 0, sa.literal(NO_SALES_ORDER)),
                (classes > 1, sa.literal(MIXED)),
                (classes == 0, sa.literal(TYPE_NOT_SET)),
                *[(one == cls, sa.literal(kind)) for cls, kind in _CLASS_TYPES.items()],
                else_=sa.literal(TYPE_NOT_SET),
            )
        )
        .where(in_traced(so.id))
        .correlate(BillingDocument).scalar_subquery()
    )


def in_traced_sales_orders(so_id: Any) -> Any:
    """`so_id` is one of the sales orders this document's figures follow: its own traced
    orders, else (a credit or debit note with no traced line) its invoice's."""
    own = _traced_sales_order_ids(BillingDocument.id, BillingDocument.company_id)
    has_own = (
        sa.select(sa.func.count()).select_from(own.subquery("own_ids")).correlate(BillingDocument).scalar_subquery() > 0
    )
    inherited = _traced_sales_order_ids(
        BillingDocument.against_document_id, BillingDocument.company_id
    )
    return sa.or_(
        so_id.in_(own),
        sa.and_(BillingDocument.against_document_id.isnot(None), ~has_own, so_id.in_(inherited)),
    )


def _set_apart() -> Any:
    row = aliased(SetApartCustomer)
    month = sa.cast(sa.func.date_trunc("month", BillingDocument.doc_date), sa.Date)
    return sa.exists(
        sa.select(row.id).where(
            row.company_id == BillingDocument.company_id,
            row.customer_id == BillingDocument.customer_id,
            row.from_month <= month,
            sa.or_(row.to_month.is_(None), row.to_month >= month),
        ).correlate(BillingDocument)
    )


def sales_type() -> Any:
    """The document's sales type value (`SALES_TYPES`), first match wins: set apart, then the
    traced sales orders' class, then no sales order."""
    return sa.case(
        (_set_apart(), sa.literal(SET_APART)),
        else_=_sales_order_class_kind(in_traced_sales_orders),
    )


def sales_type_label() -> Any:
    value = sales_type()
    return sa.case(
        *[(value == key, sa.literal(label)) for key, label in SALES_TYPES],
        else_=sa.null(),
    )


def normalise_sales_types(values: List[str]) -> List[str]:
    """The sales type values a caller named, the order bases' words (`retail`, `dealer`) read as
    the type they mean; an unknown word is 422."""
    out: List[str] = []
    for raw in values:
        value = CHANNEL_ALIASES.get(raw, raw)
        if value not in SALES_TYPE_LABELS:
            raise AppException(
                status_code=422,
                message=f"Unknown channel '{raw}'",
                code="REPORT_INVALID_PARAMS",
            )
        out.append(value)
    return out


def sales_type_filter(values: List[str]) -> Optional[Any]:
    return sales_type().in_(normalise_sales_types(values))


# ------------------------------------------------------------------------ access

#: Invoiced figures are finance data: the reports read them under this slug, and so must every
#: route that answers them (security review M1: the order routes are gated on orders.view).
INVOICED_SLUG = "sales.reports.view"


def require_invoiced_access(db: Any, current_user: dict) -> None:
    """403 unless the caller (a user, or an API key's act-as user) holds `sales.reports.view`."""
    from app.services.user_service import holds_permission

    # The route dependencies' own check (superadmin and admin pass), so the rule is one rule.
    if not holds_permission(db, current_user, INVOICED_SLUG):
        raise AppException(
            status_code=403,
            message="Invoiced sales need the sales reports permission; ask delivered or ordered sales",
            code="invoiced_needs_sales_reports",
        )


#: Unpaid invoices are receivables: finance data, read under the billing documents' own slug everywhere else
#: (`api/v1/finance/billing_documents`, `OUTSTANDING_VIEW_SLUG`).
UNPAID_SLUG = "finance.billing_documents.view"


def require_unpaid_access(db: Any, current_user: dict) -> None:
    """The chatbot route's unpaid gate on the act-as user (superadmin and admin pass). The contact's Outstanding reveal
    is checked separately, next to the other outstanding kinds."""
    from app.services.user_service import holds_permission

    if not holds_permission(db, current_user, UNPAID_SLUG):
        raise AppException(
            status_code=403,
            message="Unpaid invoices need the finance billing documents permission",
            code="unpaid_needs_finance_view",
        )


# ------------------------------------------------------------------------ entry points


def quantity_by_product_month(
    db: Any,
    since: Any,
    until: Any,
    product_ids: Optional[List[str]] = None,
    *,
    company_ids: Optional[List[str]] = None,
) -> List[Tuple[str, str, Any]]:
    """`(product_id, 'YYYY-MM', signed quantity)` over posted invoice, cash sale, debit note and
    credit note lines (a credit note negative), `since <= doc_date < until`, lines with a
    product only, in the session's company scope; `product_ids` None = every product. Every
    sales type counts. The stock position report's Monthly sales and Highest per month read
    this (STOCK-POSITION-REPORT #1913, owner ruling 27 Oct: one shared sales function).

    The companies are explicit: `company_ids`, else the session's company scope, and an
    unrestricted or unset scope is refused rather than summing every company (security
    review L6)."""
    from app.models.base import get_company_scope

    if company_ids is None:
        scope = get_company_scope(db)
        if not isinstance(scope, frozenset):
            raise AppException(
                status_code=500,
                message="quantity_by_product_month needs a company",
                code="company_required",
            )
        company_ids = sorted(scope)
    month = sa.func.to_char(BillingDocument.doc_date, "YYYY-MM")
    q = (
        sa.select(
            BillingDocumentLine.product_id,
            month.label("month"),
            sa.func.sum(signed_line_quantity()).label("quantity"),
        )
        .join(BillingDocument, BillingDocument.id == BillingDocumentLine.document_id)
        .where(
            posted(),
            BillingDocumentLine.product_id.isnot(None),
            BillingDocument.doc_date >= since,
            BillingDocument.doc_date < until,
            BillingDocument.company_id.in_(list(company_ids)),
        )
        .group_by(BillingDocumentLine.product_id, month)
        .order_by(BillingDocumentLine.product_id, month)
    )
    if product_ids is not None:
        if not product_ids:
            return []
        q = q.where(BillingDocumentLine.product_id.in_(product_ids))
    return [(str(p), str(m), qty) for p, m, qty in db.execute(q).all()]
