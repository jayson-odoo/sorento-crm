"""PromotionService.list_promotions period window semantics per date_mode."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.marketing_service import PromotionService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite with a JSONB->JSON compile shim and a hand-listed
    subset of tables. The real schema has all 199 and the real column types.
    """
    with blank_session() as session:
        yield session


TODAY = datetime.utcnow().date()


def _seed_promotion(
    db,
    *,
    description: str,
    start_offset: int,
    end_offset: int,
    active: bool = True,
) -> str:
    """Seed a promotion with start/end as day offsets from today."""
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=TODAY + timedelta(days=start_offset),
        end_date=TODAY + timedelta(days=end_offset),
        is_active=active,
        access_levels=["dealer"],
    )
    db.add(promo)
    db.flush()
    return promo.id


def _seed_product(db) -> str:
    """A product plus the category/UOM rows its NOT NULL FKs require."""
    product_id = str(uuid.uuid4())
    category_id = str(uuid.uuid4())
    uom_id = str(uuid.uuid4())
    db.add(ProductCategory(id=category_id, category_code="CAT1", category_name="Category One"))
    db.add(UnitOfMeasure(id=uom_id, uom_code="EA", uom_name="Each"))
    db.flush()
    db.add(
        Product(
            id=product_id,
            product_code="SKU-1",
            product_name="SKU One",
            category_id=category_id,
            base_uom_id=uom_id,
            list_price=0,
            is_active=True,
        )
    )
    db.flush()
    return product_id


@pytest.fixture
def seeded(db):
    """Three promotions around a 10-day lookback window [today-10, today].

    - old_runner: started 60 days ago, still running (overlaps window,
      NOT released in it).
    - fresh: started 5 days ago, still running (released in window).
    - just_ended: started 40 days ago, ended 3 days ago (overlaps window,
      ended in it, not released in it). is_active flag still True but the
      window has passed -> treated as inactive by the active gate.
    """
    ids = {
        "old_runner": _seed_promotion(
            db, description="OLD_RUNNER", start_offset=-60, end_offset=30
        ),
        "fresh": _seed_promotion(
            db, description="FRESH", start_offset=-5, end_offset=30
        ),
        "just_ended": _seed_promotion(
            db, description="JUST_ENDED", start_offset=-40, end_offset=-3
        ),
    }
    db.commit()
    return ids


def _list_ids(db, **kwargs) -> set[str]:
    result = PromotionService(db).list_promotions(**kwargs)
    return {p.id for p in result["data"]}


WINDOW = {"period_from": TODAY - timedelta(days=10), "period_to": TODAY}


def test_overlap_default_matches_any_promo_running_during_window(db, seeded):
    # No date_mode -> overlap: all three ran at some point inside the window.
    ids = _list_ids(db, status="all", **WINDOW)
    assert ids == set(seeded.values())


def test_started_matches_only_promos_launched_in_window(db, seeded):
    ids = _list_ids(db, status="all", date_mode="started", **WINDOW)
    assert ids == {seeded["fresh"]}


def test_ended_matches_only_promos_expiring_in_window(db, seeded):
    ids = _list_ids(db, status="all", date_mode="ended", **WINDOW)
    assert ids == {seeded["just_ended"]}


def test_unknown_date_mode_falls_back_to_overlap(db, seeded):
    ids = _list_ids(db, status="all", date_mode="bogus", **WINDOW)
    assert ids == set(seeded.values())


def test_started_one_sided_window_since_date(db, seeded):
    # "released since 10 days ago" — only period_from supplied.
    ids = _list_ids(
        db, status="all", date_mode="started",
        period_from=TODAY - timedelta(days=10),
    )
    assert ids == {seeded["fresh"]}


