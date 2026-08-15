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
from sqlalchemy import text as sql_text

import pytest

from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_search import (
    _states,
    _numeric_score,
    resolve_terms_to_specs,
    search_specs,
)
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS")
        wc = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-WC", category_name="SRT-WC")
        # Taps, showers and basins: the classes the first user report was actually
        # about. The ranker has to be exercised across all of them, not only sinks.
        ft = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-FT", category_name="SRT-FT")
        sh = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-SH", category_name="SRT-SH")
        wb = ProductCategory(id=str(uuid.uuid4()), category_code="SRT-WB", category_name="SRT-WB")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        # Brand is read off the product now, so the house-preference tests need real
        # brand rows rather than a category prefix.
        house = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
        rival = Brand(id=str(uuid.uuid4()), brand_code="ZZT-BRV", brand_name="BRAVAT")
        s.add_all([cat, wc, ft, sh, wb, uom, house, rival])
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        _REFS.update(
            {
                "cat": cat.id,
                "wc": wc.id,
                "ft": ft.id,
                "sh": sh.id,
                "wb": wb.id,
                "uom": uom.id,
                "house": house.id,
                "rival": rival.id,
            }
        )
        yield s


def _product(db, code, description, *, category="cat", discontinued=False, variant_of=None, brand=None):
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS[category],
        base_uom_id=_REFS["uom"],
        list_price=Decimal("1.00"),
        brand_id=_REFS[brand] if brand else None,
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
    """A small catalog with the shapes that matter, across every class in the baseline.

    Each row exists because a baseline case needs something real to hit. Wording is
    copied from live descriptions so the derivation is exercised the way it will be.
    """
    _product(db, "ZZT-SINK-A", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    _product(db, "ZZT-SINK-B", "SORENTO S/STEEL KITCHEN SINK (800X450X200MM)")
    _product(db, "ZZT-SINK-C", "CABANA CERAMIC KITCHEN SINK (1000X500X140MM)")
    _product(db, "ZZT-BASKET", "CABANA KITCHEN SINK TRIANGLE BASKET")
    _product(db, "ZZT-WC-A", "SORENTO CERAMIC WALL HUNG WATER CLOSET", category="wc")
    _product(db, "ZZT-SINK-1B", "SORENTO S/STEEL SINGLE BOWL SINK 860X500X200MM")
    _product(db, "ZZT-SINK-2B", "MOCHA KITCHEN SINK (DOUBLE BOWL)")
    _product(db, "ZZT-TAP-W", "SORENTO WALL MOUNTED KITCHEN TAP", category="ft")
    _product(db, "ZZT-TAP-P", "SORENTO PILLAR MOUNTED KITCHEN TAP", category="ft")
    _product(db, "ZZT-TAP-F", "SORENTO WALL MOUNTED FLEXIBLE HEAD KITCHEN TAP", category="ft")
    _product(db, "ZZT-AV", "BRAVAT ANGLE VALVE", category="ft")
    _product(db, "ZZT-SH-RAIN", "SORENTO RAIN SHOWER SET", category="sh")
    _product(db, "ZZT-WB-CT", "SORENTO COUNTER TOP WASH BASIN", category="wb")


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


# --------------------------------------------------------------------------- #
# `top_evidence`: HOW MUCH the floor was tested against, not just the verdict    #
# --------------------------------------------------------------------------- #
# The endpoint ships this as `spec_top_score` (tests/test_resolve_raw_text.py).
# These two are the unit-level pin underneath those: they say what the number IS,
# where the endpoint tests say what a caller may conclude from it.
def test_nothing_scored_at_all_reports_no_evidence(db):
    # A regression here (a sentinel default, a `None`, the catalogue's best score)
    # tells the renderer a greeting nearly found something. Nothing scored, so
    # there is nothing to be near, and the bot must not say there was.
    _catalog(db)

    results = search_specs(db, specs=[], free_terms=["flux capacitor"])

    assert results["candidates"] == []
    assert results["top_evidence"] == 0.0


def test_the_reported_evidence_is_the_best_one_in_the_shown_set(db):
    """`max` over the shown rows, measured on EVIDENCE and not on the total.

    `_evidence` is stripped from a candidate before the caller sees it, so the
    quantity is read here off the row carrying no house preference and no penalty:
    for that row the total IS its evidence. The house-preferred row outranks it on
    the total while holding LESS evidence, which is what makes the three readings
    distinguishable - `top[0]`'s evidence, the top total, and the real maximum are
    three different numbers here. Without that separation a refactor could hand the
    field the first row's score and every other test in this file would still pass.
    """
    _prefer(db, "brand", {"sorento": 8.0})
    _product(db, "ZZT-HOUSE", "SORENTO S/STEEL KITCHEN SINK", brand="house")
    _product(db, "ZZT-RIVAL", "BRAVAT S/STEEL KITCHEN SINK DOUBLE BOWL", brand="rival")

    results = search_specs(
        db,
        specs=[{"key": "class", "value": "Kitchen Sink"}],
        free_terms=["kitchen sink", "double bowl"],
    )
    scores = {c["product_code"]: c["score"] for c in results["candidates"]}
    house_evidence = scores["ZZT-HOUSE"] - 8.0

    assert _codes(results)[0] == "ZZT-HOUSE", "the preference still orders the list"
    assert results["top_evidence"] == scores["ZZT-RIVAL"]
    assert results["top_evidence"] > house_evidence, "the max over the set, not the first row's"
    assert results["top_evidence"] < scores["ZZT-HOUSE"], "evidence, never the top total"


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


def test_a_spoken_number_resolves_onto_a_numeric_key(db):
    """Customers say the number in words, and the synonym map is JSON.

    Without coercion "2" never equalled 2, and a comparison that cannot match also
    cannot be penalised: a SINGLE bowl sink scored identically to a double for "double
    bowl kitchen sink", which is the one distinction the customer cared about.
    """
    _product(db, "ZZT-1B", "CABANA SINGLE BOWL KITCHEN SINK")
    _product(db, "ZZT-2B", "CABANA DOUBLE BOWL KITCHEN SINK")

    result = search_specs(db, specs=[], free_terms=["double bowl kitchen sink"])
    codes = _codes(result)

    assert codes[0] == "ZZT-2B"
    assert "bowl_count" in result["candidates"][0]["matched_specs"]
    # Demoted for stating the other number, not removed.
    assert codes.index("ZZT-1B") > 0


# --------------------------------------------------------------------------- #
# #96 numeric tolerance is a property of the QUANTITY, not of the ranker
# --------------------------------------------------------------------------- #
def test_a_count_is_matched_exactly_not_within_a_millimetre_tolerance(db):
    """The defect this exists to stop: 1 bowl scoring a PERFECT match for 2.

    `_numeric_score` used one module-level `+/- 5` for every numeric key. That is a
    millimetre intuition, and against a COUNT it made 1 and 2 indistinguishable — a
    single-bowl sink ranked above real double-bowl sinks for "double bowl kitchen sink"
    while reporting `bowl_count` as a matched spec.
    """
    _product(db, "ZZT-1BOWL", "CABANA SINGLE BOWL KITCHEN SINK")
    _product(db, "ZZT-2BOWL", "CABANA DOUBLE BOWL KITCHEN SINK")

    result = search_specs(db, specs=[{"key": "bowl_count", "value": 2}], free_terms=[])
    top = result["candidates"][0]

    assert top["product_code"] == "ZZT-2BOWL"
    assert "bowl_count" in top["matched_specs"]

    # The single-bowl sink is absent entirely, and correctly so: this query states one
    # spec and no free terms, so contradicting it leaves the row with NO positive
    # evidence at all — the one condition that drops a candidate. Where the query
    # carries other signal it is demoted instead, which the next test asserts.
    assert "ZZT-1BOWL" not in _codes(result)


def test_a_millimetre_key_keeps_its_tolerance(db):
    """The mm behaviour must not regress while fixing counts: +/-5mm still reads exact."""
    _product(db, "ZZT-DIM", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")

    result = search_specs(db, specs=[{"key": "dim_length", "value": 998}], free_terms=[])

    assert "dim_length" in result["candidates"][0]["matched_specs"]


def test_a_numeric_contradiction_demotes_without_removing(db):
    """A number can contradict exactly as an enum can — and still not be deleted."""
    _product(db, "ZZT-1BOWL", "CABANA SINGLE BOWL KITCHEN SINK")
    _product(db, "ZZT-2BOWL", "CABANA DOUBLE BOWL KITCHEN SINK")

    result = search_specs(db, specs=[], free_terms=["double bowl kitchen sink"])
    codes = _codes(result)

    assert codes[0] == "ZZT-2BOWL"
    # Demoted, never removed: the parser is the thing most likely to be wrong.
    assert "ZZT-1BOWL" in codes


# --------------------------------------------------------------------------- #
# #97 quantities and units in the phrase
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "phrase,expected_mm",
    [
        ("S trap 200mm close couple wc", 200.0),
        ("s trap 20cm wc", 200.0),
        ('S trap 8" ( 200mm) Close Couple WC', 203.2),   # nearest word wins: the 8"
        ("s trap 8 inch wc", 203.2),
    ],
)
def test_a_quantity_is_bound_to_the_key_its_own_word_names(db, phrase, expected_mm):
    """Numbers in a phrase were dropped entirely — resolution scanned synonyms only."""
    resolved = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, [phrase])}

    assert resolved.get("trap_length") == pytest.approx(expected_mm)
    # The enum still resolves alongside it; they are different keys.
    assert resolved.get("trap_type") == "s_trap"


