"""S7b audit gate, round 2 - five gaps the implementer's own brief flagged as
uncovered by `test_warranty_config_error_envelope.py` and
`test_warranty_config_response_contract.py`. Both of those pass today; this file
targets what they do not.

**Gap A.** `TermResponse.created_at` and `KindRuleResponse.created_at` are still
declared `Optional[datetime] = None` in `app/schemas/warranty_config.py`, exactly
the lie `PolicyResponse.created_at` carried before it was fixed. The columns behind
them (`warranty_terms.created_at`, `warranty_kind_rules.created_at`) are
`nullable=False, server_default=now()`. Pins the DECLARATION (`model_fields`, same
technique `test_warranty_config_response_contract.py` uses for the policy) and the
runtime value, for both entities. `updated_at` on both is genuinely nullable in the
model, so it is deliberately left alone here - asserting it non-optional would be
gating a fact that is not true.

**Gap B.** `KindCreate` / `KindUpdate` still carry `_not_blank` as Pydantic
`field_validator`s on `code` and `name` (with `min_length=1`), so
`POST /kinds` and `PATCH /kinds/{id}` with a whitespace-only value still raise a raw
`RequestValidationError` - `{"detail":[{"msg":"Value error, This field is
required."}]}` - while every other rule in this module answers through the house
`AppException` envelope. Gated exactly the way
`test_warranty_config_error_envelope.py` gates the other four rules: same status,
same top-level `message`, same sentence on create and update, never the substring
"value error". A whitespace-only string is used rather than `""`, because
`min_length=1` would refuse `""` before the app's own rule runs and the test would
pin Pydantic's stock message instead of this app's.

**Gap C.** The `_required_text` / `_validated_match_type` family *returns* the
cleaned value and every write path (verified by reading this module) already
writes that cleaned value back - but nothing pins it. A future refactor that
returns the cleaned value without writing it back (or drops the strip entirely)
would stay green against every test that exists today: the create/update response
echoes whatever was written, right or wrong, and no test re-reads the row. Pinned
here by reading the value back through a SEPARATE endpoint (a GET / list call, not
the write response) after both create and update, for:
  - policy `version`
  - kind rule `match_type` (also case-folded)
  - term `part_name`
  - kind `code` / `name`

**Gap D.** Several `*Update` schemas declare a NOT NULL column as `Optional`, and
the corresponding service method writes `changes[field]` straight onto the row with
`setattr` when the caller sends an explicit JSON `null` - no re-validation of the
already-computed value, because the validation that DOES run reads a *coerced*
local variable while the raw `None` sails through in `changes`. Postgres's own NOT
NULL constraint then raises `IntegrityError` at `commit()`, which is not an
`AppException`, so it falls to `app.main.global_exception_handler` and comes back
as ``{"message": "Internal server error"}`` with status 500 - a crash, not a
refusal. Confirmed by direct probe against this branch (see PR description) for:
  - `PATCH /kind-rules/{id}` `{"priority": null}` (`warranty_kind_rules.priority`
    is NOT NULL)
  - `PATCH /policies/{id}` `{"effective_from": null}` (NOT NULL - the model's own
    docstring calls this column out by name)
  - `PATCH /policies/{id}/terms/{id}` `{"is_lifetime": null}` and
    `{"installation_included": null}` (both NOT NULL; `installation_included` is
    the other column the model docstring calls out by name)
  - `PATCH /kinds/{id}` `{"code": null}`, `{"name": null}` and `{"sort_order":
    null}` - the existing `_not_blank` validator on `KindUpdate` explicitly
    special-cases `None` (`if value is None: return None`), which lets an explicit
    null sail past the one guard that exists
`PATCH /kind-rules/{id}` `{"match_type": null}` is ALSO pinned, as a positive
control: `_validated_match_type` calls `(value or "").strip().lower()`, which
already treats `None` the same as blank and answers a clean 422 today. Confirmed
by the same probe. It is included so a regression in this exact shape - the one
the brief called out by name - is caught even though it is not currently broken.

**Gap E.** `supersede_policy` takes the same `PolicyCreate` payload as `create_policy`
and, by inspection, already calls `_required_text` and `_assert_window_not_inverted`
before mutating anything. This file pins that it stays that way: a blank/whitespace
`version` and an inverted effective window on supersede both answer the identical
sentence create and update use, AND - the part no other test checks - the incumbent
policy is NOT closed when either refusal fires (AC-P2a / AC-P21). Confirmed by
direct probe: both refusals currently leave `effective_to` on the incumbent at
`None`. Pinned here as a regression guard, not because it is broken today.

Everything runs on Postgres via ``blank_session`` - never sqlite (PRINCIPLES.md).
Every seeded row uses `unique_code()` / the `ZZT` prefix and lives inside a rolled
back transaction; nothing here can leak into the shared database.

Run: venv/bin/python -m pytest tests/test_warranty_config_audit_round2.py -q -p no:randomly
"""
from __future__ import annotations

