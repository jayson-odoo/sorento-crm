"""Arithmetic expression parser and evaluator for computed form fields.

Ported from foundryx-shared-service (plan forms-platform F0).

Security rationale
------------------
A computed expression is TENANT-AUTHORED data evaluated against user-supplied
answers. It must NEVER reach Python ``eval`` / ``exec`` / ``ast.literal_eval``,
and never a general-purpose template engine: every one of those paths is an
SSTI to RCE vector. So this module ships its own tokeniser, recursive-descent
parser and AST over a deliberately tiny grammar. Anything outside the grammar
is a parse error, raised BEFORE any data touches the expression, so a
mis-authored formula fails loudly at publish instead of quietly computing the
wrong number for years.

At evaluate time the evaluator is fail-closed: a missing answer, a null, a
non-numeric string, a boolean, a container or a division by zero all produce
``None``. ``evaluate`` runs inside the submit request path, so one raise there
is a 500 on a form the user filled in correctly.

Grammar (EBNF)
--------------
    expr        = term  (( '+' | '-' )  term)*
    term        = unary (( '*' | '/' | '×' | '÷' )  unary)*
    unary       = '-' unary | primary
    primary     = NUMBER | IDENT | AGGREGATE | '(' expr ')'
    AGGREGATE   = FUNC '(' IDENT ')'
    NUMBER      = [0-9]+ ('.' [0-9]+)?
    IDENT       = [a-zA-Z_] [a-zA-Z0-9_]* ('.' [a-zA-Z_] [a-zA-Z0-9_]*)?

Hard caps
---------
- ``MAX_EXPR_LEN`` = 1000 characters, checked before tokenising.
- ``MAX_TOKENS``   = 100, checked after tokenising. This is the cap that bounds
  parser recursion: a short string can still be thousands of tokens.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple, Union

# ---- hard caps ----
MAX_EXPR_LEN: int = 1000
MAX_TOKENS: int = 100

# ---- token kinds ----
_TK_NUMBER = "NUMBER"
_TK_IDENT = "IDENT"
_TK_PLUS = "+"
_TK_MINUS = "-"
_TK_STAR = "*"
_TK_SLASH = "/"
_TK_LPAREN = "("
_TK_RPAREN = ")"
_TK_EOF = "EOF"

# The builder offers the unicode multiply/divide signs; both normalise to ASCII.
_UNICODE_MUL = "×"
_UNICODE_DIV = "÷"

# Order matters (longest match first). IDENT may carry ONE dotted segment
# (``repeater.subKey``) so an aggregate argument is a single token.
_TOKEN_RE = re.compile(
    r"(?P<NUMBER>[0-9]+(?:\.[0-9]+)?)"
    r"|(?P<IDENT>[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)"
    r"|(?P<OP>[+\-*/×÷()])"
    r"|(?P<WS>\s+)"
    r"|(?P<BAD>.)"  # catch-all: the tokeniser is a whitelist
)

# The only callable names in the grammar: ``sum/avg/min/max(repeater.column)``
# and ``count(repeater)``. The whitelist IS the security boundary for calls.
AGGREGATE_FUNCS: FrozenSet[str] = frozenset({"sum", "avg", "count", "min", "max"})


class ComputedExpressionError(ValueError):
    """Raised on any parse-time syntax or safety error.

    A ``ValueError`` subclass so a caller mapping it to a 422 can catch
    ``ValueError`` without an extra import.
    """


# ---- tokens ----


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str  # raw text from the source


# ---- public parse result ----


@dataclass(frozen=True)
class AggregateRef:
    """One ``func(repeaterKey.subKey)`` reference.

    The three parts stay separate because the publish gate checks each against a
    different thing: the repeater must be an earlier repeater/table field, and
    the column must be one of its numeric sub-fields.
    """

    func: str
    repeater_key: str
    sub_key: Optional[str]  # None for count(repeater)


@dataclass(frozen=True)
class ParsedExpression:
    """A successfully parsed expression.

    ``source`` is the trimmed original (two identical formulas must compare
    equal). ``field_refs`` are the SCALAR keys only, so an aggregate's repeater
    key is never mistaken for a numeric field. ``_ast`` is an implementation
    detail: callers use :func:`evaluate`.
    """

    source: str
    field_refs: FrozenSet[str]
    aggregates: Tuple[AggregateRef, ...] = ()
    _ast: object = field(default=None, repr=False, compare=False)


# ---- internal AST nodes (not exported) ----


@dataclass(slots=True)
class _Num:
    value: float


@dataclass(slots=True)
class _Ref:
    key: str


@dataclass(slots=True)
class _BinOp:
    op: str  # one of + - * /
    left: "_ASTNode"
    right: "_ASTNode"


@dataclass(slots=True)
class _UnaryMinus:
    operand: "_ASTNode"


@dataclass(slots=True)
class _Aggregate:
    func: str  # one of AGGREGATE_FUNCS
    repeater_key: str
    sub_key: Optional[str]


_ASTNode = Union[_Num, _Ref, _BinOp, _UnaryMinus, _Aggregate]


# ---- tokeniser ----


def _tokenise(source: str) -> List[_Token]:
    """A flat token list, whitespace dropped.

    ``**`` is rejected explicitly rather than read as two multiplies: a typo
    that silently changes the arithmetic is worse than an error.
    """
    tokens: List[_Token] = []
    prev_star = False

    for match in _TOKEN_RE.finditer(source):
        kind = match.lastgroup
        raw = match.group()

        if kind == "WS":
            prev_star = False
            continue

        if kind == "BAD":
            raise ComputedExpressionError(
                f"Unexpected character {raw!r} in expression."
            )

        if kind == "OP":
            if raw == _UNICODE_MUL:
                raw = "*"
            elif raw == _UNICODE_DIV:
                raw = "/"

            if raw == "*" and prev_star:
                raise ComputedExpressionError(
                    "Operator '**' is not supported; use '* *' for repeated "
                    "multiplication or rearrange with parentheses."
                )
            prev_star = raw == "*"

            op_map = {
                "+": _TK_PLUS,
                "-": _TK_MINUS,
                "*": _TK_STAR,
                "/": _TK_SLASH,
                "(": _TK_LPAREN,
                ")": _TK_RPAREN,
            }
            tokens.append(_Token(op_map[raw], raw))
        elif kind == "NUMBER":
            prev_star = False
            tokens.append(_Token(_TK_NUMBER, raw))
        elif kind == "IDENT":
            prev_star = False
            tokens.append(_Token(_TK_IDENT, raw))

    if len(tokens) > MAX_TOKENS:
        raise ComputedExpressionError(
            f"Expression exceeds the {MAX_TOKENS}-token limit."
        )

    tokens.append(_Token(_TK_EOF, ""))
    return tokens


# ---- recursive-descent parser ----


class _Parser:
    """Single-use: instantiate, call ``parse()``, discard."""

    def __init__(self, tokens: List[_Token]) -> None:
        self._tokens = tokens
        self._pos: int = 0

    # -- helpers --

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        token = self._tokens[self._pos]
        if token.kind != _TK_EOF:
            self._pos += 1
        return token

    def _expect(self, kind: str) -> _Token:
        token = self._advance()
        if token.kind != kind:
            raise ComputedExpressionError(
                f"Expected {kind!r} but got {token.kind!r} ({token.value!r})."
            )
        return token

    # -- grammar rules --

    def parse(self) -> _ASTNode:
        node = self._expr()
        if self._peek().kind != _TK_EOF:
            # "2 2" parses a valid 2 and then stops; without this check the rest
            # of the expression would be silently dropped.
            leftover = self._peek().value
            raise ComputedExpressionError(
                f"Unexpected token {leftover!r}: expression has trailing content."
            )
        return node

    def _expr(self) -> _ASTNode:
        """expr = term (('+' | '-') term)* - left-associative."""
        node = self._term()
        while self._peek().kind in (_TK_PLUS, _TK_MINUS):
            op = self._advance().value
            node = _BinOp(op, node, self._term())
        return node

    def _term(self) -> _ASTNode:
        """term = unary (('*' | '/') unary)* - left-associative."""
        node = self._unary()
        while self._peek().kind in (_TK_STAR, _TK_SLASH):
            op = self._advance().value
            node = _BinOp(op, node, self._unary())
        return node

    def _unary(self) -> _ASTNode:
        """unary = '-' unary | primary."""
        if self._peek().kind == _TK_MINUS:
            self._advance()
            return _UnaryMinus(self._unary())
        return self._primary()

    def _primary(self) -> _ASTNode:
        """primary = NUMBER | IDENT | AGGREGATE | '(' expr ')'."""
        token = self._peek()

        if token.kind == _TK_NUMBER:
            self._advance()
            return _Num(float(token.value))

        if token.kind == _TK_IDENT:
            self._advance()
            name = token.value
            # ``name(`` is an aggregate call (a function name carries no dot).
            # An unknown name must NOT fall back to "field times a parenthesised
            # group" - that would let any identifier be called.
            if self._peek().kind == _TK_LPAREN and "." not in name:
                func = name.lower()  # the builder title-cases in its own UI
                if func not in AGGREGATE_FUNCS:
                    raise ComputedExpressionError(f"Unknown function {name!r}.")
                self._advance()  # consume '('
                arg = self._expect(_TK_IDENT).value
                self._expect(_TK_RPAREN)
                repeater_key, _, sub = arg.partition(".")
                sub_key = sub or None
                if func != "count" and sub_key is None:
                    raise ComputedExpressionError(
                        f"{func}() needs a column, e.g. {func}(repeater.column)."
                    )
                return _Aggregate(func, repeater_key, sub_key)
            return _Ref(name)

        if token.kind == _TK_LPAREN:
            self._advance()
            node = self._expr()
            self._expect(_TK_RPAREN)
            return node

        if token.kind == _TK_EOF:
            raise ComputedExpressionError(
                "Unexpected end of expression; expected a number, field "
                "reference, or '('."
            )

        raise ComputedExpressionError(
            f"Unexpected token {token.value!r} in expression."
        )


# ---- ref collector ----


def _collect_refs(node: _ASTNode) -> Tuple[FrozenSet[str], Tuple[AggregateRef, ...]]:
    """(scalar field-ref keys, aggregate refs) for an AST.

    The two are separate because the publish gate holds them to different
    rules: a scalar ref must be an earlier NUMERIC field, an aggregate's key
    must be an earlier REPEATER or table.
    """
    refs: set[str] = set()
    aggregates: List[AggregateRef] = []

    def _walk(current: object) -> None:
        if isinstance(current, _Ref):
            refs.add(current.key)
        elif isinstance(current, _Aggregate):
            aggregates.append(
                AggregateRef(current.func, current.repeater_key, current.sub_key)
            )
        elif isinstance(current, _BinOp):
            _walk(current.left)
            _walk(current.right)
        elif isinstance(current, _UnaryMinus):
            _walk(current.operand)
        # _Num references nothing

    _walk(node)
    return frozenset(refs), tuple(aggregates)


# ---- public parse API ----


def parse_expression(expr: str) -> ParsedExpression:
    """Parse *expr*, raising ``ComputedExpressionError`` on anything illegal.

    Called from the publish gate with whatever JSON put in
    ``computed.expression``, which may not be a string at all.
    """
    if not isinstance(expr, str) or not expr.strip():
        raise ComputedExpressionError("Expression must be a non-empty string.")

    # Length first, so a megabyte of garbage never reaches the regex.
    if len(expr) > MAX_EXPR_LEN:
        raise ComputedExpressionError(
            f"Expression length {len(expr)} exceeds the "
            f"{MAX_EXPR_LEN}-character limit."
        )

    source = expr.strip()
    tokens = _tokenise(source)
    ast_node = _Parser(tokens).parse()
    refs, aggregates = _collect_refs(ast_node)
    return ParsedExpression(
        source=source, field_refs=refs, aggregates=aggregates, _ast=ast_node
    )


# ---- evaluator ----


def _coerce(value: object) -> Optional[float]:
    """*value* as a float, or ``None``.

    ``bool`` is deliberately NOT numeric here: a yesno answer must never
    silently contribute 1 to a money total.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, OverflowError):
            return None
    return None


