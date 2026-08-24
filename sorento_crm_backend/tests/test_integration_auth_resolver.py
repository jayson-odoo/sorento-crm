"""Slice 4 of AutoCount Group A - resolving a key to an RBAC principal.

This is the join between the key lifecycle and Sorento's existing RBAC: a
presented key becomes the ``users`` row the integration acts as, and from there
every ordinary permission check applies unchanged.

  AC-AC-02  the caller's identity is recorded on every request
  AC-AC-04  no ==/!= on a secret on any path
  AC-AC-05  permissions are enforced against the resolved principal
  AC-AC-05a writes attribute to a real users row, never the string "system"
  AC-AC-39  keys never appear in logs, errors or responses

The refusal *reason* reaches the caller as a stable code so an operator can tell
a closed grace window from a key that was never valid, but the key itself must
never appear in any message.
"""
import pytest
from fastapi import HTTPException

from app.models.integration import Integration, IntegrationApiKey
from app.models.user import User
from app.services.integration_auth import resolve_integration_principal
from app.services.integration_key_service import IntegrationKeyService
from tests._pg_fixture import pg_session, unique_code


@pytest.fixture()
def db():
    with pg_session() as session:
        yield session


def _integration(db, name=None, is_active=True, with_user=True):
    """A throwaway integration and its principal.

    Uniquely named: `integrations.name` and `users.email` are unique and the
    live tables already hold the seeded rows, where the old sqlite fixture
    started empty and could reuse fixed names.
    """
    name = name or unique_code("INT")
    user_id = None
    if with_user:
        user = User(
            email=f"{name}@integrations.local".lower(),
            name=f"Integration {name}",
            status="ACTIVE",
            is_integration=True,
        )
        db.add(user)
        db.flush()
        user_id = user.id
    row = Integration(name=name, type="autocount_esb", act_as_user_id=user_id, is_active=is_active)
    db.add(row)
    db.flush()
    return row


def _key_row(db, integration):
    """The integration's own key. The table holds real rows, so `.one()` has to
    be scoped or it is asserting against production data."""
    return db.query(IntegrationApiKey).filter_by(integration_id=integration.id).one()


class TestSuccessfulResolution:
    def test_returns_the_act_as_user_not_a_synthetic_principal(self, db):
        integration = _integration(db)
        key = IntegrationKeyService(db).issue_key(integration)

        principal = resolve_integration_principal(db, key)

        # AC-AC-05a: the string "system" is exactly what this replaces.
        assert principal["id"] == integration.act_as_user_id
        assert principal["id"] != "system"
        assert principal["email"] == f"{integration.name}@integrations.local".lower()

    def test_records_which_integration_the_call_came_from(self, db):
        # AC-AC-02/38: attribution must survive to the audit trail, and two
        # integrations sharing one act-as user would otherwise be indistinguishable.
        integration = _integration(db)
        key = IntegrationKeyService(db).issue_key(integration)

        principal = resolve_integration_principal(db, key)

        assert principal["integration_id"] == integration.id
        assert principal["integration_name"] == integration.name

    def test_marks_the_auth_method(self, db):
        integration = _integration(db)
        key = IntegrationKeyService(db).issue_key(integration)
        assert resolve_integration_principal(db, key)["auth_method"] == "integration_api_key"

    def test_two_integrations_resolve_to_their_own_principals(self, db):
        svc = IntegrationKeyService(db)
        n8n, esb = _integration(db), _integration(db)
        n8n_key, esb_key = svc.issue_key(n8n), svc.issue_key(esb)

        assert resolve_integration_principal(db, n8n_key)["id"] == n8n.act_as_user_id
        assert resolve_integration_principal(db, esb_key)["id"] == esb.act_as_user_id


