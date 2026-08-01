"""The submission validation pipeline, ported from foundryx-shared-service
(plan F0). Written before the implementation, per PRINCIPLES step 4.

Target module: ``app.form_engine.validation``.

This module is the server boundary. Everything the client validated is
re-validated here, because the client is a suggestion: a portal submission can
be curl'd. So the tests that matter most are the ones about what the server
refuses to trust:

* ``test_a_hidden_answer_cannot_drive_downstream_visibility`` -- the injection
  case. Conditions must evaluate against the answers ACCEPTED SO FAR, not the
  raw request body, or a caller can force-feed a hidden field's value to unlock
  a later field.
* ``test_an_empty_condition_group_hides_the_field`` -- the runtime half of the
  known Sorento rule-engine trap. ``{combinator, rules: []}`` matches everything
  in the bare evaluator, which would REVEAL a field the author never finished
  configuring. In this context an empty group must match nothing.
* ``test_a_computed_answer_is_recomputed_and_the_client_value_ignored`` and its
  table-column twin -- a client-supplied total is a price the customer chose.
* ``test_required_applies_only_when_visible`` -- hidden answers are dropped
  silently, never errored, or a conditional form could never be submitted.

The contract is ``(clean_answers, errors)``: ``clean`` is exactly what gets
stored, ``errors`` is the ``{fieldKey: message}`` map the route turns into a 422.
Repeater and table cells are keyed ``<fieldKey>.<rowIndex>.<subKey>``.

Pure unit tests, no database.
Run: venv/bin/pytest tests/test_form_engine_validation.py -q
"""
from __future__ import annotations

import copy
import math

import pytest

from app.form_engine.validation import is_visible, validate_submission

REQUIRED = "This field is required."


# ---------------------------------------------------------------------------
# document builders
# ---------------------------------------------------------------------------

def field(type_, key=None, **extra):
    f = {"id": f"fld_{key or type_}", "type": type_, "label": key or type_}
    if key is not None:
        f["key"] = key
    f.update(extra)
    return f


def doc(*fields):
    return {
        "schemaVersion": 1,
        "pages": [{"id": "pg_1", "sections": [{"id": "sec_1", "fields": list(fields)}]}],
    }


def two_sections(first, second, second_extra=None):
    return {
        "schemaVersion": 1,
        "pages": [
            {
                "id": "pg_1",
                "sections": [
                    {"id": "s1", "fields": list(first)},
                    {"id": "s2", "fields": list(second), **(second_extra or {})},
                ],
            }
        ],
    }


def cond(fact, operator="is_true", value=None):
    return {
        "kind": "group",
        "combinator": "and",
        "rules": [
            {"kind": "condition", "fact": fact, "operator": operator, "value": value}
        ],
    }


def opts(*values):
    return {
        "kind": "static",
        "items": [{"value": v, "label": v.upper()} for v in values],
    }


def table_field(key="lines", columns=None, **table_extra):
    cols = columns if columns is not None else [
        {"id": "c1", "type": "text", "key": "item", "label": "Item", "required": True},
        {"id": "c2", "type": "number", "key": "qty", "label": "Qty", "required": True},
        {"id": "c3", "type": "number", "key": "unit_price", "label": "Unit price"},
        {
            "id": "c4",
            "type": "computed",
            "key": "amount",
            "label": "Amount",
            "computed": {"expression": "qty * unit_price"},
            "summarize": "sum",
        },
    ]
    return {
        "id": "t1",
        "type": "table",
        "key": key,
        "label": "Lines",
        "table": {"columns": cols, **table_extra},
    }


def repeater_field(key="notes", subs=None, **repeater_extra):
    if subs is None:
        subs = [
            {"id": "s1", "type": "text", "key": "note", "label": "Note", "required": True},
            {"id": "s2", "type": "number", "key": "hours", "label": "Hours"},
        ]
    return field(
        "repeater", key=key, repeater={"fields": subs, **repeater_extra}
    )


def errors_of(document, answers):
    clean, errors = validate_submission(document, answers)
    assert isinstance(clean, dict)
    assert isinstance(errors, dict)
    assert all(isinstance(k, str) for k in errors)
    assert all(isinstance(v, str) and v.strip() for v in errors.values()), errors
    return errors


def clean_of(document, answers):
    clean, errors = validate_submission(document, answers)
    assert errors == {}, f"expected a clean submission, got {errors!r}"
    return clean


# ---------------------------------------------------------------------------
# the contract shape
# ---------------------------------------------------------------------------

def test_the_return_value_is_clean_answers_then_errors():
    """The route stores the first and 422s on the second. Swapping them would
    persist an error map as a submission."""
    clean, errors = validate_submission(doc(field("text", key="name")), {"name": "Jay"})
    assert clean == {"name": "Jay"}
    assert errors == {}


def test_a_missing_answers_map_is_treated_as_empty():
    """Portal callers post partial bodies. ``None`` must not be an
    AttributeError inside the walker."""
    clean, errors = validate_submission(doc(field("text", key="name")), None)
    assert clean == {}
    assert errors == {}