def test_an_inch_query_reaches_the_millimetre_product(db):
    '''8" is 203.2mm and the catalog calls that size 200mm.

    This only lands because the mm tolerance (#96) absorbs the 3.2mm rounding, which is
    why the two tickets had to ship together.
    '''
    _product(db, "ZZT-T200", "CABANA CLOSE COUPLED WC (S-TRAP 200MM)", category="wc")
    _product(db, "ZZT-T250", "CABANA CLOSE COUPLED WC (S-TRAP 250MM)", category="wc")

    result = search_specs(db, specs=[], free_terms=['S trap 8" close couple wc'])

    assert _codes(result)[0] == "ZZT-T200"


def test_a_word_stated_value_beats_a_number_sitting_nearby(db):
    """"double bowl ... 1.2mm" must not let the 1.2 land on bowl_count."""
    resolved = {e["key"]: e["value"] for e in
                resolve_terms_to_specs(db, ["double bowl kitchen sink with thickness 1.2mm"])}

    assert resolved["bowl_count"] == 2
    assert resolved["thickness"] == pytest.approx(1.2)


def test_an_unqualified_number_is_not_guessed_onto_a_key(db):
    """No key's word is near it, so it binds to nothing rather than to the wrong thing.

    Guessing "the obvious dimension" is how a wrong product reaches a customer.
    """
    resolved = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["1000mm kitchen sink"])}

    assert "dim_length" not in resolved
    assert resolved == {}


