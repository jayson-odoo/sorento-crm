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

**Artwork is the design, and a product's photo is not artwork (S7.5, AC-F4).**
What reads as a header band or a divider on these pages is a full-width IMAGE
with the heading typeset on top - flyer page 4 contains exactly one vector rule
in the whole spread. So the artwork has to be read out and kept, or a seeded
section looks nothing like the paper. But the same page places 68 images, and
almost all of them are product photographs: a rule that keeps any picture wider
than a card would fill the asset library with hundreds of product shots and, on
page 4, would choose a composited sheet of toilets as the section background. A
picture with a printed code ON it or directly above it belongs to that card and
comes from the product master at render time. The one exception is a picture the
size of the whole page, which is a full-bleed background with everything printed
over it - the cover is exactly that.

**And it is cropped to the paper (AC-F2).** The designer's artwork bleeds: one
image on flyer page 4 is 1.17x the page width, anchored 662pt above the top
edge. Taken whole it is a different picture from the one that was printed, so
both the reported geometry and the stored pixels stop at the page box.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

import fitz  # PyMuPDF

from app.services.image_normalizer import ensure_rgb_image

logger = logging.getLogger(__name__)

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

# How far a photograph may sit ABOVE the code it belongs to. Measured across the
# fixture: the water closet spread's photos stop between 7 and 30pt above their
# SKU. Wider than that and the banner across the top of a page starts being read
# as the first row's photo - the real gap there is 90pt.
PHOTO_CODE_GAP_PT = 36.0

# A piece of art has to reach this much of the page width, at the very top of
# it, to be the page's BANNER - the one image a seeded section takes as its
# background. Everything narrower is an element within the layout: real, worth
# recording, and not something to put a heading on top of.
BANNER_MIN_WIDTH_FRACTION = 0.80
BANNER_TOP_TOLERANCE_PCT = 0.02

# A banner this tall was the page itself rather than a band across it, so it is
# laid out to COVER its section instead of being stretched across the top.
BANNER_COVER_MIN_HEIGHT_PCT = 0.50

# How close to the paper's own edges a picture has to reach to count as a
# full-bleed page background. Those are exempt from the product-photo rule: every
# product on the cover is printed over the cover image, so "carries a code"
# would throw away the one piece of art on the page.
FULL_BLEED_TOLERANCE_PCT = 0.02

# The whole source image, as a crop box. Named so the "nothing to cut" case reads
# as a decision rather than as four magic numbers.
UNCROPPED = (0.0, 0.0, 1.0, 1.0)

# Colour spaces a browser renders. Anything else the PDF happens to hold (JPEG
# 2000, a separation) is re-encoded rather than handed on.
_BROWSER_SAFE_IMAGE_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
_REENCODE_QUALITY = 90


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
    """A picture big enough to be part of the design rather than of a product.

    The four percentages are the part of the picture that is ON the page, so
    they always lie inside it (AC-F2). ``crop`` is the matching sub-rectangle of
    the SOURCE image, as fractions, which is what lets the stored pixels be cut
    the same way the geometry was.
    """

    x_pct: float
    y_pct: float
    width_pct: float
    height_pct: float
    xref: int
    crop: tuple[float, float, float, float] = UNCROPPED


@dataclass(frozen=True)
class FlyerBanner:
    """The one piece of art a seeded section takes as its background.

    Carries the BYTES, which is why it exists apart from ``FlyerArtwork``: the
    geometry is cheap and is read on every extraction, while decoding and
    re-encoding an image is not, so only an upload asks for it. The bytes are
    never serialised into a reading - they go to storage and the reading keeps
    the asset id.
    """

    artwork: FlyerArtwork
    image: bytes
    mime: str
    #: How the section should lay it out: ``width`` across the top for a band,
    #: ``cover`` when the artwork was the whole printed page.
    fit: str


@dataclass
class FlyerPage:
    number: int
    width: float
    height: float
    cards: list[FlyerCard] = field(default_factory=list)
    grids: list[FlyerGrid] = field(default_factory=list)
    artwork: list[FlyerArtwork] = field(default_factory=list)
    heading: Optional[str] = None
    #: Present only when the caller asked for images. Never serialised.
    banner: Optional[FlyerBanner] = None
    #: Where the banner ENDED UP once it was stored, which is what a seeded
    #: document binds. Filled in by the reading service, not by the extractor.
    banner_asset_id: Optional[str] = None
    banner_fit: Optional[str] = None

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


class EncryptedFlyerError(ValueError):
    """A real PDF that this system is not allowed to read.

    A subclass of ``ValueError`` on purpose, so every existing caller that
    already refuses unreadable files keeps working unchanged. It exists only so
    the layer that turns the failure into WORDS can tell the two cases apart:
    "that is not a PDF" and "that is a PDF I cannot open" call for opposite
    actions from the person holding the file.
    """


