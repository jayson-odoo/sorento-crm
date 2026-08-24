"""`app/services/media_extract/schema.py` - the strict output contract and its
tolerant parse.

Contract:
 - UAC S4-01 (entity shape verbatim, no snapping), S4-02 (unhinted values ride
    `attributes[]`), S4-03 (conflicts are first class and force
    `confident: false`), S4-10 (the cap, stated not silent), S4-12 (this whole
    file - prompt/schema behaviour tested against recorded provider JSON, no
    provider call).
 - PLAN section 13 records four defects the first corpus run exposed; three of
    them are regression-guarded here by name:
      defect 1 - conflict confidence leaking across lines by matching on `kind`
        alone (fixed by scoping on `entity_raw`);
      defect 4 - an entity reappearing as a spurious attribute (fixed by
        dropping an attribute whose `raw` duplicates an emitted entity).
 - PLAN Appendix A amendment 2 - the cap applies to `entities` and
    `attributes` SEPARATELY, including when the overflow in `attributes` comes
    entirely from entities the parser rescued out of `entities` (schema.py
    module docstring rule 1 / rule 4).

Pure functions, no DB, no provider call - every payload here is a plain dict
standing in for "what the vision model returned", exactly as S4-12 requires.
"""
from __future__ import annotations

import pytest

from app.services.media_extract.schema import (
    MediaExtractionParseError,
    norm_code,
    parse_extraction,
    parse_provider_json,
)


# --------------------------------------------------------------------------- #
# Conflict scoping (S4-03) - the highest-value case                           #
# --------------------------------------------------------------------------- #


def _four_line_payload(conflict_entity_raw):
    """Four product lines, each with its own quantity attribute, and one
    conflict. Shared by the scoping tests below so only the conflict's
    `entity_raw` varies."""
    return {
        "entities": [
            {"raw": "SRTA", "hint": "product"},
            {"raw": "SRTB", "hint": "product"},
            {"raw": "SRTC", "hint": "product"},
            {"raw": "SRTD", "hint": "product"},
        ],
        "attributes": [
            {"kind": "quantity", "raw": "6", "entity_raw": "SRTA"},
            {"kind": "quantity", "raw": "6", "entity_raw": "SRTB"},
            {"kind": "quantity", "raw": "6", "entity_raw": "SRTC"},
            {"kind": "quantity", "raw": "4", "entity_raw": "SRTD"},
        ],
        "conflicts": [
            {
                "field": "quantity",
                "entity_raw": conflict_entity_raw,
                "values": [
                    {"value": "6", "source": "printed"},
                    {"value": "4", "source": "handwritten"},
                ],
                "note": "amended",
            }
        ],
    }


def test_conflict_naming_one_line_only_unconfidents_that_lines_quantity():
    """S4-03 / PLAN section 13 defect 1 regression guard: four `quantity`
    attributes on four different `entity_raw` lines, one conflict naming the
    fourth - only the named line's attribute (and the entity it belongs to)
    loses confidence. The other three, which share the SAME `kind`, must stay
    confident: a flag that fires on correct lines is worth nothing."""
    extraction = parse_extraction(_four_line_payload("SRTD"), max_entities=10)

    by_line = {a.entity_raw: a for a in extraction.attributes}
    assert by_line["SRTA"].confident is True
    assert by_line["SRTB"].confident is True
    assert by_line["SRTC"].confident is True
    assert by_line["SRTD"].confident is False

    by_raw = {e.raw: e for e in extraction.entities}
    assert by_raw["SRTA"].confident is True
    assert by_raw["SRTB"].confident is True
    assert by_raw["SRTC"].confident is True
    assert by_raw["SRTD"].confident is False, (
        "the entity the conflict names by its own raw must also be flagged, "
        "not only the attribute on its line"
    )


def test_conflict_with_null_entity_raw_applies_document_wide():
    """S4-03: a conflict naming no line is the document-wide case and touches
    every attribute of the conflicted kind, unlike the scoped case above."""
    extraction = parse_extraction(_four_line_payload(None), max_entities=10)

    assert all(not a.confident for a in extraction.attributes)


@pytest.mark.parametrize(
    "spelling", ["srt-d", "SRT D", "srtd", "SRT-D", "  SrtD  "]
)
def test_conflict_entity_raw_matching_is_dash_and_case_insensitive(spelling):
    """S4-03: the conflict's `entity_raw` is matched against a line the same
    way every other code comparison in this repo works - casefolded, dashes
    and spaces stripped (`norm_code`) - so a model that writes the line
    reference with different punctuation than the entity's own `raw` still
    scopes correctly."""
    extraction = parse_extraction(_four_line_payload(spelling), max_entities=10)

    by_line = {a.entity_raw: a for a in extraction.attributes}
    assert by_line["SRTD"].confident is False
    assert by_line["SRTA"].confident is True


