"""How alike the seeded catalogue is to the printed document (UAC group Z).

The requirement is that a seeded catalogue is at least 90% alike the flyer it
came from. That cannot be an image comparison. The seed is deliberately
STRUCTURE-faithful rather than pixel-faithful: exact positions were traded away
so prices, photos and stock resolve per viewer. A picture diff would score a
correctly-working seed low, and would score highly on one that had baked a
single frozen price in for every audience. It would measure the wrong thing and
punish the right answer.

So likeness is measured on what the page SAYS and how it is GROUPED, in six
components with fixed weights. Coverage carries the most because a product
missing from the catalogue is the worst outcome; a wrong heading carries little
because it is a five second correction.

**The ground truth is never the extractor.** Scoring a reading against itself
would let it misread the flyer completely and still score 100%. So the chain is
measured in two independent links:

    PRINTED DOCUMENT --(A)--> READING --(B)--> SEEDED PAGE

Both links live here, and they score different things with different bars.

``score_reading`` is link A: a reading against a hand-verified transcript of
what is actually printed. Its bar is 0.90, because paper is ambiguous and a
heuristic reading it is allowed to be imperfect.

``score_seed`` is link B: the seeded document against the reading it was built
from. Its bar is **1.00**. The seeder is pure code operating on a structure it
was handed, so a card that does not reach the document is a bug with a line
number, not a tolerance to be tuned - which is also why every link B failure
NAMES the cards that went missing and where on the flyer they should have been.
A number alone would be useless at that bar.

Invention is not scored, it is forbidden. A tolerance on the way IN is not a
tolerance on the way OUT: a catalogue offering a product the flyer never
advertised is a different kind of wrong from one missing a product, so it fails
the run outright rather than costing a fraction of a component.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.services.dealer_kit.flyer_extraction import FlyerPage, FlyerReading

# What each component is worth. They sum to 1.0.
WEIGHTS = {
    "coverage": 0.30,
    "placement": 0.20,
    "grouping": 0.20,
    "order": 0.10,
    "heading": 0.10,
    "artwork": 0.10,
}

#: The bar. A reading below this has stopped representing the document.
FIDELITY_THRESHOLD = 0.90


@dataclass
class PageScore:
    number: int
    coverage: float = 0.0
    placement: float = 0.0
    grouping: float = 0.0
    order: float = 0.0
    heading: float = 0.0
    artwork: float = 0.0
    #: Codes printed on this page that never reached the reading.
    missed: list[str] = field(default_factory=list)
    #: Codes in the reading that are not printed on this page. Must be empty.
    invented: list[str] = field(default_factory=list)
    #: How much this page counts for: dense spreads outweigh a cover.
    weight: int = 0

    @property
    def composite(self) -> float:
        return sum(WEIGHTS[key] * getattr(self, key) for key in WEIGHTS)


@dataclass
class FidelityReport:
    pages: list[PageScore] = field(default_factory=list)

    @property
    def invented(self) -> list[str]:
        return [code for page in self.pages for code in page.invented]

    @property
    def composite(self) -> float:
        """The headline number, weighted by how much is printed on each page.

        Zero when anything was invented: no amount of accuracy elsewhere makes
        up for a catalogue advertising a product the flyer does not.
        """
        if self.invented:
            return 0.0
        total = sum(page.weight for page in self.pages)
        if not total:
            return 0.0
        return sum(page.composite * page.weight for page in self.pages) / total

    @property
    def passes(self) -> bool:
        return self.composite >= FIDELITY_THRESHOLD

    def summary(self) -> str:
        """A number is never reported without the list behind it (AC-Z6)."""
        lines = [f"composite {self.composite:.3f}  (threshold {FIDELITY_THRESHOLD:.2f})"]
        lines.extend(_component_lines(self.pages, WEIGHTS))
        for page in self.pages:
            if page.missed or page.invented:
                lines.append(f"  page {page.number}:")
                if page.missed:
                    lines.append(f"    missed:   {', '.join(page.missed)}")
                if page.invented:
                    lines.append(f"    INVENTED: {', '.join(page.invented)}")
        return "\n".join(lines)


def _weighted(pages: Sequence[Any], key: str) -> float:
    """A component averaged over pages, weighted by how much each one carries.

    Shared by both links. ``pages`` is anything with a ``weight`` and the named
    component on it, which is the only thing the two page-score shapes have to
    agree about.
    """
    total = sum(page.weight for page in pages)
    if not total:
        return 0.0
    return sum(getattr(page, key) * page.weight for page in pages) / total


def _component_lines(pages: Sequence[Any], weights: Mapping[str, float]) -> list[str]:
    """The per-component breakdown every report prints (AC-Z6).

    A composite on its own does not say which component moved, and "which one
    moved" is the whole of a regression report.
    """
    return [
        f"  {key:<10} {_weighted(pages, key):.3f}  (weight {weights[key]:.2f})"
        for key in weights
    ]


def score_reading(reading: FlyerReading, golden: dict[str, Any]) -> FidelityReport:
    """Score a reading against a hand-verified transcript of the document."""
    report = FidelityReport()
    by_number = {page.number: page for page in reading.pages}

    for entry in golden.get("pages", []):
        number = entry["number"]
        page = by_number.get(number)
        printed: list[str] = list(entry.get("codes", []))
        score = PageScore(number=number, weight=max(1, len(printed)))

        read_codes = [card.code for card in page.cards] if page else []
        score.missed = [code for code in printed if code not in read_codes]
        score.invented = [code for code in read_codes if code not in printed]

        score.coverage = _ratio(len(printed) - len(score.missed), len(printed))
        # Placement: on a single-document reading, a code is placed correctly
        # when it was read on the page it is printed on. Codes read on the WRONG
        # page show up as invented there and missed here, so this is not double
        # counting - it is the same failure seen from the page that lost it.
        score.placement = score.coverage

        golden_rows = [list(row) for row in entry.get("rows", [])]
        read_rows = [[card.code for card in grid.cards] for grid in (page.grids if page else [])]
        score.grouping = _grouping(golden_rows, read_rows)
        score.order = _order(golden_rows, read_rows)
        score.heading = _heading(entry.get("heading"), page.heading if page else None)
        score.artwork = _artwork(
            bool(entry.get("full_width_band")),
            [art.width_pct for art in (page.artwork if page else [])],
        )
        report.pages.append(score)

    return report


def _ratio(hit: int, total: int) -> float:
    return 1.0 if total == 0 else max(0.0, hit / total)


def _grouping(golden_rows: Sequence[Sequence[str]], read_rows: Sequence[Sequence[str]]) -> float:
    """How well each product's neighbours survived.

    Measured per PRODUCT rather than per row, because rows do not line up one to
    one once the extractor splits or merges one. For each printed code, its
    printed row-mates are compared with the row-mates it ended up beside, by
    Jaccard overlap. A code the reading lost scores zero, which is correct: it
    has no neighbours at all.
    """
    read_row_of: dict[str, set[str]] = {}
    for row in read_rows:
        members = set(row)
        for code in row:
            read_row_of[code] = members

    scores: list[float] = []
    for row in golden_rows:
        expected = set(row)
        for code in row:
            actual = read_row_of.get(code)
            if actual is None:
                scores.append(0.0)
                continue
            union = expected | actual
            scores.append(len(expected & actual) / len(union) if union else 1.0)

    return sum(scores) / len(scores) if scores else 1.0


def _order(golden_rows: Sequence[Sequence[str]], read_rows: Sequence[Sequence[str]]) -> float:
    """The fraction of printed left-to-right neighbours still adjacent, in order.

    Adjacent PAIRS rather than whole-sequence equality, so one product moving in
    a row of six costs a fraction rather than the row.
    """
    read_index: dict[str, tuple[int, int]] = {}
    for row_index, row in enumerate(read_rows):
        for position, code in enumerate(row):
            read_index[code] = (row_index, position)

    pairs = 0
    kept = 0
    for row in golden_rows:
        for left, right in zip(row, row[1:]):
            pairs += 1
            first = read_index.get(left)
            second = read_index.get(right)
            if first and second and first[0] == second[0] and first[1] < second[1]:
                kept += 1

    return 1.0 if pairs == 0 else kept / pairs


def _heading(expected: str | None, actual: str | None) -> float:
    """Headings match on their words, not their whitespace.

    The flyer letterspaces its section titles ("C O L L E C T I O N"), so a
    character-exact comparison would fail on a heading a reader would call
    identical.
    """
    if not expected:
        return 1.0
    if not actual:
        return 0.0
    return 1.0 if _normalise(expected) == _normalise(actual) else 0.0


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _artwork(expected_band: bool, widths: Iterable[float]) -> float:
    if not expected_band:
        return 1.0
    return 1.0 if any(width > 0.8 for width in widths) else 0.0


# =========================================================================== #
# LINK B: the reading, and the document the seeder built from it (AC-Z3..Z5)
#
# The bar is EQUALITY. Link A is allowed to be imperfect because paper is
# ambiguous; the seeder was handed a structure, so a card that does not reach
# the document is a defect with a line number rather than a tolerance to be
# tuned. The components below therefore exist to make a FAILURE readable, not to
# be traded against one another: at 1.00 every one of them is 1.00.
#
# The one legitimate drop is a printed code the master does not have. It cannot
# be pinned - a collection pins product ids, and inventing a product for a code
# would put a SKU nobody stocks in front of a customer (PLAN D8) - so link B is
# scored over the cards the seeder was ABLE to place, and every card it could
# not place is reconciled against the seed result's ``skipped`` list. A card
# that vanishes WITHOUT appearing in ``skipped`` is the exact defect this gate
# exists to catch, and it fails the run outright.
# =========================================================================== #

#: What each link B component is worth. They sum to 1.0.
#:
#: Coverage carries the most for the same reason it does in link A: a product
#: missing from the catalogue is the worst outcome. ``sequence`` carries the
#: least because rows landing down the page in the wrong order is the one defect
#: here a reviewer spots instantly with the flyer in hand.
SEED_WEIGHTS = {
    "coverage": 0.40,  # placeable cards that reached a tile at all
    "section": 0.20,  # ... in the section built for the page they were printed on
    "grouping": 0.20,  # ... beside exactly the row-mates they were printed with
    "order": 0.15,  # ... in the printed left-to-right sequence
    "sequence": 0.05,  # ... and the printed rows running down the page in order
}

#: Exact equality, not a threshold. See the block comment above.
SEED_FIDELITY_BAR = 1.0

# Field names that mean the document has BOUND something which must be resolved
# per viewer instead (AC-Z5). A price frozen into a document serves one figure to
# every audience and breaks the one thing the Kit exists to do; a photo URL
# breaks the moment the file is re-signed or renamed.
_PRICE_KEY_TOKENS = ("price", "amount", "rrp", "cost", "currency")
_URL_KEY_TOKENS = ("url", "src", "href", "photo", "image", "thumbnail")

# A money figure written into a value rather than a key: "RM 1,299" or "1299.00".
_PRICE_TEXT = re.compile(r"(?i)\brm\s*[\d,]|\d[\d,]*\.\d{2}\b")


@dataclass
class SeedPageScore:
    """One flyer page, and what became of its cards."""

    number: int
    coverage: float = 0.0
    section: float = 0.0
    grouping: float = 0.0
    order: float = 0.0
    sequence: float = 0.0
    #: Codes that reached a tile somewhere in the document.
    placed: list[str] = field(default_factory=list)
    #: Codes the master has no product for. They CANNOT be pinned, so they are
    #: excluded from the score - but only once they are reconciled against the
    #: seed result's ``skipped`` list. Anything unreconciled is in ``lost``.
    unplaceable: list[str] = field(default_factory=list)
    #: Cards that reached no tile and that nothing accounts for. The defect.
    lost: list[str] = field(default_factory=list)
    #: Cards that reached the document, but not in this page's own section.
    misplaced: list[str] = field(default_factory=list)
    #: Where each card was printed, so a failure is actionable without a
    #: debugger: "SRTJC8041 (flyer page 2, row 2, position 3)".
    where: dict[str, str] = field(default_factory=dict)
    #: How much this page counts for: the cards the seeder could have placed.
    weight: int = 0

    @property
    def composite(self) -> float:
        return sum(SEED_WEIGHTS[key] * getattr(self, key) for key in SEED_WEIGHTS)

    def at(self, code: str) -> str:
        return self.where.get(code, f"{code} (flyer page {self.number})")


@dataclass
class SeedFidelityReport:
    pages: list[SeedPageScore] = field(default_factory=list)
    #: Product ids pinned by the document that no printed card resolves to
    #: (AC-Z4). Fails the run outright.
    invented: list[str] = field(default_factory=list)
    #: Prices, photo URLs and other bound text the document must not hold
    #: (AC-Z5). Fails the run outright.
    forbidden: list[str] = field(default_factory=list)
    #: Collection ids a block points at that were never created. Renders an
    #: empty grid inside a page that otherwise looks complete.
    dangling: list[str] = field(default_factory=list)
    sections_expected: int = 0
    sections_found: int = 0

    @property
    def lost(self) -> list[str]:
        return [code for page in self.pages for code in page.lost]

    @property
    def misplaced(self) -> list[str]:
        return [code for page in self.pages for code in page.misplaced]

    @property
    def composite(self) -> float:
        """The headline number, weighted by what each page had to place.

        Zero on any hard failure. A card the seeder lost, a product the flyer
        never printed, a price baked into the document and a block pointing at
        nothing are all defects rather than fractions: no amount of accuracy
        elsewhere makes up for one, and averaging them away is how a gate ends
        up reporting "0.97" to somebody who cannot act on it.
        """
        if self.invented or self.forbidden or self.dangling or self.lost:
            return 0.0
        total = sum(page.weight for page in self.pages)
        if not total:
            # Nothing was placeable, so nothing was proved. Reporting 1.00 for a
            # run that seeded an empty catalogue is the failure mode a naive
            # ratio hides.
            return 0.0
        return sum(page.composite * page.weight for page in self.pages) / total

    @property
    def passes(self) -> bool:
        return self.composite >= SEED_FIDELITY_BAR

    def component(self, key: str) -> float:
        """One component on its own, so a failure names which one moved."""
        return _weighted(self.pages, key)

    def summary(self) -> str:
        """The breakdown, and the cards behind it (AC-Z6).

        Every list names WHERE the card was printed, because "SRTJC8041 is
        missing" sends somebody hunting through 36 pages and "SRTJC8041 (flyer
        page 2, row 2, position 3)" does not.
        """
        lines = [f"link B {self.composite:.3f}  (bar {SEED_FIDELITY_BAR:.2f}, exact)"]
        lines.extend(_component_lines(self.pages, SEED_WEIGHTS))

        if self.sections_found != self.sections_expected:
            lines.append(
                f"  SECTIONS: {self.sections_found} in the document for "
                f"{self.sections_expected} flyer pages"
            )
        if self.invented:
            lines.append(f"  INVENTED (not on the flyer): {', '.join(self.invented)}")
        if self.forbidden:
            lines.append("  FORBIDDEN:")
            lines.extend(f"    {entry}" for entry in self.forbidden)
        if self.dangling:
            lines.append(f"  DANGLING collections: {', '.join(self.dangling)}")

        for page in self.pages:
            if not (page.lost or page.misplaced or page.unplaceable):
                continue
            lines.append(f"  flyer page {page.number}:")
            if page.lost:
                lines.append("    LOST (in neither the document nor skipped):")
                lines.extend(f"      {page.at(code)}" for code in page.lost)
            if page.misplaced:
                lines.append("    misplaced (seeded under another page):")
                lines.extend(f"      {page.at(code)}" for code in page.misplaced)
            if page.unplaceable:
                lines.append("    no product in the master, reported as skipped:")
                lines.extend(f"      {page.at(code)}" for code in page.unplaceable)
        return "\n".join(lines)


def score_seed(
    reading: FlyerReading,
    doc: Mapping[str, Any],
    *,
    product_by_code: Mapping[str, str],
    collections: Iterable[Any],
    skipped: Iterable[Any] = (),
    banned_text: Iterable[str] = (),
) -> SeedFidelityReport:
    """Score a seeded document against the reading it was built from.

    ``collections`` are the rows the seed created, read by attribute so an ORM
    ``Collection`` and a test double are equally acceptable: the scorer touches
    no database, which is what lets it run over a hand-built document proving it
    can fail.

    ``skipped`` is the seed result's own account of what it dropped - entries
    with a ``.code``, or bare code strings. It is the ONLY excuse for a card
    that did not reach the document, and it excuses nothing the master could
    have resolved.

    ``banned_text`` is whatever must not be bound into the document beyond the
    prices and URLs recognised structurally: company names, product names. Text
    the flyer itself printed (a section name, a heading block) is exempt and
    deliberately so - the extractor carries headings through VERBATIM, the real
    flyer prints prices inside its own copy, and failing the run because a
    heading reads "RM 1,299 OFF" would punish the seeder for the paper. The tile
    beside it still resolves its price per viewer, which is what AC-Z5 protects.
    """
    report = SeedFidelityReport()
    sections = list((doc or {}).get("sections") or [])
    report.sections_expected = len(reading.pages)
    report.sections_found = len(sections)

    by_id = {getattr(collection, "id"): collection for collection in collections}
    dropped = {getattr(entry, "code", entry) for entry in skipped}

    seeded_pins: list[list[list[str]]] = []
    seeded_order: list[list[list[str]]] = []
    for section in sections:
        pins, order, dangling = _seeded_rows(section, by_id)
        seeded_pins.append(pins)
        seeded_order.append(order)
        for collection_id in dangling:
            if collection_id not in report.dangling:
                report.dangling.append(collection_id)

    placed_anywhere = {
        product_id for rows in seeded_pins for row in rows for product_id in row
    }
    printed_ids = {
        product_by_code[card.code]
        for page in reading.pages
        for card in page.cards
        if card.code in product_by_code
    }
    report.invented = [
        product_id
        for product_id in _in_order(seeded_pins)
        if product_id not in printed_ids
    ]

    for index, page in enumerate(reading.pages):
        own_pins = seeded_pins[index] if index < len(sections) else []
        own_order = seeded_order[index] if index < len(sections) else []
        own_ids = {product_id for row in own_pins for product_id in row}

        score = SeedPageScore(number=page.number, where=_where(page))
        printed_here = 0
        in_document = 0
        in_section = 0

        for card in page.cards:
            product_id = product_by_code.get(card.code)
            if product_id is None:
                # The one legitimate drop - but only once the seed admitted to
                # it. Unreconciled, it is indistinguishable from a card the
                # seeder silently lost, which is the whole reason this gate is
                # written as a reconciliation rather than a count.
                score.unplaceable.append(card.code)
                if card.code not in dropped:
                    score.lost.append(card.code)
                continue

            printed_here += 1
            if product_id in placed_anywhere:
                in_document += 1
                score.placed.append(card.code)
                if product_id in own_ids:
                    in_section += 1
                else:
                    score.misplaced.append(card.code)
            else:
                # The master HAS this product, so ``skipped`` does not excuse it
                # however it is listed: a code the seed could resolve and did not
                # place is a defect either way.
                score.lost.append(card.code)

        score.weight = printed_here
        score.coverage = _ratio(in_document, printed_here)
        score.section = _ratio(in_section, printed_here)

        printed_rows = _printed_rows(page, product_by_code)
        score.grouping = _grouping(printed_rows, own_pins)
        score.order = _order(printed_rows, own_order)
        score.sequence = _row_sequence(printed_rows, own_pins)
        report.pages.append(score)

    report.forbidden = _forbidden(doc, banned_text)
    return report


def _seeded_rows(
    section: Mapping[str, Any], by_id: Mapping[str, Any]
) -> tuple[list[list[str]], list[list[str]], list[str]]:
    """One section's collection blocks, in the order they are laid down.

    Membership comes from ``pinned_product_ids`` and sequence from
    ``manual_order``, which are two different questions: the resolver sorts
    members by ``manual_order``, so a collection holding the right products in
    the wrong order renders the row backwards while pinning perfectly.
    """
    pins: list[list[str]] = []
    order: list[list[str]] = []
    dangling: list[str] = []

    for block in section.get("blocks") or []:
        if block.get("type") != "collection":
            continue
        collection_id = (block.get("props") or {}).get("collectionId")
        collection = by_id.get(collection_id)
        if collection is None:
            dangling.append(collection_id)
            pins.append([])
            order.append([])
            continue
        pins.append(list(collection.pinned_product_ids or []))
        order.append(list(collection.manual_order or []))

    return pins, order, dangling


def _printed_rows(page: FlyerPage, product_by_code: Mapping[str, str]) -> list[list[str]]:
    """What each printed row SHOULD have become, as product ids.

    De-duplicated and with unplaceable codes removed, which mirrors what the
    seeder can physically produce: a collection cannot pin one product twice,
    and a code the master lacks has no id to pin. Rows left empty produce no
    block at all, so they are dropped rather than compared against nothing.
    """
    rows: list[list[str]] = []
    for grid in page.grids:
        row: list[str] = []
        for card in grid.cards:
            product_id = product_by_code.get(card.code)
            if product_id and product_id not in row:
                row.append(product_id)
        if row:
            rows.append(row)
    return rows


def _row_sequence(printed_rows: Sequence[Sequence[str]], seeded_rows: Sequence[Sequence[str]]) -> float:
    """Printed rows running DOWN the page in the order they were printed.

    Measured on adjacent pairs, like ``_order`` measures left to right, so one
    row moving costs a fraction rather than the page. A printed row that
    produced no block at all is skipped: that is a coverage question, already
    answered, and counting it twice would say a page was worse than it is.
    """
    first_seen: dict[str, int] = {}
    for position, row in enumerate(seeded_rows):
        for product_id in row:
            first_seen.setdefault(product_id, position)

    landed = [
        next((first_seen[product_id] for product_id in row if product_id in first_seen), None)
        for row in printed_rows
    ]

    pairs = 0
    kept = 0
    for above, below in zip(landed, landed[1:]):
        if above is None or below is None:
            continue
        pairs += 1
        if above < below:
            kept += 1

    return 1.0 if pairs == 0 else kept / pairs


def _where(page: FlyerPage) -> dict[str, str]:
    """Where every card on this page was printed, in words a reviewer can use."""
    located: dict[str, str] = {}
    for row_index, grid in enumerate(page.grids, start=1):
        for position, card in enumerate(grid.cards, start=1):
            located[card.code] = (
                f"{card.code} (flyer page {page.number}, row {row_index}, position {position})"
            )
    for card in page.cards:
        # A card the extractor placed in no row at all. It cannot be seeded, and
        # naming it that way is the difference between a fixable report and a
        # confusing one.
        located.setdefault(card.code, f"{card.code} (flyer page {page.number}, no printed row)")
    return located


def _in_order(rows: Iterable[Iterable[Iterable[str]]]) -> list[str]:
    """Every product id the document pins, de-duplicated, in document order."""
    seen: dict[str, None] = {}
    for section in rows:
        for row in section:
            for product_id in row:
                seen.setdefault(product_id, None)
    return list(seen)


# --------------------------------------------------------------------------- #
# AC-Z5: what a document must never hold
# --------------------------------------------------------------------------- #
def _forbidden(doc: Mapping[str, Any], banned_text: Iterable[str]) -> list[str]:
    """Prices, URLs and bound text the document must resolve rather than carry.

    Present as a check because it is the rule a well-meaning change breaks
    first: adding ``listPrice`` to a tile's props looks like a performance win
    and is a catalogue quoting one figure to every audience.
    """
    wanted = [(text, _normalise(text)) for text in banned_text]
    findings: list[str] = []

    for path, key, value in _walk(doc, "doc"):
        lowered = (key or "").lower()
        if any(token in lowered for token in _PRICE_KEY_TOKENS):
            findings.append(f"{path} binds a price field")
        elif any(token in lowered for token in _URL_KEY_TOKENS):
            findings.append(f"{path} binds a URL field")

        if not isinstance(value, str):
            continue
        if "://" in value or value.startswith("//"):
            findings.append(f"{path} holds a URL: {value!r}")
        if _PRICE_TEXT.search(value):
            findings.append(f"{path} holds a price: {value!r}")
        haystack = _normalise(value)
        for text, needle in wanted:
            if needle and needle in haystack:
                findings.append(f"{path} holds {text!r}")

    return findings


def _walk(node: Any, path: str, key: str | None = None):
    """Every node of the document EXCEPT the text the flyer itself printed.

    Section names and heading blocks are verbatim copy a designer edits, not
    bindings, and this extractor is known to carry a misread heading through
    unchanged. Scanning them would fail a run because of what the paper says.
    """
    yield path, key, node
    if isinstance(node, dict):
        for child_key, value in node.items():
            if _is_verbatim(node, child_key):
                continue
            yield from _walk(value, f"{path}.{child_key}", child_key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]", key)


def _is_verbatim(container: Mapping[str, Any], key: str) -> bool:
    if key == "name" and "blocks" in container:
        return True  # a section named after the flyer page
    return key == "text" and container.get("kind") == "heading"


__all__ = [
    "FIDELITY_THRESHOLD",
    "FidelityReport",
    "PageScore",
    "SEED_FIDELITY_BAR",
    "SEED_WEIGHTS",
    "SeedFidelityReport",
    "SeedPageScore",
    "WEIGHTS",
    "score_reading",
    "score_seed",
]