def test_digits_inside_a_product_code_are_not_read_as_a_quantity(db):
    resolved = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["CKS1050 trap"])}

    assert "trap_length" not in resolved


# --------------------------------------------------------------------------- #
# tuning: a house preference, and a discontinued deboost (#99)
# --------------------------------------------------------------------------- #
def _set_policy(db, key: str, value: float) -> None:
    from app.models.product_spec import ProductSpecSearchPolicy
    from app.services.product_spec_registry import seed_search_policy

    seed_search_policy(db)
    db.query(ProductSpecSearchPolicy).filter_by(policy_key=key).one().value = value
    db.flush()


def _prefer(db, spec_key: str, weights: dict) -> None:
    from app.models.product_spec import ProductSpecRegistry

    db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).one().value_weights = weights
    db.flush()


def test_a_discontinued_product_ranks_below_an_otherwise_identical_live_one(db):
    _product(db, "ZZT-LIVE", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")
    _product(db, "ZZT-DEAD", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)", discontinued=True)

    codes = _codes(search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}]))

    assert codes.index("ZZT-LIVE") < codes.index("ZZT-DEAD")


def test_a_discontinued_product_is_still_offered(db):
    """4,969 discontinued products are still active and still sellable.

    The deboost ranks them second, it does not hide them - otherwise a customer asking
    for the only thing that matches gets told nothing matches.
    """
    _product(db, "ZZT-DEAD", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)", discontinued=True)

    assert "ZZT-DEAD" in _codes(search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}]))


