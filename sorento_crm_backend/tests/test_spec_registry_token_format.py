"""The enum-value token format, enforced at the WRITE path (not only in a test).

`tests/test_spec_values_on_rows.py` pins the format across the SEEDED registry, using
a blank schema. That is the seed's contract with the n8n renderer, and it cannot see
a prod UI edit: the renderer humanises a value token blind (underscore -> space, title
case), so a value saved as `Free_Standing` or `wall-hung` renders wrong with nothing
failing anywhere.

This module pins the runtime guard that closes it, and mirrors the seeded test's two
exemptions exactly (`class` holds category labels, `brand` holds display-cased names).

The subject is the VALUE, never the customer word. `wall hung` is a perfectly good
thing for a customer to say for the value `wall_hung`, and a guard that rejected it
would break the search it is meant to protect.
"""
from __future__ import annotations

import pytest

from app.api.v1.master_data.spec_registry import _validate_value_tokens


def _detail(excinfo) -> dict:
    """`AppException` packs message/code into HTTPException's `detail` dict rather
    than exposing them as attributes, so read them the way the handler does."""
    detail = excinfo.value.detail
    assert isinstance(detail, dict), detail
    return detail


def _message(excinfo) -> str:
    return str(_detail(excinfo)["message"])


# --------------------------------------------------------------------------- #
# accepted                                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        "chrome",
        "wall_hung",
        "free_standing",
        "single_bowl",
        "s304",           # digits inside a word
        "1200",           # all digits
        "grade_304_steel",
    ],
)
def test_a_well_formed_token_is_accepted(value):
    _validate_value_tokens("finish", [value])  # must not raise


def test_no_values_is_not_an_error():
    _validate_value_tokens("finish", [])
    _validate_value_tokens("finish", None)


def test_the_self_synonym_marker_is_not_a_value():
    """`_self` names the measurement, not a value. It is the one leading-underscore
    token the registry ships, and the seeded test skips it for the same reason."""
    _validate_value_tokens("thickness", ["_self"])


# --------------------------------------------------------------------------- #
# rejected - each is a real way the renderer breaks                             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        "Free_Standing",   # title case survives into the render
        "WALL_HUNG",
        "wall-hung",       # dash is not the separator the renderer splits on
        "wall hung",       # already spaced; humanising does nothing and it sorts wrong
        "_wall_hung",      # leading separator renders as a blank first word
        "wall_hung_",
        "wall__hung",      # double separator renders a blank word in the middle
        "50%",
        "café",
    ],
)
def test_a_malformed_token_is_rejected(value):
    with pytest.raises(Exception) as excinfo:
        _validate_value_tokens("finish", [value])
    assert value in _message(excinfo)


def test_the_error_names_every_offender_not_just_the_first():
    """A staff member fixing values one rejection at a time is a bad afternoon."""
    with pytest.raises(Exception) as excinfo:
        _validate_value_tokens("finish", ["chrome", "Brushed Nickel", "matte-black"])
    message = _message(excinfo)
    assert "Brushed Nickel" in message
    assert "matte-black" in message
    assert "chrome" not in message  # the good one is not blamed


def test_the_error_carries_the_registry_code():
    with pytest.raises(Exception) as excinfo:
        _validate_value_tokens("finish", ["Bad Value"])
    assert _detail(excinfo)["code"] == "spec_registry_value_token_format"


# --------------------------------------------------------------------------- #
# exemptions - must match tests/test_spec_values_on_rows.py exactly             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec_key", ["class", "brand"])
@pytest.mark.parametrize("value", ["Kitchen Sink", "SORENTO", "Wall-Hung Basin"])
def test_class_and_brand_are_exempt(spec_key, value):
    """Their values are human labels by design, not render tokens."""
    _validate_value_tokens(spec_key, [value])


def test_a_key_that_merely_contains_an_exempt_name_is_not_exempt():
    """`class` is exempt; `product_class` is a different key and is not."""
    with pytest.raises(Exception):
        _validate_value_tokens("product_class", ["Kitchen Sink"])


# --------------------------------------------------------------------------- #
# the guard agrees with the seeded pin                                          #
# --------------------------------------------------------------------------- #
def test_the_guard_uses_the_same_pattern_as_the_seeded_registry_test():
    """Two regexes drifting apart would let the UI write what the seed forbids, which
    is the whole failure this guard exists to prevent."""
    from app.api.v1.master_data.spec_registry import _VALUE_TOKEN_RE

    assert _VALUE_TOKEN_RE.pattern == r"^[a-z0-9]+(_[a-z0-9]+)*$"