def test_the_input_answers_map_is_not_mutated():
    """The route logs / audits the raw payload after validating. Mutating it in
    place would make the audit trail show the cleaned version, hiding exactly
    the tampering the cleaning removed."""
    document = doc(field("text", key="name"), table_field())
    answers = {"name": "Jay", "lines": [{"item": "A", "qty": 1, "unit_price": 2, "junk": "x"}], "ghost": 1}
    snapshot = copy.deepcopy(answers)
    validate_submission(document, answers)
    assert answers == snapshot


def test_unknown_answer_keys_are_dropped():
    """Anything not declared in the document is not stored. Otherwise a caller
    could grow the JSONB payload without limit and smuggle fields past the
    schema."""
    clean = clean_of(doc(field("text", key="name")), {"name": "Jay", "ghost": "boo"})
    assert clean == {"name": "Jay"}


def test_display_blocks_never_produce_an_answer():
    """A heading has no key. It must not appear in the stored payload even if the
    client sends something for its id."""
    clean = clean_of(doc(field("heading"), field("text", key="name")), {"name": "Jay", "heading": "x"})
    assert clean == {"name": "Jay"}


def test_an_absent_optional_answer_is_not_stored_as_null():
    """A visible optional field the user skipped is absent, not null: the two are
    distinguishable in reporting and in a later resubmission diff."""
    clean = clean_of(doc(field("text", key="a"), field("text", key="b")), {"a": "x"})
    assert clean == {"a": "x"}


# ---------------------------------------------------------------------------
# visibility, required-if-visible, and the empty-group trap
# ---------------------------------------------------------------------------

def test_required_applies_only_when_visible():
    """The whole point of conditional requirement: "if out of warranty, require a
    charge acknowledgement". When the condition is false the field is not
    required, and when it is true it is."""
    document = two_sections(
        [field("yesno", key="agree")],
        [field("text", key="why", required=True, conditionsJson=cond("answers.agree"))],
    )
    assert errors_of(document, {"agree": False}) == {}
    assert errors_of(document, {"agree": True}) == {"why": REQUIRED}


def test_a_hidden_answer_is_dropped_without_an_error():
    """A user who answers "no" and then changes an earlier answer leaves stale
    values in the body. They must be discarded, not stored and not errored."""
    document = two_sections(
        [field("yesno", key="agree")],
        [field("text", key="why", required=True, conditionsJson=cond("answers.agree"))],
    )
    clean, errors = validate_submission(document, {"agree": False, "why": "leftover"})
    assert "why" not in clean
    assert errors == {}


def test_a_hidden_section_hides_every_field_inside_it():
    """Section-level conditions are how a whole warranty block is switched off.
    A field inside a hidden section must not be required and must not be
    stored."""
    document = two_sections(
        [field("yesno", key="agree")],
        [field("text", key="a", required=True), field("text", key="b", required=True)],
        second_extra={"conditionsJson": cond("answers.agree")},
    )
    clean, errors = validate_submission(document, {"agree": False, "a": "x", "b": "y"})
    assert errors == {}
    assert clean == {"agree": False}


def test_an_equality_condition_drives_visibility():
    """The commonest authored condition is "kind equals X", not a boolean."""
    document = two_sections(
        [field("select", key="kind", options=opts("exchange", "return"))],
        [field("text", key="detail", required=True,
               conditionsJson=cond("answers.kind", operator="eq", value="return"))],
    )
    assert errors_of(document, {"kind": "exchange"}) == {}
    assert "detail" in errors_of(document, {"kind": "return"})


def test_a_hidden_answer_cannot_drive_downstream_visibility():
    """The injection case, and the reason conditions read ``clean`` not the body.

    ``gate`` is itself hidden (its own condition can never be true), so the value
    the caller supplied for it must not become a fact. If it did, curl could
    reveal ``secret`` - a field the real form never shows - by sending both.
    """
    never = cond("answers.nothing_ever")
    document = doc(
        field("yesno", key="gate", conditionsJson=never),
        field("text", key="secret", conditionsJson=cond("answers.gate")),
    )
    clean, errors = validate_submission(document, {"gate": True, "secret": "leak"})
    assert "gate" not in clean
    assert "secret" not in clean
    assert errors == {}


def test_an_empty_condition_group_hides_the_field():
    """The runtime half of the known rule-engine trap.

    Sorento's ``rule_engine.evaluator.evaluate`` returns True for
    ``{combinator, rules: []}`` because it treats an empty rule list as "no
    conditions". Passing a form field's tree straight through would REVEAL a
    field whose condition the author never finished, and if it is required the
    user is blocked by a question they were never meant to see.

    Publish blocks this document (see test_form_engine_schemas.py); this pins the
    behaviour for any tree that reaches runtime anyway.
    """
    empty = {"kind": "group", "combinator": "and", "rules": []}
    document = doc(
        field("yesno", key="agree"),
        field("text", key="why", required=True, conditionsJson=empty),
    )
    clean, errors = validate_submission(document, {"agree": True, "why": "shown"})
    assert errors == {}, "an unfinished condition must not make the field required"
    assert "why" not in clean, "an empty condition group must match nothing"