def test_turning_the_discontinued_penalty_off_restores_the_old_order(db):
    # Proves the number is really the setting and not a decoration next to a constant.
    _product(db, "ZZT-DEAD", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)", discontinued=True)
    _product(db, "ZZT-LIVE", "SORENTO S/STEEL KITCHEN SINK (1000X500X220MM)")

    _set_policy(db, "discontinued_penalty", 0)
    scores = {
        r["product_code"]: r["score"]
        for r in search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}])["candidates"]
    }

    assert scores["ZZT-DEAD"] == scores["ZZT-LIVE"]


def _scores(db, specs) -> dict:
    return {r["product_code"]: r["score"] for r in search_specs(db, specs=specs)["candidates"]}


def test_a_house_brand_preference_floats_that_brand(db):
    # Asserted on the SCORE, not on list order: with the two products otherwise equal
    # the order is a tie either way, so an order assertion passes whether or not the
    # preference is applied - a test that cannot fail.
    _product(db, "ZZT-RIVAL", "BRAVAT S/STEEL KITCHEN SINK", brand="rival")
    _product(db, "ZZT-HOUSE", "SORENTO S/STEEL KITCHEN SINK", brand="house")
    class_only = [{"key": "class", "value": "Kitchen Sink"}]

    before = _scores(db, class_only)
    assert before["ZZT-HOUSE"] == before["ZZT-RIVAL"], "equal until a preference is set"

    _prefer(db, "brand", {"SORENTO": 1.5})
    after = _scores(db, class_only)

    assert after["ZZT-HOUSE"] == before["ZZT-HOUSE"] + 1.5
    assert after["ZZT-RIVAL"] == before["ZZT-RIVAL"]
    assert _codes(search_specs(db, specs=class_only))[0] == "ZZT-HOUSE"


def test_a_house_preference_never_overrides_the_brand_the_customer_asked_for(db):
    """Someone who asks for Bravat is asking for Bravat.

    A preference that outranked the customer's own words would be a bug wearing a
    boost's clothes, so it is only applied to keys they did not state.
    """
    _product(db, "ZZT-HOUSE", "SORENTO S/STEEL KITCHEN SINK", brand="house")
    _product(db, "ZZT-RIVAL", "BRAVAT S/STEEL KITCHEN SINK", brand="rival")
    asked_for_bravat = [
        {"key": "class", "value": "Kitchen Sink"},
        {"key": "brand", "value": "BRAVAT"},
    ]

    before = _scores(db, asked_for_bravat)
    _prefer(db, "brand", {"SORENTO": 1.5})
    after = _scores(db, asked_for_bravat)

    assert after == before, "the customer named the brand, so no house preference applies"
    assert _codes(search_specs(db, specs=asked_for_bravat))[0] == "ZZT-RIVAL"


def test_no_preference_configured_changes_nothing(db):
    # The mechanism ships inert: an empty value_weights must score exactly as before.
    _product(db, "ZZT-HOUSE", "SORENTO S/STEEL KITCHEN SINK", brand="house")
    _product(db, "ZZT-RIVAL", "BRAVAT S/STEEL KITCHEN SINK", brand="rival")

    scores = {
        r["product_code"]: r["score"]
        for r in search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}])["candidates"]
    }

    assert scores["ZZT-HOUSE"] == scores["ZZT-RIVAL"]


