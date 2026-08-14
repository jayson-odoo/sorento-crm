"""Link B: did the reading actually reach the seeded document? (UAC group Z)

Written before the scorer.

``test_dealer_kit_flyer_fidelity.py`` guards link A, paper to reading, and its
bar is 0.90 because paper is ambiguous and a heuristic reading it is allowed to
be imperfect. This file guards link B, reading to seeded document, and its bar
is **1.00**. The seeder is pure code operating on a structure it was handed, so
a card that does not reach the document is a bug with a line number, not a
tolerance to be tuned. That is why the assertion here is equality.

A number on its own would be useless at that bar: "0.97" tells a reader nothing
they can act on. So every failure must NAME the cards that went missing and say
where on the flyer they should have been.

**The one legitimate drop.** A printed code the master does not have cannot be
pinned: a collection pins product ids, and inventing a product for a code would
put a SKU nobody stocks in front of a customer (PLAN D8). So link B is scored
over the cards the seeder was ABLE to place, and every card it could not place
is reconciled against the seed result's ``skipped`` list. A card that vanishes
without appearing in ``skipped`` is exactly the defect this gate exists to
catch, and it fails the run outright rather than costing a fraction.

Postgres only, on a blank scratch schema, and storage is faked: creating a
reading stores every page's banner, and unfaked that is a live PUT into the real
bucket (see tests/_fake_storage.py).
"""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.dealer_kit import flyer_reading_service, flyer_seed_service
from app.services.dealer_kit.flyer_extraction import (
    FlyerCard,
    FlyerGrid,
    FlyerPage,
    FlyerReading,
    extract_flyer,
)
from app.services.dealer_kit.flyer_fidelity import (
    SEED_FIDELITY_BAR,
    SEED_WEIGHTS,
    score_seed,
)
from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

_SORENTO = "00000000-0000-0000-0000-000000000001"


# --------------------------------------------------------------------------- #
# The real thing: a real reading of the committed fixture, seeded for real
# --------------------------------------------------------------------------- #
@pytest.fixture
def db(monkeypatch):
    with blank_session() as session:
        patch_storage(monkeypatch)
        yield session


def _product(db, code: str):
    """A product carrying a code the fixture flyer actually prints.

    The CODE is real by necessity - matching a printed code is the entire point
    of the exercise, and a ZZT-prefixed code would match nothing. Everything
    else about the row is ZZT-scoped.
    """
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTSF")
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem, uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()

    product = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"ZZT product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(product)
    db.flush()
    return product


def _products(db, codes):
    """One product per code, sharing a single category and unit of measure.

    Shared on purpose for the 36 page run: 998 codes at three rows each is 2,994
    inserts, and the category a test product sits in is not what is under test.
    """
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = unique_code("ZZTSF")
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem, uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()

    made = {}
    for code in codes:
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=f"ZZT product {code}",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal("100.00"),
        )
        db.add(product)
        made[code] = product
    db.commit()
    return made


def _seeded(db, pdf: bytes, *, codes=None):
    """Read a flyer, stock the master with what it prints, and seed it.

    Returns everything the gate needs: the reading the seeder was handed, the
    document it produced, the collections it created, and what it reported as
    skipped.

    ``product_by_code`` is rebuilt from the SAME match report the seeder used.
    That is deliberate: link B is reading to document, and what a code resolves
    to against the master is link D's question (group D), tested there. What
    stops the two sharing a fate is the reconciliation below - every card the
    seeder could not place has to be in ``skipped``, so a matcher that silently
    lost a code still fails this gate.
    """
    record = flyer_reading_service.create_reading(
        db, filename="zzt-fidelity-flyer.pdf", data=pdf, user_id=None
    )
    reading = flyer_reading_service.to_reading(record)

    products = _products(db, codes if codes is not None else reading.codes)

    result = flyer_seed_service.seed(
        db,
        record,
        name=unique_code("ZZT Fidelity Catalogue"),
        slug=unique_code("zzt-fid").lower(),
        user_id=None,
    )

    report = flyer_reading_service.report_for(db, record)
    product_by_code = {entry.code: entry.product_id for entry in report.matched}

    return {
        "reading": reading,
        "doc": result.version.doc,
        "collections": result.collections,
        "skipped": result.skipped,
        "product_by_code": product_by_code,
        "products": products,
        "result": result,
    }


def _score(seeded, **extra):
    return score_seed(
        seeded["reading"],
        seeded["doc"],
        product_by_code=seeded["product_by_code"],
        collections=seeded["collections"],
        skipped=seeded["skipped"],
        **extra,
    )


