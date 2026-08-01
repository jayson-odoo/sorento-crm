"""The computed-expression engine ported from foundryx-shared-service (plan F0).

Written before the implementation, per PRINCIPLES step 4. Target module:
``app.form_engine.computed``.

This is the highest-risk file in the port because it is the only place in the
codebase where a *tenant-authored string* is turned into arithmetic. Three
properties matter more than any individual formula:

* ``test_no_python_evaluation_path`` -- the reason this parser exists at all. A
  form definition is authored data; running it through ``eval``, ``exec``,
  ``ast.literal_eval`` or a template engine would be an SSTI to RCE vector. The
  grammar must accept numbers, field refs, ``+ - * /``, unary minus, parens and
  the five aggregates, and reject literally everything else.
* the fail-closed table -- a missing answer, a null, a non-numeric string, a
  boolean, or a division by zero must all produce ``None`` and never raise.
  ``evaluate`` runs inside the submit request path, so one raise there is a 500
  on a form the user filled in correctly.
* the hard caps -- ``MAX_EXPR_LEN`` / ``MAX_TOKENS`` are the DoS guard. Without
  the token cap, a deeply parenthesised expression recurses until the
  interpreter dies.

Pure unit tests, no database. Run:
    venv/bin/pytest tests/test_form_engine_computed.py -q
"""
from __future__ import annotations

import math

import pytest

from app.form_engine.computed import (
    AGGREGATE_FUNCS,
    AggregateRef,
    ComputedExpressionError,
    MAX_EXPR_LEN,
    MAX_TOKENS,
    ParsedExpression,
    aggregate_refs,
    evaluate,
    field_refs,
    parse_expression,
)


def _fin(value) -> float:
    """Assert the result is a finite float and hand it back.

    Every arithmetic result is a float, even a whole-number one: the JSON column
    stores what this returns, so an int/float mix would make two submissions of
    the same form disagree on type.
    """
    assert isinstance(value, float), f"expected a float, got {value!r}"
    assert math.isfinite(value), f"expected a finite float, got {value!r}"
    return value


# ---------------------------------------------------------------------------
# parse_expression -- the public parse result
# ---------------------------------------------------------------------------

def test_parse_returns_a_parsed_expression_with_a_trimmed_source():
    """The publish gate stores/echoes ``source``; leading space would make two
    identical formulas compare unequal."""
    parsed = parse_expression("  qty * 2  ")
    assert isinstance(parsed, ParsedExpression)
    assert parsed.source == "qty * 2"


def test_field_refs_are_the_scalar_keys_only_and_deduplicated():
    """``field_refs`` drives the publish gate's earlier-numeric-field check, so
    a key repeated three times must not produce three problems."""
    parsed = parse_expression("x + x * (x - unit_price)")
    assert parsed.field_refs == frozenset({"x", "unit_price"})


def test_literal_only_expression_references_nothing():
    """A constant formula is legal and must not invent a field reference."""
    assert parse_expression("3.14").field_refs == frozenset()


def test_aggregate_arguments_are_not_scalar_field_refs():
    """``sum(lines.qty)`` must NOT surface ``lines`` (or ``lines.qty``) as a
    scalar ref: the gate checks scalar refs against numeric *fields* and would
    reject a repeater key that is perfectly valid as an aggregate target."""
    assert field_refs("sum(lines.qty) + fee") == frozenset({"fee"})


def test_aggregate_refs_carry_func_repeater_and_column():
    """The gate needs all three parts to check "earlier repeater" plus "numeric
    column"; collapsing them into one string would make that check impossible."""
    aggs = aggregate_refs("sum(lines.qty) / count(lines)")
    assert isinstance(aggs, tuple)
    assert all(isinstance(a, AggregateRef) for a in aggs)
    assert {(a.func, a.repeater_key, a.sub_key) for a in aggs} == {
        ("sum", "lines", "qty"),
        ("count", "lines", None),
    }