import typing
import uuid
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app import database as app_database  # noqa: E402
from app.dependencies import get_current_user, get_current_user_or_api_key  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402
from app.schemas.warranty_config import KindRuleResponse, TermResponse  # noqa: E402
from app.services.company_scope_resolver import apply_company_scope  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code  # noqa: E402

BASE = "/api/v1/warranty-management"
POLICIES = f"{BASE}/policies"
KINDS = f"{BASE}/kinds"
RULES = f"{BASE}/kind-rules"

P_VIEW = "warranty.policies.view"
P_ADD = "warranty.policies.add"
P_EDIT = "warranty.policies.edit"
K_VIEW = "warranty.kinds.view"
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
    """Mirrors `test_warranty_config_error_envelope.py`'s fixture exactly."""
    holder = {"scope": frozenset({SORENTO})}

    def _override_db():
        yield db

    async def _override_scope():
        set_company_scope(db, holder["scope"])
        return holder["scope"]

    principal = {"id": str(uuid.uuid4()), "email": "warranty-gate-2@example.test"}
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


def _policy_body(**overrides) -> dict:
    body = {
        "version": unique_code("V")[:32],
        "effective_from": "2026-01-01",
        "effective_to": None,
        "policy_text": f"{TEST_PREFIX} clause 17: residential installations only.",
    }
    body.update(overrides)
    return body


