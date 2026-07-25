"""Bug A5 — campaign list status filter must actually filter (uppercase-normalized).

Previously `list_campaigns(page, limit)` ignored status entirely → the FE filter
was dead. Now it accepts an optional `status`, normalised to UPPERCASE so a
lowercase FE value still matches stored uppercase rows.
"""
import uuid
from datetime import datetime

import pytest

from app.models.marketing import CampaignType, MarketingCampaign
from app.services.marketing_service import MarketingCampaignService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield from _seeded(session)


def _seeded(session):
    # A real campaign type: campaign_type_id is a FK, which Postgres enforces
    # and sqlite did not, so a made-up uuid per row is no longer acceptable.
    camp_type = CampaignType(
        id=str(uuid.uuid4()), type_code="ZZT-PROMO", type_name="ZZT Promo"
    )
    session.add(camp_type)
    session.flush()

    def _camp(code, status):
        return MarketingCampaign(
            id=str(uuid.uuid4()),
            campaign_code=code,
            campaign_name=code,
            campaign_type_id=camp_type.id,
            start_date=datetime(2026, 1, 1),
            status=status,
        )

    session.add_all([_camp("A", "planning"), _camp("B", "active"), _camp("C", "planning")])
    session.commit()
    yield session


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