# --------------------------------------------------------------------------- #
# a preference can reorder answers; it cannot BE one
# --------------------------------------------------------------------------- #
def test_a_phrase_that_matches_nothing_misses_the_floor_despite_a_house_preference(db):
    """"hi" must return nothing, not five Sorento products.

    The house preference is added to every product carrying the preferred value,
    whatever the customer said. Counted as evidence it sat permanently above the
    relevance floor, so the floor could never be missed and a greeting came back as a
    shortlist of arbitrary products presented as answers.
    """
    _prefer(db, "brand", {"sorento": 8.0})
    _product(db, "ZZT-HOUSE", "SORENTO S/STEEL KITCHEN SINK", brand="house")

    result = search_specs(db, specs=[], free_terms=["flux", "capacitor"])

    assert result["floor_missed"] is True
    assert result["candidates"] == []


def test_the_preference_still_reorders_answers_the_customer_did_find(db):
    # The other half of the same rule: excluded from the floor, still applied to the
    # score. Without this the fix above would read as "the preference was removed".
    _prefer(db, "brand", {"sorento": 8.0})
    _product(db, "ZZT-HOUSE", "SORENTO S/STEEL KITCHEN SINK", brand="house")
    _product(db, "ZZT-RIVAL", "BRAVAT S/STEEL KITCHEN SINK", brand="rival")

    result = search_specs(db, specs=[{"key": "class", "value": "Kitchen Sink"}])
    scores = {r["product_code"]: r["score"] for r in result["candidates"]}

    assert result["floor_missed"] is False
    assert scores["ZZT-HOUSE"] == scores["ZZT-RIVAL"] + 8.0



# --------------------------------------------------------------------------- #
# say what was asked for and not delivered (#105)
# --------------------------------------------------------------------------- #
def test_a_brand_that_has_no_match_is_reported_as_unmet(db):
    """"cabana free standing bathtub" offers Sorento ones — and must say so.

    Every spec is a boost, never a filter, so offering the next best thing is correct.
    Offering it SILENTLY is what reads as a broken search: the customer said Cabana,
    got Sorento, and nothing in the answer acknowledged the difference.
    """
    _product(db, "ZZT-BT-SRT", "SORENTO FREE STANDING BATHTUB", brand="house", category="sh")

    result = search_specs(
        db,
        specs=[
            {"key": "class", "value": "Bathtub and Jacuzzi"},
            {"key": "brand", "value": "CABANA"},
        ],
        free_terms=["bathtub"],
    )

    assert [u["key"] for u in result["unmet"]] == ["brand"]
    assert result["unmet"][0]["value"] == "CABANA"


def test_nothing_is_unmet_when_every_asked_spec_matches(db):
    _product(db, "ZZT-BT-CB", "CABANA FREE STANDING BATHTUB", brand="rival", category="sh")

    result = search_specs(
        db, specs=[{"key": "brand", "value": "BRAVAT"}], free_terms=["bathtub"]
    )

    assert result["unmet"] == [], "the brand asked for is the brand offered"


# --------------------------------------------------------------------------- #
# a class minted by a rule must be searchable by its own name (#107)
# --------------------------------------------------------------------------- #
def _seat_cover(db, code: str):
    """A product whose class came from a RULE, not from any category.

    Written through the rule the user would write in the UI, so the test exercises the
    real path rather than hand-stuffing a value into the JSON.
    """
    from app.models.product_spec import ProductSpecRegistry
    from app.services.product_spec_derivation import derive_for_code

    row = db.query(ProductSpecRegistry).filter_by(spec_key="class").one()
    row.derivation_rules = [
        {"match": "contains", "pattern": "SEAT COVER", "value": "Seat Cover"}
    ]
    db.flush()
    product = _product(db, code, "SORENTO WC 8065 SEAT COVER", category="wc")
    derive_for_code(db, code)
    return product


def test_a_class_that_no_category_declares_is_still_resolvable_by_its_words(db):
    """"seat cover" found nothing while 172 products carried `Seat Cover`.

    Class comes from configured derivation rules now, so a rule can mint a class the
    categories have never heard of. The word could only ever be looked up against
    `product_categories`, so the strongest signal in the ranker was unreachable for
    exactly the classes someone had just gone to the trouble of defining.
    """
    from app.services.product_class_signal import resolve_classes_for_term

    _seat_cover(db, "ZZT-SC-1")

    assert resolve_classes_for_term(db, "seat cover") == ["Seat Cover"]


