"""Slice 2 of AutoCount Group A — the integration + API key schema.

Pins the shape the rest of the group depends on:

  AC-AC-01  an integration is a first-class record, not an env var
  AC-AC-02  each integration has its own key; revoking one leaves the other alone
  AC-AC-03  only a hash persists; the plaintext is never stored
  AC-AC-05a an integration acts as a real users row, never the string "system"
  AC-AC-05b integration users carry is_integration, distinct from is_protected
  AC-AC-06  rotation links new key to old via rotated_from_id
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.integration import Integration, IntegrationApiKey
from app.models.user import User
from app.services.integration_key_crypto import generate_api_key, hash_api_key, key_prefix
from tests._sqlite_compat import create_all_sqlite_safe


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    # Only the tables under test. A whole-metadata create_all cannot work on
    # sqlite here: the SCM models declare schema="scm", which sqlite has no
    # concept of. create_all_sqlite_safe additionally strips the Postgres-cast
    # server defaults ('{}'::jsonb) that sqlite's DDL compiler rejects.
    create_all_sqlite_safe(
        Base.metadata,
        engine,
        tables=[User.__table__, Integration.__table__, IntegrationApiKey.__table__],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _user(db, email="esb@integrations.local", name="FoundryX ESB"):
    row = User(email=email, name=name, status="ACTIVE", is_integration=True)
    db.add(row)
    db.flush()
    return row


def _integration(db, name="foundryx-esb", **kw):
    row = Integration(
        name=name,
        type=kw.pop("type", "autocount_esb"),
        act_as_user_id=kw.pop("act_as_user_id", None) or _user(db, f"{name}@integrations.local").id,
        **kw,
    )
    db.add(row)
    db.flush()
    return row


class TestIntegrationRecord:
    def test_persists_with_the_documented_columns(self, db):
        row = _integration(db)
        assert row.id
        assert row.name == "foundryx-esb"
        assert row.type == "autocount_esb"
        assert row.act_as_user_id
        assert row.created_at is not None

    def test_defaults_to_unverified_and_active(self, db):
        # A brand-new integration has not proven it can talk to anything yet.
        # Claiming ACTIVE before a successful call would misreport health.
        row = _integration(db)
        assert row.status == "UNVERIFIED"
        assert row.is_active is True

    def test_tracks_last_used_and_last_error(self, db):
        row = _integration(db)
        assert row.last_used_at is None
        assert row.last_error is None

    def test_config_and_credentials_are_separate_columns(self, db):
        # config_json is displayable; credentials_json is Fernet ciphertext and
        # write-only over the API. Collapsing them would leak secrets to any
        # read endpoint that returns config.
        row = _integration(db, config_json={"esb_base_url": "https://esb.example"})
        row.credentials_json = "gAAAAAB-ciphertext"
        db.flush()
        assert row.config_json == {"esb_base_url": "https://esb.example"}
        assert row.credentials_json == "gAAAAAB-ciphertext"

    def test_name_is_unique(self, db):
        _integration(db, name="n8n")
        db.commit()
        with pytest.raises(Exception):
            _integration(db, name="n8n")
            db.commit()

    def test_act_as_user_id_is_a_real_user_fk(self, db):
        # AC-AC-05a: the fake {"id": "system"} principal is what this replaces.
        cols = {c["name"]: c for c in inspect(db.get_bind()).get_columns("integrations")}
        assert "act_as_user_id" in cols
        fks = inspect(db.get_bind()).get_foreign_keys("integrations")
        target = [fk for fk in fks if fk["referred_table"] == "users"]
        assert target, "act_as_user_id must be a FK to users"


class TestIntegrationApiKey:
    def test_stores_hash_and_prefix_never_plaintext(self, db):
        integration = _integration(db)
        plaintext = generate_api_key()
        key = IntegrationApiKey(
            integration_id=integration.id,
            key_hash=hash_api_key(plaintext),
            key_prefix=key_prefix(plaintext),
        )
        db.add(key)
        db.flush()

        assert key.key_hash != plaintext
        # AC-AC-03: no column anywhere may hold the plaintext.
        values = [str(getattr(key, c.name)) for c in key.__table__.columns]
        assert plaintext not in values

    def test_key_hash_is_unique_across_integrations(self, db):
        # Verification is an indexed lookup on key_hash, so a collision would
        # make the caller's identity ambiguous.
        a, b = _integration(db, name="n8n"), _integration(db, name="mcp")
        plaintext = generate_api_key()
        db.add(IntegrationApiKey(integration_id=a.id, key_hash=hash_api_key(plaintext), key_prefix="sk_x"))
        db.commit()
        db.add(IntegrationApiKey(integration_id=b.id, key_hash=hash_api_key(plaintext), key_prefix="sk_x"))
        with pytest.raises(Exception):
            db.commit()

    def test_new_key_has_no_expiry_and_no_revocation(self, db):
        integration = _integration(db)
        key = IntegrationApiKey(
            integration_id=integration.id, key_hash=hash_api_key(generate_api_key()), key_prefix="sk_abc"
        )
        db.add(key)
        db.flush()
        # An issued key lives until rotated or revoked. A default expiry would
        # silently kill integrations nobody touched.
        assert key.expires_at is None
        assert key.revoked_at is None
        assert key.last_used_at is None

    def test_rotation_links_new_key_to_the_one_it_replaced(self, db):
        integration = _integration(db)
        old = IntegrationApiKey(
            integration_id=integration.id, key_hash=hash_api_key(generate_api_key()), key_prefix="sk_old"
        )
        db.add(old)
        db.flush()

        old.expires_at = datetime.utcnow() + timedelta(days=7)
        new = IntegrationApiKey(
            integration_id=integration.id,
            key_hash=hash_api_key(generate_api_key()),
            key_prefix="sk_new",
            rotated_from_id=old.id,
        )
        db.add(new)
        db.flush()

        assert new.rotated_from_id == old.id
        assert old.expires_at is not None

    def test_two_integrations_hold_independent_keys(self, db):
        # AC-AC-02: revoking one must not affect the other.
        n8n, esb = _integration(db, name="n8n"), _integration(db, name="esb")
        k1 = IntegrationApiKey(
            integration_id=n8n.id, key_hash=hash_api_key(generate_api_key()), key_prefix="sk_1"
        )
        k2 = IntegrationApiKey(
            integration_id=esb.id, key_hash=hash_api_key(generate_api_key()), key_prefix="sk_2"
        )
        db.add_all([k1, k2])
        db.flush()

        k1.revoked_at = datetime.utcnow()
        db.flush()

        assert k1.revoked_at is not None
        assert k2.revoked_at is None


class TestUserIsIntegrationFlag:
    def test_users_carry_is_integration_defaulting_false(self, db):
        human = User(email="human@example.com", name="Human", status="ACTIVE")
        db.add(human)
        db.flush()
        assert human.is_integration is False

    def test_is_integration_is_distinct_from_is_protected(self, db):
        # AC-AC-05b: is_protected already selects notification recipients in
        # automation_service.py:34. An integration user marked is_protected
        # would silently start receiving automation email.
        row = _user(db)
        assert row.is_integration is True
        assert row.is_protected is False