@pytest.fixture
def fixture_seed(db):
    return _seeded(db, FIXTURE_PDF.read_bytes())


# --------------------------------------------------------------------------- #
# AC-Z3 - the seeder loses nothing, and the bar is equality
# --------------------------------------------------------------------------- #
class TestLinkB:
    def test_the_reading_reaches_the_document_exactly(self, fixture_seed) -> None:
        """1.00, not a threshold.

        The extractor is allowed to be imperfect because paper is ambiguous.
        The seeder is not: it was handed a structure. Anything below 1.00 is a
        defect with a line number.
        """
        report = _score(fixture_seed)
        assert report.composite == SEED_FIDELITY_BAR, report.summary()
        assert report.passes, report.summary()

    def test_every_component_is_exactly_one(self, fixture_seed) -> None:
        """Not just the composite: a weighted average can hide a component.

        0.30 lost on grouping and 0.30 gained on coverage cannot happen at 1.00,
        but pinning each component separately is what makes the FAILURE readable
        rather than sending somebody hunting for which one moved.
        """
        report = _score(fixture_seed)
        for key in SEED_WEIGHTS:
            assert report.component(key) == 1.0, report.summary()

    def test_nothing_was_lost_and_nothing_was_invented(self, fixture_seed) -> None:
        report = _score(fixture_seed)
        assert report.lost == [], report.summary()
        assert report.invented == [], report.summary()

    def test_every_card_is_either_in_the_document_or_in_skipped(
        self, fixture_seed
    ) -> None:
        """The reconciliation this gate exists for.

        The seeder legitimately drops a code the master does not have. It must
        never drop one for any other reason, and the only way to tell the two
        apart is to insist that everything dropped is named in ``skipped``.
        """
        report = _score(fixture_seed)
        placed = {code for page in report.pages for code in page.placed}
        accounted = {code for page in report.pages for code in page.unplaceable}
        for page in fixture_seed["reading"].pages:
            for card in page.cards:
                assert card.code in placed or card.code in accounted, report.summary()


# --------------------------------------------------------------------------- #
# AC-Z4 / AC-Z5 - what must not be in the document
# --------------------------------------------------------------------------- #
class TestForbidden:
    def test_every_code_in_the_document_was_printed_on_the_flyer(
        self, fixture_seed
    ) -> None:
        """AC-Z4. A catalogue offering a product the flyer never advertised is a
        different kind of wrong from one missing a product, so it fails the run
        outright rather than costing a fraction of a component."""
        report = _score(fixture_seed)
        assert report.invented == [], report.summary()

        printed = set(fixture_seed["product_by_code"].values())
        for collection in fixture_seed["collections"]:
            assert set(collection.pinned_product_ids or []) <= printed

    def test_the_document_binds_no_price_no_photo_url_and_no_company_name(
        self, fixture_seed
    ) -> None:
        """AC-Z5, and the rule a well-meaning change breaks first.

        A price written into the document freezes one number for every audience
        and breaks the one thing the Kit exists to do. A photo URL breaks the
        moment the file is re-signed or renamed. Both are resolved per viewer at
        read time from ids the document holds instead.
        """
        codes = list(fixture_seed["product_by_code"])
        names = [f"ZZT product {code}" for code in codes]
        report = _score(fixture_seed, banned_text=["Sorento", *codes, *names])
        assert report.forbidden == [], report.summary()
        assert report.composite == SEED_FIDELITY_BAR, report.summary()


# --------------------------------------------------------------------------- #
# AC-Z6 - a number is never reported without the list behind it
# --------------------------------------------------------------------------- #
class TestTheReadout:
    def test_the_summary_breaks_the_score_down_by_component(
        self, fixture_seed
    ) -> None:
        summary = _score(fixture_seed).summary()
        for key in SEED_WEIGHTS:
            assert key in summary

    def test_the_summary_names_the_cards_the_master_could_not_place(self, db) -> None:
        """The fixture prints SRTWC286-SH; this run gives the master everything
        else. The card cannot be pinned, so it is reported as unplaceable AND
        reconciled against ``skipped`` - which is what stops it being confused
        with a card the seeder lost."""
        reading = extract_flyer(FIXTURE_PDF.read_bytes())
        stocked = [code for code in reading.codes if code != "SRTWC286-SH"]

        seeded = _seeded(db, FIXTURE_PDF.read_bytes(), codes=stocked)
        report = _score(seeded)

        assert report.composite == SEED_FIDELITY_BAR, report.summary()
        assert "SRTWC286-SH" in report.summary()
        assert report.lost == []
        unplaceable = [code for page in report.pages for code in page.unplaceable]
        assert "SRTWC286-SH" in unplaceable


