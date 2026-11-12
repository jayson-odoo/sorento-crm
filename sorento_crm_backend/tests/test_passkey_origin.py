"""PASSKEY-LOGIN: the origin rule (AC-01, AC-02) and proof that the test authenticator is right.

AC-02: an origin is allowed when its hostname is in `settings.webauthn_rp_ids` AND it is
`https` on any port, or `http` on `localhost` (only when `localhost` is listed). The RP ID is
that hostname. `passkey_service.origin_allowed(origin)` answers the RP ID or None.

The helper-proof tests (`test_helper_*`) are GREEN on purpose: they pin that
`tests/_soft_authenticator.py` builds correct WebAuthn bytes, so a red sign-in test is about
the implementation and never about the test double.

Contract: documentation/plans/identity/passkey-login-12nov-acceptance-criteria.md
"""
from __future__ import annotations

import hashlib
import json
import struct

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from tests._soft_authenticator import (
    FLAG_AT,
    FLAG_UP,
    FLAG_UV,
    SoftAuthenticator,
    b64url,
    b64url_decode,
    cbor_decode,
    cbor_encode,
)

RP_IDS = "crm.example.test,localhost"


# --------------------------------------------------------------------------------------
# AC-01 / AC-02: config + origin_allowed
# --------------------------------------------------------------------------------------


def test_ac01_settings_carry_rp_ids_and_rp_name_with_their_defaults():
    from app.config import Settings

    fields = Settings.model_fields
    assert "webauthn_rp_ids" in fields, "AC-01: Settings.webauthn_rp_ids is missing"
    assert "webauthn_rp_name" in fields, "AC-01: Settings.webauthn_rp_name is missing"
    assert fields["webauthn_rp_ids"].default == ""
    assert fields["webauthn_rp_name"].default == "Sorento CRM"


@pytest.fixture()
def rp_ids(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "webauthn_rp_ids", RP_IDS)
    return RP_IDS


@pytest.mark.parametrize(
    "origin, expected",
    [
        ("https://crm.example.test", "crm.example.test"),
        ("https://crm.example.test:8443", "crm.example.test"),
        ("https://crm.example.test:3001", "crm.example.test"),
        ("http://localhost:3000", "localhost"),
        ("http://localhost", "localhost"),
        ("https://localhost:3000", "localhost"),
    ],
    ids=["https", "https_port_8443", "https_port_3001", "http_localhost_port", "http_localhost", "https_localhost"],
)
def test_ac02_allowed_origin_returns_its_hostname_as_rp_id(rp_ids, origin, expected):
    from app.services import passkey_service

    assert passkey_service.origin_allowed(origin) == expected


@pytest.mark.parametrize(
    "origin",
    [
        "http://crm.example.test",  # http on a non-localhost host
        "http://crm.example.test:3000",
        "https://evil.example.test",  # unlisted host
        "https://sub.crm.example.test",  # a subdomain is not the listed hostname
        "https://example.test",  # a parent domain is not the listed hostname
        "https://crm.example.test.evil.test",
        "ftp://crm.example.test",
        "crm.example.test",  # no scheme
        "not a url",
        "",
        "null",  # what a sandboxed iframe sends
        None,
    ],
)
def test_ac02_refused_origin_returns_none(rp_ids, origin):
    from app.services import passkey_service

    assert passkey_service.origin_allowed(origin) is None


def test_ac02_http_localhost_refused_when_localhost_is_not_listed(monkeypatch):
    from app.config import settings
    from app.services import passkey_service

    monkeypatch.setattr(settings, "webauthn_rp_ids", "crm.example.test")
    assert passkey_service.origin_allowed("http://localhost:3000") is None
    assert passkey_service.origin_allowed("https://crm.example.test") == "crm.example.test"


def test_ac02_list_is_comma_separated_and_whitespace_tolerant(monkeypatch):
    from app.config import settings
    from app.services import passkey_service

    monkeypatch.setattr(settings, "webauthn_rp_ids", " crm.example.test , other.example.test ,")
    assert passkey_service.origin_allowed("https://other.example.test") == "other.example.test"
    assert passkey_service.origin_allowed("https://crm.example.test") == "crm.example.test"


def test_ac03_empty_list_allows_nothing(monkeypatch):
    from app.config import settings
    from app.services import passkey_service

    monkeypatch.setattr(settings, "webauthn_rp_ids", "")
    assert passkey_service.origin_allowed("https://crm.example.test") is None
    assert passkey_service.origin_allowed("http://localhost:3000") is None


def test_ac05_passkey_is_a_session_auth_method():
    from app.models.user_session import UserSession
    from app.services.user_session_service import AUTH_METHODS

    assert "passkey" in AUTH_METHODS
    checks = [
        str(c.sqltext)
        for c in UserSession.__table__.constraints
        if getattr(c, "name", None) == "ck_user_sessions_auth_method"
    ]
    assert checks and "'passkey'" in checks[0], checks


# --------------------------------------------------------------------------------------
# Helper proof (green): the soft authenticator's bytes are right
# --------------------------------------------------------------------------------------


def test_helper_cbor_round_trips_every_type_webauthn_uses():
    sample = {
        1: 2,
        3: -7,
        -1: 1,
        -2: b"\x01" * 32,
        "fmt": "none",
        "attStmt": {},
        "n": [0, 23, 24, 255, 256, 65535, 65536, 2**32, -1, -24, -25, -256, -257],
        "t": True,
        "f": False,
        "z": None,
    }
    encoded = cbor_encode(sample)
    decoded, used = cbor_decode(encoded)
    assert decoded == sample
    assert used == len(encoded)
    # Known vectors from RFC 8949 Appendix A.
    assert cbor_encode(-7) == b"\x26"
    assert cbor_encode(24) == b"\x18\x18"
    assert cbor_encode(-257) == b"\x39\x01\x00"
    assert cbor_encode("a") == b"\x61\x61"
    assert cbor_encode({1: 2}) == b"\xa1\x01\x02"