@pytest.mark.parametrize(
    "tree,expected",
    [
        # Nothing authored: the field is unconditional and always visible.
        (None, True),
        ({}, True),
        # An authored group with no rules matches NOTHING (the trap).
        ({"kind": "group", "combinator": "and", "rules": []}, False),
        ({"kind": "group", "combinator": "or", "rules": []}, False),
        ({"combinator": "and"}, False),
        ({"kind": "group", "combinator": "and", "rules": "nonsense"}, False),
        # A real rule still evaluates normally.
        ({"kind": "group", "combinator": "and",
          "rules": [{"kind": "condition", "fact": "answers.agree", "operator": "is_true"}]}, True),
        ({"kind": "group", "combinator": "and",
          "rules": [{"kind": "condition", "fact": "answers.missing", "operator": "is_true"}]}, False),
        # A nested empty group is False, so an AND that contains one cannot pass.
        ({"kind": "group", "combinator": "and", "rules": [
            {"kind": "condition", "fact": "answers.agree", "operator": "is_true"},
            {"kind": "group", "combinator": "and", "rules": []},
        ]}, False),
        # ... but an OR whose other arm passes still passes: the empty group
        # contributes False, it does not poison the whole tree.
        ({"kind": "group", "combinator": "or", "rules": [
            {"kind": "condition", "fact": "answers.agree", "operator": "is_true"},
            {"kind": "group", "combinator": "and", "rules": []},
        ]}, True),
        ({"kind": "group", "combinator": "or", "rules": [
            {"kind": "condition", "fact": "answers.missing", "operator": "is_true"},
            {"kind": "group", "combinator": "and", "rules": []},
        ]}, False),
    ],
)
def test_is_visible_treats_an_empty_group_as_no_match(tree, expected):
    """``is_visible`` is the explicit guard the plan calls for, sitting between
    the document and the shared rule evaluator. Absent conditions mean visible;
    an authored-but-empty group means hidden. Without the distinction the two
    cases are indistinguishable and the unfinished one wins."""
    assert is_visible(tree, {"answers.agree": True}) is expected


@pytest.mark.parametrize("garbage", ["yes", 1, [{"fact": "x"}], object()])
def test_is_visible_fails_closed_on_a_tree_it_cannot_read(garbage):
    """A stale or hand-edited tree must hide the field, not raise inside the
    submit request. Hiding is the safe direction: it drops an answer, where
    revealing could require an unanswerable question."""
    assert is_visible(garbage, {}) is False


# ---------------------------------------------------------------------------
# text family
# ---------------------------------------------------------------------------

def test_required_text_rejects_whitespace_only():
    """A space is not an answer. Accepting it would let a required field be
    satisfied by pressing the space bar."""
    document = doc(field("text", key="t", required=True))
    assert errors_of(document, {"t": "   "}) == {"t": REQUIRED}
    assert errors_of(document, {"t": ""}) == {"t": REQUIRED}
    assert errors_of(document, {"t": None}) == {"t": REQUIRED}


def test_text_length_bounds():
    document = doc(field("text", key="t", text={"minLength": 3, "maxLength": 5}))
    assert errors_of(document, {"t": "abcd"}) == {}
    assert "t" in errors_of(document, {"t": "ab"})
    assert "t" in errors_of(document, {"t": "abcdef"})


def test_a_pattern_matches_with_search_not_fullmatch():
    """The pattern is authored as an ECMAScript source string and the client uses
    ``RegExp.test``, which is a search. Compiling it as a fullmatch here would
    reject values the client accepted, so the user sees an error on a form that
    said it was valid."""
    document = doc(field("text", key="t", text={"pattern": "[0-9]+", "patternMessage": "need a digit"}))
    assert errors_of(document, {"t": "abc123"}) == {}
    assert errors_of(document, {"t": "abc"}) == {"t": "need a digit"}


def test_a_pattern_failure_without_a_message_still_reports_something():
    """The publish gate requires a message, but a legacy or hand-edited document
    may lack one. An empty error string would render as a red field with no
    text."""
    document = doc(field("text", key="t", text={"pattern": "^[0-9]+$"}))
    errors = errors_of(document, {"t": "abc"})
    assert "t" in errors and errors["t"].strip()


def test_an_uncompilable_pattern_does_not_break_the_submission():
    """Blocked at publish, but if one reaches runtime the submission must not
    500. Failing open here is deliberate: the author's regex is broken, not the
    user's answer."""
    document = doc(field("text", key="t", text={"pattern": "([0-9]+", "patternMessage": "x"}))
    assert errors_of(document, {"t": "anything"}) == {}