# --------------------------------------------------------------------------- #
# The gate has to BITE. A gate that cannot fail is worse than no gate.
#
# These build the document by hand rather than seeding, because the point is to
# show the scorer catching a defect the real seeder does not currently have.
# --------------------------------------------------------------------------- #
class _FakeCollection:
    def __init__(self, ident: str, pins: list[str], order: list[str] | None = None):
        self.id = ident
        self.pinned_product_ids = pins
        self.manual_order = pins if order is None else order


def _reading_of(rows_by_page: list[list[list[str]]]) -> FlyerReading:
    """A reading printed exactly as described: pages of rows of codes."""
    reading = FlyerReading()
    for number, rows in enumerate(rows_by_page, start=1):
        page = FlyerPage(number=number, width=842.0, height=1191.0)
        for row_index, row in enumerate(rows):
            cards = [
                FlyerCard(code=code, lines=[code], x=float(index), y=float(row_index))
                for index, code in enumerate(row)
            ]
            page.cards.extend(cards)
            page.grids.append(FlyerGrid(cards=cards, y=float(row_index)))
        reading.pages.append(page)
    return reading


def _doc_of(sections: list[list[str]]) -> dict:
    """A document holding one collection block per collection id given."""
    return {
        "sections": [
            {
                "id": f"sec-{index}",
                "name": f"Page {index + 1}",
                "style": {"background": "transparent"},
                "blocks": [
                    {
                        "id": f"blk-{index}-{position}",
                        "type": "collection",
                        "props": {
                            "kind": "collection",
                            "collectionId": collection_id,
                            "tileTemplateId": None,
                            "columns": {"desktop": 3, "tablet": 3, "mobile": 1},
                        },
                    }
                    for position, collection_id in enumerate(ids)
                ],
                "printMode": "breakBefore",
            }
            for index, ids in enumerate(sections)
        ],
        "printProfile": {"pageSize": "A3"},
    }