def _eval_node(node: _ASTNode, values: Dict[str, object]) -> Optional[float]:
    """Evaluate *node* against *values*. Fail-closed, never raises."""
    if isinstance(node, _Num):
        return node.value

    if isinstance(node, _Ref):
        raw = values.get(node.key)  # missing key reads as None
        if raw is None:
            return None
        return _coerce(raw)

    if isinstance(node, _UnaryMinus):
        inner = _eval_node(node.operand, values)
        return None if inner is None else -inner

    if isinstance(node, _Aggregate):
        rows = values.get(node.repeater_key)
        if not isinstance(rows, list):
            rows = []  # a renamed/absent repeater degrades, never explodes
        if node.func == "count":
            return float(len(rows))
        numbers: List[float] = []
        for row in rows:
            if isinstance(row, dict):
                # A partially-filled column is the normal case: skip the blanks
                # rather than poisoning the whole total.
                coerced = _coerce(row.get(node.sub_key))
                if coerced is not None:
                    numbers.append(coerced)
        if node.func == "sum":
            return float(sum(numbers))  # an empty order legitimately totals 0
        if not numbers:
            return None  # avg/min/max over nothing has no value, and is not 0
        if node.func == "avg":
            return sum(numbers) / len(numbers)
        if node.func == "min":
            return min(numbers)
        if node.func == "max":
            return max(numbers)
        return None

    if isinstance(node, _BinOp):
        left = _eval_node(node.left, values)
        if left is None:
            return None
        right = _eval_node(node.right, values)
        if right is None:
            return None

        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            if right == 0.0:
                return None  # division by zero fails closed, never raises
            return left / right

    return None  # unreachable, keeps the type-checker happy


