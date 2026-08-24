"""Sandboxed Jinja2 rendering for email templates and automation messages."""
from __future__ import annotations

import html as _html
import logging
import re
from typing import Any

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


_html_env = SandboxedEnvironment(
    autoescape=True,
    undefined=_MarkerUndefined,
    keep_trailing_newline=True,
)
_text_env = SandboxedEnvironment(
    autoescape=False,
    undefined=_MarkerUndefined,
    keep_trailing_newline=True,
)


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
        template = env.from_string(_unescape_jinja_tags(source or ""))
        return template.render(**(context or {}))
    except TemplateError as exc:
        logger.warning("Template render error: %s", exc)
        return f"[template-error:{exc.message}]"


def render_html(source: str, context: dict[str, Any]) -> str:
    return _render(_html_env, source, context)


def render_text(source: str, context: dict[str, Any]) -> str:
    return _render(_text_env, source, context)


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