def test_aggregate_function_set_is_exactly_the_whitelist():
    """The whitelist is the security boundary for the call syntax: anything not
    in it must be a parse error, so the set itself is part of the contract."""
    assert AGGREGATE_FUNCS == frozenset({"sum", "avg", "count", "min", "max"})


# ---------------------------------------------------------------------------
# arithmetic: precedence, associativity, parentheses, unary minus
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "expr,expected",
    [
        # multiplication and division bind tighter than addition/subtraction.
        ("2 + 3 * 4", 14.0),
        ("2 * 3 + 4", 10.0),
        ("10 - 8 / 4", 8.0),
        ("8 / 4 - 10", -8.0),
        # left associativity: getting this wrong flips the sign of real invoices.
        ("8 - 3 - 2", 3.0),
        ("8 / 4 / 2", 1.0),
        ("1 + 2 + 3", 6.0),
        # parentheses override precedence.
        ("(2 + 3) * 4", 20.0),
        ("10 / (2 + 3)", 2.0),
        ("((2 + 3))", 5.0),
        ("(1 + 2) * (3 + 4)", 21.0),
        # unary minus, including doubled and applied to a parenthesised group.
        ("-3 + 5", 2.0),
        ("2 * -3", -6.0),
        ("- -4", 4.0),
        ("-(2 + 3)", -5.0),
        # unicode operator aliases: the builder offers x and division signs.
        ("3 × 4", 12.0),
        ("10 ÷ 4", 2.5),
        ("2 × 3 + 10 ÷ 2", 11.0),
        # decimals.
        ("0.5 * 4", 2.0),
        ("1.25 + 2.75", 4.0),
    ],
)
def test_arithmetic_table(expr, expected):
    """One table for the whole grammar. Precedence and associativity are the
    bugs nobody notices: a wrong answer looks like a plausible number, so only a
    table of known-good results catches it."""
    assert _fin(evaluate(expr, {})) == pytest.approx(expected)


def test_nesting_within_the_token_cap_parses():
    """Deep but legal nesting must work; the cap, not the recursion limit, is
    what bounds it."""
    expr = ("(" * 20) + "1 + 2" + (")" * 20)
    assert _fin(evaluate(expr, {})) == 3.0


# ---------------------------------------------------------------------------
# field references and value coercion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "values,expected",
    [
        ({"qty": 3, "unit_price": 10}, 30.0),
        ({"qty": 3.5, "unit_price": 2}, 7.0),
        # numeric strings: every answer arriving from a JSON form body is a
        # string when the input was typed, so refusing them would break the
        # commonest case of all.
        ({"qty": "3", "unit_price": "10"}, 30.0),
        ({"qty": " 3 ", "unit_price": 10}, 30.0),
        ({"qty": "3.5", "unit_price": "2"}, 7.0),
    ],
)
def test_field_reference_coercion(values, expected):
    """Answers reach the evaluator as whatever JSON carried, so int, float and
    numeric string must all resolve; anything else fails closed (below)."""
    assert _fin(evaluate("qty * unit_price", values)) == pytest.approx(expected)


def test_extra_values_are_ignored():
    """The evaluator is handed the whole cleaned answer map, most of which is
    irrelevant to a given formula."""
    assert _fin(evaluate("qty", {"qty": 2, "name": "Jane", "rows": [{}]})) == 2.0


# ---------------------------------------------------------------------------
# fail-closed evaluation -- never raise, never guess
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "expr,values",
    [
        # missing operand.
        ("qty * 2", {}),
        ("a + b", {"a": 5}),
        # explicit null: a visible-but-unanswered optional number.
        ("qty * 2", {"qty": None}),
        # non-numeric text.
        ("qty", {"qty": "hello"}),
        ("qty", {"qty": ""}),
        # booleans are NOT 1/0 in this domain: a yesno answer must not silently
        # contribute 1 to a money total.
        ("x", {"x": True}),
        ("x", {"x": False}),
        ("x + 1", {"x": True}),
        # containers.
        ("x", {"x": [1, 2]}),
        ("x", {"x": {"a": 1}}),
        # division by zero, literal and via a reference.
        ("10 / 0", {}),
        ("1 / x", {"x": 0}),
        ("1 / x", {"x": "0"}),
        ("1 / (2 - 2)", {}),
        # a raw string with a syntax error: evaluate() parses on the fly and must
        # still not raise into the request path.
        ("2 +", {}),
        ("$$$", {}),
    ],
)
def test_evaluate_fails_closed_to_none(expr, values):
    """``None`` is the only failure mode ``evaluate`` may have.

    It runs inside the submit request, so a raise here is a 500 on a valid
    submission, and a guessed 0 would silently store a wrong total.
    """
    assert evaluate(expr, values) is None