@pytest.mark.parametrize(
    "value,ok",
    [
        ("a@b.co", True),
        ("first.last@sub.domain.my", True),
        ("nope", False),
        ("a@b", False),
        ("a b@c.co", False),
        ("@b.co", False),
    ],
)
def test_email_shape(value, ok):
    """Pragmatic shape only. Deliverability is never asserted, so the rule must
    not reject legitimate addresses."""
    errors = errors_of(doc(field("email", key="e")), {"e": value})
    assert (errors == {}) is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("https://x.com/path", True),
        ("http://x.com", True),
        ("ftp://x.com", False),
        ("javascript:alert(1)", False),
        ("notaurl", False),
        ("https://", False),
    ],
)
def test_url_shape(value, ok):
    """Only http/https. A stored ``javascript:`` URL rendered as a link in the
    admin detail page is a stored XSS."""
    errors = errors_of(doc(field("url", key="u")), {"u": value})
    assert (errors == {}) is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("+60 12-345 6789", True),
        ("(555) 123-4567", True),
        ("0123456789", True),
        ("123", False),
        ("abc", False),
        ("+6012345678901234567890", False),
    ],
)
def test_phone_shape(value, ok):
    """Permissive on purpose (international formats vary), but a 3-digit or
    alphabetic value is not a number anyone can call back."""
    errors = errors_of(doc(field("phone", key="p")), {"p": value})
    assert (errors == {}) is ok


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------

def test_number_bounds_and_step():
    """Bounds and step are what make a quantity field meaningful. A step is
    measured from ``min`` when one is set, not from zero."""
    document = doc(field("number", key="n", number={"min": 0, "max": 10, "step": 2}))
    assert errors_of(document, {"n": 4}) == {}
    assert "n" in errors_of(document, {"n": 11})
    assert "n" in errors_of(document, {"n": -1})
    assert "n" in errors_of(document, {"n": 3})


def test_a_numeric_string_is_accepted():
    """Every answer typed into a text input arrives as a string. Rejecting "4"
    would fail the commonest case."""
    assert errors_of(doc(field("number", key="n")), {"n": "4"}) == {}
    assert errors_of(doc(field("number", key="n")), {"n": "4.5"}) == {}


@pytest.mark.parametrize("value", ["x", "", "1,000", True, False, [1], {"a": 1}])
def test_a_non_number_is_rejected_or_treated_as_empty(value):
    """Booleans are not 1/0 here: a yesno answer pasted into a number field must
    not silently become a quantity."""
    document = doc(field("number", key="n", required=True))
    assert "n" in errors_of(document, {"n": value})


@pytest.mark.parametrize("value", ["1e400", "-1e400", "nan", "inf", "Infinity", float("inf"), float("nan")])
def test_a_non_finite_number_is_rejected(value):
    """``inf``/``nan`` serialise as ``Infinity``/``NaN``, which are not valid JSON
    and are rejected by the JSONB column - so a 200-looking validation followed
    by a 500 on insert."""
    assert "n" in errors_of(doc(field("number", key="n")), {"n": value})


def test_the_integer_field_type_rejects_a_fraction():
    """A quantity of 2.5 units is not orderable."""
    document = doc(field("integer", key="qty", required=True))
    errors = errors_of(document, {"qty": "2.5"})
    assert "qty" in errors and "whole" in errors["qty"].lower()
    assert errors_of(document, {"qty": "30"}) == {}


def test_decimal_places_are_capped_including_scientific_notation():
    """``1e-07`` has seven decimal places. Counting the digits after the "." in
    the raw string would see none and let it through, then store a price with
    more precision than the money column."""
    document = doc(field("number", key="price", number={"decimals": 2}))
    assert errors_of(document, {"price": "1.23"}) == {}
    assert "price" in errors_of(document, {"price": "1.234"})
    assert "price" in errors_of(document, {"price": "1e-07"})


# ---------------------------------------------------------------------------
# choices
# ---------------------------------------------------------------------------

def test_select_membership_is_enforced_server_side():
    """The client renders the option list; a caller can send anything. An
    unvalidated value pollutes every report that groups by this field."""
    document = doc(field("select", key="s", options=opts("a", "b")))
    assert errors_of(document, {"s": "a"}) == {}
    assert "s" in errors_of(document, {"s": "z"})


def test_a_select_answer_is_stored_as_the_string_option_value():
    """Option values are strings. A numeric ``0`` that passes membership against
    the option ``"0"`` must be stored as ``"0"``, or equality conditions, CSV
    export and label lookup all disagree with each other."""
    document = doc(field("select", key="pick", options={"kind": "static", "items": [{"value": "0", "label": "Zero"}]}))
    clean = clean_of(document, {"pick": 0})
    assert clean["pick"] == "0"


def test_radio_membership_is_enforced():
    document = doc(field("radio", key="r", options=opts("x", "y")))
    assert errors_of(document, {"r": "y"}) == {}
    assert "r" in errors_of(document, {"r": "nope"})


