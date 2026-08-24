"""
n8n callback v1 schema validation tests.

Covers IntegrationLogUpdateRequest validator behaviour:
 - v1 payload (schema_version=1) → strict validation, malformed → 422 / ValueError
 - legacy free-form payload (no schema_version) → accepted with deprecation log
 - non-JSON payload → rejected
See app/schemas/integration.py and docs/plans/PLAN-upload-activity-drawer.md §4.4.
"""
import json

import pytest

from app.schemas.integration import (
    IntegrationLogUpdateRequest,
    N8nCallbackPayloadV1,
)


def test_v1_payload_accepted_and_serialised():
    payload = {
        "schema_version": 1,
        "outcome": "linked",
        "summary": "Linked to 1 product",
        "linked": [
            {
                "entity_type": "product",
                "entity_id": "p1",
                "display_name": "CBMC5570",
                "matched_by": "filename_token",
            }
        ],
        "unlinked_reasons": [],
        "errors": [],
    }
    req = IntegrationLogUpdateRequest(status="success", response_payload=payload)
    assert req.response_payload is not None
    parsed = json.loads(req.response_payload)
    assert parsed["schema_version"] == 1
    assert parsed["outcome"] == "linked"


def test_v1_payload_partial_outcome_supported():
    """outcome=partial is the mixed-result case (some linked, some unlinked)."""
    payload = {
        "schema_version": 1,
        "outcome": "partial",
        "summary": "1 linked, 1 unlinked",
        "linked": [
            {
                "entity_type": "product",
                "entity_id": "p1",
                "display_name": "CBMC5570",
                "matched_by": "filename_token",
            }
        ],
        "unlinked_reasons": [{"reason": "Token CBFAL9999 not found"}],
        "errors": [],
    }
    req = IntegrationLogUpdateRequest(status="success", response_payload=payload)
    assert json.loads(req.response_payload)["outcome"] == "partial"


def test_v1_payload_invalid_outcome_rejected():
    bad = {"schema_version": 1, "outcome": "not-an-outcome", "summary": "x"}
    with pytest.raises(Exception):  # noqa: PT011 - pydantic ValidationError or ValueError
        IntegrationLogUpdateRequest(status="success", response_payload=bad)


def test_v1_payload_missing_summary_rejected():
    bad = {"schema_version": 1, "outcome": "linked"}  # no summary
    with pytest.raises(Exception):  # noqa: PT011
        IntegrationLogUpdateRequest(status="success", response_payload=bad)


def test_legacy_payload_accepted(caplog):
    """No schema_version → legacy mode, accepted with deprecation log."""
    caplog.clear()
    with caplog.at_level("WARNING"):
        req = IntegrationLogUpdateRequest(
            status="success",
            response_payload={"some": "free-form"},
        )
    assert "schema_version" in caplog.text
    assert json.loads(req.response_payload) == {"some": "free-form"}


def test_invalid_json_string_rejected():
    with pytest.raises(Exception):  # noqa: PT011
        IntegrationLogUpdateRequest(status="failed", response_payload="not json")


def test_v1_schema_model_direct_validation():
    """Bare schema validation also works (used by upload_activity endpoint reader)."""
    model = N8nCallbackPayloadV1(
        schema_version=1,
        outcome="unlinked",
        summary="no match",
        linked=[],
        unlinked_reasons=[{"reason": "x"}],
        errors=[],
    )
    assert model.outcome == "unlinked"
