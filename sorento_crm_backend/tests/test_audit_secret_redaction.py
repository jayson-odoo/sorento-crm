"""Secrets never enter `audit_logs` (issue #1281, section 6.1).

`User` opted into the audit listener with no `__audit_columns__`, so every user
write (every login included, because `last_sign_in_at` changes) snapshotted the
bcrypt `password` into `old_values` and `new_values`, and `GET /audit/logs/`
handed it back. Two layers now keep it out:

* `User.__audit_columns__` names the columns worth auditing, and `password` is
  not one of them.
* `log_audit` drops every key on a deny list (`AUDIT_SECRET_KEYS`) from both
  payloads, whichever model or caller produced them, so a secret column on a
  model with no `__audit_columns__` (`project_quotation_issues.sign_token`, a
  bearer link token) or on the next model to opt in cannot leak either.

Every test seeds its own rows on a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.audit_context import set_audit_context
from app.models.audit import AuditLog
from app.models.user import User
from app.services import audit_service
from app.services.audit_service import log_audit, register_audit_listeners

from ._pg_fixture import blank_session


@pytest.fixture(autouse=True)
def _listeners():
    register_audit_listeners()


@pytest.fixture(autouse=True)
def _no_leaked_actor():
    yield
    set_audit_context(None, None)


def _user_rows(db, user_id):
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "users", AuditLog.entity_id == user_id)
        .all()
    )


def test_user_create_and_update_never_write_the_password_hash():
    with blank_session() as db:
        user_id = str(uuid.uuid4())
        db.add(
            User(
                id=user_id,
                email=f"zz-audit-{user_id[:8]}@example.com",
                name="Before",
                password="$2b$12$thisisnotarealbcrypthashbutlookslikeone",
                status="ACTIVE",
            )
        )
        db.commit()

        user = db.get(User, user_id)
        user.name = "After"
        user.last_sign_in_at = datetime(2026, 9, 26, 10, 0, 0)
        db.commit()

        rows = _user_rows(db, user_id)
        assert {r.action for r in rows} == {"CREATE", "UPDATE"}
        for row in rows:
            for payload in (row.old_values, row.new_values):
                assert "password" not in (payload or {})
                assert "$2b$12$" not in str(payload or {})

        update = next(r for r in rows if r.action == "UPDATE")
        # The audit still records what an admin needs: the real change.
        assert update.old_values["name"] == "Before"
        assert update.new_values["name"] == "After"


def test_a_password_change_writes_no_hash_either():
    with blank_session() as db:
        user_id = str(uuid.uuid4())
        db.add(
            User(
                id=user_id,
                email=f"zz-audit-{user_id[:8]}@example.com",
                password="$2b$12$oldhasholdhasholdhasholdhasholdhash",
                status="ACTIVE",
            )
        )
        db.commit()
        db.get(User, user_id).password = "$2b$12$newhashnewhashnewhashnewhashnewhash"
        db.commit()

        for row in _user_rows(db, user_id):
            assert "hash" not in str(row.old_values or {})
            assert "hash" not in str(row.new_values or {})


def test_user_declares_audit_columns_without_password():
    cols = getattr(User, "__audit_columns__", None)
    assert cols is not None, "User must name its audited columns explicitly"
    assert "password" not in cols
    # Every named column is real, or the filter silently drops it.
    real = {c.key for c in User.__table__.columns}
    assert set(cols) <= real
    assert {"email", "name", "status"} <= set(cols)


def test_log_audit_drops_deny_listed_keys_from_any_caller():
    with blank_session() as db:
        entry = log_audit(
            db,
            "project_quotation_issues",
            str(uuid.uuid4()),
            "UPDATE",
            old_values={"status": "draft", "sign_token": "old-bearer", "password": "x"},
            new_values={"status": "issued", "sign_token": "new-bearer", "password": "y"},
        )
        db.flush()
        db.refresh(entry)
        assert entry.old_values == {"status": "draft"}
        assert entry.new_values == {"status": "issued"}


def test_deny_list_covers_the_secret_columns_on_audited_models():
    # The two secret-bearing columns found on `__audit_track__` models at the time
    # of #1281. A new one belongs here AND in the deny list.
    assert {"password", "sign_token"} <= set(getattr(audit_service, "AUDIT_SECRET_KEYS", ()))