def test_started_default_includes_both_active_and_already_ended_releases(db):
    # Two promos released inside the window: one still running, one already
    # ended. started/ended skip the active gate by default — both must come
    # back in ONE call (the active-first fallback alone would silently drop
    # the ended one whenever any active row matches).
    running = _seed_promotion(
        db, description="RUNNING", start_offset=-5, end_offset=30
    )
    flash = _seed_promotion(
        db, description="FLASH_SALE", start_offset=-5, end_offset=-1
    )
    db.commit()

    result = PromotionService(db).list_promotions(date_mode="started", **WINDOW)
    assert {p.id for p in result["data"]} == {running, flash}
    assert result["fallback_used"] is False


def test_started_with_explicit_active_true_keeps_the_gate(db):
    running = _seed_promotion(
        db, description="RUNNING", start_offset=-5, end_offset=30
    )
    _seed_promotion(db, description="FLASH_SALE", start_offset=-5, end_offset=-1)
    db.commit()

    result = PromotionService(db).list_promotions(
        active=True, date_mode="started", **WINDOW
    )
    assert {p.id for p in result["data"]} == {running}


def test_ended_default_returns_expired_promo_without_fallback(db, seeded):
    result = PromotionService(db).list_promotions(date_mode="ended", **WINDOW)
    assert {p.id for p in result["data"]} == {seeded["just_ended"]}
    assert result["fallback_used"] is False


def test_overlap_default_keeps_active_gate(db, seeded):
    # No date_mode -> active-first behaviour unchanged: just_ended is past
    # its window so the default gate excludes it while active rows match.
    ids = _list_ids(db, **WINDOW)
    assert ids == {seeded["old_runner"], seeded["fresh"]}


def test_promotion_ids_only_falls_back_to_expired_promo(db, seeded):
    # Explicit UUID = strongest narrowing filter: an expired promotion fetched
    # by id must come back via the inactive fallback, not an empty page.
    result = PromotionService(db).list_promotions(
        promotion_ids=[seeded["just_ended"]]
    )
    assert {p.id for p in result["data"]} == {seeded["just_ended"]}
    assert result["fallback_used"] is True


def test_product_ids_only_falls_back_to_expired_promo(db, seeded):
    # The filter itself only consults promotion_products.product_id, but the
    # column is a real FK, so the product (and its category/UOM parents) must
    # exist. sqlite let this be a dangling UUID.
    product_id = _seed_product(db)
    group = PromotionGroup(
        id=uuid.uuid4(),  # UUID(as_uuid=True) column wants the object, not str
        promotion_id=seeded["just_ended"],
        group_name="FB Group",
    )
    db.add(group)
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=seeded["just_ended"],
            promotion_group_id=group.id,
            product_id=product_id,
        )
    )
    db.commit()
    result = PromotionService(db).list_promotions(product_ids=[product_id])
    assert {p.id for p in result["data"]} == {seeded["just_ended"]}
    assert result["fallback_used"] is True


def test_promotion_ids_active_promo_no_fallback(db, seeded):
    result = PromotionService(db).list_promotions(promotion_ids=[seeded["fresh"]])
    assert {p.id for p in result["data"]} == {seeded["fresh"]}
    assert result["fallback_used"] is False


def test_is_expired_flag_marks_fallback_rows(db, seeded):
    # Fallback row (past end_date) -> is_expired=True even though is_active flag on.
    result = PromotionService(db).list_promotions(
        promotion_ids=[seeded["just_ended"]]
    )
    assert result["data"][0].is_expired is True

    # Live row -> is_expired=False.
    result = PromotionService(db).list_promotions(promotion_ids=[seeded["fresh"]])
    assert result["data"][0].is_expired is False


def test_is_expired_flag_no_window_follows_is_active(db):
    no_window = Promotion(
        id=str(uuid.uuid4()),
        description="NO_WINDOW",
        start_date=None,
        end_date=None,
        is_active=True,
        access_levels=["dealer"],
    )
    db.add(no_window)
    db.commit()
    result = PromotionService(db).list_promotions(promotion_ids=[no_window.id])
    assert result["data"][0].is_expired is False
