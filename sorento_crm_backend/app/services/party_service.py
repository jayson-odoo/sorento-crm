"""Who a contact is, which Dealer a Complaint belongs to, and who the Dealer's
salesperson is. One module, because three consumers already need the same answers
(the portal door, the notification spine, the dashboard flag) and none of them owns
the rule.

It deliberately does not live inside `portal_service`: that would tie "who is this
contact" to the portal, and the WhatsApp intake in S5 has no portal at all.

Three properties this module holds, each of which the obvious implementation breaks:

**Kind is derived, never stored.** A `party_kind` column would be a second source of
truth that can disagree with the bindings, and nothing would ever notice.

**Derivation is a pure function of the row.** No query, so it cannot return one kind
for a loaded row and another for a detached one, and it is safe inside a
list-serializer loop without an N+1.

**Precedence is data, not branches.** AC-B2 permits several bindings at once and
named no order, which made derivation a partial function: the portal, the
notification spine and the dashboard would each have resolved it their own way.
AC-B14 fixes it as narrowest-binding-wins. The top rung is unreachable until S6 lands
its binding, so it is declared rather than inferred - which is the point, because
otherwise the order stays undecided until exactly the moment somebody re-decides it
under delivery pressure.

The Site is NOT resolved here, and that is the AC-B3 rule rather than an omission: a
dealer's owner reporting a fault in his own home carries a dealer binding and a
residential Site on the same Complaint. Anything that derives the Site from the
customer record sends a technician to a shop.

The legacy account-category mapping lives at the bottom of this file, under a header
marking it for deletion. It briefly lived in its own module behind a star import,
because the S1 gate banned the bare substring `customer_type` here while another gate
test required a public function whose NAME contains it - a guard that dictated module
boundaries rather than measuring behaviour. The guard now matches attribute-access and
lookup-key patterns, so the code is laid out for the reader again.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.order import Customer, Order

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Vocabulary                                                                    #
# --------------------------------------------------------------------------- #

# Highest priority first (AC-B14). Narrowest binding wins: a technician is only ever
# bound deliberately and must never reach a dealer form (AC-F8 gives them today's
# jobs and nothing else); being a Sorento employee outranks being somebody's shop
# contact, because the employee relationship is the one that grants tools.
#
# All four members ship in S1 even though `technician` is unreachable until S6 lands
# its binding. The journey route is a PUBLIC, unauthenticated portal contract
# consumed by a frontend and by n8n, neither of which deploys atomically with the
# backend: a three-member response literal would make S6 a breaking change to
# OpenAPI, to the FE union type and to any exhaustive switch that would silently
# fall through to its default.
KIND_PRECEDENCE = ("technician", "staff", "dealer", "consumer")

# Which nullable binding on `respond_contacts` implies each kind. `consumer` is
# absent on purpose: it is the by-elimination answer and has no binding of its own.
# Kept as a table rather than an if-chain so S6 adds one entry and changes nothing
# else - not this function, not the endpoint, not the order.
BINDING_FOR_KIND: dict[str, str] = {
    "technician": "technician_id",  # deferred to S6 (AC-B13); read defensively below
    "staff": "user_id",
    "dealer": "customer_id",
}

# The five values `complaints.reported_by_role` may hold (AC-B6). Closed, so anything
# else is a typo with a home. Shares no vocabulary with KIND_PRECEDENCE by accident:
# a reporter role is not a party kind, and `cs` / `end_user` have no binding.
REPORTED_BY_ROLES = frozenset({"end_user", "dealer", "salesperson", "cs", "technician"})

# The legacy mapping and its import-time check live together at the bottom of this
# file, under the DEPRECATED header, so the drop slice removes one contiguous block.


# --------------------------------------------------------------------------- #
# Kind derivation (AC-B2, AC-B14, AC-B15)                                       #
# --------------------------------------------------------------------------- #


def derive_contact_kind(contact) -> str:
    """Return the party kind for a contact row. Pure, total, no query.

    `getattr(..., None)` rather than attribute access because the technician binding
    does not exist as a column until S6 (AC-B13). Reading it defensively now is what
    makes S6 a pure column addition.
    """
    for kind in KIND_PRECEDENCE:
        binding = BINDING_FOR_KIND.get(kind)
        if binding is None:
            continue  # the by-elimination kind, handled by falling through
        if getattr(contact, binding, None):
            return kind
    return KIND_PRECEDENCE[-1]


# --------------------------------------------------------------------------- #
# Dealer and salesperson resolution (AC-B3, AC-B9, AC-B10)                      #
# --------------------------------------------------------------------------- #


def resolve_dealer_customer_id(db: Session, contact) -> Optional[str]:
    """The Dealer a contact reports on behalf of, or None for a Consumer.

    `db` is in the signature because every caller has one and the resolution rule may
    grow a lookup (S3's fuzzy shop-name match is the candidate); today it is the
    binding and nothing else, so the query count stays zero.
    """
    if contact is None:
        return None
    return getattr(contact, "customer_id", None) or None


def resolve_salesperson_user_id(db: Session, complaint) -> Optional[str]:
    """The Dealer's account owner, or None.

    Reads `customers.account_owner_user_id` and nothing else (AC-B9). Orders are the
    seed, never the source: the seed script derives the account owner once, and
    falling back to an order at runtime would make the answer drift every time a new
    order lands.

    None is a real answer and is returned rather than guessed (AC-B10). About 770
    dealers have no orders and so no derivable owner; those Complaints are flagged
    `salesperson unresolved` and routed to the after-sales team lead by the
    notification spine, never silently dropped.
    """
    if complaint is None:
        return None
    customer_id = getattr(complaint, "customer_id", None)
    if not customer_id:
        return None
    owner = (
        db.query(Customer.account_owner_user_id)
        .filter(Customer.id == customer_id)
        .scalar()
    )
    return owner or None


# --------------------------------------------------------------------------- #
# The self-heal (AC-B5a)                                                        #
# --------------------------------------------------------------------------- #


def find_customer_by_order_number(db: Session, order_number: str) -> Optional[str]:
    """Resolve a quoted Sorento order number to its customer, or None.

    Exact match on the trimmed number. Fuzzy matching is deliberately not attempted:
    a consumer holding a dealer's own receipt quotes formats that do not exist in
    `orders` at all (AC-C12 lists six), and a near-miss there would bind them to the
    wrong Dealer, which is the single error this whole slice exists to avoid.
    """
    cleaned = (order_number or "").strip()
    if not cleaned:
        return None
    customer_id = (
        db.query(Order.customer_id)
        .filter(Order.order_number == cleaned)
        .order_by(Order.order_date.desc().nullslast(), Order.id.desc())
        .limit(1)
        .scalar()
    )
    return customer_id or None


def self_heal_dealer_binding(db: Session, contact: RespondContact, order_number: str) -> dict:
    """Bind an UNBOUND contact to the Dealer on a quoted order number.

    Returns `{"matched": bool, "bound": bool}`. Never raises for an unresolvable
    number: AC-C14's rule applies here first, and a 4xx would turn the self-heal into
    a wall for exactly the people it was not aimed at (a Consumer with a dealer's own
    receipt will type something that does not resolve).

    **An existing binding is never re-pointed.** AC-B5a repairs a contact nobody
    configured. A contact Sorento DID configure is a deliberate act, and moving them
    to another Dealer because somebody pasted an order number would silently re-route
    their complaints, their notifications and their salesperson. The write lives here
    rather than on the route so the WhatsApp intake gets the same rule for free
    (ADR-0013 rule 7: a guard on the routes is not a guard).
    """
    customer_id = find_customer_by_order_number(db, order_number)
    if customer_id is None:
        return {"matched": False, "bound": False}
    if getattr(contact, "customer_id", None):
        return {"matched": True, "bound": False}
    contact.customer_id = customer_id
    db.commit()
    db.refresh(contact)
    logger.info(
        "portal self-heal bound contact %s to customer %s from an order number",
        contact.id,
        customer_id,
    )
    return {"matched": True, "bound": True}


# --------------------------------------------------------------------------- #
# Display                                                                       #
# --------------------------------------------------------------------------- #


def dealer_display_name(db: Session, contact) -> Optional[str]:
    """The Dealer's human-readable name, or None.

    Named, never identified: the portal is a frontend and no uuid may reach it.
    """
    customer_id = resolve_dealer_customer_id(db, contact)
    if not customer_id:
        return None
    return (
        db.query(Customer.customer_name)
        .filter(Customer.id == customer_id)
        .scalar()
    )


# =========================================================================== #
# DEPRECATED - the one-release legacy shim. Delete this whole block, and       #
# nothing above it, when `complaints.customer_type` is dropped (AC-B6).        #
# =========================================================================== #
#
# AC-B6 leaves the legacy free-text account category in place, read-only, for
# exactly one release. This maps it to a `reported_by_role` and is the only part
# of S1 with a stated expiry.
#
# **Unrecognised and blank map to None, never to a role.** AC-B16: a backfill
# that guesses cannot be told from a fact afterwards. `Project` (24 live rows),
# `SMC` (7) and `E Commerce` (1) are account categories or channels, not
# reporters, and the 3 NULLs assert nothing at all. `reported_by_role` is
# nullable precisely so they can stay honest. The plan's "the 7 blanks become
# cs" was wrong twice: the 7 was the SMC count, and `cs` would have asserted
# Customer Service reported those complaints.
#
# **`Salesperson` is in the map and was never in the lookup set.** The configured
# `complaints_customer_type` options are Dealer / Project / SMC / E Commerce /
# End User; 5 live rows nonetheless say `Salesperson` (AC-B17). A mapping derived
# from the configured options alone silently misses them.
#
# The SQL twin lives in `alembic/versions/316_after_sales_parties.py` and is a
# frozen snapshot on purpose: a migration that imports application code breaks
# the day that code is deleted, which for this block is scheduled. Change one,
# change the other, in the same commit.

# Normalized legacy value -> reported_by_role. Anything absent maps to None.
_ROLE_BY_LEGACY_VALUE: dict[str, str] = {
    "dealer": "dealer",
    "end user": "end_user",
    "enduser": "end_user",
    "salesperson": "salesperson",
    "sales person": "salesperson",
    "cs": "cs",
    "customer service": "cs",
    "technician": "technician",
}

_SEPARATORS = re.compile(r"[\s_\-]+")


def _normalize_legacy(value: Optional[str]) -> str:
    """Case, whitespace and separator tolerant: the column is free text today."""
    if not value:
        return ""
    return _SEPARATORS.sub(" ", str(value).strip().lower()).strip()


def reported_by_role_from_customer_type(value: Optional[str]) -> Optional[str]:
    """Map one legacy account-category string to a role, or to None.

    Total: every input has an answer, and the answer for anything unrecognised is
    None rather than a default role.
    """
    return _ROLE_BY_LEGACY_VALUE.get(_normalize_legacy(value))


def legacy_role_values() -> frozenset:
    """Every role this shim can emit."""
    return frozenset(_ROLE_BY_LEGACY_VALUE.values())


# Fail at import rather than write an unknown role during the backfill window.
_unknown = legacy_role_values() - REPORTED_BY_ROLES
if _unknown:  # pragma: no cover - a wiring error, not a runtime branch
    raise RuntimeError(
        f"The legacy shim maps to role(s) outside REPORTED_BY_ROLES: {sorted(_unknown)}"
    )