def test_document_wide_conflict_unconfidents_the_entity_it_disputes():
    """S4-03, the RMA-photo case: printed and handwritten product codes disagree,
    the model reports the conflict with no `entity_raw` (it cannot say which
    line - the line IS the dispute), and the code it emitted as an entity must
    not still ship `confident: true`. The disputed `values` are the handle."""
    extraction = parse_extraction(
        {
            "entities": [
                {"raw": "SRT-KS-6647", "hint": "product"},
                {"raw": "SRTBF31610", "hint": "product"},
            ],
            "attributes": [{"kind": "quantity", "raw": "3", "entity_raw": "SRTBF31610"}],
            "conflicts": [
                {
                    "field": "product code",
                    "entity_raw": None,
                    "values": [
                        {"value": "SRTKS6647", "source": "printed"},
                        {"value": "SRTKS6641", "source": "handwritten"},
                    ],
                }
            ],
        },
        max_entities=10,
    )

    by_raw = {entity.raw: entity for entity in extraction.entities}
    assert by_raw["SRT-KS-6647"].confident is False
    # The other product is not in dispute and keeps its confidence: a flag
    # that fires on correct lines is a flag nobody can act on.
    assert by_raw["SRTBF31610"].confident is True
    assert extraction.attributes[0].confident is True


def test_a_disputed_value_carried_as_an_attribute_is_unconfident_too():
    extraction = parse_extraction(
        {
            "entities": [{"raw": "SRTBF31610", "hint": "product"}],
            "attributes": [
                {"kind": "batch_number", "raw": "YG2539", "entity_raw": "SRTBF31610"},
                {"kind": "batch_number", "raw": "YG2540", "entity_raw": "SRTBF31610"},
            ],
            "conflicts": [
                {
                    "field": "lot",
                    "entity_raw": None,
                    "values": [{"value": "YG-2539", "source": "printed"}],
                }
            ],
        },
        max_entities=10,
    )

    by_raw = {a.raw: a for a in extraction.attributes}
    assert by_raw["YG2539"].confident is False
    assert by_raw["YG2540"].confident is True


def test_norm_code_strips_dashes_spaces_and_case():
    assert norm_code("SRT-D") == norm_code("srt d") == norm_code("  SrtD ") == "srtd"


# --------------------------------------------------------------------------- #
# Entity-duplicate attributes dropped (PLAN section 13, defect 4)             #
# --------------------------------------------------------------------------- #


def test_attribute_duplicating_an_emitted_entity_is_dropped_exact_and_variants():
    """A product code repeated inside a description line came back a second
    time as `batch_number` on the corpus run (PLAN 13.4). Exact, case-differing,
    space-differing and dash-differing spellings of an already-emitted entity
    are all dropped; a genuinely different value survives; the entity itself
    is never touched."""
    payload = {
        "entities": [{"raw": "SRTKS6647", "hint": "product"}],
        "attributes": [
            {"kind": "batch_number", "raw": "SRTKS6647"},  # exact
            {"kind": "batch_number", "raw": "srtks6647"},  # case-differing
            {"kind": "batch_number", "raw": "SRT KS6647"},  # space-differing
            {"kind": "batch_number", "raw": "SRT-KS6647"},  # dash-differing
            {"kind": "batch_number", "raw": "YG2539"},  # not a duplicate
        ],
    }
    extraction = parse_extraction(payload, max_entities=10)

    assert [a.raw for a in extraction.attributes] == ["YG2539"]
    assert [e.raw for e in extraction.entities] == ["SRTKS6647"], (
        "the entity is kept - it is the correct home - only the duplicate "
        "attribute is dropped"
    )


# --------------------------------------------------------------------------- #
# Entity/attribute split, both directions (S4-01, S4-02)                      #
# --------------------------------------------------------------------------- #


def test_entity_kinded_as_an_attribute_is_rescued_not_dropped():
    """S4-02: an entity whose `hint` is actually an attribute kind (the model
    ignoring 'never put an attribute in entities under an approximate hint')
    is MOVED into `attributes[]`, not dropped - the value was read correctly,
    only its home was wrong."""
    payload = {
        "entities": [{"raw": "YG2539", "hint": "batch_number", "confident": True}]
    }
    extraction = parse_extraction(payload, max_entities=10)

    assert extraction.entities == []
    assert len(extraction.attributes) == 1
    assert extraction.attributes[0].kind == "batch_number"
    assert extraction.attributes[0].raw == "YG2539"
    assert extraction.attributes[0].entity_raw is None, (
        "a rescued entity carries no line of its own - it must not be "
        "invented onto a line it may not belong to"
    )


def test_entity_with_an_unusable_hint_is_dropped_not_forced_through():
    """S4-01: `hint` may only carry one of the 14 reformulator values.
    Anything neither an accepted hint nor a known attribute kind is dropped -
    `resolve-entity` would reject it, so passing it on fails downstream
    instead of degrading."""
    payload = {"entities": [{"raw": "FOO", "hint": "totally_unknown"}]}
    extraction = parse_extraction(payload, max_entities=10)

    assert extraction.entities == []
    assert extraction.attributes == []


