"""PromotionService.list_promotions attachment_state cleanup filter.

unlinked            -> promotion with no attachment linkages
linked_to_trashed   -> promotion linked to >=1 soft-deleted attachment
unlinked_or_trashed -> union (delete-candidate set)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

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


TODAY = datetime.utcnow().date()


def _promo(db, desc: str) -> str:
    p = Promotion(
        id=str(uuid.uuid4()),
        description=desc,
        start_date=TODAY - timedelta(days=5),
        end_date=TODAY + timedelta(days=30),
        is_active=True,
        access_levels=["dealer"],
    )
    db.add(p)
    db.flush()
    return p.id


def _att(db, *, is_deleted: bool) -> str:
    a = Attachment(
        id=str(uuid.uuid4()),
        original_filename="f.jpg",
        stored_filename="f.jpg",
        file_path="https://cdn-sorento.com/promotion/f.jpg",
        storage_provider="r2",
        access_levels=["dealer"],
        is_deleted=is_deleted,
    )
    db.add(a)
    db.flush()
    return a.id


def _link(db, promo_id: str, att_id: str) -> None:
    db.add(
        PromotionAttachment(
            id=str(uuid.uuid4()), promotion_id=promo_id, attachment_id=att_id
        )
    )
    db.flush()


@pytest.fixture
def seeded(db):
    # unlinked: no linkage rows
    unlinked = _promo(db, "UNLINKED")
    # healthy: linked to a live attachment
    healthy = _promo(db, "HEALTHY")
    _link(db, healthy, _att(db, is_deleted=False))
    # trashed: linked to a soft-deleted attachment
    trashed = _promo(db, "TRASHED")
    _link(db, trashed, _att(db, is_deleted=True))
    db.commit()
    return {"unlinked": unlinked, "healthy": healthy, "trashed": trashed}


def _ids(result):
    return {r.id for r in result["data"]}


def test_unlinked_only(db, seeded):
    res = PromotionService(db).list_promotions(attachment_state="unlinked")
    assert _ids(res) == {seeded["unlinked"]}


def test_linked_to_trashed_only(db, seeded):
    res = PromotionService(db).list_promotions(attachment_state="linked_to_trashed")
    assert _ids(res) == {seeded["trashed"]}


def test_unlinked_or_trashed_union(db, seeded):
    res = PromotionService(db).list_promotions(attachment_state="unlinked_or_trashed")
    assert _ids(res) == {seeded["unlinked"], seeded["trashed"]}


def test_no_filter_excludes_nothing_by_state(db, seeded):
    # Without the filter all three are returned (active-first; all are active).
    res = PromotionService(db).list_promotions(status="all")
    assert _ids(res) == set(seeded.values())
