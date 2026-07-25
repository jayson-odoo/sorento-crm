"""Slice 1 of AutoCount Group A — the key crypto primitives.

These are the security core: how an integration API key is minted, stored and
verified. Everything else in Group A (rotation, expiry, RBAC resolution) sits on
top of these four functions, so they are pinned first and pinned hard.

Contract, per the UAC:
  AC-AC-03  plaintext shown once at creation; only a hash persists; never retrievable
  AC-AC-04  verification is constant-time; no ``==``/``!=`` on a secret anywhere
"""
import inspect
import re

import pytest

from app.services.integration_key_crypto import (
    generate_api_key,
    hash_api_key,
    key_prefix,
    verify_api_key,
)


class TestGenerateApiKey:
    def test_returns_a_string_with_an_identifying_prefix(self):
        key = generate_api_key()
        assert isinstance(key, str)
        # A recognisable prefix lets an operator spot a Sorento key in a config
        # file or a leaked log line and know what they are looking at.
        assert key.startswith("sk_")

    def test_has_at_least_128_bits_of_entropy_in_the_random_segment(self):
        key = generate_api_key()
        random_part = key.split("_", 1)[1]
        # urlsafe base64 carries 6 bits per character; 128 bits needs >= 22 chars.
        assert len(random_part) >= 22

    def test_is_urlsafe(self):
        # Keys travel in headers and get pasted into config by hand. Anything
        # needing escaping invites truncation bugs at the caller.
        assert re.fullmatch(r"[A-Za-z0-9_\-]+", generate_api_key())

    def test_successive_keys_differ(self):
        assert len({generate_api_key() for _ in range(100)}) == 100


class TestHashApiKey:
    def test_hash_is_not_the_plaintext(self):
        key = generate_api_key()
        assert hash_api_key(key) != key

    def test_hash_does_not_contain_the_plaintext(self):
        # Guards against a "hash" that merely decorates the secret.
        key = generate_api_key()
        assert key not in hash_api_key(key)

    def test_hash_is_deterministic(self):
        # Deterministic, unlike bcrypt: verification must be a single indexed
        # lookup on key_hash, not a scan-and-compare across every stored key.
        key = generate_api_key()
        assert hash_api_key(key) == hash_api_key(key)

    def test_distinct_keys_hash_differently(self):
        assert hash_api_key(generate_api_key()) != hash_api_key(generate_api_key())

    def test_hash_is_hex_sha256(self):
        assert re.fullmatch(r"[0-9a-f]{64}", hash_api_key(generate_api_key()))


class TestKeyPrefix:
    def test_returns_a_short_non_secret_fragment(self):
        key = generate_api_key()
        prefix = key_prefix(key)
        assert len(prefix) <= 12
        assert key.startswith(prefix)

    def test_prefix_is_far_too_short_to_bruteforce_the_key_from(self):
        key = generate_api_key()
        # The displayed fragment must leave the overwhelming majority of the
        # secret unknown, or "show the prefix in the UI" becomes a key leak.
        assert len(key_prefix(key)) < len(key) / 2

    def test_prefix_is_stable(self):
        key = generate_api_key()
        assert key_prefix(key) == key_prefix(key)


class TestVerifyApiKey:
    def test_accepts_the_matching_key(self):
        key = generate_api_key()
        assert verify_api_key(key, hash_api_key(key)) is True

    def test_rejects_a_different_key(self):
        assert verify_api_key(generate_api_key(), hash_api_key(generate_api_key())) is False

    def test_rejects_empty_key(self):
        assert verify_api_key("", hash_api_key(generate_api_key())) is False

    def test_rejects_none_key(self):
        assert verify_api_key(None, hash_api_key(generate_api_key())) is False

    def test_rejects_when_stored_hash_is_empty(self):
        # A row with a blank hash must never authenticate anyone. This is the
        # failure mode AC-AC-09 guards against when EXTERNAL_API_KEY is absent
        # at migration time and a naive seed writes "".
        key = generate_api_key()
        assert verify_api_key(key, "") is False

    def test_rejects_when_stored_hash_is_none(self):
        assert verify_api_key(generate_api_key(), None) is False

    def test_uses_constant_time_comparison(self):
        # AC-AC-04 is a source-level requirement, not an observable behaviour:
        # a timing-unsafe implementation passes every functional test above.
        # Assert on the source directly.
        source = inspect.getsource(verify_api_key)
        assert "compare_digest" in source, "verify_api_key must use hmac.compare_digest"

    def test_source_contains_no_equality_comparison_on_the_secret(self):
        source = inspect.getsource(verify_api_key)
        body = source.split("\n", 1)[1]
        stripped = "\n".join(
            line for line in body.splitlines() if not line.strip().startswith("#")
        )
        # `is None` / `is not None` guards are fine; `==` / `!=` on secret
        # material is precisely what app/dependencies.py:546-582 does today.
        assert "==" not in stripped, "no == on secret material"
        assert "!=" not in stripped, "no != on secret material"


class TestRoundTrip:
    @pytest.mark.parametrize("_", range(20))
    def test_generated_keys_always_verify_against_their_own_hash(self, _):
        key = generate_api_key()
        assert verify_api_key(key, hash_api_key(key)) is True

    def test_a_key_never_verifies_against_another_keys_hash(self):
        keys = [generate_api_key() for _ in range(10)]
        hashes = [hash_api_key(k) for k in keys]
        for i, key in enumerate(keys):
            for j, stored in enumerate(hashes):
                assert verify_api_key(key, stored) is (i == j)
