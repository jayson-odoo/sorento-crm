"""S7b audit gate, defect 1 - the same validation rule must answer the SAME way on
CREATE and on UPDATE.

`PolicyCreate` carries its window-inversion check as a Pydantic `model_validator`
(`_window_is_not_inverted`); `update_policy` in `warranty_config_service.py` carries
the IDENTICAL rule as a hand-written `if` that raises `AppException`. A Pydantic
failure is caught by `app.main.validation_exception_handler` and rendered as
``{"detail": [{..., "msg": "Value error, <sentence>"}]}`` - literally the string
``"Value error, "`` glued onto the human sentence, because that prefix is Pydantic's
own `ValueError.__str__` framing, not anything this app wrote. An `AppException`
is rendered by `app.main.app_exception_handler` as ``{"message": <sentence>, ...}``
with no such prefix. Same rule, two shapes, two strings, depending only on the verb
the admin used to trigger it.

This file pins that a caller-facing rule answers identically regardless of verb:
same status code, same envelope shape (a `"message"` key carrying a clean string,
never a raw Pydantic `detail` array), same sentence, and never the substring
``"Value error"`` on either side.

Four rules are exercised, matching the UAC's validators one-for-one:
  - the effective window (`PolicyCreate._window_is_not_inverted` / the `if` in
    `update_policy`)
  - a blank/whitespace `version` (`PolicyCreate`/`PolicyUpdate._version_not_blank`)
  - a blank/whitespace `part_name` on a Term (`TermCreate`/`TermUpdate._part_not_blank`)
  - an unknown `match_type` on a Kind Rule (`KindRuleCreate`/`KindRuleUpdate._match_type`)

Whitespace-only values are used for "blank" rather than the empty string on fields
that also carry Pydantic's built-in `min_length=1` (`version`, `part_name`): an
empty string is refused by `min_length` BEFORE the app's own validator ever runs,
which would test Pydantic's stock message instead of this app's. A whitespace-only
string clears `min_length` and reaches the strip-and-check validator this app wrote.

Everything runs on Postgres via ``blank_session`` - never sqlite (PRINCIPLES.md).

Run: venv/bin/python -m pytest tests/test_warranty_config_error_envelope.py -q -p no:randomly
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app import database as app_database  # noqa: E402
from app.dependencies import get_current_user, get_current_user_or_api_key  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402
from app.models.warranty import WarrantyProductKind  # noqa: E402
from app.services.company_scope_resolver import apply_company_scope  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code  # noqa: E402

BASE = "/api/v1/warranty-management"
POLICIES = f"{BASE}/policies"
KINDS = f"{BASE}/kinds"
RULES = f"{BASE}/kind-rules"

P_ADD = "warranty.policies.add"
P_EDIT = "warranty.policies.edit"
K_ADD = "warranty.kinds.add"
K_EDIT = "warranty.kinds.edit"

SORENTO = "00000000-0000-0000-0000-000000000001"


# ----------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


@pytest.fixture
def client(db):
    """A logged-in principal scoped to Sorento; permissions come from `granted()`.

    Mirrors `tests/test_warranty_config_api.py`'s fixture exactly, so both files
    exercise the identical mechanism AC-P9 depends on.
    """
    holder = {"scope": frozenset({SORENTO})}

    def _override_db():
        yield db

    async def _override_scope():
        set_company_scope(db, holder["scope"])
        return holder["scope"]

    principal = {"id": str(uuid.uuid4()), "email": "warranty-gate@example.test"}
    app.dependency_overrides[app_database.get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        with TestClient(app) as c:
            yield c
    finally:
        for dep in (
            app_database.get_db,
            get_current_user,
            get_current_user_or_api_key,
            apply_company_scope,
        ):
            app.dependency_overrides.pop(dep, None)


from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def granted(*slugs: str):
    allowed = set(slugs)
    with patch("app.dependencies.UserPermissionService") as service:
        service.return_value.check_user_has_permission.side_effect = (
            lambda _user_id, slug: slug in allowed
        )
        service.return_value.get_user_role_slugs.return_value = set()
        yield


# ------------------------------------------------------------------- seed helpers


def _kind_row(db, stem: str) -> WarrantyProductKind:
    row = WarrantyProductKind(
        id=str(uuid.uuid4()),
        code=unique_code(stem)[:64],
        name=f"{TEST_PREFIX} {stem}"[:255],
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _policy_body(**overrides) -> dict:
    body = {
        "version": unique_code("V")[:32],
        "effective_from": "2026-01-01",
        "effective_to": None,
        "policy_text": f"{TEST_PREFIX} clause 17: residential installations only.",
    }
    body.update(overrides)
    return body


def _term_body(kind_id: str, **overrides) -> dict:
    body = {
        "kind_id": kind_id,
        "part_name": f"{TEST_PREFIX} Ceramic Body",
        "duration_months": 60,
        "is_lifetime": False,
        "installation_included": False,
        "registration_bonus_months": None,
        "covered_defect_type_ids": None,
    }
    body.update(overrides)
    return body


def _rule_body(kind_id: str, **overrides) -> dict:
    body = {
        "kind_id": kind_id,
        "match_type": "model_prefix",
        "match_value": "SRTWC",
        "priority": 0,
    }
    body.update(overrides)
    return body


def _create_policy(client, **overrides) -> dict:
    with granted(P_ADD):
        response = client.post(POLICIES, json=_policy_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _create_kind(client, **overrides) -> dict:
    with granted(K_ADD):
        response = client.post(KINDS, json=_kind_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _kind_body(**overrides) -> dict:
    body = {
        "code": unique_code("kind")[:64],
        "name": f"{TEST_PREFIX} Water Closet",
        "sort_order": 0,
        "is_active": True,
    }
    body.update(overrides)
    return body


def _create_term(client, policy_id: str, **overrides) -> dict:
    kind_id = overrides.pop("kind_id", None)
    if kind_id is None:
        kind_id = _create_kind(client)["id"]
    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{policy_id}/terms", json=_term_body(kind_id, **overrides)
        )
    assert response.status_code == 201, response.text
    return response.json()


def _create_rule(client, **overrides) -> dict:
    kind_id = overrides.pop("kind_id", None)
    if kind_id is None:
        kind_id = _create_kind(client)["id"]
    with granted(K_ADD):
        response = client.post(RULES, json=_rule_body(kind_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------- assertions


def _house_error_message(response) -> str:
    """The clean envelope every write-time refusal must carry: a top-level
    `"message"` string.

    `RequestValidationError`'s body has NO `"message"` key at all - only a
    `"detail"` list of Pydantic error objects - so calling this on a raw Pydantic
    failure fails loudly here, which is exactly the "different shape" half of
    defect 1.
    """
    body = response.json()
    assert isinstance(body, dict), f"Error body is not a JSON object: {body!r}"
    assert "message" in body, (
        "Expected the house AppException envelope (message/detail/code) on both "
        "verbs; got a raw validation-error body instead (no top-level 'message' "
        f"key): {body!r}"
    )
    message = body["message"]
    assert isinstance(message, str) and message.strip(), (
        f"'message' is missing or not a non-empty string: {body!r}"
    )
    return message


def _assert_same_clean_refusal(create_response, update_response) -> None:
    assert create_response.status_code == 422, create_response.text
    assert update_response.status_code == 422, update_response.text

    create_message = _house_error_message(create_response)
    update_message = _house_error_message(update_response)

    assert create_message == update_message, (
        "CREATE and UPDATE disagree on the human sentence for the identical rule:\n"
        f"  create: {create_message!r}\n"
        f"  update: {update_message!r}"
    )
    for label, message in (("create", create_message), ("update", update_message)):
        assert "value error" not in message.lower(), (
            f"The {label} error message leaks Pydantic's 'Value error' prefix "
            f"straight to the UI: {message!r}"
        )


# =============================================================================
# the effective window
# =============================================================================


def test_inverted_window_is_rejected_the_same_way_on_create_and_update(client):
    """`PolicyCreate._window_is_not_inverted` (Pydantic model_validator) vs the `if`
    in `update_policy` (service, AppException) - the headline example of defect 1.
    """
    baseline = _create_policy(
        client, effective_from="2026-03-01", effective_to="2026-06-30"
    )

    with granted(P_ADD):
        create_response = client.post(
            POLICIES,
            json=_policy_body(effective_from="2027-01-10", effective_to="2027-01-01"),
        )

    with granted(P_EDIT):
        update_response = client.patch(
            f"{POLICIES}/{baseline['id']}",
            json={"effective_to": "2026-01-01"},
        )

    _assert_same_clean_refusal(create_response, update_response)


# =============================================================================
# a blank version
# =============================================================================


def test_blank_version_is_rejected_the_same_way_on_create_and_update(client):
    """`min_length=1` alone would refuse "" before the app's own check ever runs, so
    a whitespace-only string is used to reach `_version_not_blank` on both schemas."""
    baseline = _create_policy(client)

    with granted(P_ADD):
        create_response = client.post(POLICIES, json=_policy_body(version="   "))

    with granted(P_EDIT):
        update_response = client.patch(
            f"{POLICIES}/{baseline['id']}", json={"version": "   "}
        )

    _assert_same_clean_refusal(create_response, update_response)


# =============================================================================
# a blank part_name on a term
# =============================================================================


def test_blank_part_name_is_rejected_the_same_way_on_create_and_update(client):
    policy = _create_policy(client)
    kind = _create_kind(client)
    baseline_term = _create_term(client, policy["id"], kind_id=kind["id"])

    with granted(P_ADD):
        create_response = client.post(
            f"{POLICIES}/{policy['id']}/terms",
            json=_term_body(kind["id"], part_name="   ", duration_months=12),
        )

    with granted(P_EDIT):
        update_response = client.patch(
            f"{POLICIES}/{policy['id']}/terms/{baseline_term['id']}",
            json={"part_name": "   "},
        )

    _assert_same_clean_refusal(create_response, update_response)


# =============================================================================
# an unknown match_type on a kind rule
# =============================================================================


def test_unknown_match_type_is_rejected_the_same_way_on_create_and_update(client):
    kind = _create_kind(client)
    baseline_rule = _create_rule(client, kind_id=kind["id"])

    with granted(K_ADD):
        create_response = client.post(
            RULES, json=_rule_body(kind["id"], match_type="not_a_real_match_type")
        )

    with granted(K_EDIT):
        update_response = client.patch(
            f"{RULES}/{baseline_rule['id']}",
            json={"match_type": "not_a_real_match_type"},
        )

    _assert_same_clean_refusal(create_response, update_response)
