"""List-filter test: promotions filtered by expiry_notify_batch_id.

PromotionService.list_promotions(expiry_notify_batch_id=<id>) must return only
promos stamped with that batch id (the deep link from the expiry-reminder email).
Uses a blank Postgres schema, rolled back at teardown.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.marketing import Promotion
from app.services.marketing_service import PromotionService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


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
