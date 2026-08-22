"""An untyped promotion reports the DEFAULT type, not a blank (codex finding).

The serving policy already treats a promotion with no `promotion_type_id` as the
default type (D3) - a legacy row is served exactly as `standard`. The display
path looked the label up from the raw column, so the same payload said "served
under the standard rules" and "type: (blank)" at once, and the bot had nothing
to name.

Also pinned here: a detail read carries the same `expired_but_usable` verdict as
the list, so a drill-down cannot contradict the list it came from.

Run: pytest tests/test_promotion_default_type_labels.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.marketing import Promotion, PromotionType
from app.services.marketing_service import _stamp_promotion_type_fields
from tests._pg_fixture import blank_session


@pytest.fixture()
def db_with_types():
    with blank_session() as db:
        db.add_all(
            [
                PromotionType(
                    type_code="standard",
                    type_name="Standard Promo",
                    show_expired=True,
                    expired_valid_until_year_end=True,
                    is_default=True,
                    match_priority=99,
                ),
                PromotionType(
                    type_code="special",
                    type_name="Special Promo",
                    show_expired=False,
                    match_markers=["special"],
                    match_priority=10,
                ),
            ]
        )
        db.flush()
        yield db


def _promo(db, description, *, start, end, promo_type=None):
    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=start,
        end_date=end,
        is_active=True,
        access_levels=["dealer"],
        promotion_type_id=promo_type.id if promo_type else None,
    )
    db.add(promotion)
    db.flush()
    return promotion


def test_untyped_row_reports_the_default_type(db_with_types):
    """A legacy row served as standard says so instead of showing a blank."""
    db = db_with_types
    today = datetime.utcnow().date()
    promotion = _promo(
        db, "LEGACY PROMO", start=today - timedelta(days=10), end=today + timedelta(days=10)
    )

    _stamp_promotion_type_fields(db, [promotion])

    assert promotion.promotion_type_code == "standard"
    assert promotion.promotion_type_name == "Standard Promo"


def test_expired_untyped_row_is_flagged_usable_under_the_default_rules(db_with_types):
    """The label and the verdict agree: served under standard, and still usable."""
    db = db_with_types
    today = datetime.utcnow().date()
    promotion = _promo(
        db, "LEGACY EXPIRED PROMO", start=today - timedelta(days=90), end=today - timedelta(days=5)
    )

    _stamp_promotion_type_fields(db, [promotion])

    assert promotion.promotion_type_code == "standard"
    assert promotion.expired_but_usable is True


def test_typed_row_still_reports_its_own_type(db_with_types):
    """The fallback must not overwrite a row that has a type of its own."""
    db = db_with_types
    special = db.query(PromotionType).filter(PromotionType.type_code == "special").one()
    today = datetime.utcnow().date()
    promotion = _promo(
        db,
        "SORENTO SPECIAL PROMO",
        start=today - timedelta(days=10),
        end=today + timedelta(days=10),
        promo_type=special,
    )

    _stamp_promotion_type_fields(db, [promotion])

    assert promotion.promotion_type_code == "special"
    assert promotion.promotion_type_name == "Special Promo"


def test_detail_read_matches_the_list_verdict_for_an_expired_special(db_with_types):
    """A withheld special reads expired_but_usable=false on the detail path too."""
    db = db_with_types
    special = db.query(PromotionType).filter(PromotionType.type_code == "special").one()
    today = datetime.utcnow().date()
    promotion = _promo(
        db,
        "SORENTO SPECIAL PROMO ENDED",
        start=today - timedelta(days=90),
        end=today - timedelta(days=5),
        promo_type=special,
    )

    _stamp_promotion_type_fields(db, [promotion])

    assert promotion.expired_but_usable is False
