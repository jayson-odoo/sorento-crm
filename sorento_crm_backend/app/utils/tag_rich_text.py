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
from typing import Dict, List, Optional

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


#: C0 controls except tab and newline: a NUL breaks the database driver, the rest print as nothing.
_CONTROLS = re.compile("[\x00-\x08\x0b-\x1f]")


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
        #: Open count per tag, so an end tag with no open match is O(1) (no stack scan).
        self._open: Dict[str, int] = {}

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
        self._open[tag] = self._open.get(tag, 0) + 1

    def handle_startendtag(self, tag, attrs):
        # `<p/>` style self-closing: treat as a start followed by an end.
        self.handle_starttag(tag, attrs)
        if tag != "br":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self._leave_drop(tag) or self._dropping:
            return
        if not self._open.get(tag):
            return
        while self._stack:
            top = self._stack.pop()
            self._open[top] -= 1
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


def _rich_pass(value: str) -> Optional[str]:
    parser = _RichSanitiser()
    parser.feed(value)
    parser.close()
    out = parser.result()
    return out if parser.text_seen else None


def _text_pass(value: str) -> str:
    parser = _TextModeSanitiser()
    parser.feed(value)
    parser.close()
    return "".join(parser.out)


def sanitise_tag_html(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = _CONTROLS.sub("", value)
    if not value.strip():
        return None
    if is_rich(value):
        return _rich_pass(value)
    if "<" not in value:
        return value
    # Plain-text mode removes tags, and removing one can leave another behind (`<<b>p>`): repeat
    # until nothing changes; one that will not settle loses its `<` outright, so no tag outside the allow-list is ever stored.
    current = value
    for _ in range(5):
        nxt = _text_pass(current)
        if nxt == current:
            break
        current = nxt
    else:
        current = current.replace("<", "")
    return current if current.strip() else None


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: List[str] = []
        self.buf = ""
        self._lists: List[List] = []  # [kind, counter]
        self._dropping = 0
        #: The marker just written for a list item, while no text has followed it yet.
        self._marker = ""

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
            self._marker = self.buf
        elif tag in ("p", "h1", "h2", "h3", "blockquote"):
            # The editor wraps each list item's text in a <p>: it continues the marker's line
            # ("• bullet one"), it does not start a new one.
            if not (self._marker and self.buf == self._marker):
                self._flush()
            self._marker = ""

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


#: Sanitised rich output carrying no styling at all: bare paragraphs, line breaks and text.
_UNSTYLED_RE = re.compile(r"^(?:<p>|</p>|<br>|[^<])*$")


def sanitise_description(value: Optional[str]) -> Optional[str]:
    """The save rule for a quotation line description (QUOTE-DESC-RICHTEXT).

    Rich input goes through the same allow-list as a price tag (`_rich_pass`). Unlike
    `sanitise_tag_html`, plain text is kept exactly as typed (a bill of quantities says
    "PIPE <DN50"), since every reader of a plain description escapes it. An edit that carries no
    styling at all is stored back as plain lines, so typing in an old plain line does not turn
    it into HTML.
    """
    if value is None:
        return None
    # Leading invisible characters (BOM, zero-width) are dropped, so the server and the browser
    # (whose `\s` differs from Python's) always agree on whether a value is rich.
    value = _CONTROLS.sub("", value).lstrip("\ufeff\u200b\u200c\u200d\u2060\x85")
    if not value.strip():
        return None
    if not is_rich(value):
        return value
    clean = _rich_pass(value)
    if clean is None:
        return None
    if _UNSTYLED_RE.match(clean):
        text = plain_text(clean)
        if text and text.strip() and not is_rich(text):
            return text
        if not text or not text.strip():
            return None
    return clean