def test_multiselect_requires_a_list_of_known_unique_values():
    """A duplicate selection would double-count in any aggregation over the
    stored array."""
    document = doc(field("multiselect", key="m", options=opts("a", "b", "c")))
    assert errors_of(document, {"m": ["a", "c"]}) == {}
    assert "m" in errors_of(document, {"m": ["a", "z"]})
    assert "m" in errors_of(document, {"m": ["a", "a"]})
    assert "m" in errors_of(document, {"m": "a"})
    assert "m" in errors_of(document, {"m": [1]})


def test_checkboxes_follow_the_multiselect_rules():
    """Same storage shape, different renderer. Only validating one of the two
    leaves the other unchecked."""
    document = doc(field("checkboxes", key="c", options=opts("a", "b")))
    assert errors_of(document, {"c": ["a"]}) == {}
    assert "c" in errors_of(document, {"c": ["a", "zzz"]})


def test_an_empty_multi_choice_is_only_an_error_when_required():
    assert errors_of(doc(field("multiselect", key="m", options=opts("a"))), {"m": []}) == {}
    assert "m" in errors_of(doc(field("multiselect", key="m", required=True, options=opts("a"))), {"m": []})


# ---------------------------------------------------------------------------
# yesno, dates, rating, signature
# ---------------------------------------------------------------------------

def test_yesno_must_be_a_real_boolean():
    """"false" is a truthy string. Accepting it would invert the answer to a
    warranty acknowledgement."""
    document = doc(field("yesno", key="y"))
    assert errors_of(document, {"y": True}) == {}
    assert errors_of(document, {"y": False}) == {}
    assert "y" in errors_of(document, {"y": "true"})
    assert "y" in errors_of(document, {"y": 1})


@pytest.mark.parametrize(
    "value,ok",
    [
        ("2026-06-10", True),
        ("06/10/2026", False),
        ("2026-13-99", False),
        ("2026-6-1", False),
        ("2026-06-10T00:00:00", False),
    ],
)
def test_date_is_strictly_iso_calendar_date(value, ok):
    """Exactly ``YYYY-MM-DD``, zero-padded.

    A DELIBERATE tightening of the source, which validates with
    ``strptime(value, "%Y-%m-%d")``. That accepts ``2026-6-1`` too, because
    ``%m``/``%d`` match one OR two digits - so two spellings of the same day can
    both be stored. Dates live in a JSONB answer map and are compared, sorted and
    grouped as STRINGS, where ``"2026-6-1" > "2026-12-01"``. The HTML date input
    always emits a padded value, so requiring the shape rejects nothing a real
    client sends. Guard the format with a regex before parsing.
    """
    errors = errors_of(doc(field("date", key="d")), {"d": value})
    assert (errors == {}) is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("2026-06-10T14:30:00", True),
        ("2026-06-10T14:30:00Z", True),
        ("2026-06-10T14:30:00+08:00", True),
        ("2026-06-10", True),
        ("not-a-time", False),
        ("2026-06-10T25:00:00", False),
    ],
)
def test_datetime_accepts_iso_instants_including_a_z_suffix(value, ok):
    """The FE sends a ``Z``-suffixed instant; python's ``fromisoformat`` did not
    accept ``Z`` before 3.11, so this is the case a port silently breaks. A
    date-only value is also accepted: it is a calendar instant."""
    errors = errors_of(doc(field("datetime", key="dt")), {"dt": value})
    assert (errors == {}) is ok


def test_an_empty_datetime_is_only_an_error_when_required():
    """Emptiness is checked before format, for every scalar type. Otherwise a
    skipped optional field reports "enter a valid date and time"."""
    assert errors_of(doc(field("datetime", key="dt")), {"dt": ""}) == {}
    assert "dt" in errors_of(doc(field("datetime", key="dt", required=True)), {"dt": ""})


def test_rating_must_be_a_whole_number_within_the_scale():
    document = doc(field("rating", key="r", rating={"max": 5}))
    assert errors_of(document, {"r": 3}) == {}
    assert errors_of(document, {"r": "5"}) == {}
    assert "r" in errors_of(document, {"r": 0})
    assert "r" in errors_of(document, {"r": 6})
    assert "r" in errors_of(document, {"r": 2.5})


def test_rating_falls_back_to_a_five_point_scale():
    """A document without a rating bag is blocked at publish, but a legacy one
    must still validate against something rather than accept any integer."""
    document = doc(field("rating", key="r"))
    assert errors_of(document, {"r": 5}) == {}
    assert "r" in errors_of(document, {"r": 99})


def test_a_signature_is_any_non_empty_string():
    """The value is an opaque data URL or storage key; the engine only checks
    presence, because the bytes are handled by the upload layer."""
    document = doc(field("signature", key="sig", required=True))
    assert errors_of(document, {"sig": "data:image/png;base64,AAAA"}) == {}
    assert "sig" in errors_of(document, {"sig": ""})
    assert "sig" in errors_of(document, {"sig": {"not": "a string"}})


