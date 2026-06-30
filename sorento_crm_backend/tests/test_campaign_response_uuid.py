"""Bug A1 follow-on — MarketingCampaignResponse must accept UUID-typed fields.

A freshly-created campaign row holds `created_by` as a UUID object
(current_user["id"]) before any re-fetch. The str-typed response field would
raise ResponseValidationError without a UUID->str coercion. (Caught in browser
verification of the create flow.)
"""
import uuid
from datetime import datetime

from app.schemas.marketing import MarketingCampaignResponse


def test_response_coerces_uuid_fields_to_str():
    r = MarketingCampaignResponse(
        id=uuid.uuid4(),
        campaign_code="X",
        campaign_name="X",
        campaign_type_id=uuid.uuid4(),
        start_date=datetime(2026, 1, 1),
        status="planning",
        created_by=uuid.uuid4(),
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    assert isinstance(r.id, str)
    assert isinstance(r.campaign_type_id, str)
    assert isinstance(r.created_by, str)


def test_response_created_by_none_ok():
    r = MarketingCampaignResponse(
        id=uuid.uuid4(),
        campaign_code="X",
        campaign_name="X",
        campaign_type_id=uuid.uuid4(),
        start_date=datetime(2026, 1, 1),
        status="planning",
        created_by=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    assert r.created_by is None
