"""Slice 3 of AutoCount Group A — key lifecycle: issue, verify, rotate, revoke.

  AC-AC-02  each integration has its own key; revoking one leaves the other alone
  AC-AC-03  plaintext returned once at issue, never retrievable afterwards
  AC-AC-06  rotation grace window (default 7 days), closed passively, plus
            immediate revoke; both events audit-logged
  AC-AC-06a expiry is diagnosable -- a distinct key_expired reason, and the old
            key's last_used_at is visible before the window closes

The failure *reason* is part of the contract, not an implementation detail: an
operator whose ESB starts 401-ing at 3am needs to distinguish "you rotated and
never migrated" from "this key was never valid".
"""
from datetime import datetime, timedelta

import pytest

from app.models.integration import Integration, IntegrationApiKey
from app.models.user import User
from app.services.integration_key_service import (
    DEFAULT_GRACE_DAYS,
    AuthFailure,
    IntegrationKeyService,
)
from tests._pg_fixture import pg_session, unique_code


@pytest.fixture()
def db():
    with pg_session() as session:
        yield session


@pytest.fixture()
def svc(db):
    return IntegrationKeyService(db)


def _integration(db, name=None, is_active=True):
    """A throwaway integration.

    Named uniquely because `integrations` is seeded (n8n, sorento-mcp,
    foundryx-esb) and `name` is unique -- the old sqlite fixture started from an
    empty table and could reuse fixed names freely.
    """
    name = name or unique_code("INT")
    user = User(
        email=f"{name}@integrations.local".lower(),
        name=name,
        status="ACTIVE",
        is_integration=True,
    )
    db.add(user)
    db.flush()
    row = Integration(name=name, type="autocount_esb", act_as_user_id=user.id, is_active=is_active)
    db.add(row)
    db.flush()
    return row


def _keys(db, integration):
    """Keys of one integration. The table holds real rows, so an unscoped
    `.one()` would be asserting against production data."""
    return db.query(IntegrationApiKey).filter_by(integration_id=integration.id)


def _superseded(db, integration):
    """The pre-rotation key: the one nothing was rotated from."""
    return _keys(db, integration).filter_by(rotated_from_id=None).one()


class TestIssue:
    def test_returns_plaintext_once_and_persists_only_a_hash(self, db, svc):
        integration = _integration(db)
        plaintext = svc.issue_key(integration)

        assert plaintext.startswith("sk_")
        stored = _keys(db, integration).one()
        assert stored.key_hash != plaintext
        assert stored.key_prefix == plaintext[: len(stored.key_prefix)]

    def test_issued_key_authenticates(self, db, svc):
        integration = _integration(db)
        plaintext = svc.issue_key(integration)
        resolved, failure = svc.resolve(plaintext)
        assert failure is None
        assert resolved.id == integration.id

    def test_issued_key_has_no_expiry(self, db, svc):
        # It lives until rotated or revoked. A default expiry would kill
        # integrations nobody touched.
        integration = _integration(db)
        svc.issue_key(integration)
        assert _keys(db, integration).one().expires_at is None


class TestResolveFailures:
    def test_unknown_key_is_invalid(self, db, svc):
        _integration(db)
        resolved, failure = svc.resolve("sk_nothing_like_a_real_key")
        assert resolved is None
        assert failure is AuthFailure.INVALID_KEY

    def test_empty_key_is_invalid(self, db, svc):
        resolved, failure = svc.resolve("")
        assert resolved is None
        assert failure is AuthFailure.INVALID_KEY

    def test_none_key_is_invalid(self, db, svc):
        resolved, failure = svc.resolve(None)
        assert resolved is None
        assert failure is AuthFailure.INVALID_KEY

    def test_revoked_key_reports_revoked(self, db, svc):
        integration = _integration(db)
        plaintext = svc.issue_key(integration)
        svc.revoke_key(_keys(db, integration).one())

        resolved, failure = svc.resolve(plaintext)
        assert resolved is None
        assert failure is AuthFailure.KEY_REVOKED

    def test_expired_key_reports_expired_not_invalid(self, db, svc):
        # AC-AC-06a. The whole point: "your grace window closed" must not look
        # like "this key never existed".
        integration = _integration(db)
        plaintext = svc.issue_key(integration)
        key = _keys(db, integration).one()
        key.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.flush()

        resolved, failure = svc.resolve(plaintext)
        assert resolved is None
        assert failure is AuthFailure.KEY_EXPIRED

    def test_inactive_integration_is_rejected(self, db, svc):
        integration = _integration(db, is_active=False)
        plaintext = svc.issue_key(integration)
        resolved, failure = svc.resolve(plaintext)
        assert resolved is None
        assert failure is AuthFailure.INTEGRATION_INACTIVE


