"""PromotionService.list_promotions period window semantics per date_mode."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.audit import AuditLog
from app.models.embeddings import EmbeddingQueue
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.models.marketing import (
    Promotion,
    PromotionAttachment,
    PromotionGroup,
    PromotionProduct,
)
from app.models.product import Product
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.services.marketing_service import PromotionService


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(_element, _compiler, **_kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AttachmentDirectory.__table__,
            AttachmentType.__table__,
            Attachment.__table__,
            Product.__table__,
            Promotion.__table__,
            PromotionGroup.__table__,
            PromotionProduct.__table__,
            PromotionAttachment.__table__,
            LookupSet.__table__,
            LookupOption.__table__,
            LookupBinding.__table__,
            AuditLog.__table__,
            EmbeddingQueue.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


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
