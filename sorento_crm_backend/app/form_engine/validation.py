"""Form submission validation: the SERVER boundary.

Ported from foundryx-shared-service (plan forms-platform F0).

``validate_submission`` re-derives the visible set, drops hidden and unknown
answers, applies required-if-visible, runs the per-type constraints, recomputes
computed fields and computed/fixed table columns, and returns
``(clean_answers, errors)``. ``clean`` is exactly what gets stored; ``errors`` is
the ``{fieldKey: message}`` map the route turns into a 422, with repeater and
table cells keyed ``<fieldKey>.<rowIndex>.<subKey>``.

Everything the client validated is re-validated here, because the client is a
suggestion: a portal submission can be curl'd. Two consequences worth stating
explicitly:

* Conditions evaluate against the answers ACCEPTED SO FAR, never the raw request
  body. Otherwise a caller could force-feed a hidden field's value to unlock a
  later field.
* Computed fields and computed/fixed table columns are recomputed server-side and
  the client value is ignored entirely. A client-supplied total is a price the
  customer chose for themselves.

Pure functions, no DB or ORM imports.

Two deliberate deviations from the shared-service source:

* ``is_visible`` is a new public function and the ONLY way this module asks about
  visibility. The source called the rule evaluator inline and inherited its
  empty-``rules[]``-matches-everything trap.
* ``date`` requires a zero-padded ``YYYY-MM-DD``. The source parsed with
  ``strptime(value, "%Y-%m-%d")``, which also accepts ``2026-6-1``, so two
  spellings of one day could both be stored in a JSONB map that is compared,
  sorted and grouped as STRINGS (where ``"2026-6-1" > "2026-12-01"``).
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.form_engine.computed import evaluate as compute_eval
from app.form_engine.schemas import (
    INPUT_FIELD_TYPES,
    FormDocument,
    FormField,
    FormSubField,
)
from app.rule_engine.evaluator import _MAX_DEPTH
from app.rule_engine.evaluator import evaluate as rule_eval

# Pragmatic email shape, mirroring the client. Deliverability is never asserted,
# so the rule must not reject legitimate addresses.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
# Permissive phone: international formats vary, but a 3-digit or alphabetic value
# is not a number anyone can call back.
_PHONE_RE = re.compile(r"^[0-9+\-()\s]{7,20}$")
# Zero-padded ISO calendar date. The HTML date input always emits this shape, so
# requiring it rejects nothing a real client sends.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The address composite is a fixed shape: an extra key would be stored forever
# and is a place to smuggle unvalidated data into the JSONB payload.
_ADDRESS_KEYS = ("line1", "line2", "city", "state", "postcode", "country")
_ADDRESS_REQUIRED = ("line1", "city", "country")

_REQUIRED_MSG = "This field is required."

# A leaf reading a fact that no form can ever supply, so the rule engine scores
# it False. See ``_close_empty_groups``.
_NEVER_LEAF: Dict[str, Any] = {
    "kind": "condition",
    "fact": "__form_engine_never__",
    "operator": "is_true",
    "value": None,
}


# ---- visibility ----


def _close_empty_groups(node: Any, depth: int = 1) -> Dict[str, Any]:
    """Rewrite every rules-less group into a leaf that reads an absent fact.

    ``rule_engine.evaluator`` reads an empty ``rules[]`` as "unconditional" and
    returns True. Passed a form field's tree verbatim that would REVEAL a field
    whose condition the author never finished, and if the field is required the
    user is blocked by a question they were never meant to see. Substituting a
    never-true leaf makes an empty group a False NODE rather than a True one, so
    an ``and`` containing one cannot pass while an ``or`` can still pass through
    a sibling.
    """
    if depth > _MAX_DEPTH or not isinstance(node, dict):
        return _NEVER_LEAF
    if node.get("kind") == "condition" or "fact" in node:
        return node  # a leaf: the rule engine owns its grammar
    rules = node.get("rules")
    if not isinstance(rules, list) or not rules:
        return _NEVER_LEAF
    return {**node, "rules": [_close_empty_groups(r, depth + 1) for r in rules]}


def is_visible(conditions: Any, facts: Dict[str, Any]) -> bool:
    """Whether a field or section with *conditions* is shown, given *facts*.

    Nothing authored (``None`` or ``{}``) means unconditional, so visible.
    Anything authored must be an evaluable group with at least one rule:
    otherwise it matches NOTHING. That distinction is the whole point of the
    function, because without it the "author saved an unfinished condition" case
    is indistinguishable from "there are no conditions" and the unfinished one
    wins.

    Fails closed on a tree it cannot read: hiding drops an answer, where
    revealing could require an unanswerable question.
    """
    if conditions is None:
        return True
    if not isinstance(conditions, dict):
        return False
    if not conditions:
        return True
    closed = _close_empty_groups(conditions)
    rules = closed.get("rules")
    if not isinstance(rules, list) or not rules:
        return False  # the root is not an evaluable group
    return bool(rule_eval(closed, facts))


# ---- public entry ----


def validate_submission(
    doc: "FormDocument | Dict[str, Any]", answers: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Validate a raw answer map against the form document.

    Returns ``(clean_answers, errors)``:
    - ``clean_answers``: the stored payload. Visible answers only, unknown keys
      dropped, computed values recomputed.
    - ``errors``: per-field ``{fieldKey: message}``, empty meaning valid.

    The input ``answers`` is never mutated: the route audits the raw payload
    after validating, and mutating it in place would make the audit trail show
    the cleaned version, hiding exactly the tampering the cleaning removed.
    """
    form = doc if isinstance(doc, FormDocument) else FormDocument.model_validate(doc)
    answers = answers or {}

    clean: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    # Conditions read the VISIBLE set accumulated so far, never the raw client
    # map. Conditions may only reference earlier fields (publish gate) and we
    # walk in document order, so a hidden upstream field contributes no fact and
    # its leaf fails closed. That is what stops curl force-feeding a hidden
    # field's value to flip a later field's visibility.
    def _facts() -> Dict[str, Any]:
        return {f"answers.{key}": value for key, value in clean.items()}

    for page in form.pages:
        for section in page.sections:
            if not is_visible(section.conditions_json, _facts()):
                continue  # the whole section is hidden: every field within drops
            for field in section.fields:
                if field.type not in INPUT_FIELD_TYPES or not field.key:
                    continue  # a display block collects nothing
                if not is_visible(field.conditions_json, _facts()):
                    continue  # hidden: drop the answer, never raise an error

                if field.type == "computed":
                    # Always present, even when it cannot be evaluated, so a
                    # report reading the key need not distinguish "no answer"
                    # from "field did not exist".
                    clean[field.key] = _recompute(field, clean)
                    continue

                value = answers.get(field.key)
                error = _validate_field(field, value, errors)
                if error:
                    errors[field.key] = error
                # Store only what was actually sent: a visible optional field the
                # user skipped is absent, not null.
                if field.key in answers:
                    clean[field.key] = _clean_value(field, value)

    return clean, errors