# ---------------------------------------------------------------------------
# address composite
# ---------------------------------------------------------------------------

def test_an_address_stores_only_whitelisted_sub_keys():
    """The composite is a fixed shape. An extra key would be stored forever and
    is a place to smuggle unvalidated data into the JSONB payload."""
    answer = {"line1": "1 Main St", "city": "Town", "country": "MY", "evil": "DROP ME"}
    clean = clean_of(doc(field("address", key="addr", required=True)), {"addr": answer})
    assert clean["addr"] == {"line1": "1 Main St", "city": "Town", "country": "MY"}


def test_a_partially_filled_address_reports_the_missing_line():
    """Once the user starts an address, the deliverable parts are mandatory: a
    city with no street cannot be shipped to."""
    errors = errors_of(doc(field("address", key="addr", required=True)), {"addr": {"city": "Town"}})
    assert "addr" in errors


def test_an_untouched_optional_address_is_not_an_error():
    assert errors_of(doc(field("address", key="addr")), {"addr": {}}) == {}
    assert errors_of(doc(field("address", key="addr")), {"addr": None}) == {}


def test_an_untouched_required_address_is_an_error():
    assert "addr" in errors_of(doc(field("address", key="addr", required=True)), {"addr": {}})


# ---------------------------------------------------------------------------
# file uploads
# ---------------------------------------------------------------------------

_FILE = {"key": "k1", "name": "receipt.pdf", "size": 1024, "mime": "application/pdf"}


def test_a_file_answer_must_be_a_list_of_upload_descriptors():
    """The answer is a list of ``{key, name, size, mime}``. Anything else is a
    client that did not complete the upload handshake, so it counts as no file
    at all rather than as a valid answer."""
    document = doc(field("file", key="f", required=True))
    assert errors_of(document, {"f": [_FILE]}) == {}
    assert "f" in errors_of(document, {"f": []})
    assert "f" in errors_of(document, {"f": "receipt.pdf"})
    assert "f" in errors_of(document, {"f": [{"name": "no key"}]})


def test_malformed_upload_descriptors_are_dropped_from_the_stored_answer():
    """A half-formed entry must not survive into storage, where the download
    route would later dereference a missing key."""
    document = doc(field("file", key="f"))
    clean = clean_of(document, {"f": [_FILE, {"name": "junk"}, "nope"]})
    assert clean["f"] == [_FILE]


def test_the_file_count_cap_is_enforced():
    """``maxCount`` is the only upload limit the engine can enforce from the
    answer alone; size and mime are re-checked at upload time."""
    document = doc(field("file", key="f", file={"maxCount": 1}))
    assert errors_of(document, {"f": [_FILE]}) == {}
    assert "f" in errors_of(document, {"f": [_FILE, dict(_FILE, key="k2")]})


def test_an_optional_file_field_may_be_empty():
    assert errors_of(doc(field("file", key="f")), {"f": []}) == {}


# ---------------------------------------------------------------------------
# repeater rows
# ---------------------------------------------------------------------------

def test_repeater_errors_are_keyed_by_row_index_and_sub_key():
    """The renderer highlights the offending cell. A single error on the whole
    repeater would tell a user with 20 rows only that something is wrong."""
    rows = [{"note": "ok", "hours": 5}, {"note": "", "hours": "bad"}]
    errors = errors_of(doc(repeater_field()), {"notes": rows})
    assert errors["notes.1.note"] == REQUIRED
    assert "notes.1.hours" in errors
    assert "notes.0.note" not in errors


def test_repeater_row_bounds():
    document = doc(repeater_field(minRows=2, maxRows=3))
    assert errors_of(document, {"notes": [{"note": "a"}, {"note": "b"}]}) == {}
    assert "notes" in errors_of(document, {"notes": [{"note": "a"}]})
    assert "notes" in errors_of(document, {"notes": [{"note": str(i)} for i in range(4)]})


def test_a_min_rows_repeater_cannot_be_submitted_empty():
    """``minRows`` implies required. Otherwise a form that demands at least one
    line item accepts zero."""
    assert "notes" in errors_of(doc(repeater_field(minRows=1)), {"notes": []})
    assert "notes" in errors_of(doc(repeater_field(minRows=1)), {})


def test_an_optional_repeater_may_be_empty():
    assert errors_of(doc(repeater_field()), {"notes": []}) == {}
    assert errors_of(doc(repeater_field()), {}) == {}


def test_repeater_rows_drop_undeclared_sub_keys():
    """Rows are free-form JSON on the wire. Only declared sub-fields are
    stored."""
    clean = clean_of(doc(repeater_field()), {"notes": [{"note": "ok", "junk": "DROP"}]})
    assert clean["notes"] == [{"note": "ok"}]


def test_rows_that_are_not_objects_are_ignored():
    """A stray string in the rows array must not abort validation of the real
    rows around it."""
    clean = clean_of(doc(repeater_field()), {"notes": [{"note": "a"}, "junk", None]})
    assert clean["notes"] == [{"note": "a"}]


