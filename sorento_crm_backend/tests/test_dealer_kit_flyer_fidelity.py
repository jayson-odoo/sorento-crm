"""The 90% gate: is the reading still the document? (UAC group Z)

The scored artefact is a hand-verified transcript of what is printed on the
fixture pages, NOT the extractor's own output. Scoring the extractor against
itself would let it misread the flyer completely and still pass.

The scorer itself is tested too. A metric nobody has tried to break is a metric
that reports whatever the code happens to compute, and this one decides whether
a catalogue is fit to publish.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from app.services.dealer_kit.flyer_extraction import extract_flyer
from app.services.dealer_kit.flyer_fidelity import (
    FIDELITY_THRESHOLD,
    WEIGHTS,
    score_reading,
)

FIXTURES = Path(__file__).parent / "fixtures" / "dealer_kit"
FIXTURE_PDF = FIXTURES / "flyer_sample.pdf"
GOLDEN = FIXTURES / "flyer_golden.json"


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def report(golden: dict):
    return score_reading(extract_flyer(FIXTURE_PDF.read_bytes()), golden)


class TestTheGate:
    def test_the_reading_is_at_least_ninety_percent_the_document(self, report) -> None:
        assert report.composite >= FIDELITY_THRESHOLD, report.summary()

    def test_nothing_was_invented(self, report) -> None:
        # Not a component with a weight: a catalogue offering a product the
        # flyer never advertised is a different kind of wrong from one missing a
        # product, so it fails the run outright.
        assert report.invented == [], report.summary()

    def test_every_component_is_reported_separately(self, report) -> None:
        # So a regression names which one moved instead of just dropping a
        # single number (AC-Z6).
        summary = report.summary()
        for key in WEIGHTS:
            assert key in summary

    def test_what_was_missed_is_named(self, report) -> None:
        # SRT764-25 is printed as "SRT764-25 -CR", with a space inside the SKU.
        # It is a known miss, it is NOT forgiven by the score, and it must be
        # listed rather than quietly absorbed.
        missed = [code for page in report.pages for code in page.missed]
        assert "SRT764-25" in missed
        assert "SRT764-25" in report.summary()

    def test_the_golden_is_pinned_to_this_fixture(self, golden: dict) -> None:
        # If the PDF changes, the transcript must be re-verified against the new
        # one rather than silently re-blessed.
        digest = hashlib.sha256(FIXTURE_PDF.read_bytes()).hexdigest()
        assert digest.startswith(golden["sha256_prefix"])


class TestComponents:
    def test_a_dense_page_counts_for_more_than_a_cover(self, report) -> None:
        cover = next(page for page in report.pages if page.number == 1)
        spread = next(page for page in report.pages if page.number == 3)
        assert spread.weight > cover.weight

    def test_the_wrong_heading_is_caught(self, report) -> None:
        # The detector reads "Transforming Your" on the bathtub spread, where the
        # printed title is "BATHTUB COLLECTION". Pinned deliberately: the gate is
        # only worth having if it fails on a real defect, and this is the known
        # one.
        bathtub = next(page for page in report.pages if page.number == 2)
        assert bathtub.heading == 0.0

    def test_headings_match_on_words_not_whitespace(self, golden: dict) -> None:
        from app.services.dealer_kit.flyer_fidelity import _heading

        # The flyer letterspaces its titles, and a reader would call these the
        # same heading.
        assert _heading("BATHTUB COLLECTION", "B A T H T U B  C O L L E C T I O N") == 1.0
        assert _heading("BATHTUB COLLECTION", "Transforming Your") == 0.0

    def test_grouping_is_measured_per_product_not_per_row(self) -> None:
        from app.services.dealer_kit.flyer_fidelity import _grouping

        # A row split in half keeps each product beside SOME of its neighbours,
        # so it must cost a fraction rather than everything: rows do not line up
        # one to one once the extractor splits or merges one.
        printed = [["a", "b", "c", "d"]]
        split = [["a", "b"], ["c", "d"]]
        assert 0.0 < _grouping(printed, split) < 1.0
        assert _grouping(printed, printed) == 1.0

    def test_a_lost_product_has_no_neighbours(self) -> None:
        from app.services.dealer_kit.flyer_fidelity import _grouping

        assert _grouping([["a", "b"]], [["a"]]) < 1.0

    def test_order_costs_a_fraction_of_a_row_not_the_row(self) -> None:
        from app.services.dealer_kit.flyer_fidelity import _order

        printed = [["a", "b", "c", "d"]]
        # One product moved to the end: three adjacent pairs printed, two kept.
        moved = [["a", "c", "d", "b"]]
        assert _order(printed, moved) == pytest.approx(2 / 3)
        assert _order(printed, printed) == 1.0

    def test_a_page_read_as_empty_scores_zero_not_one(self) -> None:
        from app.services.dealer_kit.flyer_fidelity import score_reading
        from app.services.dealer_kit.flyer_extraction import FlyerReading

        # The failure mode a naive ratio hides: nothing read means nothing wrong.
        empty = FlyerReading()
        report = score_reading(
            empty,
            {"pages": [{"number": 1, "codes": ["a", "b"], "rows": [["a", "b"]],
                        "heading": "X", "full_width_band": True}]},
        )
        assert report.composite == 0.0
        assert not report.passes


@pytest.mark.skipif(
    not os.environ.get("FLYER_FIXTURE_PDF"),
    reason="Set FLYER_FIXTURE_PDF to score the whole 36 page flyer",
)
def test_the_whole_flyer_can_be_scored() -> None:
    """The full document, which is too large to commit (AC-Z7).

    CI guards the three committed pages; this is how the real 36 page flyer gets
    a number before anything is published from it.
    """
    reading = extract_flyer(Path(os.environ["FLYER_FIXTURE_PDF"]).read_bytes())

    assert len(reading.pages) > 3
    assert reading.codes
