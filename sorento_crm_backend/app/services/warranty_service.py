"""The deterministic warranty entitlement engine (AC-D4 to AC-D7, AC-D9, AC-D15
to AC-D21).

It answers one question - "what cover does this thing carry" - from four lookup
tables and a date, and it answers it the same way every time. One module owns the
algorithm because three callers are already known (the CS verdict panel, the
consumer portal, the policy-answer surface) and the moment two of them compute an
expiry the answers diverge.

`resolve` takes PLAIN VALUES, never a purchase row. That signature is what makes
the engine provable with no consumer table in existence, and it is the line
between this slice and the consumer module.

Seven rulings are encoded below. Each one is a place the acceptance criteria are
silent or self-contradictory, and each was decided rather than left to the caller,
because an engine that answers "not covered" for a reason nobody wrote down is
worse than one that refuses to answer.

1. **A gap in the policy calendar is not an absence of cover** (AC-D17). `resolve`
   NEVER returns an empty sequence. No policy in force yields exactly one
   `unknown`; a policy that says nothing about this Kind yields `no_term`. An
   empty list renders as "no cover" on every screen, which refuses a real customer
   because of a data-entry hole, and nothing anywhere says so. `unknown` is a
   calendar gap to fix; `no_term` is a scope question for the publisher; the two
   must not be collapsed or the only signal saying which is lost.

2. **The policy in force is judged on the PURCHASE date**, never today's. Clause
   16 lets the document be amended without notice, so judging by today's would
   retroactively change what somebody already bought.

3. **Overlapping policy windows are reachable by ordinary data entry**, so the
   winner is pinned: latest `effective_from`, ties broken on `id` ascending. The
   answering `policy_id` rides on every verdict, so an overlap is diagnosable from
   the output instead of invisible.

4. **Empty means "all defects", and so does NULL.** A term with no defect
   restriction is the normal case; forcing every row to enumerate every defect
   would be worse. Empty, NULL and populated-but-not-matching are three distinct
   behaviours, and a defect the caller never stated can never convict a restricted
   term (that is `unknown`, not `defect_not_covered`).

5. **Kind resolution is a total order** (AC-D20): explicit `priority` first (higher
   wins), then `KIND_RULE_SPECIFICITY`, then the longest matched value, then kind
   `code` ascending. Ambiguous data must never raise - a complaint would stop - and
   must never answer differently on two calls, or CS and the portal disagree about
   the same product.

6. **The expiry date itself is covered** (AC-D19), and refusal starts the next day.
   So does the purchase date. Customer-favourable where the documents were silent.

7. **Month arithmetic clamps, it never rolls forward.** 31 January plus one month
   is 29 February, not 2 March. Rolling gives a customer a day of cover they were
   not sold, or takes one away, depending on the month.

Clause 17 restricts cover to residential installations and is MODELLED, NOT
ENFORCED (AC-D15). `resolve` has nowhere to put an installation context on
purpose: no usage, no customer type, no site flag. 23 of 50 live Complaints are
Project cases, so a well-meaning branch would refuse half of them the day it
shipped.
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.warranty import (
    WarrantyKindRule,
    WarrantyPolicy,
    WarrantyProductKind,
    WarrantyTerm,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Vocabulary                                                                    #
# --------------------------------------------------------------------------- #

# Asia/Kuala_Lumpur, fixed UTC+8, no DST. Mirrors sla_service.MALAYSIA_TZ.
MALAYSIA_TZ = timezone(timedelta(hours=8))

VERDICT_COVERED = "covered"
VERDICT_EXPIRED = "expired"
VERDICT_DEFECT_NOT_COVERED = "defect_not_covered"
VERDICT_NO_TERM = "no_term"
VERDICT_UNKNOWN = "unknown"

# The closed set. A sixth value appearing quietly in one branch is the failure this
# constant exists to prevent.
VERDICTS = frozenset(
    {
        VERDICT_COVERED,
        VERDICT_EXPIRED,
        VERDICT_DEFECT_NOT_COVERED,
        VERDICT_NO_TERM,
        VERDICT_UNKNOWN,
    }
)

# AC-D2's four match types.
KIND_RULE_MATCH_TYPES = ("category", "model_prefix", "model_list", "series")

# "Most specific wins", made concrete (AC-D20). An explicit model list enumerates
# exactly which things it covers; a prefix covers a family; a series is a marketing
# grouping that spans families; a category is the whole merchandise bucket and is
# brand-split besides (ADR-0010).
#
# Declared as DATA, not inferred from the order of an if-chain, so it survives
# somebody adding a fifth match type: a new type with no declared rank is a silent
# coin flip, a new entry in this tuple is a decision somebody made on purpose.
KIND_RULE_SPECIFICITY = ("model_list", "model_prefix", "series", "category")

_SPECIFICITY_RANK = {match_type: rank for rank, match_type in enumerate(KIND_RULE_SPECIFICITY)}

# A match type nobody declared sorts last rather than raising. Bad data must not
# stop a complaint.
_UNRANKED = len(KIND_RULE_SPECIFICITY)


# --------------------------------------------------------------------------- #
# The verdict                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WarrantyVerdict:
    """One answer, about one part.

    The FIELD NAMES are the contract; every caller reads them and none of them
    should have to know whether this is a dataclass or a row.

    `policy_id` is on every verdict deliberately: without it an argument about a
    verdict cannot be settled without re-running the engine, and an overlapping
    policy window is invisible.
    """

    verdict: str
    part_name: Optional[str] = None
    expiry: Optional[date] = None
    is_lifetime: bool = False
    installation_included: bool = False
    kind_id: Optional[str] = None
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None
    term_id: Optional[str] = None
    duration_months: Optional[int] = None
    # How many months the registration bonus actually added. 0 when unregistered or
    # when the term carries no bonus, so "why is this three years" is answerable
    # from the verdict alone.
    bonus_months_applied: int = 0
    qualifications: Optional[str] = None
    exclusions: Optional[str] = None
    # Plain English, for the CS panel and for a log line. Never a substitute for the
    # verdict itself.
    reason: str = ""
    # Set only by resolve_replacement.
    replaced_on: Optional[date] = None


# --------------------------------------------------------------------------- #
# Dates                                                                         #
# --------------------------------------------------------------------------- #


def warranty_today() -> date:
    """Today, in Malaysian time.

    Which day it is decides an expiring claim. Computed from UTC the engine calls
    it yesterday for the first eight hours of every Malaysian day, so a claim made
    at 9am on the expiry date would be refused. Exposed as a function so `as_of`
    has ONE default and every caller shares it.
    """
    return datetime.now(MALAYSIA_TZ).date()


def add_months(start: date, months: int) -> date:
    """`start` plus `months`, clamped to the last valid day of the target month.

    31 January plus one month is 29 February in a leap year and 28 February
    otherwise, never 2 or 3 March. The rolling implementations give a customer a
    different expiry than the one implied by their receipt, in a direction that
    changes with the month.
    """
    total = (start.month - 1) + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# --------------------------------------------------------------------------- #
# Kind resolution (AC-D2, AC-D20, AC-D21)                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _RuleMatch:
    """A rule that matched, plus everything needed to rank it against another."""

    kind: WarrantyProductKind
    priority: int
    specificity: int
    matched_length: int
    kind_code: str

    @property
    def sort_key(self):
        # Higher priority first, then narrower match type, then the longer matched
        # value, then the kind code ascending. Total, and stable across processes,
        # which is all a tie-break has to be.
        return (-self.priority, self.specificity, -self.matched_length, self.kind_code)


def _matched_length(rule: WarrantyKindRule, product_code: str, category_code: str, product_name: str) -> Optional[int]:
    """How specifically `rule` matched, or None if it did not match at all.

    The length of the token that actually matched, so `SRTWC8152` beats `SRTWC` on
    the same product. Without it the answer depends on which row Postgres happened
    to return first.
    """
    value = (rule.match_value or "").strip()
    if not value:
        # An empty match value would match EVERYTHING - the same footgun as an empty
        # rule-engine `rules[]`. It matches nothing instead.
        return None

    match_type = (rule.match_type or "").strip().lower()

    if match_type == "category":
        return len(value) if category_code and value.lower() == category_code else None

    if match_type == "model_prefix":
        return len(value) if product_code and product_code.startswith(value.lower()) else None

    if match_type == "model_list":
        # AC-D2 prints the list comma-separated, with whitespace after the commas,
        # in a `text` column. An enumeration, never a prefix: a code that is not IN
        # it must not match it.
        for token in value.split(","):
            token = token.strip()
            if token and product_code and token.lower() == product_code:
                return len(token)
        return None

    if match_type == "series":
        # There is NO products.series column - `products` carries code, name,
        # category and brand and nothing else - so the product NAME is the only
        # place a series can be read from. A placeholder until real series data
        # exists (AC-D21).
        return len(value) if product_name and value.lower() in product_name else None

    # An undeclared match type matches nothing rather than raising.
    logger.warning("warranty kind rule %s has unknown match_type %r", rule.id, rule.match_type)
    return None


def resolve_kind(
    db: Session,
    *,
    product_code: Optional[str] = None,
    category_code: Optional[str] = None,
    product_name: Optional[str] = None,
) -> Optional[WarrantyProductKind]:
    """The Kind a product belongs to, or None.

    Needs no `products` row (AC-C17): the codes people actually report do not
    resolve to one, and deciding cover BEFORE the exact variant is pinned down is
    the entire justification for the Kind layer. An unmatched code returns None
    rather than raising - nothing in this journey blocks.

    Rules are ranked in Python rather than in SQL. There are tens of them, the
    ranking is four-deep, and two of the four match types (a comma-separated
    enumeration, a substring of a name) cannot be expressed as an index-using
    predicate anyway. Doing it here keeps the whole precedence order readable in
    one place.
    """
    code = (product_code or "").strip().lower()
    category = (category_code or "").strip().lower()
    name = (product_name or "").strip().lower()
    if not (code or category or name):
        return None

    rows = (
        db.query(WarrantyKindRule, WarrantyProductKind)
        .join(WarrantyProductKind, WarrantyProductKind.id == WarrantyKindRule.kind_id)
        .filter(WarrantyProductKind.is_active.isnot(False))
        .all()
    )

    matches: List[_RuleMatch] = []
    for rule, kind in rows:
        length = _matched_length(rule, code, category, name)
        if length is None:
            continue
        matches.append(
            _RuleMatch(
                kind=kind,
                priority=rule.priority or 0,
                specificity=_SPECIFICITY_RANK.get(
                    (rule.match_type or "").strip().lower(), _UNRANKED
                ),
                matched_length=length,
                kind_code=(kind.code or ""),
            )
        )

    if not matches:
        return None
    matches.sort(key=lambda m: m.sort_key)
    return matches[0].kind


# --------------------------------------------------------------------------- #
# Entitlement (AC-D4 to AC-D7, AC-D9, AC-D17 to AC-D19)                         #
# --------------------------------------------------------------------------- #


def policy_in_force(db: Session, purchase_date: date) -> Optional[WarrantyPolicy]:
    """The policy governing `purchase_date`, or None if the calendar has a hole.

    Both ends of the window are INCLUSIVE. A purchase made on the day a policy took
    effect is governed by that policy; the alternative leaves a one-day hole at
    every version change, and a hole is an `unknown` verdict handed to a customer
    for no reason.

    Company scoping is not applied here by hand and must not be: `WarrantyPolicy`
    is a `CompanyScopedMixin`, so the session's company scope is already injected
    into this SELECT by the global listener (AC-D16). Filtering again would be a
    second copy of the same rule that can disagree with the first.
    """
    return (
        db.query(WarrantyPolicy)
        .filter(WarrantyPolicy.effective_from <= purchase_date)
        .filter(
            or_(
                WarrantyPolicy.effective_to.is_(None),
                WarrantyPolicy.effective_to >= purchase_date,
            )
        )
        # Overlapping windows are reachable by ordinary data entry, so the most
        # recently published applicable policy answers - the one a human would have
        # believed was current when the sale happened. `id` breaks the last tie so
        # two calls can never disagree.
        .order_by(WarrantyPolicy.effective_from.desc(), WarrantyPolicy.id.asc())
        .first()
    )


def _normalized_defect_scope(raw: Optional[Iterable]) -> frozenset:
    """A term's defect scope as a comparable set. NULL and empty are IDENTICAL.

    They are different values in Postgres and the same intent here. Nobody will
    maintain the distinction across a seed, an admin form and a migration, and the
    version that does eventually refuses a claim because one row held NULL where
    its neighbour held `{}`.
    """
    if not raw:
        return frozenset()
    return frozenset(str(value).strip().lower() for value in raw if value)


def _judge_term(
    term: WarrantyTerm,
    policy: WarrantyPolicy,
    *,
    purchase_date: date,
    defect_type_id: Optional[str],
    registered: bool,
    as_of: date,
) -> WarrantyVerdict:
    """One term, one verdict. Defect scope is the first gate, the date the second.

    They are INDEPENDENT: a lifetime ceramic body that never expires can still
    refuse a defect it does not cover, and passing the defect gate hands the answer
    straight to the date rather than being the answer.
    """
    scope = _normalized_defect_scope(term.covered_defect_type_ids)
    bonus = (term.registration_bonus_months or 0) if registered else 0
    is_lifetime = bool(term.is_lifetime)

    # Lifetime wins over a duration that was also filled in: contradictory data, and
    # lifetime is the longer promise and the one the policy document prints.
    if is_lifetime:
        expiry = None
    elif term.duration_months is None:
        expiry = None
    else:
        expiry = add_months(purchase_date, term.duration_months + bonus)

    def _verdict(name: str, reason: str) -> WarrantyVerdict:
        return WarrantyVerdict(
            verdict=name,
            part_name=term.part_name,
            expiry=expiry,
            is_lifetime=is_lifetime,
            installation_included=bool(term.installation_included),
            kind_id=term.kind_id,
            policy_id=policy.id,
            policy_version=policy.version,
            term_id=term.id,
            duration_months=term.duration_months,
            bonus_months_applied=bonus if not is_lifetime else 0,
            qualifications=term.qualifications,
            exclusions=term.exclusions,
            reason=reason,
        )

    if scope:
        if defect_type_id is None:
            # Neither "covered" nor "defect_not_covered" is knowable. Treating "not
            # stated" as "not in the list" refuses a customer for a question they
            # were never asked; treating it as "in the list" promises cover that may
            # not exist. A complaint routinely arrives unclassified (AC-C14).
            return _verdict(
                VERDICT_UNKNOWN,
                "This term covers specific defect types and no defect type was stated.",
            )
        if str(defect_type_id).strip().lower() not in scope:
            return _verdict(
                VERDICT_DEFECT_NOT_COVERED,
                "The reported defect type is outside the defects this term covers.",
            )

    if is_lifetime:
        return _verdict(VERDICT_COVERED, "Lifetime cover on this part.")

    if expiry is None:
        # A half-entered term: `duration_months` is nullable and `is_lifetime`
        # defaults false, so this is one forgotten field away. Adding NULL months
        # raises (a 500 on a complaint) and treating NULL as zero tells the customer
        # their cover expired on the day they bought it. Neither is honest.
        return _verdict(
            VERDICT_UNKNOWN,
            "This term records neither a duration nor lifetime cover.",
        )

    if as_of <= expiry:
        return _verdict(VERDICT_COVERED, f"Covered to {expiry.isoformat()} inclusive.")
    return _verdict(VERDICT_EXPIRED, f"Cover ended on {expiry.isoformat()}.")


def resolve(
    db: Session,
    *,
    kind_id: str,
    purchase_date: date,
    defect_type_id: Optional[str] = None,
    registered: bool = False,
    as_of: Optional[date] = None,
) -> Sequence[WarrantyVerdict]:
    """Every promise this Kind carries on this purchase, one verdict per part.

    NEVER returns one answer for a product and NEVER returns an empty sequence.

    `registered` defaults to False because the default must be the SHORTER cover:
    defaulting to registered would quietly promise a year that was never sold, on
    every call that forgot the argument. Registration only ever lengthens cover and
    is never a precondition of it (ADR-0010, BRD over policy clause 3(b)).

    There is deliberately no parameter for installation context - see the module
    docstring on clause 17 (AC-D15).
    """
    as_of = as_of or warranty_today()

    policy = policy_in_force(db, purchase_date)
    if policy is None:
        # A purchase dated before every policy on record, or in a gap between two.
        # The engine CANNOT answer, which is not the same as the cover having run
        # out, and must never be reported as `expired` (AC-D17).
        return [
            WarrantyVerdict(
                verdict=VERDICT_UNKNOWN,
                kind_id=kind_id,
                reason=(
                    f"No warranty policy is on record as being in force on "
                    f"{purchase_date.isoformat()}."
                ),
            )
        ]

    terms = (
        db.query(WarrantyTerm)
        .filter(WarrantyTerm.policy_id == policy.id)
        .filter(WarrantyTerm.kind_id == kind_id)
        .all()
    )
    if not terms:
        # A DIFFERENT answer from `unknown`: the policy was found and consulted, and
        # it says nothing about this Kind. `policy_id` is what distinguishes them.
        return [
            WarrantyVerdict(
                verdict=VERDICT_NO_TERM,
                kind_id=kind_id,
                policy_id=policy.id,
                policy_version=policy.version,
                reason=(
                    f"Policy {policy.version} was in force but records no term for this "
                    "product kind."
                ),
            )
        ]

    verdicts = [
        _judge_term(
            term,
            policy,
            purchase_date=purchase_date,
            defect_type_id=defect_type_id,
            registered=registered,
            as_of=as_of,
        )
        for term in terms
    ]
    # Ordered by part name ascending: a total order that needs no extra column, and
    # one that happens to read correctly for a water closet. Sorted in Python, not
    # by the database, so the order cannot shift with the server's collation.
    # Without it the CS panel reshuffles between page loads.
    verdicts.sort(key=lambda v: ((v.part_name or ""), (v.term_id or "")))
    return verdicts


# --------------------------------------------------------------------------- #
# Replacement (AC-D7)                                                           #
# --------------------------------------------------------------------------- #


def resolve_replacement(
    *,
    source_expiry: Optional[date],
    source_is_lifetime: bool = False,
    replaced_on: date,
    as_of: Optional[date] = None,
) -> WarrantyVerdict:
    """A replaced part inherits the REMAINING cover and starts no new term.

    Policy clause 6 note: "the replaced Warranty Part does not carry a new
    warranty". So the source expiry is COPIED, never recomputed - the difference is
    invisible when the two happen to coincide and is years of free cover when they
    do not. Inheriting the date means inheriting its end, including one already
    past: a part replaced under goodwill after the term ran out does not acquire
    cover by being new.

    Takes NO session on purpose. A `db` here would mean it could re-derive the
    source expiry instead of copying it, which is exactly the recomputation this
    function exists to prevent, reintroduced through the back door.
    """
    as_of = as_of or warranty_today()

    if source_is_lifetime:
        return WarrantyVerdict(
            verdict=VERDICT_COVERED,
            expiry=None,
            is_lifetime=True,
            replaced_on=replaced_on,
            reason="Replacement of a lifetime part. Cover remains lifetime.",
        )

    if source_expiry is None:
        return WarrantyVerdict(
            verdict=VERDICT_UNKNOWN,
            expiry=None,
            replaced_on=replaced_on,
            reason="The source term has no expiry to inherit.",
        )

    covered = as_of <= source_expiry
    return WarrantyVerdict(
        verdict=VERDICT_COVERED if covered else VERDICT_EXPIRED,
        expiry=source_expiry,
        replaced_on=replaced_on,
        reason=(
            f"Inherited the source term's cover to {source_expiry.isoformat()}; "
            "the replacement starts no new term."
        ),
    )
