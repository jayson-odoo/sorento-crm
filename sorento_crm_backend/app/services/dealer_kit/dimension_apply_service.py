"""Writing a flyer's printed sizes onto the product master (S7.6).

Every other module in this feature reads. This one writes to ``products``, a
table the whole business quotes from, on the evidence of a PDF - so it is built
to refuse rather than to apply.

**The caller names codes. It never sends numbers.**
The millimetres come from the stored reading, resolved through the same
``match_reading`` the review screen was looking at. If a request could carry
figures, this would be an endpoint for writing anything at all into the product
master, reachable by anybody who can upload a PDF.

**A conflict is not a correction (PLAN D9).**
A card that disagrees with a value somebody entered deliberately is not evidence
that the master is wrong; it is evidence that one of the two is, and which one
is a decision a human makes. So a conflicting row is refused unless the request
says out loud that it is overwriting. A blank master row is a different act -
there is nothing to destroy - and needs no such confirmation. A HALF filled row
counts as a conflict, because completing it and silently correcting it would
otherwise be the same click.

**Nothing is applied that was not named.**
There is no "apply everything you found": an empty selection is a 422, not a
sweep over 425 candidates.

**Every code asked about is answered.**
Applied or refused, with the reason, one entry each. A response that reports 20
successes and stays quiet about the 3 that failed is the failure this shape
exists to prevent: nobody chases what they were not told about.

**No embedding event.** A product's embedded document is code, name, category,
brand, description and item type (``embedding_worker``); it carries no
dimension. Re-embedding after a size change would spend an API call to produce
the identical vector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.dealer_kit import FlyerReadingRecord
from app.models.product import Product
from app.services.dealer_kit.flyer_matching import (
    AGREES,
    CONFLICTS,
    DimensionCandidate,
)
from app.services.dealer_kit.flyer_reading_service import report_for

# Why a named code was not written. Each one sends a reviewer to a different
# place, which is the entire reason they are not one "failed".
CONFLICT_NOT_CONFIRMED = "conflict_not_confirmed"
ALREADY_MATCHES = "already_matches"
PRODUCT_NOT_FOUND = "product_not_found"
NOT_A_CANDIDATE = "not_a_candidate"

# A ceiling on one request. The real flyer prints 998 codes and 425 sizes, so
# this clears the largest honest selection several times over while still
# refusing a client that has decided to post its entire catalogue.
MAX_CODES = 2000


@dataclass(frozen=True)
class AppliedDimension:
    """One product whose size now says what the flyer says.

    ``previous_*`` is kept because it is the one answer nobody can get back out
    of the master afterwards: once 592 is overwritten with 590, the response is
    the only place the 592 still exists in front of the person who did it.
    """

    code: str
    product_code: str
    product_name: str
    pages: tuple[int, ...]
    length_mm: Decimal
    width_mm: Decimal
    height_mm: Decimal
    previous_length_mm: Optional[Decimal]
    previous_width_mm: Optional[Decimal]
    previous_height_mm: Optional[Decimal]
    was_conflict: bool


@dataclass(frozen=True)
class RefusedDimension:
    """One code that was asked for and not written, and why.

    ``message`` is written for a human reading a table, not for a log: it names
    the value that was protected, because "conflict" alone leaves a reviewer
    with no way to tell a refusal from a bug.
    """

    code: str
    reason: str
    message: str


@dataclass(frozen=True)
class DimensionApplyResult:
    applied: list[AppliedDimension] = field(default_factory=list)
    refused: list[RefusedDimension] = field(default_factory=list)


def normalise_codes(codes: list[str]) -> list[str]:
    """The codes actually asked about: trimmed, de-duplicated, in order.

    A code named twice is one product. Order is kept so the response reads in
    the order the caller ticked the rows.
    """
    seen: dict[str, None] = {}
    for raw in codes:
        code = (raw or "").strip()
        if code:
            seen.setdefault(code, None)
    return list(seen)


def apply_dimensions(
    db: Session,
    record: FlyerReadingRecord,
    *,
    codes: list[str],
    overwrite_conflicts: bool = False,
    user_id: Optional[str] = None,
) -> DimensionApplyResult:
    """Write the printed size of each NAMED code onto its product.

    The report is recomputed here rather than trusted from the client, and that
    recompute is the safety property: a row that read "master has no size" when
    the screen was drawn, and has since been filled in by somebody else, comes
    back a conflict and is refused. The alternative - believing the verdict the
    browser was holding - loses whatever was entered in between, and loses it
    silently.
    """
    wanted = normalise_codes(codes)
    if not wanted:
        # The route's schema refuses this first; the guard is here as well
        # because a service that sweeps on an empty list is one careless caller
        # away from rewriting the whole catalogue.
        return DimensionApplyResult()

    report = report_for(db, record)
    candidates = {entry.code: entry for entry in report.dimension_candidates}
    unmatched = {entry.code for entry in report.unmatched}

    to_write: list[DimensionCandidate] = []
    refused: list[RefusedDimension] = []

    for code in wanted:
        candidate = candidates.get(code)
        if candidate is None:
            refused.append(_not_a_candidate(code, unmatched))
            continue
        if candidate.verdict == AGREES:
            refused.append(
                RefusedDimension(
                    code=code,
                    reason=ALREADY_MATCHES,
                    message="The product master already holds this size.",
                )
            )
            continue
        if candidate.verdict == CONFLICTS and not overwrite_conflicts:
            refused.append(
                RefusedDimension(
                    code=code,
                    reason=CONFLICT_NOT_CONFIRMED,
                    message=(
                        "The product master holds "
                        f"{_printed(candidate.current_length_mm, candidate.current_width_mm, candidate.current_height_mm)}"
                        ", which is not what the flyer prints. Confirm the "
                        "overwrite to replace it."
                    ),
                )
            )
            continue
        to_write.append(candidate)

    applied = _write(db, to_write, user_id=user_id, refused=refused)
    return DimensionApplyResult(applied=applied, refused=refused)


def _not_a_candidate(code: str, unmatched: set[str]) -> RefusedDimension:
    """Why a code the report does not offer was not written.

    Split in two on purpose. "The product is gone" sends somebody to the product
    master; "the flyer prints no size for it" sends them to the paper. One
    reason covering both sends half of them to the wrong place.
    """
    if code in unmatched:
        return RefusedDimension(
            code=code,
            reason=PRODUCT_NOT_FOUND,
            message=(
                "No product in this company carries that code any more. "
                "It may have been deleted since the report was drawn."
            ),
        )
    return RefusedDimension(
        code=code,
        reason=NOT_A_CANDIDATE,
        message="This flyer prints no size for that code.",
    )


def _write(
    db: Session,
    candidates: list[DimensionCandidate],
    *,
    user_id: Optional[str],
    refused: list[RefusedDimension],
) -> list[AppliedDimension]:
    """One statement to load, one commit to write, and no partial transaction.

    The refusals decided above are the partial part of "partial success"; the
    writes themselves are all or nothing, so a database error cannot leave half
    a selection applied with a 200 in front of it.

    Products are loaded through the ordinary ORM so the company predicate lands
    on the query. A candidate resolved inside this scope cannot address another
    company's row, and a raw ``UPDATE`` here would pass every test in the suite
    while being able to.
    """
    if not candidates:
        return []

    rows = (
        db.query(Product)
        .filter(Product.id.in_([entry.product_id for entry in candidates]))
        .all()
    )
    by_id = {row.id: row for row in rows}

    now = datetime.utcnow()
    applied: list[AppliedDimension] = []

    for candidate in candidates:
        product = by_id.get(candidate.product_id)
        if product is None:  # pragma: no cover - the report just matched it
            refused.append(
                RefusedDimension(
                    code=candidate.code,
                    reason=PRODUCT_NOT_FOUND,
                    message="That product could not be read back for writing.",
                )
            )
            continue

        previous = (
            product.dimensions_length,
            product.dimensions_width,
            product.dimensions_height,
        )
        product.dimensions_length = candidate.printed_length_mm
        product.dimensions_width = candidate.printed_width_mm
        product.dimensions_height = candidate.printed_height_mm
        # Attribution matters more here than on most writes: the question people
        # ask afterwards is "who changed what this product measures", and the
        # audit listener answers the rest of it (``__audit_track__`` on Product).
        product.updated_by = user_id
        product.updated_at = now

        applied.append(
            AppliedDimension(
                code=candidate.code,
                product_code=product.product_code,
                product_name=product.product_name,
                pages=candidate.pages,
                length_mm=candidate.printed_length_mm,
                width_mm=candidate.printed_width_mm,
                height_mm=candidate.printed_height_mm,
                previous_length_mm=previous[0],
                previous_width_mm=previous[1],
                previous_height_mm=previous[2],
                was_conflict=candidate.verdict == CONFLICTS,
            )
        )

    db.commit()
    return applied


def _printed(
    length: Optional[Decimal], width: Optional[Decimal], height: Optional[Decimal]
) -> str:
    """``1700 x 800 x 592 mm``, with a blank where the master has nothing.

    Millimetres throughout, and stated in the message so nobody has to assume:
    ``products.dimensions_*`` holds millimetres, which is what the flyer prints,
    so nothing on this path converts anything.
    """
    return f"{_mm(length)} x {_mm(width)} x {_mm(height)} mm"


def _mm(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    # Trailing zeros come from Numeric(10, 2) and mean nothing to a reader.
    return f"{value.normalize():f}"