def test_evaluate_rejects_a_wrong_type_of_expression():
    """Defensive: a caller passing a dict or an int must get ``None``, not an
    AttributeError from deep inside the walker."""
    assert evaluate(42, {}) is None  # type: ignore[arg-type]
    assert evaluate(None, {}) is None  # type: ignore[arg-type]
    assert evaluate({"expression": "1+1"}, {}) is None  # type: ignore[arg-type]


def test_evaluate_accepts_a_pre_parsed_expression():
    """Recomputing every row of a table would re-parse the same string N times;
    the pre-parsed form is the hot path."""
    parsed = parse_expression("x * 2 + 1")
    assert _fin(evaluate(parsed, {"x": 3})) == 7.0
    assert _fin(evaluate(parsed, {"x": 4})) == 9.0


def test_overflow_to_infinity_is_not_reported_as_a_number():
    """``inf`` serialises as ``Infinity``, which is not valid JSON and is
    rejected by the JSONB column on insert. Two finite operands can still
    overflow, so the caller must be able to tell."""
    result = evaluate("a * b", {"a": 1e308, "b": 1e308})
    assert result is None or not math.isfinite(result)


# ---------------------------------------------------------------------------
# syntax errors -- rejected at parse time, before any data is involved
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "expr",
    [
        "",
        "   ",
        "2 +",
        "* 2",
        "2 + * 3",
        "(2 + 3",
        "2 + 3)",
        "()",
        "2 2",
        "qty qty",
        "2 3 +",
        "/",
    ],
)
def test_syntax_errors_raise_at_parse_time(expr):
    """A mis-authored formula must fail loudly at publish, not silently compute
    the wrong number for every submission afterwards."""
    with pytest.raises(ComputedExpressionError):
        parse_expression(expr)


def test_empty_expression_message_names_the_problem():
    """The publish gate surfaces this string to the form author."""
    with pytest.raises(ComputedExpressionError, match="non-empty"):
        parse_expression("")


def test_trailing_content_is_reported_as_such():
    """``2 2`` parses a valid ``2`` and then stops. Without the trailing-token
    check the parser would silently accept it and drop the rest."""
    with pytest.raises(ComputedExpressionError, match="trailing"):
        parse_expression("2 2")


def test_exponentiation_is_rejected_explicitly():
    """``**`` is not in the grammar. It must not be mis-read as two multiplies:
    a typo that silently changes the maths is worse than an error."""
    with pytest.raises(ComputedExpressionError, match=r"\*\*"):
        parse_expression("2 ** 3")


@pytest.mark.parametrize(
    "expr",
    [
        "2 # 3",
        "10 % 3",
        "@qty",
        "2 ^ 3",
        "qty, price",
        "qty; price",
        "'qty'",
        '"qty"',
        "qty[0]",
        "{qty}",
        "qty > 2",
        "qty = 2",
        "qty & 2",
        "qty | 2",
        "1e5",
    ],
)
def test_illegal_characters_are_rejected(expr):
    """The tokeniser is a whitelist. Anything outside it - comparison
    operators, subscripts, quotes, separators, scientific notation - is a
    character the grammar has no meaning for and must not be skipped over."""
    with pytest.raises(ComputedExpressionError):
        parse_expression(expr)


