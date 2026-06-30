"""Bug A5 — campaign list status filter must actually filter (uppercase-normalized).

Previously `list_campaigns(page, limit)` ignored status entirely → the FE filter
was dead. Now it accepts an optional `status`, normalised to UPPERCASE so a
lowercase FE value still matches stored uppercase rows.
"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.marketing import MarketingCampaign
from app.models.lookup import LookupBinding
from app.services.marketing_service import MarketingCampaignService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # LookupBinding table required even though unused here: a globally-registered
    # SQLAlchemy write-listener (lookup_write_listener) fires on inserts when the
    # full suite runs and queries lookup_bindings. (See CLAUDE.md sqlite gotcha.)
    Base.metadata.create_all(
        engine, tables=[MarketingCampaign.__table__, LookupBinding.__table__]
    )
    session = sessionmaker(bind=engine)()

    def _camp(code, status):
        return MarketingCampaign(
            id=str(uuid.uuid4()),
            campaign_code=code,
            campaign_name=code,
            campaign_type_id=str(uuid.uuid4()),
            start_date=datetime(2026, 1, 1),
            status=status,
        )

    session.add_all([_camp("A", "planning"), _camp("B", "active"), _camp("C", "planning")])
    session.commit()
    yield session
    session.close()


def test_no_status_returns_all(db):
    res = MarketingCampaignService(db).list_campaigns(page=1, limit=50)
    assert res["pagination"]["total"] == 3


def test_status_filter_lowercase(db):
    res = MarketingCampaignService(db).list_campaigns(page=1, limit=50, status="planning")
    assert res["pagination"]["total"] == 2
    assert all(c.status == "planning" for c in res["data"])


def test_status_filter_uppercase_input_still_matches(db):
    # FE may send any case; service normalises to lowercase to match the DB.
    res = MarketingCampaignService(db).list_campaigns(page=1, limit=50, status="ACTIVE")
    assert res["pagination"]["total"] == 1
    assert res["data"][0].campaign_code == "B"


def test_status_all_is_noop(db):
    res = MarketingCampaignService(db).list_campaigns(page=1, limit=50, status="all")
    assert res["pagination"]["total"] == 3
