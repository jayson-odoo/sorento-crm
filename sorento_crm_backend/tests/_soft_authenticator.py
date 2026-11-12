"""A software WebAuthn authenticator for tests (PASSKEY-LOGIN).

Produces registration and authentication responses in exactly the JSON shape
`@simplewebauthn/browser` sends (`RegistrationResponseJSON` /
`AuthenticationResponseJSON`): every binary field base64url without padding,
`type: "public-key"`, `clientExtensionResults: {}`.

Built on `cryptography` alone (EC P-256, ES256) plus the tiny CBOR encoder below, so the
helper does not lean on the `webauthn` package the implementation verifies with: a bug in
that library cannot hide behind the same bug in the test double. `tests/test_passkey_origin.py`
round-trips this helper's output through `cryptography` verification to prove it.

Every knob a refusal test needs is a keyword: origin, rp_id, challenge, sign_count, the
UP/UV/AT flags, the signing key, the credential id and the clientData type.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_BE = 0x08
FLAG_BS = 0x10
FLAG_AT = 0x40
FLAG_ED = 0x80

COSE_ALG_ES256 = -7


# --------------------------------------------------------------------------------------
# base64url
# --------------------------------------------------------------------------------------


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


# --------------------------------------------------------------------------------------
# CBOR (RFC 8949), the subset WebAuthn uses: ints (incl. negative), bytes, text, arrays,
# maps, bools, null. Encoder for the authenticator, decoder for the helper's own proof.
# --------------------------------------------------------------------------------------


def _head(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([(major << 5) | value])
    if value < 0x100:
        return bytes([(major << 5) | 24, value])
    if value < 0x10000:
        return bytes([(major << 5) | 25]) + struct.pack(">H", value)
    if value < 0x100000000:
        return bytes([(major << 5) | 26]) + struct.pack(">I", value)
    return bytes([(major << 5) | 27]) + struct.pack(">Q", value)


def cbor_encode(obj: Any) -> bytes:
    if obj is False:
        return b"\xf4"
    if obj is True:
        return b"\xf5"
    if obj is None:
        return b"\xf6"
    if isinstance(obj, int):
        return _head(0, obj) if obj >= 0 else _head(1, -1 - obj)
    if isinstance(obj, (bytes, bytearray)):
        return _head(2, len(obj)) + bytes(obj)
    if isinstance(obj, str):
        raw = obj.encode("utf-8")
        return _head(3, len(raw)) + raw
    if isinstance(obj, (list, tuple)):
        return _head(4, len(obj)) + b"".join(cbor_encode(i) for i in obj)
    if isinstance(obj, dict):
        return _head(5, len(obj)) + b"".join(cbor_encode(k) + cbor_encode(v) for k, v in obj.items())
    raise TypeError(f"cbor_encode: unsupported type {type(obj).__name__}")


def cbor_decode(data: bytes) -> tuple[Any, int]:
    """Decode one CBOR item from the start of ``data``; return (item, bytes consumed)."""

    def _read(pos: int) -> tuple[Any, int]:
        initial = data[pos]
        major, info = initial >> 5, initial & 0x1F
        pos += 1
        if major == 7:
            return {20: False, 21: True, 22: None}[info], pos
        if info < 24:
            value = info
        elif info == 24:
            value, pos = data[pos], pos + 1
        elif info == 25:
            value, pos = struct.unpack(">H", data[pos:pos + 2])[0], pos + 2
        elif info == 26:
            value, pos = struct.unpack(">I", data[pos:pos + 4])[0], pos + 4
        elif info == 27:
            value, pos = struct.unpack(">Q", data[pos:pos + 8])[0], pos + 8
        else:
            raise ValueError("indefinite lengths are not used by WebAuthn")
        if major == 0:
            return value, pos
        if major == 1:
            return -1 - value, pos
        if major == 2:
            return bytes(data[pos:pos + value]), pos + value
        if major == 3:
            return data[pos:pos + value].decode("utf-8"), pos + value
        if major == 4:
            items = []
            for _ in range(value):
                item, pos = _read(pos)
                items.append(item)
            return items, pos
        if major == 5:
            out = {}
            for _ in range(value):
                k, pos = _read(pos)
                v, pos = _read(pos)
                out[k] = v
            return out, pos
        raise ValueError(f"unsupported CBOR major type {major}")

    return _read(0)


# --------------------------------------------------------------------------------------
# The authenticator
# --------------------------------------------------------------------------------------


class SoftAuthenticator:
    """One passkey: a P-256 key pair and a credential id, both overridable."""

    def __init__(
        self,
        *,
        credential_id: Optional[bytes] = None,
        private_key: Optional[ec.EllipticCurvePrivateKey] = None,
        aaguid: bytes = b"\x00" * 16,
        sign_count: int = 0,
    ):
        self.credential_id = credential_id if credential_id is not None else os.urandom(32)
        self.private_key = private_key if private_key is not None else ec.generate_private_key(ec.SECP256R1())
        self.aaguid = aaguid
        self.sign_count = sign_count

    # ---- key material -----------------------------------------------------------------

    @property
    def public_key(self) -> ec.EllipticCurvePublicKey:
        return self.private_key.public_key()

    @property
    def credential_id_b64(self) -> str:
        return b64url(self.credential_id)

    def cose_public_key(self) -> bytes:
        """The COSE_Key (EC2, ES256) bytes, as stored in attested credential data."""
        numbers = self.public_key.public_numbers()
        return cbor_encode(
            {
                1: 2,  # kty: EC2
                3: COSE_ALG_ES256,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    # ---- building blocks --------------------------------------------------------------

    @staticmethod
    def client_data_json(*, type_: str, challenge: str, origin: str) -> bytes:
        """``challenge`` is the base64url string the server put in the options."""
        return json.dumps(
            {"type": type_, "challenge": challenge, "origin": origin, "crossOrigin": False},
            separators=(",", ":"),
        ).encode("utf-8")

    def authenticator_data(
        self,
        *,
        rp_id: str,
        sign_count: int,
        up: bool = True,
        uv: bool = True,
        at: bool = False,
        backup_eligible: bool = False,
        backed_up: bool = False,
        credential_id: Optional[bytes] = None,
    ) -> bytes:
        flags = 0
        if up:
            flags |= FLAG_UP
        if uv:
            flags |= FLAG_UV
        if backup_eligible:
            flags |= FLAG_BE
        if backed_up:
            flags |= FLAG_BS
        if at:
            flags |= FLAG_AT
        out = hashlib.sha256(rp_id.encode("utf-8")).digest() + bytes([flags]) + struct.pack(">I", sign_count)
        if at:
            cred = credential_id if credential_id is not None else self.credential_id
            out += self.aaguid + struct.pack(">H", len(cred)) + cred + self.cose_public_key()
        return out

    # ---- registration (navigator.credentials.create) ----------------------------------

    def registration_response(
        self,
        *,
        challenge: str,
        origin: str,
        rp_id: str,
        sign_count: Optional[int] = None,
        up: bool = True,
        uv: bool = True,
        at: bool = True,
        backup_eligible: bool = True,
        backed_up: bool = True,
        type_: str = "webauthn.create",
        credential_id: Optional[bytes] = None,
        transports: Optional[list[str]] = None,
    ) -> dict:
        cred = credential_id if credential_id is not None else self.credential_id
        auth_data = self.authenticator_data(
            rp_id=rp_id,
            sign_count=self.sign_count if sign_count is None else sign_count,
            up=up,
            uv=uv,
            at=at,
            backup_eligible=backup_eligible,
            backed_up=backed_up,
            credential_id=cred,
        )
        attestation_object = cbor_encode({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cdj = self.client_data_json(type_=type_, challenge=challenge, origin=origin)
        return {
            "id": b64url(cred),
            "rawId": b64url(cred),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(cdj),
                "attestationObject": b64url(attestation_object),
                "transports": transports if transports is not None else ["internal", "hybrid"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    # ---- authentication (navigator.credentials.get) -----------------------------------

    def authentication_response(
        self,
        *,
        challenge: str,
        origin: str,
        rp_id: str,
        sign_count: Optional[int] = None,
        up: bool = True,
        uv: bool = True,
        type_: str = "webauthn.get",
        user_handle: Optional[bytes] = None,
        signing_key: Optional[ec.EllipticCurvePrivateKey] = None,
        credential_id: Optional[bytes] = None,
    ) -> dict:
        cred = credential_id if credential_id is not None else self.credential_id
        auth_data = self.authenticator_data(
            rp_id=rp_id,
            sign_count=self.sign_count if sign_count is None else sign_count,
            up=up,
            uv=uv,
            at=False,
        )
        cdj = self.client_data_json(type_=type_, challenge=challenge, origin=origin)
        key = signing_key if signing_key is not None else self.private_key
        signature = key.sign(auth_data + hashlib.sha256(cdj).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64url(cred),
            "rawId": b64url(cred),
            "type": "public-key",
            "response": {
                "authenticatorData": b64url(auth_data),
                "clientDataJSON": b64url(cdj),
                "signature": b64url(signature),
                "userHandle": b64url(user_handle) if user_handle is not None else None,
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }


def user_handle_for(user_id: str) -> bytes:
    """The user handle a test sends back: the user's id as UTF-8 bytes.

    AC-04 stores no user-handle column, so the handle the implementation puts in the
    registration options' ``user.id`` has to be derivable from the user id.
    """
    return str(user_id).encode("utf-8")
