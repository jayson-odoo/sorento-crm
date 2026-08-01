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

Link A, here, scores a reading against a hand-verified transcript of what is
actually printed. Link B is mechanical, so its bar is exact equality rather than
a tolerance, and it lands with the seeder.

Invention is not scored, it is forbidden. A tolerance on the way IN is not a
tolerance on the way OUT: a catalogue offering a product the flyer never
advertised is a different kind of wrong from one missing a product, so it fails
the run outright rather than costing a fraction of a component.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from app.services.dealer_kit.flyer_extraction import FlyerReading

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
        for key in WEIGHTS:
            value = _weighted(self.pages, key)
            lines.append(f"  {key:<10} {value:.3f}  (weight {WEIGHTS[key]:.2f})")
        for page in self.pages:
            if page.missed or page.invented:
                lines.append(f"  page {page.number}:")
                if page.missed:
                    lines.append(f"    missed:   {', '.join(page.missed)}")
                if page.invented:
                    lines.append(f"    INVENTED: {', '.join(page.invented)}")
        return "\n".join(lines)


def _weighted(pages: Sequence[PageScore], key: str) -> float:
    total = sum(page.weight for page in pages)
    if not total:
        return 0.0
    return sum(getattr(page, key) * page.weight for page in pages) / total


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
