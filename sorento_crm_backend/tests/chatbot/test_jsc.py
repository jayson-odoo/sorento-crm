"""`jsc.py`'s JavaScript semantics, direct.

Every ported node body (`route.py`, `output_exchange.py`, `build_ctx.py`, ...) leans on
these primitives instead of Python's own truthiness / coercion / equality, because the
bodies are line-by-line translations of JS that ran in production (D8). A drift here is
invisible at the call site - it shows up as a replay fixture disagreeing for a reason
nobody can see by reading the node - so the primitives get their own direct suite rather
than relying on the replay corpus to exercise every corner of every one of them.

No fixture, no database, no I/O. Pure functions, asserted against MDN's own semantics.
"""
from __future__ import annotations

import math

from app.services.chatbot import jsc


class TestTruthy:
    """`if (x)` in JS. The two Python collections that are truthy when EMPTY are the
    trap: `[]` and `{}` are objects, and every object is truthy in JS regardless of
    what it holds - only the primitives have their own falsy values."""

    def test_empty_list_is_truthy(self) -> None:
        assert jsc.truthy([]) is True

    def test_empty_dict_is_truthy(self) -> None:
        assert jsc.truthy({}) is True

    def test_non_empty_list_is_truthy(self) -> None:
        assert jsc.truthy([0]) is True

    def test_empty_string_is_falsy(self) -> None:
        assert jsc.truthy("") is False

    def test_zero_is_falsy(self) -> None:
        assert jsc.truthy(0) is False

    def test_zero_point_zero_is_falsy(self) -> None:
        assert jsc.truthy(0.0) is False

    def test_none_is_falsy(self) -> None:
        assert jsc.truthy(None) is False

    def test_undefined_sentinel_is_falsy(self) -> None:
        assert jsc.truthy(jsc.UNDEFINED) is False

    def test_false_is_falsy(self) -> None:
        assert jsc.truthy(False) is False

    def test_true_is_truthy(self) -> None:
        assert jsc.truthy(True) is True

    def test_nan_is_falsy(self) -> None:
        assert jsc.truthy(float("nan")) is False

    def test_non_empty_string_is_truthy(self) -> None:
        assert jsc.truthy("0") is True  # the STRING "0", not the number - truthy in JS
        assert jsc.truthy("false") is True


class TestStringCoercion:
    """`String(v)`. `null` and `undefined` print DIFFERENT words - the one thing that
    trips up a `.get()`-flattened Python read, which is why `jsc.has()` exists at all."""

    def test_string_of_none_is_the_word_null(self) -> None:
        assert jsc.js_string(None) == "null"

    def test_string_of_undefined_is_the_word_undefined(self) -> None:
        assert jsc.js_string(jsc.UNDEFINED) == "undefined"

    def test_string_of_true_and_false(self) -> None:
        assert jsc.js_string(True) == "true"
        assert jsc.js_string(False) == "false"

    def test_string_of_an_integral_float_drops_the_point(self) -> None:
        assert jsc.js_string(3.0) == "3"

    def test_string_of_an_int_is_itself(self) -> None:
        assert jsc.js_string(5) == "5"

    def test_string_of_a_string_is_itself(self) -> None:
        assert jsc.js_string("hi") == "hi"

    def test_string_of_a_list_joins_with_commas_and_nulls_blank(self) -> None:
        """`String([1, null, 'a'])` === `'1,,a'` - `Array.prototype.toString`."""
        assert jsc.js_string([1, None, "a"]) == "1,,a"

    def test_string_of_a_plain_object_is_the_generic_tag(self) -> None:
        assert jsc.js_string({"a": 1}) == "[object Object]"


class TestNumberCoercion:
    """`Number(v)`."""

    def test_number_of_empty_string_is_zero(self) -> None:
        assert jsc.js_number("") == 0

    def test_number_of_blank_string_is_zero(self) -> None:
        """`Number('   ')` is `0` in JS - whitespace-only strings coerce like empty."""
        assert jsc.js_number("   ") == 0

    def test_number_of_a_bad_parse_is_nan(self) -> None:
        result = jsc.js_number("abc")
        assert isinstance(result, float) and math.isnan(result)

    def test_number_of_none_is_zero(self) -> None:
        assert jsc.js_number(None) == 0

    def test_number_of_undefined_is_nan(self) -> None:
        result = jsc.js_number(jsc.UNDEFINED)
        assert isinstance(result, float) and math.isnan(result)

    def test_number_of_true_and_false(self) -> None:
        assert jsc.js_number(True) == 1
        assert jsc.js_number(False) == 0

    def test_number_of_a_numeric_string_parses(self) -> None:
        assert jsc.js_number("42") == 42
        assert jsc.js_number("3.5") == 3.5

    def test_number_of_a_whole_float_comes_back_as_int(self) -> None:
        """So the port's JSON round trip serialises `2`, not `2.0`, matching n8n."""
        result = jsc.js_number("2")
        assert result == 2
        assert isinstance(result, int)

    def test_number_of_an_already_numeric_value_is_passed_through(self) -> None:
        assert jsc.js_number(7) == 7
        assert jsc.js_number(7.5) == 7.5


class TestJsMapKeyIdentity:
    """`new Map()` uses SameValueZero: `1`, `"1"` and `true` are three DIFFERENT keys,
    where a plain Python dict would collide `1` and `True` (same hash) and a naive
    stringifying map would collide `1` and `"1"`."""

    def test_number_one_and_string_one_are_different_keys(self) -> None:
        m = jsc.JsMap()
        m.set(1, "number-one")
        m.set("1", "string-one")
        assert m.get(1) == "number-one"
        assert m.get("1") == "string-one"
        assert len(m) == 2

    def test_true_and_number_one_are_different_keys(self) -> None:
        """Python's own dict would merge these - `hash(True) == hash(1) == 1` and
        `True == 1`. JsMap must not, because `Map` does not coerce booleans."""
        m = jsc.JsMap()
        m.set(1, "number-one")
        m.set(True, "boolean-true")
        assert m.get(1) == "number-one"
        assert m.get(True) == "boolean-true"
        assert len(m) == 2

    def test_false_and_number_zero_are_different_keys(self) -> None:
        m = jsc.JsMap()
        m.set(0, "number-zero")
        m.set(False, "boolean-false")
        assert m.get(0) == "number-zero"
        assert m.get(False) == "boolean-false"
        assert len(m) == 2

    def test_has_reflects_the_same_identity_rule(self) -> None:
        m = jsc.JsMap()
        m.set("1", "x")
        assert m.has("1") is True
        assert m.has(1) is False

    def test_missing_key_returns_the_default(self) -> None:
        m = jsc.JsMap()
        assert m.get("missing") is None
        assert m.get("missing", "fallback") == "fallback"

    def test_constructed_from_pairs_preserves_the_same_identity_rule(self) -> None:
        m = jsc.JsMap([(1, "a"), ("1", "b")])
        assert m.get(1) == "a"
        assert m.get("1") == "b"