def extract_flyer(data: bytes, *, with_artwork_images: bool = False) -> FlyerReading:
    """Read a flyer PDF into its structure.

    Raises ``ValueError`` for anything that is not a PDF, rather than returning
    an empty reading: a designer who uploaded the wrong file needs to be told,
    not handed a catalogue with nothing in it. A password-protected PDF raises
    the ``EncryptedFlyerError`` subclass, because that one is fixable by the
    person uploading it.

    ``with_artwork_images`` additionally decodes each page's banner and hands
    back the bytes. Off by default because the expensive half of this module is
    the image work and almost nobody needs it: the match report is recomputed
    from a stored reading on every read of the review screen, and it is about
    codes. Only the upload, which stores the banners once, asks for them.
    """
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # pragma: no cover - the message varies by version
        raise ValueError(f"Not a readable PDF: {exc}") from exc

    # Checked HERE rather than left to fail later. PyMuPDF opens a locked
    # document happily and only objects when something reads a page, by which
    # point its complaint is "document closed or encrypted" - a message that is
    # actively misleading in front of somebody looking at an open document.
    if document.needs_pass:
        document.close()
        raise EncryptedFlyerError("The PDF is password protected")

    if document.page_count == 0:
        raise ValueError("The PDF has no pages")

    reading = FlyerReading()
    try:
        for index in range(document.page_count):
            reading.pages.append(
                _read_page(
                    document,
                    document[index],
                    index + 1,
                    with_artwork_images=with_artwork_images,
                )
            )
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


def _read_page(
    document: "fitz.Document",
    page: "fitz.Page",
    number: int,
    *,
    with_artwork_images: bool = False,
) -> FlyerPage:
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
    # Cards first: which pictures are artwork is decided by where the codes are.
    result.artwork = _artwork(page, cards)
    result.heading = _heading(spans, cards, page.rect.height)
    if with_artwork_images:
        result.banner = _banner(document, result)
        result.banner_fit = result.banner.fit if result.banner else None
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


def _artwork(page: "fitz.Page", cards: list[FlyerCard]) -> list[FlyerArtwork]:
    """The pictures on this page that are part of its DESIGN.

    Three filters, in this order, because each depends on the one before it:

    1. **Crop to the paper.** A placement that bleeds off the page is reported
       as the part that was printed. Done first so everything after it measures
       what a reader saw rather than what the designer's file holds (AC-F2).
    2. **Drop what is too narrow** to be anything but a product photo or a badge
       inside a card.
    3. **Drop what belongs to a card.** A picture with a SKU on it or directly
       above it is that product's photograph (AC-F4).
    """
    width = page.rect.width or 1
    height = page.rect.height or 1
    found: list[FlyerArtwork] = []
    seen: set[int] = set()

    for placed in page.get_image_info(xrefs=True):
        bbox = placed.get("bbox")
        if not bbox:
            continue

        visible = _visible_rect(bbox, width, height)
        if visible is None:
            continue

        vx0, vy0, vx1, vy1 = visible
        image_width = (vx1 - vx0) / width
        if image_width < ARTWORK_MIN_WIDTH_FRACTION:
            continue

        xref = int(placed.get("xref", 0))
        # The same artwork placed twice (a background and its own drop shadow)
        # is one piece of art.
        key = xref or int(bbox[0] * 1000 + bbox[1])
        if key in seen:
            continue
        seen.add(key)

        if _belongs_to_a_card(visible, cards, width, height):
            continue

        found.append(
            FlyerArtwork(
                x_pct=vx0 / width,
                y_pct=vy0 / height,
                width_pct=image_width,
                height_pct=(vy1 - vy0) / height,
                xref=xref,
                crop=_crop_of(bbox, visible),
            )
        )
    return found


def _visible_rect(
    bbox: Iterable[float], page_width: float, page_height: float
) -> Optional[tuple[float, float, float, float]]:
    """The part of a placement that is on the paper, or None if none of it is."""
    x0, y0, x1, y1 = (float(value) for value in bbox)
    visible = (
        max(0.0, min(x0, x1)),
        max(0.0, min(y0, y1)),
        min(page_width, max(x0, x1)),
        min(page_height, max(y0, y1)),
    )
    if visible[2] <= visible[0] or visible[3] <= visible[1]:
        return None
    return visible


