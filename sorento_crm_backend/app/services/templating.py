"""Sandboxed Jinja2 rendering for email templates and automation messages."""
from __future__ import annotations

import html as _html
import logging
import operator
import re
import time
from contextvars import ContextVar
from typing import Any, Optional

from jinja2 import Undefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment

logger = logging.getLogger(__name__)


class _MarkerUndefined(Undefined):
    """Render undefined references inline as ``[unknown:<name>]`` instead of raising.

    Attribute / item access on the marker returns another marker so deep
    expressions like ``{{ missing.field }}`` resolve to the marker rather than
    aborting the whole template render.
    """

    def _hint(self) -> str:
        name = getattr(self, "_undefined_name", None) or "?"
        return f"[unknown:{name}]"

    def __str__(self) -> str:
        return self._hint()

    def __html__(self) -> str:
        return self._hint()

    def __getattr__(self, name: str) -> "Undefined":
        if name.startswith("_"):
            raise AttributeError(name)
        return _MarkerUndefined(name=name)

    def __getitem__(self, key: object) -> "Undefined":
        return _MarkerUndefined(name=str(key))

    def __iter__(self):  # support for {% for x in missing %}
        return iter(())

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _MarkerUndefined)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return id(self)


class TemplateBudgetExceeded(Exception):
    """A template tried to spend more time, loop steps or memory than any real mail needs."""


# Render budget (#1349 security review B2/S1). Admin-authored Jinja now renders on public
# paths (password reset, onboarding submit) and in the editor's live preview, and the stock
# sandbox blocks attribute escapes but not work: nested `range(100000)` loops or
# `'a' * 2000000000` stall a worker. These caps are far above anything a mail uses.
RENDER_MAX_RANGE = 1000
RENDER_MAX_SECONDS = 2.0
RENDER_MAX_OUTPUT_CHARS = 1_000_000
RENDER_MAX_SEQUENCE = 100_000

_deadline: ContextVar[Optional[float]] = ContextVar("templating_deadline", default=None)


def _check_deadline() -> None:
    deadline = _deadline.get()
    if deadline is not None and time.monotonic() > deadline:
        raise TemplateBudgetExceeded("template render took too long")


def _budget_range(*args: int):
    rng = range(*args)
    if len(rng) > RENDER_MAX_RANGE:
        raise TemplateBudgetExceeded(f"range larger than {RENDER_MAX_RANGE}")

    def _gen():
        for i in rng:
            _check_deadline()
            yield i

    return _gen()


class _BudgetSandbox(SandboxedEnvironment):
    """The stock sandbox plus a work budget: a capped, deadline-checked `range`, and `*` /
    `**` refused when the result would be huge."""

    intercepted_binops = frozenset(["*", "**"])

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.globals["range"] = _budget_range

    def call_binop(self, context: Any, op: str, left: Any, right: Any) -> Any:
        _check_deadline()
        if op == "**":
            if isinstance(right, (int, float)) and abs(right) > 64:
                raise TemplateBudgetExceeded("exponent too large")
            return operator.pow(left, right)
        # "*": repeating a sequence is where memory goes.
        for seq, n in ((left, right), (right, left)):
            if isinstance(seq, (str, bytes, list, tuple)) and isinstance(n, int):
                if len(seq) * max(n, 0) > RENDER_MAX_SEQUENCE:
                    raise TemplateBudgetExceeded("repeated sequence too large")
        return operator.mul(left, right)


_html_env = _BudgetSandbox(
    autoescape=True,
    undefined=_MarkerUndefined,
    keep_trailing_newline=True,
)
_text_env = _BudgetSandbox(
    autoescape=False,
    undefined=_MarkerUndefined,
    keep_trailing_newline=True,
)


class render_budget:
    """Share one deadline across several renders (one email = many block fields). An
    enclosing budget is never extended by an inner one."""

    def __init__(self, seconds: float = RENDER_MAX_SECONDS) -> None:
        self.seconds = seconds
        self._token = None

    def __enter__(self) -> "render_budget":
        new = time.monotonic() + self.seconds
        current = _deadline.get()
        self._token = _deadline.set(min(current, new) if current is not None else new)
        return self

    def __exit__(self, *exc: Any) -> None:
        _deadline.reset(self._token)


