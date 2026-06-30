"""Bug A5 — campaign status is canonicalised to LOWERCASE + enum-validated.

The DB CHECK constraint `marketing_campaigns_status_check` only allows lowercase
(planning/active/completed/cancelled). The create/update schema must coerce
incoming status to lowercase and reject values outside the enum, so stored data
satisfies the constraint + agrees with the FE badge/filter maps.
"""
import pytest
from pydantic import ValidationError

from app.schemas.marketing import MarketingCampaignCreate, MarketingCampaignUpdate


def _create(**over):
    base = dict(
        campaign_code="C1",
        campaign_name="Spring",
        campaign_type_id="t1",
        start_date="2026-01-01T00:00:00",
    )
    base.update(over)
    return MarketingCampaignCreate(**base)


def test_create_uppercase_coerced_to_lowercase():
    # DB CHECK constraint only allows lowercase — normalise to that.
    assert _create(status="PLANNING").status == "planning"
    assert _create(status="Active").status == "active"


def test_create_default_is_valid_lowercase():
    assert _create().status == "planning"


def test_create_rejects_unknown_status():
    with pytest.raises(ValidationError):
        _create(status="bogus")


def test_update_none_passthrough():
    assert MarketingCampaignUpdate(status=None).status is None
    assert MarketingCampaignUpdate().status is None


def test_update_uppercase_coerced():
    assert MarketingCampaignUpdate(status="COMPLETED").status == "completed"


def test_update_rejects_unknown():
    with pytest.raises(ValidationError):
        MarketingCampaignUpdate(status="nope")
