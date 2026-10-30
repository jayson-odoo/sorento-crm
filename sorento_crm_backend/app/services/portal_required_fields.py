"""Fields a portal form must carry before it is SUBMITTED (FORM-REQUIRED-SERVER).

The same fields the portal form marks required: SubmissionForm.tsx `FIELDS`
(`required: true`), plus the complaint's "at least one product" that the form adds
in `collectMissingRequired` under the name ``product_lines``.
``tests/test_form_required_server.py`` fails if this list and the form drift apart.

A draft save is never checked; drafts may be incomplete. Contact-dependent
requirements (the sponsorship ``project_id``, AC-F4) and the sponsorship unit price
(#1227) keep their own checks in ``portal_service.submit_draft``. Project registration
has its own list (``project_registration_service.REQUIRED_ON_SUBMIT``). The external,
chatbot and MCP create paths keep their own, stricter contracts.
"""
from __future__ import annotations

from typing import Any

from app.services.error_handler import AppException

REQUIRED_ON_SUBMIT: dict[str, tuple[str, ...]] = {
    "stock_inquiry": ("salesperson_contact_id",),
    "complaint": (
        "delivery_order_number",
        "customer_name",
        "contact_person",
        "contact_number",
        "customer_type",
        "complaint_date",
        "within_warranty",
        "defects_discovered",
        "complaint_type",
        "defect_description",
        "salesperson",
        "product_lines",
    ),
    "purchase_request": ("requested_by_contact_id",),
    "sponsorship_form": ("requested_by_contact_id",),
}


def _filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def missing_on_submit(kind: str, row: Any, skip: tuple[str, ...] = ()) -> list[str]:
    """Required fields of `kind` still empty on `row`, in form order, minus `skip`."""
    missing: list[str] = []
    for name in REQUIRED_ON_SUBMIT.get(kind, ()):
        if name in skip:
            continue
        # Complaint product lines are rebuilt into the legacy `product_code` CSV
        # (`_replace_complaint_lines_if_needed`), which older clients also send flat.
        attr = "product_code" if name == "product_lines" else name
        if not _filled(getattr(row, attr, None)):
            missing.append(name)
    return missing


def require_complete(kind: str, row: Any, skip: tuple[str, ...] = ()) -> None:
    """422 naming every empty required field. Same body project registration answers
    with: `detail` is the comma-separated names, which the portal client reads into
    the error's `fields`. `skip` names fields the caller cannot let the contact change
    (a revise's frozen fields): demanding one would refuse with no way out."""
    missing = missing_on_submit(kind, row, skip)
    if missing:
        raise AppException(
            status_code=422,
            message="Fill in the required fields before submitting.",
            detail=",".join(missing),
            code="VALIDATION_ERROR",
        )