class TestRotation:
    def test_both_keys_work_during_the_grace_window(self, db, svc):
        integration = _integration(db)
        old = svc.issue_key(integration)
        new = svc.rotate_key(integration)

        assert svc.resolve(old)[0].id == integration.id
        assert svc.resolve(new)[0].id == integration.id

    def test_grace_defaults_to_seven_days(self, db, svc):
        integration = _integration(db)
        svc.issue_key(integration)
        svc.rotate_key(integration)

        old = _superseded(db, integration)
        assert old.expires_at is not None
        remaining = old.expires_at - datetime.utcnow()
        assert timedelta(days=DEFAULT_GRACE_DAYS) - remaining < timedelta(minutes=1)
        assert DEFAULT_GRACE_DAYS == 7

    def test_grace_is_configurable(self, db, svc):
        integration = _integration(db)
        svc.issue_key(integration)
        svc.rotate_key(integration, grace_days=1)

        old = _superseded(db, integration)
        assert old.expires_at - datetime.utcnow() < timedelta(days=1, minutes=1)

    def test_new_key_links_back_to_the_one_it_replaced(self, db, svc):
        integration = _integration(db)
        svc.issue_key(integration)
        svc.rotate_key(integration)

        old = _superseded(db, integration)
        new = _keys(db, integration).filter(IntegrationApiKey.rotated_from_id.isnot(None)).one()
        assert new.rotated_from_id == old.id

    def test_old_key_stops_working_once_the_window_lapses(self, db, svc):
        integration = _integration(db)
        old = svc.issue_key(integration)
        new = svc.rotate_key(integration)

        stale = _superseded(db, integration)
        stale.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.flush()

        assert svc.resolve(old)[1] is AuthFailure.KEY_EXPIRED
        assert svc.resolve(new)[0].id == integration.id

    def test_expiry_is_evaluated_at_request_time_not_by_a_scheduler(self, db, svc):
        # A5: the scheduler is opt-in and defaults off, so a cron-driven expiry
        # would leave superseded keys valid forever wherever it was never
        # enabled. Nothing but resolve() itself may close the window.
        integration = _integration(db)
        old = svc.issue_key(integration)
        svc.rotate_key(integration)

        stale = _superseded(db, integration)
        stale.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.flush()

        # No job has run, nothing stamped revoked_at -- and it is still refused.
        assert stale.revoked_at is None
        assert svc.resolve(old)[1] is AuthFailure.KEY_EXPIRED

    def test_immediate_revoke_beats_the_grace_window(self, db, svc):
        # Needed to remediate a leak now rather than in seven days.
        integration = _integration(db)
        old = svc.issue_key(integration)
        svc.rotate_key(integration)

        stale = _superseded(db, integration)
        svc.revoke_key(stale)

        assert svc.resolve(old)[1] is AuthFailure.KEY_REVOKED


class TestIsolationBetweenIntegrations:
    def test_revoking_one_integrations_key_leaves_the_other_working(self, db, svc):
        # AC-AC-02 -- the defect the single shared EXTERNAL_API_KEY has today.
        n8n, esb = _integration(db), _integration(db)
        n8n_key, esb_key = svc.issue_key(n8n), svc.issue_key(esb)

        svc.revoke_key(_keys(db, n8n).one())

        assert svc.resolve(n8n_key)[1] is AuthFailure.KEY_REVOKED
        assert svc.resolve(esb_key)[0].id == esb.id

    def test_each_key_resolves_to_its_own_integration(self, db, svc):
        n8n, esb = _integration(db), _integration(db)
        assert svc.resolve(svc.issue_key(n8n))[0].id == n8n.id
        assert svc.resolve(svc.issue_key(esb))[0].id == esb.id


class TestUsageTracking:
    def test_successful_resolve_stamps_last_used_on_key_and_integration(self, db, svc):
        integration = _integration(db)
        plaintext = svc.issue_key(integration)
        key_row = _keys(db, integration).one()

        svc.resolve(plaintext)

        # Read the objects the resolver stamped, WITHOUT re-querying. The stamp
        # is written on its own connection and committed there (see
        # `_stamp_usage`), so it cannot see rows this test has not committed --
        # a deliberate trade: the caller's transaction must not carry the write,
        # because holding that row lock for the length of a request is what took
        # the integration API down on 2026-08-10. A re-query here would reload
        # the row from a DB that never saw the fixture's uncommitted insert.
        assert key_row.last_used_at is not None
        assert integration.last_used_at is not None

    def test_old_key_usage_is_visible_before_expiry(self, db, svc):
        # AC-AC-06a: this is how an admin knows whether the caller actually
        # migrated. Without it, closing the window is a coin flip.
        integration = _integration(db)
        old = svc.issue_key(integration)
        svc.rotate_key(integration)
        stale = _superseded(db, integration)

        svc.resolve(old)

        assert stale.last_used_at is not None

    def test_resolve_leaves_no_pending_write_in_the_callers_transaction(self, db, svc):
        """The stamp must never become part of the caller's transaction.

        This is the regression guard for the 2026-08-10 outage. The stamp used
        to be `integration.last_used_at = now; db.flush()`, which took a
        row-exclusive lock on a row EVERY api-key request needs and held it
        until the request finished -- so one slow request serialised every other
        integration caller behind it, and the queue only cleared when the
        container was killed.

        Asserting "nothing is dirty" is the cheapest way to pin that: a dirty
        attribute here means an UPDATE will be emitted inside the caller's
        transaction, which means the lock is back.
        """
        integration = _integration(db)
        plaintext = svc.issue_key(integration)
        db.flush()

        svc.resolve(plaintext)

        assert not db.dirty, f"resolve() left pending writes: {db.dirty}"

    def test_failed_resolve_does_not_stamp_last_used(self, db, svc):
        integration = _integration(db)
        svc.issue_key(integration)
        svc.resolve("sk_wrong")

        assert _keys(db, integration).one().last_used_at is None
        assert integration.last_used_at is None