def _crop_of(
    bbox: Iterable[float], visible: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """Which sub-rectangle of the SOURCE image survived the crop, as fractions.

    An unrotated PDF image maps its top-left sample onto the top-left of the
    placement box, so the fractions carry straight across to pixels. Every band
    and background in this document is placed that way; a rotated one would come
    out cropped along the wrong axis, which is a trade for not carrying a full
    transform matrix through the reading.
    """
    x0, y0, x1, y1 = (float(value) for value in bbox)
    span_x = (x1 - x0) or 1.0
    span_y = (y1 - y0) or 1.0
    return (
        (visible[0] - x0) / span_x,
        (visible[1] - y0) / span_y,
        (visible[2] - x0) / span_x,
        (visible[3] - y0) / span_y,
    )


def _covers_the_page(
    visible: tuple[float, float, float, float], page_width: float, page_height: float
) -> bool:
    """A full-bleed background: the paper itself, with everything printed over it."""
    slack_x = page_width * FULL_BLEED_TOLERANCE_PCT
    slack_y = page_height * FULL_BLEED_TOLERANCE_PCT
    return (
        visible[0] <= slack_x
        and visible[1] <= slack_y
        and visible[2] >= page_width - slack_x
        and visible[3] >= page_height - slack_y
    )


def _belongs_to_a_card(
    visible: tuple[float, float, float, float],
    cards: list[FlyerCard],
    page_width: float,
    page_height: float,
) -> bool:
    """Whether this picture is a product's photograph rather than the page's art.

    Three ways a picture can belong to a card, all of them measured off the real
    document:

    * the SKU is printed ON it - the water closet spread sets three codes
      directly onto their card panels, and one 0.53-page-wide panel spans a pair
      of them, which is the two-products-under-one-photo case;
    * the SKU is printed directly BENEATH it, which is the ordinary tile;
    * the SKU is printed directly ABOVE it, which is the card's own copy - its
      price flag, its badge - sitting in the column under the code.

    A full-bleed page background is exempt, because every product on such a page
    is printed over it by construction.
    """
    if _covers_the_page(visible, page_width, page_height):
        return False

    x0, y0, x1, y1 = visible
    for card in cards:
        if not x0 <= card.x <= x1:
            continue
        if y0 <= card.y <= y1:
            return True
        if 0.0 <= y0 - card.y <= CARD_TEXT_DEPTH_PT:
            return True
        if 0.0 <= card.y - y1 <= PHOTO_CODE_GAP_PT:
            return True
    return False


def _banner(document: "fitz.Document", page: FlyerPage) -> Optional[FlyerBanner]:
    """The page's background: a full-width piece of art at the very top of it.

    Candidates are taken in DRAW order and the last one wins, because a later
    placement is painted over the earlier ones and is therefore the one a reader
    sees. A candidate whose bytes cannot be read back is skipped rather than
    bound: PyMuPDF reports an unresolvable placement as ``xref`` 0, and binding
    a section to a background that can never load is worse than no background.
    """
    candidates = [
        art
        for art in page.artwork
        if art.xref
        and art.width_pct >= BANNER_MIN_WIDTH_FRACTION
        and art.y_pct <= BANNER_TOP_TOLERANCE_PCT
    ]

    for art in reversed(candidates):
        loaded = _artwork_image(document, art)
        if loaded is None:
            continue
        content, mime = loaded
        fit = "cover" if art.height_pct >= BANNER_COVER_MIN_HEIGHT_PCT else "width"
        return FlyerBanner(artwork=art, image=content, mime=mime, fit=fit)
    return None


def _artwork_image(
    document: "fitz.Document", art: FlyerArtwork
) -> Optional[tuple[bytes, str]]:
    """The artwork's own pixels, RGB and cropped to the page.

    RGB conversion goes through the SAME normaliser the attachment upload uses
    (``ensure_rgb_image``). The real flyer's banners are DeviceCMYK JPEGs - 15
    of 15 measured - which browsers render unreliably and Meta rejects outright;
    it is the identical defect that broke WhatsApp media, so it gets the
    identical fix rather than a second one.
    """
    try:
        raw = document.extract_image(art.xref)
    except Exception as exc:  # noqa: BLE001 - a placement we cannot read back
        logger.warning("Flyer artwork xref=%s could not be extracted: %s", art.xref, exc)
        return None

    content = raw.get("image")
    if not content:
        return None

    extension = (raw.get("ext") or "").lower()
    mime = _BROWSER_SAFE_IMAGE_MIME.get(extension)
    content, _name, mime = ensure_rgb_image(content, f"banner.{extension}", mime)

    if art.crop == UNCROPPED and mime:
        return content, mime

    # Either there is a bleed to cut off, or the PDF holds the image in a format
    # no browser opens. Both end in one re-encode.
    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            box = _pixel_box(art.crop, image.width, image.height)
            cropped = image.crop(box) if box else image
            if cropped.mode not in ("RGB", "L"):
                cropped = cropped.convert("RGB")
            out = io.BytesIO()
            cropped.save(out, format="JPEG", quality=_REENCODE_QUALITY)
    except Exception as exc:  # noqa: BLE001 - a picture PIL cannot open
        logger.warning("Flyer artwork xref=%s could not be cropped: %s", art.xref, exc)
        return None

    return out.getvalue(), "image/jpeg"


def _pixel_box(
    crop: tuple[float, float, float, float], width: int, height: int
) -> Optional[tuple[int, int, int, int]]:
    if crop == UNCROPPED:
        return None
    left = max(0, min(width - 1, round(crop[0] * width)))
    top = max(0, min(height - 1, round(crop[1] * height)))
    right = max(left + 1, min(width, round(crop[2] * width)))
    bottom = max(top + 1, min(height, round(crop[3] * height)))
    return left, top, right, bottom


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
