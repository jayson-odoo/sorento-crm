"""The per-type "is revisions on" map the office detail pages read (round 6).

GET /api/v1/forms-management/revision-configs/enabled

The office Revisions TAB is decided by this one call, so the map has to answer
exactly what `PortalRevisionService.resolve_policy` would answer for a submission
of that type: the global kill switch, the per-type row, a missing row (fail
closed) and a zero cap all collapse into one boolean per type.

It is deliberately NOT admin-gated: every handler who can open a form has to be
able to see whether the tab exists, and the payload carries four booleans and
nothing else.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session
from tests._revision_harness import seed_config, seed_system_settings

URL = "/api/v1/forms-management/revision-configs/enabled"

# A handler, not an admin: the route must answer them the same way.
STAFF_USER = {
    "id": str(uuid.uuid4()),
    "email": "handler@example.test",
    "role": "user",
}


@pytest.fixture
def client():
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key

    with blank_session() as db:

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: STAFF_USER
        app.dependency_overrides[get_current_user_or_api_key] = lambda: STAFF_USER
        try:
            with patch("app.services.queue_service.enqueue_job", return_value=None):
                with TestClient(app) as c:
                    yield c, db
        finally:
            app.dependency_overrides.clear()


def _types(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()["types"]


def test_enabled_map_answers_a_non_admin_without_a_403(client):
    """The tab is decided for every handler, so the route carries no admin gate."""
    c, db = client
    seed_system_settings(db)
    seed_config(db, "stock_inquiry")

    response = c.get(URL)
    assert response.status_code == 200, response.text
    assert response.json()["types"]["stock_inquiry"] is True


def test_every_supported_type_is_named_even_when_it_has_no_row(client):
    """A missing config row means disabled (UAC A3, fail closed) - and the type is
    still named, so the caller never has to distinguish absent from false."""
    from app.services.portal_service import SUPPORTED_TYPES

    c, db = client
    seed_system_settings(db)
    seed_config(db, "stock_inquiry")

    types = _types(c.get(URL))
    assert set(types) == set(SUPPORTED_TYPES)
    assert types["stock_inquiry"] is True
    # No row at all.
    assert types["purchase_request"] is False


def test_the_global_kill_switch_turns_every_type_off(client):
    c, db = client
    seed_system_settings(db, enabled=False)
    seed_config(db, "stock_inquiry")
    seed_config(db, "purchase_request")

    assert set(_types(c.get(URL)).values()) == {False}


def test_a_disabled_type_is_false_while_its_siblings_stay_true(client):
    c, db = client
    seed_system_settings(db)
    seed_config(db, "stock_inquiry", is_enabled=False)
    seed_config(db, "purchase_request")
    seed_config(db, "sponsorship_form")

    types = _types(c.get(URL))
    assert types["stock_inquiry"] is False
    assert types["purchase_request"] is True
    assert types["sponsorship_form"] is True


def test_a_type_with_no_adapter_is_false_however_its_row_reads(client):
    """`complaint` ships an enabled-able config row but no revision adapter, and
    `resolve_policy` fails closed on it. The map has to agree, or the office gets
    a tab whose contact-side action can never exist."""
    c, db = client
    seed_system_settings(db)
    seed_config(db, "complaint", is_enabled=True)

    assert _types(c.get(URL))["complaint"] is False


def test_a_zero_cap_reads_as_off(client):
    """UAC A4: a cap of zero turns the type off whatever `is_enabled` says, and
    `resolve_policy` returns enabled=False for it. Same answer here."""
    c, db = client
    seed_system_settings(db, cap=5)
    seed_config(db, "stock_inquiry", max_revisions=0)

    assert _types(c.get(URL))["stock_inquiry"] is False


def test_the_map_matches_resolve_policy_for_a_real_submission(client):
    """One rule, one implementation: the map and the per-submission policy are the
    same derivation, so they can never disagree about whether the tab belongs."""
    from app.services.portal_revision_service import PortalRevisionService
    from tests._revision_harness import seed_contact, seed_entity

    c, db = client
    seed_system_settings(db)
    seed_config(db, "stock_inquiry")
    seed_config(db, "purchase_request", is_enabled=False)
    contact = seed_contact(db)
    row = seed_entity(db, "stock_inquiry", contact)

    service = PortalRevisionService(db)
    types = _types(c.get(URL))
    assert types["stock_inquiry"] == service.resolve_policy("stock_inquiry", row).enabled
    assert types["purchase_request"] is False
