"""PromotionService.list_promotions search matches linked attachment filename."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.marketing import Promotion, PromotionAttachment
from app.models.resources import Attachment
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


def _seed_attachment(db, filename: str) -> str:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"/tmp/{filename}",
        access_levels=["dealer"],
    )
    db.add(att)
    db.flush()
    return att.id


def _seed_promotion(
    db,
    *,
    description: str,
    active: bool = True,
) -> str:
    today = datetime.utcnow().date()
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=30),
        is_active=active,
        access_levels=["dealer"],
    )
    db.add(promo)
    db.flush()
    return promo.id


def _link_attachment(db, promotion_id: str, attachment_id: str) -> None:
    db.add(
        PromotionAttachment(
            id=str(uuid.uuid4()),
            promotion_id=promotion_id,
            attachment_id=attachment_id,
            is_primary=True,
            sort_order=0,
        )
    )
    db.flush()


def test_search_matches_linked_promotion_attachment_filename(db):
    promo_id = _seed_promotion(db, description="Summer Promo")
    other_id = _seed_promotion(db, description="Other Promo")
    att_id = _seed_attachment(db, "summer-sale-poster.pdf")
    _link_attachment(db, promo_id, att_id)
    db.commit()

    result = PromotionService(db).list_promotions(query="summer-sale-poster")
    ids = [p.id for p in result["data"]]
    assert promo_id in ids
    assert other_id not in ids


def test_search_matches_promotion_description(db):
    target_id = _seed_promotion(db, description="UNIQUE_XYZ_123")
    _seed_promotion(db, description="OTHER_ABC")
    db.commit()

    result = PromotionService(db).list_promotions(query="UNIQUE_XYZ_123")
    ids = [p.id for p in result["data"]]
    assert ids == [target_id]