def _kind_body(**overrides) -> dict:
    body = {
        "code": unique_code("kind")[:64],
        "name": f"{TEST_PREFIX} Water Closet",
        "sort_order": 0,
        "is_active": True,
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
    """The clean envelope every write-time refusal must carry.

    Fails loudly (and correctly) on either of the two ways a caller can fall
    outside this shape: a raw `RequestValidationError` body (`detail` list, no
    top-level `message`) or a raw 500 (`{"message": "Internal server error"}` -
    which DOES have a `message` key, so the caller of this helper must also check
    `status_code == 422` separately; this helper only checks the shape, not the
    code).
    """
    body = response.json()
    assert isinstance(body, dict), f"Error body is not a JSON object: {body!r}"
    assert "message" in body, (
        "Expected the house AppException envelope (message/detail/code); got a "
        f"body with no top-level 'message' key: {body!r}"
    )
    message = body["message"]
    assert isinstance(message, str) and message.strip(), (
        f"'message' is missing or not a non-empty string: {body!r}"
    )
    return message


def _assert_clean_422(response, *, forbidden_substrings=("value error", "internal server error")):
    """The full shape a caller-facing refusal must have: 422, house envelope,
    never a leaked Pydantic prefix, never the generic crash message."""
    assert response.status_code == 422, (
        f"Expected a clean 422 refusal, got {response.status_code}: {response.text}"
    )
    message = _house_error_message(response)
    lowered = message.lower()
    for forbidden in forbidden_substrings:
        assert forbidden not in lowered, (
            f"Refusal message leaks '{forbidden}': {message!r}"
        )
    return message


def _assert_same_clean_refusal(create_response, update_response) -> str:
    create_message = _assert_clean_422(create_response)
    update_message = _assert_clean_422(update_response)
    assert create_message == update_message, (
        "CREATE and UPDATE disagree on the human sentence for the identical rule:\n"
        f"  create: {create_message!r}\n"
        f"  update: {update_message!r}"
    )
    return create_message


# =============================================================================
# Gap A - TermResponse / KindRuleResponse created_at declared Optional
# =============================================================================


def _assert_created_at_required_and_not_optional(schema_cls, label: str) -> None:
    field_info = schema_cls.model_fields["created_at"]
    assert field_info.is_required(), (
        f"{label}.created_at carries a default (`= None`), so a caller "
        "constructing this schema without the field is accepted. The column "
        "behind it is `nullable=False, server_default=now()` - the field must be "
        "required, matching the column it represents."
    )
    origin = typing.get_origin(field_info.annotation)
    args = typing.get_args(field_info.annotation)
    is_optional = origin in (typing.Union, getattr(__import__("types"), "UnionType", object())) and type(None) in args
    assert not is_optional, (
        f"{label}.created_at is declared Optional ({field_info.annotation!r}) but "
        "the column is NOT NULL with a server default - the declared type lies to "
        "every consumer of this schema."
    )


def test_term_response_declares_created_at_as_required_and_not_optional():
    """`warranty_terms.created_at` is `nullable=False, server_default=now()`
    (app/models/warranty.py) - `TermResponse` must say the same, the way
    `PolicyResponse` already does after its own fix."""
    _assert_created_at_required_and_not_optional(TermResponse, "TermResponse")


def test_kind_rule_response_declares_created_at_as_required_and_not_optional():
    """`warranty_kind_rules.created_at` is `nullable=False, server_default=now()`
    (app/models/warranty.py) - `KindRuleResponse` must say the same."""
    _assert_created_at_required_and_not_optional(KindRuleResponse, "KindRuleResponse")


def test_a_freshly_created_term_carries_a_non_null_created_at(client):
    term = _create_term(client, _create_policy(client)["id"])
    assert term.get("created_at"), (
        f"TermResponse.created_at came back null/missing on a freshly created "
        f"row: {term!r}"
    )
    datetime.fromisoformat(term["created_at"].replace("Z", "+00:00"))


def test_a_freshly_created_kind_rule_carries_a_non_null_created_at(client):
    rule = _create_rule(client)
    assert rule.get("created_at"), (
        f"KindRuleResponse.created_at came back null/missing on a freshly "
        f"created row: {rule!r}"
    )
    datetime.fromisoformat(rule["created_at"].replace("Z", "+00:00"))


# =============================================================================
# Gap B - blank kind code / name still leaks the raw Pydantic envelope
# =============================================================================


def test_blank_kind_code_is_rejected_the_same_way_on_create_and_update(client):
    """`KindCreate`/`KindUpdate._not_blank` are still Pydantic `field_validator`s -
    the same disease `test_warranty_config_error_envelope.py` gates on Policy/Term/
    KindRule, one route this repo's first audit round never touched.

    Whitespace-only, not `""`: `min_length=1` would refuse `""` before this app's
    own rule ever runs.
    """
    baseline = _create_kind(client)

    with granted(K_ADD):
        create_response = client.post(KINDS, json=_kind_body(code="   "))
    with granted(K_EDIT):
        update_response = client.patch(
            f"{KINDS}/{baseline['id']}", json={"code": "   "}
        )

    _assert_same_clean_refusal(create_response, update_response)


def test_blank_kind_name_is_rejected_the_same_way_on_create_and_update(client):
    baseline = _create_kind(client)

    with granted(K_ADD):
        create_response = client.post(KINDS, json=_kind_body(name="   "))
    with granted(K_EDIT):
        update_response = client.patch(
            f"{KINDS}/{baseline['id']}", json={"name": "   "}
        )

    _assert_same_clean_refusal(create_response, update_response)


# =============================================================================
# Gap C - the CLEANED value, not just the raw one, must be what gets stored
# =============================================================================


def test_policy_version_is_stored_stripped_on_both_create_and_update(client):
    raw_create = f" {unique_code('V')[:20]} "
    created = _create_policy(client, version=raw_create)
    assert created["version"] == raw_create.strip(), created

    with granted(P_VIEW):
        fetched = client.get(f"{POLICIES}/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["version"] == raw_create.strip(), (
        "A fresh GET disagrees with the write response about the stored version - "
        f"the raw untrimmed value may have been what actually persisted: {fetched.json()!r}"
    )

    raw_update = f" {unique_code('V2')[:18]} "
    with granted(P_EDIT):
        updated = client.patch(f"{POLICIES}/{created['id']}", json={"version": raw_update})
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == raw_update.strip(), updated.json()

    with granted(P_VIEW):
        refetched = client.get(f"{POLICIES}/{created['id']}")
    assert refetched.json()["version"] == raw_update.strip(), (
        f"PATCH's own response was clean but the STORED value was not: {refetched.json()!r}"
    )


def test_kind_rule_match_type_is_stored_case_folded_on_both_create_and_update(client):
    kind = _create_kind(client)
    created = _create_rule(client, kind_id=kind["id"], match_type="MODEL_PREFIX")
    assert created["match_type"] == "model_prefix", created

    with granted(K_VIEW):
        listed = client.get(RULES, params={"kind_id": kind["id"]})
    assert listed.status_code == 200, listed.text
    row = next(r for r in listed.json() if r["id"] == created["id"])
    assert row["match_type"] == "model_prefix", (
        f"A fresh list-read disagrees with the write response: {row!r}"
    )

    with granted(K_EDIT):
        updated = client.patch(
            f"{RULES}/{created['id']}", json={"match_type": "CATEGORY"}
        )
    assert updated.status_code == 200, updated.text
    assert updated.json()["match_type"] == "category", updated.json()

    with granted(K_VIEW):
        relisted = client.get(RULES, params={"kind_id": kind["id"]})
    row = next(r for r in relisted.json() if r["id"] == created["id"])
    assert row["match_type"] == "category", (
        f"PATCH's own response was clean but the STORED value was not: {row!r}"
    )


def test_term_part_name_is_stored_stripped_on_both_create_and_update(client):
    policy = _create_policy(client)
    kind = _create_kind(client)
    created = _create_term(
        client, policy["id"], kind_id=kind["id"], part_name="  Ceramic Body  "
    )
    assert created["part_name"] == "Ceramic Body", created

    with granted(P_VIEW):
        listed = client.get(f"{POLICIES}/{policy['id']}/terms")
    assert listed.status_code == 200, listed.text
    row = next(r for r in listed.json() if r["id"] == created["id"])
    assert row["part_name"] == "Ceramic Body", (
        f"A fresh list-read disagrees with the write response: {row!r}"
    )

    with granted(P_EDIT):
        updated = client.patch(
            f"{POLICIES}/{policy['id']}/terms/{created['id']}",
            json={"part_name": "  New Part  "},
        )
    assert updated.status_code == 200, updated.text
    assert updated.json()["part_name"] == "New Part", updated.json()

    with granted(P_VIEW):
        relisted = client.get(f"{POLICIES}/{policy['id']}/terms")
    row = next(r for r in relisted.json() if r["id"] == created["id"])
    assert row["part_name"] == "New Part", (
        f"PATCH's own response was clean but the STORED value was not: {row!r}"
    )


def test_kind_code_and_name_are_stored_stripped_on_both_create_and_update(client):
    raw_code = f"  {unique_code('c')[:20]}  "
    created = _create_kind(client, code=raw_code, name="  My Name  ")
    assert created["code"] == raw_code.strip(), created
    assert created["name"] == "My Name", created

    with granted(K_VIEW):
        listed = client.get(KINDS, params={"query": raw_code.strip()})
    assert listed.status_code == 200, listed.text
    row = next(r for r in listed.json() if r["id"] == created["id"])
    assert row["code"] == raw_code.strip(), (
        f"A fresh list-read disagrees with the write response: {row!r}"
    )
    assert row["name"] == "My Name", row

    raw_code_2 = f"  {unique_code('c2')[:18]}  "
    with granted(K_EDIT):
        updated = client.patch(
            f"{KINDS}/{created['id']}", json={"code": raw_code_2, "name": "  New Name  "}
        )
    assert updated.status_code == 200, updated.text
    assert updated.json()["code"] == raw_code_2.strip(), updated.json()
    assert updated.json()["name"] == "New Name", updated.json()

    with granted(K_VIEW):
        relisted = client.get(KINDS, params={"query": raw_code_2.strip()})
    row = next(r for r in relisted.json() if r["id"] == created["id"])
    assert row["code"] == raw_code_2.strip(), (
        f"PATCH's own response was clean but the STORED value was not: {row!r}"
    )
    assert row["name"] == "New Name", row


# =============================================================================
# Gap D - an explicit PATCH null onto a NOT NULL column must be a clean 422,
# never an IntegrityError surfacing as a 500
# =============================================================================


def test_patch_kind_rule_explicit_null_match_type_is_a_clean_422(client):
    """Positive control: `_validated_match_type` already treats `None` the same
    as blank (`(value or "").strip().lower()`), so this already answers a clean
    422 today. Pinned anyway - it is the exact shape the brief named, and a future
    change to that helper's `None`-handling should not silently reopen it."""
    rule = _create_rule(client)
    with granted(K_EDIT):
        response = client.patch(f"{RULES}/{rule['id']}", json={"match_type": None})
    _assert_clean_422(response)


def test_patch_kind_rule_explicit_null_priority_is_a_clean_422(client):
    """`warranty_kind_rules.priority` is `nullable=False`. `KindRuleUpdate.priority`
    is `Optional[int]`, and `update_kind_rule` never validates it before `setattr` -
    an explicit `null` sails straight through to `db.commit()` and raises
    `IntegrityError`, which is not an `AppException` and lands in
    `global_exception_handler` as a 500."""
    rule = _create_rule(client)
    with granted(K_EDIT):
        response = client.patch(f"{RULES}/{rule['id']}", json={"priority": None})
    _assert_clean_422(response)


def test_patch_policy_explicit_null_effective_from_is_a_clean_422(client):
    """`warranty_policies.effective_from` is `nullable=False` - the model's own
    docstring calls this out: "A policy with no start date cannot be 'in force on
    the purchase date' at all". `update_policy` reads `changes.get("effective_from",
    policy.effective_from)`, which returns the explicit `None` (the key IS present),
    then `_assert_window_not_inverted` short-circuits on `effective_from is None`
    and never refuses it. It never even reaches Postgres's NOT NULL constraint:
    `_assert_no_overlap` -> `_overlapping_policy` builds
    `WarrantyPolicy.effective_to >= effective_from` with `effective_from=None`,
    and SQLAlchemy refuses `column >= None` outright with
    `sqlalchemy.exc.ArgumentError: Only '=', '!=', 'is_()', ... can be used with
    None` - an even earlier, uncaught crash than the NOT NULL violation the other
    columns in this section hit at `commit()`."""
    policy = _create_policy(client)
    with granted(P_EDIT):
        response = client.patch(
            f"{POLICIES}/{policy['id']}", json={"effective_from": None}
        )
    _assert_clean_422(response)


def test_patch_term_explicit_null_is_lifetime_is_a_clean_422(client):
    """`warranty_terms.is_lifetime` is `nullable=False`. `update_term` computes a
    LOCAL `is_lifetime = bool(changes["is_lifetime"] if ... else term.is_lifetime)`
    for `_assert_term_shape` - `bool(None)` coerces to `False`, so the shape check
    passes using a value that is not what actually gets written. The final
    `for field, value in changes.items(): setattr(term, field, value)` loop writes
    the RAW `None` from `changes`, not the coerced local, straight past every
    guard."""
    policy = _create_policy(client)
    term = _create_term(client, policy["id"])
    with granted(P_EDIT):
        response = client.patch(
            f"{POLICIES}/{policy['id']}/terms/{term['id']}",
            json={"is_lifetime": None},
        )
    _assert_clean_422(response)


def test_patch_term_explicit_null_installation_included_is_a_clean_422(client):
    """`warranty_terms.installation_included` is `nullable=False` - the model's own
    docstring calls this out by name: "A null would be rendered as 'no' by every
    consumer of it and nobody would ever notice." `update_term` has no validation
    on this field at all before `setattr`."""
    policy = _create_policy(client)
    term = _create_term(client, policy["id"])
    with granted(P_EDIT):
        response = client.patch(
            f"{POLICIES}/{policy['id']}/terms/{term['id']}",
            json={"installation_included": None},
        )
    _assert_clean_422(response)


def test_patch_kind_explicit_null_code_is_a_clean_422(client):
    """`warranty_product_kinds.code` is `nullable=False, unique=True` - the seed's
    idempotence key. `KindUpdate._not_blank` explicitly special-cases `None`
    (`if value is None: return None`), so the one guard that exists deliberately
    lets an explicit null straight through to `setattr` and the NOT NULL
    constraint."""
    kind = _create_kind(client)
    with granted(K_EDIT):
        response = client.patch(f"{KINDS}/{kind['id']}", json={"code": None})
    _assert_clean_422(response)


def test_patch_kind_explicit_null_name_is_a_clean_422(client):
    """Same shape as `code`, same `_not_blank` `None`-passthrough."""
    kind = _create_kind(client)
    with granted(K_EDIT):
        response = client.patch(f"{KINDS}/{kind['id']}", json={"name": None})
    _assert_clean_422(response)


def test_patch_kind_explicit_null_sort_order_is_a_clean_422(client):
    """`warranty_product_kinds.sort_order` is `nullable=False, server_default="0"`.
    Nothing in `update_kind` validates it before `setattr` - the same unguarded
    `for field, value in changes.items(): setattr(...)` pattern as `priority` on a
    kind rule."""
    kind = _create_kind(client)
    with granted(K_EDIT):
        response = client.patch(f"{KINDS}/{kind['id']}", json={"sort_order": None})
    _assert_clean_422(response)


# =============================================================================
# Gap E - supersede_policy had NO server-side coverage for either rule
# =============================================================================


def test_supersede_with_a_blank_version_is_the_same_clean_refusal_as_create_and_update(
    client,
):
    """`supersede_policy` calls `_required_text(payload.version, "A policy version
    is required.")` - the SAME helper and SAME sentence `create_policy` and
    `update_policy` use. Pinned as a three-way comparison, not just supersede vs
    create, so a future edit that gives supersede its own wording is caught even
    if it still answers 422."""
    baseline = _create_policy(
        client, effective_from="2026-01-01", effective_to="2026-06-30"
    )
    incumbent = _create_policy(
        client, effective_from="2027-01-01", effective_to=None
    )

    with granted(P_ADD):
        create_response = client.post(POLICIES, json=_policy_body(version="   "))
    with granted(P_EDIT):
        update_response = client.patch(
            f"{POLICIES}/{baseline['id']}", json={"version": "   "}
        )
    with granted(P_ADD):
        supersede_response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(
                version="   ", effective_from="2027-07-01", effective_to=None
            ),
        )

    create_message = _assert_clean_422(create_response)
    update_message = _assert_clean_422(update_response)
    supersede_message = _assert_clean_422(supersede_response)
    assert create_message == update_message == supersede_message, (
        "create/update/supersede disagree on the sentence for the identical blank-"
        f"version rule:\n  create: {create_message!r}\n  update: {update_message!r}\n"
        f"  supersede: {supersede_message!r}"
    )