class TestTheGateBites:
    def test_a_card_the_seeder_drops_is_named_with_where_it_should_have_been(
        self,
    ) -> None:
        """The whole reason the bar is equality.

        "0.97" tells nobody anything. The failure has to say WHICH card and
        WHERE on the flyer, or the gate is a number without an action behind it.
        """
        reading = _reading_of([[["a", "b", "c"]]])
        pins = {"a": "p-a", "b": "p-b", "c": "p-c"}
        # The last card of the row never reaches the document, and nothing says
        # so: this is the silent loss the gate exists to catch.
        collection = _FakeCollection("col-1", ["p-a", "p-b"])

        report = score_seed(
            reading,
            _doc_of([["col-1"]]),
            product_by_code=pins,
            collections=[collection],
            skipped=[],
        )

        assert report.composite < SEED_FIDELITY_BAR
        assert not report.passes
        assert report.lost == ["c"]
        summary = report.summary()
        assert "c" in summary
        assert "page 1" in summary
        assert "row 1" in summary
        assert "position 3" in summary

    def test_a_card_dropped_because_the_master_lacks_it_is_not_a_loss(self) -> None:
        """The one legitimate drop, reconciled against ``skipped``.

        The seeder cannot pin a code with no product. That is a gap somebody can
        see, not a defect, so it must not cost the score.
        """
        reading = _reading_of([[["a", "b", "c"]]])
        collection = _FakeCollection("col-1", ["p-a", "p-b"])

        report = score_seed(
            reading,
            _doc_of([["col-1"]]),
            product_by_code={"a": "p-a", "b": "p-b"},  # "c" resolves to nothing
            collections=[collection],
            skipped=["c"],
        )

        assert report.composite == SEED_FIDELITY_BAR, report.summary()
        assert report.lost == []
        assert report.pages[0].unplaceable == ["c"]

    def test_the_same_card_missing_from_skipped_is_a_loss(self) -> None:
        """The pair to the test above, and the point of the whole gate.

        Identical document, identical master, identical card missing. The ONLY
        difference is whether the seed result admitted to dropping it. An
        implementation that could not tell these two runs apart would let a
        silently lost card score 1.00.
        """
        reading = _reading_of([[["a", "b", "c"]]])
        collection = _FakeCollection("col-1", ["p-a", "p-b"])

        report = score_seed(
            reading,
            _doc_of([["col-1"]]),
            product_by_code={"a": "p-a", "b": "p-b"},
            collections=[collection],
            skipped=[],  # the seed never admitted to dropping it
        )

        assert report.lost == ["c"]
        assert report.composite == 0.0
        assert "c" in report.summary()

    def test_a_product_the_flyer_never_printed_fails_the_run_outright(self) -> None:
        """AC-Z4. Not a component with a weight."""
        reading = _reading_of([[["a", "b"]]])
        collection = _FakeCollection("col-1", ["p-a", "p-b", "p-ghost"])

        report = score_seed(
            reading,
            _doc_of([["col-1"]]),
            product_by_code={"a": "p-a", "b": "p-b"},
            collections=[collection],
        )

        assert report.invented == ["p-ghost"]
        assert report.composite == 0.0
        assert "p-ghost" in report.summary()

    def test_a_card_landing_in_the_wrong_section_costs_placement(self) -> None:
        """Same document, right cards, wrong page.

        Coverage alone would score this 1.00: everything the flyer printed is
        somewhere in the catalogue. A reader holding the flyer would find the
        bathtubs under Water Closets.
        """
        reading = _reading_of([[["a"]], [["b"]]])
        first = _FakeCollection("col-1", ["p-a", "p-b"])

        report = score_seed(
            reading,
            _doc_of([["col-1"], []]),
            product_by_code={"a": "p-a", "b": "p-b"},
            collections=[first],
        )

        assert report.component("coverage") == 1.0
        assert report.component("section") < 1.0
        assert report.composite < SEED_FIDELITY_BAR
        assert "b" in report.summary()

    def test_a_row_printed_out_of_order_costs_order(self) -> None:
        """The paper decides the order, not the master (AC-E3)."""
        reading = _reading_of([[["a", "b", "c"]]])
        reversed_row = _FakeCollection(
            "col-1", ["p-a", "p-b", "p-c"], order=["p-c", "p-b", "p-a"]
        )

        report = score_seed(
            reading,
            _doc_of([["col-1"]]),
            product_by_code={"a": "p-a", "b": "p-b", "c": "p-c"},
            collections=[reversed_row],
        )

        assert report.component("coverage") == 1.0
        assert report.component("grouping") == 1.0
        assert report.component("order") == 0.0
        assert report.composite < SEED_FIDELITY_BAR

    def test_two_printed_rows_merged_into_one_costs_grouping(self) -> None:
        """A row is the layout unit. Merging two makes a grid the flyer never
        printed, and every tile in it sits beside a neighbour it was not
        printed with."""
        reading = _reading_of([[["a", "b"], ["c", "d"]]])
        merged = _FakeCollection("col-1", ["p-a", "p-b", "p-c", "p-d"])

        report = score_seed(
            reading,
            _doc_of([["col-1"]]),
            product_by_code={"a": "p-a", "b": "p-b", "c": "p-c", "d": "p-d"},
            collections=[merged],
        )

        assert report.component("coverage") == 1.0
        assert report.component("grouping") < 1.0
        assert report.composite < SEED_FIDELITY_BAR

    def test_rows_laid_down_out_of_printed_sequence_cost_sequence(self) -> None:
        """Down the page as well as across it: a catalogue that prints the
        flyer's third row first is not the same document."""
        reading = _reading_of([[["a"], ["b"]]])
        top = _FakeCollection("col-1", ["p-a"])
        bottom = _FakeCollection("col-2", ["p-b"])

        report = score_seed(
            reading,
            _doc_of([["col-2", "col-1"]]),  # printed second row placed first
            product_by_code={"a": "p-a", "b": "p-b"},
            collections=[top, bottom],
        )

        assert report.component("coverage") == 1.0
        assert report.component("grouping") == 1.0
        assert report.component("sequence") == 0.0
        assert report.composite < SEED_FIDELITY_BAR

    def test_a_block_pointing_at_a_collection_that_does_not_exist_fails(self) -> None:
        """It renders an empty grid inside a page that otherwise looks complete,
        which is the failure mode the seeder avoids by never emitting an empty
        collection at all."""
        reading = _reading_of([[["a"]]])

        report = score_seed(
            reading,
            _doc_of([["col-missing"]]),
            product_by_code={"a": "p-a"},
            collections=[],
        )

        assert report.dangling == ["col-missing"]
        assert report.composite == 0.0
        assert "col-missing" in report.summary()

    def test_a_missing_section_is_reported_rather_than_shifting_every_page(
        self,
    ) -> None:
        """One section per flyer page (AC-E1). A dropped section renumbers every
        page after it, so a reviewer holding the flyer can no longer line the
        draft up against the paper."""
        reading = _reading_of([[["a"]], [["b"]]])
        second = _FakeCollection("col-2", ["p-b"])

        report = score_seed(
            reading,
            _doc_of([["col-2"]]),  # only ONE section for two flyer pages
            product_by_code={"a": "p-a", "b": "p-b"},
            collections=[second],
            skipped=[],
        )

        assert report.composite < SEED_FIDELITY_BAR
        assert "section" in report.summary()
        assert report.lost == ["a"]


