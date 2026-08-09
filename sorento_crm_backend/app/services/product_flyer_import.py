"""Take what the printed flyer says about each product code, so derivation can read it.

The product master's descriptions are abbreviation-heavy and often say only what a
thing IS. The A3 flyer says what it is MADE OF and what it COMES WITH, because that is
what sells it — measured against the live catalogue, of 998 codes printed on the
2025-2026 flyer:

    S/Steel 304              219 cards, 216 absent from that product's description
    Brass                    220 cards, 210 absent
    (POP UP WASTE)           194 cards, 180 absent
    Matt Black               152 cards, 147 absent
    Gunmetal                 103 cards, 102 absent
    With Drainer & Overflow   56 cards,  55 absent

So the flyer is not a nicer copy of the description, it is a different set of facts.

**It fills gaps, it never overrules.** The description is the business's own record; a
leaflet is a leaflet, and where the two disagree the master wins. A value that did come
from the flyer says so in its provenance, so the Specifications tab can show which
sentence produced it and nobody has to guess.

The reading itself belongs to the dealer-kit module (`dealer_kit.flyer_reading`), which
already parses the PDF into cards. This copies the text across rather than reaching into
that schema at derivation time: the catalog-wide job must not break because another
module's table is absent, and the copy is what makes the flyer's contribution auditable
after the fact.

Ticket: jayson-odoo/sorento-crm#102.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_spec import ProductFlyerText

logger = logging.getLogger(__name__)

# Lines that carry no specification: the price furniture a card always has, and bare
# numbers. Kept out so the stored text is only the sentences worth matching against.
_NOISE = re.compile(r"^(SP|RM|LP\s*:.*|NP\s*:.*|[\d,.\s%]+|RM\s*[\d,.]+)$", re.I)


def _spec_lines(card: dict) -> list[str]:
    lines = []
    for raw in card.get("lines") or []:
        line = " ".join(str(raw).split())
        if not line or _NOISE.match(line):
            continue
        lines.append(line)
    return lines


def import_flyer_reading(db: Session, reading_id: str, *, commit: bool = False) -> dict:
    """Copy one flyer reading's card text onto the product codes it names.

    Only codes that exist in the product master are stored: the 2025-2026 flyer prints
    37 codes that are not products (bundles and discontinued lines), and a row keyed on
    a code nothing joins to is a row nobody will ever look at again.
    """
    row = db.execute(
        sql_text(
            "SELECT filename, reading_json FROM dealer_kit.flyer_reading WHERE id = :id"
        ),
        {"id": reading_id},
    ).first()
    if row is None:
        return {"error": "reading_not_found", "imported": 0}

    filename, reading = row[0], row[1] or {}
    label = re.sub(r"[_\s]+", " ", filename.rsplit(".", 1)[0]).strip()

    known = {code for (code,) in db.query(Product.product_code).distinct().all()}
    existing = {r.product_code: r for r in db.query(ProductFlyerText).all()}

    # One code can appear on several cards (a range printed twice, a variant grid).
    # Their lines are merged rather than last-one-wins: two cards mentioning different
    # facts about one product are both true.
    #
    # AMBIGUOUS CARDS ARE SKIPPED. The reading assigns each card a code by position on
    # the page, and on a bundle tile - a sink printed with its tap, a basin with its
    # cabinet - the lines belong to SEVERAL products while the card carries one code.
    # Three separate cards in the 2025-2026 flyer are all labelled SRTKT73SS while their
    # text names SRTWT5830-BL, SRTKT1861SS and SRTKT71SS-GY. Attributing all of it to the
    # card's code taught the ranker that a tap is a mirror cabinet.
    #
    # Where a card's own lines name another real product code, there is no way to tell
    # from the reading which line describes which product, so nothing is taken from it.
    # Losing a fact is recoverable; publishing another product's material is not.
    collected: dict[str, list[str]] = {}
    unmatched: set[str] = set()
    ambiguous: set[str] = set()
    for page in reading.get("pages") or []:
        for card in page.get("cards") or []:
            code = str(card.get("code") or "").strip()
            if not code:
                continue
            if code not in known:
                unmatched.add(code)
                continue
            lines = _spec_lines(card)
            others = {
                token
                for line in lines
                for token in [line.strip().strip("().,").upper()]
                if token in known and token != code.upper()
            }
            if others:
                ambiguous.add(code)
                continue
            for line in lines:
                bucket = collected.setdefault(code, [])
                if line not in bucket:
                    bucket.append(line)

    written = 0
    for code, lines in collected.items():
        joined = ". ".join(lines)
        record = existing.get(code)
        if record is None:
            record = ProductFlyerText(product_code=code)
            db.add(record)
        record.source_label = label
        record.source_id = str(reading_id)
        record.lines = lines
        record.text = joined
        written += 1

    db.flush()
    if commit:
        db.commit()

    logger.info(
        "flyer import: %s codes from %r, %s unmatched, %s ambiguous (multi-code cards)",
        written, label, len(unmatched), len(ambiguous),
    )
    return {
        "source": label,
        "imported": written,
        "unmatched_codes": sorted(unmatched),
        "ambiguous_codes": sorted(ambiguous),
    }