def test_unknown_attribute_kind_is_dropped():
    payload = {"attributes": [{"kind": "unknown_kind", "raw": "ZZZ"}]}
    extraction = parse_extraction(payload, max_entities=10)

    assert extraction.attributes == []


def test_document_number_and_document_date_attribute_kinds_parse():
    """PLAN section 13, defects 2 and 3: these two kinds did not exist before
    the first corpus run, so a return-authorisation number and a bare date had
    nowhere to go and were silently dropped."""
    payload = {
        "attributes": [
            {
                "kind": "document_number",
                "raw": "RMA-SRT2608-0104",
                "entity_raw": None,
            },
            {"kind": "document_date", "raw": "11/08/2026", "entity_raw": None},
        ]
    }
    extraction = parse_extraction(payload, max_entities=10)

    by_kind = {a.kind: a.raw for a in extraction.attributes}
    assert by_kind["document_number"] == "RMA-SRT2608-0104"
    assert by_kind["document_date"] == "11/08/2026"


def test_entity_raw_is_transcribed_exactly_no_snapping_or_matching():
    """S4-01: `raw` is the literal string as it appears - no product-code
    matching or snapping. `resolve-entity` adjudicates, not this parser."""
    payload = {
        "entities": [
            {"raw": " srt-ks6647 (odd casing) ", "hint": "product", "confident": True}
        ]
    }
    extraction = parse_extraction(payload, max_entities=10)

    assert extraction.entities[0].raw == "srt-ks6647 (odd casing)"


# --------------------------------------------------------------------------- #
# Caps (S4-10)                                                                #
# --------------------------------------------------------------------------- #


def test_entities_are_capped_and_truncated_is_set():
    payload = {"entities": [{"raw": f"P{i}", "hint": "product"} for i in range(5)]}
    extraction = parse_extraction(payload, max_entities=2)

    assert [e.raw for e in extraction.entities] == ["P0", "P1"]
    assert extraction.truncated is True


def test_attributes_are_capped_separately_from_entities():
    """PLAN Appendix A amendment 2: the cap was originally pinned to `entities`
    only, so an unbounded `attributes[]` (a price list has a size and a
    quantity on every row) could slip through uncapped."""
    payload = {
        "entities": [{"raw": "P0", "hint": "product"}],  # well under the cap
        "attributes": [
            {"kind": "quantity", "raw": str(i), "entity_raw": None} for i in range(5)
        ],
    }
    extraction = parse_extraction(payload, max_entities=2)

    assert len(extraction.entities) == 1
    assert len(extraction.attributes) == 2
    assert extraction.truncated is True


def test_truncated_is_forced_true_even_when_the_model_did_not_say_so():
    payload = {
        "entities": [{"raw": f"P{i}", "hint": "product"} for i in range(3)],
        "truncated": False,
    }
    extraction = parse_extraction(payload, max_entities=1)

    assert extraction.truncated is True, "say so rather than truncate silently"


def test_cap_applies_even_when_the_overflow_is_entirely_rescued_entities():
    """The rescued-attribute path (S4-02) must still respect the attribute
    cap: three carton fields sent as mis-hinted entities all land in
    `attributes[]`, and that list is capped exactly like a model-supplied
    one."""
    payload = {
        "entities": [{"raw": f"B{i}", "hint": "batch_number"} for i in range(3)],
        "attributes": [],
    }
    extraction = parse_extraction(payload, max_entities=2)

    assert len(extraction.attributes) == 2
    assert extraction.truncated is True


# --------------------------------------------------------------------------- #
# Tolerant parsing (S4-12)                                                    #
# --------------------------------------------------------------------------- #


def test_parse_provider_json_accepts_a_json_fenced_block():
    assert parse_provider_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_provider_json_accepts_a_bare_fenced_block():
    assert parse_provider_json('```\n{"a": 1}\n```') == {"a": 1}


def test_parse_provider_json_accepts_trailing_prose():
    content = 'Here is the result: {"a": 1} Thanks!'
    assert parse_provider_json(content) == {"a": 1}


def test_parse_provider_json_raises_on_non_object_json():
    with pytest.raises(MediaExtractionParseError):
        parse_provider_json("[1, 2, 3]")


def test_parse_provider_json_raises_on_a_bare_json_string():
    with pytest.raises(MediaExtractionParseError):
        parse_provider_json('"just a string"')


def test_parse_provider_json_raises_on_empty_content():
    with pytest.raises(MediaExtractionParseError):
        parse_provider_json("")


def test_parse_provider_json_raises_on_genuinely_non_json_content():
    with pytest.raises(MediaExtractionParseError):
        parse_provider_json("the model refused to answer in JSON at all")
