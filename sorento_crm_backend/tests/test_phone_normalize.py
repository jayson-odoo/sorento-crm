"""TCK-2026-000031 AC-31-F3 - E.164 (MY) phone normalisation.

Run: pytest tests/test_phone_normalize.py -v
"""
import pytest

from app.services.phone_utils import normalize_msisdn


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("012-345 6789", "60123456789"),
        ("0123456789", "60123456789"),
        ("+60123456789", "60123456789"),
        ("60123456789", "60123456789"),
        ("+6012-345 6789", "60123456789"),
        ("0060123456789", "60123456789"),  # 00 international prefix
        ("123456789", "60123456789"),       # bare subscriber, no trunk 0
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_my(raw, expected):
    assert normalize_msisdn(raw) == expected


def test_idempotent():
    for raw in ("012-345 6789", "+60123456789", "0123456789"):
        once = normalize_msisdn(raw)
        assert normalize_msisdn(once) == once


def test_local_and_e164_converge():
    """A user typing local form matches a contact stored in E.164 - the link key."""
    assert normalize_msisdn("0123456789") == normalize_msisdn("+60123456789")