def _cose_to_public_key(cose: bytes) -> ec.EllipticCurvePublicKey:
    key, _ = cbor_decode(cose)
    assert key[1] == 2 and key[3] == -7 and key[-1] == 1
    numbers = ec.EllipticCurvePublicNumbers(
        int.from_bytes(key[-2], "big"), int.from_bytes(key[-3], "big"), ec.SECP256R1()
    )
    return numbers.public_key()


def test_helper_registration_response_is_well_formed():
    auth = SoftAuthenticator()
    challenge = b64url(b"registration-challenge-bytes-32!")
    reg = auth.registration_response(
        challenge=challenge, origin="https://crm.example.test", rp_id="crm.example.test", sign_count=3
    )

    assert reg["type"] == "public-key"
    assert reg["id"] == reg["rawId"] == auth.credential_id_b64
    assert reg["clientExtensionResults"] == {}
    cdj = json.loads(b64url_decode(reg["response"]["clientDataJSON"]))
    assert cdj == {
        "type": "webauthn.create",
        "challenge": challenge,
        "origin": "https://crm.example.test",
        "crossOrigin": False,
    }

    att, _ = cbor_decode(b64url_decode(reg["response"]["attestationObject"]))
    assert att["fmt"] == "none" and att["attStmt"] == {}
    ad = att["authData"]
    assert ad[:32] == hashlib.sha256(b"crm.example.test").digest()
    flags = ad[32]
    assert flags & FLAG_UP and flags & FLAG_UV and flags & FLAG_AT
    assert struct.unpack(">I", ad[33:37])[0] == 3
    assert ad[37:53] == auth.aaguid
    cred_len = struct.unpack(">H", ad[53:55])[0]
    assert ad[55:55 + cred_len] == auth.credential_id
    cose = ad[55 + cred_len:]
    assert cose == auth.cose_public_key()
    assert _cose_to_public_key(cose).public_numbers() == auth.public_key.public_numbers()

    no_uv = auth.registration_response(
        challenge=challenge, origin="https://crm.example.test", rp_id="crm.example.test", uv=False
    )
    att2, _ = cbor_decode(b64url_decode(no_uv["response"]["attestationObject"]))
    assert not att2["authData"][32] & FLAG_UV


def test_helper_assertion_signature_verifies_with_cryptography():
    auth = SoftAuthenticator()
    challenge = b64url(b"sign-in-challenge-bytes-32-long!")
    assertion = auth.authentication_response(
        challenge=challenge,
        origin="https://crm.example.test",
        rp_id="crm.example.test",
        sign_count=9,
        user_handle=b"user-1",
    )
    resp = assertion["response"]
    ad = b64url_decode(resp["authenticatorData"])
    cdj = b64url_decode(resp["clientDataJSON"])
    sig = b64url_decode(resp["signature"])

    assert len(ad) == 37
    assert ad[:32] == hashlib.sha256(b"crm.example.test").digest()
    assert ad[32] & FLAG_UP and ad[32] & FLAG_UV and not ad[32] & FLAG_AT
    assert struct.unpack(">I", ad[33:37])[0] == 9
    assert json.loads(cdj)["type"] == "webauthn.get"
    assert json.loads(cdj)["challenge"] == challenge
    assert b64url_decode(resp["userHandle"]) == b"user-1"

    # The verifier's own computation, from the COSE key the registration would store.
    public = _cose_to_public_key(auth.cose_public_key())
    public.verify(sig, ad + hashlib.sha256(cdj).digest(), ec.ECDSA(hashes.SHA256()))

    # A different signing key must NOT verify against the registered key.
    forged = auth.authentication_response(
        challenge=challenge,
        origin="https://crm.example.test",
        rp_id="crm.example.test",
        signing_key=ec.generate_private_key(ec.SECP256R1()),
    )
    fr = forged["response"]
    with pytest.raises(InvalidSignature):
        public.verify(
            b64url_decode(fr["signature"]),
            b64url_decode(fr["authenticatorData"]) + hashlib.sha256(b64url_decode(fr["clientDataJSON"])).digest(),
            ec.ECDSA(hashes.SHA256()),
        )


def test_helper_is_accepted_by_py_webauthn_when_installed():
    """Cross-check against the library the implementation is planned to use (py_webauthn).
    Skips until `webauthn` is in requirements; green once it is."""
    webauthn = pytest.importorskip("webauthn")

    auth = SoftAuthenticator()
    origin, rp_id = "https://crm.example.test:8443", "crm.example.test"
    reg_challenge = b"r" * 32
    reg = auth.registration_response(challenge=b64url(reg_challenge), origin=origin, rp_id=rp_id)
    verified = webauthn.verify_registration_response(
        credential=json.dumps(reg),
        expected_challenge=reg_challenge,
        expected_origin=origin,
        expected_rp_id=rp_id,
        require_user_verification=True,
    )
    assert verified.credential_id == auth.credential_id
    assert verified.credential_public_key == auth.cose_public_key()

    sign_challenge = b"s" * 32
    assertion = auth.authentication_response(
        challenge=b64url(sign_challenge), origin=origin, rp_id=rp_id, sign_count=5, user_handle=b"u"
    )
    result = webauthn.verify_authentication_response(
        credential=json.dumps(assertion),
        expected_challenge=sign_challenge,
        expected_origin=origin,
        expected_rp_id=rp_id,
        credential_public_key=verified.credential_public_key,
        credential_current_sign_count=0,
        require_user_verification=True,
    )
    assert result.new_sign_count == 5
