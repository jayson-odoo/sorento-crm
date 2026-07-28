"""Shared "requestor" contact picker query for PR/SF/stock-inquiry "Requested by".

One definition of "who can be a requestor" reused by the internal (JWT) CRM
picker and the portal (token) picker. Fail-closed: no flagged market segment
means the eligible set is empty (this is a directory-exposure surface, see
PLAN-requested-by-contact-routing.md risk section) plus whatever ids the
caller explicitly asks to include (D6: the row's submitting contact + the
currently-saved requestor, so nobody is ever blocked from submitting and a
staff edit can never silently blank the field).

Kept dependency-free of any request/token object so both the portal route
and the internal route can call it directly with a plain Session.
"""
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.access import (
    MarketSegment,
    RespondContact,
    respond_contact_market_segments,
)

DEFAULT_LIMIT = 50


def list_requestor_options(
    db: Session,
    q: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    include_ids: Optional[Iterable[str]] = None,
) -> tuple[list[dict], bool]:
    """Return `([{id, name}], has_more)`.

    Eligible set = contacts with >= 1 row in `respond_contact_market_segments`
    whose `market_segments` row has `is_requestor_selectable=true` AND
    `is_active=true`, UNION every id in `include_ids` (regardless of `q` or
    eligibility, per D6). Ordered by name, capped at `limit`, distinct by id.
    Names only, no phone / email / respond_io_id.
    """
    include_ids = [str(i) for i in include_ids if i] if include_ids else []

    # A contact's display name: prefer the freeform `name`, else derive from
    # first + last (same precedence as portal_service._contact_display_name).
    name_expr = func.coalesce(
        func.nullif(func.trim(RespondContact.name), ""),
        func.nullif(
            func.trim(func.concat_ws(" ", RespondContact.first_name, RespondContact.last_name)),
            "",
        ),
    )

    eligible_q = (
        db.query(RespondContact.id.label("id"), name_expr.label("name"))
        .join(
            respond_contact_market_segments,
            respond_contact_market_segments.c.contact_id == RespondContact.id,
        )
        .join(
            MarketSegment,
            MarketSegment.code == respond_contact_market_segments.c.segment_code,
        )
        .filter(
            MarketSegment.is_requestor_selectable.is_(True),
            MarketSegment.is_active.is_(True),
        )
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        eligible_q = eligible_q.filter(name_expr.ilike(needle))

    # A contact tagged with two flagged segments joins twice; without this it
    # shows up twice in the picker, eats two of the `limit` slots and skews
    # has_more. The include_ids UNION below dedups on its own, so the duplicate
    # only ever appeared when include_ids was empty.
    eligible_q = eligible_q.distinct()

    combined = eligible_q
    if include_ids:
        include_q = db.query(RespondContact.id.label("id"), name_expr.label("name")).filter(
            RespondContact.id.in_(include_ids)
        )
        combined = combined.union(include_q)

    combined_sub = combined.subquery()
    rows = (
        db.query(combined_sub.c.id, combined_sub.c.name)
        .order_by(combined_sub.c.name.asc().nulls_last(), combined_sub.c.id.asc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [{"id": r.id, "name": r.name or ""} for r in rows]
    return items, has_more


def filter_form_referenced_ids(db: Session, ids: Optional[Iterable[str]]) -> list[str]:
    """Keep only ids already referenced by a PR / SF / stock-inquiry row as its
    submitter or its saved requestor.

    `include_ids` on the internal picker exists so an edit form never silently
    blanks a requestor who sits outside a flagged segment. Passing it straight
    through would turn the endpoint into a contact-name lookup for ANY id an
    authenticated user cares to guess, which defeats the fail-closed design of
    the eligible set. Ids the caller can already see on the row stay allowed.
    """
    wanted = [str(i).strip() for i in (ids or []) if i and str(i).strip()]
    if not wanted:
        return []
    from sqlalchemy import text as _sql_text

    rows = db.execute(
        _sql_text(
            """
            SELECT contact_id AS id FROM purchase_requests WHERE contact_id = ANY(:ids)
            UNION
            SELECT requested_by_contact_id FROM purchase_requests
              WHERE requested_by_contact_id = ANY(:ids)
            UNION
            SELECT contact_id FROM stock_inquiries WHERE contact_id = ANY(:ids)
            UNION
            SELECT salesperson_contact_id FROM stock_inquiries
              WHERE salesperson_contact_id = ANY(:ids)
            """
        ),
        {"ids": wanted},
    ).fetchall()
    allowed = {str(r[0]) for r in rows if r[0]}
    return [i for i in wanted if i in allowed]


def contact_display_name(contact: RespondContact) -> Optional[str]:
    """Freeform `name`, else first + last. Same precedence as the picker query's
    `name_expr` and portal_service._contact_display_name."""
    name = (
        (contact.name or "").strip()
        or " ".join(
            p
            for p in [(contact.first_name or "").strip(), (contact.last_name or "").strip()]
            if p
        ).strip()
    )
    return name or None


def apply_requestor_contact(
    db: Session,
    row: object,
    fk_field: str,
    label_field: str,
    contact_id_value: object,
    extra_eligible_ids: Optional[Iterable[Optional[str]]] = None,
) -> None:
    """Validate + stamp the requestor FK AND its text label on `row`.

    Shared by the portal (token) save and the internal (JWT) create/update so
    both behave identically: the id must be eligible or the save is rejected
    (never trust the client), and the text label (``requested_by`` /
    ``salesperson``) is re-derived from the chosen contact's CURRENT name. The
    label is what the document, the PDF and the public approval page print, so
    stamping the FK without it leaves those reading "-" (that was the bug).

    An empty value clears BOTH the FK and the label.
    """
    from app.services.error_handler import AppException

    raw = str(contact_id_value).strip() if contact_id_value not in (None, "") else ""
    if not raw:
        setattr(row, fk_field, None)
        return
    extra = list(extra_eligible_ids or [])
    extra.append(getattr(row, "contact_id", None))
    extra.append(getattr(row, fk_field, None))
    if not is_eligible_requestor(db, raw, extra_ids=extra):
        raise AppException(
            status_code=422,
            message="Selected requestor is not an eligible contact.",
            code="REQUESTOR_NOT_ELIGIBLE",
        )
    contact = db.query(RespondContact).filter(RespondContact.id == raw).first()
    if contact is None:
        raise AppException(
            status_code=422,
            message="Selected requestor could not be found.",
            code="REQUESTOR_NOT_ELIGIBLE",
        )
    setattr(row, fk_field, contact.id)
    display = contact_display_name(contact)
    if display:
        setattr(row, label_field, display)


def is_eligible_requestor(
    db: Session,
    contact_id: Optional[str],
    extra_ids: Optional[Iterable[Optional[str]]] = None,
) -> bool:
    """True when `contact_id` may be saved as a requestor.

    Single-row EXISTS against the SAME predicate `list_requestor_options` uses -
    a save must never materialise the whole eligible set just to test one id
    (that was thousands of rows over the wire per save on a large segment).
    `extra_ids` are always eligible (D6: the row's submitting contact + the
    currently-saved requestor).
    """
    raw = str(contact_id).strip() if contact_id not in (None, "") else ""
    if not raw:
        return False
    allowed_extra = {str(i).strip() for i in (extra_ids or []) if i}
    if raw in allowed_extra:
        return True
    hit = (
        db.query(RespondContact.id)
        .join(
            respond_contact_market_segments,
            respond_contact_market_segments.c.contact_id == RespondContact.id,
        )
        .join(
            MarketSegment,
            MarketSegment.code == respond_contact_market_segments.c.segment_code,
        )
        .filter(
            RespondContact.id == raw,
            MarketSegment.is_requestor_selectable.is_(True),
            MarketSegment.is_active.is_(True),
        )
        .first()
    )
    return hit is not None
