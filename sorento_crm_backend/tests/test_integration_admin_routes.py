"""Slice 8 of AutoCount Group A - the integration management API (AC-AC-08).

  AC-AC-03  plaintext shown once at creation, never retrievable
  AC-AC-06  rotation with a grace window; immediate revoke
  AC-AC-07  credentials encrypted, never returned, blank-on-update means keep
  AC-AC-39  no key or credential appears in any response

The leak tests matter most. These endpoints exist to manage secrets, so a
careless response field would publish credentials to every client that can read
the list.
"""
import pytest

import app.main  # noqa: F401  isort:skip

from app.models.integration import Integration, IntegrationApiKey
from app.models.user import User
from app.services.integration_admin_service import IntegrationAdminService
from app.services.integration_key_service import IntegrationKeyService
from tests._pg_fixture import pg_empty_schema

_TABLES = [User.__table__, Integration.__table__, IntegrationApiKey.__table__]


@pytest.fixture()
def db():
    """An empty Postgres schema.

    Empty because these tests create integrations under fixed names ("n8n",
    "esb") that the live table already holds under a unique constraint, and
    several assert on ``.one()`` over the whole table.
    """
    with pg_empty_schema(_TABLES) as session:
        yield session


@pytest.fixture()
def svc(db):
    return IntegrationAdminService(db)


@pytest.fixture()
def principal(db):
    user = User(
        email="esb@integrations.local", name="Integration: ESB", status="ACTIVE", is_integration=True
    )
    db.add(user)
    db.flush()
    return user


class TestCreate:
    def test_creates_an_integration(self, svc, principal):
        row = svc.create(
            name="foundryx-esb", type_="autocount_esb", act_as_user_id=principal.id
        )
        assert row.id
        assert row.name == "foundryx-esb"
        assert row.status == "UNVERIFIED"

    def test_rejects_a_duplicate_name(self, svc, principal):
        svc.create(name="n8n", type_="automation", act_as_user_id=principal.id)
        with pytest.raises(Exception):
            svc.create(name="n8n", type_="automation", act_as_user_id=principal.id)

    def test_credentials_are_encrypted_at_rest(self, svc, db, principal):
        svc.create(
            name="esb",
            type_="autocount_esb",
            act_as_user_id=principal.id,
            credentials_json={"esb_key": "super-secret"},
        )
        stored = db.query(Integration).one().credentials_json
        # Ciphertext, not the plaintext and not readable JSON.
        assert stored is not None
        assert "super-secret" not in stored


class TestSerialisationNeverLeaks:
    def test_response_omits_credentials_entirely(self, svc, principal):
        row = svc.create(
            name="esb",
            type_="autocount_esb",
            act_as_user_id=principal.id,
            credentials_json={"esb_key": "super-secret"},
        )
        payload = svc.serialise(row)

        assert "super-secret" not in str(payload)
        assert "credentials_json" not in payload
        # The operator still needs to know a credential exists.
        assert payload["has_credentials"] is True

    def test_response_omits_key_hash_and_plaintext(self, svc, db, principal):
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        plaintext = IntegrationKeyService(db).issue_key(row)

        payload = svc.serialise(row)
        rendered = str(payload)
        assert plaintext not in rendered
        assert "key_hash" not in rendered

    def test_key_metadata_is_still_visible(self, svc, db, principal):
        # AC-AC-06a: last_used_at on the old key is how an admin decides whether
        # closing a grace window is safe. Hiding it would make rotation blind.
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        IntegrationKeyService(db).issue_key(row)

        keys = svc.serialise(row)["keys"]
        assert len(keys) == 1
        assert keys[0]["key_prefix"].startswith("sk_")
        assert "last_used_at" in keys[0]

    def test_has_credentials_is_false_when_unset(self, svc, principal):
        row = svc.create(name="n8n", type_="automation", act_as_user_id=principal.id)
        assert svc.serialise(row)["has_credentials"] is False


class TestUpdate:
    def test_blank_credentials_keep_the_existing_value(self, svc, db, principal):
        # AC-AC-07. A PATCH that wiped credentials because a form posted an
        # empty field would be indistinguishable from an outage.
        row = svc.create(
            name="esb",
            type_="autocount_esb",
            act_as_user_id=principal.id,
            credentials_json={"esb_key": "keep-me"},
        )
        before = db.query(Integration).one().credentials_json

        svc.update(row, name="esb-renamed", credentials_json=None)

        assert db.query(Integration).one().credentials_json == before
        assert row.name == "esb-renamed"

    def test_supplying_credentials_replaces_them(self, svc, db, principal):
        row = svc.create(
            name="esb",
            type_="autocount_esb",
            act_as_user_id=principal.id,
            credentials_json={"esb_key": "old"},
        )
        before = db.query(Integration).one().credentials_json

        svc.update(row, credentials_json={"esb_key": "new"})

        after = db.query(Integration).one().credentials_json
        assert after != before
        assert "new" not in after  # still encrypted

    def test_deactivating_stops_the_integration_authenticating(self, svc, db, principal):
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        key = IntegrationKeyService(db).issue_key(row)

        svc.update(row, is_active=False)

        resolved, failure = IntegrationKeyService(db).resolve(key)
        assert resolved is None
        assert failure is not None


class TestKeyLifecycleThroughTheService:
    def test_issue_returns_plaintext_once(self, svc, db, principal):
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        issued = svc.issue_key(row)

        assert issued["key"].startswith("sk_")
        # Nowhere in the stored record does the plaintext survive.
        assert issued["key"] not in str(svc.serialise(row))

    def test_rotate_returns_a_new_key_and_dates_the_old(self, svc, db, principal):
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        first = svc.issue_key(row)["key"]
        second = svc.rotate_key(row, grace_days=7)["key"]

        assert first != second
        old = db.query(IntegrationApiKey).filter_by(rotated_from_id=None).one()
        assert old.expires_at is not None

    def test_rotate_with_zero_grace_kills_the_old_key_immediately(self, svc, db, principal):
        # The leaked-key path: waiting seven days is not an acceptable response
        # to a secret that is already public.
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        old_key = svc.issue_key(row)["key"]
        svc.rotate_key(row, grace_days=0)

        resolved, failure = IntegrationKeyService(db).resolve(old_key)
        assert resolved is None

    def test_revoke_kills_a_specific_key(self, svc, db, principal):
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        key = svc.issue_key(row)["key"]
        stored = db.query(IntegrationApiKey).one()

        svc.revoke_key(row, stored.id)

        assert IntegrationKeyService(db).resolve(key)[0] is None

    def test_revoking_a_key_from_another_integration_is_refused(self, svc, db, principal):
        # Otherwise an operator scoped to one integration could disable another.
        a = svc.create(name="a", type_="automation", act_as_user_id=principal.id)
        b = svc.create(name="b", type_="automation", act_as_user_id=principal.id)
        svc.issue_key(b)
        b_key_id = db.query(IntegrationApiKey).filter_by(integration_id=b.id).one().id

        with pytest.raises(Exception):
            svc.revoke_key(a, b_key_id)


class TestDelete:
    def test_delete_removes_the_integration_and_its_keys(self, svc, db, principal):
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        svc.issue_key(row)

        svc.delete(row)

        assert db.query(Integration).count() == 0
        assert db.query(IntegrationApiKey).count() == 0

    def test_deleted_integrations_key_stops_working(self, svc, db, principal):
        row = svc.create(name="esb", type_="autocount_esb", act_as_user_id=principal.id)
        key = svc.issue_key(row)["key"]
        svc.delete(row)

        assert IntegrationKeyService(db).resolve(key)[0] is None
