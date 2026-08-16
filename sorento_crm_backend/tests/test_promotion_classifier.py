"""The promotion type read off an uploaded file's name (UAC C1-C6).

Every test builds its own type rows in a blank schema: the classifier's answers
must come from the seed VALUES under test, not from whatever the shared database
happens to hold.
"""
from __future__ import annotations

import pytest

from app.models.marketing import PromotionType
from app.services.promotion_classifier import (
    classify_promotion_type,
    classify_text,
    list_types_for_matching,
)
from tests._pg_fixture import blank_session


SEED = [
    ("special", "Special Promo", ["special"], 10, False),
    ("pp", "PP Promo", ["pp"], 20, False),
    ("focus_item", "Focus Item", ["focus", "focus item"], 30, False),
    ("a3_flyer", "A3 Flyer", ["a3", "a3 flyer"], 40, False),
    ("standard", "Standard Promo", [], 99, True),
]


def _seed_types(db):
    for code, name, markers, priority, is_default in SEED:
        db.add(
            PromotionType(
                type_code=code,
                type_name=name,
                match_markers=markers,
                match_priority=priority,
                is_default=is_default,
                show_expired=code != "special",
            )
        )
    db.flush()
    return list_types_for_matching(db)


@pytest.mark.parametrize(
    "filename, expected",
    [
        # C1 / C2 — the five markers as they actually appear in production names.
        ("SORENTO SPECIAL PROMO_22052026 DEALER.pdf", "special"),
        ("SORENTO PP PROMO COMBINE_08072026 (OFFICE).pdf", "pp"),
        ("SORENTO FOCUS ITEM JULY 2026.pdf", "focus_item"),
        ("_SORENTO A3 FLYER 2025-2026_compressed", "a3_flyer"),
        ("CABANA SHELF PROMO 31032026 (DEALER USE)", "standard"),
        # C3 — word boundaries, not substrings.
        ("SUPPLY PROMO 2026.pdf", "standard"),
        ("SPECIALIST TOOLS PROMO.pdf", "standard"),
        # Separators are token boundaries, so a marker glued to punctuation still counts.
        ("@ CABANA PP-PROMO (OFFICE)_08072026.pdf", "pp"),
        # C4 — two markers resolve to the most conservative type.
        ("SORENTO PP SPECIAL PROMO 2026.pdf", "special"),
        ("A3 FLYER SPECIAL EDITION.pdf", "special"),
    ],
)
def test_marker_classification(filename, expected):
    with blank_session() as db:
        types = _seed_types(db)
        assert classify_text(filename, types).type_code == expected


def test_no_types_at_all_classifies_to_none():
    with blank_session() as db:
        assert classify_text("SORENTO SPECIAL PROMO.pdf", []) is None


def test_blank_name_falls_back_to_the_default_type():
    with blank_session() as db:
        types = _seed_types(db)
        assert classify_text(None, types).type_code == "standard"
        assert classify_text("   ", types).type_code == "standard"


def test_filename_beats_description():
    """The stored description is sanitised; the attachment's name is the truth."""
    with blank_session() as db:
        _seed_types(db)
        result = classify_promotion_type(
            db,
            description="CABANA COMBINE PROMO OFFICE_08072026.pdf",
            filename="@ CABANA SPECIAL PROMO (OFFICE)_08072026.pdf",
        )
        assert result.type_code == "special"


def test_filename_marker_beats_a_conflicting_description_marker():
    """Filename precedence holds even when the description names a stricter type."""
    with blank_session() as db:
        _seed_types(db)
        result = classify_promotion_type(
            db,
            description="SORENTO SPECIAL PROMO_22052026.pdf",
            filename="SORENTO PP PROMO COMBINE_08072026.pdf",
        )
        assert result.type_code == "pp"


def test_marker_less_filename_falls_back_to_the_description():
    """A generic first attachment must not bury the marker n8n posted.

    The first linked file can be a re-saved / renamed document or a T&C page, so
    a name with no marker is "nothing said", not "standard".
    """
    with blank_session() as db:
        _seed_types(db)
        result = classify_promotion_type(
            db,
            description="SORENTO SPECIAL PROMO_22052026.pdf",
            filename="document_2026_final_compressed.pdf",
        )
        assert result.type_code == "special"


def test_neither_name_carrying_a_marker_still_yields_the_default_type():
    with blank_session() as db:
        _seed_types(db)
        result = classify_promotion_type(
            db,
            description="CABANA SHELF PROMO 31032026 (DEALER USE).pdf",
            filename="document_2026_final_compressed.pdf",
        )
        assert result.type_code == "standard"


def test_markers_come_from_the_database_not_from_code():
    """C6: adding a marker to a row changes the verdict with no code change."""
    with blank_session() as db:
        types = _seed_types(db)
        assert classify_text("SORENTO CLEARANCE PROMO.pdf", types).type_code == "standard"

        special = db.query(PromotionType).filter(PromotionType.type_code == "special").one()
        special.match_markers = ["special", "clearance"]
        db.flush()

        types = list_types_for_matching(db)
        assert classify_text("SORENTO CLEARANCE PROMO.pdf", types).type_code == "special"


def test_priority_zero_wins_over_a_higher_number():
    """An explicit priority of 0 is the strongest, not the weakest.

    The admin form allows 0 and tells the user the lowest number wins, so a
    `or 100` fallback that folded 0 into the default slot handed the match to
    whichever type sorted first instead.
    """
    with blank_session() as db:
        types = _seed_types(db)
        db.add(
            PromotionType(
                type_code="clearance",
                type_name="Clearance",
                match_markers=["clearance", "special"],
                match_priority=0,
                show_expired=False,
            )
        )
        db.flush()

        types = list_types_for_matching(db)
        # Both types carry the "special" marker; priority 0 must outrank 10.
        assert classify_text("SORENTO SPECIAL PROMO.pdf", types).type_code == "clearance"


def test_a_missing_priority_still_falls_back_to_the_default_slot():
    """Only NULL falls back - that behaviour is unchanged."""
    with blank_session() as db:
        _seed_types(db)
        db.add(
            PromotionType(
                type_code="no_priority",
                type_name="No Priority",
                match_markers=["special"],
                match_priority=None,
                show_expired=False,
            )
        )
        db.flush()

        types = list_types_for_matching(db)
        # `special` (10) still wins over a type with no priority at all.
        assert classify_text("SORENTO SPECIAL PROMO.pdf", types).type_code == "special"
