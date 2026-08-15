"""S7b audit gate, defects 2 and 3 - `PolicyResponse`'s wire contract lies about
`created_at` and leaks a raw UUID nothing consumes.

**Defect 2.** `PolicyResponse.created_at` is declared `Optional[datetime] = None` in
`app/schemas/warranty_config.py`. The column behind it
(`app/models/warranty.py:WarrantyPolicy.created_at`) is `nullable=False,
server_default=func.now()` - it can never actually be null. The declared type lies:
every consumer of this schema (FE types generated from it, anything hand-reading
`model_fields`, a future author copy-pasting the field) is told to defend against a
`None` that cannot occur, and nothing stops the field being silently omitted from a
request body that happens to construct a `PolicyResponse` some other way.

**Defect 3.** `PolicyResponse.source_attachment_id` puts a raw UUID on the wire and
nothing consumes it. The repo's standing cursor rule is "no UUIDs in the frontend
UI" (CLAUDE.md, "Cursor rules"), and the schema's own module docstring states the
rule for this exact pair - "every id-bearing relation is ALSO returned resolved" -
which is why `source_attachment_name` exists right next to it. The id has no reason
to also be on the wire once the name is.

Both defects touch the same schema `PolicyResponse` builds every write from
(`create_policy`, `update_policy`, `supersede_policy`, `list_policies`,
`get_policy`), so this file also re-confirms, after the fix, that the audit's
verified-matching set still holds:
  - `term_count` on the LIST row (AC-P13 / AC-P16)
  - `source_attachment_name` resolved from the linked attachment's
    `original_filename`, including the null case when nothing is linked
  - the `{closed, created}` supersede envelope (AC-P2a) - both halves are built by
    the SAME `_policy_dict`, so a `PolicyResponse` schema edit that only survived
    single-policy testing could still break Supersede

Everything runs on Postgres via ``blank_session`` - never sqlite (PRINCIPLES.md).

Run: venv/bin/python -m pytest tests/test_warranty_config_response_contract.py -q -p no:randomly
"""
from __future__ import annotations

import typing
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app import database as app_database  # noqa: E402
from app.dependencies import get_current_user, get_current_user_or_api_key  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402
from app.models.resources import Attachment  # noqa: E402
from app.schemas.warranty_config import PolicyResponse  # noqa: E402
from app.services.company_scope_resolver import apply_company_scope  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code  # noqa: E402

BASE = "/api/v1/warranty-management"
POLICIES = f"{BASE}/policies"

P_VIEW = "warranty.policies.view"
P_ADD = "warranty.policies.add"

SORENTO = "00000000-0000-0000-0000-000000000001"


# ----------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


@pytest.fixture
def client(db):
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


def _create_policy(client, **overrides) -> dict:
    with granted(P_ADD):
        response = client.post(POLICIES, json=_policy_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _attachment(db, stem: str) -> Attachment:
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{TEST_PREFIX}-{stem}.pdf",
        stored_filename=f"{uuid.uuid4().hex}.pdf",
        file_path=f"https://cdn.test/{TEST_PREFIX}-{stem}.pdf",
    )
    db.add(row)
    db.flush()
    return row


# =============================================================================
# defect 2 - PolicyResponse.created_at lies about being Optional
# =============================================================================


def test_policy_response_declares_created_at_as_required_and_not_optional():
    """Pins the DECLARATION itself, not just a runtime value - `model_fields` is
    Pydantic v2's own introspection of what was written in the schema, so this
    fails for the schema being wrong even if a caller never notices at runtime."""
    field_info = PolicyResponse.model_fields["created_at"]

    assert field_info.is_required(), (
        "PolicyResponse.created_at carries a default (`= None`), so a caller "
        "constructing this schema without the field is accepted. The column "
        "behind it is `nullable=False, server_default=now()` - the field must be "
        "required, matching the column it represents."
    )

    origin = typing.get_origin(field_info.annotation)
    args = typing.get_args(field_info.annotation)
    is_optional = origin is typing.Union and type(None) in args
    assert not is_optional, (
        f"PolicyResponse.created_at is declared Optional ({field_info.annotation!r}) "
        "but the column is NOT NULL with a server default - the declared type lies "
        "to every consumer of this schema."
    )


def test_a_freshly_created_policy_carries_a_non_null_created_at(client):
    """The runtime companion to the declaration test above. This may already pass
    today (the service refreshes the row after commit, so the server default is
    populated) - it is here so a future regression that starts omitting or
    nulling `created_at` at the ORM layer is caught even though the schema will,
    once fixed, refuse to serialize a null in that slot anyway.
    """
    created = _create_policy(client)
    assert created.get("created_at"), (
        f"PolicyResponse.created_at came back null/missing on a freshly created "
        f"row: {created!r}"
    )
    # A parseable ISO datetime, not just a truthy placeholder.
    datetime.fromisoformat(created["created_at"].replace("Z", "+00:00"))


