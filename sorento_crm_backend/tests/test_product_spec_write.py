"""Pure unit tests of `app.services.product_spec_write` - no DB needed for most of it.

Contract: PR1-CONTRACT.md section 1. UAC: `spec-authoring-verification-acceptance-
criteria.md`, section "F - Foundations (PR 1)".

This module does not exist yet. Every test here is expected to fail at collection
with an ImportError until `app/services/product_spec_write.py` is written - that
import failure IS the red state (see the tester brief: "Import failures ARE the red
state").
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.product_spec import ProductSpecifications
from app.services.product_spec_write import (
    AUTHORED_SOURCES,
    _UNCHANGED,
    canonical_values_hash,
    merge_authored_over,
    write_spec_row,
)


def _spec() -> ProductSpecifications:
    """A bare, unpersisted row - write_spec_row only assigns Python attributes."""
    return ProductSpecifications(product_id=str(uuid.uuid4()))


# --------------------------------------------------------------------------- #
# AC-F.7 - AUTHORED_SOURCES, never a bare '== human' (M2-S1)
# --------------------------------------------------------------------------- #
def test_authored_sources_contains_human_and_supplier():
    assert AUTHORED_SOURCES == frozenset({"human", "supplier"})


def test_authored_sources_is_a_frozenset():
    # A plain set here would let a careless `AUTHORED_SOURCES.add(...)` mutate the
    # module-level constant from anywhere that imports it.
    assert isinstance(AUTHORED_SOURCES, frozenset)


# --------------------------------------------------------------------------- #
# AC-F.11 - canonical_values_hash, and the traps measured in M8
# --------------------------------------------------------------------------- #
def test_the_hash_is_a_sha256_hex_digest():
    digest = canonical_values_hash({"material": {"value": "brass"}})
    assert isinstance(digest, str)
    assert len(digest) == 64
    int(digest, 16)  # must be valid hex


def test_int_float_and_decimal_forms_of_the_same_number_hash_alike():
    assert (
        canonical_values_hash({"diameter": {"value": 407}})
        == canonical_values_hash({"diameter": {"value": 407.0}})
        == canonical_values_hash({"diameter": {"value": Decimal("407.000")}})
    )


def test_array_values_are_order_insensitive():
    assert canonical_values_hash(
        {"spray_functions": {"value": ["a", "b"]}}
    ) == canonical_values_hash({"spray_functions": {"value": ["b", "a"]}})


def test_a_key_whose_value_normalises_to_none_is_dropped_entirely():
    """M2-S8 - a pre-seeded blank must never collide with a tombstone, which is what
    would happen if a None-valued key survived into the hash as a real entry."""
    assert canonical_values_hash({"a": {"value": None}}) == canonical_values_hash({})


def test_booleans_are_tested_before_numbers_and_hash_differently_from_one():
    # bool is a subclass of int in Python - a naive isinstance(v, (int, float)) check
    # would treat True and 1 as the same number.
    assert canonical_values_hash({"is_smart": {"value": True}}) != canonical_values_hash(
        {"is_smart": {"value": 1}}
    )


def test_a_missing_a_none_and_an_empty_string_unit_all_hash_alike():
    assert (
        canonical_values_hash({"diameter": {"value": 10}})
        == canonical_values_hash({"diameter": {"value": 10, "unit": None}})
        == canonical_values_hash({"diameter": {"value": 10, "unit": ""}})
    )


def test_a_present_unit_is_casefolded():
    assert canonical_values_hash({"diameter": {"value": 10, "unit": "MM"}}) == canonical_values_hash(
        {"diameter": {"value": 10, "unit": "mm"}}
    )


def test_a_different_unit_changes_the_hash():
    assert canonical_values_hash({"hose_length": {"value": 10, "unit": "mm"}}) != canonical_values_hash(
        {"hose_length": {"value": 10, "unit": "L"}}
    )


def test_string_values_are_stripped_of_surrounding_whitespace():
    assert canonical_values_hash({"finish": {"value": "  chrome  "}}) == canonical_values_hash(
        {"finish": {"value": "chrome"}}
    )


def test_string_case_is_preserved_not_folded():
    # A case change is a real edit a person can see, so it must move the hash - unlike
    # the unit, which is a system-chosen spelling rather than something a person typed.
    assert canonical_values_hash({"finish": {"value": "Chrome"}}) != canonical_values_hash(
        {"finish": {"value": "chrome"}}
    )


def test_a_bare_scalar_is_treated_as_a_value_entry():
    """Defensive per contract 1.2: a bare scalar stored under a key is `{"value": v}`."""
    assert canonical_values_hash({"bowl_count": 2}) == canonical_values_hash(
        {"bowl_count": {"value": 2}}
    )


def test_extra_keys_in_an_entry_do_not_move_the_hash():
    """Provenance is never an input to this function (it does not even take a
    provenance argument). Even an entry shaped like a provenance record - carrying a
    `source`/`evidence` key alongside `value` - must hash identically to the plain
    value entry, proving only `value` and `unit` are read.
    """
    plain = {"material": {"value": "brass"}}
    with_provenance_shaped_keys = {
        "material": {"value": "brass", "source": "human", "evidence": "reviewed", "confidence": 1.0}
    }
    assert canonical_values_hash(plain) == canonical_values_hash(with_provenance_shaped_keys)


def test_different_values_hash_differently():
    # Sanity check: the hash is not a constant.
    assert canonical_values_hash({"material": {"value": "brass"}}) != canonical_values_hash(
        {"material": {"value": "ceramic"}}
    )


# --------------------------------------------------------------------------- #
# AC-F.3 - THE RESURRECTION PIN, the most important test in this PR
# --------------------------------------------------------------------------- #
def test_a_provenance_only_tombstone_drops_the_value_and_keeps_the_flag_verbatim():
    """AC-F.3 - the documented resurrection trap.

    Under today's merge (`product_spec_derivation.py:1292-1301`), a "kept" entry is
    built by keeping the human PROVENANCE unconditionally, but only carrying the VALUE
    across when the key is already present in `spec.values`:

        kept_values, kept_provenance = {}, {}
        for key, entry in (spec.provenance or {}).items():
            if entry.get("source") == "human":
                kept_provenance[key] = entry
                if key in (spec.values or {}):
                    kept_values[key] = spec.values[key]
        spec.values = {**result.values, **kept_values}
        spec.provenance = {**result.provenance, **kept_provenance}

    A tombstone is, by construction, NOT in `spec.values` (that is what "removed"
    means). So `kept_values` never gets the key, `spec.values` falls through to
    `result.values` - derivation's own answer - while `spec.provenance` still says a
    human set it. The derived value comes back badged as human-set and attributed to
    whoever deleted it: worse than "remove means revert to derived", because it LIES
    about who set the surviving value.

    `merge_authored_over` must instead drop the key from `values` entirely and keep
    exactly `{"source": "human", ..., "absent": True}` in `provenance`.
    """
    derived_values = {"material": {"value": "ceramic"}}
    derived_provenance = {"material": {"source": "derived", "confidence": 1.0, "evidence": "CERAMIC"}}
    existing_values: dict = {}
    existing_provenance = {
        "material": {"source": "human", "confidence": 1.0, "evidence": "removed by a person", "absent": True}
    }

    values, provenance, conflicts = merge_authored_over(
        derived_values, derived_provenance, existing_values, existing_provenance
    )

    assert "material" not in values, "the derived value must not resurrect under a tombstone"
    assert provenance["material"]["source"] == "human"
    assert provenance["material"]["absent"] is True
    assert conflicts == []


def test_the_old_merge_line_resurrects_the_value_the_new_merge_does_not():
    """AC-F.3, made a real pin rather than a documented-but-unasserted claim.

    The docstring on the test above only asserts the NEW merge's behaviour, so a
    regression that reintroduced the resurrection bug would not fail anything named
    "resurrection". This test inlines the OLD merge line verbatim (PR1-CONTRACT.md
    section 1.3, `product_spec_derivation.py:1292-1301` before this PR) as a local
    helper, runs it against the SAME tombstone fixture, and asserts it fails for the
    documented reason - the derived value comes back badged as human-set - before
    asserting `merge_authored_over` does not.
    """
    derived_values = {"material": {"value": "ceramic"}}
    derived_provenance = {"material": {"source": "derived", "confidence": 1.0, "evidence": "CERAMIC"}}
    existing_values: dict = {}
    existing_provenance = {
        "material": {"source": "human", "confidence": 1.0, "evidence": "removed by a person", "absent": True}
    }

    class _Result:
        values = derived_values
        provenance = derived_provenance

    def _old_merge(result, spec_values, spec_provenance):
        """Verbatim inline of the pre-PR1 merge line quoted in the contract."""
        kept_values, kept_provenance = {}, {}
        for key, entry in (spec_provenance or {}).items():
            if entry.get("source") == "human":
                kept_provenance[key] = entry
                if key in (spec_values or {}):
                    kept_values[key] = spec_values[key]
        values = {**result.values, **kept_values}
        provenance = {**result.provenance, **kept_provenance}
        return values, provenance

    old_values, old_provenance = _old_merge(_Result(), existing_values, existing_provenance)

    # The pin fails for the RIGHT reason only if the old merge actually resurrects the
    # value: the key falls through to derivation's answer while provenance still says
    # a human set it.
    assert old_values["material"] == derived_values["material"], (
        "the old merge line must resurrect the derived value under a tombstone - if "
        "this fails, the trap this test pins has changed shape and the test itself "
        "needs re-reading, not the source"
    )
    assert old_provenance["material"]["source"] == "human", (
        "the old merge keeps the human provenance verbatim - that is what makes the "
        "resurrected value a lie about who set it"
    )

    new_values, new_provenance, new_conflicts = merge_authored_over(
        derived_values, derived_provenance, existing_values, existing_provenance
    )

    assert "material" not in new_values, "merge_authored_over must not resurrect the value"
    assert new_provenance["material"]["source"] == "human"
    assert new_provenance["material"]["absent"] is True
    assert new_conflicts == []


# --------------------------------------------------------------------------- #
# AC-F.6 - a tombstone never raises a conflict, even against a disagreeing derivation
# --------------------------------------------------------------------------- #
def test_a_tombstoned_key_raises_no_conflict_even_when_derivation_disagrees():
    derived_values = {"shape": {"value": "round"}}
    derived_provenance = {"shape": {"source": "derived", "confidence": 1.0, "evidence": "ROUND"}}
    existing_provenance = {
        "shape": {"source": "human", "confidence": 1.0, "evidence": "not applicable", "absent": True}
    }

    values, provenance, conflicts = merge_authored_over(
        derived_values, derived_provenance, {}, existing_provenance
    )

    assert "shape" not in values
    assert conflicts == []


# --------------------------------------------------------------------------- #
# AC-F.5 - an authored value wins a conflict, and raises exactly one record
# --------------------------------------------------------------------------- #
def test_a_conflicting_authored_value_stays_in_force_and_raises_one_conflict():
    derived_values = {"material": {"value": "ceramic"}}
    derived_provenance = {"material": {"source": "derived", "confidence": 1.0, "evidence": "CERAMIC"}}
    existing_values = {"material": {"value": "brass"}}
    existing_provenance = {
        "material": {"source": "human", "confidence": 1.0, "evidence": "set by a person"}
    }

    values, provenance, conflicts = merge_authored_over(
        derived_values, derived_provenance, existing_values, existing_provenance
    )

    assert values["material"] == {"value": "brass"}, "the authored value stays in force"
    assert provenance["material"]["source"] == "human"
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["spec_key"] == "material"
    assert conflict["reason"] == "human_override_conflict"
    assert conflict["proposed"] == derived_values["material"]
    assert conflict["stored"] == existing_values["material"]


def test_an_authored_value_that_agrees_after_normalisation_raises_no_conflict():
    """407 vs 407.0 is the same value once canonicalised - not a disagreement."""
    derived_values = {"diameter": {"value": 407.0}}
    derived_provenance = {"diameter": {"source": "derived", "confidence": 1.0, "evidence": "407"}}
    existing_values = {"diameter": {"value": 407}}
    existing_provenance = {
        "diameter": {"source": "human", "confidence": 1.0, "evidence": "set by a person"}
    }

    values, provenance, conflicts = merge_authored_over(
        derived_values, derived_provenance, existing_values, existing_provenance
    )

    assert values["diameter"]["value"] == 407
    assert conflicts == []


def test_a_supplier_sourced_entry_conflicts_exactly_like_a_human_one():
    """M2-S1 - 'supplier' behaves identically to 'human' in the merge."""
    derived_values = {"material": {"value": "ceramic"}}
    derived_provenance = {"material": {"source": "derived", "confidence": 1.0, "evidence": "CERAMIC"}}
    existing_values = {"material": {"value": "brass"}}
    existing_provenance = {
        "material": {"source": "supplier", "confidence": 1.0, "evidence": "supplier submission"}
    }

    values, provenance, conflicts = merge_authored_over(
        derived_values, derived_provenance, existing_values, existing_provenance
    )

    assert values["material"]["value"] == "brass"
    assert provenance["material"]["source"] == "supplier"
    assert len(conflicts) == 1
    assert conflicts[0]["reason"] == "human_override_conflict"


# --------------------------------------------------------------------------- #
# The defensive general case - authored provenance, no value, no absent flag
# --------------------------------------------------------------------------- #
def test_authored_provenance_with_no_value_and_no_absent_flag_behaves_as_a_tombstone():
    """Section 1.3.3 of the contract - the shape that produces today's resurrection
    bug. Treated defensively as a tombstone: the key does not come back and no
    conflict is raised."""
    derived_values = {"seat_material": {"value": "pp"}}
    derived_provenance = {"seat_material": {"source": "derived", "confidence": 1.0, "evidence": "PP"}}
    existing_provenance = {
        "seat_material": {"source": "human", "confidence": 1.0, "evidence": "reviewed"}
    }
    # No matching entry in existing_values, and no "absent" flag either.

    values, provenance, conflicts = merge_authored_over(
        derived_values, derived_provenance, {}, existing_provenance
    )

    assert "seat_material" not in values
    assert conflicts == []


# --------------------------------------------------------------------------- #
# AC-F.8 - status precedence, computed by write_spec_row
# --------------------------------------------------------------------------- #
def test_status_is_needs_review_when_exceptions_are_present():
    spec = _spec()
    write_spec_row(spec, values={}, provenance={}, has_exceptions=True)
    assert spec.status == "needs_review"


def test_status_is_authored_when_a_human_provenance_entry_exists_and_no_exceptions():
    spec = _spec()
    write_spec_row(
        spec,
        values={"material": {"value": "brass"}},
        provenance={"material": {"source": "human", "confidence": 1.0, "evidence": "x"}},
        has_exceptions=False,
    )
    assert spec.status == "authored"


def test_status_is_authored_for_a_supplier_sourced_entry_too():
    spec = _spec()
    write_spec_row(
        spec,
        values={},
        provenance={"material": {"source": "supplier", "confidence": 1.0, "evidence": "x"}},
        has_exceptions=False,
    )
    assert spec.status == "authored"


def test_status_is_authored_for_a_tombstone_entry_too():
    spec = _spec()
    write_spec_row(
        spec,
        values={},
        provenance={
            "material": {"source": "human", "confidence": 1.0, "evidence": "x", "absent": True}
        },
        has_exceptions=False,
    )
    assert spec.status == "authored"


def test_status_is_derived_otherwise():
    spec = _spec()
    write_spec_row(
        spec,
        values={"material": {"value": "ceramic"}},
        provenance={"material": {"source": "derived", "confidence": 1.0, "evidence": "x"}},
        has_exceptions=False,
    )
    assert spec.status == "derived"


def test_needs_review_outranks_authored():
    spec = _spec()
    write_spec_row(
        spec,
        values={"material": {"value": "brass"}},
        provenance={"material": {"source": "human", "confidence": 1.0, "evidence": "x"}},
        has_exceptions=True,
    )
    assert spec.status == "needs_review"


def test_approved_is_never_written():
    """AC-F.8 - the documented-but-never-written `approved` value is not reused."""
    spec = _spec()
    write_spec_row(spec, values={}, provenance={}, has_exceptions=False)
    assert spec.status != "approved"

    spec2 = _spec()
    write_spec_row(
        spec2,
        values={"material": {"value": "brass"}},
        provenance={"material": {"source": "human", "confidence": 1.0, "evidence": "x"}},
        has_exceptions=False,
    )
    assert spec2.status != "approved"


# --------------------------------------------------------------------------- #
# derived_hash sentinel behaviour
# --------------------------------------------------------------------------- #
def test_derived_hash_is_left_untouched_when_not_passed():
    spec = _spec()
    spec.derived_hash = "an-existing-hash"
    write_spec_row(spec, values={}, provenance={})
    assert spec.derived_hash == "an-existing-hash"


def test_derived_hash_is_set_to_none_when_explicitly_passed_as_none():
    """AC-F.12 - apply_spec_values passes derived_hash=None to force a re-derive, so
    the sentinel must distinguish "not passed" from "passed as None"."""
    spec = _spec()
    spec.derived_hash = "an-existing-hash"
    write_spec_row(spec, values={}, provenance={}, derived_hash=None)
    assert spec.derived_hash is None


def test_derived_hash_is_set_when_a_real_value_is_passed():
    spec = _spec()
    write_spec_row(spec, values={}, provenance={}, derived_hash="a-new-fingerprint")
    assert spec.derived_hash == "a-new-fingerprint"


def test_unchanged_sentinel_leaves_derived_hash_alone_while_none_clears_it_on_the_same_row():
    """`assert _UNCHANGED is not None` is true of every object in existence and pins
    nothing about behaviour. The property that matters, both exercised on ONE row so
    the sentinel's actual job is unambiguous: omitting `derived_hash` from the call
    leaves the column exactly as it was, and passing `derived_hash=None` explicitly
    clears it."""
    spec = _spec()
    spec.derived_hash = "an-existing-hash"

    write_spec_row(spec, values={}, provenance={})
    assert spec.derived_hash == "an-existing-hash", "omitting derived_hash must not touch it"

    write_spec_row(spec, values={}, provenance={}, derived_hash=None)
    assert spec.derived_hash is None, "an explicit None must clear it"

    assert _UNCHANGED is not None, "the sentinel must itself be distinguishable from None"


# --------------------------------------------------------------------------- #
# write_spec_row also owns rendered_text and values/provenance assignment
# --------------------------------------------------------------------------- #
def test_write_spec_row_assigns_values_and_provenance_verbatim():
    spec = _spec()
    values = {"material": {"value": "brass"}}
    provenance = {"material": {"source": "human", "confidence": 1.0, "evidence": "x"}}
    write_spec_row(spec, values=values, provenance=provenance)
    assert spec.values == values
    assert spec.provenance == provenance


def test_write_spec_row_renders_the_spec_sentence():
    spec = _spec()
    write_spec_row(spec, values={"material": {"value": "brass"}}, provenance={})
    assert spec.rendered_text, "a non-empty values dict must render a non-empty sentence"