# ---- per-field validation ----


def _validate_field(
    field: FormField, value: Any, errors: Dict[str, str]
) -> Optional[str]:
    """An error string for *value* against *field*, or None. Row-bearing types
    write their cell errors into *errors* directly and return only their own
    row-count problem."""
    ftype = field.type

    if ftype == "address":
        return _validate_address(field, value)
    if ftype == "repeater":
        return _validate_repeater(field, value, errors)
    if ftype == "table":
        return _validate_table(field, value, errors)
    if ftype == "file":
        return _validate_file(field, value)

    # Emptiness is checked before format for every scalar type, or a skipped
    # optional field reports "enter a valid date and time".
    if _is_empty(value):
        return _REQUIRED_MSG if field.required else None

    if ftype in ("text", "textarea"):
        return _validate_text(field, str(value))
    if ftype == "email":
        if not _EMAIL_RE.match(str(value)):
            return "Enter a valid email address."
        return _validate_text(field, str(value))
    if ftype == "url":
        if not _is_url(str(value)):
            return "Enter a valid URL."
        return _validate_text(field, str(value))
    if ftype == "phone":
        if not _PHONE_RE.match(str(value)):
            return "Enter a valid phone number."
        return _validate_text(field, str(value))
    if ftype in ("number", "integer"):
        return _validate_number(field, value)
    if ftype in ("select", "radio"):
        return _validate_choice(field, [str(value)])
    if ftype in ("multiselect", "checkboxes"):
        return _validate_multi_choice(field, value)
    if ftype == "yesno":
        # "false" is a truthy string; accepting it would invert the answer to a
        # warranty acknowledgement.
        if not isinstance(value, bool):
            return "Choose an option."
        return None
    if ftype == "date":
        if not _is_date(str(value)):
            return "Enter a valid date."
        return None
    if ftype == "datetime":
        if not _is_datetime(str(value)):
            return "Enter a valid date and time."
        return None
    if ftype == "rating":
        return _validate_rating(field, value)
    if ftype == "signature":
        # The value is an opaque data URL or storage key: only presence matters,
        # because the bytes are the upload layer's problem.
        if not isinstance(value, str) or not value.strip():
            return _REQUIRED_MSG if field.required else None
        return None
    return None


