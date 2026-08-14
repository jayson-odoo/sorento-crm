"""The PR/SF list response must carry `revision_no`.

`response_model` strips any field the schema does not declare. When
`PurchaseRequestHeaderListResponse` omitted `revision_no`, three things broke at
once on purchase requests and sponsorship forms: the "Rev N" badge never
rendered, the -R{n} display suffix never rendered, and - the part that matters -
the frontend revision-fence registry harvested nothing from list rows, so a row
action taken without ever opening the detail page went through UNFENCED.

Stock inquiry never had the bug because it reuses one schema for list and detail.
This is a contract test, not a behaviour test: it asserts the field survives
serialization, which is exactly what a manual round of testing would miss.
"""
from datetime import datetime

from app.schemas.procurement import (
    PurchaseRequestHeaderListResponse,
    PurchaseRequestHeaderResponse,
)


def test_pr_list_response_declares_revision_fields():
    fields = PurchaseRequestHeaderListResponse.model_fields
    assert "revision_no" in fields, (
        "PurchaseRequestHeaderListResponse must declare revision_no or "
        "response_model strips it, silently unfencing PR/SF row actions."
    )
    assert "last_revised_at" in fields


def test_pr_list_response_keeps_revision_no_through_serialization():
    row = PurchaseRequestHeaderListResponse(
        id="00000000-0000-0000-0000-000000000001",
        request_type="purchase_request",
        request_number="PR26-0332",
        revision_no=2,
        last_revised_at=datetime(2026, 8, 10, 9, 14, 0),
    )
    dumped = row.model_dump()
    assert dumped["revision_no"] == 2
    assert dumped["last_revised_at"] == datetime(2026, 8, 10, 9, 14, 0)


def test_pr_list_and_detail_agree_on_revision_fields():
    """Detail already carried these; list must not drift away from it again."""
    for name in ("revision_no", "last_revised_at"):
        assert name in PurchaseRequestHeaderResponse.model_fields
        assert name in PurchaseRequestHeaderListResponse.model_fields


def test_revision_no_defaults_to_none_not_missing():
    """A row that predates the feature serializes cleanly rather than raising."""
    row = PurchaseRequestHeaderListResponse(
        id="00000000-0000-0000-0000-000000000002",
        request_type="sponsorship_form",
    )
    assert row.model_dump()["revision_no"] is None