def test_the_class_boost_reaches_a_rule_minted_class(db):
    # The half that matters: resolvable AND scored, not merely resolvable.
    _seat_cover(db, "ZZT-SC-2")
    _product(db, "ZZT-SINK-2", "SORENTO S/STEEL KITCHEN SINK")

    result = search_specs(db, specs=[], free_terms=["seat", "cover", "seat cover"])

    assert result["floor_missed"] is False
    assert _codes(result)[0] == "ZZT-SC-2"


# --------------------------------------------------------------------------- #
# a refusal removes, it does not demote
# --------------------------------------------------------------------------- #
def test_a_refused_value_removes_the_product_entirely(db):
    """"golden yellow wash basin not glass" returned a glass basin at rank 5.

    A penalty cannot fix that: any weight small enough to keep the ranking sane still
    leaves the refused product on the page, and the customer said no. Removal is the
    only answer that matches what was asked.
    """
    _catalog(db)
    _product(db, "ZZT-WB-GLASS", "SORENTO GLASS WASH BASIN", category="wb")

    without = search_specs(db, free_terms=["wash basin"])
    assert "ZZT-WB-GLASS" in _codes(without), "the glass basin is findable to begin with"

    refused = search_specs(
        db,
        free_terms=["wash basin"],
        exclusions=[{"key": "material", "value": "glass"}],
    )

    assert "ZZT-WB-GLASS" not in _codes(refused)
    assert "ZZT-WB-CT" in _codes(refused), "only the refused product goes"


def test_a_refusal_does_not_remove_products_whose_value_is_unknown(db):
    """Absence of a word is not evidence of the thing.

    Most of the catalog has no material derived at all. Excluding on "not known to be
    glass" would empty the results for any refusal, which is the opposite of helpful.
    """
    _catalog(db)

    refused = search_specs(
        db,
        free_terms=["wash basin"],
        exclusions=[{"key": "material", "value": "glass"}],
    )

    assert "ZZT-WB-CT" in _codes(refused)


def test_the_word_resolver_cannot_reinstate_a_refused_spec(db):
    """The phrase still contains the word "glass", and the word-level resolver reads it.

    Without withholding refused values from that resolver, the exclusion is understood
    and then undone one line later — the product is filtered out but the spec comes back
    as a positive boost on everything else made of glass.
    """
    _catalog(db)
    _product(db, "ZZT-WB-GLASS2", "SORENTO GLASS WASH BASIN 500MM", category="wb")

    result = search_specs(
        db,
        free_terms=["glass wash basin"],
        exclusions=[{"key": "material", "value": "glass"}],
    )

    assert "ZZT-WB-GLASS2" not in _codes(result)


# --------------------------------------------------------------------------- #
# the flyer is the better source
# --------------------------------------------------------------------------- #
def test_the_flyer_source_boost_lifts_only_flyer_sourced_specs(db):
    """The flyer states things the product master does not.

    14 flyer cards say FRAMELESS where 2 descriptions do; 9 say MASSAGE JET where none
    do, so a flyer-stated spec is better evidence than a word in a description.

    Each product is compared against ITSELF at two settings rather than against another
    product. Two products are never equal in other ways - the first version of this test
    compared a pair whose scores differed by an unrelated 2.0 and would have passed for
    the wrong reason.
    """
    from app.models.product_spec import ProductSpecifications, ProductSpecSearchPolicy
    from app.services.product_spec_registry import seed_search_policy

    # The blank schema has no policy rows, so an UPDATE against it matches nothing and
    # every read falls back to the seeded default - the first version of this test moved
    # a number that was never read and passed its own sabotage.
    seed_search_policy(db)

    _catalog(db)
    from_flyer = _product(db, "ZZT-MIRROR-F", "SORENTO MIRROR", category="cat")
    from_text = _product(db, "ZZT-MIRROR-D", "SORENTO MIRROR", category="cat")
    for product, source in ((from_flyer, "flyer"), (from_text, "derived")):
        spec = db.query(ProductSpecifications).filter_by(product_id=product.id).first()
        spec.values = {**(spec.values or {}), "is_frameless": {"value": True}}
        spec.provenance = {**(spec.provenance or {}), "is_frameless": {"source": source}}
    db.flush()

    def score_for(code: str) -> float:
        result = search_specs(db, specs=[{"key": "is_frameless", "value": True}], free_terms=[])
        return next(c["score"] for c in result["candidates"] if c["product_code"] == code)

    def set_boost(value: float) -> None:
        db.query(ProductSpecSearchPolicy).filter_by(policy_key="flyer_source_boost").update(
            {"value": value}
        )
        db.flush()

    set_boost(1.0)
    flyer_at_one, text_at_one = score_for("ZZT-MIRROR-F"), score_for("ZZT-MIRROR-D")
    set_boost(3.0)
    flyer_at_three, text_at_three = score_for("ZZT-MIRROR-F"), score_for("ZZT-MIRROR-D")

    assert flyer_at_three > flyer_at_one, "the flyer-sourced spec is worth more"
    assert text_at_three == text_at_one, "a description-sourced spec is untouched by it"