def _validate_text(field: FormField, value: str) -> Optional[str]:
    cfg = field.text
    if cfg is None:
        return None
    if cfg.min_length is not None and len(value) < cfg.min_length:
        return f"Enter at least {cfg.min_length} characters."
    if cfg.max_length is not None and len(value) > cfg.max_length:
        return f"Enter at most {cfg.max_length} characters."
    if cfg.pattern:
        try:
            compiled = re.compile(cfg.pattern)
        except re.error:
            # The author's regex is broken, not the user's answer: fail open here
            # and let the publish gate be the place it is reported.
            compiled = None
        # The client uses ``RegExp.test``, which is a search. A fullmatch here
        # would reject values the client said were valid.
        if compiled is not None and not compiled.search(value):
            return (cfg.pattern_message or "").strip() or (
                "This value is not in the expected format."
            )
    return None


def _decimal_places(value: Any) -> int:
    """Decimal digits in *value*, via Decimal's exponent so scientific notation
    is counted properly (``1e-07`` has seven, not none)."""
    from decimal import Decimal, InvalidOperation

    try:
        exponent = Decimal(str(value).strip()).as_tuple().exponent
    except (InvalidOperation, ValueError):
        return 0
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _number_kind_error(
    value: Any, num: float, *, integer: Optional[bool], decimals: Optional[int]
) -> Optional[str]:
    if integer:
        return None if num == int(num) else "Enter a whole number."
    if decimals is not None and _decimal_places(value) > decimals:
        return f"Enter at most {decimals} decimal place{'' if decimals == 1 else 's'}."
    return None


def _validate_number(field: FormField, value: Any) -> Optional[str]:
    num = _to_number(value)
    if num is None:
        return "Enter a valid number."
    cfg = field.number
    is_integer = field.type == "integer" or bool(cfg and cfg.integer)
    decimals = cfg.decimals if cfg else None
    kind_error = _number_kind_error(
        value, num, integer=is_integer, decimals=decimals
    )
    if kind_error:
        return kind_error
    if cfg is None:
        return None
    if cfg.min is not None and num < cfg.min:
        return f"Enter a value of at least {cfg.min}."
    if cfg.max is not None and num > cfg.max:
        return f"Enter a value of at most {cfg.max}."
    if cfg.step is not None and cfg.step > 0:
        # A step is measured from ``min`` when one is set, not from zero.
        base = cfg.min if cfg.min is not None else 0
        steps = (num - base) / cfg.step
        if abs(steps - round(steps)) > 1e-9:
            return f"Enter a value in steps of {cfg.step}."
    return None


def _validate_choice(field: FormField, values: List[str]) -> Optional[str]:
    allowed = _option_values(field)
    if any(v not in allowed for v in values):
        return "Choose a valid option."
    return None


