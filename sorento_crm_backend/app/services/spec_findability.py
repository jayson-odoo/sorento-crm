"""Can a customer find this product by describing it?

The question the business actually asks, and the one the spec registry exists to answer:
open a flyer, read a card, say what is printed on it, and see whether that product comes
back. This runs that check over a whole flyer instead of one card at a time, and it does
it from several ANGLES, because "found" and "not found" is not the useful answer - where
the boundary sits is.

The angles, per card:

  card        the card's printed words, as free text. The only angle that can catch a
              spec we never derived: the other angles are built FROM what we derived, so
              a missing fact is absent from the question too and the product passes
              without it. "2-Ways" and "Rose Gold" hid here for exactly that reason.
  all         every spec the flyer states, together. The best case. A miss here is a
              ranking problem, not a vocabulary one.
  one:<key>   each stated spec alone. Says which single facts are worth anything: if
              "shower set" alone finds it, a customer barely has to try.
  without:<key>  everything except one. Says which spec is load-bearing - the one whose
              removal loses the product is the one doing the work.

The boundary is then readable per product: the smallest angle that finds it. A product
found by `one:product_type` is easy; one found only by `all` is fragile; one found by
nothing is a gap, and the report says whether the card stated something we never stored.

Repeatable per flyer on purpose. `source_id` already separates them, so the Cabana and
Mocha flyers are new rows, not new code.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.models.product_spec import (
    ProductFindabilityResult,
    ProductFindabilityRun,
)
from app.services.product_spec_search import search_specs

# How deep a result still counts as found. The picker shows five; this is deliberately
# wider, because a product sitting at 20 is a ranking problem worth seeing, while a
# product absent from 25 is a different problem entirely.
DEFAULT_WINDOW = 25

# Marketing furniture that is not a description of the product.
_NOISE = re.compile(
    r"\b(SCAN ME|WHILE STOCKS LAST|RECOMMENDED USAGE|WARRANTY|PWP|LP|NEW)\b",
    re.IGNORECASE,
)
_PRICE = re.compile(r"\bRM\s*[\d,]+\b", re.IGNORECASE)
# Anything shaped like a product code. Leaving the code in the query would turn a spec
# search into a code lookup, and every card would pass whether or not a single spec had
# been derived.
_CODE_LIKE = re.compile(r"\b[A-Z]{2,}[-\d][A-Z0-9\-]*\b")

# The customer says a sentence, not a spec sheet.
_PHRASE_WORDS = 24


def customer_phrase(card: str, code: str) -> str:
    """The card's words as a person would say them, with the code taken out."""
    said = (card or "").replace("\n", " ").replace("•", " ")
    said = _PRICE.sub(" ", said)
    said = _NOISE.sub(" ", said)
    said = said.replace(code, " ")
    said = _CODE_LIKE.sub(" ", said)
    said = re.sub(r"[^A-Za-z0-9./+\- ]", " ", said)
    said = re.sub(r"\s+", " ", said).strip()
    return " ".join(said.split()[:_PHRASE_WORDS])


@dataclass
class Angle:
    """One way of asking for a product."""

    name: str
    specs: list[dict] = field(default_factory=list)
    free_terms: list[str] = field(default_factory=list)
    spec_keys: list[str] = field(default_factory=list)


def angles_for(
    values: dict, provenance: dict, phrase: str, *, detail: bool = True
) -> list[Angle]:
    """Every way we will ask for one product.

    Structured angles are built from the specs the FLYER states. A spec that only the
    description mentions is not something the customer reading the card can say, so
    including it would flatter the result.

    `detail=False` asks only the two broad questions. The per-spec angles are what make
    a sweep expensive - a search takes about a second, and 756 cards times seventeen
    angles is four hours, which is not a thing anyone will press a button for. They are
    also only interesting where a card FAILED, so the sweep asks them there.
    """
    stated = [
        {"key": key, "value": (entry or {}).get("value")}
        for key, entry in sorted((values or {}).items())
        # brand is not a discriminator: near enough every row carries the same one.
        if key != "brand"
        and isinstance(entry, dict)
        and entry.get("value") is not None
        and (provenance.get(key) or {}).get("source") == "flyer"
    ]

    out: list[Angle] = []
    if phrase:
        out.append(Angle(name="card", free_terms=[phrase] + phrase.split()))
    if not stated:
        return out

    keys = [s["key"] for s in stated]
    out.append(Angle(name="all", specs=stated, spec_keys=keys))
    if not detail:
        return out
    for spec in stated:
        out.append(Angle(name=f"one:{spec['key']}", specs=[spec], spec_keys=[spec["key"]]))
    if len(stated) > 1:
        for spec in stated:
            rest = [s for s in stated if s["key"] != spec["key"]]
            out.append(
                Angle(
                    name=f"without:{spec['key']}",
                    specs=rest,
                    spec_keys=[s["key"] for s in rest],
                )
            )
    return out