@pytest.mark.parametrize(
    "sub_type,value,ok",
    [
        ("text", "hello", True),
        ("email", "a@b.co", True),
        ("email", "nope", False),
        ("url", "https://x.com", True),
        ("url", "nope", False),
        ("phone", "+60 12 345 6789", True),
        ("phone", "ab", False),
        ("number", "12", True),
        ("number", "abc", False),
        ("date", "2026-06-10", True),
        ("date", "10/06/2026", False),
        ("yesno", True, True),
        ("yesno", "true", False),
    ],
)
def test_sub_fields_are_type_checked_like_top_level_fields(sub_type, value, ok):
    """A repeater row is not a free-for-all: the same per-type rules apply, or
    the line items of an exchange request are the one unvalidated part of the
    form."""
    subs = [{"id": "s1", "type": sub_type, "key": "v", "label": "V"}]
    errors = errors_of(doc(repeater_field(subs=subs)), {"notes": [{"v": value}]})
    assert (errors == {}) is ok, errors


def test_a_sub_field_choice_must_be_a_declared_option():
    subs = [{"id": "s1", "type": "select", "key": "v", "label": "V", "options": opts("a", "b")}]
    document = doc(repeater_field(subs=subs))
    assert errors_of(document, {"notes": [{"v": "a"}]}) == {}
    assert "notes.0.v" in errors_of(document, {"notes": [{"v": "z"}]})


def test_a_sub_field_rating_is_bounded():
    subs = [{"id": "s1", "type": "rating", "key": "v", "label": "V", "rating": {"max": 3}}]
    document = doc(repeater_field(subs=subs))
    assert errors_of(document, {"notes": [{"v": 3}]}) == {}
    assert "notes.0.v" in errors_of(document, {"notes": [{"v": 4}]})


# ---------------------------------------------------------------------------
# table rows
# ---------------------------------------------------------------------------

def test_table_cell_errors_are_keyed_by_row_index_and_column():
    errors = errors_of(doc(table_field()), {"lines": [{"item": "", "qty": 5, "unit_price": 2}]})
    assert errors["lines.0.item"] == REQUIRED


def test_a_computed_column_is_recomputed_per_row_and_the_client_value_ignored():
    """The line amount is money. A client-supplied ``amount`` is a price the
    customer chose for themselves."""
    answers = {
        "lines": [
            {"item": "A", "qty": 5, "unit_price": 10, "amount": 9999},
            {"item": "B", "qty": "2", "unit_price": "3"},
        ]
    }
    clean = clean_of(doc(table_field()), answers)
    assert clean["lines"][0]["amount"] == 50
    assert clean["lines"][1]["amount"] == 6


def test_a_fixed_column_is_stamped_server_side_and_feeds_later_computed_columns():
    """The tax rate is not asked for and not accepted from the client; it is a
    constant on the definition. A later computed column must see the stamped
    value, not the submitted one."""
    cols = [
        {"id": "c1", "type": "number", "key": "qty", "label": "Qty", "required": True},
        {"id": "c2", "type": "fixed", "key": "tax_rate", "label": "Tax", "fixedValue": "0.06"},
        {"id": "c3", "type": "computed", "key": "tax", "label": "Tax amount",
         "computed": {"expression": "qty * tax_rate"}, "summarize": "sum"},
    ]
    clean = clean_of(doc(table_field(columns=cols)), {"lines": [{"qty": 10, "tax_rate": "999"}]})
    row = clean["lines"][0]
    assert row["tax_rate"] == "0.06"
    assert row["tax"] == pytest.approx(0.6)


def test_a_computed_column_that_cannot_be_evaluated_stores_an_empty_cell():
    """A blank optional operand must not store ``None`` where the FE renders a
    number, and must never store ``inf``."""
    clean = clean_of(doc(table_field()), {"lines": [{"item": "A", "qty": 5}]})
    assert clean["lines"][0]["amount"] == ""


def test_table_rows_drop_undeclared_keys():
    clean = clean_of(doc(table_field()), {"lines": [{"item": "X", "qty": 1, "unit_price": 1, "junk": "evil"}]})
    assert "junk" not in clean["lines"][0]


def test_computed_and_fixed_columns_are_not_validated_as_user_input():
    """They are derived, so a required-looking blank in the client payload is
    irrelevant: the server fills them in."""
    cols = [
        {"id": "c1", "type": "number", "key": "qty", "label": "Qty", "required": True},
        {"id": "c2", "type": "fixed", "key": "rate", "label": "Rate", "required": True, "fixedValue": "2"},
        {"id": "c3", "type": "computed", "key": "amount", "label": "Amount", "required": True,
         "computed": {"expression": "qty * rate"}},
    ]
    assert errors_of(doc(table_field(columns=cols)), {"lines": [{"qty": 3}]}) == {}


