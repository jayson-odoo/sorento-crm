"""Customer select endpoint for dropdowns."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.models.base import get_company_scope
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.services.error_handler import handle_internal_error
from app.services.scm import sales_agent_service

router = APIRouter()

#: The largest page a caller may ask for, matching `master_data/products_select.py`.
MAX_LIMIT = 200


@router.get("/select")
async def get_customers_select(
    query: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Customers for a dropdown, SEARCHABLE AND PAGEABLE on the server.

    This used to return every active customer as a whole ORM row - 6,397 of them on the
    client's database - on every open of every customer select in the product. The
    sales-order detail page is where it finally showed: seconds to open a dropdown, because
    the browser was being handed the entire debtor master to filter locally.

    **`limit` has no default, deliberately.** `products_select.py` could default to 100
    because that is exactly what it already returned unconditionally; this endpoint already
    returned EVERYTHING, so a default of 50 here would silently make the 51st customer
    unreachable in the two callers that hold the whole array and filter it in the browser
    (`use-customer-select-query`, `scmOptionsService.getCustomerOptions`). Omitted means
    what it has always meant; a caller that wants paging asks for it.

    Ordered by code so paging is stable: without an ORDER BY, two pages of the same result
    set can repeat or skip rows.

    Fields are listed explicitly rather than dumping the ORM row - the raw row carries
    credit limits and payment terms, and a dropdown is not the place to decide who may see a
    customer's credit.
    """
    try:
        q = db.query(Customer).filter(Customer.is_active == True)  # noqa: E712

        if query:
            needle = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Customer.customer_code.ilike(needle),
                    Customer.customer_name.ilike(needle),
                )
            )

        q = q.order_by(Customer.customer_code).offset(offset)
        if limit is not None:
            q = q.limit(limit)
        customers = q.all()

        return {
            "data": [
                {
                    "id": c.id,
                    "customer_code": c.customer_code,
                    "customer_name": c.customer_name,
                    "market_segment_code": c.market_segment_code,
                }
                for c in customers
            ],
            # `total` is the size of THIS page, as it always has been - a true count would
            # be a second full scan on every keystroke, and no caller reads it.
            "pagination": {
                "total": len(customers),
                "page": (offset // limit) + 1 if limit else 1,
                "limit": limit,
                "offset": offset,
            },
            "empty": len(customers) == 0
        }
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/sales-agents-select")
async def get_customer_sales_agents_select(
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sales agents for the customer form's "Sales agent" select, code + name, unscoped by
    page (~38 active rows today, comfortably below one).

    Served here rather than the sales-agents master's own list (`master_data.sales_agents.
    view`) or the SCM one (`scm.dashboard.view`): a role that may edit a customer does not
    necessarily hold either, the same reasoning `/scm/sales-orders/agents` already states for
    itself. `query` matches the code OR the annotated person, since a customer edit picks the
    agent by whichever one is remembered.
    """
    try:
        q = db.query(SalesAgent).filter(SalesAgent.is_active.is_(True))
        scope_pred = sales_agent_service.scope_filter(get_company_scope(db))
        if scope_pred is not None:
            q = q.filter(scope_pred)
        if query:
            needle = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    SalesAgent.sales_agent.ilike(needle),
                    SalesAgent.person_label.ilike(needle),
                )
            )
        agents = q.order_by(SalesAgent.sales_agent.asc()).all()
        return {
            "data": [
                {"id": a.id, "sales_agent": a.sales_agent, "person_label": a.person_label}
                for a in agents
            ],
        }
    except Exception as e:
        raise handle_internal_error(str(e))
