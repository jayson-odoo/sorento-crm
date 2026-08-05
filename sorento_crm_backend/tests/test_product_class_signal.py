"""The class/brand signal hiding in product_categories.category_code.

`category_name` is a verbatim copy of `category_code` on all 175 live rows, so the
brand and class encoded in `SRT-KS` / `CB-FT` / `BRT-WC` are machine-invisible. Spec
search needs them as real values: class is the highest-coverage, highest-precision
ranking signal available (100% of products have a category, versus 14.6% with
dimensions).

Ticket: jayson-odoo/sorento-crm#72. Contract:
documentation/plans/products/spec-search-acceptance-criteria.md AC-T0a-01 .. AC-T0a-05.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product import ProductCategory
from app.services.product_class_signal import (
    NON_SEARCHABLE_CODES,
    backfill_category_signals,
    explain_code,
    resolve_classes_for_term,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _category(db, code: str) -> ProductCategory:
    """A category row shaped like the live ones: category_name copies category_code."""
    row = ProductCategory(id=str(uuid.uuid4()), category_code=code, category_name=code)
    db.add(row)
    db.flush()
    return row


def _reload(db, code: str) -> ProductCategory:
    return db.query(ProductCategory).filter(ProductCategory.category_code == code).one()


# AC-T0a-02: the pilot seed resolves both kitchen-sink categories.
def test_backfill_maps_the_pilot_categories(db):
    _category(db, "SRT-KS")
    _category(db, "CB-KS")

    backfill_category_signals(db)

    srt = _reload(db, "SRT-KS")
    assert srt.class_label == "Kitchen Sink"
    assert srt.brand_hint == "Sorento"

    cb = _reload(db, "CB-KS")
    assert cb.class_label == "Kitchen Sink"
    assert cb.brand_hint == "Cabana"


# AC-T0a-02: synonyms are seeded, because customer language is not catalog language.
def test_backfill_seeds_synonyms(db):
    _category(db, "SRT-KS")

    backfill_category_signals(db)

    synonyms = _reload(db, "SRT-KS").search_synonyms
    assert "kitchen sink" in synonyms
    assert "sink" in synonyms


# AC-T0a-04: idempotent by set-where-mismatch, NOT update-where-null. The distinction
# matters: update-where-null cannot repair a prior run that wrote the wrong value, and
# this backfill is expected to be re-run as the map grows.
def test_backfill_corrects_a_wrong_value_on_rerun(db):
    row = _category(db, "SRT-KS")
    backfill_category_signals(db)

    row = _reload(db, "SRT-KS")
    row.class_label = "Bathtub"          # a prior bad run, or a fat-fingered edit
    row.brand_hint = "Cabana"
    db.flush()

    backfill_category_signals(db)

    fixed = _reload(db, "SRT-KS")
    assert fixed.class_label == "Kitchen Sink"
    assert fixed.brand_hint == "Sorento"


def test_backfill_is_a_no_op_when_already_correct(db):
    _category(db, "SRT-KS")
    first = backfill_category_signals(db)
    second = backfill_category_signals(db)

    assert first["updated"] == 1
    assert second["updated"] == 0


# AC-T0a-04 / AC-T2-02: an unmapped code is left NULL, counted, and reported. Never
# silently defaulted to a class, because a wrong class is the single most damaging
# thing in the ranker (class carries the largest boost).
def test_unmapped_code_is_left_null_and_reported(db):
    _category(db, "ZZT-UNKNOWN-CODE")

    result = backfill_category_signals(db)

    row = _reload(db, "ZZT-UNKNOWN-CODE")
    assert row.class_label is None
    assert row.brand_hint is None
    assert "ZZT-UNKNOWN-CODE" in result["unmapped"]


# Codes with no class meaning must not masquerade as a searchable class.
def test_non_searchable_codes_are_flagged_and_carry_no_class(db):
    for code in sorted(NON_SEARCHABLE_CODES):
        _category(db, code)

    backfill_category_signals(db)

    for code in sorted(NON_SEARCHABLE_CODES):
        row = _reload(db, code)
        assert row.is_searchable is False, code
        assert row.class_label is None, code


def test_searchable_defaults_true_for_a_mapped_class(db):
    _category(db, "SRT-KS")
    backfill_category_signals(db)
    assert _reload(db, "SRT-KS").is_searchable is True


# AC-T0a-03: lookup matches label AND synonym, case-insensitively. The customer types
# "kitchen sink", the catalog says "SRT-KS", and neither knows about the other.
@pytest.mark.parametrize(
    "term",
    ["Kitchen Sink", "kitchen sink", "KITCHEN SINK", "  kitchen sink  ", "sink", "SINK"],
)
def test_resolve_classes_for_term_matches_label_and_synonym(db, term):
    _category(db, "SRT-KS")
    _category(db, "CB-KS")
    backfill_category_signals(db)

    assert resolve_classes_for_term(db, term) == ["Kitchen Sink"]


def test_resolve_classes_for_term_returns_empty_for_an_unknown_term(db):
    _category(db, "SRT-KS")
    backfill_category_signals(db)

    assert resolve_classes_for_term(db, "flux capacitor") == []


def test_resolve_classes_for_term_ignores_non_searchable_categories(db):
    _category(db, "MISC")
    backfill_category_signals(db)

    assert resolve_classes_for_term(db, "misc") == []


class TestExplainCode:
    """Four silences, four fixes.

    A product with no derived specs is not one situation. Collapsing them into a bare
    "no specs" sends whoever is troubleshooting into the ranker looking for a fault
    that actually lives in the pilot scope list, which is where the first real report
    from this feature came from.
    """

    def test_an_enabled_class_is_eligible(self):
        assert explain_code("SRT-KS") == {
            "reason": "eligible",
            "class_label": "Kitchen Sink",
            "brand_hint": "Sorento",
            "suffix": "KS",
        }

    def test_an_out_of_scope_class_names_the_suffix_that_is_off(self):
        # Taps: 7,120 live products, zero derived. The reason has to say so.
        result = explain_code("CB-FT")
        assert result["reason"] == "class_not_enabled"
        assert result["suffix"] == "FT"
        assert result["class_label"] is None
        # The brand half still parsed; only the class is missing.
        assert result["brand_hint"] == "Cabana"

    def test_a_meaningless_category_is_distinguished_from_an_unknown_one(self):
        for code in NON_SEARCHABLE_CODES:
            assert explain_code(code)["reason"] == "category_non_searchable"
        assert explain_code("NOTACODE")["reason"] == "code_unparsed"

    def test_a_missing_category_is_its_own_reason(self):
        assert explain_code(None)["reason"] == "no_category"
        assert explain_code("   ")["reason"] == "no_category"

    def test_every_reason_is_one_the_ui_can_render(self):
        # A reason the tab has no copy for renders as a blank, which is the exact
        # failure this function exists to prevent.
        rendered = {
            "eligible",
            "not_yet_derived",
            "class_not_enabled",
            "category_non_searchable",
            "code_unparsed",
            "no_category",
        }
        for code in ("SRT-KS", "CB-FT", "MISC", "NOTACODE", None, "", "ZZ-QQ"):
            assert explain_code(code)["reason"] in rendered