def _render_budgeted(env: SandboxedEnvironment, source: str, context: dict[str, Any]) -> str:
    template = env.from_string(_unescape_jinja_tags(source or ""))
    with render_budget():
        out: list[str] = []
        size = 0
        for chunk in template.generate(**(context or {})):
            _check_deadline()
            size += len(chunk)
            if size > RENDER_MAX_OUTPUT_CHARS:
                raise TemplateBudgetExceeded("template output too large")
            out.append(chunk)
        return "".join(out)


# Matches Jinja statement/expression blocks so we can repair their contents.
_JINJA_TAG_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)


def _unescape_jinja_tags(source: str) -> str:
    """Un-escape HTML entities *inside* Jinja ``{% %}`` / ``{{ }}`` blocks.

    Rich-text/HTML email editors entity-escape control operators they don't
    understand, so an authored ``{% if x > 1 %}`` is persisted as
    ``{% if x &gt; 1 %}``. Jinja's lexer then aborts on the ``&`` with
    ``unexpected char '&'`` and the whole template renders as
    ``[template-error:...]``. Entities never carry meaning *inside* a Jinja tag
    (logic uses ``and``/``or``/``>``/``"``, never ``&amp;``), so decoding within
    the delimiters is safe and leaves output text - where ``&amp;`` is real - 
    untouched.
    """
    if not source or "&" not in source:
        return source
    return _JINJA_TAG_RE.sub(lambda m: _html.unescape(m.group(0)), source)


def _render(env: SandboxedEnvironment, source: str, context: dict[str, Any]) -> str:
    try:
        return _render_budgeted(env, source, context)
    except TemplateError as exc:
        logger.warning("Template render error: %s", exc)
        return f"[template-error:{exc.message}]"
    except TemplateBudgetExceeded as exc:
        logger.warning("Template render budget exceeded: %s", exc)
        return f"[template-error:{exc}]"


def render_html(source: str, context: dict[str, Any]) -> str:
    return _render(_html_env, source, context)


def render_text(source: str, context: dict[str, Any]) -> str:
    return _render(_text_env, source, context)


def _render_strict(env: SandboxedEnvironment, source: str, context: dict[str, Any]) -> str:
    return _render_budgeted(env, source, context)


def render_html_strict(source: str, context: dict[str, Any]) -> str:
    """Like `render_html`, but a template error RAISES instead of rendering
    ``[template-error:...]`` - the email layout (email_layout.py) catches it and sends
    its safe fallback, so the marker can never reach a recipient."""
    return _render_strict(_html_env, source, context)


def render_text_strict(source: str, context: dict[str, Any]) -> str:
    return _render_strict(_text_env, source, context)


_MARKDOWN_INLINE_LINK_RE = None


def html_to_text(html: str) -> str:
    """Best-effort plain-text fallback. Uses html2text if installed; otherwise strips tags.

    Post-processes html2text output to flatten markdown inline links
    `[label](url)` into `label: url`. Naive auto-linkers in plain-text viewers
    (e.g. Respond.io inbox) capture the trailing `)` as part of the URL,
    producing dead links - the bracketed form is safer and renders cleanly in
    every viewer.
    """
    if not html:
        return ""
    import re

    global _MARKDOWN_INLINE_LINK_RE
    if _MARKDOWN_INLINE_LINK_RE is None:
        _MARKDOWN_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")

    try:
        import html2text  # type: ignore

        h = html2text.HTML2Text()
        h.body_width = 0
        h.ignore_images = True
        h.ignore_emphasis = False
        text = h.handle(html).strip()
    except Exception:
        text = re.sub(r"<[^>]+>", "", html).strip()

    return _MARKDOWN_INLINE_LINK_RE.sub(r"\1: \2", text)
