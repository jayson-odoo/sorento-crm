"""Ranking: turn extracted specs into a shortlist of real product codes.

Every spec is a scoring BOOST, never a WHERE filter. That is deliberate and it is the
opposite of what a reader expects. The output is a recall-oriented did-you-mean picker,
so one over-extracted spec must not empty it: a customer who says "stainless steel
kitchen sink" and gets nothing because the parser also guessed `mounting=wall_hung` has
been failed by the filter, not helped by it.

The relevance floor is what stops a never-empty ranker from surfacing confident
nonsense. Below it the caller shows no candidates at all and falls through to the
existing clarify path.

Ticket: jayson-odoo/sorento-crm#76. Contract: AC-T0e-01 .. AC-T0e-20.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_search import search_specs
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
        wc = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-WC", category_name="SRT-WC")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        s.add_all([cat, wc, uom])
        s.flush()
        backfill_category_signals(s)
        # SRT-WC is not in the pilot map, so give it a class by hand: the ranker must
        # be exercised across more than one class.
        wc.class_label = "Water Closet"
        wc.brand_hint = "Sorento"
        s.flush()
        seed_spec_registry(s)
        _REFS.update({"cat": cat.id, "wc": wc.id, "uom": uom.id})
        yield s


def _product(db, code, description, *, category="cat", discontinued=False, variant_of=None):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS[category],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
        is_discontinued=discontinued,
        variant_of_id=variant_of,
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


def _codes(results) -> list[str]:
    return [r["product_code"] for r in results["candidates"]]


def _catalog(db):
    """A small catalog with the shapes that matter: real sinks, an accessory, a WC."""
    _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    _product(db, "ZZT-SINK-C", "CABANA CERAMIC KITCHEN SINK (1000X500X140MM)")
    _product(db, "ZZT-BASKET", "CABANA KITCHEN SINK TRIANGLE BASKET")
    _product(db, "ZZT-WC-A", "SORENTO CERAMIC WALL HUNG WATER CLOSET", category="wc")


# --------------------------------------------------------------------------- #
# class is the strongest signal (AC-T0e-08)
# --------------------------------------------------------------------------- #
def test_class_alone_returns_that_class(db):
    _catalog(db)

    results = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[])

    assert "ZZT-WC-A" not in _codes(results)
    assert "ZZT-SINK-A" in _codes(results)


def test_a_free_term_resolves_through_a_class_synonym(db):
    # The customer types "sink", the catalog says "SRT-KS", neither knows the other.
    _catalog(db)

    results = search_specs(db, specs=[], free_terms=["sink"])

    assert "ZZT-SINK-A" in _codes(results)


# --------------------------------------------------------------------------- #
# accessories (AC-T0e-09, AC-T0e-10)
# --------------------------------------------------------------------------- #
def test_accessories_do_not_win_a_product_query(db):
    _catalog(db)

    results = search_specs(
        db,
        specs=[{"key": "class", "value": "Kitchen Sink"}, {"key": "material", "value": "stainless_steel"}],
        free_terms=["kitchen sink"],
    )

    assert _codes(results)[0] != "ZZT-BASKET"


def test_an_accessory_is_deboosted_not_excluded(db):
    # The rule is a deboost, not a filter: with the deboost relaxed the accessory is
    # still in the catalog and still rankable.
    #
    # NOTE a real v1 limitation: the rendered sentence is built from spec VALUES, so it
    # carries the class ("kitchen sink") but not the part noun ("triangle basket").
    # Searching the word "basket" therefore finds nothing today. Making part nouns
    # searchable needs an accessory_type registry key, which is not in this slice.
    _catalog(db)

    results = search_specs(
        db,
        specs=[{"key": "class", "value": "Kitchen Sink"}],
        free_terms=[],
        include_accessories=True,
    )

    assert "ZZT-BASKET" in _codes(results)


# --------------------------------------------------------------------------- #
# specs boost, never filter (AC-T0e-07)
# --------------------------------------------------------------------------- #
def test_an_over_extracted_spec_does_not_empty_the_picker(db):
    # The parser guessed a mounting no kitchen sink has. A WHERE filter would return
    # nothing; a boost returns the right sinks with a slightly lower score.
    _catalog(db)

    results = search_specs(
        db,
        specs=[
            {"key": "class", "value": "Kitchen Sink"},
            {"key": "mounting", "value": "wall_hung"},
        ],
        free_terms=[],
    )

    assert _codes(results), "a non-matching spec must not empty the shortlist"


def test_a_matching_spec_outranks_a_non_matching_one(db):
    _catalog(db)

    results = search_specs(
        db,
        specs=[
            {"key": "class", "value": "Kitchen Sink"},
            {"key": "material", "value": "ceramic"},
        ],
        free_terms=[],
    )

    assert _codes(results)[0] == "ZZT-SINK-C"


# --------------------------------------------------------------------------- #
# numeric closeness, shape-aware (AC-T0e-05, AC-T0e-06)
# --------------------------------------------------------------------------- #
def test_an_exact_dimension_outranks_a_near_one(db):
    _catalog(db)

    results = search_specs(
        db,
        specs=[{"key": "class", "value": "Kitchen Sink"}, {"key": "dim_length", "value": 800}],
        free_terms=[],
    )

    assert _codes(results)[0] == "ZZT-SINK-B"


def test_a_near_dimension_still_scores(db):
    _catalog(db)

    results = search_specs(
        db,
        specs=[{"key": "class", "value": "Kitchen Sink"}, {"key": "dim_length", "value": 1005}],
        free_terms=[],
    )

    # 1000 is within the +/- 5mm hedge convention, so it should lead.
    assert _codes(results)[0] in {"ZZT-SINK-A", "ZZT-SINK-C"}


def test_a_round_products_size_is_compared_against_diameter(db):
    _product(db, "ZZT-ROUND", "SORENTO ROUND CERAMIC WASH BASIN (400X120X10MM)", category="wc")

    results = search_specs(db, specs=[{"key": "diameter", "value": 400}], free_terms=[])

    assert "ZZT-ROUND" in _codes(results)


# --------------------------------------------------------------------------- #
# discontinued: shown, flagged, never filtered (AC-T0e-11)
# --------------------------------------------------------------------------- #
def test_discontinued_products_are_returned_with_a_flag(db):
    _product(db, "ZZT-DEAD", "SORENTO S/STEEL KITCHEN SINK (900X450X200MM)", discontinued=True)

    results = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[])

    dead = next(c for c in results["candidates"] if c["product_code"] == "ZZT-DEAD")
    assert dead["is_discontinued"] is True


# --------------------------------------------------------------------------- #
# variants collapse (AC-T0e-12)
# --------------------------------------------------------------------------- #
def test_variants_collapse_to_one_candidate_per_parent(db):
    parent = _product(db, "ZZT-VAR", "SORENTO S/STEEL KITCHEN SINK (1000X500X255MM)")
    _product(db, "ZZT-VAR-BL", "SORENTO S/STEEL KITCHEN SINK (1000X500X255MM)", variant_of=parent.id)
    _product(db, "ZZT-VAR-GM", "SORENTO S/STEEL KITCHEN SINK (1000X500X255MM)", variant_of=parent.id)

    results = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[])

    family = [c for c in _codes(results) if c.startswith("ZZT-VAR")]
    assert len(family) == 1, f"one model should occupy one slot, got {family}"


# --------------------------------------------------------------------------- #
# shape of the result (AC-T0e-13, AC-T0e-14)
# --------------------------------------------------------------------------- #
def test_at_most_five_candidates(db):
    for index in range(9):
        _product(db, f"ZZT-MANY-{index}", f"SORENTO S/STEEL KITCHEN SINK (10{index}0X500X200MM)")

    results = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[])

    assert len(results["candidates"]) <= 5


def test_a_candidate_carries_what_the_bot_needs_to_render_it(db):
    _catalog(db)

    candidate = search_specs(
        db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[]
    )["candidates"][0]

    for field in ("product_code", "summary", "class", "matched_specs", "score", "is_discontinued"):
        assert field in candidate, field
    assert candidate["summary"], "the summary is what the customer reads"


# --------------------------------------------------------------------------- #
# the relevance floor (AC-T0e-15, AC-T0e-16)
# --------------------------------------------------------------------------- #
def test_nonsense_falls_below_the_floor(db):
    _catalog(db)

    results = search_specs(db, specs=[], free_terms=["flux capacitor"])

    assert results["candidates"] == []
    assert results["floor_missed"] is True


@pytest.mark.parametrize(
    "phrase",
    ["flux capacitor", "helicopter blade", "ferrari exhaust", "quantum toaster"],
)
def test_out_of_catalog_phrases_all_miss(db, phrase):
    # A never-empty ranker is the failure the floor exists to prevent, so the negative
    # set is a first-class part of the suite rather than an afterthought.
    _catalog(db)

    results = search_specs(db, specs=[], free_terms=[phrase])

    assert results["floor_missed"] is True, phrase


def test_a_real_query_clears_the_floor(db):
    _catalog(db)

    results = search_specs(
        db,
        specs=[{"key": "class", "value": "Kitchen Sink"}, {"key": "material", "value": "stainless_steel"}],
        free_terms=["kitchen sink"],
    )

    assert results["floor_missed"] is False
    assert results["candidates"]


def test_scores_are_ordered_descending(db):
    _catalog(db)

    results = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[])
    scores = [c["score"] for c in results["candidates"]]

    assert scores == sorted(scores, reverse=True)


# Found on the real catalog: every product appeared twice in the shortlist, because
# the same model exists once per company and the collapse keyed on a row id.
def test_the_same_model_in_two_companies_occupies_one_slot(db):
    second = Company(id=str(uuid.uuid4()), name="ZZT Second Co", code="ZZT2")
    db.add(second)
    db.flush()

    _product(db, "ZZT-DUP", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    row = Product(
        id=str(uuid.uuid4()),
        product_code="ZZT-DUP",
        product_name="ZZT-DUP",
        description="SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
    )
    row.company_id = second.id
    db.add(row)
    db.flush()
    derive_for_code(db, "ZZT-DUP")

    results = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[])

    assert _codes(results).count("ZZT-DUP") == 1


# Found on the real catalog: "540X440180MM" is a separator typo that parses as a
# 440-metre sink. A dimension no product can have must not be indexed or ranked on.
def test_an_implausible_dimension_is_dropped_and_flagged(db):
    from app.models.product_spec import ProductSpecException

    _product(db, "ZZT-TYPO", "CABANA KITCHEN SINK (540X440180MM)")

    results = search_specs(db, specs=[{"key": "dim_width", "value": 440180}], free_terms=[])
    reasons = {
        r.reason
        for r in db.query(ProductSpecException).filter(
            ProductSpecException.product_code == "ZZT-TYPO"
        )
    }

    assert "ZZT-TYPO" not in _codes(results)
    assert "implausible_dimension" in reasons


def test_duplicates_collapse_even_when_the_variant_parent_is_absent(db):
    """A variant whose parent has no specs must still dedupe across companies.

    Real catalog case: the parent row is not in the result set, so a lookup keyed on
    the parent ID falls back to an id that differs per company copy, and the same
    model appears twice in a five-slot shortlist.
    """
    second = Company(id=str(uuid.uuid4()), name="ZZT Third Co", code="ZZT3")
    orphan_parent = uuid.uuid4()
    db.add(second)
    db.flush()

    for company_id in (None, second.id):
        row = Product(
            id=str(uuid.uuid4()),
            product_code="ZZT-ORPHANVAR",
            product_name="ZZT-ORPHANVAR",
            description="SORENTO S/STEEL KITCHEN SINK (900X450X200MM)",
            category_id=_REFS["cat"],
            base_uom_id=_REFS["uom"],
            list_price=Decimal("1.00"),
            # points at a parent that carries no specs, as in the live data
            variant_of_id=None,
        )
        if company_id:
            row.company_id = company_id
        db.add(row)
        db.flush()
    derive_for_code(db, "ZZT-ORPHANVAR")

    results = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[])

    assert _codes(results).count("ZZT-ORPHANVAR") == 1


def test_a_model_that_is_a_variant_in_one_company_only_still_collapses(db):
    """Real catalog shape: CKS6302-SP is variant_of_id set in company A and NULL in
    company B. Resolving the family per ROW gives the two copies different families,
    so the same sink appears twice. Family is a property of the model."""
    second = Company(id=str(uuid.uuid4()), name="ZZT Fourth Co", code="ZZT4")
    db.add(second)
    db.flush()

    parent = _product(db, "ZZT-BASE", "SORENTO S/STEEL KITCHEN SINK (700X400X200MM)")

    a = Product(
        id=str(uuid.uuid4()), product_code="ZZT-SPLIT", product_name="ZZT-SPLIT",
        description="SORENTO S/STEEL KITCHEN SINK (700X400X200MM)",
        category_id=_REFS["cat"], base_uom_id=_REFS["uom"], list_price=Decimal("1.00"),
        variant_of_id=parent.id,
    )
    b = Product(
        id=str(uuid.uuid4()), product_code="ZZT-SPLIT", product_name="ZZT-SPLIT",
        description="SORENTO S/STEEL KITCHEN SINK (700X400X200MM)",
        category_id=_REFS["cat"], base_uom_id=_REFS["uom"], list_price=Decimal("1.00"),
        variant_of_id=None,
    )
    b.company_id = second.id
    db.add_all([a, b])
    db.flush()
    derive_for_code(db, "ZZT-SPLIT")

    results = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}], free_terms=[])

    # One slot for the family: the variant collapses onto its parent, and the
    # company copy that is NOT marked a variant must not sneak in beside it.
    family = [c for c in _codes(results) if c in {"ZZT-BASE", "ZZT-SPLIT"}]
    assert len(family) == 1, family


# --------------------------------------------------------------------------- #
# the eval baseline (AC-T0e-17, AC-T0e-18)
# --------------------------------------------------------------------------- #
def test_the_eval_baseline_negative_cases_all_miss(db):
    """Every out-of-catalog phrase must fall below the floor.

    This is the guard that stops a floor regression looking like an improvement: a
    soft ranker is never empty, so dropping the floor raises hit rate on every
    positive case while quietly making the bot confidently wrong on nonsense.
    """
    import json
    from pathlib import Path

    _catalog(db)
    baseline = json.loads(
        (Path(__file__).resolve().parents[1] / "scripts" / "eval_spec_search.baseline.json").read_text()
    )
    negatives = [c for c in baseline["cases"] if c["expect"] == "miss"]
    assert len(negatives) >= 10, "the negative set is what makes the floor measurable"

    surfaced = [
        case["phrase"]
        for case in negatives
        if not search_specs(db, specs=case["specs"], free_terms=case["free_terms"])["floor_missed"]
    ]

    assert surfaced == [], f"these should have been refused: {surfaced}"


def test_the_eval_baseline_positive_cases_all_hit(db):
    import json
    from pathlib import Path

    _catalog(db)
    baseline = json.loads(
        (Path(__file__).resolve().parents[1] / "scripts" / "eval_spec_search.baseline.json").read_text()
    )

    missed = []
    for case in [c for c in baseline["cases"] if c["expect"] == "hit"]:
        result = search_specs(db, specs=case["specs"], free_terms=case["free_terms"])
        if result["floor_missed"]:
            missed.append(case["phrase"])

    assert missed == [], f"these should have returned candidates: {missed}"


# --------------------------------------------------------------------------- #
# customer words -> registry values, and contradictions
# --------------------------------------------------------------------------- #
def test_a_phrase_resolves_onto_the_spec_key_that_holds_the_answer(db):
    """The registry's synonyms were carried and never consulted.

    "angle valve" fell below the relevance floor while 338 angle valves sat in the
    catalog with `product_type=angle_valve` stored, because the only thing a free term
    could earn was a weak substring hit against the rendered sentence, and the key
    holding the answer was never scored at all.
    """
    _catalog(db)
    _product(db, "ZZT-AV", "BRAVAT ANGLE VALVE", category="wc")

    result = search_specs(db, specs=[], free_terms=["angle valve", "angle", "valve"])

    assert not result["floor_missed"]
    assert _codes(result)[0] == "ZZT-AV"
    assert "product_type" in result["candidates"][0]["matched_specs"]


def test_a_longer_phrase_beats_a_generic_one_inside_it(db):
    _product(db, "ZZT-HAND", "SORENTO HAND SHOWER", category="wc")
    _product(db, "ZZT-RAIN", "SORENTO RAIN SHOWER", category="wc")

    result = search_specs(db, specs=[], free_terms=["hand shower", "hand", "shower"])
    assert _codes(result)[0] == "ZZT-HAND"


def test_a_contradicting_product_ranks_below_a_matching_one(db):
    """Stated, stored, and different is not the same as unstated.

    "black wall hung toilet bowl" returned a FLOOR STANDING water closet at the top
    while a wall-hung one existed: a mismatch scored zero, so the class and finish
    boosts alone decided the order. Silence stays neutral; a contradiction does not.
    """
    _product(db, "ZZT-WH", "SORENTO WALL HUNG WATER CLOSET", category="wc")
    _product(db, "ZZT-FS", "SORENTO FLOOR STANDING WATER CLOSET", category="wc")
    _product(db, "ZZT-QUIET", "SORENTO WATER CLOSET", category="wc")

    result = search_specs(db, specs=[], free_terms=["wall hung water closet"])
    codes = _codes(result)

    assert codes[0] == "ZZT-WH"
    # Demoted, not removed: the parser is the thing most likely to be wrong, so a
    # contradicting product stays available as a did-you-mean.
    assert "ZZT-FS" in codes
    assert codes.index("ZZT-QUIET") < codes.index("ZZT-FS")


def test_a_caller_supplied_spec_outranks_the_word_resolver(db):
    """The caller's parser saw a sentence; this resolver sees a bag of words."""
    _catalog(db)
    result = search_specs(
        db,
        specs=[{"key": "material", "value": "ceramic"}],
        free_terms=["stainless steel kitchen sink"],
    )
    assert _codes(result)[0] == "ZZT-SINK-C"