def _validate_multi_choice(field: FormField, value: Any) -> Optional[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        return "Choose a valid option."
    if len(set(value)) != len(value):
        # A duplicate selection would double-count in any aggregation over the
        # stored array.
        return "Duplicate selection."
    return _validate_choice(field, value)


def _validate_rating(field: FormField, value: Any) -> Optional[str]:
    num = _to_number(value)
    # A legacy document with no rating bag is blocked at publish, but it must
    # still validate against something rather than accept any integer.
    max_value = field.rating.max if field.rating else 5
    if num is None or num != int(num) or int(num) < 1 or int(num) > max_value:
        return "Choose a rating."
    return None


def _validate_address(field: FormField, value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return _REQUIRED_MSG if field.required else None
    # Once the user starts an address, the deliverable parts are mandatory: a
    # city with no street cannot be shipped to.
    started = any(
        isinstance(value.get(k), str) and value[k].strip()
        for k in _ADDRESS_REQUIRED
    )
    if not started:
        return _REQUIRED_MSG if field.required else None
    for key in _ADDRESS_REQUIRED:
        if not (isinstance(value.get(key), str) and value[key].strip()):
            return {
                "line1": "Address line 1 is required.",
                "city": "City is required.",
                "country": "Country is required.",
            }[key]
    return None


def _validate_file(field: FormField, value: Any) -> Optional[str]:
    files = value if isinstance(value, list) else []
    # A malformed descriptor is a client that did not complete the upload
    # handshake, so it counts as no file at all.
    files = [f for f in files if _is_file_shape(f)]
    if not files:
        return _REQUIRED_MSG if field.required else None
    max_count = field.file.max_count if field.file else None
    if max_count is not None and len(files) > max_count:
        return f"Attach at most {max_count} file{'' if max_count == 1 else 's'}."
    # Size and mime are re-checked at upload time; count is the only limit
    # derivable from the answer alone.
    return None


def _validate_repeater(
    field: FormField, value: Any, errors: Dict[str, str]
) -> Optional[str]:
    rows = value if isinstance(value, list) else []
    # Rows arrive from a JSON body and can be anything: a stray string must not
    # abort validation of the real rows around it.
    real_rows = [r for r in rows if isinstance(r, dict)]
    cfg = field.repeater
    low = cfg.min_rows if cfg else None
    high = cfg.max_rows if cfg else None
    key = field.key or ""

    if not real_rows:
        # ``minRows`` implies required, or a form demanding one line item would
        # accept zero.
        if field.required or (low is not None and low > 0):
            if low is not None and low > 0:
                return f"Add at least {low} item{'' if low == 1 else 's'}."
            return _REQUIRED_MSG
        return None

    bound_error: Optional[str] = None
    if low is not None and len(real_rows) < low:
        bound_error = f"Add at least {low} item{'' if low == 1 else 's'}."
    elif high is not None and len(real_rows) > high:
        bound_error = f"Add at most {high} item{'' if high == 1 else 's'}."

    subs = cfg.fields if cfg else []
    for row_index, row in enumerate(real_rows):
        for sub in subs:
            sub_error = _validate_sub_field(sub, row.get(sub.key))
            if sub_error:
                # Cell-level keys so the renderer can highlight the offending
                # cell rather than the whole 20-row repeater.
                errors[f"{key}.{row_index}.{sub.key}"] = sub_error

    return bound_error


def _validate_table(
    field: FormField, value: Any, errors: Dict[str, str]
) -> Optional[str]:
    rows = [
        r for r in (value if isinstance(value, list) else []) if isinstance(r, dict)
    ]
    cfg = field.table
    cols = cfg.columns if cfg else []
    low = cfg.min_rows if cfg else None
    high = cfg.max_rows if cfg else None
    key = field.key or ""

    if not rows:
        if field.required or (low is not None and low > 0):
            if low is not None and low > 0:
                return f"Add at least {low} item{'' if low == 1 else 's'}."
            return _REQUIRED_MSG
        return None

    bound_error: Optional[str] = None
    if low is not None and len(rows) < low:
        bound_error = f"Add at least {low} item{'' if low == 1 else 's'}."
    elif high is not None and len(rows) > high:
        bound_error = f"Add at most {high} item{'' if high == 1 else 's'}."

    for row_index, row in enumerate(rows):
        for col in cols:
            if col.type in ("computed", "fixed"):
                continue  # derived / server-stamped, not user input
            cell_error = _validate_table_cell(col, row.get(col.key))
            if cell_error:
                errors[f"{key}.{row_index}.{col.key}"] = cell_error

    return bound_error


def _validate_table_cell(col: Any, value: Any) -> Optional[str]:
    if _is_empty(value):
        return _REQUIRED_MSG if col.required else None
    ctype = col.type
    if ctype in ("number", "integer"):
        num = _to_number(value)
        if num is None:
            return "Enter a valid number."
        is_integer = ctype == "integer" or bool(col.integer)
        kind_error = _number_kind_error(
            value, num, integer=is_integer, decimals=col.decimals
        )
        if kind_error:
            return kind_error
        cfg = col.number
        if cfg and cfg.min is not None and num < cfg.min:
            return f"Enter a value of at least {cfg.min}."
        if cfg and cfg.max is not None and num > cfg.max:
            return f"Enter a value of at most {cfg.max}."
        return None
    if ctype == "date":
        return None if _is_date(str(value)) else "Enter a valid date."
    if ctype == "select":
        allowed = {item.value for item in (col.options.items if col.options else [])}
        return None if str(value) in allowed else "Choose a valid option."
    return None  # text


def _validate_sub_field(sub: FormSubField, value: Any) -> Optional[str]:
    """A repeater row is not a free-for-all: the same per-type rules apply, or the
    line items are the one unvalidated part of the form."""
    if _is_empty(value):
        return _REQUIRED_MSG if sub.required else None
    stype = sub.type
    text = str(value)
    if stype in ("text", "textarea"):
        cfg = sub.text
        if cfg and cfg.min_length is not None and len(text) < cfg.min_length:
            return f"Enter at least {cfg.min_length} characters."
        if cfg and cfg.max_length is not None and len(text) > cfg.max_length:
            return f"Enter at most {cfg.max_length} characters."
        return None
    if stype == "email":
        return None if _EMAIL_RE.match(text) else "Enter a valid email address."
    if stype == "url":
        return None if _is_url(text) else "Enter a valid URL."
    if stype == "phone":
        return None if _PHONE_RE.match(text) else "Enter a valid phone number."
    if stype == "number":
        num = _to_number(value)
        if num is None:
            return "Enter a valid number."
        cfg = sub.number
        if cfg and cfg.min is not None and num < cfg.min:
            return f"Enter a value of at least {cfg.min}."
        if cfg and cfg.max is not None and num > cfg.max:
            return f"Enter a value of at most {cfg.max}."
        return None
    if stype == "date":
        return None if _is_date(text) else "Enter a valid date."
    if stype == "rating":
        num = _to_number(value)
        max_value = sub.rating.max if sub.rating else 5
        if num is None or num != int(num) or int(num) < 1 or int(num) > max_value:
            return "Choose a rating."
        return None
    if stype in ("select", "radio"):
        allowed = {item.value for item in (sub.options.items if sub.options else [])}
        return None if text in allowed else "Choose a valid option."
    if stype == "yesno":
        return None if isinstance(value, bool) else "Choose an option."
    return None


# ---- what actually gets stored ----


def _recompute(field: FormField, clean: Dict[str, Any]) -> Optional[float]:
    """Recompute a computed field over the already-cleaned answers, so a hidden
    upstream number contributes nothing. Fail-closed."""
    expr = (field.computed.expression or "").strip() if field.computed else ""
    if not expr:
        return None  # blocked at publish; at runtime it degrades to null
    result = compute_eval(expr, clean)
    # Two finite operands can still overflow, and inf/nan serialise as
    # Infinity/NaN, which the JSONB column rejects on insert: a 500 after a
    # clean validation.
    if result is None or not math.isfinite(result):
        return None
    return result


def _clean_value(field: FormField, value: Any) -> Any:
    """Normalise the stored answer. Builds new containers throughout, so the
    caller's ``answers`` map is left untouched."""
    if field.type == "address" and isinstance(value, dict):
        return {k: value[k] for k in _ADDRESS_KEYS if k in value}
    if field.type == "repeater" and isinstance(value, list):
        sub_keys = {s.key for s in (field.repeater.fields if field.repeater else [])}
        return [
            {k: v for k, v in row.items() if k in sub_keys}
            for row in value
            if isinstance(row, dict)
        ]
    if field.type == "table" and isinstance(value, list):
        # Drop undeclared keys, STAMP fixed columns and RECOMPUTE computed
        # columns per row. Walk the columns in order so a fixed or computed
        # column is available to a later computed one.
        cols = field.table.columns if field.table else []
        input_keys = {c.key for c in cols if c.type not in ("computed", "fixed")}
        cleaned_rows = []
        for row in value:
            if not isinstance(row, dict):
                continue
            clean_row = {k: v for k, v in row.items() if k in input_keys}
            for col in cols:
                if col.type == "fixed":
                    clean_row[col.key] = (
                        col.fixed_value if col.fixed_value is not None else ""
                    )
                elif col.type == "computed":
                    expr = (
                        (col.computed.expression or "").strip() if col.computed else ""
                    )
                    result = compute_eval(expr, clean_row) if expr else None
                    # An empty cell, never None and never inf: the FE renders a
                    # number here.
                    clean_row[col.key] = (
                        result if (result is not None and math.isfinite(result)) else ""
                    )
            cleaned_rows.append(clean_row)
        return cleaned_rows
    if field.type == "file" and isinstance(value, list):
        return [f for f in value if _is_file_shape(f)]
    # Choice answers store the STRING option value: membership compares via
    # str(), so a numeric 0 passing against the option "0" must not then be
    # stored as 0, or equality conditions, CSV export and label lookup all
    # disagree with each other.
    if field.type in ("select", "radio") and value is not None:
        return str(value)
    if field.type in ("multiselect", "checkboxes") and isinstance(value, list):
        return [str(v) for v in value]
    return value


# ---- primitive predicates and coercion ----


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        # A space is not an answer: otherwise a required field is satisfied by
        # pressing the space bar.
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None  # a yesno answer must not silently become a quantity
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        try:
            num = float(value.strip())
        except (ValueError, OverflowError):
            return None
    else:
        return None
    # inf/nan round-trip as Infinity/NaN, which is invalid JSON and is rejected
    # by the JSONB column on insert.
    return num if math.isfinite(num) else None


def _is_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except (ValueError, AttributeError):
        return False
    # http/https only: a stored ``javascript:`` URL rendered as a link in the
    # admin detail page is a stored XSS.
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _is_date(value: str) -> bool:
    """Exactly ``YYYY-MM-DD``, zero-padded.

    The regex is the deviation from the source: ``%m``/``%d`` match one OR two
    digits, so ``strptime`` alone would accept ``2026-6-1`` as well.
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not _DATE_RE.match(candidate):
        return False
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _is_datetime(value: str) -> bool:
    """Any ISO-8601 instant, date-only included (it is a calendar instant)."""
    if not isinstance(value, str) or not value.strip():
        return False
    # ``fromisoformat`` did not accept a Z suffix before 3.11, and the FE always
    # sends one: this is the case a port silently breaks.
    candidate = value.strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
        return True
    except ValueError:
        pass
    try:
        date.fromisoformat(candidate)
        return True
    except ValueError:
        return False


def _option_values(field: FormField) -> set:
    return {item.value for item in (field.options.items if field.options else [])}


def _is_file_shape(f: Any) -> bool:
    return (
        isinstance(f, dict)
        and isinstance(f.get("key"), str)
        and isinstance(f.get("name"), str)
        and "size" in f
        and isinstance(f.get("mime"), str)
    )
