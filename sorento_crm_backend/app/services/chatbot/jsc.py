"""JavaScript semantics the ported node bodies depend on, in one place.

The ported files are line-by-line translations of node bodies that ran in production for
months (D8: parity before improvement). Several of their behaviours are JavaScript's, not
Python's, and reproducing them by hand at every call site is how a port drifts:

* **truthiness** - `[]` and `{}` are TRUTHY in JS and falsy in Python. `if (_roster)` and
  `!!(_prev.dym_offer && typeof _prev.dym_offer === 'object')` both hinge on it.
* **`String(v)`** - `String(null)` is `"null"`, `String(true)` is `"true"`, `String(3.0)`
  is `"3"`. The dash normaliser, `_ceKey` and half the guards run through it.
* **`Number(v)`** - `""` is `0`, `null` is `0`, a bad parse is `NaN`, and every result is
  an integer when it is integral (so it JSON-serialises as `2`, not `2.0`).
* **`undefined` vs `null`** - a captured fixture has been through JSON, so `undefined` is
  an ABSENT KEY. Python dicts model that exactly; `.get()` collapses the two, which is
  right everywhere the JS wrote `x.k` and wrong at the four sites that test
  `=== undefined`. Those sites use `has()`.

Nothing in here is chatbot-specific and nothing in here makes a decision. It is the
shim, not the logic.
"""
from __future__ import annotations

import math
import re
from typing import Any

# Sentinel for a genuine JS `undefined` where a value has to be carried around rather
# than simply left out of a dict.
UNDEFINED: Any = object()


def truthy(value: Any) -> bool:
    """JS truthiness. Empty list / dict are TRUE; 0, "", None, False, NaN are FALSE."""
    if value is None or value is UNDEFINED:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return not (value == 0 or (isinstance(value, float) and math.isnan(value)))
    if isinstance(value, str):
        return value != ""
    return True


def js_string(value: Any) -> str:
    """`String(v)`."""
    if value is None:
        return "null"
    if value is UNDEFINED:
        return "undefined"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, (int, str)):
        return str(value)
    if isinstance(value, list):
        return ",".join("" if v is None else js_string(v) for v in value)
    return "[object Object]"


# ASCII, like JavaScript's own numeric grammar. Python's `\d` matches every Unicode
# decimal, so `Number("\uff11")` would be 1 here and NaN in JS - and a full-width digit
# reaching the member-pick extractor resolves to a real assignment.
_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$", re.ASCII)
NAN = float("nan")


def js_number(value: Any) -> float | int:
    """`Number(v)`. Integral results come back as `int` so JSON round trips as n8n's."""
    if value is None:
        return 0
    if value is UNDEFINED:
        return NAN
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return _int_if_whole(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return 0
        if not _NUMERIC_RE.match(stripped):
            return NAN
        return _int_if_whole(float(stripped))
    return NAN


def _int_if_whole(value: float | int) -> float | int:
    if isinstance(value, int):
        return value
    if math.isnan(value) or math.isinf(value):
        return value
    return int(value) if float(value).is_integer() else value


def is_integer(value: Any) -> bool:
    """`Number.isInteger(v)` - the value must ALREADY be a number, no coercion."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not math.isnan(value) and not math.isinf(value) and float(value).is_integer()


def is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


def get(obj: Any, key: str, default: Any = None) -> Any:
    """`obj?.key` - None for a missing key, and never raises on a non-object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def has(obj: Any, key: str) -> bool:
    """`'key' in obj` - the ONLY way to tell `undefined` from `null` after a JSON trip."""
    return isinstance(obj, dict) and key in obj


def is_array(value: Any) -> bool:
    """`Array.isArray(v)`."""
    return isinstance(value, list)


def array(value: Any) -> list:
    """`Array.isArray(v) ? v : []`, the idiom the bodies open almost every block with."""
    return value if isinstance(value, list) else []


def norm(value: Any) -> Any:
    """output_exchange's own `norm`: null/undefined/"null"/"" collapse to None."""
    if value is None or value is UNDEFINED or value == "null" or value == "":
        return None
    return value


def to_boolean(value: Any) -> bool:
    """n8n's `String.prototype.toBoolean` expression extension."""
    return js_string(value).strip().lower() in {"true", "yes", "1"}


def is_empty(value: Any) -> bool:
    """n8n's `empty` operator: undefined / null / "" / an empty array."""
    return value is None or value is UNDEFINED or value == "" or (isinstance(value, list) and not value)


def lower_trim(value: Any) -> str:
    return js_string(value).strip().lower()


class JsMap:
    """`new Map()` - keys compare by SameValueZero, so `1` and `"1"` are different keys.

    A plain dict is nearly right but not quite: Python hashes `True` and `1` the same and
    JS does not, and the reference-positions block builds its map on the RAW `row.idx`
    then looks it up with `Number(pos)` - a fixture whose idx is a string genuinely
    misses in n8n, and the port has to miss too.
    """

    __slots__ = ("_items",)

    def __init__(self, pairs: list[tuple[Any, Any]] | None = None) -> None:
        self._items: dict[tuple[str, Any], Any] = {}
        for key, value in pairs or []:
            self.set(key, value)

    @staticmethod
    def _k(key: Any) -> tuple[str, Any]:
        # SameValueZero: every JS number is a double, so `1` and `1.0` are ONE key - but
        # `1` and `"1"` are two, and `true` is not `1`. Keying on the type NAME alone got
        # the first of those wrong (`int` vs `float`), so numbers collapse to one bucket
        # and everything else keeps its type.
        if isinstance(key, bool):
            return ("boolean", key)
        if isinstance(key, (int, float)):
            return ("number", float(key))
        return (type(key).__name__, key)

    def set(self, key: Any, value: Any) -> None:
        self._items[self._k(key)] = value

    def get(self, key: Any, default: Any = None) -> Any:
        return self._items.get(self._k(key), default)

    def has(self, key: Any) -> bool:
        return self._k(key) in self._items

    def values(self):
        return self._items.values()

    def __len__(self) -> int:
        return len(self._items)


def find(items: Any, predicate) -> Any:
    """`arr.find(fn)` - the matched element or None."""
    for item in array(items):
        if predicate(item):
            return item
    return None


def find_index(items: Any, predicate) -> int:
    """`arr.findIndex(fn)` - the index or -1."""
    for index, item in enumerate(array(items)):
        if predicate(item):
            return index
    return -1


def word_boundary_re(token: str) -> re.Pattern[str]:
    """`new RegExp('(^|[^a-z0-9])' + escaped + '([^a-z0-9]|$)')` from `_coCompanyPick`."""
    return re.compile(r"(^|[^a-z0-9])" + re.escape(token) + r"([^a-z0-9]|$)")


def lower_or_empty(value: Any) -> str:
    """`String(v || '').toLowerCase()` - the single most common idiom in the bodies."""
    return js_string(value if truthy(value) else "").lower()


def nullish_str(value: Any, fallback: str = "") -> str:
    """`String(v ?? fallback)`. Unlike `||` this keeps `0` and `false`."""
    return js_string(fallback if (value is None or value is UNDEFINED) else value)
