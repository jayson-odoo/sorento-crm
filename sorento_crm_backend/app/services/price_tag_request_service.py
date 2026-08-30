"""Price tag request service: doc-number generation, creation, status transitions.

The status graph:

    new -> designing -> proof_ready -> approved -> ready
                  ^                |
                  |                v
                  +-- changes_requested
    * -> rejected
    * -> void

``void`` and ``rejected`` are reachable from any non-terminal status.
``ready`` is terminal - once exported, no further transitions.
"""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.price_tag import PriceTagRequest, PriceTagRequestLine
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

# Status constants.
STATUS_NEW = "new"
STATUS_DESIGNING = "designing"
STATUS_PROOF_READY = "proof_ready"
STATUS_CHANGES_REQUESTED = "changes_requested"
STATUS_APPROVED = "approved"
STATUS_READY = "ready"
STATUS_REJECTED = "rejected"
STATUS_VOID = "void"

_TERMINAL = frozenset({STATUS_READY, STATUS_REJECTED, STATUS_VOID})

# Valid transitions: current_status -> set of allowed next statuses.
# ``rejected`` and ``void`` are reachable from any non-terminal status.
VALID_TRANSITIONS: dict[str, set[str]] = {
    STATUS_NEW: {STATUS_DESIGNING, STATUS_REJECTED, STATUS_VOID},
    STATUS_DESIGNING: {
        STATUS_PROOF_READY,
        STATUS_REJECTED,
        STATUS_VOID,
    },
    STATUS_PROOF_READY: {
        STATUS_APPROVED,
        STATUS_CHANGES_REQUESTED,
        STATUS_REJECTED,
        STATUS_VOID,
    },
    STATUS_CHANGES_REQUESTED: {
        STATUS_DESIGNING,
        STATUS_REJECTED,
        STATUS_VOID,
    },
    STATUS_APPROVED: {STATUS_READY, STATUS_REJECTED, STATUS_VOID},
    # Terminal statuses have no outgoing edges.
    STATUS_READY: set(),
    STATUS_REJECTED: set(),
    STATUS_VOID: set(),
}

# The product class label that triggers the set guard. A product with this
# class cannot be submitted ala carte - it must come as a product_set line.
_BATHROOM_FURNITURE_CLASS = "Bathroom Furniture"


