"""One rule everywhere on the resolve endpoint (captain, 2026-08-16).

The resolver reaches promotions by two different doors: the product-membership
walk ("any promo for SRTWC286?") and the description-text probe ("special
promo"). Only the first honoured the per-type serving policy, so naming a promo
returned an expired special that asking by product would have withheld - the
same endpoint answering the same question two ways.

These pin the name door to the same policy: served rows carry the type labels
and the expired-but-usable flag, withheld rows do not come back at all.

Run: pytest tests/test_references_name_probe_serving.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.api.v1.system.references import (
    _apply_serving_policy_to_promo_matches,
    _build_promotion_resolutions,
)
from app.models.marketing import Promotion, PromotionType
from tests._pg_fixture import blank_session


def _types(db):
    rows = {
        "standard": PromotionType(
            type_code="standard",
            type_name="Standard Promo",
            show_expired=True,
            expired_valid_until_year_end=True,
            is_default=True,
            match_priority=99,
        ),
        "special": PromotionType(
            type_code="special",
            type_name="Special Promo",
            show_expired=False,
            match_markers=["special"],
            match_priority=10,
        ),
    }
    db.add_all(rows.values())
    db.flush()
    return rows


def _promo(db, description, *, start, end, promo_type):
    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=start,
        end_date=end,
        is_active=True,
        access_levels=["dealer"],
        promotion_type_id=promo_type.id,
        promotion_type_source="auto",
    )
    db.add(promotion)
    db.flush()
    return promotion


@pytest.fixture()
def named_promos():
    """An expired special and an expired standard, both findable by name."""
    with blank_session() as db:
        types = _types(db)
        today = datetime.utcnow().date()
        special = _promo(
            db,
            "SORENTO SPECIAL PROMO 22052026",
            start=today - timedelta(days=120),
            end=today - timedelta(days=10),
            promo_type=types["special"],
        )
        standard = _promo(
            db,
            "SORENTO KITCHEN SINK PROMO",
            start=today - timedelta(days=120),
            end=today - timedelta(days=10),
            promo_type=types["standard"],
        )
        live = _promo(
            db,
            "SORENTO LIVE STANDARD PROMO",
            start=today - timedelta(days=5),
            end=today + timedelta(days=30),
            promo_type=types["standard"],
        )
        yield db, special, standard, live


def test_name_probe_withholds_the_expired_special(named_promos):
    """Naming a special that has ended returns nothing - it cannot be honoured."""
    db, special, _standard, _live = named_promos
    out = _build_promotion_resolutions(db, {str(special.id)})
    assert out == []


def test_name_probe_serves_expired_standard_with_the_flag(named_promos):
    """An expired standard is returned, flagged so the bot can phrase it."""
    db, _special, standard, _live = named_promos
    out = _build_promotion_resolutions(db, {str(standard.id)})
    assert len(out) == 1
    display = out[0]["display"]
    assert display["promotion_type_code"] == "standard"
    assert display["promotion_type_name"] == "Standard Promo"
    assert display["is_expired"] is True
    assert display["expired_but_usable"] is True


def test_name_probe_live_promo_is_not_flagged_expired(named_promos):
    """A live promo comes back plainly live - no expired-but-usable dressing."""
    db, _special, _standard, live = named_promos
    out = _build_promotion_resolutions(db, {str(live.id)})
    assert len(out) == 1
    display = out[0]["display"]
    assert display["is_active"] is True
    assert display["is_expired"] is False
    assert display["expired_but_usable"] is False


def test_name_probe_and_product_walk_agree_on_a_mixed_set(named_promos):
    """Asking for both at once: the special is dropped, the standard survives."""
    db, special, standard, _live = named_promos
    out = _build_promotion_resolutions(db, {str(special.id), str(standard.id)})
    assert [row["uuid"] for row in out] == [str(standard.id)]


def test_resolver_native_matches_get_the_same_policy(named_promos):
    """The resolver's own probe output is filtered by the same helper."""
    db, special, standard, _live = named_promos
    matches = [
        {"entity_type": "promotion", "uuid": str(special.id), "display": {}},
        {"entity_type": "promotion", "uuid": str(standard.id), "display": {}},
    ]
    kept = _apply_serving_policy_to_promo_matches(db, matches)
    assert [m["uuid"] for m in kept] == [str(standard.id)]
    assert kept[0]["display"]["promotion_type_code"] == "standard"
    assert kept[0]["display"]["expired_but_usable"] is True


def test_matches_without_a_uuid_are_left_alone(named_promos):
    """Defensive: a match the resolver could not key is passed through."""
    db, _special, _standard, _live = named_promos
    matches = [{"entity_type": "promotion", "display": {}}]
    assert _apply_serving_policy_to_promo_matches(db, matches) == matches
