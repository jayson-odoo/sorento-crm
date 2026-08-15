"""Per-type serving semantics (UAC S1-S6, E1, E4, N1).

The candidate set is always built here in a blank schema, because the whole point
of the policy is which of a KNOWN set of promotions answers a question.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.marketing import Promotion, PromotionGroup, PromotionProduct, PromotionType
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import promotion_serving
from app.services.marketing_service import PromotionService
from tests._pg_fixture import blank_session, unique_code


TODAY = date(2026, 8, 14)


def _type(db, code, **kwargs):
    defaults = dict(
        type_name=code.title(),
        show_expired=True,
        expired_valid_until_year_end=False,
        expired_max_age_days=None,
        match_markers=[],
        match_priority=50,
        is_default=False,
    )
    defaults.update(kwargs)
    promo_type = PromotionType(type_code=code, **defaults)
    db.add(promo_type)
    db.flush()
    return promo_type


def _promo(db, description, *, start, end, promo_type=None, is_active=True, created_at=None):
    promotion = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=start,
        end_date=end,
        is_active=is_active,
        access_levels=["dealer"],
        promotion_type_id=promo_type.id if promo_type else None,
        created_at=created_at or datetime(2026, 1, 1),
    )
    db.add(promotion)
    db.flush()
    return promotion


def _evaluate(db, promotions, today=TODAY):
    return promotion_serving.evaluate_candidates(db, [p.id for p in promotions], today)


def _standard(db):
    return _type(db, "standard", expired_valid_until_year_end=True, is_default=True)


def test_live_promotion_is_served_and_suppresses_its_own_expired(  # S1, S2
):
    with blank_session() as db:
        standard = _standard(db)
        live = _promo(db, "live standard", start=TODAY - timedelta(days=10), end=TODAY + timedelta(days=10), promo_type=standard)
        expired = _promo(db, "expired standard", start=TODAY - timedelta(days=90), end=TODAY - timedelta(days=5), promo_type=standard)

        verdict = _evaluate(db, [live, expired])

        assert verdict.is_served(live.id)
        assert not verdict.is_served(expired.id)
        assert not verdict.is_expired_but_usable(live.id)


def test_latest_expired_of_a_type_is_served_when_nothing_live():  # S2
    with blank_session() as db:
        standard = _standard(db)
        older = _promo(db, "june", start=TODAY - timedelta(days=120), end=TODAY - timedelta(days=45), promo_type=standard)
        newer = _promo(db, "july", start=TODAY - timedelta(days=90), end=TODAY - timedelta(days=14), promo_type=standard)

        verdict = _evaluate(db, [older, newer])

        assert verdict.is_served(newer.id)
        assert verdict.is_expired_but_usable(newer.id)
        assert not verdict.is_served(older.id)


def test_exact_end_date_tie_serves_both_capped_at_two():  # S2 tail
    with blank_session() as db:
        standard = _standard(db)
        end = TODAY - timedelta(days=14)
        a = _promo(db, "tie a", start=TODAY - timedelta(days=90), end=end, promo_type=standard, created_at=datetime(2026, 6, 1))
        b = _promo(db, "tie b", start=TODAY - timedelta(days=90), end=end, promo_type=standard, created_at=datetime(2026, 5, 1))
        c = _promo(db, "tie c", start=TODAY - timedelta(days=90), end=end, promo_type=standard, created_at=datetime(2026, 4, 1))

        verdict = _evaluate(db, [a, b, c])

        assert verdict.served_ids == {str(a.id), str(b.id)}


def test_special_never_serves_after_expiry():  # S3
    with blank_session() as db:
        _standard(db)
        special = _type(db, "special", show_expired=False, match_priority=10)
        expired = _promo(db, "expired special", start=TODAY - timedelta(days=60), end=TODAY - timedelta(days=1), promo_type=special)

        verdict = _evaluate(db, [expired])

        assert verdict.served_ids == set()


def test_year_end_bound():  # S4
    with blank_session() as db:
        pp = _type(db, "pp", expired_valid_until_year_end=True)
        _standard(db)
        this_year = _promo(db, "pp this year", start=date(2026, 1, 1), end=date(2026, 7, 31), promo_type=pp)
        last_year = _promo(db, "pp last year", start=date(2025, 1, 1), end=date(2025, 12, 31), promo_type=pp)

        verdict = _evaluate(db, [this_year, last_year])

        assert verdict.is_served(this_year.id)
        assert not verdict.is_served(last_year.id)


def test_max_age_bound_and_reconfiguring_it():  # S4
    with blank_session() as db:
        _standard(db)
        flyer = _type(db, "a3_flyer", expired_max_age_days=180)
        old = _promo(db, "old flyer", start=date(2025, 6, 1), end=TODAY - timedelta(days=200), promo_type=flyer)

        assert not _evaluate(db, [old]).is_served(old.id)

        # The bound is configuration, not code: widening it changes the answer.
        flyer.expired_max_age_days = 365
        db.flush()
        assert _evaluate(db, [old]).is_served(old.id)


def test_live_of_one_type_does_not_suppress_expired_of_another():  # S5 — the SRTWC286 bug
    with blank_session() as db:
        standard = _standard(db)
        flyer = _type(db, "a3_flyer", expired_max_age_days=180)
        live_flyer = _promo(db, "A3 flyer", start=TODAY - timedelta(days=30), end=TODAY + timedelta(days=60), promo_type=flyer)
        expired_wc = _promo(db, "July WC promo", start=TODAY - timedelta(days=90), end=TODAY - timedelta(days=14), promo_type=standard)

        verdict = _evaluate(db, [live_flyer, expired_wc])

        assert verdict.is_served(live_flyer.id)
        assert verdict.is_served(expired_wc.id)
        assert verdict.is_expired_but_usable(expired_wc.id)
        assert not verdict.is_expired_but_usable(live_flyer.id)


def test_unclassified_promotion_follows_the_default_type():  # S6
    with blank_session() as db:
        standard = _standard(db)
        untyped = _promo(db, "legacy promo", start=TODAY - timedelta(days=90), end=TODAY - timedelta(days=14), promo_type=None)

        verdict = _evaluate(db, [untyped])
        assert verdict.is_served(untyped.id)
        assert verdict.is_expired_but_usable(untyped.id)

        # And when the default cannot be honoured after expiry, neither can it.
        standard.show_expired = False
        db.flush()
        assert not _evaluate(db, [untyped]).is_served(untyped.id)


def test_is_active_flag_off_inside_the_window_is_a_kill_switch():
    """Switching a promotion off mid-window pulls it from answers entirely."""
    with blank_session() as db:
        standard = _standard(db)
        switched_off = _promo(
            db,
            "switched off",
            start=TODAY - timedelta(days=5),
            end=TODAY + timedelta(days=5),
            promo_type=standard,
            is_active=False,
        )
        verdict = _evaluate(db, [switched_off])
        assert verdict.served_ids == set()


def test_is_active_flag_off_after_the_end_date_is_still_an_expired_candidate():
    with blank_session() as db:
        standard = _standard(db)
        ended = _promo(
            db,
            "ended and off",
            start=TODAY - timedelta(days=60),
            end=TODAY - timedelta(days=10),
            promo_type=standard,
            is_active=False,
        )
        verdict = _evaluate(db, [ended])
        assert verdict.is_served(ended.id)
        assert verdict.is_expired_but_usable(ended.id)


def test_not_yet_started_promotion_is_neither_live_nor_expired():
    """September promo uploaded in August must not be served as expired-but-usable."""
    with blank_session() as db:
        standard = _standard(db)
        september = _promo(
            db,
            "september pp",
            start=TODAY + timedelta(days=17),
            end=TODAY + timedelta(days=47),
            promo_type=standard,
        )
        verdict = _evaluate(db, [september])
        assert verdict.served_ids == set()


# --- the endpoint (UAC E1, N1) ---------------------------------------------


def _product(db):
    """A product with its own category and UOM -- Postgres enforces both FKs."""
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=unique_code("CAT"),
        category_name="Serving policy fixture",
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM"), uom_name="Piece")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code("PROD"),
        product_name="Serving policy fixture",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=100,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _link(db, promotion, product):
    group = PromotionGroup(promotion_id=promotion.id, group_name="Default", sort_order=0)
    db.add(group)
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promotion.id,
            promotion_group_id=group.id,
            product_id=product.id,
        )
    )
    db.flush()


@pytest.fixture()
def served_fixture():
    with blank_session() as db:
        standard = _standard(db)
        special = _type(db, "special", show_expired=False, match_priority=10)
        flyer = _type(db, "a3_flyer", expired_max_age_days=180)

        product = _product(db)
        today = datetime.utcnow().date()
        live_flyer = _promo(db, "ZZT flyer", start=today - timedelta(days=30), end=today + timedelta(days=60), promo_type=flyer)
        expired_standard = _promo(db, "ZZT standard", start=today - timedelta(days=90), end=today - timedelta(days=14), promo_type=standard)
        expired_special = _promo(db, "ZZT special", start=today - timedelta(days=90), end=today - timedelta(days=7), promo_type=special)
        for promotion in (live_flyer, expired_standard, expired_special):
            _link(db, promotion, product)

        yield db, product, live_flyer, expired_standard, expired_special


def test_list_promotions_serving_policy(served_fixture):  # E1
    db, product, live_flyer, expired_standard, expired_special = served_fixture
    result = PromotionService(db).list_promotions(
        product_ids=[product.id], serving_policy=True, limit=50
    )

    ids = {str(row.id) for row in result["data"]}
    assert ids == {str(live_flyer.id), str(expired_standard.id)}
    assert result["serving_policy_applied"] is True
    assert result["fallback_used"] is False

    by_id = {str(row.id): row for row in result["data"]}
    assert by_id[str(expired_standard.id)].is_expired is True
    assert by_id[str(expired_standard.id)].expired_but_usable is True
    assert by_id[str(expired_standard.id)].promotion_type_code == "standard"
    assert by_id[str(live_flyer.id)].expired_but_usable is False
    assert by_id[str(live_flyer.id)].promotion_type_name == "A3_Flyer"


def test_list_promotions_without_policy_is_the_old_behaviour(served_fixture):  # N1
    db, product, live_flyer, _expired_standard, _expired_special = served_fixture
    result = PromotionService(db).list_promotions(product_ids=[product.id], limit=50)

    assert {str(row.id) for row in result["data"]} == {str(live_flyer.id)}
    assert result.get("serving_policy_applied") is None
    assert result["fallback_used"] is False


def test_policy_with_only_expired_specials_returns_an_empty_page():  # S3 at the route
    with blank_session() as db:
        _standard(db)
        special = _type(db, "special", show_expired=False, match_priority=10)
        product = _product(db)
        today = datetime.utcnow().date()
        expired_special = _promo(
            db,
            "ZZT lone special",
            start=today - timedelta(days=90),
            end=today - timedelta(days=7),
            promo_type=special,
        )
        _link(db, expired_special, product)

        result = PromotionService(db).list_promotions(
            product_ids=[product.id], serving_policy=True, limit=50
        )

        assert result["data"] == []
        assert result["pagination"]["total"] == 0
        assert result["serving_policy_applied"] is True


def test_policy_result_is_paginated(served_fixture):
    db, product, *_ = served_fixture
    page1 = PromotionService(db).list_promotions(
        product_ids=[product.id], serving_policy=True, limit=1, page=1
    )
    page2 = PromotionService(db).list_promotions(
        product_ids=[product.id], serving_policy=True, limit=1, page=2
    )
    assert page1["pagination"]["total"] == 2
    assert len(page1["data"]) == 1
    assert len(page2["data"]) == 1
    assert page1["data"][0].id != page2["data"][0].id
