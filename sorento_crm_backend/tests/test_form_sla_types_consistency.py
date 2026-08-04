"""The form-SLA type list must cover every type present in form_sla_configs.

Background: a `workflow_submission` config row was inserted on 2026-08-01 while
`source_entity_type` was still validated against a 5-value tuple that did not include
it. `GET /form-sla-config` declares `response_model=list[FormSLAConfigResponse]`, so
ONE illegal row failed validation for the WHOLE list and the endpoint 500'd. An
unhandled 500 bypasses CORSMiddleware, so the browser saw a missing
Access-Control-Allow-Origin header and reported "Failed to fetch" - the admin page
could never load, and the visible error named CORS rather than the real cause.

These tests pin the two things that let that happen:
  1. the schema tuple and the service tuple must not drift apart,
  2. no row in the live table may carry a type outside them.
"""
from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.schemas.sla import _FORM_SLA_TYPES
from app.services.form_sla_service import FORM_SLA_TYPES


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_schema_and_service_type_tuples_agree() -> None:
    """Two hardcoded copies of the same list is how they drifted in the first place.

    `FORM_SLA_TYPES` (service) gates routing and, more importantly,
    `conversation_tracking_scope()` - it is what tells a form stage row apart from a
    contact-keyed conversation row. `_FORM_SLA_TYPES` (schema) validates the API
    response. A type in one but not the other is a live bug in whichever direction it
    points.
    """
    assert set(FORM_SLA_TYPES) == set(_FORM_SLA_TYPES)


def test_workflow_submission_is_a_recognised_form_type() -> None:
    """It has had an active config row since 2026-08-01; the tuples must admit it."""
    assert "workflow_submission" in FORM_SLA_TYPES
    assert "workflow_submission" in _FORM_SLA_TYPES


def test_no_config_row_carries_an_unrecognised_type(db: Session) -> None:
    """Every row must serialize. One that cannot takes the whole endpoint down."""
    rows = db.execute(
        text("SELECT DISTINCT source_entity_type FROM form_sla_configs")
    ).fetchall()
    present = {r[0] for r in rows if r[0]}
    unknown = present - set(_FORM_SLA_TYPES)
    assert not unknown, (
        f"form_sla_configs holds source_entity_type(s) the response schema rejects: "
        f"{sorted(unknown)}. GET /form-sla-config will 500 for every caller."
    )


def test_every_live_config_row_serializes(db: Session) -> None:
    """Exercise the real serializer + response model against the real table."""
    from app.api.v1.sla.form_sla_config import _serialize
    from app.models.sla import FormSLAConfig
    from app.schemas.sla import FormSLAConfigResponse

    for config in db.query(FormSLAConfig).all():
        FormSLAConfigResponse.model_validate(_serialize(config))