def test_supersede_with_an_inverted_window_is_the_same_clean_refusal_as_create_and_update(
    client,
):
    """`supersede_policy` calls `_assert_window_not_inverted` - the SAME function
    `create_policy` and `update_policy` call."""
    baseline = _create_policy(
        client, effective_from="2026-03-01", effective_to="2026-06-30"
    )
    incumbent = _create_policy(
        client, effective_from="2027-01-01", effective_to=None
    )

    with granted(P_ADD):
        create_response = client.post(
            POLICIES,
            json=_policy_body(effective_from="2028-01-10", effective_to="2028-01-01"),
        )
    with granted(P_EDIT):
        update_response = client.patch(
            f"{POLICIES}/{baseline['id']}", json={"effective_to": "2026-01-01"}
        )
    with granted(P_ADD):
        supersede_response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(effective_from="2027-07-10", effective_to="2027-07-01"),
        )

    create_message = _assert_clean_422(create_response)
    update_message = _assert_clean_422(update_response)
    supersede_message = _assert_clean_422(supersede_response)
    assert create_message == update_message == supersede_message, (
        "create/update/supersede disagree on the sentence for the identical "
        f"inverted-window rule:\n  create: {create_message!r}\n  update: "
        f"{update_message!r}\n  supersede: {supersede_message!r}"
    )


