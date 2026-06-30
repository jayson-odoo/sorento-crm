"""C1 — marketing DELETE was a no-op stub (returned success, deleted nothing).

`delete_campaign` / `delete_campaign_type` now hard-delete per the ADR standard.
Deleting a campaign type still referenced by a campaign is blocked with 409
(the `marketing_campaigns.campaign_type_id` FK is NOT NULL — cascading would
silently break those campaigns).
"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.marketing import MarketingCampaign, CampaignType
from app.models.lookup import LookupBinding
from app.services.marketing_service import (
    MarketingCampaignService,
    CampaignTypeService,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # LookupBinding required: a globally-registered write-listener queries it on
    # inserts when the full suite runs (CLAUDE.md sqlite gotcha).
    Base.metadata.create_all(
        engine,
        tables=[
            MarketingCampaign.__table__,
            CampaignType.__table__,
            LookupBinding.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _type(db, code="EMAIL"):
    t = CampaignType(id=str(uuid.uuid4()), type_code=code, type_name=code)
    db.add(t)
    db.commit()
    return t


def _campaign(db, type_id, code="A"):
    c = MarketingCampaign(
        id=str(uuid.uuid4()),
        campaign_code=code,
        campaign_name=code,
        campaign_type_id=type_id,
        start_date=datetime(2026, 1, 1),
        status="planning",
    )
    db.add(c)
    db.commit()
    return c


def test_delete_campaign_actually_removes_row(db):
    t = _type(db)
    c = _campaign(db, t.id)
    res = MarketingCampaignService(db).delete_campaign(c.id)
    assert "deleted successfully" in res["message"]
    assert db.query(MarketingCampaign).filter_by(id=c.id).first() is None


def test_delete_campaign_missing_raises(db):
    with pytest.raises(Exception):
        MarketingCampaignService(db).delete_campaign(str(uuid.uuid4()))


def test_delete_unused_campaign_type_removes_row(db):
    t = _type(db)
    res = CampaignTypeService(db).delete_campaign_type(t.id)
    assert "deleted successfully" in res["message"]
    assert db.query(CampaignType).filter_by(id=t.id).first() is None


def test_delete_in_use_campaign_type_blocked_409(db):
    t = _type(db)
    _campaign(db, t.id)
    with pytest.raises(Exception) as exc:
        CampaignTypeService(db).delete_campaign_type(t.id)
    # AppException carries a 409 status + "in use" message.
    assert "in use" in str(getattr(exc.value, "detail", exc.value)).lower()
    # Type must still exist (delete refused).
    assert db.query(CampaignType).filter_by(id=t.id).first() is not None


def test_delete_missing_campaign_type_raises(db):
    with pytest.raises(Exception):
        CampaignTypeService(db).delete_campaign_type(str(uuid.uuid4()))
