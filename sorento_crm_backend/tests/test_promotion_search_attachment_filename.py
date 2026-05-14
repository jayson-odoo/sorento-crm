"""PromotionService.list_promotions search matches linked attachment filename."""
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
    promo_code: str,
    name: str,
    active: bool = True,
) -> str:
    today = datetime.utcnow().date()
    promo = Promotion(
        id=str(uuid.uuid4()),
        promo_code=promo_code,
        name=name,
        description="",
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
    promo_id = _seed_promotion(db, promo_code="PROMO_SUMMER", name="Summer Promo")
    other_id = _seed_promotion(db, promo_code="PROMO_OTHER", name="Other Promo")
    att_id = _seed_attachment(db, "summer-sale-poster.pdf")
    _link_attachment(db, promo_id, att_id)
    db.commit()

    result = PromotionService(db).list_promotions(query="summer-sale-poster")
    ids = [p.id for p in result["data"]]
    assert promo_id in ids
    assert other_id not in ids


def test_search_still_matches_promo_code(db):
    target_id = _seed_promotion(db, promo_code="UNIQUE_XYZ_123", name="Specific Promo")
    _seed_promotion(db, promo_code="OTHER_ABC", name="Other")
    db.commit()

    result = PromotionService(db).list_promotions(query="UNIQUE_XYZ_123")
    ids = [p.id for p in result["data"]]
    assert ids == [target_id]
