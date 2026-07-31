"""Read a printed flyer well enough to seed a catalogue from it.

Sorento's catalogue already exists: 36 A3 pages of finished design that somebody
spent weeks laying out. Rebuilding it block by block in the builder is the single
biggest reason the Kit would sit unused, so this module reads the PDF and hands
back the STRUCTURE a page document can be built from.

**Pure by design.** Bytes in, a reading out. No database, no HTTP, no writes.
Matching a code to a product, suggesting a near miss, seeding a version: all of
that is the next slice. Keeping them apart is what makes this one exhaustively
testable against the real document rather than a synthetic one.

**Prices read here are a reading aid, and nothing more.** The offer price a
brochure shows comes from the PROMOTION the brochure is linked to, never from
this module, for two reasons. The promotion is the system's own record of what
was offered, to whom, between which dates. And reading prices off a page is
demonstrably lossy: 1,081 cards in the real flyer yield a list price but only
660 an offer price, because the typesetter sets the figure wherever the artwork
leaves room. `SRTWC286-SH` prints "SP RM 599" in a place this module's column
band does not reach, so it reads `SP` and `RM` and no number at all.

That is exactly why a price found here is never compared against the promotion
as though a difference meant something: most differences would be this module's
own misses. The numbers exist so the review screen can show a human what the
card said, beside the product it matched.

A reading is never a document either. A price baked into a page document freezes
one number for every audience and breaks the rule that one published page serves
staff, dealers and consumers at the price each is allowed to see.

The layout is regular enough to exploit. A product card is a code, with its
name, price and size printed in a narrow column directly beneath it, and its
photo directly above. Cards sit on repeating baselines, so the codes sharing a
baseline are a printed row, and a printed row is one collection block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

import fitz  # PyMuPDF

# Sorento SKUs and the free-gift codes that sit beside them. Deliberately not
# "any word in capitals": the flyer is full of shouting headings, and a heading
# read as a SKU would put a phantom product into somebody's catalogue.
CODE_PATTERN = re.compile(r"^(?:SRT|FG-)[A-Z0-9][A-Z0-9\-\.]{2,}$")

# "L680xW365xH735mm", "L 1700 x W 800 x H 590 mm", and the spaced variants the
# typesetter used interchangeably.
DIMENSION_PATTERN = re.compile(
    r"L\s*(\d{2,5})\s*[xX*]\s*W\s*(\d{2,5})\s*[xX*]\s*H\s*(\d{2,5})"
)

LIST_PRICE_PATTERN = re.compile(r"LP\s*:?\s*RM\s*([\d,]+)", re.IGNORECASE)
# The offer price is printed as a bare "RM 299" under an "SP" flag rather than
# as "SP: RM 299", so it is matched on its own and the LP occurrences removed.
PRICE_PATTERN = re.compile(r"RM\s*([\d,]+)")

# How far below a code its own text reaches, and how wide its column is. Both in
# points, both measured off the real flyer: cards are about 130pt apart across
# and their copy runs about 80pt down.
CARD_TEXT_DEPTH_PT = 80.0
CARD_COLUMN_HALF_WIDTH_PT = 60.0

# Codes printed within this many points of each other vertically were printed on
# the same row.
ROW_TOLERANCE_PT = 24.0

# Artwork narrower than this fraction of the page is decoration inside a card,
# or a product photo, and neither belongs in the seeded document: a product's
# picture comes from the product master at render time.
ARTWORK_MIN_WIDTH_FRACTION = 0.25


@dataclass(frozen=True)
class FlyerCard:
    """One product as it was printed: a code, and what was set around it."""

    code: str
    lines: list[str]
    x: float
    y: float
    list_price: Optional[float] = None
    offer_price: Optional[float] = None
    length_mm: Optional[int] = None
    width_mm: Optional[int] = None
    height_mm: Optional[int] = None


@dataclass(frozen=True)
class FlyerGrid:
    """A printed row of cards, which becomes one collection block."""

    cards: list[FlyerCard]
    y: float

    @property
    def columns(self) -> int:
        return len(self.cards)


@dataclass(frozen=True)
class FlyerArtwork:
    """A picture big enough to be part of the design rather than of a product."""

    x_pct: float
    y_pct: float
    width_pct: float
    height_pct: float
    xref: int


@dataclass
class FlyerPage:
    number: int
    width: float
    height: float
    cards: list[FlyerCard] = field(default_factory=list)
    grids: list[FlyerGrid] = field(default_factory=list)
    artwork: list[FlyerArtwork] = field(default_factory=list)
    heading: Optional[str] = None

    @property
    def orientation(self) -> str:
        return "portrait" if self.height >= self.width else "landscape"


@dataclass
class FlyerReading:
    pages: list[FlyerPage] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        """Every distinct code in the document, in the order it was printed."""
        seen: dict[str, None] = {}
        for page in self.pages:
            for card in page.cards:
                seen.setdefault(card.code, None)
        return list(seen)


def extract_flyer(data: bytes) -> FlyerReading:
    """Read a flyer PDF into its structure.

    Raises ``ValueError`` for anything that is not a PDF, rather than returning
    an empty reading: a designer who uploaded the wrong file needs to be told,
    not handed a catalogue with nothing in it.
    """
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # pragma: no cover - the message varies by version
        raise ValueError(f"Not a readable PDF: {exc}") from exc

    if document.page_count == 0:
        raise ValueError("The PDF has no pages")

    reading = FlyerReading()
    try:
        for index in range(document.page_count):
            reading.pages.append(_read_page(document[index], index + 1))
    finally:
        document.close()
    return reading


def _code_of(span: dict) -> Optional[str]:
    """The SKU in a span, if it is one.

    Trailing punctuation is stripped first. The cover sets the gift codes as
    "FG-CW13:" because a description follows, and the colon belongs to the
    sentence rather than to the SKU. A card lost to a punctuation mark is a
    product missing from the seeded catalogue.
    """
    text = span["text"].strip().rstrip(":;,.")
    return text if CODE_PATTERN.match(text) else None


def _read_page(page: "fitz.Page", number: int) -> FlyerPage:
    spans = _spans(page)
    code_spans = [span for span in spans if _code_of(span)]

    cards = [_read_card(span, spans) for span in code_spans]
    # A code printed twice on one page (a product shown in two colourways under
    # one photo) is one card. The first wins, because it is the one the reader's
    # eye reaches first.
    cards = _dedupe(cards)
    cards.sort(key=lambda card: (card.y, card.x))

    result = FlyerPage(number=number, width=page.rect.width, height=page.rect.height)
    result.cards = cards
    result.grids = _rows(cards)
    result.artwork = _artwork(page)
    result.heading = _heading(spans, cards, page.rect.height)
    return result


def _spans(page: "fitz.Page") -> list[dict]:
    text = page.get_text("dict")
    return [
        span
        for block in text.get("blocks", [])
        if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]


def _read_card(code_span: dict, spans: Iterable[dict]) -> FlyerCard:
    bbox = code_span["bbox"]
    centre = (bbox[0] + bbox[2]) / 2

    lines = [
        span["text"].strip()
        for span in spans
        if span is not code_span
        and abs(_centre_x(span) - centre) < CARD_COLUMN_HALF_WIDTH_PT
        # Slightly above the code's baseline as well as below it: the typesetter
        # sets a name above the code as often as beneath it.
        and -12.0 <= span["bbox"][1] - bbox[3] < CARD_TEXT_DEPTH_PT
    ]

    blob = " ".join(lines)
    length, width, height = _dimensions(blob)
    return FlyerCard(
        code=_code_of(code_span) or code_span["text"].strip(),
        lines=lines,
        x=bbox[0],
        y=bbox[1],
        list_price=_list_price(blob),
        offer_price=_offer_price(blob),
        length_mm=length,
        width_mm=width,
        height_mm=height,
    )


def _centre_x(span: dict) -> float:
    return (span["bbox"][0] + span["bbox"][2]) / 2


def _dedupe(cards: list[FlyerCard]) -> list[FlyerCard]:
    seen: set[str] = set()
    kept: list[FlyerCard] = []
    for card in cards:
        if card.code in seen:
            continue
        seen.add(card.code)
        kept.append(card)
    return kept


def _dimensions(blob: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    match = DIMENSION_PATTERN.search(blob.replace(" ", ""))
    if not match:
        return None, None, None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _list_price(blob: str) -> Optional[float]:
    match = LIST_PRICE_PATTERN.search(blob)
    return _money(match.group(1)) if match else None


def _offer_price(blob: str) -> Optional[float]:
    """The promotional price, which is printed without a label of its own.

    The list price is removed first, so what is left is the SP figure. A card
    with only one price on it has no offer: reporting the list price twice would
    make every product look discounted to itself.
    """
    remainder = LIST_PRICE_PATTERN.sub(" ", blob)
    prices = [_money(value) for value in PRICE_PATTERN.findall(remainder)]
    prices = [price for price in prices if price is not None]
    return prices[0] if prices else None


def _money(value: str) -> Optional[float]:
    try:
        return float(value.replace(",", ""))
    except ValueError:  # pragma: no cover - the pattern only matches digits
        return None


def _rows(cards: list[FlyerCard]) -> list[FlyerGrid]:
    """Cards sharing a baseline were printed as one row.

    One grid per page would seed an undifferentiated wall of products; one grid
    per card would seed 40 blocks. The paper already answered this, and the
    answer is legible in the y co-ordinates.
    """
    grids: list[FlyerGrid] = []
    for card in cards:
        for index, grid in enumerate(grids):
            if abs(grid.y - card.y) <= ROW_TOLERANCE_PT:
                grids[index] = FlyerGrid(cards=[*grid.cards, card], y=grid.y)
                break
        else:
            grids.append(FlyerGrid(cards=[card], y=card.y))

    return [
        FlyerGrid(cards=sorted(grid.cards, key=lambda card: card.x), y=grid.y)
        for grid in sorted(grids, key=lambda grid: grid.y)
    ]


def _artwork(page: "fitz.Page") -> list[FlyerArtwork]:
    width = page.rect.width or 1
    height = page.rect.height or 1
    found: list[FlyerArtwork] = []
    seen: set[int] = set()

    for placed in page.get_image_info(xrefs=True):
        bbox = placed.get("bbox")
        if not bbox:
            continue
        image_width = (bbox[2] - bbox[0]) / width
        if image_width < ARTWORK_MIN_WIDTH_FRACTION:
            continue
        xref = int(placed.get("xref", 0))
        # The same artwork placed twice (a background and its own drop shadow)
        # is one piece of art.
        key = xref or int(bbox[0] * 1000 + bbox[1])
        if key in seen:
            continue
        seen.add(key)
        found.append(
            FlyerArtwork(
                x_pct=bbox[0] / width,
                y_pct=bbox[1] / height,
                width_pct=image_width,
                height_pct=(bbox[3] - bbox[1]) / height,
                xref=xref,
            )
        )
    return found


def _heading(
    spans: list[dict], cards: list[FlyerCard], page_height: float
) -> Optional[str]:
    """The section title: the biggest type in the top third that is not a card.

    A heuristic, and it will be wrong on the pages that are pure artwork. That is
    why the seed is reviewed before it is published: a wrong heading is a
    correction, not a defect.
    """
    card_lines = {line for card in cards for line in card.lines}
    card_codes = {card.code for card in cards}

    candidates = [
        span
        for span in spans
        if span["bbox"][1] < page_height / 3
        and span["text"].strip() not in card_lines
        and span["text"].strip() not in card_codes
        and len(span["text"].strip()) > 2
    ]
    if not candidates:
        return None

    best = max(candidates, key=lambda span: (round(span.get("size", 0), 1), -span["bbox"][1]))
    return best["text"].strip()