# --------------------------------------------------------------------------- #
# "above 900mm" is a limit, not a target
# --------------------------------------------------------------------------- #
def test_an_at_least_threshold_keeps_only_products_that_clear_it(db):
    """Scored as approximate equality, a limit selects the wrong products.

    "free standing basin above 900mm" put two 850mm basins above the one 960mm basin,
    because 850 sits nearer to 900 than 960 does. Nearness is the wrong question: a
    basin that does not clear 900 does not nearly clear it.
    """
    _catalog(db)
    _product(db, "ZZT-WB-TALL", "SORENTO FREE STANDING WASH BASIN (460X480X960MM)", category="wb")
    _product(db, "ZZT-WB-SHORT", "SORENTO FREE STANDING WASH BASIN (480X480X850MM)", category="wb")

    result = search_specs(
        db,
        specs=[{"key": "dim_height", "value": 900, "op": "at_least"}],
        free_terms=["free standing wash basin"],
    )
    codes = _codes(result)

    assert "ZZT-WB-TALL" in codes
    assert "ZZT-WB-SHORT" not in codes, "850mm does not answer 'above 900mm'"


def test_an_at_most_threshold_is_the_mirror_of_it(db):
    _catalog(db)
    _product(db, "ZZT-WB-NARROW", "SORENTO WASH BASIN (410X410X150MM)", category="wb")
    _product(db, "ZZT-WB-WIDE", "SORENTO WASH BASIN (820X600X830MM)", category="wb")

    codes = _codes(
        search_specs(
            db,
            specs=[{"key": "dim_width", "value": 500, "op": "at_most"}],
            free_terms=["wash basin"],
        )
    )

    assert "ZZT-WB-NARROW" in codes
    assert "ZZT-WB-WIDE" not in codes


def test_a_threshold_does_not_remove_a_product_whose_size_is_unknown(db):
    """Absence of a measurement is not failure to meet it.

    Most of the catalog has no derived height. Excluding on "not known to clear 900"
    would empty the result for any threshold, which is the opposite of helpful.
    """
    _catalog(db)
    sizeless = _product(db, "ZZT-WB-NOSIZE", "SORENTO WASH BASIN", category="wb")
    assert sizeless is not None

    codes = _codes(
        search_specs(
            db,
            specs=[{"key": "dim_height", "value": 900, "op": "at_least"}],
            free_terms=["wash basin"],
        )
    )

    assert "ZZT-WB-NOSIZE" in codes


def test_a_bare_number_still_means_about_that_size(db):
    # Only an explicit limit filters. "600mm wash basin" is a target, and a 590mm basin
    # is a perfectly good answer to it.
    _catalog(db)
    _product(db, "ZZT-WB-590", "SORENTO WASH BASIN (900X590X500MM)", category="wb")

    codes = _codes(
        search_specs(db, specs=[{"key": "dim_width", "value": 600}], free_terms=["wash basin"])
    )

    assert "ZZT-WB-590" in codes


