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
import copy
import logging
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import Integer, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

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
        # Marketing revises and re-sends without a forced detour through
        # `designing` first - the FE's own Mark design ready CTA already
        # shows at designing OR changes_requested (RequestTagDesigner.tsx)
        # and posts `proof_ready` directly; the extra hop served nobody and
        # only produced a 409 the toast then swallowed.
        STATUS_PROOF_READY,
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

# The classes the package guard warns about when `system_settings` has no row at
# all. Repeats `SystemSetting.price_tag_guarded_classes`' own server default
# (app/models/user.py), which is the source of truth; this copy only covers a
# database with no settings row, which is every fresh install and every test that
# does not seed one.
_DEFAULT_GUARDED_CLASSES = ("Bathroom Furniture", "Kitchen Sink")


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

        No promotion audience check here: this service method is also the
        CRM-side entry point (``tag_data_service`` etc.), which is not bound
        by a portal contact's audience. The audience gate
        (``validate_promotion_access``) is applied by the PORTAL create/update
        routes only (``portal_price_tag.py``), the one surface it is meant to
        guard - moved out of here after it 422ed two CRM-side create paths
        that have no contact audience to check.
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
                price_mode=data.get("price_mode") or "list",
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
    def _add_lines(
        db: Session,
        request: PriceTagRequest,
        lines: list[dict],
        *,
        carry_tags: dict[tuple, list[dict]] | None = None,
    ) -> None:
        """Append lines in the order given, which is the order the form shows.

        ``show_promo_price`` is DERIVED from the request's header ``price_mode``
        (D5), never taken from the payload: the per-line switch is gone, and
        every line save - create, replace on update - re-derives every line
        from whatever the header says right now, so a header flip never leaves
        a stale line behind.

        Every line gets its TAGS here too (D3): exactly one, carrying the line's
        quantity and an empty `choices`, unless ``carry_tags`` hands over the set
        a surviving line already had. ``replace_lines`` passes that map, keyed by
        ``(product_id, product_set_id)``, since the form payload has no field for
        any of it - a re-save with just a new remark used to silently wipe a
        marketing-set override, and would now silently un-split the line.

        Raises 422 ``DUPLICATE_LINE`` (round 3, R3-7/AC-R4) naming the code
        the FIRST time the same product or set repeats within ``lines`` -
        before any insert, so the table's own
        ``uq_ptag_line_request_product`` / ``uq_ptag_line_request_set``
        constraints never get the chance to answer with a 500.
        """
        PriceTagRequestService._raise_on_duplicate_line(db, lines)
        show_promo_price = request.price_mode == "selling"
        carry_tags = carry_tags or {}
        for idx, line_data in enumerate(lines):
            sort_order = line_data.get("sort_order")
            key = (line_data.get("product_id"), line_data.get("product_set_id"))
            line = (
                PriceTagRequestLine(
                    request_id=request.id,
                    line_type=line_data["line_type"],
                    product_id=line_data.get("product_id"),
                    product_set_id=line_data.get("product_set_id"),
                    show_promo_price=show_promo_price,
                    quantity=line_data.get("quantity", 1),
                    combo_id=PriceTagRequestService._resolve_combo_id(db, line_data, idx),
                    included_accessories=line_data.get("included_accessories"),
                    remarks=line_data.get("remarks"),
                    sort_order=idx if sort_order is None else sort_order,
                )
            )
            db.add(line)
            db.flush()
            PriceTagRequestService._add_line_parts(
                db, line, line_data.get("parts") or [], index=idx
            )
            PriceTagRequestService._add_line_tags(db, line, carry_tags.get(key))

    @staticmethod
    def _add_line_tags(db: Session, line, carried: list[dict] | None = None) -> None:
        """The tags that will be printed for this line (D3, AC-S3-1).

        Exactly ONE at submit, carrying the line's quantity and an empty
        `choices`: not zero (the designer would have nothing to key its document
        on) and not one per candidate (auto-split was rejected by the owner -
        marketing decides in the designer).

        `carried` is a surviving line's existing tag set, handed over by
        `replace_lines`, so a revision that changes a remark keeps the split
        marketing already made.
        """
        from app.models.price_tag import PriceTagRequestTag

        rows = carried if carried else [
            {"sort_order": 0, "quantity": line.quantity or 1, "choices": {}}
        ]
        # A line that was never split has exactly one tag, and that tag's
        # quantity is not marketing's - it is the salesperson's number, seeded
        # from the line. Without this, a draft saved at 1, changed to 5 and
        # submitted (or revised to 9) kept a tag at 1 and printed one tile
        # instead of five (review round 2, B1). A SPLIT line keeps its per-tag
        # quantities: once marketing has divided the line up, those numbers are
        # decisions, not a copy of anything.
        if carried and len(rows) == 1:
            rows = [{**rows[0], "quantity": line.quantity or 1}]
        for index, row in enumerate(rows):
            db.add(
                PriceTagRequestTag(
                    line_id=line.id,
                    sort_order=row.get("sort_order", index),
                    quantity=row.get("quantity") or 1,
                    choices=row.get("choices") or {},
                    marketing_price_override=row.get("marketing_price_override"),
                    marketing_override_reason=row.get("marketing_override_reason"),
                )
            )

    @staticmethod
    def _add_line_parts(db: Session, line, parts: list[dict], *, index: int = 0) -> None:
        """The package under a line, written in the order the form sent it (AC-S2-8).

        Order is display order on the request, in the tag's parts text (D4) and in
        the designer's rail, so the position is stored rather than left to the
        primary key.

        Two shapes, and the table's own CHECK keeps them apart: a RESOLVED row
        names a product and carries no candidates; an OPEN row names the choice
        group and the candidates it is still choosing between. A row that is
        neither - no product and no candidates - is dropped rather than written,
        because the constraint would refuse it with a 500 the salesperson cannot
        act on and an empty row means nothing anyway.

        EVERY id here comes from the portal, so every id is validated before it
        is stored (security review B1). Two separate failures were reachable by
        any portal contact:

        * a non-UUID candidate is accepted by JSONB and then blows up
          `Product.id.in_(...)` on EVERY later read of that request - a stored
          denial of service on the request, the designer and the PDF alike;
        * an id belonging to another company would be stored and then resolved,
          leaking that product onto this company's tag.

        One scoped query answers both: anything the caller cannot see simply is
        not returned, and a 422 naming the row is what the form can act on.
        """
        from app.models.price_tag import PriceTagRequestLinePart
        from app.models.product import Product

        cleaned: list[dict] = []
        wanted: set[str] = set()
        for part in parts:
            product_id = PriceTagRequestService._part_uuid(part.get("product_id"), index)
            candidates = [
                PriceTagRequestService._part_uuid(candidate, index)
                for candidate in (part.get("candidates") or [])
                if candidate
            ]
            if product_id:
                candidates = []
            elif not candidates:
                continue
            cleaned.append(
                {"product_id": product_id, "role": part.get("role"), "candidates": candidates}
            )
            if product_id:
                wanted.add(product_id)
            wanted.update(candidates)

        if wanted:
            # Company-scoped through the ordinary ORM filter: another company's
            # product reads exactly like one that does not exist.
            found = {
                pid
                for (pid,) in db.query(Product.id).filter(Product.id.in_(wanted)).all()
            }
            missing = wanted - found
            if missing:
                raise AppException(
                    status_code=422,
                    message="A product on this line's package could not be found.",
                    detail=f"line:{index}",
                    code="INVALID_PART",
                )

        for position, part in enumerate(cleaned):
            db.add(
                PriceTagRequestLinePart(
                    line_id=line.id,
                    product_id=part["product_id"],
                    role=part["role"],
                    candidates=part["candidates"],
                    sort_order=position,
                )
            )

    @staticmethod
    def _part_uuid(value, index: int) -> str | None:
        """A portal-supplied id, or a 422 naming the row it came from.

        JSONB will store any string at all, and `candidates` is read back into
        `Product.id.in_(...)`, where a non-UUID is a Postgres error rather than
        an empty result - so the check has to happen on the way IN.
        """
        if value in (None, ""):
            return None
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            raise AppException(
                status_code=422,
                message="A product on this line's package is not a valid reference.",
                detail=f"line:{index}",
                code="INVALID_PART",
            ) from None

    @staticmethod
    def _resolve_combo_id(db: Session, line_data: dict, index: int) -> str | None:
        """The package this line is asked for as, or None.

        Validated rather than trusted, same reason as the part ids: `combo_id`
        arrives from the portal. It must be a real combo, visible to the caller
        (the query is scoped through the host product), and it must belong to
        THIS line's product - a combo id from another cabinet would price and
        print somebody else's package on this one.

        A combo that fails any of those is stored as None rather than refused:
        the S2 guard then says "No package chosen" on the row, which is the
        warn-and-allow rule the whole slice is built on (AC-S2-5).
        """
        from app.models.product_combo import ProductCombo

        raw = line_data.get("combo_id")
        if not raw:
            return None
        try:
            combo_id = str(uuid.UUID(str(raw)))
        except (ValueError, AttributeError, TypeError):
            return None
        product_id = line_data.get("product_id")
        if not product_id:
            return None
        combo = (
            db.query(ProductCombo)
            .filter(
                ProductCombo.id == combo_id,
                ProductCombo.host_product_id == product_id,
            )
            .first()
        )
        return combo.id if combo is not None else None

    @staticmethod
    def _raise_on_duplicate_line(db: Session, lines: list[dict]) -> None:
        """The first repeated product or set in ``lines``, named by code, as a
        422 - before ``_add_lines`` inserts a second row the table's own
        unique constraint would otherwise refuse with an unhandled 500."""
        seen_products: set[str] = set()
        seen_sets: set[str] = set()
        for line_data in lines:
            product_id = line_data.get("product_id")
            if product_id:
                if product_id in seen_products:
                    raise PriceTagRequestService._duplicate_line_refusal(
                        db, product_id=product_id
                    )
                seen_products.add(product_id)
            set_id = line_data.get("product_set_id")
            if set_id:
                if set_id in seen_sets:
                    raise PriceTagRequestService._duplicate_line_refusal(
                        db, product_set_id=set_id
                    )
                seen_sets.add(set_id)

    @staticmethod
    def _duplicate_line_refusal(
        db: Session,
        *,
        product_id: str | None = None,
        product_set_id: str | None = None,
    ) -> AppException:
        from app.models.product import Product
        from app.models.product_set import ProductSet

        if product_id:
            row = db.query(Product).filter(Product.id == product_id).first()
            code = row.product_code if row else product_id
        else:
            row = db.query(ProductSet).filter(ProductSet.id == product_set_id).first()
            code = row.set_code if row else product_set_id
        return AppException(
            status_code=422,
            message=f"{code} appears twice; merge the quantities.",
            detail="lines",
            code="DUPLICATE_LINE",
        )

    @staticmethod
    def replace_lines(db: Session, request: PriceTagRequest, lines: list[dict]) -> None:
        """Swap a draft's lines for the ones the form just posted.

        A re-save sends the whole table, not a diff: the rows are unsaved form
        state on the client and carry no stable identity there. Deleting through
        the relationship keeps ``delete-orphan`` in charge, so nothing is left
        pointing at the request.

Marketing's own work is not part of the form's payload, so it is captured
        from the OLD rows before they are cleared and carried onto whichever new
        row keeps the same product or set. Since S3 that work lives on the TAGS
        (D3), so what is carried is the tag set itself - its split, its choices,
        its quantities and its overrides - rather than one override per line: a
        salesperson fixing a typo in a remark must not un-split a line marketing
        already turned into four tags.
        """
        carry_tags = {
            (old.product_id, old.product_set_id): [
                {
                    "sort_order": tag.sort_order,
                    "quantity": tag.quantity,
                    "choices": dict(tag.choices or {}),
                    "marketing_price_override": tag.marketing_price_override,
                    "marketing_override_reason": tag.marketing_override_reason,
                }
                for tag in sorted(
                    old.tags or [], key=lambda t: (t.sort_order or 0, t.id)
                )
            ]
            for old in request.lines
        }
        request.lines.clear()
        db.flush()
        PriceTagRequestService._add_lines(db, request, lines, carry_tags=carry_tags)
        db.flush()
        # `_add_lines` inserts the new rows via `db.add(...)`, not
        # `request.lines.append(...)`, so the in-memory collection is left
        # holding the CLEARED (empty) state even though the DB now has the
        # new rows - a caller reading `request.lines` right after this (e.g.
        # a post-submit PUT's `validate_submittable`, review round 2) saw
        # zero lines regardless of what was just saved. Expiring forces the
        # next access to re-query.
        db.expire(request, ["lines"])

    @staticmethod
    def submit_request(
        db: Session,
        contact_id: str,
        company_id: str,
        data: dict,
    ) -> PriceTagRequest:
        """Create a price tag request and stamp its package warnings (D2).

        Submit is NEVER refused for a package reason (AC-S2-5, AC-S2-7). The set
        guard that used to 422 an ala-carte Bathroom Furniture line is retired;
        a guarded product that arrives with no package, or with parts taken off,
        carries a `package_warning` marketing reads instead. `DUPLICATE_LINE` and
        the completeness rules are untouched.

        The warnings are stamped AFTER the lines exist, not from the payload:
        the rule reads what was actually stored, so a revision and a submit
        cannot answer differently for the same request.
        """
        request = PriceTagRequestService.create_request(
            db, contact_id, company_id, data
        )
        # Clear the draft timestamp to indicate submission.
        request.portal_draft_at = None
        db.flush()
        PriceTagRequestService.apply_package_warnings(db, request)
        db.flush()
        return request

    @staticmethod
    def auto_assign_from_tracker(db: Session, request: PriceTagRequest) -> str | None:
        """D8: copy the form SLA tracker's resolved assignee onto the request.

        Reads the newest OPEN ``price_tag_request`` tracker for this request -
        the one ``emit_form_event`` just opened, if an active config placed it
        (``_start_for_config`` commits as part of opening it, so this read
        always sees it: no explicit flush needed). No tracker, or a tracker
        with no assignee, leaves the request ``new`` and unclaimed - the Claim
        path is unchanged (AC-S3-2). Returns the assignee id, or ``None``.

        The write (status, assignee, the tag_sheet page) runs inside its own
        SAVEPOINT: ``assigned_to_id`` is set only after ``transition_status``
        has actually succeeded, and a failure anywhere in the block rolls the
        savepoint back rather than leaving a half-write (assigned but still
        ``new``, or vice versa) for the caller's own ``db.commit()`` to
        persist. Called from ``portal_submit_price_tag_request`` in its OWN
        try/except: a failure here must not fail the submit (AC-S3-3).
        """
        from app.models.sla import ConversationSLATracking
        from app.services.sla_scope import open_tracker_scope

        tracker = (
            db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.source_entity_type == "price_tag_request",
                ConversationSLATracking.source_entity_id == str(request.id),
                *open_tracker_scope(),
            )
            .order_by(ConversationSLATracking.initiated_at.desc())
            .first()
        )
        if not tracker or not tracker.assigned_to_id:
            return None

        savepoint = db.begin_nested()
        try:
            PriceTagRequestService.transition_status(
                db, str(request.id), STATUS_DESIGNING, user_id=tracker.assigned_to_id,
            )
            request.assigned_to_id = tracker.assigned_to_id
            # B1: a request auto-assigned straight into `designing` needs the
            # same tag_sheet page Claim creates - without this GET
            # .../design 404s NO_PAGE, and auto-assign has already claimed
            # it, so there is no Claim button left to fix it from.
            PriceTagRequestService.ensure_tag_sheet_page(
                db, request, tracker.assigned_to_id,
            )
            db.flush()
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            raise
        return tracker.assigned_to_id

    @staticmethod
    def ensure_tag_sheet_page(
        db: Session, request: PriceTagRequest, user_id: str | None,
    ) -> None:
        """The tag_sheet ``Page`` a request needs before design can happen.

        Idempotent: a no-op once ``request.page_id`` is set. Extracted from
        the CRM claim route (``claim_price_tag_request``) so BOTH claim and
        ``auto_assign_from_tracker`` (D8) create it the same way - a request
        that lands in ``designing`` with no page 404s NO_PAGE on
        ``GET .../design`` (B1).
        """
        if request.page_id:
            return
        from app.models.dealer_kit import Page

        page = Page(
            name=f"Tags - {request.doc_number}",
            slug=f"tag-sheet-{request.doc_number.lower()}",
            kind="tag_sheet",
            request_id=request.id,
            company_id=request.company_id,
            created_by=user_id,
        )
        db.add(page)
        db.flush()
        request.page_id = page.id

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

        # D12: an approve auto-queues one tag-sheet export, so the salesperson
        # never has to ask marketing to run it separately. Function-local
        # module import (not a from-import) - tag_sheet_export_service
        # imports STATUS_APPROVED/STATUS_READY from THIS module at ITS own
        # top level, so a top-level import here would be circular, and tests
        # monkeypatch this module's `request_tag_sheet_export` attribute,
        # which only a call through the module (not a bound name) picks up.
        # Own try/except: a failure here must never turn a successful
        # approve into a failed one (AC-S5-2) - logged, nothing raised.
        if new_status == STATUS_APPROVED:
            try:
                from app.services.dealer_kit import tag_sheet_export_service

                tag_sheet_export_service.request_tag_sheet_export(
                    db, request_id=request_id, user_id=user_id, sheet_ids=None,
                )
            except Exception:
                logger.warning(
                    "Auto-export failed for price_tag_request %s",
                    request_id,
                    exc_info=True,
                )

        return request

    @staticmethod
    def validate_submittable(
        request: PriceTagRequest, *, require_debtor: bool = True
    ) -> None:
        """What a request needs before it may be submitted (D48a).

        A draft can be sloppy; a submitted request cannot. Every missing field is
        named at once, in ``detail`` as a comma-separated list of keys the form
        knows how to place, so the portal can put each message under the field it
        belongs to instead of showing one sentence in a toast.

        A line with neither a product nor a set cannot exist here: the table's
        ``ck_price_tag_request_lines_one_ref`` refuses it on insert. The form
        catches that one on the client, where the empty row actually is.

        ``require_debtor=False`` (review round 2): a post-submit PUT reuses this
        for its own completeness bar (AC-B10), but that bar is lines-only - the
        debtor was already locked in at the ORIGINAL submit and this PUT does
        not touch it, so re-checking it here would refuse an edit over a field
        the edit never asked about.
        """
        # D-P2b: need by is optional - dropped from what "complete" requires.
        missing: list[tuple[str, str]] = []
        if require_debtor and not (request.debtor_name or "").strip():
            missing.append(("debtor_name", "a dealer"))
        if not request.lines:
            missing.append(("lines", "at least one line"))
        if missing:
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

        # D-P2 (owner ruling): Selling with no promotion is a valid end state
        # now - the PRICE_MODE_NEEDS_PROMOTION guard is retired.

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
    def validate_designable(request: PriceTagRequest) -> None:
        """Mirrors the FE's ``priceTagActions`` design/"view design" predicate.

        The CRM Lines tab and the request header both compute
        ``actions.some(spec => spec.action === 'design')`` off
        ``priceTagActions(status, assigned_to_id)`` to decide whether the
        designer route is legal right now; this is that same rule, so the
        endpoint that actually writes a design doc cannot be reached from a
        status the UI never offers it from. ``designing`` / ``changes_requested``
        / ``proof_ready`` are legal outright; ``new`` is legal only once
        claimed (``assigned_to_id`` set) - the FE checks ``!assignedToId``
        truthiness only, never "claimed by ME", so this does the same and
        does not additionally require ``assigned_to_id == the caller``.
        """
        legal_claimed_new = request.status == STATUS_NEW and request.assigned_to_id
        legal_status = request.status in (
            STATUS_DESIGNING,
            STATUS_CHANGES_REQUESTED,
            STATUS_PROOF_READY,
        )
        if not (legal_claimed_new or legal_status):
            raise AppException(
                status_code=409,
                message=(
                    "This request's tags cannot be designed in its current "
                    "status."
                ),
                code="INVALID_STATE",
            )

    @staticmethod
    def _fill_line_parts(db: Session, request: PriceTagRequest, response) -> None:
        """Resolve every part row on every line to codes and names (D2).

        One query for every product any part mentions - the resolved rows AND
        the candidates of the open ones - rather than one per row: a request
        with four packaged lines carries twenty part products, and the portal
        read view is not the place to spend twenty round trips.
        """
        from app.models.product import Product
        from app.schemas.price_tag import (
            LinePartCandidateResponse,
            PriceTagRequestLinePartResponse,
        )

        parts_by_line: dict[str, list] = {}
        wanted: set[str] = set()
        for line in request.lines:
            rows = sorted(line.parts or [], key=lambda p: (p.sort_order or 0, p.id))
            parts_by_line[line.id] = rows
            for row in rows:
                if row.product_id:
                    wanted.add(row.product_id)
                for candidate in row.candidates or []:
                    wanted.add(str(candidate))
        if not wanted:
            return

        products = {
            product.id: product
            for product in db.query(Product).filter(Product.id.in_(wanted)).all()
        }

        def _code(product_id):
            product = products.get(product_id)
            return product.product_code if product else None

        def _name(product_id):
            product = products.get(product_id)
            return product.product_name if product else None

        for line in response.lines:
            rows = parts_by_line.get(line.id) or []
            line.parts = [
                PriceTagRequestLinePartResponse(
                    id=row.id,
                    product_id=row.product_id,
                    code=_code(row.product_id),
                    name=_name(row.product_id),
                    role=row.role,
                    candidates=[
                        LinePartCandidateResponse(
                            product_id=str(candidate),
                            code=_code(str(candidate)) or "",
                            name=_name(str(candidate)) or "",
                        )
                        for candidate in (row.candidates or [])
                    ],
                    sort_order=row.sort_order or 0,
                )
                for row in rows
            ]

    # ------------------------------------------------------------------- tags

    @staticmethod
    def tag_body(tag, resolved: dict | None) -> dict:
        """One tag in the shape every surface reads (D3).

        `choices_display` resolves the stored `{role: product_id}` map to codes -
        the raw map is never rendered (AC-X-2) - and the prices come off the ONE
        resolver, so the rail, the Lines tab and the PDF cannot disagree.
        """
        chosen = dict(tag.choices or {})
        by_id = {}
        for group in (resolved or {}).get("open_groups") or []:
            for candidate in group.get("candidates") or []:
                by_id[candidate["product_id"]] = candidate["code"]
        # A resolved choice is no longer an open group, so its code comes off the
        # tag's own resolved parts, matched by id.
        for part in (resolved or {}).get("parts") or []:
            if part.get("product_id"):
                by_id.setdefault(str(part["product_id"]), part.get("code", ""))
        return {
            "id": tag.id,
            "line_id": tag.line_id,
            "sort_order": tag.sort_order or 0,
            "label": (resolved or {}).get("tag_label", ""),
            "quantity": tag.quantity,
            "choices": chosen,
            "choices_display": [
                {"role": role, "code": by_id.get(str(product_id), "")}
                for role, product_id in chosen.items()
            ],
            "open_groups": (resolved or {}).get("open_groups") or [],
            "marketing_price_override": (
                None
                if tag.marketing_price_override is None
                else float(tag.marketing_price_override)
            ),
            "marketing_override_reason": tag.marketing_override_reason,
            "list_price": (resolved or {}).get("list_price"),
            "sell_price": (resolved or {}).get("sell_price"),
        }

    @staticmethod
    def validate_choices(db: Session, tag, choices: dict) -> None:
        """"Pick one" may only pick from what the line actually left open.

        Unvalidated, `choices` was a free `{anything: anything}` write from a
        marketing user: a role the line never opened, or a product id from
        another company, would be stored and then resolved onto the tag - which
        is how a cabinet ends up printing a basin nobody offered.

        Both halves are checked against the LINE's own part rows, which is the
        only place that says what was asked for.
        """
        open_groups = {}
        for part in tag.line.parts or []:
            if part.product_id or not part.role:
                continue
            open_groups[part.role] = {str(c) for c in (part.candidates or [])}

        for role, product_id in (choices or {}).items():
            if role not in open_groups:
                raise AppException(
                    status_code=422,
                    message=f"This line has no open {role} to choose.",
                    code="INVALID_CHOICE",
                )
            if str(product_id) not in open_groups[role]:
                raise AppException(
                    status_code=422,
                    message=f"That product is not one of the {role} options on this line.",
                    code="INVALID_CHOICE",
                )

    @staticmethod
    def split_tag(db: Session, tag, role: str) -> list:
        """"Split into N tags" (AC-S3-4).

        The tag that is there resolves to candidate 1 and KEEPS ITS ID, so its
        placed geometry and its review pins survive; N-1 siblings are inserted
        after it, one per remaining candidate in combo order, and the draft
        document gets a copy of the original's placement for each.
        """
        from app.models.price_tag import PriceTagRequestTag

        line = tag.line
        candidates: list[str] = []
        for part in sorted(line.parts or [], key=lambda p: (p.sort_order or 0, p.id)):
            if part.product_id or (part.role or "") != role:
                continue
            candidates = [str(c) for c in (part.candidates or [])]
            break
        if not candidates:
            raise AppException(
                status_code=422,
                message=f"This line has no open {role} to split.",
                code="NO_OPEN_GROUP",
            )

        siblings = sorted(line.tags or [], key=lambda t: (t.sort_order or 0, t.id))
        after = [row for row in siblings if (row.sort_order or 0) > (tag.sort_order or 0)]
        shift = len(candidates) - 1
        for row in after:
            row.sort_order = (row.sort_order or 0) + shift

        tag.choices = {**dict(tag.choices or {}), role: candidates[0]}
        created = []
        for offset, candidate in enumerate(candidates[1:], start=1):
            sibling = PriceTagRequestTag(
                line_id=line.id,
                sort_order=(tag.sort_order or 0) + offset,
                quantity=tag.quantity,
                choices={**dict(tag.choices or {}), role: candidate},
                marketing_price_override=tag.marketing_price_override,
                marketing_override_reason=tag.marketing_override_reason,
            )
            db.add(sibling)
            created.append(sibling)
        db.flush()

        PriceTagRequestService._copy_placements_in_draft(
            db, line.request_id, tag.id, [row.id for row in created]
        )
        db.flush()
        db.expire(line, ["tags"])
        return sorted(line.tags, key=lambda t: (t.sort_order or 0, t.id))

    @staticmethod
    def delete_tag(db: Session, tag) -> None:
        """Remove one tag and its placements. Never the line's last (AC-S3-6)."""
        line = tag.line
        if len(line.tags or []) <= 1:
            raise AppException(
                status_code=422,
                message="A line must keep at least one tag.",
                code="LAST_TAG",
            )
        request_id, tag_id = line.request_id, tag.id
        db.delete(tag)
        db.flush()
        PriceTagRequestService._drop_placements_in_draft(db, request_id, tag_id)
        db.flush()

    @staticmethod
    def _tag_sheet_page(db: Session, request_id: str):
        from app.models.dealer_kit import Page

        return (
            db.query(Page)
            .filter(Page.request_id == request_id, Page.kind == "tag_sheet")
            .first()
        )

    @staticmethod
    def _copy_placements_in_draft(
        db: Session, request_id: str, source_tag_id: str, new_tag_ids: list[str]
    ) -> None:
        """Give every new sibling the split tag's own geometry (AC-S3-4).

        Marketing drew ONE tag and asked for four; landing three of them
        unplaced would make the sheet look broken at the moment of the split.
        The copies keep their own `-cN` suffix, which is how `tagsFromDoc` tells
        copy 0 (the master, whose layers are the design) from the rest.
        """
        page = PriceTagRequestService._tag_sheet_page(db, request_id)
        if page is None or not page.draft_doc or not new_tag_ids:
            return
        doc = copy.deepcopy(page.draft_doc)
        changed = False
        for sheet in doc.get("sheets") or []:
            placed = sheet.get("tags") or []
            sources = [p for p in placed if p.get("request_tag_id") == source_tag_id]
            for source in sources:
                suffix = str(source.get("id") or "")
                copy_index = suffix.rsplit("-c", 1)[-1] if "-c" in suffix else "0"
                for new_tag_id in new_tag_ids:
                    clone = copy.deepcopy(source)
                    clone["request_tag_id"] = new_tag_id
                    clone["id"] = f"{new_tag_id}-c{copy_index}"
                    placed.append(clone)
                    changed = True
            sheet["tags"] = placed
        if changed:
            page.draft_doc = doc
            flag_modified(page, "draft_doc")

    @staticmethod
    def _drop_placements_in_draft(db: Session, request_id: str, tag_id: str) -> None:
        """A deleted tag leaves no placement behind (AC-S3-6)."""
        page = PriceTagRequestService._tag_sheet_page(db, request_id)
        if page is None or not page.draft_doc:
            return
        doc = copy.deepcopy(page.draft_doc)
        changed = False
        for sheet in doc.get("sheets") or []:
            kept = [p for p in (sheet.get("tags") or []) if p.get("request_tag_id") != tag_id]
            if len(kept) != len(sheet.get("tags") or []):
                changed = True
            sheet["tags"] = kept
        if changed:
            page.draft_doc = doc
            flag_modified(page, "draft_doc")

    @staticmethod
    def guarded_classes(db: Session) -> set[str]:
        """The product classes a missing package is worth warning about (D2).

        Read from `system_settings`, never a literal, or the settings control is
        decorative and the tenant that packages shower trays has no way to say
        so. No settings row at all (a fresh install, most tests) falls back to
        the column's own default.
        """
        from app.models.user import SystemSetting

        row = db.query(SystemSetting).first()
        if row is None:
            return set(_DEFAULT_GUARDED_CLASSES)
        configured = getattr(row, "price_tag_guarded_classes", None)
        if configured is None:
            return set(_DEFAULT_GUARDED_CLASSES)
        # An empty list is a legitimate answer - warn about nothing.
        return {str(label) for label in configured}

    @staticmethod
    def apply_package_warnings(db: Session, request: PriceTagRequest) -> None:
        """Stamp `package_warning` on every line of `request` (D2, AC-S2-5).

        Replaces `validate_set_guard`, which raised 422. Runs wherever that one
        ran - `submit_request` and the portal revision path - so a salesperson
        can never submit a bare cabinet and then be blocked from correcting it.

        A product_set line is skipped entirely: parts are a combo fact on a
        PRODUCT line, and nothing about a set is a package question.
        """
        guarded = PriceTagRequestService.guarded_classes(db)
        for line in request.lines:
            line.package_warning = PriceTagRequestService._package_warning_for(
                db, line, guarded
            )

    @staticmethod
    def _package_warning_for(db: Session, line, guarded: set[str]) -> str | None:
        """The D2 rule, in the order it reads on the plan.

        `None` for anything that is not a guarded product line, then the two
        "no package" cases, then whatever the chosen combo asks for that no part
        row answers. A choice group left OPEN is an ANSWER, not an omission: the
        whole point of the open row is that the salesperson may not know which
        basin, and marketing splits it into one tag per candidate later (S3).
        """
        from app.models.product import Product, ProductCategory
        from app.models.product_combo import ProductCombo, ProductComboPart

        if line.line_type != "product" or not line.product_id:
            return None

        product = db.query(Product).filter(Product.id == line.product_id).first()
        if product is None:
            return None
        category = (
            db.query(ProductCategory)
            .filter(ProductCategory.id == product.category_id)
            .first()
        )
        if category is None or category.class_label not in guarded:
            return None

        if not line.combo_id:
            has_combos = (
                db.query(ProductCombo)
                .filter(ProductCombo.host_product_id == line.product_id)
                .first()
                is not None
            )
            return "No package chosen" if has_combos else "No package defined"

        combo_parts = (
            db.query(ProductComboPart)
            .filter(ProductComboPart.combo_id == line.combo_id)
            .order_by(ProductComboPart.sort_order)
            .all()
        )
        if not combo_parts:
            return None

        rows = list(line.parts or [])
        answered_products = {row.product_id for row in rows if row.product_id}
        answered_roles = {row.role for row in rows if row.role}

        missing: list[str] = []
        seen_groups: list[str] = []
        for part in combo_parts:
            if part.choice_group:
                if part.choice_group not in seen_groups:
                    seen_groups.append(part.choice_group)
                continue
            if part.part_product_id not in answered_products:
                # Never the raw id as a fallback: this text is rendered on the
                # portal row and in the CRM Lines tab, and no UUID reaches a
                # screen (AC-X-2). A part whose product will not resolve is
                # named by nothing rather than by its id.
                code = (
                    part.part_product.product_code
                    if part.part_product is not None
                    else ""
                )
                if code:
                    missing.append(code)
        for group in seen_groups:
            # Neither a resolved nor an open row answers this group. A row
            # RESOLVED from the group keeps its `role`, which is why one check
            # covers both shapes.
            if group not in answered_roles:
                missing.append(group)

        return f"Missing: {', '.join(missing)}" if missing else None

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
        from app.services.portal_service import PortalService

        labels = PriceTagRequestService.resolved_labels(
            db, [request.id for request in requests]
        )
        # R3-1/AC-R5: the summary carries whether an unsent revision draft is
        # parked for this row, same shared check the other portal kinds use.
        draft_ids = PortalService(db)._ids_with_revision_draft(  # noqa: SLF001
            "price_tag_request", [str(request.id) for request in requests]
        )
        items = []
        for request in requests:
            item = PriceTagRequestListItem.model_validate(request)
            for key, value in labels.get(request.id, {}).items():
                setattr(item, key, value)
            item.has_revision_draft = str(request.id) in draft_ids
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
        portal detail route both answer with it (D49). Same reason
        ``attachments`` is resolved here rather than in either route: one call
        to ``list_attachments_for_entity`` is what keeps the two screens from
        ever disagreeing about what this request's PO files look like
        (PLAN-price-tag-feedback-r2 S1).
        """
        from app.schemas.price_tag import (
            PriceTagRequestAttachment,
            PriceTagRequestResponse,
            PriceTagRequestTagResponse,
        )
        from app.services.dealer_kit import tag_data_service
        from app.services.entity_attachment_service import list_attachments_for_entity

        response = PriceTagRequestResponse.model_validate(request)
        # One resolver row per TAG since S3 (D3). The line's own code, name and
        # prices come off its FIRST tag - every tag on a line prints the same
        # host product, so those three are a line fact even though the rows are
        # per tag.
        rows = tag_data_service.resolve_request_line_data(db, request)
        by_tag = {row["tag_id"]: row for row in rows}
        first_by_line: dict[str, dict] = {}
        for row in rows:
            first_by_line.setdefault(row["line_id"], row)
        tags_by_line: dict[str, list] = {}
        for line in request.lines:
            tags_by_line[line.id] = sorted(
                line.tags or [], key=lambda t: (t.sort_order or 0, t.id)
            )

        for line in response.lines:
            line.tags = [
                PriceTagRequestTagResponse(
                    **PriceTagRequestService.tag_body(tag, by_tag.get(tag.id))
                )
                for tag in tags_by_line.get(line.id, [])
            ]
            row = first_by_line.get(line.id)
            if not row:
                continue
            line.code = row["code"]
            line.name = row["name"]
            # float() here rather than trusting the annotation: assigning to a
            # pydantic field does NOT validate, so a Decimal set on a `float` field
            # is serialised as a JSON STRING and the page's `.toFixed(2)` throws.
            line.list_price = None if row["list_price"] is None else float(row["list_price"])
            line.sell_price = None if row["sell_price"] is None else float(row["sell_price"])

        PriceTagRequestService._fill_line_parts(db, request, response)

        response.attachments = [
            PriceTagRequestAttachment(**row)
            for row in list_attachments_for_entity(db, "price_tag_request", request.id)
        ]

        # Function-local: breaks a module cycle. tag_sheet_export_service
        # imports STATUS_APPROVED/STATUS_READY from THIS module at its own
        # top level, so a top-level import here would be circular.
        from app.services.dealer_kit.tag_sheet_export_service import (
            latest_completed_export,
        )

        response.has_completed_export = (
            latest_completed_export(db, request.id) is not None
        )

        # R3-1/AC-R1: reverses S8's D-P6 - a submitted request is read-only
        # exactly like a stock inquiry. True for a draft only; a submitted
        # request changes through the revision engine instead.
        response.is_editable = bool(request.portal_draft_at)

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
    def lookup_promotions(
        db: Session, contact_id: str, query: str | None = None
    ) -> list[dict]:
        """Active-window, audience-gated promotions for the portal's promotion
        dropdown (S4, #477).

        The active-window half mirrors ``resolve_prices``' ``_offer_prices``:
        switched-on (``is_active``) AND inside an inclusive ``[start_date,
        end_date]`` window, either end open. Company scoping is not written here
        on purpose - ``Promotion`` carries ``CompanyScopedMixin`` and the ordinary
        ORM scope filter already keeps another company's promotion off this list,
        the same way it already keeps it out of a price.

        The audience half is applied too - a first cut of this lookup shipped
        without it, so a dealer-only promotion showed up in every contact's
        dropdown. It intersects the contact's own access codes
        (``ContactAccessTypeService.get_contact_access_codes``) against
        ``Promotion.access_levels``, same rule ``pricing._may_see_offer``
        enforces: an empty ``access_levels`` reaches nobody. It deliberately does
        NOT call ``_may_see_offer`` itself, though, because that helper's other
        half does not apply here - an empty ``ViewerContext.access_codes`` there
        falls back to the PUBLIC access code, because the anonymous public
        catalogue is a real, intentional viewer. A portal contact is never
        anonymous: one with no assigned access code is missing data, not a
        member of the public, so it fails closed instead of widening to the
        public audience.
        """
        from app.models.marketing import Promotion
        from app.services.contact_access_type_service import ContactAccessTypeService
        from app.services.dealer_kit.pricing import business_today

        contact_codes = set(
            ContactAccessTypeService(db).get_contact_access_codes(contact_id)
        )
        if not contact_codes:
            return []

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
        return [
            {"id": row.id, "name": row.description or ""}
            for row in rows
            if row.access_levels and contact_codes & set(row.access_levels)
        ]

    @staticmethod
    def validate_promotion_access(
        db: Session, contact_id: str, promotion_id: str | None
    ) -> None:
        """Review round 2: a raw ``promotion_id`` on create/update must be one
        this contact's own audience can see. ``lookup_promotions`` already
        gates the dropdown by access code and active window; nothing gated a
        promotion id posted directly, so a promotion whose ``access_levels``
        exclude this contact went through unchecked. Reuses the same lookup
        rather than re-deriving the rule, so the two can never disagree.
        """
        if promotion_id is None:
            return
        allowed_ids = {
            row["id"] for row in PriceTagRequestService.lookup_promotions(db, contact_id)
        }
        if promotion_id not in allowed_ids:
            raise AppException(
                status_code=422,
                message="This promotion is not available for your account.",
                code="PROMOTION_NOT_AVAILABLE",
            )

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