class TestForbiddenBites:
    """AC-Z5 asserted from the failing side, because a rule nobody has broken on
    purpose is a rule nobody knows is enforced."""

    def _reading(self) -> FlyerReading:
        return _reading_of([[["a"]]])

    def _base(self) -> tuple[dict, list]:
        return _doc_of([["col-1"]]), [_FakeCollection("col-1", ["p-a"])]

    def test_a_bound_price_fails_the_run(self) -> None:
        doc, collections = self._base()
        doc["sections"][0]["blocks"][0]["props"]["listPrice"] = "1299.00"

        report = score_seed(
            self._reading(),
            doc,
            product_by_code={"a": "p-a"},
            collections=collections,
        )

        assert report.forbidden, report.summary()
        assert "listPrice" in report.summary()
        assert report.composite == 0.0

    def test_a_bound_photo_url_fails_the_run(self) -> None:
        doc, collections = self._base()
        doc["sections"][0]["style"]["backgroundUrl"] = "https://cdn.test/banner.jpg"

        report = score_seed(
            self._reading(),
            doc,
            product_by_code={"a": "p-a"},
            collections=collections,
        )

        assert report.forbidden, report.summary()
        assert report.composite == 0.0

    def test_a_bound_company_name_fails_the_run(self) -> None:
        doc, collections = self._base()
        doc["sections"][0]["style"]["watermark"] = "Sorento Sdn Bhd"

        report = score_seed(
            self._reading(),
            doc,
            product_by_code={"a": "p-a"},
            collections=collections,
            banned_text=["Sorento"],
        )

        assert report.forbidden, report.summary()
        assert report.composite == 0.0

    def test_flyer_text_carried_through_verbatim_is_not_a_violation(self) -> None:
        """A heading is text a designer edits, not a binding.

        The extractor carries headings through verbatim, and the real flyer
        prints prices inside its own artwork copy. Failing the run because a
        heading read "RM 1,299 OFF" would punish the seeder for the paper, and
        the tile beside it still resolves its price per viewer.
        """
        doc, collections = self._base()
        doc["sections"][0]["name"] = "SRTJC8037 SALE RM 1,299"
        doc["sections"][0]["blocks"].insert(
            0,
            {
                "id": "blk-h",
                "type": "heading",
                "props": {"kind": "heading", "text": "Sorento RM 1,299 OFF", "scale": "2xl"},
            },
        )

        report = score_seed(
            self._reading(),
            doc,
            product_by_code={"a": "p-a"},
            collections=collections,
            banned_text=["Sorento", "SRTJC8037"],
        )

        assert report.forbidden == [], report.summary()
        assert report.composite == SEED_FIDELITY_BAR, report.summary()


# --------------------------------------------------------------------------- #
# AC-Z7 - the whole document, not only the fixture
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not os.environ.get("FLYER_FIXTURE_PDF"),
    reason="Set FLYER_FIXTURE_PDF to score the seed of the whole 36 page flyer",
)
def test_the_whole_flyer_seeds_at_one_point_zero(db, capsys) -> None:
    """The 36 page document, which is too large to commit (AC-Z7).

    Three pages are not a proof of scale: the real flyer holds 998 codes across
    347 printed rows, including rows the 24pt tolerance splits and codes the
    master does not have. CI guards the committed fixture; this is how the real
    document gets a number before anything is published from it.
    """
    seeded = _seeded(db, Path(os.environ["FLYER_FIXTURE_PDF"]).read_bytes())
    codes = list(seeded["product_by_code"])
    report = _score(seeded, banned_text=["Sorento", *codes])

    with capsys.disabled():
        print("\n" + report.summary())

    assert len(seeded["reading"].pages) > 3
    assert report.composite == SEED_FIDELITY_BAR, report.summary()


def test_the_document_is_json_serialisable_as_stored(fixture_seed) -> None:
    """A guard on the scan itself: the forbidden-text walk reads the document as
    the database holds it, so anything the walk cannot reach is something the
    database would not hold either."""
    assert json.loads(json.dumps(fixture_seed["doc"])) == fixture_seed["doc"]