def test_the_nearer_of_two_matches_ranks_first():
    """Both answer the question; the one they actually named comes first.

    SRTSCBD701 is 500mm and SRTSCBD702 is 495mm, and the tolerance covers 5mm. Both
    scored a flat 1.0, so the order between them was arbitrary - and a customer asking
    for 495 could be shown 500 instead, with the product they named nowhere.
    """
    exact = _numeric_score(495.0, 495.0, tolerance=10.0, decay=50.0)
    near = _numeric_score(495.0, 500.0, tolerance=10.0, decay=50.0)

    assert exact > near, "an exact size must outrank a merely tolerable one"
    # ...but only just: closeness orders equals, it does not outweigh a whole spec.
    assert near > 0.9, "a size inside the tolerance still fully matches"


def test_a_two_tone_product_answers_for_either_finish():
    """SRTWT9605-RG is "Rose Gold + Matt Black". Both are true of it.

    A single scalar had to discard one, and WHICH one depended on rule order - so
    searching the flyer's own words for "2 ways shower set rose gold" returned every
    rose gold set except the one on the card.
    """
    assert _states(["rose_gold", "black"], "rose_gold")
    assert _states(["rose_gold", "black"], "black")
    assert not _states(["rose_gold", "black"], "chrome")
    # A scalar keeps behaving exactly as it did.
    assert _states("chrome", "chrome")
    assert not _states("chrome", "black")


def test_a_labelled_size_is_read_as_the_dimension_it_names(db):
    """"L750 x W165 x H247mm" is how the flyer prints a size, and how a salesperson
    quoting a card says it. The letter states which dimension it is, so reading it is
    not the guess the binder deliberately refuses to make - it is the statement.

    188 flyer cards use this form and none of them reached a dimension key.
    """
    seed_spec_registry(db)
    resolved = {
        e["key"]: e["value"]
        for e in resolve_terms_to_specs(db, ["Grab Bar. L750 x W165 x H247mm. ABS"])
    }

    assert resolved.get("dim_length") == 750.0
    assert resolved.get("dim_width") == 165.0
    assert resolved.get("dim_height") == 247.0


def test_a_millimetre_never_becomes_a_count(db):
    """"grab bar 750mm" was a search for a bar with 750 bars.

    `bar_count` has no unit, so it counts things, and "bar" sat next to the number. The
    false bind did not merely add noise - a count mismatch PENALISES, so every real grab
    bar was pushed down for not having 750 of them.
    """
    seed_spec_registry(db)
    resolved = {
        e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["grab bar 750mm"])
    }

    assert "bar_count" not in resolved
    assert resolved.get("product_type") == "grab_bar"

    # A real count still binds.
    counted = {
        e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["towel bar 2 bars"])
    }
    assert counted.get("bar_count") == 2.0


def test_a_number_already_spoken_for_is_not_also_a_measurement(db):
    """"S/Steel 304" states a grade. 304 is not then free to be a length.

    Found while fixing the case above it: once "Length 23" was rejected as too small to
    be millimetres, 304 was the next number near the word "length", so the steel grade
    silently became the towel bar's length.
    """
    seed_spec_registry(db)
    resolved = {
        e["key"]: e["value"]
        for e in resolve_terms_to_specs(db, ["Towel Bar. Length 23 . S/Steel 304. Matt Black"])
    }

    assert resolved.get("steel_grade") == "304"
    assert "dim_length" not in resolved, "the grade was read as a measurement"


def test_a_size_with_no_unit_is_not_assumed_to_be_millimetres(db):
    """The flyer prints towel bars as "Length 23", meaning inches.

    Read as millimetres it asks for a 23mm towel bar, which penalises every real one.
    Limited to the three envelope dimensions on purpose: an 8mm thickness is ordinary.
    """
    seed_spec_registry(db)

    bare = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["towel bar length 23"])}
    assert "dim_length" not in bare

    stated = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["basin length 500mm"])}
    assert stated.get("dim_length") == 500.0

    thin = {e["key"]: e["value"] for e in resolve_terms_to_specs(db, ["thickness 8"])}
    assert thin.get("thickness") == 8.0, "a small measurement that is not an envelope is fine"
