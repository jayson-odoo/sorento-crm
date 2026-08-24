"""Deriving candidate sets from the shape of the catalogue's codes.

Sorento's two-piece water closets name their parts by putting a role letter
inside the code: `SRTWCX8608-RL` is the pedestal, `SRTWCY8608` the cistern, and
`SRTWC8608-SC` the seat cover. The code the flyer prints, `SRTWC8608-RL`, is the
pedestal's with the role letter taken out - and no product carries it. That is
the whole derivation: read the role, group by family, and propose the code the
family is missing.

The pass WRITES NOTHING. It stores candidates and a person ticks the ones that
are right (UAC D14). The role labels in this feature's own design came out
inverted at the start, which is the argument against a regex that writes by
itself: it would have propagated that across 94 rows before anybody looked.

`derive_candidates` is pure - a sequence of plain rows in, a list of candidates
out, no session and no ORM object - so every rule below is a row in a table test
rather than a fixture.

UAC group H: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
Plan: `documentation/plans/master-data/PLAN-product-sets.md` section 7.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

# `SRTWCX8608-RL` -> prefix SRTWC, role X, number 8608, rest `-RL`.
#
# The prefix is NON-GREEDY so the role letter is the FIRST X or Y that a number
# follows, not the last one the brand happens to contain. Greedy would read
# `SRTWCX8608` as prefix `SRTWCX` and then find no role at all.
ROLE_INFIX = re.compile(r"^(?P<prefix>[A-Z]{2,8}?)(?P<role>[XY])(?P<number>\d{3,5})(?P<rest>.*)$")

# `SRTWC8608-SC` -> prefix SRTWC, number 8608, rest `-SC`. An accessory carries
# no role letter; its role is a token in the tail.
NO_INFIX = re.compile(r"^(?P<prefix>[A-Z]{2,8})(?P<number>\d{3,5})(?P<rest>.*)$")

#: The anchor: the pedestal or the bowl. It carries the flyer's code and, in this
#: catalogue, the whole assembly's price.
ANCHOR = "X"
#: The cistern.
CISTERN = "Y"
#: Seat cover, fitting, pan connector, lid. Only `SC` is proposed as a member
#: today - the model permits an `FT` and no set ships with one (UAC "out of
#: scope") - but all four are recognised so a spare part is classified rather
#: than mistaken for a half of the assembly itself. `LID` earns its place the
#: hard way: `CWCX605-LID` ("CABANA WC LID ONLY") wears an X and was proposed as
#: the anchor of `CWC605-LID`, paired with the real cistern.
SEAT_COVER = "SC"
ACCESSORY_ROLES = (SEAT_COVER, "FT", "PS", "LID")


@dataclass(frozen=True)
class CatalogueRow:
    """One product, as the derivation needs it: a code, words and a price.

    A plain row rather than the ORM object, so the rule cannot accidentally reach
    for a relationship, a company or a session it has no business reading.
    """

    product_code: str
    description: Optional[str] = None
    list_price: Optional[Decimal] = None
    #: Read here because a retired row must never be PROPOSED. That is a
    #: different question from D8, which governs a member that goes discontinued
    #: after the set exists: there the set survives and the member is flagged.
    is_discontinued: bool = False


@dataclass(frozen=True)
class CandidateMember:
    product_code: str
    quantity: Decimal
    contributes_to_price: bool
    sort_order: int


@dataclass(frozen=True)
class Candidate:
    family_key: str
    set_code: str
    name: str
    members: tuple[CandidateMember, ...]


@dataclass(frozen=True)
class _Part:
    """A catalogue row that parsed into a family and a role."""

    row: CatalogueRow
    family_key: str
    role: str
    #: The tail after the number, split on `-`, e.g. `SRTWCX8608-P-RL` -> P, RL.
    #: What tells the S-trap pedestal's cistern from the P-trap one's.
    tokens: tuple[str, ...]
    #: The code with the role letter removed. Only meaningful for an anchor: it
    #: is exactly what the flyer prints.
    bare_code: str


def derive_candidates(
    products: Sequence[Any], *, taken_codes: Iterable[str]
) -> list[Candidate]:
    """One candidate per anchor, for every family holding an anchor and a cistern.

    `taken_codes` is every code that must not be proposed: every existing product
    code and every existing product-set code for the company. It is what makes
    re-running the pass leave an applied set alone (AC-H.3), and what stops a set
    being proposed for a family whose bare code the catalogue already carries.
    """
    taken = {str(code).strip().upper() for code in taken_codes if code}

    families: dict[str, list[_Part]] = {}
    seen_codes: set[str] = set()
    for row in products:
        code = (getattr(row, "product_code", None) or "").strip()
        if not code:
            continue
        # A discontinued row is never proposed as an anchor, a cistern or an
        # accessory, and a family left without an anchor or without a cistern
        # simply yields no candidate. Token overlap outranks everything in
        # `_best_match`, so a retired placeholder beat its own replacement:
        # `SRTWC188-P-180` named `SRTWCY188-P`, whose description reads
        # "****PLS USE CODE  SRTWCY188", because the live row shares no `-P`.
        #
        # NOT the same question as D8. D8 is about a member that goes
        # discontinued AFTER the set exists - that set survives, the member is
        # flagged and complete sets reads 0. This is about what to propose in
        # the first place, where a retired code is simply the wrong answer.
        if getattr(row, "is_discontinued", False):
            continue
        # The same code can legitimately reach here twice - Sorento and Mocha
        # carry identical codes, so an unscoped read returns both rows. First one
        # wins so the output is deterministic either way.
        if code.upper() in seen_codes:
            continue
        seen_codes.add(code.upper())

        part = _classify(row, code)
        if part is not None:
            families.setdefault(part.family_key, []).append(part)

    candidates: list[Candidate] = []
    for family_key in sorted(families):
        parts = families[family_key]
        anchors = [p for p in parts if p.role == ANCHOR]
        cisterns = [p for p in parts if p.role == CISTERN]
        seats = [p for p in parts if p.role == SEAT_COVER]
        # A set names an assembly. One half of one is not an assembly, and this
        # is what keeps the pass off the roughly 20,000 codes that carry no role.
        if not anchors or not cisterns:
            continue

        for anchor in sorted(anchors, key=lambda p: p.row.product_code):
            if anchor.bare_code.upper() in taken:
                continue
            members = [_member(anchor, sort_order=0, contributes=_has_price(anchor))]
            members.append(_member(_best_match(anchor, cisterns), sort_order=1, contributes=False))
            if seats:
                members.append(
                    _member(_best_match(anchor, seats), sort_order=2, contributes=False)
                )
            candidates.append(
                Candidate(
                    family_key=family_key,
                    set_code=anchor.bare_code,
                    name=_name_for(anchor),
                    members=tuple(members),
                )
            )

    return candidates


def _classify(row: Any, code: str) -> Optional[_Part]:
    """The family and the role a code declares, or None when it declares neither."""
    catalogue_row = row if isinstance(row, CatalogueRow) else CatalogueRow(
        product_code=code,
        description=getattr(row, "description", None),
        list_price=getattr(row, "list_price", None),
        is_discontinued=bool(getattr(row, "is_discontinued", False)),
    )

    infix = ROLE_INFIX.match(code.upper())
    if infix:
        prefix, role, number, rest = (
            infix.group("prefix"),
            infix.group("role"),
            infix.group("number"),
            infix.group("rest"),
        )
        tokens = _tokens(rest)
        # The accessory TOKEN wins over the role LETTER, on this branch too.
        # `CWCX605-LID` is the CWC605 assembly's lid, not its pedestal, and
        # `CWCY605-FT` its fitting rather than its cistern; reading the letter
        # first proposed the lid as an anchor and paired it with the cistern.
        return _Part(
            row=catalogue_row,
            family_key=f"{prefix}{number}",
            role=_accessory_role(tokens) or role,
            tokens=tokens,
            # Taken off the ORIGINAL code, not the upper-cased match, so a
            # lower-case catalogue row proposes the code as it is actually
            # written rather than shouted.
            bare_code=code[: infix.start("role")] + code[infix.end("role") :],
        )

    plain = NO_INFIX.match(code.upper())
    if not plain:
        return None
    tokens = _tokens(plain.group("rest"))
    role = _accessory_role(tokens)
    if role is None:
        return None
    return _Part(
        row=catalogue_row,
        family_key=f"{plain.group('prefix')}{plain.group('number')}",
        role=role,
        tokens=tokens,
        bare_code=code,
    )


def _tokens(rest: str) -> tuple[str, ...]:
    return tuple(token for token in rest.split("-") if token)


def _accessory_role(tokens: tuple[str, ...]) -> Optional[str]:
    """The spare-part role the tail names, or None when it names none."""
    return next((token for token in ACCESSORY_ROLES if token in tokens), None)


def _best_match(anchor: _Part, candidates: list[_Part]) -> _Part:
    """The part whose modifiers overlap the anchor's most.

    `SRTWCX8608-RL-WEPLS` takes `SRTWCY8608-WEPLS` because they share WEPLS;
    `SRTWCX8608-RL` takes the plain `SRTWCY8608` because neither cistern shares
    anything with it and the shortest code wins. Ties break on length and then
    lexically so the pass is deterministic - a proposal that changes between two
    runs over the same catalogue is unreviewable.
    """
    anchor_tokens = set(anchor.tokens)
    return min(
        candidates,
        key=lambda part: (
            -len(anchor_tokens & set(part.tokens)),
            len(part.row.product_code),
            part.row.product_code,
        ),
    )


def _member(part: _Part, *, sort_order: int, contributes: bool) -> CandidateMember:
    return CandidateMember(
        product_code=part.row.product_code,
        quantity=Decimal("1"),
        contributes_to_price=contributes,
        sort_order=sort_order,
    )


def _has_price(part: _Part) -> bool:
    """Whether the anchor carries a price worth calling the set's basis.

    Tick the anchor, and ONLY the anchor. Sorento parks the whole assembly's
    price on the pedestal (1180.00) while the cistern reads 0.00, and the seat
    cover's 85.00 is its standalone spare-part price - ticking that too would
    charge for the same seat twice. An anchor reading 0.00 ticks nothing, so the
    candidate reports its price as absent rather than as RM 0.00: a price of zero
    and a missing price are different facts.
    """
    price = part.row.list_price
    if price is None:
        return False
    return (price if isinstance(price, Decimal) else Decimal(str(price))) > 0


def _name_for(anchor: _Part) -> str:
    """The anchor's description with its own code taken out of it.

    "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM) SRTWCX8608-RL" becomes
    "SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)". No cleverer word surgery
    than that: a reviewer renames it if they care, and a guess that mangles two
    thirds of the catalogue costs more to check than to fix.
    """
    description = (anchor.row.description or "").strip()
    if not description:
        return anchor.bare_code
    without_code = re.sub(
        re.escape(anchor.row.product_code), " ", description, flags=re.IGNORECASE
    )
    collapsed = re.sub(r"\s+", " ", without_code).strip()
    return collapsed or anchor.bare_code


# ------------------------------------------------------------- the service
#
# Everything above is the rule. Everything below connects it to a database, a
# company scope and the review screen, and does no deriving of its own.

from uuid import UUID as _UUID  # noqa: E402

from sqlalchemy.orm import Session, selectinload  # noqa: E402

from app.models.company import Company  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.product_set import ProductSet  # noqa: E402
from app.models.product_set_proposal import (  # noqa: E402
    ProductSetProposal,
    ProductSetProposalBatch,
)
from app.models.user import User  # noqa: E402
from app.services.company_scope import (  # noqa: E402
    get_company_scope,
    resolve_write_company_id,
)
from app.services.error_handler import AppException  # noqa: E402
from app.services.product_set_service import ProductSetService  # noqa: E402

#: Refusals a reviewer reads on a toast, so they are sentences rather than codes.
REFUSAL_UNKNOWN = (
    "it is no longer in the current batch. Scan the catalogue again to refresh it"
)
REFUSAL_CODE_TAKEN = "a set with that code already exists for this company"
REFUSAL_MEMBER_GONE = "one of its members is no longer in the catalogue"

#: What a refusal names when the id belongs to no proposal this company can see.
#: A label, deliberately not a code: reading the foreign proposal to fetch its
#: real code would leak another company's catalogue into this one's screen.
UNKNOWN_LABEL = "That proposal"


class ProductSetProposalService:
    """Run the pass, read the open batch, apply what somebody ticked.

    Company scope is NOT an argument. Every read is ORM, so `do_orm_execute`
    applies the caller's scope: the catalogue the pass sees, the sets it checks
    against and the batch it writes all belong to the caller's company, which is
    what keeps two companies carrying the same codes from proposing each other's
    parts (AC-H.4).
    """

    def __init__(self, db: Session):
        self.db = db

    # ----------------------------------------------------------------- running

    def run(self, *, created_by: Optional[str]) -> dict:
        """Derive candidates and REPLACE the company's open batch. Writes no set."""
        self._require_one_company()
        products = (
            self.db.query(Product)
            .filter(Product.product_code.isnot(None))
            .order_by(Product.product_code.asc())
            .all()
        )
        rows = [
            CatalogueRow(
                product_code=p.product_code,
                description=p.description,
                list_price=p.list_price,
                is_discontinued=bool(getattr(p, "is_discontinued", False)),
            )
            for p in products
        ]
        # FIRST wins, matching the dedupe inside `derive_candidates`. An
        # all-companies scope returns the same code twice, and the two halves
        # disagreeing would store a member id from one company for a candidate
        # derived from the other.
        by_code: dict[str, Product] = {}
        for p in products:
            by_code.setdefault((p.product_code or "").upper(), p)

        taken = {(p.product_code or "").upper() for p in products}
        taken |= {(s.set_code or "").upper() for s in self.db.query(ProductSet).all()}

        candidates = derive_candidates(rows, taken_codes=taken)

        # One open batch per company. A second list alongside the first would
        # leave the reviewer choosing which of two answers about the same
        # catalogue to believe.
        for previous in self.db.query(ProductSetProposalBatch).all():
            self.db.delete(previous)
        self.db.flush()

        batch = ProductSetProposalBatch(created_by=created_by)
        self.db.add(batch)
        self.db.flush()

        for candidate in candidates:
            self.db.add(
                ProductSetProposal(
                    batch_id=batch.id,
                    family_key=candidate.family_key,
                    set_code=candidate.set_code,
                    name=candidate.name,
                    members=[
                        {
                            "product_id": by_code[m.product_code.upper()].id,
                            "quantity": str(m.quantity),
                            "contributes_to_price": m.contributes_to_price,
                            "sort_order": m.sort_order,
                        }
                        for m in candidate.members
                    ],
                )
            )
        self.db.commit()
        # Just written, so the read cannot miss it; `or batch` keeps this total
        # without an assert.
        return self._serialize(self._batch() or batch)

    # ----------------------------------------------------------------- reading

    def current(self) -> Optional[dict]:
        """The open batch, hydrated, or None when no pass has ever run.

        No batch and a batch that found nothing are different facts, and the
        second one is the good news: every family already has a set.
        """
        batch = self._batch()
        return None if batch is None else self._serialize(batch)

    # ---------------------------------------------------------------- applying

    def apply(self, proposal_ids: list[str], *, applied_by: Optional[str]) -> dict:
        """Create a set per ticked proposal, and name every refusal.

        IDS ONLY. The set code, the name and the members come off the stored
        proposal, never off the request body, so the screen cannot write a set
        the pass did not derive.
        """
        self._require_one_company()
        batch = self._batch()
        # Only well-formed ids reach the query: Postgres refuses to compare a
        # UUID column with "not-a-uuid" and the whole apply would 500 on one bad
        # entry rather than refusing it. A malformed id is a guaranteed-missing
        # row, so it takes the same refusal as a stale one.
        wanted = [str(pid) for pid in proposal_ids if _is_uuid(pid)]
        stored: dict[str, dict] = {}
        if batch is not None and wanted:
            for proposal in (
                self.db.query(ProductSetProposal)
                .filter(ProductSetProposal.batch_id == batch.id)
                .filter(ProductSetProposal.id.in_(wanted))
                .all()
            ):
                stored[str(proposal.id)] = {
                    "set_code": proposal.set_code,
                    "name": proposal.name,
                    "members": list(proposal.members or []),
                }

        applied: list[dict] = []
        refused: list[dict] = []
        for proposal_id in proposal_ids:
            proposal = stored.get(str(proposal_id))
            # An id this company's open batch does not hold: stale, already
            # applied, or another company's. One answer for all three, because a
            # scoped reader must not learn which.
            if proposal is None:
                refused.append(
                    {
                        "proposal_id": str(proposal_id),
                        "set_code": UNKNOWN_LABEL,
                        "reason": REFUSAL_UNKNOWN,
                    }
                )
                continue

            payload = self._payload_for(proposal)
            if payload is None:
                refused.append(
                    {
                        "proposal_id": str(proposal_id),
                        "set_code": proposal["set_code"],
                        "reason": REFUSAL_MEMBER_GONE,
                    }
                )
                continue

            try:
                # Through the EXISTING service, so authoring has exactly one
                # write path and a set born here is indistinguishable from one
                # somebody typed.
                ProductSetService(self.db).create(payload, created_by=applied_by)
            except AppException as exc:
                # The code was taken between propose and apply, or a member
                # stopped resolving. Refused per proposal and never a 500: the
                # other ticked candidates still land.
                self.db.rollback()
                refused.append(
                    {
                        "proposal_id": str(proposal_id),
                        "set_code": proposal["set_code"],
                        "reason": _readable(exc),
                    }
                )
                continue

            # It has become a set. Leaving it in the batch would offer it again
            # and invite a duplicate (AC-H.3).
            self.db.query(ProductSetProposal).filter(
                ProductSetProposal.id == proposal_id
            ).delete(synchronize_session=False)
            self.db.commit()
            applied.append(
                {"proposal_id": str(proposal_id), "set_code": proposal["set_code"]}
            )

        return {"applied": applied, "refused": refused}

    # ---------------------------------------------------------------- internals

    def _require_one_company(self) -> str:
        """The one company this pass is for, or a refusal.

        An `X-API-Key` principal carries no contact identity and resolves to the
        `None` scope, which means ALL companies - and every part of this pass
        reads that as a licence it must not have. It would derive over both
        catalogues at once, pick an arbitrary row per duplicated code, treat a
        family already set in one company as taken for the other, stamp the batch
        onto whichever company is incumbent, and hand a set of one company's
        products to the other. There is no correct answer to "which company is
        this batch for" when the caller names two, so the pass declines to guess.

        `resolve_write_company_id` already refuses an unset, empty or
        multi-company scope with the right message, so `None` is handed to it as
        the empty scope and takes that same refusal rather than a second one
        worded differently. It is the ONE case that function deliberately lets
        through, mapping it to the incumbent company (see its own note).
        """
        scope = get_company_scope(self.db)
        company_id = resolve_write_company_id(frozenset() if scope is None else scope)
        # `resolve_write_company_id` can answer None only under the test-only
        # escape hatch, which this pass has no legacy rows to accommodate.
        if company_id is None:
            raise AppException(
                status_code=400,
                message=(
                    "Cannot create this record without an active company. "
                    "A single active company is required to stamp company_id."
                ),
                code="company_scope_required",
            )
        return company_id

    def _batch(self) -> Optional[ProductSetProposalBatch]:
        return (
            self.db.query(ProductSetProposalBatch)
            .options(selectinload(ProductSetProposalBatch.proposals))
            # `created_at` alone is no tiebreaker: two rows written in one
            # transaction share `now()` to the microsecond. The id ends the
            # ordering so "the latest batch" is one answer, not a coin toss.
            .order_by(
                ProductSetProposalBatch.created_at.desc(),
                ProductSetProposalBatch.id.desc(),
            )
            .first()
        )

    def _payload_for(self, proposal: dict) -> Optional[dict]:
        """The `ProductSetService.create` payload, addressed by code.

        Returns None when a member no longer resolves, which is a refusal rather
        than a partial set: a set missing its cistern is worse than no set.
        """
        members = proposal["members"]
        products = self._products_by_id([m.get("product_id") for m in members])
        if len(products) != len({m.get("product_id") for m in members}):
            return None
        return {
            "set_code": proposal["set_code"],
            "name": proposal["name"],
            "members": [
                {
                    "product_code": products[m["product_id"]].product_code,
                    "quantity": Decimal(str(m.get("quantity") or "1")),
                    "contributes_to_price": bool(m.get("contributes_to_price")),
                    "sort_order": m.get("sort_order", index),
                }
                for index, m in enumerate(members)
            ],
        }

    def _products_by_id(self, product_ids: Iterable[Optional[str]]) -> dict[str, Product]:
        wanted = [pid for pid in product_ids if pid]
        if not wanted:
            return {}
        rows = self.db.query(Product).filter(Product.id.in_(list(set(wanted)))).all()
        return {str(row.id): row for row in rows}

    def _serialize(self, batch: ProductSetProposalBatch) -> dict:
        """The batch as the review screen reads it.

        Codes, descriptions and prices are hydrated HERE, from `products`, rather
        than read back off the proposal: a stored price snapshot goes stale the
        moment somebody edits the product and becomes a second source of truth
        for the same number.

        Counts are derived from the rows for the same reason. A stored count that
        disagrees with the list under it sends people to debug the list.
        """
        proposals = sorted(batch.proposals, key=lambda p: (p.family_key, p.set_code))
        products = self._products_by_id(
            [m.get("product_id") for p in proposals for m in (p.members or [])]
        )

        rendered = [self._serialize_proposal(p, products) for p in proposals]
        return {
            "id": str(batch.id),
            "company_name": self._company_name(batch.company_id),
            "created_at": batch.created_at,
            "created_by_name": self._user_name(batch.created_by),
            "family_count": len({p["family_key"] for p in rendered}),
            "proposal_count": len(rendered),
            "proposals": rendered,
        }

    def _serialize_proposal(
        self, proposal: ProductSetProposal, products: dict[str, Product]
    ) -> dict:
        members = []
        computed: Optional[Decimal] = None
        for stored in proposal.members or []:
            product = products.get(str(stored.get("product_id")))
            # A member whose product has been removed outright is left out of the
            # view rather than rendered as a UUID. Applying it is refused by
            # name, which is where the reviewer learns about it.
            if product is None:
                continue
            quantity = Decimal(str(stored.get("quantity") or "1"))
            contributes = bool(stored.get("contributes_to_price"))
            members.append(
                {
                    "product_code": product.product_code,
                    "description": product.description,
                    "list_price": product.list_price,
                    "quantity": quantity,
                    "contributes_to_price": contributes,
                    "sort_order": stored.get("sort_order", len(members)),
                    "is_discontinued": bool(getattr(product, "is_discontinued", False)),
                }
            )
            if contributes:
                price = product.list_price
                computed = (computed or Decimal("0")) + (
                    Decimal(str(price)) if price is not None else Decimal("0")
                ) * quantity

        return {
            "id": str(proposal.id),
            "family_key": proposal.family_key,
            "set_code": proposal.set_code,
            "name": proposal.name,
            "members": sorted(members, key=lambda m: m["sort_order"]),
            # None, never 0.00, when nothing is ticked. A price of zero and a
            # missing price are different facts.
            "computed_price": None if computed is None else computed.quantize(Decimal("0.01")),
        }

    def _company_name(self, company_id: Optional[str]) -> Optional[str]:
        if not company_id:
            return None
        row = self.db.query(Company).filter(Company.id == company_id).first()
        return row.name if row else None

    def _user_name(self, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        row = self.db.query(User).filter(User.id == str(user_id)).first()
        return (row.name or row.email) if row else None


def _is_uuid(value) -> bool:
    try:
        _UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _readable(exc: AppException) -> str:
    """The refusal a reviewer reads, lower-cased so it follows "was not created:"."""
    message = (getattr(exc, "message", None) or "").strip()
    if not message:
        return REFUSAL_CODE_TAKEN
    return message[0].lower() + message[1:]


__all__ = [
    "Candidate",
    "CandidateMember",
    "CatalogueRow",
    "ProductSetProposalService",
    "derive_candidates",
]