def test_none_and_non_string_input_raise():
    """``parse_expression`` is called from the publish gate with whatever JSON
    put in ``computed.expression``, which may not be a string at all."""
    with pytest.raises(ComputedExpressionError):
        parse_expression(None)  # type: ignore[arg-type]
    with pytest.raises(ComputedExpressionError):
        parse_expression(123)  # type: ignore[arg-type]


def test_no_python_evaluation_path():
    """The security property this whole module exists for.

    A form definition is tenant-authored data. If the expression were ever fed
    to ``eval``/``exec``/``literal_eval`` or a template engine, these strings
    would be code execution. They must all be parse errors, and ``evaluate``
    must return ``None`` rather than doing anything at all.
    """
    hostile = [
        "__import__('os').system('id')",
        "().__class__.__bases__[0]",
        "{{7*7}}",
        "${7*7}",
        "eval('1+1')",
        "open('/etc/passwd')",
        "1 if True else 2",
        "[x for x in range(3)]",
        "lambda: 1",
    ]
    for expr in hostile:
        with pytest.raises(ComputedExpressionError):
            parse_expression(expr)
        assert evaluate(expr, {}) is None


def test_unknown_function_is_rejected():
    """Only the five aggregates may be called. An unknown name followed by
    ``(`` must not fall back to being read as a field reference times a
    parenthesised group."""
    with pytest.raises(ComputedExpressionError, match="function"):
        parse_expression("total(lines.qty)")
    with pytest.raises(ComputedExpressionError):
        parse_expression("round(qty)")


def test_aggregate_argument_arity_is_enforced():
    """``sum(lines)`` has no column to add up, and ``count(lines.qty)`` counts
    rows regardless of the column - accepting either would produce a number the
    author did not ask for."""
    with pytest.raises(ComputedExpressionError, match="column"):
        parse_expression("sum(lines)")
    with pytest.raises(ComputedExpressionError):
        parse_expression("avg(lines)")
    # count is the one function that takes a bare repeater key.
    assert aggregate_refs("count(lines)")[0].sub_key is None


def test_aggregate_names_are_case_insensitive():
    """The FE builder title-cases function names in its own UI; a form authored
    as ``SUM(...)`` must behave identically to ``sum(...)``."""
    assert aggregate_refs("SUM(lines.qty)")[0].func == "sum"
    assert evaluate("SUM(lines.qty)", {"lines": [{"qty": 2}, {"qty": 3}]}) == 5.0


# ---------------------------------------------------------------------------
# hard caps -- the DoS guard
# ---------------------------------------------------------------------------

def test_expression_over_the_length_cap_is_rejected():
    """Length is checked before tokenising, so a megabyte of garbage never
    reaches the regex."""
    with pytest.raises(ComputedExpressionError, match="character limit"):
        parse_expression("a" * (MAX_EXPR_LEN + 1))


def test_expression_over_the_token_cap_is_rejected():
    """A short string can still be thousands of tokens. The token cap is what
    bounds parser recursion, so it must trip on token count, not length."""
    expr = "+".join(["1"] * (MAX_TOKENS + 2))
    assert len(expr) < MAX_EXPR_LEN
    with pytest.raises(ComputedExpressionError, match="token limit"):
        parse_expression(expr)


def test_pathological_nesting_is_stopped_by_the_token_cap():
    """400 open parens would recurse the descent parser past the interpreter's
    limit. The cap must reject it before ``parse`` is entered."""
    expr = ("(" * 60) + "1" + (")" * 60)
    assert len(expr) < MAX_EXPR_LEN
    with pytest.raises(ComputedExpressionError):
        parse_expression(expr)


def test_caps_are_sane_values():
    """Pinned so a "temporary" bump does not ship: these two numbers are the
    only thing standing between an authored string and unbounded work."""
    assert MAX_EXPR_LEN == 1000
    assert MAX_TOKENS == 100


# ---------------------------------------------------------------------------
# aggregates over table / repeater rows
# ---------------------------------------------------------------------------

_ROWS = [{"item": "A", "qty": "3"}, {"item": "B", "qty": 5}, {"item": "C", "qty": None}]


