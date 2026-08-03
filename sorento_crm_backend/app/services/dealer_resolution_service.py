"""Resolving a printed shop name to a Dealer, by rules the S3-pre spike measured.

Full numbers: `documentation/plans/after-sales/S3-pre-extraction-accuracy.md`. In short,
over 38 real consumer-track receipts: 87% printed a readable shop name, 68% resolved to a
`customers` row exactly, and the three receipts that landed in the middle band each named a
real but WRONG dealer.

**The answer is a state, never a score.** The score distribution is bimodal - 26 receipts at
exactly 1.00 and nothing at all between 0.70 and 0.99 - so there is no gradient for a caller
to threshold. Handing out a float means every caller invents its own cutoff, and the cutoff
somebody eventually invents pre-fills one of those three wrong dealers. A wrong dealer shown
as resolved attributes a consumer's purchase to a shop that never sold it, inside the
sell-through ledger this module exists to build. That is the failure worth engineering
against, not the misses: a miss costs the consumer one edit (AC-C10a) and CS one look.

**One resolver, not one per caller.** The consumer portal, the CS review screen and any
later dealer-track path have to reach the same verdict for the same receipt, or the ledger
disagrees with itself.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

STATE_RESOLVED = "resolved"
STATE_CANDIDATE = "candidate"
STATE_UNMATCHED = "unmatched"

# Exact-after-normalisation only. Deliberately not "0.9-ish": the spike found NOTHING
# between 0.70 and 0.99, so anything below 1.0 is the middle band where the wrong dealers
# live. If a future measurement finds real matches in that gap, move this with the evidence.
RESOLVE_AT = 1.0

# Worth showing CS, not worth asserting. Below this a "suggestion" is noise - the document
# number mistaken for a shop name scored 0.16 against an unrelated company.
CANDIDATE_AT = 0.35

# Words every Malaysian company shares. Stripped from BOTH sides before comparing, because
# trigram similarity over full legal names measures how Malaysian a company is rather than
# which company it is: unstripped, "SORENTO SDN BHD" matched "SL & A SDN BHD" at 0.42.
_CORPORATE_NOISE: Tuple[str, ...] = (
    "sdn bhd", "sdn. bhd.", "sdn bhd.", "s/b", "bhd", "berhad", "sdn",
    "enterprise", "enterprises", "trading", "company", "co.", "co",
    "hardware", "marketing", "holdings", "resources", "supply", "supplies",
    "sanitary", "sanitaryware", "ceramic", "ceramics",
)

# Receipts print the branch the consumer walked into; `customers` stores the company.
# "(JLN IPOH BRANCH)", "[A/C III]", "(PUCHONG)". Stripping these lifted exact resolution
# from 23 to 26 of 38, and a branch is never what distinguishes two dealers.
_BRACKETED = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_BRANCH_WORDS = re.compile(r"\b(branch|cawangan|hq|head\s+office)\b", re.IGNORECASE)

# A shop name is letters. A string with no letters at all is a document number the
# extractor mislabelled - "B10-2-26050837" - and the honest answer for it is nothing,
# not the nearest of 3,284 rows.
_HAS_LETTERS = re.compile(r"[a-z]", re.IGNORECASE)


@dataclass(frozen=True)
class DealerMatch:
    """What the caller gets. `printed_name` always survives (AC-C14)."""

    state: str
    printed_name: Optional[str]
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    # Populated for `candidate` only: CS sees this, the consumer never does.
    suggestion_customer_id: Optional[str] = None
    suggestion_name: Optional[str] = None
    score: float = 0.0


def normalise_company_name(name: Optional[str]) -> str:
    """Strip everything two different companies would share, keep what tells them apart."""
    if not name:
        return ""
    value = _BRACKETED.sub(" ", str(name))
    value = _BRANCH_WORDS.sub(" ", value)
    value = re.sub(r"[^a-z0-9& ]+", " ", value.lower())
    for token in sorted(_CORPORATE_NOISE, key=len, reverse=True):
        value = re.sub(rf"\b{re.escape(token)}\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _trigrams(value: str) -> set:
    padded = f"  {value} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def _similarity(left: str, right: str) -> float:
    """pg_trgm's similarity, computed here because BOTH sides need normalising first.

    Doing it in SQL would need the normalisation as a Postgres function, which is a second
    copy of these rules in a second language - and the day the two drift, the portal and
    the CS screen name different dealers for the same receipt.
    """
    a, b = _trigrams(left), _trigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _candidates(db: Session) -> List[Tuple[str, str, str]]:
    """(customer_id, display_name, normalised) for every name a dealer is known by.

    Three columns, not one: a receipt prints the TRADING name while `customer_name` is
    often the registered entity. 3,284 customers is small enough to scan, and scanning
    keeps the normalisation in one language.
    """
    rows = db.execute(
        text(
            """
            SELECT id::text, customer_name, trading_name, registered_name
            FROM customers
            WHERE COALESCE(is_active, true) = true
            """
        )
    ).all()
    out: List[Tuple[str, str, str]] = []
    for customer_id, *names in rows:
        for name in names:
            if not name or not str(name).strip():
                continue
            normalised = normalise_company_name(name)
            if normalised:
                out.append((customer_id, str(name).strip(), normalised))
    return out


def resolve_dealer(db: Session, printed_name: Optional[str]) -> DealerMatch:
    """Which dealer, if any, printed this on their receipt."""
    raw = str(printed_name).strip() if printed_name else None
    if not raw or not _HAS_LETTERS.search(raw):
        # No name, or a document number wearing the name's place on the form.
        return DealerMatch(state=STATE_UNMATCHED, printed_name=raw)

    needle = normalise_company_name(raw)
    if not needle:
        # Everything printed was corporate boilerplate: "SDN BHD" and nothing else.
        return DealerMatch(state=STATE_UNMATCHED, printed_name=raw)

    try:
        candidates = _candidates(db)
    except Exception as exc:  # pragma: no cover - a lookup failure is not a match
        logger.warning("Dealer candidate load failed: %s", exc)
        return DealerMatch(state=STATE_UNMATCHED, printed_name=raw)

    best_score = 0.0
    best: Optional[Tuple[str, str, str]] = None
    for row in candidates:
        score = _similarity(row[2], needle)
        # Ties break on the display name so two identically-named dealers resolve the same
        # way every time. An ordering-dependent tie-break would let the ledger disagree
        # with itself across two identical receipts.
        if score > best_score or (score == best_score and best is not None and row[1] < best[1]):
            best_score, best = score, row

    if best is None:
        return DealerMatch(state=STATE_UNMATCHED, printed_name=raw)

    if best_score >= RESOLVE_AT:
        return DealerMatch(
            state=STATE_RESOLVED,
            printed_name=raw,
            customer_id=best[0],
            customer_name=best[1],
            score=best_score,
        )
    if best_score >= CANDIDATE_AT:
        return DealerMatch(
            state=STATE_CANDIDATE,
            printed_name=raw,
            suggestion_customer_id=best[0],
            suggestion_name=best[1],
            score=best_score,
        )
    return DealerMatch(state=STATE_UNMATCHED, printed_name=raw, score=best_score)