def test_a_refused_supersede_leaves_the_incumbent_open_blank_version(client):
    """AC-P2a / AC-P21's atomicity, the blank-version half: every precondition in
    `supersede_policy` must be checked BEFORE `incumbent.effective_to` is mutated.
    A half-supersede is the worst of the three states - the incumbent would be
    closed with no successor, so every purchase after that day answers `unknown`."""
    incumbent = _create_policy(client, effective_from="2026-01-01", effective_to=None)

    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(
                version="   ", effective_from="2026-07-01", effective_to=None
            ),
        )
    assert response.status_code == 422, response.text

    with granted(P_VIEW):
        refetched = client.get(f"{POLICIES}/{incumbent['id']}")
    assert refetched.status_code == 200, refetched.text
    assert refetched.json()["effective_to"] is None, (
        "The incumbent was closed even though the supersede was refused for a "
        f"blank version - half a supersede: {refetched.json()!r}"
    )


def test_a_refused_supersede_leaves_the_incumbent_open_inverted_window(client):
    """AC-P2a / AC-P21's atomicity, the inverted-window half."""
    incumbent = _create_policy(client, effective_from="2026-01-01", effective_to=None)

    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(effective_from="2026-07-10", effective_to="2026-07-01"),
        )
    assert response.status_code == 422, response.text

    with granted(P_VIEW):
        refetched = client.get(f"{POLICIES}/{incumbent['id']}")
    assert refetched.status_code == 200, refetched.text
    assert refetched.json()["effective_to"] is None, (
        "The incumbent was closed even though the supersede was refused for an "
        f"inverted window - half a supersede: {refetched.json()!r}"
    )
