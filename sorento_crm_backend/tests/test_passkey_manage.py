"""PASSKEY-LOGIN: adding, listing, renaming and removing passkeys, the per-user switch and
the re-check before adding (AC-06, AC-20 to AC-27, AC-30, AC-31, AC-33).

Authenticated routes under /api/v1/auth (`/passkeys...`) and the admin ones under
/api/v1/user-management/users. Removal is the deferred record action `user_passkey.delete`,
driven through the generic `/api/v1/pending-actions` route exactly as the frontend does it
(park, let the window lapse, poll `/current`, which commits an overdue action).

Every request runs on a real staff session (`mint_session` + Bearer), and permissions are
real role grants seeded per test, so nothing about RBAC is stubbed.

Postgres only, own seed chain per test (`tests/_passkey_env.py`).
Contract: documentation/plans/identity/passkey-login-12nov-acceptance-criteria.md
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from tests._passkey_env import (
    ALT_ORIGIN,
    IPHONE_SAFARI_UA,
    ITEM_KEYS,
    ORIGIN,
    PASSWORD,
    RP_ID,
    make_env,
)
from tests._soft_authenticator import SoftAuthenticator

USERS = "/api/v1/user-management/users"
PENDING = "/api/v1/pending-actions"
VIEW = "user_management.users.view"
EDIT = "user_management.users.edit"


@pytest.fixture()
def env(monkeypatch):
    yield from make_env(monkeypatch)


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _code(res) -> str | None:
    try:
        return res.json().get("code")
    except Exception:
        return None


def _park(env, headers, passkey_id):
    return env.client.post(
        PENDING,
        json={
            "action_key": "user_passkey.delete",
            "entity_type": "user_passkey",
            "entity_id": str(passkey_id),
            "payload": {},
        },
        headers=headers,
    )


def _lapse_and_poll(env, headers, passkey_id, action_id):
    """Close the window now, then read `/current`, which commits an overdue action."""
    from app.models.sla import SlaFormAction

    env.db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False
    )
    env.db.commit()
    res = env.client.get(
        f"{PENDING}/current",
        params={"entity_type": "user_passkey", "entity_id": str(passkey_id)},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


def _remove(env, headers, passkey_id):
    parked = _park(env, headers, passkey_id)
    assert parked.status_code == 202, parked.text
    return parked, _lapse_and_poll(env, headers, passkey_id, parked.json()["id"])


# --------------------------------------------------------------------------------------
# AC-06: users.passkey_enabled
# --------------------------------------------------------------------------------------


def test_ac06_passkey_enabled_is_not_null_default_false():
    from app.models.user import User

    col = User.__table__.c.passkey_enabled
    assert col.nullable is False
    assert col.server_default is not None and "false" in str(col.server_default.arg).lower()


def test_ac06_a_new_user_starts_switched_off(env):
    from app.models.user import User

    user = User(id=str(uuid.uuid4()), email=f"pk-default-{uuid.uuid4().hex[:8]}@example.com", name="ZZT", status="ACTIVE")
    env.db.add(user)
    env.db.commit()
    env.db.expire_all()
    assert env.db.query(User).filter(User.id == user.id).one().passkey_enabled is False


def test_ac06_get_user_and_get_me_return_passkey_enabled(env):
    admin = env.make_admin()
    on = env.make_user(passkey_enabled=True)
    off = env.make_user(passkey_enabled=False)

    for user, expected in ((on, True), (off, False)):
        res = env.client.get(f"{USERS}/{user.id}", headers=env.auth(admin))
        assert res.status_code == 200, res.text
        assert res.json().get("passkey_enabled") is expected

        me = env.client.get(f"{USERS}/me", headers=env.auth(user))
        assert me.status_code == 200, me.text
        assert me.json().get("passkey_enabled") is expected


# --------------------------------------------------------------------------------------
# AC-33: the admin switch
# --------------------------------------------------------------------------------------


def test_ac33_users_edit_turns_the_switch_on_and_off_and_it_is_audited(env):
    from app.models.user import User

    editor = env.make_user()
    env.grant(editor, EDIT, VIEW)
    target = env.make_user(passkey_enabled=False)

    res = env.client.patch(f"{USERS}/{target.id}/passkey-enabled", json={"enabled": True}, headers=env.auth(editor))
    assert res.status_code == 200, res.text
    assert res.json() == {"user_id": str(target.id), "passkey_enabled": True}
    env.db.expire_all()
    assert env.db.query(User).filter(User.id == target.id).one().passkey_enabled is True

    audit = env.audit_rows(entity_type="users", entity_id=target.id, action="UPDATE")
    assert any("passkey_enabled" in (a.new_values or {}) for a in audit), [a.new_values for a in audit]

    res = env.client.patch(f"{USERS}/{target.id}/passkey-enabled", json={"enabled": False}, headers=env.auth(editor))
    assert res.status_code == 200, res.text
    assert res.json()["passkey_enabled"] is False


def test_ac33_without_users_edit_is_403(env):
    from app.models.user import User

    viewer = env.make_user()
    env.grant(viewer, VIEW)
    target = env.make_user(passkey_enabled=False)

    res = env.client.patch(f"{USERS}/{target.id}/passkey-enabled", json={"enabled": True}, headers=env.auth(viewer))
    assert res.status_code == 403, res.text
    env.db.expire_all()
    assert env.db.query(User).filter(User.id == target.id).one().passkey_enabled is False


def test_ac33_an_admin_may_switch_their_own_row(env):
    editor = env.make_user(passkey_enabled=False)
    env.grant(editor, EDIT)
    res = env.client.patch(f"{USERS}/{editor.id}/passkey-enabled", json={"enabled": True}, headers=env.auth(editor))
    assert res.status_code == 200, res.text
    assert res.json() == {"user_id": str(editor.id), "passkey_enabled": True}


def test_ac33_enabled_is_required(env):
    editor = env.make_user()
    env.grant(editor, EDIT)
    res = env.client.patch(f"{USERS}/{editor.id}/passkey-enabled", json={}, headers=env.auth(editor))
    assert res.status_code == 422, res.text


# --------------------------------------------------------------------------------------
# AC-20: own list
# --------------------------------------------------------------------------------------


def test_ac20_lists_only_own_passkeys_newest_first_without_key_material(env):
    me = env.make_user()
    other = env.make_user()
    older, _ = env.seed_passkey(me, name="Older", created_at=datetime.utcnow() - timedelta(days=3))
    newer, _ = env.seed_passkey(me, name="Newer", created_at=datetime.utcnow() - timedelta(hours=1))
    env.seed_passkey(other, name="Not mine")

    res = env.client.get("/api/v1/auth/passkeys", headers=env.auth(me))

    assert res.status_code == 200, res.text
    items = res.json()
    assert [i["name"] for i in items] == ["Newer", "Older"]
    assert [i["id"] for i in items] == [str(newer.id), str(older.id)]
    for item in items:
        assert set(item) == ITEM_KEYS, item
        assert item["last_used_at"] is None


def test_ac20_while_impersonating_the_list_is_the_real_users(env):
    admin = env.make_admin()
    target = env.make_user()
    env.seed_passkey(admin, name="Admin key")
    env.seed_passkey(target, name="Target key")

    res = env.client.get("/api/v1/auth/passkeys", headers=env.impersonate(admin, target))

    assert res.status_code == 200, res.text
    assert [i["name"] for i in res.json()] == ["Admin key"]


def test_ac20_list_needs_a_session(env):
    res = env.client.get("/api/v1/auth/passkeys")
    assert res.status_code == 401, res.text


# --------------------------------------------------------------------------------------
# AC-26: switch OFF
# --------------------------------------------------------------------------------------


def test_ac26_switch_off_lists_nothing_even_with_stored_passkeys(env):
    me = env.make_user(passkey_enabled=False)
    env.seed_passkey(me)
    res = env.client.get("/api/v1/auth/passkeys", headers=env.auth(me))
    assert res.status_code == 200, res.text
    assert res.json() == []


def test_ac26_switch_off_refuses_register_options(env):
    me = env.make_user(passkey_enabled=False)
    res = env.register_options(env.auth(me))
    assert res.status_code == 403, res.text
    assert _code(res) == "PASSKEY_NOT_ENABLED"


def test_ac26_switch_off_refuses_register(env):
    me = env.make_user()
    challenge_id, options = env.register_challenge(me)
    from app.models.user import User

    env.db.query(User).filter(User.id == me.id).update({User.passkey_enabled: False}, synchronize_session=False)
    env.db.commit()

    res = env.register(env.auth(me), challenge_id, env.registration(SoftAuthenticator(), options["challenge"]))
    assert res.status_code == 403, res.text
    assert _code(res) == "PASSKEY_NOT_ENABLED"
    assert env.passkeys_of(me.id) == []


def test_ac26_switch_off_refuses_reauth_code(env):
    me = env.make_user(passkey_enabled=False)
    res = env.client.post("/api/v1/auth/passkeys/reauth-code", headers=env.auth(me))
    assert res.status_code == 403, res.text
    assert _code(res) == "PASSKEY_NOT_ENABLED"


def test_ac26_switch_off_refuses_rename(env):
    me = env.make_user(passkey_enabled=False)
    row, _ = env.seed_passkey(me, name="Before")
    res = env.client.patch(f"/api/v1/auth/passkeys/{row.id}", json={"name": "After"}, headers=env.auth(me))
    assert res.status_code == 403, res.text
    assert _code(res) == "PASSKEY_NOT_ENABLED"
    assert env.passkey(row.id).name == "Before"


def test_ac26_switch_off_still_lets_you_remove_your_own(env):
    me = env.make_user(passkey_enabled=False)
    row, _ = env.seed_passkey(me)
    headers = env.auth(me)
    _parked, body = _remove(env, headers, row.id)
    assert body["last_outcome"]["status"] == "committed", body
    assert env.passkey(row.id) is None


# --------------------------------------------------------------------------------------
# AC-27: re-check before adding
# --------------------------------------------------------------------------------------


@pytest.fixture()
def phone_user(env, monkeypatch):
    """An ACTIVE, passkey-enabled user with a verified phone linked to its own WhatsApp
    contact, plus a fixed OTP (`424242`) and a recorded (not sent) Respond.io dispatch."""
    from app.models.access import RespondContact
    from app.models.respond_workspace import RespondWorkspace
    from app.services.queue_service import redis_conn

    digits = "601" + f"{uuid.uuid4().int % 10**8:08d}"
    ws = RespondWorkspace(
        id=str(uuid.uuid4()), space_id=f"sp_{uuid.uuid4().hex[:8]}", name="ZZT WS", api_key_ciphertext="test-cipher"
    )
    env.db.add(ws)
    env.db.flush()
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=digits, name="ZZT Contact", workspace_id=ws.id)
    env.db.add(contact)
    env.db.flush()
    user = env.make_user(
        password=None,
        contact_number=digits,
        respond_contact_id=contact.id,
        phone_verified_at=datetime.utcnow() - timedelta(days=1),
    )

    sent: list = []
    monkeypatch.setattr("app.services.portal_service.secrets.randbelow", lambda _n: 424242)
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: sent.append((a, k)))
    yield user, digits, sent
    for key in redis_conn.keys(f"*{digits}*"):
        redis_conn.delete(key)


def test_ac27_right_password_issues_the_registration_challenge(env):
    me = env.make_user()
    res = env.register_options(env.auth(me), {"password": PASSWORD})
    assert res.status_code == 200, res.text
    assert res.json()["challenge_id"]


def test_ac27_wrong_password_is_401_and_counted_in_the_login_throttle(env, monkeypatch):
    from app.services import login_throttle

    me = env.make_user()
    failures: list = []
    real = login_throttle.record_failure
    monkeypatch.setattr(login_throttle, "record_failure", lambda email, ip: (failures.append(email), real(email, ip)))
    try:
        res = env.register_options(env.auth(me), {"password": "not-the-password"})
    finally:
        login_throttle.clear(me.email, "testclient")

    assert res.status_code == 401, res.text
    assert res.json().get("code") == "REAUTH_FAILED"
    assert res.json().get("message") == "That password is not right."
    assert "challenge_id" not in res.text
    assert [str(e).lower() for e in failures] == [me.email.lower()]


def test_ac27_locked_login_throttle_is_429(env, monkeypatch):
    from app.services import login_throttle

    me = env.make_user()
    monkeypatch.setattr(
        login_throttle, "check", lambda email, ip: login_throttle.ThrottleResult(allowed=False, retry_after_seconds=60)
    )
    res = env.register_options(env.auth(me), {"password": PASSWORD})
    assert res.status_code == 429, res.text
    assert "challenge_id" not in res.text


def test_ac27_neither_password_nor_phone_code_is_422(env):
    me = env.make_user()
    res = env.register_options(env.auth(me), {})
    assert res.status_code == 422, res.text


def test_ac27_a_user_without_a_password_cannot_use_the_password_path(env):
    me = env.make_user(password=None)
    res = env.register_options(env.auth(me), {"password": PASSWORD})
    assert res.status_code == 401, res.text
    assert res.json().get("code") == "REAUTH_FAILED"
    assert "challenge_id" not in res.text


def test_ac27_reauth_code_without_a_verified_phone_is_no_phone(env):
    me = env.make_user()  # email + password, no phone
    res = env.client.post("/api/v1/auth/passkeys/reauth-code", headers=env.auth(me))
    assert res.status_code == 400, res.text
    assert res.json().get("code") == "NO_PHONE"


def test_ac27_phone_code_sent_to_own_phone_issues_the_challenge(env, phone_user):
    user, _digits, sent = phone_user
    headers = env.auth(user)

    sent_res = env.client.post("/api/v1/auth/passkeys/reauth-code", headers=headers)
    assert sent_res.status_code == 200, sent_res.text
    assert sent, "AC-27: the code goes out through the phone sign-in send path"

    res = env.register_options(headers, {"phone_code": "424242"})
    assert res.status_code == 200, res.text
    assert res.json()["challenge_id"]


def test_ac27_wrong_phone_code_is_401(env, phone_user):
    user, _digits, _sent = phone_user
    headers = env.auth(user)
    assert env.client.post("/api/v1/auth/passkeys/reauth-code", headers=headers).status_code == 200

    res = env.register_options(headers, {"phone_code": "000000"})
    assert res.status_code == 401, res.text
    assert res.json().get("code") == "REAUTH_FAILED"
    assert str(res.json().get("message", "")).startswith("That code is not right.")
    assert "challenge_id" not in res.text


def test_ac27_phone_code_attempt_budget_ends_in_429(env, phone_user):
    from app.services.phone_signin_service import MAX_WRONG_ATTEMPTS

    user, _digits, _sent = phone_user
    headers = env.auth(user)
    assert env.client.post("/api/v1/auth/passkeys/reauth-code", headers=headers).status_code == 200

    statuses = [
        env.register_options(headers, {"phone_code": "000000"}).status_code for _ in range(MAX_WRONG_ATTEMPTS + 1)
    ]
    assert statuses[0] == 401, statuses
    assert 429 in statuses, statuses
    # Spent: even the right code is refused now.
    assert env.register_options(headers, {"phone_code": "424242"}).status_code == 429


def test_ac27_reauth_code_cannot_be_used_to_sign_in(env, phone_user):
    user, digits, _sent = phone_user
    headers = env.auth(user)
    assert env.client.post("/api/v1/auth/passkeys/reauth-code", headers=headers).status_code == 200
    before = len(env.sessions(user.id))

    res = env.client.post("/api/v1/auth/phone/verify", json={"phone": digits, "code": "424242"})

    assert res.status_code != 200, res.text
    assert len(env.sessions(user.id)) == before


# --------------------------------------------------------------------------------------
# AC-21: registration options
# --------------------------------------------------------------------------------------


def test_ac21_registration_options_shape_and_exclude_existing(env):
    me = env.make_user()
    existing, _ = env.seed_passkey(me)
    other = env.make_user()
    env.seed_passkey(other)

    res = env.register_options(env.auth(me, origin=ALT_ORIGIN))

    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["challenge_id"], str) and body["challenge_id"]
    opts = body["options"]
    assert opts["rp"]["id"] == RP_ID
    assert opts["authenticatorSelection"]["residentKey"] == "required"
    assert opts["authenticatorSelection"]["userVerification"] == "required"
    assert [c["id"] for c in opts["excludeCredentials"]] == [existing.credential_id]
    assert any(p.get("alg") == -7 for p in opts["pubKeyCredParams"]), "ES256 must be offered"


def test_ac21_registration_options_refused_while_impersonating(env):
    admin = env.make_admin()
    target = env.make_user()
    res = env.register_options(env.impersonate(admin, target))
    assert res.status_code == 403, res.text
    assert "challenge_id" not in res.text


def test_ac21_registration_options_need_a_session(env):
    res = env.client.post("/api/v1/auth/passkeys/register/options", json={"password": PASSWORD}, headers={"Origin": ORIGIN})
    assert res.status_code == 401, res.text


# --------------------------------------------------------------------------------------
# AC-22: registering
# --------------------------------------------------------------------------------------


def test_ac22_register_stores_the_passkey_named_after_the_device(env):
    me = env.make_user()
    headers = env.auth(me)
    auth = SoftAuthenticator()
    challenge_id, options = env.register_challenge(me)

    res = env.register(headers, challenge_id, env.registration(auth, options["challenge"], sign_count=0))

    assert res.status_code == 201, res.text
    item = res.json()
    assert set(item) == ITEM_KEYS, item
    assert item["name"] == "Safari on iPhone"
    assert item["last_used_at"] is None

    rows = env.passkeys_of(me.id)
    assert len(rows) == 1
    row = rows[0]
    assert str(row.id) == item["id"]
    assert row.credential_id == auth.credential_id_b64
    assert row.public_key
    assert row.sign_count == 0
    assert row.backed_up is True


def test_ac22_register_keeps_a_given_name(env):
    me = env.make_user()
    challenge_id, options = env.register_challenge(me)
    res = env.register(env.auth(me), challenge_id, env.registration(SoftAuthenticator(), options["challenge"]), name="Work laptop")
    assert res.status_code == 201, res.text
    assert res.json()["name"] == "Work laptop"


def test_ac22_the_same_credential_twice_is_409(env):
    me = env.make_user()
    headers = env.auth(me)
    auth = SoftAuthenticator()
    cid1, opts1 = env.register_challenge(me)
    assert env.register(headers, cid1, env.registration(auth, opts1["challenge"])).status_code == 201

    cid2, opts2 = env.register_challenge(me)
    res = env.register(headers, cid2, env.registration(auth, opts2["challenge"]))
    assert res.status_code == 409, res.text
    assert len(env.passkeys_of(me.id)) == 1


def test_ac22_a_credential_another_user_holds_is_409(env):
    me = env.make_user()
    other = env.make_user()
    _row, auth = env.seed_passkey(other)
    challenge_id, options = env.register_challenge(me)
    res = env.register(env.auth(me), challenge_id, env.registration(auth, options["challenge"]))
    assert res.status_code == 409, res.text
    assert env.passkeys_of(me.id) == []


def test_ac22_another_users_challenge_is_refused(env):
    owner = env.make_user()
    thief = env.make_user()
    challenge_id, options = env.register_challenge(owner)
    res = env.register(env.auth(thief), challenge_id, env.registration(SoftAuthenticator(), options["challenge"]))
    assert res.status_code == 400, res.text
    assert _code(res) == "PASSKEY_FAILED"
    assert env.passkeys_of(thief.id) == [] and env.passkeys_of(owner.id) == []


def test_ac22_replayed_registration_challenge_is_refused(env):
    me = env.make_user()
    headers = env.auth(me)
    challenge_id, options = env.register_challenge(me)
    assert env.register(headers, challenge_id, env.registration(SoftAuthenticator(), options["challenge"])).status_code == 201

    res = env.register(headers, challenge_id, env.registration(SoftAuthenticator(), options["challenge"]))
    assert res.status_code == 400, res.text
    assert _code(res) == "PASSKEY_FAILED"
    assert len(env.passkeys_of(me.id)) == 1


def test_ac22_wrong_origin_is_refused(env):
    me = env.make_user()
    challenge_id, options = env.register_challenge(me, origin=ORIGIN)
    res = env.register(
        env.auth(me), challenge_id, env.registration(SoftAuthenticator(), options["challenge"], origin=ALT_ORIGIN)
    )
    assert res.status_code == 400, res.text
    assert _code(res) == "PASSKEY_FAILED"
    assert env.passkeys_of(me.id) == []


def test_ac22_a_sign_in_challenge_cannot_register(env):
    me = env.make_user()
    challenge_id, challenge = env.sign_in_challenge()
    res = env.register(env.auth(me), challenge_id, env.registration(SoftAuthenticator(), challenge))
    assert res.status_code == 400, res.text
    assert _code(res) == "PASSKEY_FAILED"
    assert env.passkeys_of(me.id) == []


def test_ac22_register_refused_while_impersonating(env):
    admin = env.make_admin()
    target = env.make_user()
    # The admin's own (non-impersonating) challenge, presented while viewing as the target.
    challenge_id, options = env.register_challenge(admin)
    res = env.register(env.impersonate(admin, target), challenge_id, env.registration(SoftAuthenticator(), options["challenge"]))
    assert res.status_code == 403, res.text
    assert env.passkeys_of(admin.id) == [] and env.passkeys_of(target.id) == []


def test_ac22_missing_credential_is_422(env):
    me = env.make_user()
    res = env.client.post("/api/v1/auth/passkeys", json={"challenge_id": "x"}, headers=env.auth(me))
    assert res.status_code == 422, res.text


# --------------------------------------------------------------------------------------
# AC-23: rename
# --------------------------------------------------------------------------------------


def test_ac23_rename_own_passkey_trims_the_name(env):
    me = env.make_user()
    row, _ = env.seed_passkey(me, name="Before")
    res = env.client.patch(f"/api/v1/auth/passkeys/{row.id}", json={"name": "  Work laptop  "}, headers=env.auth(me))
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Work laptop"
    assert set(res.json()) == ITEM_KEYS
    assert env.passkey(row.id).name == "Work laptop"


def test_ac23_rename_accepts_exactly_100_chars(env):
    me = env.make_user()
    row, _ = env.seed_passkey(me)
    res = env.client.patch(f"/api/v1/auth/passkeys/{row.id}", json={"name": "a" * 100}, headers=env.auth(me))
    assert res.status_code == 200, res.text


def test_ac23_renaming_someone_elses_passkey_is_404(env):
    me = env.make_user()
    other = env.make_user()
    row, _ = env.seed_passkey(other, name="Theirs")
    res = env.client.patch(f"/api/v1/auth/passkeys/{row.id}", json={"name": "Mine now"}, headers=env.auth(me))
    assert res.status_code == 404, res.text
    assert env.passkey(row.id).name == "Theirs"


def test_ac23_renaming_an_unknown_id_is_404(env):
    me = env.make_user()
    res = env.client.patch(f"/api/v1/auth/passkeys/{uuid.uuid4()}", json={"name": "x"}, headers=env.auth(me))
    assert res.status_code == 404, res.text


@pytest.mark.parametrize("name", ["", "   ", "a" * 101], ids=["empty", "blank", "101_chars"])
def test_ac23_invalid_name_is_422(env, name):
    me = env.make_user()
    row, _ = env.seed_passkey(me, name="Before")
    res = env.client.patch(f"/api/v1/auth/passkeys/{row.id}", json={"name": name}, headers=env.auth(me))
    assert res.status_code == 422, res.text
    assert env.passkey(row.id).name == "Before"


# --------------------------------------------------------------------------------------
# AC-24 / AC-31: removal through the deferred record action
# --------------------------------------------------------------------------------------


def test_ac24_user_passkey_delete_is_a_registered_destructive_record_action():
    from app.services import record_actions  # noqa: F401  registers the actions
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE, window_class_for
    from app.services.form_action_registry import REGISTRY

    action = REGISTRY.get("user_passkey.delete")
    assert action is not None, "AC-24: user_passkey.delete is not registered"
    assert action.entity_types == ("user_passkey",)
    assert action.permission, "a record action must declare its park-time permission"
    assert window_class_for(action) == WINDOW_DESTRUCTIVE


def test_ac24_removing_your_own_passkey_needs_no_permission_and_hard_deletes(env):
    me = env.make_user()  # no role at all
    row, _ = env.seed_passkey(me)
    headers = env.auth(me)

    parked = _park(env, headers, row.id)
    assert parked.status_code == 202, parked.text
    assert parked.json()["window_seconds"] == 10, "destructive window, not the short one"
    assert env.passkey(row.id) is not None, "nothing happens until the window lapses"

    body = _lapse_and_poll(env, headers, row.id, parked.json()["id"])
    assert body["last_outcome"]["status"] == "committed", body
    assert env.passkey(row.id) is None


def test_ac24_removing_someone_elses_passkey_without_users_edit_is_403(env):
    me = env.make_user()
    env.grant(me, VIEW)
    other = env.make_user()
    row, _ = env.seed_passkey(other)

    res = _park(env, env.auth(me), row.id)

    assert res.status_code == 403, res.text
    assert env.passkey(row.id) is not None


def test_ac31_users_edit_removes_someone_elses_passkey(env):
    editor = env.make_user()
    env.grant(editor, EDIT)
    other = env.make_user()
    row, _ = env.seed_passkey(other)
    headers = env.auth(editor)

    _parked, body = _remove(env, headers, row.id)

    assert body["last_outcome"]["status"] == "committed", body
    assert env.passkey(row.id) is None


def test_ac24_removing_an_unknown_passkey_is_refused_at_park_time(env):
    editor = env.make_user()
    env.grant(editor, EDIT)
    res = _park(env, env.auth(editor), uuid.uuid4())
    assert res.status_code in (403, 404), res.text


# --------------------------------------------------------------------------------------
# AC-25: audit of add, rename, remove
# --------------------------------------------------------------------------------------


def test_ac25_add_rename_and_remove_each_leave_an_audit_row(env):
    me = env.make_user()
    headers = env.auth(me)
    challenge_id, options = env.register_challenge(me)
    created = env.register(headers, challenge_id, env.registration(SoftAuthenticator(), options["challenge"]))
    assert created.status_code == 201, created.text
    pk_id = created.json()["id"]
    assert env.audit_rows(entity_type="user_passkeys", entity_id=pk_id, action="CREATE"), "add not audited"

    renamed = env.client.patch(f"/api/v1/auth/passkeys/{pk_id}", json={"name": "Renamed"}, headers=headers)
    assert renamed.status_code == 200, renamed.text
    assert env.audit_rows(entity_type="user_passkeys", entity_id=pk_id, action="UPDATE"), "rename not audited"

    _parked, body = _remove(env, headers, pk_id)
    assert body["last_outcome"]["status"] == "committed", body
    assert env.audit_rows(entity_type="user_passkeys", entity_id=pk_id, action="DELETE"), "remove not audited"


def test_ac25_audit_never_stores_key_material(env):
    me = env.make_user()
    challenge_id, options = env.register_challenge(me)
    created = env.register(env.auth(me), challenge_id, env.registration(SoftAuthenticator(), options["challenge"]))
    assert created.status_code == 201, created.text
    rows = env.audit_rows(entity_type="user_passkeys", entity_id=created.json()["id"])
    assert rows
    for row in rows:
        assert "public_key" not in (row.new_values or {}), "raw key bytes in the audit log"


# --------------------------------------------------------------------------------------
# AC-30: admin list
# --------------------------------------------------------------------------------------


def test_ac30_users_view_lists_that_users_passkeys(env):
    viewer = env.make_user()
    env.grant(viewer, VIEW)
    target = env.make_user()
    env.seed_passkey(target, name="Target key")
    env.seed_passkey(viewer, name="Viewer key")

    res = env.client.get(f"{USERS}/{target.id}/passkeys", headers=env.auth(viewer))

    assert res.status_code == 200, res.text
    items = res.json()
    assert [i["name"] for i in items] == ["Target key"]
    assert set(items[0]) == ITEM_KEYS


def test_ac30_admin_list_without_users_view_is_403(env):
    nobody = env.make_user()
    target = env.make_user()
    env.seed_passkey(target)
    res = env.client.get(f"{USERS}/{target.id}/passkeys", headers=env.auth(nobody))
    assert res.status_code == 403, res.text


def test_ac22_default_name_follows_the_user_agent():
    """The default name is `device_label_from_ua`, unchanged ("Safari on iPhone")."""
    from app.services.user_session_service import device_label_from_ua

    assert device_label_from_ua(IPHONE_SAFARI_UA) == "Safari on iPhone"