@pytest.mark.parametrize(
    "expr,expected",
    [
        # a partially-filled column is the normal case, not an error: sum and
        # avg skip the blanks rather than poisoning the whole total.
        ("sum(lines.qty)", 8.0),
        ("avg(lines.qty)", 4.0),
        ("min(lines.qty)", 3.0),
        ("max(lines.qty)", 5.0),
        # count is over ROWS, not over non-null values in a column.
        ("count(lines)", 3.0),
        # aggregates compose with ordinary arithmetic.
        ("sum(lines.qty) * 2 + 1", 17.0),
        ("sum(lines.qty) / count(lines)", 8.0 / 3.0),
        ("-sum(lines.qty)", -8.0),
    ],
)
def test_aggregate_evaluation_table(expr, expected):
    """The whole point of the port: totalling line items without bespoke code.
    Mixed strings, ints and nulls in one column is what a real submission looks
    like."""
    assert _fin(evaluate(expr, {"lines": _ROWS})) == pytest.approx(expected)


@pytest.mark.parametrize("rows", [[], None, "not a list", 5, {}])
def test_empty_sum_is_zero_but_empty_avg_is_none(rows):
    """A sum over nothing is legitimately 0 (an empty order totals zero), while
    an average over nothing has no value and must not be reported as 0."""
    values = {} if rows is None else {"lines": rows}
    assert evaluate("sum(lines.qty)", values) == 0.0
    assert evaluate("avg(lines.qty)", values) is None
    assert evaluate("min(lines.qty)", values) is None
    assert evaluate("max(lines.qty)", values) is None


def test_aggregate_over_a_column_of_only_junk_behaves_like_an_empty_column():
    """Non-numeric cells are skipped, so a text column aggregates to the empty
    case rather than raising."""
    rows = [{"qty": "abc"}, {"qty": True}, {"qty": [1]}]
    assert evaluate("sum(lines.qty)", {"lines": rows}) == 0.0
    assert evaluate("avg(lines.qty)", {"lines": rows}) is None


def test_aggregate_skips_rows_that_are_not_objects():
    """Rows arrive from a JSON body and can be anything; a stray string in the
    array must not abort the whole total."""
    rows = [{"qty": 2}, "junk", None, {"qty": 3}]
    assert evaluate("sum(lines.qty)", {"lines": rows}) == 5.0


def test_aggregate_over_an_absent_column_is_the_empty_case():
    """Renaming a column leaves formulas pointing at a key no row carries. That
    is caught at publish, but at runtime it must degrade, not explode."""
    assert evaluate("sum(lines.ghost)", {"lines": _ROWS}) == 0.0
    assert evaluate("max(lines.ghost)", {"lines": _ROWS}) is None


def test_aggregate_null_result_poisons_the_surrounding_arithmetic():
    """``avg`` over an empty table is ``None``; using it in a larger formula must
    yield ``None`` rather than treating the missing average as zero."""
    assert evaluate("avg(lines.qty) + 1", {"lines": []}) is None


# ---------------------------------------------------------------------------
# circular references
# ---------------------------------------------------------------------------

def test_a_self_reference_parses_so_the_publish_gate_can_catch_it():
    """The parser has no idea which field owns the expression, so ``total`` in
    ``total + 1`` is just a reference. Detecting the cycle is the publish gate's
    job (document order), and it can only do that if the ref is reported here.

    See ``test_form_engine_schemas.py::test_computed_field_cannot_reference_itself``.
    """
    assert field_refs("total + 1") == frozenset({"total"})
    # At runtime a cycle can only ever be missing data, so it fails closed.
    assert evaluate("total + 1", {}) is None


def test_mutually_referencing_expressions_evaluate_to_none_not_a_loop():
    """Two formulas pointing at each other must not recurse. Because evaluation
    is a single pass over a value map, the absent operand simply fails closed."""
    assert evaluate("b + 1", {"a": None}) is None
    assert evaluate("a + 1", {"b": None}) is None
