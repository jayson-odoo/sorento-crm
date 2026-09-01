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

from sqlalchemy import Integer, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import company_scope
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

# How many times a create re-derives its number after losing an insert race
# before it gives up. Five is far past what a human-paced portal ever needs; the
# point is that the loop terminates rather than spins.
_DOC_NUMBER_ATTEMPTS = 5

# The product class label that triggers the set guard. A product with this
# class cannot be submitted ala carte - it must come as a product_set line.
_BATHROOM_FURNITURE_CLASS = "Bathroom Furniture"


class PriceTagRequestService:
    """Stateless helpers for price tag requests."""

    @staticmethod
    def generate_doc_number(db: Session, company_id: str) -> str:
        """``PT-YYYYMM-NNNN``: the month's HIGHEST sequence so far, plus one.

        Two things about ``doc_number`` decide this, and neither is negotiable:
        it is UNIQUE across the whole table, and a draft HARD-deletes (D48b).

        A sequence derived from a COUNT of the surviving rows therefore re-issues
        a number that a deleted draft already spent, and the next create died on
        ``price_tag_requests_doc_number_key`` with a 500 - the salesperson's Save
        Draft simply stopped working after any delete. A COUNT scoped to one
        company had the same fault across companies: the constraint is global, so
        the sequence has to be global too.

        MAX over the four-digit suffix answers both. It is read with the company
        scope OFF for the same reason: the numbering space is the table, not the
        partition, and a scoped read would hand the next company a number that is
        already taken. Nothing but the number is read.

        ``company_id`` stays in the signature because the caller has it and a
        future per-company prefix would need it; it does not narrow the sequence.
        """
        now = datetime.utcnow()
        prefix = f"PT-{now.strftime('%Y%m')}-"
        with company_scope(db, None):
            highest = (
                db.query(
                    func.max(
                        cast(
                            func.substr(PriceTagRequest.doc_number, len(prefix) + 1),
                            Integer,
                        )
                    )
                )
                .filter(PriceTagRequest.doc_number.like(f"{prefix}%"))
                .scalar()
            ) or 0
        return f"{prefix}{int(highest) + 1:04d}"

    @staticmethod
    def create_request(
        db: Session,
        contact_id: str,
        company_id: str,
        data: dict,
    ) -> PriceTagRequest:
        """Create a price tag request with its lines.

        ``data`` keys: debtor_code, debtor_name, promotion_id, needed_by_date,
        notes, lines (list of line dicts). EVERY one of them is optional (D48a):
        Save Draft validates nothing, so a form with one line and no dealer is a
        request this has to be able to store. Completeness is checked on submit by
        ``validate_submittable``.

        Sets ``portal_draft_at`` on creation (the request starts as a draft).
        """
        request = PriceTagRequestService._insert_with_doc_number(
            db,
            lambda doc_number: PriceTagRequest(
                contact_id=contact_id,
                company_id=company_id,
                debtor_code=data.get("debtor_code"),
                debtor_name=data.get("debtor_name"),
                promotion_id=data.get("promotion_id"),
                needed_by_date=data.get("needed_by_date"),
                notes=data.get("notes"),
                doc_number=doc_number,
                portal_draft_at=datetime.utcnow(),
            ),
            company_id,
        )

        PriceTagRequestService._add_lines(db, request, data.get("lines") or [])
        db.flush()
        return request

    @staticmethod
    def _insert_with_doc_number(db: Session, build, company_id: str) -> PriceTagRequest:
        """Insert a request, taking the next number if another writer took ours.

        The MAX in ``generate_doc_number`` closes the gap a delete leaves, but two
        creates in flight still read the same MAX, and the loser used to get a 500
        instead of the next number. Each attempt runs inside a SAVEPOINT so a
        unique violation costs the attempt and not the whole transaction, which by
        then holds the caller's other work.
        """
        for attempt in range(_DOC_NUMBER_ATTEMPTS):
            request = build(PriceTagRequestService.generate_doc_number(db, company_id))
            db.add(request)
            savepoint = db.begin_nested()
            try:
                db.flush()  # get the id, and find out about a collision here
                savepoint.commit()
                return request
            except IntegrityError:
                savepoint.rollback()
                logger.warning(
                    "Price tag doc number %s was taken while creating; retrying "
                    "(attempt %s of %s).",
                    request.doc_number,
                    attempt + 1,
                    _DOC_NUMBER_ATTEMPTS,
                )
        raise AppException(
            status_code=409,
            message=(
                "Could not allocate a document number for this request. "
                "Please try again."
            ),
            code="DOC_NUMBER_UNAVAILABLE",
        )

    @staticmethod
    def _add_lines(db: Session, request: PriceTagRequest, lines: list[dict]) -> None:
        """Append lines in the order given, which is the order the form shows."""
        for idx, line_data in enumerate(lines):
            sort_order = line_data.get("sort_order")
            db.add(
                PriceTagRequestLine(
                    request_id=request.id,
                    line_type=line_data["line_type"],
                    product_id=line_data.get("product_id"),
                    product_set_id=line_data.get("product_set_id"),
                    show_promo_price=line_data.get("show_promo_price", True),
                    quantity=line_data.get("quantity", 1),
                    alternatives=line_data.get("alternatives", []),
                    included_accessories=line_data.get("included_accessories"),
                    sort_order=idx if sort_order is None else sort_order,
                )
            )

    @staticmethod
    def replace_lines(db: Session, request: PriceTagRequest, lines: list[dict]) -> None:
        """Swap a draft's lines for the ones the form just posted.

        A re-save sends the whole table, not a diff: the rows are unsaved form
        state on the client and carry no stable identity there. Deleting through
        the relationship keeps ``delete-orphan`` in charge, so nothing is left
        pointing at the request.
        """
        request.lines.clear()
        db.flush()
        PriceTagRequestService._add_lines(db, request, lines)
        db.flush()

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
        offenders: list[tuple[int, str]] = []
        for index, line_data in enumerate(data.get("lines") or []):
            code = PriceTagRequestService._ala_carte_offender(
                db, line_data.get("line_type"), line_data.get("product_id")
            )
            if code:
                offenders.append((index, code))
        if offenders:
            raise PriceTagRequestService._set_guard_refusal(offenders)

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
    def validate_submittable(request: PriceTagRequest) -> None:
        """What a request needs before it may be submitted (D48a).

        A draft can be sloppy; a submitted request cannot. Every missing field is
        named at once, in ``detail`` as a comma-separated list of keys the form
        knows how to place, so the portal can put each message under the field it
        belongs to instead of showing one sentence in a toast.

        A line with neither a product nor a set cannot exist here: the table's
        ``ck_price_tag_request_lines_one_ref`` refuses it on insert. The form
        catches that one on the client, where the empty row actually is.
        """
        missing: list[tuple[str, str]] = []
        if not (request.debtor_name or "").strip():
            missing.append(("debtor_name", "a dealer"))
        if request.needed_by_date is None:
            missing.append(("needed_by_date", "a needed by date"))
        if not request.lines:
            missing.append(("lines", "at least one line"))
        if not missing:
            return

        labels = [label for _, label in missing]
        wanted = (
            labels[0]
            if len(labels) == 1
            else ", ".join(labels[:-1]) + " and " + labels[-1]
        )
        raise AppException(
            status_code=422,
            message=f"This request needs {wanted} before it can be submitted.",
            detail=",".join(key for key, _ in missing),
            code="SUBMIT_INCOMPLETE",
        )

    @staticmethod
    def validate_claimable(request: PriceTagRequest) -> None:
        """What a request needs before marketing may claim it.

        A draft is refused FIRST and by its own code: it is still the
        salesperson's, and the status it carries (``new``) is the same one a
        submitted request carries, so the status check alone waved it through.
        Claiming one moved it to ``designing``, and the salesperson's later
        Submit reset it to ``new`` - the claim gone, the SLA fired twice, and a
        designer working on something nobody had sent them.
        """
        if request.portal_draft_at is not None:
            raise AppException(
                status_code=409,
                message=(
                    "This request is still a draft on the salesperson's side and "
                    "has not been submitted yet."
                ),
                code="NOT_SUBMITTED",
            )
        if request.status != STATUS_NEW:
            raise AppException(
                status_code=409,
                message="Only requests in 'new' status can be claimed.",
                code="INVALID_STATE",
            )

    @staticmethod
    def validate_set_guard(db: Session, request: PriceTagRequest) -> None:
        """Validate the set guard on an existing request's lines.

        Products with class ``Bathroom Furniture`` cannot be submitted ala carte.
        Raises ``AppException`` (422) on violation, naming EVERY line it refused:
        the message belongs on the row, and a refusal that named only the first
        offender would send the salesperson round the loop once per bad line.
        """
        offenders: list[tuple[int, str]] = []
        for index, line in enumerate(request.lines):
            code = PriceTagRequestService._ala_carte_offender(
                db, line.line_type, line.product_id
            )
            if code:
                offenders.append((index, code))
        if offenders:
            raise PriceTagRequestService._set_guard_refusal(offenders)

    @staticmethod
    def _ala_carte_offender(
        db: Session, line_type: str | None, product_id: str | None
    ) -> str | None:
        """The product code, if this line is a Bathroom Furniture product on its own."""
        from app.models.product import Product, ProductCategory

        if line_type != "product" or not product_id:
            return None
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return None
        category = (
            db.query(ProductCategory)
            .filter(ProductCategory.id == product.category_id)
            .first()
        )
        if category and category.class_label == _BATHROOM_FURNITURE_CLASS:
            return product.product_code
        return None

    @staticmethod
    def _set_guard_refusal(offenders: list[tuple[int, str]]) -> AppException:
        """One refusal for every ala carte line, addressed to the rows by position.

        ``detail`` is ``line:<sort_order>`` per offender, which is how the portal
        form finds the row to put the message on.
        """
        codes = ", ".join(f"'{code}'" for _, code in offenders)
        plural = "s" if len(offenders) > 1 else ""
        return AppException(
            status_code=422,
            message=(
                f"Product{plural} {codes} {'are' if plural else 'is'} classified as "
                f"'{_BATHROOM_FURNITURE_CLASS}' and cannot be submitted as an "
                f"individual product. Please submit as part of a product set."
            ),
            detail=",".join(f"line:{index}" for index, _ in offenders),
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
    def resolved_labels(
        db: Session, request_ids: list[str]
    ) -> dict[str, dict]:
        """The names and the line count behind a request's ids, per request id.

        A request row carries a contact id, a user id and a promotion id, and no
        screen may show a UUID. Two set-based queries answer for the whole page:
        asking per row would be four queries per row on a fifty-row listing.
        """
        if not request_ids:
            return {}

        from app.models.access import RespondContact
        from app.models.marketing import Promotion
        from app.models.user import User

        counts = dict(
            db.query(
                PriceTagRequestLine.request_id,
                func.count(PriceTagRequestLine.id),
            )
            .filter(PriceTagRequestLine.request_id.in_(request_ids))
            .group_by(PriceTagRequestLine.request_id)
            .all()
        )

        labels: dict[str, dict] = {}
        rows = (
            db.query(
                PriceTagRequest.id,
                RespondContact.name,
                User.name,
                Promotion.description,
            )
            .select_from(PriceTagRequest)
            .outerjoin(RespondContact, RespondContact.id == PriceTagRequest.contact_id)
            .outerjoin(User, User.id == PriceTagRequest.assigned_to_id)
            .outerjoin(Promotion, Promotion.id == PriceTagRequest.promotion_id)
            .filter(PriceTagRequest.id.in_(request_ids))
            .all()
        )
        for request_id, contact_name, assigned_to_name, promotion_name in rows:
            labels[request_id] = {
                "contact_name": contact_name,
                "assigned_to_name": assigned_to_name,
                "promotion_name": promotion_name,
                "line_count": int(counts.get(request_id, 0)),
            }
        return labels

    @staticmethod
    def list_items(db: Session, requests: list[PriceTagRequest]) -> list:
        """The listing rows the queue draws, names resolved."""
        from app.schemas.price_tag import PriceTagRequestListItem

        labels = PriceTagRequestService.resolved_labels(
            db, [request.id for request in requests]
        )
        items = []
        for request in requests:
            item = PriceTagRequestListItem.model_validate(request)
            for key, value in labels.get(request.id, {}).items():
                setattr(item, key, value)
            items.append(item)
        return items

    @staticmethod
    def response_with_resolved_lines(db: Session, request: PriceTagRequest):
        """The request, with each line carrying what a person can read off it.

        A line row holds a product id, a quantity and an override; the code, the
        name and both prices live in the product master and the pricing engine.
        Resolved through ``tag_data_service`` - the SAME call the designer and the
        print payload use - so no reader can quote a different price from the tag
        it is about to print.

        A line the resolver skipped (its product has been removed) keeps its blank
        defaults rather than vanishing: a request that silently lists fewer lines
        than were submitted is the worse failure.

        Lives here, not in a route module, because the CRM detail route and the
        portal detail route both answer with it (D49).
        """
        from app.schemas.price_tag import PriceTagRequestResponse
        from app.services.dealer_kit import tag_data_service

        response = PriceTagRequestResponse.model_validate(request)
        resolved = {
            row["line_id"]: row
            for row in tag_data_service.resolve_request_line_data(db, request)
        }
        for line in response.lines:
            row = resolved.get(line.id)
            if not row:
                continue
            line.code = row["code"]
            line.name = row["name"]
            # float() here rather than trusting the annotation: assigning to a
            # pydantic field does NOT validate, so a Decimal set on a `float` field
            # is serialised as a JSON STRING and the page's `.toFixed(2)` throws.
            line.list_price = None if row["list_price"] is None else float(row["list_price"])
            line.sell_price = None if row["sell_price"] is None else float(row["sell_price"])

        # The header's names, from the same resolver the listing uses so the two
        # screens cannot disagree about who claimed a request.
        for key, value in (
            PriceTagRequestService.resolved_labels(db, [request.id])
            .get(request.id, {})
            .items()
        ):
            setattr(response, key, value)
        return response

    @staticmethod
    def list_requests(
        db: Session,
        *,
        contact_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
        include_drafts: bool = True,
    ) -> list[PriceTagRequest]:
        """List requests, optionally filtered by contact_id, status, or search.

        ``include_drafts=False`` is what marketing's queue asks for. A portal
        draft carries status ``new`` exactly like a submitted request, so without
        this the CRM listing showed forms the salesperson was still typing and
        marketing could claim one. The portal's own list leaves it True: a draft
        is the whole point of that screen.
        """
        q = PriceTagRequestService._list_query(
            db,
            contact_id=contact_id,
            status=status,
            search=search,
            include_drafts=include_drafts,
        )
        return q.order_by(PriceTagRequest.created_at.desc()).all()

    @staticmethod
    def _list_query(
        db: Session,
        *,
        contact_id: str | None,
        status: str | None,
        search: str | None,
        include_drafts: bool,
    ):
        """The filtered query both the whole-list and the paged reads run."""
        q = db.query(PriceTagRequest)
        if contact_id:
            q = q.filter(PriceTagRequest.contact_id == contact_id)
        if not include_drafts:
            q = q.filter(PriceTagRequest.portal_draft_at.is_(None))
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
        return q

    # What the queue may sort by. Only real columns: the salesperson, the
    # assignee, the promotion and the line count are RESOLVED per page rather
    # than stored, so sorting on them would mean sorting something the query
    # cannot see. The listing does not offer those as sortable either.
    SORTABLE_COLUMNS = {
        "doc_number": PriceTagRequest.doc_number,
        "debtor_name": PriceTagRequest.debtor_name,
        "debtor_code": PriceTagRequest.debtor_code,
        "status": PriceTagRequest.status,
        "needed_by_date": PriceTagRequest.needed_by_date,
        "created_at": PriceTagRequest.created_at,
    }

    @staticmethod
    def list_page(
        db: Session,
        *,
        contact_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
        include_drafts: bool = True,
        page: int = 1,
        limit: int = 50,
        sort: str | None = None,
        direction: str = "asc",
    ) -> tuple[list[PriceTagRequest], int]:
        """One page of requests, and how many there are in total.

        The listing used to answer the WHOLE table and let the browser cut the
        page out of it: every keystroke shipped every request in the system, and
        the record count under the grid was the length of whatever array had
        arrived rather than what the table holds.
        """
        q = PriceTagRequestService._list_query(
            db,
            contact_id=contact_id,
            status=status,
            search=search,
            include_drafts=include_drafts,
        )
        total = q.order_by(None).count()

        column = PriceTagRequestService.SORTABLE_COLUMNS.get(sort or "")
        if column is None:
            # Newest first is the queue's own order, and it is what an unknown
            # or a resolved-only column falls back to rather than a 400 the
            # reader can do nothing about.
            ordering = [PriceTagRequest.created_at.desc()]
        else:
            ordering = [column.desc() if direction == "desc" else column.asc()]
        # Ends with the id, because created_at ties inside one transaction and a
        # tie makes page 2 repeat a row page 1 already showed.
        ordering.append(PriceTagRequest.id)

        rows = (
            q.order_by(*ordering)
            .offset(max(0, (page - 1) * limit))
            .limit(limit)
            .all()
        )
        return rows, total

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
    def lookup_promotions(db: Session, query: str | None = None) -> list[dict]:
        """Active-window promotions for the portal's promotion dropdown (S4, #477).

        Same rule ``resolve_prices``' ``_offer_prices`` already enforces when it
        prices a line against a promotion: switched-on (``is_active``) AND inside
        an inclusive ``[start_date, end_date]`` window, either end open. Company
        scoping is not written here on purpose - ``Promotion`` carries
        ``CompanyScopedMixin`` and the ordinary ORM scope filter already keeps
        another company's promotion off this list, the same way it already keeps
        it out of a price.
        """
        from app.models.marketing import Promotion
        from app.services.dealer_kit.pricing import business_today

        today = business_today()
        q = (
            db.query(Promotion)
            .filter(Promotion.is_active.is_(True))
            .filter(or_(Promotion.start_date.is_(None), Promotion.start_date <= today))
            .filter(or_(Promotion.end_date.is_(None), Promotion.end_date >= today))
        )
        if query:
            q = q.filter(Promotion.description.ilike(f"%{query}%"))
        rows = q.order_by(Promotion.description).all()
        return [{"id": row.id, "name": row.description or ""} for row in rows]

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

        # The SalesAgent linked to this contact. `sales_agents.contact_id` carries
        # no unique constraint, so an unordered `.first()` let Postgres return
        # either row: the same salesperson could open the form twice and be
        # offered two different debtor books with nothing on screen to explain
        # it. Ordered by the agent code and then the id, so the answer is the
        # same every time, and a second link is logged rather than hidden -
        # linking one contact to two agents is a data problem for a human, not
        # something to guess at here.
        agents = (
            db.query(SalesAgent)
            .filter(SalesAgent.contact_id == contact_id)
            .order_by(SalesAgent.sales_agent, SalesAgent.id)
            .all()
        )
        if not agents:
            return []
        agent = agents[0]
        if len(agents) > 1:
            logger.warning(
                "Portal contact %s is linked to %s sales agents; answering for "
                "%s. Only one link is meant to exist.",
                contact_id,
                len(agents),
                agent.sales_agent,
            )

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