def evaluate(
    expr: Union[ParsedExpression, str],
    values: Dict[str, object],
) -> Optional[float]:
    """Evaluate *expr* against a ``{field key: value}`` map.

    ``expr`` may be a :class:`ParsedExpression` (the hot path: recomputing a
    table column would otherwise re-parse the same string once per row) or a
    raw string.

    ``None`` is the ONLY failure mode: this runs inside the submit request, so a
    raise would be a 500 on a valid submission and a guessed 0 would silently
    store a wrong total.
    """
    try:
        if isinstance(expr, str):
            parsed = parse_expression(expr)
        elif isinstance(expr, ParsedExpression):
            parsed = expr
        else:
            return None  # a caller passing a dict/int fails closed
        return _eval_node(parsed._ast, values)  # type: ignore[arg-type]
    except ComputedExpressionError:
        return None
    except Exception:  # noqa: BLE001 - belt and braces, never raise
        return None


# ---- convenience: refs straight from a raw string ----


def field_refs(expr: str) -> FrozenSet[str]:
    """The SCALAR field keys in *expr*. Aggregates are :func:`aggregate_refs`."""
    return parse_expression(expr).field_refs


def aggregate_refs(expr: str) -> Tuple[AggregateRef, ...]:
    """The aggregate-over-rows refs in *expr* (``sum(lines.qty)`` etc.)."""
    return parse_expression(expr).aggregates