def _rank_of(db: Session, code: str, angle: Angle, window: int) -> int | None:
    found = search_specs(
        db, specs=angle.specs, free_terms=angle.free_terms, limit=window
    )
    for position, candidate in enumerate(found.get("candidates") or [], start=1):
        if candidate.get("product_code") == code:
            return position
    return None


def _boundary(results: dict[str, int | None]) -> str:
    """The easiest question that finds this product.

    Read in order of how little the customer had to say: one spec, then the card's own
    words, then every spec at once. `none` means no angle found it, which is the only
    verdict that needs a person.
    """
    singles = [name for name, rank in results.items() if name.startswith("one:") and rank]
    if singles:
        # The strongest single spec, by rank.
        return min(singles, key=lambda n: results[n] or 10**6)
    if results.get("card"):
        return "card"
    if results.get("all"):
        return "all"
    return "none"


def run_findability(
    db: Session,
    *,
    source_id: str | None = None,
    window: int = DEFAULT_WINDOW,
    limit: int | None = None,
    commit: bool = True,
) -> dict:
    """Ask every card in a flyer for its own product, from every angle. Persist it.

    Persisted rather than printed because the point is to compare: the number after a
    vocabulary change is only meaningful next to the number before it.
    """
    rows = db.execute(
        sql_text(
            "SELECT f.product_code, f.text, f.source_label, f.source_id,"
            "       p.is_discontinued, ps.values, ps.provenance"
            "  FROM product_flyer_text f"
            "  JOIN products p ON p.product_code = f.product_code"
            "  LEFT JOIN product_specifications ps ON ps.product_id = p.id"
            " WHERE f.text <> ''"
            "   AND (:source_id IS NULL OR f.source_id = :source_id)"
            " GROUP BY f.product_code, f.text, f.source_label, f.source_id,"
            "          p.is_discontinued, ps.values, ps.provenance"
            " ORDER BY f.product_code"
        ),
        {"source_id": source_id},
    ).fetchall()
    if limit:
        rows = rows[:limit]

    run = ProductFindabilityRun(
        id=str(uuid.uuid4()),
        status="running",
        source_id=source_id or (rows[0].source_id if rows else None),
        source_label=(rows[0].source_label if rows else None),
        window=window,
        cards=0,
        found_by_card=0,
        found_by_specs=0,
        not_found=0,
    )
    db.add(run)
    # Committed before any searching, so the screen can find the run and watch it fill
    # rather than staring at a request that will not answer for half an hour.
    if commit:
        db.commit()
    else:
        db.flush()

    for index, row in enumerate(rows, start=1):
        phrase = customer_phrase(row.text, row.product_code)
        angles = angles_for(row.values or {}, row.provenance or {}, phrase, detail=False)
        if not angles:
            continue

        ranks = {a.name: _rank_of(db, row.product_code, a, window) for a in angles}
        # Only now, and only where the broad questions did not find it, is it worth
        # paying for the per-spec angles that say WHERE the boundary is.
        if not ranks.get("card") and not ranks.get("all"):
            for angle in angles_for(row.values or {}, row.provenance or {}, phrase)[2:]:
                ranks[angle.name] = _rank_of(db, row.product_code, angle, window)
        run.cards += 1
        if ranks.get("card"):
            run.found_by_card += 1
        if ranks.get("all"):
            run.found_by_specs += 1
        boundary = _boundary(ranks)
        if boundary == "none":
            run.not_found += 1

        db.add(
            ProductFindabilityResult(
                id=str(uuid.uuid4()),
                run_id=run.id,
                product_code=row.product_code,
                is_discontinued=bool(row.is_discontinued),
                phrase=phrase,
                boundary=boundary,
                # {"all": 1, "one:product_type": null, ...} - the whole shape, so the
                # screen can show WHICH way of asking failed without a second run.
                ranks=ranks,
            )
        )
        # Periodic, so a sweep that dies half way still shows what it learned.
        if commit and index % 25 == 0:
            db.commit()

    run.status = "complete"
    if commit:
        db.commit()
    else:
        db.flush()

    return {
        "run_id": run.id,
        "status": run.status,
        "source_label": run.source_label,
        "cards": run.cards,
        "found_by_card": run.found_by_card,
        "found_by_specs": run.found_by_specs,
        "not_found": run.not_found,
    }
