"""List-filter test: promotions filtered by expiry_notify_batch_id.

PromotionService.list_promotions(expiry_notify_batch_id=<id>) must return only
promos stamped with that batch id (the deep link from the expiry-reminder email).
Uses the same in-memory sqlite fixture the other promotion service tests use.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

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


def _seed(db, description, *, batch_id=None) -> Promotion:
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=description,
        start_date=TODAY - timedelta(days=5),
        end_date=TODAY + timedelta(days=7),
        is_active=True,
        access_levels=["dealer"],
        expiry_notify_batch_id=batch_id,
    )
    db.add(promo)
    db.flush()
    return promo


def test_list_filters_to_batch_id(db):
    batch = str(uuid.uuid4())
    in_batch_a = _seed(db, "BATCH Promo A", batch_id=batch)
    in_batch_b = _seed(db, "BATCH Promo B", batch_id=batch)
    _seed(db, "Other Promo", batch_id=str(uuid.uuid4()))  # different batch
    _seed(db, "Unstamped Promo", batch_id=None)
    db.commit()

    result = PromotionService(db).list_promotions(expiry_notify_batch_id=batch)
    returned_ids = {str(row.id) for row in result["data"]}
    assert returned_ids == {str(in_batch_a.id), str(in_batch_b.id)}
    assert result["pagination"]["total"] == 2


def test_list_batch_id_no_match_is_empty(db):
    _seed(db, "Promo", batch_id=str(uuid.uuid4()))
    db.commit()
    result = PromotionService(db).list_promotions(expiry_notify_batch_id=str(uuid.uuid4()))
    assert result["data"] == []
    assert result["pagination"]["total"] == 0
