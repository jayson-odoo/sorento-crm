"""Allow-list sanitiser for the rich text stored on price tag fields.

`product_combos.description` and `products.price_tag_description` hold either legacy plain
text or the HTML the shared rich text editor emits. Every write path runs the value through
`sanitise_tag_html`, so nothing but the allow-listed elements and colour / alignment styles
is ever stored; every non-tag reader goes through `plain_text`.

Built on the standard library's `html.parser` (no new dependency). A value is "rich" only when
it starts with an allowed block tag; anything else is plain text, which is kept as typed apart
from tags (plain "text mode", captain ruling 5 Nov 2026). Contract:
documentation/plans/dealer-kit/pricetag-combo-format-contract.md.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import List, Optional

ALLOWED_TAGS = {
    "p", "br", "strong", "em", "s", "u", "code", "h1", "h2", "h3",
    "ul", "ol", "li", "blockquote", "a", "span", "mark",
}
BLOCK_TAGS = {"p", "h1", "h2", "h3", "ul", "ol", "blockquote"}

#: Dropped together with everything inside them.
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed"}
_COLOUR_TAGS = {"span", "mark"}
_ALIGN_TAGS = {"p", "h1", "h2", "h3", "li"}
_ALIGN_VALUES = {"left", "center", "right"}
_COLOUR_PROPS = {"color", "background-color"}
_COLOUR_RE = re.compile(
    r"^#[0-9a-fA-F]{3}$|^#[0-9a-fA-F]{6}$|^rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)$"
)
_RICH_RE = re.compile(r"^\s*<(?:p|h1|h2|h3|ul|ol|blockquote)(?=[\s>])", re.IGNORECASE)


def is_rich(value: Optional[str]) -> bool:
    return bool(value) and _RICH_RE.match(value) is not None


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _style_for(tag: str, raw: Optional[str]) -> str:
    """The kept declarations of a style attribute, re-emitted lower-case, or ''."""
    if not raw:
        return ""
    kept: List[str] = []
    for declaration in raw.split(";"):
        prop, sep, value = declaration.partition(":")
        if not sep:
            continue
        prop = prop.strip().lower()
        value = value.strip()
        if prop in _COLOUR_PROPS and tag in _COLOUR_TAGS and _COLOUR_RE.match(value):
            kept.append(f"{prop}: {value.lower()}")
        elif prop == "text-align" and tag in _ALIGN_TAGS and value.lower() in _ALIGN_VALUES:
            kept.append(f"text-align: {value.lower()}")
    return "; ".join(kept)


class _DropTracker(HTMLParser):
    """Shared handling of the drop-with-content elements and ignored markup."""

    def __init__(self, *, convert_charrefs: bool) -> None:
        super().__init__(convert_charrefs=convert_charrefs)
        self._dropping = 0

    def _enter_drop(self, tag: str) -> bool:
        if tag in _DROP_WITH_CONTENT:
            self._dropping += 1
            return True
        return False

    def _leave_drop(self, tag: str) -> bool:
        if tag in _DROP_WITH_CONTENT:
            self._dropping = max(0, self._dropping - 1)
            return True
        return False

    def handle_comment(self, data):  # noqa: D401
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass


class _RichSanitiser(_DropTracker):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.text_seen = False
        self._stack: List[str] = []

    def handle_starttag(self, tag, attrs):
        if self._enter_drop(tag) or self._dropping:
            return
        if tag not in ALLOWED_TAGS:
            return
        style = _style_for(tag, dict(attrs).get("style"))
        attr = f' style="{style}"' if style else ""
        if tag == "br":
            self.out.append("<br>")
            return
        self.out.append(f"<{tag}{attr}>")
        self._stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        # `<p/>` style self-closing: treat as a start followed by an end.
        self.handle_starttag(tag, attrs)
        if tag != "br":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self._leave_drop(tag) or self._dropping:
            return
        if tag not in self._stack:
            return
        while self._stack:
            top = self._stack.pop()
            self.out.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data):
        if self._dropping:
            return
        if not self._stack and not data.strip():
            return
        if data.strip():
            self.text_seen = True
        self.out.append(_escape(data))

    def result(self) -> str:
        while self._stack:
            self.out.append(f"</{self._stack.pop()}>")
        return "".join(self.out)


class _TextModeSanitiser(_DropTracker):
    """Plain input containing "<": every tag goes, the text stays exactly as typed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: List[str] = []

    def handle_starttag(self, tag, attrs):
        self._enter_drop(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        self._leave_drop(tag)

    def handle_data(self, data):
        if not self._dropping:
            self.out.append(data)

    def handle_entityref(self, name):
        if not self._dropping:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self._dropping:
            self.out.append(f"&#{name};")


def sanitise_tag_html(value: Optional[str]) -> Optional[str]:
    if value is None or not value.strip():
        return None
    if is_rich(value):
        parser = _RichSanitiser()
        parser.feed(value)
        parser.close()
        out = parser.result()
        return out if parser.text_seen else None
    if "<" not in value:
        return value
    parser = _TextModeSanitiser()
    parser.feed(value)
    parser.close()
    out = "".join(parser.out)
    return out if out.strip() else None


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: List[str] = []
        self.buf = ""
        self._lists: List[List] = []  # [kind, counter]
        self._dropping = 0

    def _flush(self, *, always: bool = False) -> None:
        if always or self.buf:
            self.lines.append(self.buf)
        self.buf = ""

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_WITH_CONTENT:
            self._dropping += 1
            return
        if self._dropping:
            return
        if tag == "br":
            self.buf += "\n"
        elif tag in ("ul", "ol"):
            self._flush()
            self._lists.append([tag, 0])
        elif tag == "li":
            self._flush()
            if not self._lists:
                self._lists.append(["ul", 0])
            current = self._lists[-1]
            current[1] += 1
            marker = "• " if current[0] == "ul" else f"{current[1]}. "
            self.buf = "  " * (len(self._lists) - 1) + marker
        elif tag in ("p", "h1", "h2", "h3", "blockquote"):
            self._flush()

    def handle_endtag(self, tag):
        if tag in _DROP_WITH_CONTENT:
            self._dropping = max(0, self._dropping - 1)
            return
        if self._dropping:
            return
        if tag in ("p", "h1", "h2", "h3", "blockquote"):
            self._flush(always=True)
        elif tag == "li":
            self._flush()
        elif tag in ("ul", "ol"):
            self._flush()
            if self._lists:
                self._lists.pop()

    def handle_data(self, data):
        if self._dropping:
            return
        if not self.buf and not data.strip():
            return
        self.buf += data

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass


def plain_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not is_rich(value):
        return value
    parser = _PlainText()
    parser.feed(value)
    parser.close()
    parser._flush()
    return "\n".join(parser.lines).strip("\n")