# =============================================================================
# defect 3 - PolicyResponse.source_attachment_id puts a raw UUID on the wire
# =============================================================================


def test_source_attachment_id_is_absent_from_the_policy_response_without_a_link(
    client,
):
    created = _create_policy(client)
    assert "source_attachment_id" not in created, (
        "PolicyResponse must not carry source_attachment_id on the wire - the "
        "repo's cursor rule is 'no UUIDs in the frontend UI', and nothing "
        f"consumes this id once source_attachment_name resolves it: {created!r}"
    )
    assert "source_attachment_name" in created, (
        "source_attachment_name must remain even with nothing linked - the UI "
        "reads this field, and dropping it alongside the id would break the "
        f"screen that shows 'no source document': {created!r}"
    )
    assert created["source_attachment_name"] is None

    with granted(P_VIEW):
        fetched = client.get(f"{POLICIES}/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert "source_attachment_id" not in body, (
        f"GET /policies/{{id}} also puts the raw id on the wire: {body!r}"
    )


def test_source_attachment_id_is_absent_even_when_a_document_is_linked(client, db):
    """The id must not leak even in the one case it might be tempting to keep it -
    a policy that DOES have a linked source document."""
    attachment = _attachment(db, "policy-v9")
    created = _create_policy(client, source_attachment_id=attachment.id)

    assert "source_attachment_id" not in created, (
        f"A linked source document still put the raw id on the wire: {created!r}"
    )
    assert created["source_attachment_name"] == attachment.original_filename, (
        "source_attachment_name must resolve the linked attachment's "
        f"original_filename: {created!r}"
    )


# =============================================================================
# protect - what the audit already verified must still hold after the fix
# =============================================================================


def test_term_count_is_still_present_on_the_policies_list_row(client, db):
    from app.models.warranty import WarrantyProductKind, WarrantyTerm

    created = _create_policy(client)
    kind = WarrantyProductKind(
        id=str(uuid.uuid4()),
        code=unique_code("kind")[:64],
        name=f"{TEST_PREFIX} Water Closet"[:255],
        is_active=True,
    )
    db.add(kind)
    db.flush()
    term = WarrantyTerm(
        id=str(uuid.uuid4()),
        policy_id=created["id"],
        kind_id=kind.id,
        part_name=f"{TEST_PREFIX} Ceramic Body",
        duration_months=60,
        is_lifetime=False,
        installation_included=False,
    )
    db.add(term)
    db.commit()

    with granted(P_VIEW):
        response = client.get(POLICIES, params={"query": created["version"]})
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    row = next(r for r in rows if r["id"] == created["id"])
    assert "term_count" in row, (
        f"term_count must ride the LIST row (AC-P13 / AC-P16), not only the "
        f"detail response: {row!r}"
    )
    assert row["term_count"] == 1, row


def test_source_attachment_name_still_resolves_from_original_filename_on_the_list(
    client, db
):
    attachment = _attachment(db, "list-row")
    created = _create_policy(client, source_attachment_id=attachment.id)

    with granted(P_VIEW):
        response = client.get(POLICIES, params={"query": created["version"]})
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    row = next(r for r in rows if r["id"] == created["id"])
    assert row["source_attachment_name"] == attachment.original_filename, row


def test_supersede_envelope_still_carries_closed_and_created_as_clean_policies(
    client,
):
    incumbent = _create_policy(
        client, effective_from="2026-01-01", effective_to=None
    )
    with granted(P_ADD):
        response = client.post(
            f"{POLICIES}/{incumbent['id']}/supersede",
            json=_policy_body(effective_from="2026-07-01", effective_to=None),
        )
    assert response.status_code == 201, response.text
    body = response.json()

    assert set(body.keys()) == {"closed", "created"}, (
        f"The supersede envelope must be exactly {{closed, created}} (AC-P2a): "
        f"{body!r}"
    )
    for label in ("closed", "created"):
        row = body[label]
        assert "source_attachment_id" not in row, (
            f"supersede's '{label}' half leaks source_attachment_id: {row!r}"
        )
        assert "source_attachment_name" in row, (
            f"supersede's '{label}' half is missing source_attachment_name: {row!r}"
        )
        assert row.get("created_at"), (
            f"supersede's '{label}' half has a null/missing created_at: {row!r}"
        )
        assert "term_count" in row, (
            f"supersede's '{label}' half is missing term_count: {row!r}"
        )

    assert body["closed"]["effective_to"] == "2026-06-30"
    assert body["created"]["effective_from"] == "2026-07-01"