def test_table_row_bounds():
    document = doc(table_field(minRows=2, maxRows=3))
    rows = [{"item": "A", "qty": 1, "unit_price": 1}]
    assert "lines" in errors_of(document, {"lines": rows})
    assert "lines" in errors_of(document, {"lines": rows * 4})
    assert errors_of(document, {"lines": rows * 2}) == {}


def test_a_required_table_cannot_be_submitted_empty():
    assert "lines" in errors_of(doc(table_field(minRows=1)), {"lines": []})
    assert errors_of(doc(table_field()), {"lines": []}) == {}


def test_table_cell_bounds_and_precision_are_enforced_per_column():
    cols = [
        {"id": "c1", "type": "number", "key": "price", "label": "Price", "decimals": 2, "number": {"min": 1, "max": 100}},
        {"id": "c2", "type": "integer", "key": "age", "label": "Age"},
    ]
    document = doc(table_field(columns=cols))
    errors = errors_of(document, {"lines": [{"price": "1.234", "age": "2.5"}]})
    assert "decimal" in errors["lines.0.price"].lower()
    assert "whole" in errors["lines.0.age"].lower()
    assert "lines.0.price" in errors_of(document, {"lines": [{"price": "0.5", "age": "2"}]})
    assert errors_of(document, {"lines": [{"price": "1.23", "age": "30"}]}) == {}


def test_a_table_select_cell_must_be_a_declared_option():
    cols = [
        {"id": "c1", "type": "select", "key": "reason", "label": "Reason", "options": opts("faulty", "wrong_item")},
    ]
    document = doc(table_field(columns=cols))
    assert errors_of(document, {"lines": [{"reason": "faulty"}]}) == {}
    assert "lines.0.reason" in errors_of(document, {"lines": [{"reason": "because"}]})


# ---------------------------------------------------------------------------
# computed fields
# ---------------------------------------------------------------------------

def test_a_computed_answer_is_recomputed_and_the_client_value_ignored():
    """Never trust the client. The stored total is the one the definition says it
    is, not the one the body claimed."""
    document = doc(
        field("number", key="qty"),
        field("number", key="price"),
        field("computed", key="total", computed={"expression": "qty * price"}),
    )
    clean = clean_of(document, {"qty": 10, "price": 100, "total": 999})
    assert clean["total"] == 1000


def test_a_computed_answer_is_always_present_even_when_it_cannot_be_evaluated():
    """The key must exist in the payload so a report reading it does not have to
    distinguish "no answer" from "field did not exist"."""
    document = doc(
        field("number", key="qty"),
        field("computed", key="total", computed={"expression": "qty * 2"}),
    )
    clean, errors = validate_submission(document, {})
    assert errors == {}
    assert "total" in clean and clean["total"] is None


def test_a_computed_overflow_stores_null_not_infinity():
    """Two finite answers can multiply to ``inf``, which is invalid JSON and
    fails the JSONB insert - a 500 after a clean validation."""
    document = doc(
        field("number", key="a"),
        field("number", key="b"),
        field("computed", key="c", computed={"expression": "a * b"}),
    )
    clean = clean_of(document, {"a": 1e308, "b": 1e308})
    assert clean["c"] is None or math.isfinite(clean["c"])
    assert clean["c"] is None


def test_a_computed_field_only_sees_visible_answers():
    """It is recomputed from the CLEANED map, so a hidden upstream number
    contributes nothing. Reading the raw body instead would let a caller drive a
    total through a field the form never showed."""
    document = doc(
        field("yesno", key="gate"),
        field("number", key="qty", conditionsJson=cond("answers.gate")),
        field("computed", key="total", computed={"expression": "qty * 2"}),
    )
    hidden = clean_of(document, {"gate": False, "qty": 50})
    assert hidden["total"] is None
    visible = clean_of(document, {"gate": True, "qty": 50})
    assert visible["total"] == 100


def test_a_form_level_aggregate_totals_the_table_rows():
    """The reason the aggregate exists: an order total with no bespoke code."""
    document = doc(
        table_field(),
        field("computed", key="grand", computed={"expression": "sum(lines.amount)"}),
    )
    answers = {"lines": [
        {"item": "A", "qty": 2, "unit_price": 3},
        {"item": "B", "qty": 4, "unit_price": 5},
    ]}
    clean = clean_of(document, answers)
    assert clean["grand"] == 26


def test_a_form_level_aggregate_totals_repeater_rows():
    document = doc(
        repeater_field(),
        field("computed", key="total_hours", computed={"expression": "sum(notes.hours)"}),
    )
    clean = clean_of(document, {"notes": [{"note": "a", "hours": 2}, {"note": "b", "hours": "3.5"}]})
    assert clean["total_hours"] == pytest.approx(5.5)


def test_a_computed_field_with_no_expression_is_null_not_an_error():
    """Blocked at publish. At runtime it must degrade to null rather than 500 a
    submission the user cannot fix."""
    document = doc(field("computed", key="c", computed={"expression": ""}))
    clean, errors = validate_submission(document, {})
    assert errors == {}
    assert clean["c"] is None
