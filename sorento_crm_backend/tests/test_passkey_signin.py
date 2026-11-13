"""PASSKEY-LOGIN: signing in with a passkey (AC-03, AC-10 to AC-15, AC-32).

Unauthenticated routes under /api/v1/auth: `GET /passkey/status`, `POST /passkey/options`,
`POST /passkey/verify`. Assertions are built by the software authenticator
(`tests/_soft_authenticator.py`), so every refusal is one deliberate defect in an otherwise
valid assertion. Every AC-12 refusal is its own test and asserts the same thing: 401, the
PASSKEY_FAILED body byte-identical to an unknown-challenge refusal, and no passkey session.

Postgres only, own seed chain per test (`tests/_passkey_env.py`).
Contract: documentation/plans/identity/passkey-login-12nov-acceptance-criteria.md
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from tests._passkey_env import (
    ALT_ORIGIN,
    ORIGIN,
    OTHER_RP_ID,
    PASSKEY_FAILED,
    RP_ID,
    make_env,
    recent,
)
from tests._soft_authenticator import SoftAuthenticator, b64url


@pytest.fixture()
def env(monkeypatch):
    yield from make_env(monkeypatch)


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _baseline(env):
    """The refusal every AC-12 case must match byte for byte: an unknown challenge id."""
    auth = SoftAuthenticator()
    res = env.verify(
        f"unknown-{uuid.uuid4().hex}",
        auth.authentication_response(challenge=b64url(b"x" * 32), origin=ORIGIN, rp_id=RP_ID, user_handle=b"u"),
    )
    assert res.status_code == 401, res.text
    return res


def _assert_refused(env, res, user, baseline=None):
    assert res.status_code == 401, res.text
    body = res.json()
    assert body.get("code") == PASSKEY_FAILED["code"], body
    assert body.get("message") == PASSKEY_FAILED["message"], body
    base = baseline if baseline is not None else _baseline(env)
    assert res.content == base.content, "AC-12: refusal bodies must be byte-identical"
    assert [s for s in env.sessions(user.id) if s.auth_method == "passkey"] == [], "no session minted"


def _enabled_user_with_passkey(env, **kw):
    user = env.make_user(**kw)
    row, auth = env.seed_passkey(user)
    return user, row, auth


# --------------------------------------------------------------------------------------
# AC-03: configuration switch
# --------------------------------------------------------------------------------------


def test_ac03_status_reports_enabled_from_the_hostname_list(env, monkeypatch):
    from app.config import settings

    res = env.client.get("/api/v1/auth/passkey/status")
    assert res.status_code == 200, res.text
    assert res.json() == {"enabled": True}

    monkeypatch.setattr(settings, "webauthn_rp_ids", "")
    res = env.client.get("/api/v1/auth/passkey/status")
    assert res.status_code == 200, res.text
    assert res.json() == {"enabled": False}


def test_ac03_empty_list_answers_passkeys_unavailable_on_every_route_but_the_list(env, monkeypatch):
    from app.config import settings

    user = env.make_user()
    headers = env.auth(user)
    monkeypatch.setattr(settings, "webauthn_rp_ids", "")

    calls = {
        "options": env.client.post("/api/v1/auth/passkey/options", headers={"Origin": ORIGIN}),
        "verify": env.client.post(
            "/api/v1/auth/passkey/verify",
            json={"challenge_id": "x", "credential": {"id": "x", "rawId": "x", "type": "public-key", "response": {}}},
            headers={"Origin": ORIGIN},
        ),
        "register_options": env.register_options(headers),
        "register": env.client.post(
            "/api/v1/auth/passkeys",
            json={"challenge_id": "x", "credential": {"id": "x", "rawId": "x", "type": "public-key", "response": {}}},
            headers=headers,
        ),
        "reauth_code": env.client.post("/api/v1/auth/passkeys/reauth-code", headers=headers),
    }
    for name, res in calls.items():
        assert res.status_code == 400, f"{name}: {res.status_code} {res.text}"
        assert res.json().get("code") == "PASSKEYS_UNAVAILABLE", f"{name}: {res.text}"

    listed = env.client.get("/api/v1/auth/passkeys", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json() == []


# --------------------------------------------------------------------------------------
# AC-10: sign-in options
# --------------------------------------------------------------------------------------


def test_ac10_options_are_discoverable_with_uv_required(env):
    res = env.sign_in_options(ORIGIN)
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["challenge_id"], str) and body["challenge_id"]
    opts = body["options"]
    assert opts["rpId"] == RP_ID
    assert opts["userVerification"] == "required"
    assert opts.get("allowCredentials", []) == [], "no email asked, so nothing to enumerate"
    assert isinstance(opts["challenge"], str) and len(opts["challenge"]) >= 22  # >= 16 random bytes

    second = env.sign_in_options(ORIGIN).json()
    assert second["challenge_id"] != body["challenge_id"]
    assert second["options"]["challenge"] != opts["challenge"]


@pytest.mark.parametrize(
    "origin, rp_id",
    [(ALT_ORIGIN, RP_ID), (f"https://{OTHER_RP_ID}", OTHER_RP_ID), ("http://localhost:3000", "localhost")],
    ids=["https_with_port", "second_listed_host", "http_localhost"],
)
def test_ac10_rp_id_is_the_origin_hostname(env, origin, rp_id):
    res = env.sign_in_options(origin)
    assert res.status_code == 200, res.text
    assert res.json()["options"]["rpId"] == rp_id


@pytest.mark.parametrize("origin", ["http://crm.example.test", "https://evil.example.test", None])
def test_ac02_options_issue_no_challenge_for_a_refused_origin(env, origin):
    headers = {"Origin": origin} if origin else {}
    res = env.client.post("/api/v1/auth/passkey/options", headers=headers)
    assert 400 <= res.status_code < 500, res.text
    assert "challenge_id" not in res.text


def test_ac10_options_are_rate_limited_per_ip_when_trusted_proxies_is_set(env, monkeypatch):
    """AC-10 (review round, M1): the per-IP gate only runs when the IP is the real client."""
    from app.config import settings

    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.0/8")
    env.deny_rate = True
    res = env.sign_in_options(ORIGIN)
    assert res.status_code == 429, res.text
    assert "challenge_id" not in res.text


def test_ac10_no_per_ip_gate_when_trusted_proxies_is_unset(env, monkeypatch):
    """Every request would share the proxy's address, so one caller could 429 every staff
    sign-in: with `trusted_proxies` unset the options route consults no per-IP limiter."""
    from app.config import settings

    monkeypatch.setattr(settings, "trusted_proxies", "")
    env.deny_rate = True
    res = env.sign_in_options(ORIGIN)
    assert res.status_code == 200, res.text
    assert env.rate_buckets == [], f"per-IP limiter consulted: {env.rate_buckets}"


def test_ac10_forty_rapid_options_calls_all_answer_200_without_trusted_proxies(env, monkeypatch):
    """Against the REAL limiter: 40 calls from one address in a burst are all served."""
    from app.config import settings
    from app.services import rate_limit
    from app.services.queue_service import redis_conn

    monkeypatch.setattr(settings, "trusted_proxies", "")
    monkeypatch.setattr(rate_limit, "hit", env.real_hit)
    try:
        statuses = [env.sign_in_options(ORIGIN).status_code for _ in range(40)]
    finally:
        for key in redis_conn.keys("rate_limit:v1:*passkey*"):
            redis_conn.delete(key)
    assert statuses == [200] * 40, statuses


# --------------------------------------------------------------------------------------
# AC-14: verify rate limit, Redis down
# --------------------------------------------------------------------------------------


def test_ac14_verify_has_no_per_ip_limit(env, monkeypatch):
    """AC-14 (review round): verify is called server-to-server by NextAuth; the single-use
    challenge and the signature bound it, not a per-IP bucket (same as `/phone/verify`).
    Even with trusted proxies set and every limiter saying no, a valid assertion signs in."""
    from app.config import settings

    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.0/8")
    user, _row, auth = _enabled_user_with_passkey(env)
    challenge_id, challenge = env.sign_in_challenge()

    env.rate_buckets.clear()
    env.deny_rate = True
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=1))
    assert res.status_code == 200, res.text
    assert env.rate_buckets == [], f"verify consulted a per-IP limiter: {env.rate_buckets}"


def test_ac14_redis_down_options_fail_closed(env):
    env.break_redis()
    res = env.sign_in_options(ORIGIN)
    assert res.status_code == 400, res.text
    assert res.json().get("code") == "PASSKEYS_UNAVAILABLE"


def test_ac14_redis_down_verify_never_accepts_an_assertion(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    challenge_id, challenge = env.sign_in_challenge()
    env.break_redis()
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=1))
    assert res.status_code == 400, res.text
    assert res.json().get("code") == "PASSKEYS_UNAVAILABLE"
    assert [s for s in env.sessions(user.id) if s.auth_method == "passkey"] == []


def test_verify_without_challenge_id_is_422(env):
    res = env.client.post("/api/v1/auth/passkey/verify", json={"credential": {}}, headers={"Origin": ORIGIN})
    assert res.status_code == 422, res.text


# --------------------------------------------------------------------------------------
# AC-11: the happy path
# --------------------------------------------------------------------------------------


def test_ac11_valid_assertion_signs_in_with_a_passkey_session(env):
    from app.models.user import User
    from app.services.user_session_service import REMEMBER_TTL, _utcnow

    user, row, auth = _enabled_user_with_passkey(env)
    challenge_id, challenge = env.sign_in_challenge()

    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=7))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == str(user.id)
    assert body["email"] == user.email
    assert body["status"] == "ACTIVE"
    assert body["token"]
    for key in ("role_id", "role_ids", "home_path", "name"):
        assert key in body, f"LoginResponse field {key} missing"

    sessions = env.sessions(user.id)
    assert len(sessions) == 1
    session = sessions[0]
    assert session.token == body["token"]
    assert session.auth_method == "passkey"
    assert session.rolling is True
    assert timedelta(days=29, hours=23) < session.expires_at - _utcnow() <= REMEMBER_TTL + timedelta(minutes=1)

    stored = env.db.query(User).filter(User.id == user.id).one()
    assert recent(stored.last_sign_in_at)
    pk = env.passkey(row.id)
    assert pk.sign_count == 7
    assert recent(pk.last_used_at)

    audit = env.audit_rows(entity_type="user_passkeys", event="passkey_sign_in")
    assert len(audit) == 1, [(a.entity_type, a.event, a.user_id) for a in audit]
    assert audit[0].user_id == str(user.id)

    # The token is a working staff session.
    me = env.client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200, me.text


def test_ac11_zero_sign_count_authenticators_keep_working(env):
    """Synced passkeys (iCloud Keychain, Google Password Manager) always report 0."""
    user, row, auth = _enabled_user_with_passkey(env)
    for _ in range(2):
        challenge_id, challenge = env.sign_in_challenge()
        res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=0))
        assert res.status_code == 200, res.text
    assert env.passkey(row.id).sign_count == 0


def test_ac11_a_passkey_added_through_the_route_signs_in(env):
    """End to end: registered via AC-21/AC-22 (the implementation's own storage format),
    then used to sign in."""
    user = env.make_user()
    headers = env.auth(user)
    auth = SoftAuthenticator()
    reg_id, reg_options = env.register_challenge(user)
    created = env.register(headers, reg_id, env.registration(auth, reg_options["challenge"]))
    assert created.status_code == 201, created.text

    challenge_id, challenge = env.sign_in_challenge()
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=1))
    assert res.status_code == 200, res.text
    assert res.json()["id"] == str(user.id)


def test_ac32_last_sign_in_method_reads_passkey(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    admin = env.make_admin()
    challenge_id, challenge = env.sign_in_challenge()
    assert env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=1)).status_code == 200

    res = env.client.get(f"/api/v1/user-management/users/{user.id}", headers=env.auth(admin))
    assert res.status_code == 200, res.text
    assert res.json().get("last_sign_in_method") == "passkey"


# --------------------------------------------------------------------------------------
# AC-12: every refusal, one test each
# --------------------------------------------------------------------------------------


def test_ac12_unknown_challenge_id_is_refused(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    _cid, challenge = env.sign_in_challenge()
    res = env.verify(f"nope-{uuid.uuid4().hex}", env.assertion(auth, user, challenge, sign_count=1))
    _assert_refused(env, res, user)


def test_ac12_replayed_challenge_is_refused(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    challenge_id, challenge = env.sign_in_challenge()
    first = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=1))
    assert first.status_code == 200, first.text
    before = len(env.sessions(user.id))

    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=2))

    assert res.status_code == 401, res.text
    assert res.content == _baseline(env).content
    assert len(env.sessions(user.id)) == before, "replay minted a second session"


def test_ac12_registration_challenge_cannot_sign_in(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    reg_id, reg_options = env.register_challenge(user)
    res = env.verify(reg_id, env.assertion(auth, user, reg_options["challenge"], sign_count=1))
    _assert_refused(env, res, user)


def test_ac12_client_data_origin_differs_from_stored_origin(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    challenge_id, challenge = env.sign_in_challenge(ORIGIN)
    # ALT_ORIGIN is itself an allowed origin for the same RP ID: only the stored origin differs.
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, origin=ALT_ORIGIN, sign_count=1))
    _assert_refused(env, res, user)


def test_ac12_rp_id_hash_for_another_hostname_is_refused(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    challenge_id, challenge = env.sign_in_challenge(ORIGIN)
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, rp_id=OTHER_RP_ID, sign_count=1))
    _assert_refused(env, res, user)


def test_ac12_unknown_credential_id_is_refused(env):
    user, _row, _auth = _enabled_user_with_passkey(env)
    stranger = SoftAuthenticator()  # never registered
    challenge_id, challenge = env.sign_in_challenge()
    res = env.verify(challenge_id, env.assertion(stranger, user, challenge, sign_count=1))
    _assert_refused(env, res, user)


def test_ac12_signature_by_a_different_key_is_refused(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    challenge_id, challenge = env.sign_in_challenge()
    forged = env.assertion(
        auth, user, challenge, sign_count=1, signing_key=ec.generate_private_key(ec.SECP256R1())
    )
    res = env.verify(challenge_id, forged)
    _assert_refused(env, res, user)


def test_ac12_wrong_challenge_bytes_in_client_data_are_refused(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    challenge_id, _challenge = env.sign_in_challenge()
    res = env.verify(challenge_id, env.assertion(auth, user, b64url(b"not-the-challenge-" * 2), sign_count=1))
    _assert_refused(env, res, user)


def test_ac12_user_verification_flag_not_set_is_refused(env):
    user, _row, auth = _enabled_user_with_passkey(env)
    challenge_id, challenge = env.sign_in_challenge()
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, uv=False, sign_count=1))
    _assert_refused(env, res, user)


@pytest.mark.parametrize("presented", [10, 5], ids=["equal_to_stored", "lower_than_stored"])
def test_ac12_sign_count_regression_is_refused(env, presented):
    user = env.make_user()
    row, auth = env.seed_passkey(user, sign_count=10)
    challenge_id, challenge = env.sign_in_challenge()
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=presented))
    _assert_refused(env, res, user)
    assert env.passkey(row.id).sign_count == 10


# --------------------------------------------------------------------------------------
# AC-13: account state
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["INACTIVE", "BLOCKED"])
def test_ac13_not_active_user_gets_the_login_403(env, status):
    user, _row, auth = _enabled_user_with_passkey(env, status=status)
    challenge_id, challenge = env.sign_in_challenge()
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=1))
    assert res.status_code == 403, res.text
    assert res.json() == {"detail": "Account not activated. Please verify your email."}
    assert env.sessions(user.id) == []


def test_ac13_trashed_user_gets_the_ac12_401(env):
    user, _row, auth = _enabled_user_with_passkey(env, is_trashed=True)
    challenge_id, challenge = env.sign_in_challenge()
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=1))
    _assert_refused(env, res, user)


# --------------------------------------------------------------------------------------
# AC-15: the per-user switch
# --------------------------------------------------------------------------------------


def test_ac15_switch_off_refuses_a_stored_passkey_and_touches_nothing(env):
    from app.models.user import User

    user = env.make_user(passkey_enabled=False)
    row, auth = env.seed_passkey(user, sign_count=3)
    challenge_id, challenge = env.sign_in_challenge()

    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=4))

    _assert_refused(env, res, user)
    pk = env.passkey(row.id)
    assert pk.sign_count == 3
    assert pk.last_used_at is None
    assert env.db.query(User).filter(User.id == user.id).one().last_sign_in_at is None


def test_ac15_switching_back_on_makes_the_stored_passkey_work_again(env):
    from app.models.user import User

    user = env.make_user(passkey_enabled=False)
    row, auth = env.seed_passkey(user)
    challenge_id, challenge = env.sign_in_challenge()
    assert env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=1)).status_code == 401

    stored = env.db.query(User).filter(User.id == user.id).one()
    stored.passkey_enabled = True
    env.db.commit()
    assert env.passkey(row.id) is not None, "AC-15: switching off keeps stored passkeys"

    challenge_id, challenge = env.sign_in_challenge()
    res = env.verify(challenge_id, env.assertion(auth, user, challenge, sign_count=2))
    assert res.status_code == 200, res.text
    assert env.passkey(row.id).sign_count == 2


# --------------------------------------------------------------------------------------
# AC-29: the assertion's userHandle must name the passkey's owner
# --------------------------------------------------------------------------------------


def test_ac29_user_handle_of_another_user_is_refused(env):
    from tests._soft_authenticator import user_handle_for

    user, row, auth = _enabled_user_with_passkey(env)
    other = env.make_user()
    challenge_id, challenge = env.sign_in_challenge()

    res = env.verify(
        challenge_id,
        env.assertion(auth, user, challenge, sign_count=1, user_handle=user_handle_for(other.id)),
    )

    _assert_refused(env, res, user)
    assert [s for s in env.sessions(other.id) if s.auth_method == "passkey"] == []
    pk = env.passkey(row.id)
    assert pk.sign_count == 0 and pk.last_used_at is None