class TestRefusals:
    @pytest.mark.parametrize(
        "presented", ["", None, "sk_not_a_real_key"], ids=["empty", "none", "unknown"]
    )
    def test_bad_keys_are_401(self, db, presented):
        _integration(db)
        with pytest.raises(HTTPException) as exc:
            resolve_integration_principal(db, presented)
        assert exc.value.status_code == 401

    def test_expired_key_reports_a_distinct_code(self, db):
        from datetime import datetime, timedelta

        integration = _integration(db)
        key = IntegrationKeyService(db).issue_key(integration)
        _key_row(db, integration).expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.flush()

        with pytest.raises(HTTPException) as exc:
            resolve_integration_principal(db, key)
        assert exc.value.status_code == 401
        assert "key_expired" in str(exc.value.detail)

    def test_revoked_key_reports_a_distinct_code(self, db):
        integration = _integration(db)
        svc = IntegrationKeyService(db)
        key = svc.issue_key(integration)
        svc.revoke_key(_key_row(db, integration))

        with pytest.raises(HTTPException) as exc:
            resolve_integration_principal(db, key)
        assert "key_revoked" in str(exc.value.detail)

    def test_inactive_integration_is_refused(self, db):
        integration = _integration(db, is_active=False)
        key = IntegrationKeyService(db).issue_key(integration)

        with pytest.raises(HTTPException) as exc:
            resolve_integration_principal(db, key)
        assert "integration_inactive" in str(exc.value.detail)

    def test_integration_without_a_principal_is_refused_not_silently_allowed(self, db):
        # act_as_user_id is nullable until the seed migration populates it.
        # A row in that state must fail closed: resolving it to "no user" and
        # continuing would hand an unauthenticated caller an unchecked session.
        integration = _integration(db, with_user=False)
        key = IntegrationKeyService(db).issue_key(integration)

        with pytest.raises(HTTPException) as exc:
            resolve_integration_principal(db, key)
        assert exc.value.status_code == 401

    def test_the_principal_cannot_be_deleted_while_in_use(self, db):
        # Replaces a sqlite test that deleted the act-as user and asserted the
        # resolver refused the dangling reference. On Postgres that state is
        # unreachable: act_as_user_id is ON DELETE RESTRICT, so the delete
        # itself fails. The sqlite fixture never enabled foreign-key
        # enforcement, so it was rehearsing a scenario the database prevents.
        #
        # The guarantee worth pinning is the stronger one: an integration's
        # principal cannot be removed out from under it. The resolver keeps its
        # defensive branch for a dangling id, but nothing can now produce one.
        integration = _integration(db)
        IntegrationKeyService(db).issue_key(integration)

        with pytest.raises(Exception):
            db.query(User).filter(User.id == integration.act_as_user_id).delete()
            db.flush()

    def test_trashed_act_as_user_is_refused(self, db):
        # Deactivating the principal must actually stop the integration, or
        # "disable this account" silently fails to do what an admin expects.
        integration = _integration(db)
        key = IntegrationKeyService(db).issue_key(integration)
        db.query(User).filter(User.id == integration.act_as_user_id).one().is_trashed = True
        db.flush()

        with pytest.raises(HTTPException) as exc:
            resolve_integration_principal(db, key)
        assert exc.value.status_code == 401


class TestNoSecretLeakage:
    def test_the_key_never_appears_in_the_error_detail(self, db):
        # AC-AC-39. An error body is the easiest place for a secret to escape
        # into a log aggregator.
        _integration(db)
        secret = "sk_super_secret_value_that_must_not_leak"
        with pytest.raises(HTTPException) as exc:
            resolve_integration_principal(db, secret)
        assert secret not in str(exc.value.detail)

    def test_the_key_never_appears_in_a_successful_principal(self, db):
        integration = _integration(db)
        key = IntegrationKeyService(db).issue_key(integration)
        principal = resolve_integration_principal(db, key)
        assert key not in str(principal)

    def test_refusals_are_not_logged_with_the_key(self, db, caplog):
        _integration(db)
        secret = "sk_another_secret_that_must_not_leak"
        with caplog.at_level("DEBUG"):
            with pytest.raises(HTTPException):
                resolve_integration_principal(db, secret)
        assert secret not in caplog.text


class TestUsageStamping:
    def test_successful_resolution_marks_the_integration_used(self, db):
        integration = _integration(db)
        key = IntegrationKeyService(db).issue_key(integration)
        resolve_integration_principal(db, key)
        assert integration.last_used_at is not None

    def test_failed_resolution_does_not_mark_it_used(self, db):
        integration = _integration(db)
        IntegrationKeyService(db).issue_key(integration)
        with pytest.raises(HTTPException):
            resolve_integration_principal(db, "sk_wrong")
        assert integration.last_used_at is None