class PriceTagRequestService:
    """Stateless helpers for price tag requests."""

    @staticmethod
    def generate_doc_number(db: Session, company_id: str) -> str:
        """Generate ``PT-YYYYMM-NNNN`` (zero-padded 4-digit per month per company).

        The sequence is derived from the count of existing requests for the same
        company in the current month. This is safe under normal concurrency
        because the unique constraint on ``doc_number`` will reject a duplicate,
        and the caller retries.
        """
        now = datetime.utcnow()
        prefix = f"PT-{now.strftime('%Y%m')}-"
        count = (
            db.query(func.count(PriceTagRequest.id))
            .filter(
                PriceTagRequest.company_id == company_id,
                PriceTagRequest.doc_number.like(f"{prefix}%"),
            )
            .scalar()
        ) or 0
        seq = count + 1
        return f"{prefix}{seq:04d}"

    @staticmethod
    def create_request(
        db: Session,
        contact_id: str,
        company_id: str,
        data: dict,
    ) -> PriceTagRequest:
        """Create a price tag request with its lines.

        ``data`` keys: debtor_code, debtor_name, promotion_id, needed_by_date,
        notes, lines (list of line dicts).

        Sets ``portal_draft_at`` on creation (the request starts as a draft).
        """
        doc_number = PriceTagRequestService.generate_doc_number(db, company_id)

        request = PriceTagRequest(
            contact_id=contact_id,
            company_id=company_id,
            debtor_code=data.get("debtor_code"),
            debtor_name=data["debtor_name"],
            promotion_id=data.get("promotion_id"),
            needed_by_date=data["needed_by_date"],
            notes=data.get("notes"),
            doc_number=doc_number,
            portal_draft_at=datetime.utcnow(),
        )
        db.add(request)
        db.flush()  # get the id

        for idx, line_data in enumerate(data.get("lines", [])):
            line = PriceTagRequestLine(
                request_id=request.id,
                line_type=line_data["line_type"],
                product_id=line_data.get("product_id"),
                product_set_id=line_data.get("product_set_id"),
                show_promo_price=line_data.get("show_promo_price", True),
                quantity=line_data.get("quantity", 1),
                alternatives=line_data.get("alternatives", []),
                included_accessories=line_data.get("included_accessories"),
                sort_order=line_data.get("sort_order", idx),
            )
            db.add(line)

        db.flush()
        return request

    @staticmethod
    def submit_request(
        db: Session,
        contact_id: str,
        company_id: str,
        data: dict,
    ) -> PriceTagRequest:
        """Create and validate a price tag request for submission.

        Runs the set guard on submit: products with class ``Bathroom Furniture``
        cannot be submitted ala carte (must come as a product_set line).
        Raises ``AppException`` (422) on guard violation.
        """
        from app.models.product import Product, ProductCategory

        lines = data.get("lines", [])
        # Validate set guard for product lines with Bathroom Furniture class.
        for line_data in lines:
            if line_data.get("line_type") != "product":
                continue
            product_id = line_data.get("product_id")
            if not product_id:
                continue
            product = (
                db.query(Product)
                .filter(Product.id == product_id)
                .first()
            )
            if not product:
                continue
            category = (
                db.query(ProductCategory)
                .filter(ProductCategory.id == product.category_id)
                .first()
            )
            if category and category.class_label == _BATHROOM_FURNITURE_CLASS:
                raise AppException(
                    status_code=422,
                    message=(
                        f"Product '{product.product_code}' is classified as "
                        f"'{_BATHROOM_FURNITURE_CLASS}' and cannot be submitted "
                        f"as an individual product. Please submit it as part of "
                        f"a product set."
                    ),
                    code="SET_GUARD_VIOLATION",
                )

        request = PriceTagRequestService.create_request(
            db, contact_id, company_id, data
        )
        # Clear the draft timestamp to indicate submission.
        request.portal_draft_at = None
        db.flush()
        return request

    @staticmethod
    def transition_status(
        db: Session,
        request_id: str,
        new_status: str,
        user_id: str | None = None,
    ) -> PriceTagRequest:
        """Validate and apply a status transition.

        Raises ``AppException`` (409) for invalid transitions.
        """
        request = db.query(PriceTagRequest).filter(
            PriceTagRequest.id == request_id,
        ).first()
        if not request:
            raise AppException(
                status_code=404,
                message=f"Price tag request {request_id} not found.",
                code="NOT_FOUND",
            )

        current = request.status
        allowed = VALID_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise AppException(
                status_code=409,
                message=(
                    f"Cannot transition from '{current}' to '{new_status}'. "
                    f"Allowed: {sorted(allowed) if allowed else 'none (terminal)'}."
                ),
                code="INVALID_TRANSITION",
            )

        request.status = new_status
        db.flush()
        return request

    @staticmethod
    def validate_set_guard(db: Session, request: PriceTagRequest) -> None:
        """Validate the set guard on an existing request's lines.

        Products with class ``Bathroom Furniture`` cannot be submitted ala carte.
        Raises ``AppException`` (422) on violation.
        """
        from app.models.product import Product, ProductCategory

        for line in request.lines:
            if line.line_type != "product":
                continue
            if not line.product_id:
                continue
            product = db.query(Product).filter(Product.id == line.product_id).first()
            if not product:
                continue
            category = (
                db.query(ProductCategory)
                .filter(ProductCategory.id == product.category_id)
                .first()
            )
            if category and category.class_label == _BATHROOM_FURNITURE_CLASS:
                raise AppException(
                    status_code=422,
                    message=(
                        f"Product '{product.product_code}' is classified as "
                        f"'{_BATHROOM_FURNITURE_CLASS}' and cannot be submitted "
                        f"as an individual product. Please submit it as part of "
                        f"a product set."
                    ),
                    code="SET_GUARD_VIOLATION",
                )

    @staticmethod
    def get_request(db: Session, request_id: str) -> PriceTagRequest | None:
        """Fetch a single request by id, eagerly loading lines."""
        return (
            db.query(PriceTagRequest)
            .filter(PriceTagRequest.id == request_id)
            .first()
        )

    @staticmethod
    def list_requests(
        db: Session,
        *,
        contact_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[PriceTagRequest]:
        """List requests, optionally filtered by contact_id, status, or search."""
        q = db.query(PriceTagRequest)
        if contact_id:
            q = q.filter(PriceTagRequest.contact_id == contact_id)
        if status:
            q = q.filter(PriceTagRequest.status == status)
        if search:
            like = f"%{search}%"
            q = q.filter(
                or_(
                    PriceTagRequest.doc_number.ilike(like),
                    PriceTagRequest.debtor_name.ilike(like),
                )
            )
        return q.order_by(PriceTagRequest.created_at.desc()).all()

    @staticmethod
    def lookup_tag_items(
        db: Session,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Sets and products in ONE list, for the lines table's single Item picker.

        A dealer does not know whether a thing is a set or a product, so the form
        stopped asking (D47) and this is what the one dropdown reads. Each row carries
        the REAL `product_sets.id` / `products.id`, because that is what a line's
        foreign key stores; the portal's generic product lookup answers with a code and
        no id at all, which is why a product line could never be saved.

        Sets come first, then products, each ordered by code and each capped at `limit`
        (so at most `2 * limit` rows reach the picker). Sets lead because they are far
        fewer and are the thing a salesperson is likeliest to miss.

        The catalogue search itself is `tag_data_service`'s, the same one the marketing
        canvas uses, so the portal and the editor cannot disagree about what exists.
        """
        from app.services.dealer_kit import tag_data_service

        items: list[dict] = [
            {
                "kind": "product_set",
                "id": str(row.id),
                "code": row.set_code,
                "name": row.name or "",
            }
            for row in tag_data_service.search_product_sets(db, query, limit=limit)
        ]
        items.extend(
            {
                "kind": "product",
                "id": str(row.id),
                "code": row.product_code,
                "name": row.product_name or "",
            }
            for row in tag_data_service.search_products(db, query, limit=limit)
        )
        return items

    @staticmethod
    def lookup_debtors_for_agent(
        db: Session,
        contact_id: str,
    ) -> list[dict]:
        """Scoped debtor lookup for a portal contact.

        Returns customers assigned to the contact's linked SalesAgent, plus
        distinct debtors from orders for that agent within the last 24 months.
        Returns an empty list if the contact has no linked agent.
        """
        from app.models.order import Customer, Order
        from app.models.sales_agent import SalesAgent

        # Find the SalesAgent linked to this contact.
        agent = (
            db.query(SalesAgent)
            .filter(SalesAgent.contact_id == contact_id)
            .first()
        )
        if not agent:
            return []

        debtors: dict[str, dict] = {}

        # Source 1: customers assigned to this agent (customers.sales_agent_id).
        customers = (
            db.query(Customer)
            .filter(Customer.sales_agent_id == agent.id)
            .all()
        )
        for c in customers:
            key = c.customer_code or c.id
            debtors[key] = {
                "customer_id": c.id,
                "customer_code": c.customer_code,
                "customer_name": c.customer_name,
                "debtor_code": c.customer_code,
                "debtor_name": c.customer_name,
                "source": "customer",
            }

        # Source 2: debtors from orders for this agent within last 24 months.
        cutoff = date.today() - timedelta(days=730)  # ~24 months
        orders = (
            db.query(Order.debtor_code, Order.debtor_name)
            .filter(
                Order.agent == agent.sales_agent,
                Order.order_date >= cutoff,
                Order.debtor_code.isnot(None),
            )
            .distinct()
            .all()
        )
        for debtor_code, debtor_name in orders:
            if debtor_code and debtor_code not in debtors:
                debtors[debtor_code] = {
                    "customer_id": None,
                    "customer_code": debtor_code,
                    "customer_name": debtor_name,
                    "debtor_code": debtor_code,
                    "debtor_name": debtor_name,
                    "source": "order",
                }

        return list(debtors.values())
