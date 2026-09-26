"""Identity S0 (#1280) security review round.

1. Impersonation stays visible: an admin's writes under impersonation carry
   user_id = the target and real_user_id = the admin (plan 8.1), so filtering by
   the admin must find them, the activity feed must say "<admin> on behalf of
   <target>", and api_call_log.actor must name both.
2. An inbound X-Trace-Id is accepted only as ^[A-Za-z0-9_-]{1,64}$.
4. A 409 names another user by name or email only, never by phone.
5. X-Tool-Name loses its control characters before it reaches the audit row.

(3, the migration's INVALID-index path, lives in
tests/test_migration_identity_0001_s0_model.py, which runs serially.)
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main  # noqa: F401  registers every model and router
from app.audit_context import AuditActor, clear_actor, get_actor
from app.main import app
from app.models.audit import AuditLog
from app.models.user import User
from tests._pg_fixture import blank_session, unique_code


def _user(db, name: str) -> User:
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('sr')}@example.com".lower(), name=name, status="ACTIVE")
    db.add(user)
    db.flush()
    return user


def _impersonated_row(db, admin: User, target: User) -> AuditLog:
    row = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="users",
        entity_id=str(uuid.uuid4()),
        action="UPDATE",
        actor_type="user",
        user_id=target.id,
        real_user_id=admin.id,
        auth_method="impersonation",
        changed_at=datetime(2026, 9, 26, 9, 0, 0),
        old_values={"name": "a"},
        new_values={"name": "b"},
    )
    db.add(row)
    db.commit()
    return row


# --------------------------------------------------------------------------- #
# 1a. Audit list: filtering by the admin finds rows written while impersonating #
# --------------------------------------------------------------------------- #
def test_list_audit_logs_user_filter_matches_real_user_id():
    from app.services.audit_service import list_audit_logs

    with blank_session() as db:
        admin = _user(db, "Nurain Admin")
        target = _user(db, "Aisyah Target")
        row = _impersonated_row(db, admin, target)

        by_admin, total_admin = list_audit_logs(db, user_id=admin.id)
        by_target, _ = list_audit_logs(db, user_id=target.id)

        assert row.id in {str(r.id) for r in by_admin}, "the admin's impersonated write is hidden from the admin filter"
        assert total_admin >= 1
        assert row.id in {str(r.id) for r in by_target}


# --------------------------------------------------------------------------- #
# 1b. Activity feed: filter, label and actor list                              #
# --------------------------------------------------------------------------- #
def test_activity_feed_filters_and_labels_impersonated_rows():
    from app.services.activity_service import get_activity_feed

    with blank_session() as db:
        admin = _user(db, "Nurain Admin")
        target = _user(db, "Aisyah Target")
        db.commit()
        db.query(AuditLog).delete()
        db.commit()
        row = _impersonated_row(db, admin, target)

        out = get_activity_feed(db, user_id=admin.id)

        ids = [i["id"] for i in out["items"]]
        assert row.id in ids, "filtering the activity feed by the admin must find the impersonated write"
        item = next(i for i in out["items"] if i["id"] == row.id)
        assert item["actor_name"] == "Nurain Admin on behalf of Aisyah Target"
        assert admin.id in {a["id"] for a in out["actors"]}, "the admin must be selectable in the actor filter"


# --------------------------------------------------------------------------- #
# 1c. api_call_log.actor names both people under impersonation                 #
# --------------------------------------------------------------------------- #
def test_api_call_log_actor_label_names_real_and_effective_user():
    from app.middleware.api_call_log_middleware import _actor_label

    admin_id, target_id = str(uuid.uuid4()), str(uuid.uuid4())
    impersonating = AuditActor(actor_type="user", user_id=target_id, real_user_id=admin_id, auth_method="impersonation")
    plain = AuditActor(actor_type="user", user_id=target_id, real_user_id=target_id)
    integration = AuditActor(actor_type="integration", user_id=target_id, real_user_id=target_id, integration_id=admin_id)

    label = _actor_label({"audit_actor": impersonating})
    assert label == f"user:{admin_id}/as:{target_id}"
    assert len(label) <= 128
    assert _actor_label({"audit_actor": plain}) == f"user:{target_id}"
    assert _actor_label({"audit_actor": integration}) == f"integration:{admin_id}"


# --------------------------------------------------------------------------- #
# 2. X-Trace-Id is validated                                                   #
# --------------------------------------------------------------------------- #
_TRACE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def test_inbound_trace_id_is_kept_only_when_well_formed():
    client = TestClient(app)

    assert client.get("/health", headers={"X-Trace-Id": "inbound_42-ok"}).headers["X-Trace-Id"] == "inbound_42-ok"

    for bad in ("has space", "semi;colon", "<script>", "a" * 65, "dot.ted"):
        echoed = client.get("/health", headers={"X-Trace-Id": bad}).headers["X-Trace-Id"]
        assert echoed != bad, f"a malformed trace id was accepted: {bad!r}"
        assert _TRACE_RE.match(echoed), echoed


# --------------------------------------------------------------------------- #
# 4. 409 messages never name a person by phone                                 #
# --------------------------------------------------------------------------- #
def test_user_label_is_name_else_email_else_another_user():
    from app.services.user_service import user_label

    assert user_label(User(name="Aisyah", email="a@example.com", contact_number="60123456789")) == "Aisyah"
    assert user_label(User(name=" ", email="a@example.com", contact_number="60123456789")) == "a@example.com"
    assert user_label(User(name=None, email=None, contact_number="60123456789")) == "another user"


# --------------------------------------------------------------------------- #
# 5. X-Tool-Name control characters                                            #
# --------------------------------------------------------------------------- #
def test_tool_name_control_characters_are_stripped_before_the_cap():
    from app.dependencies import _stamp_integration_actor

    raw = b"crm\x01_x\x7f\x1fname" + b"y" * 200
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": [(b"x-tool-name", raw), (b"user-agent", b"ZZT")],
        "client": ("10.0.0.1", 1234),
        "query_string": b"",
    }
    request = Request(scope)

    with blank_session() as db:
        clear_actor(db)
        _stamp_integration_actor(request, db, {"id": str(uuid.uuid4()), "integration_id": str(uuid.uuid4())})
        tool = get_actor(db).tool_name

    assert tool is not None
    assert not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in tool), repr(tool)
    assert tool.startswith("crm_xname")
    assert len(tool) == 128
