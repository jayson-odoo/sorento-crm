"""CHAT-STATE r6 S6: one UserTurn at ingress (AC-S6-1..3).

What the customer sent this turn, read ONCE when the turn starts, for the webhook path and the
direct ingress alike (both arrive as an `Envelope`): their own line, the quoted reply under it,
and the attachment reads. Every reader that used to re-split the latest user message takes it
instead, so the quoted `reply to: ...` block is never read as the customer's own words by one
reader and not by another.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class UserTurn:
    """`own_text`: the first line of the text the turn reads (`engine.build_latest_user_message`,
    or the media intake's rendered read on a media turn). `quoted_text`: everything after that
    first newline (the `reply to: ...` block). `media`: the attachment reads, () when none.
    `typed_line`: the first line the customer typed in the message itself, "" when it carried
    no text (an attachment alone), which is what the fallback's language reads."""

    own_text: str
    quoted_text: str = ""
    media: tuple[str, ...] = ()
    typed_line: str = ""

    @property
    def own_line(self) -> str:
        """The customer's own line as the text readers match it: `own_text` without its
        surrounding blanks, up to its first line break."""
        lines = self.own_text.strip().splitlines()
        return lines[0] if lines else ""


def _split(text: str) -> tuple[str, str]:
    own, _sep, rest = text.partition("\n")
    return own, rest


def from_envelope(envelope: Any, session_block: Any = None) -> UserTurn:
    """The ONE builder: the turn's UserTurn from its envelope, off the same text
    `engine.build_latest_user_message` builds."""
    from app.services.chatbot import jsc
    from app.services.chatbot.engine import _inner_message, build_latest_user_message

    own, quoted = _split(build_latest_user_message(envelope, session_block))
    inner = _inner_message(envelope)
    text = jsc.get(inner, "text")
    typed = jsc.js_string(text) if jsc.truthy(text) else ""
    description = jsc.get(jsc.get(inner, "attachment"), "description")
    media = (jsc.js_string(description),) if jsc.truthy(description) else ()
    return UserTurn(own_text=own, quoted_text=quoted, media=media, typed_line=_split(typed)[0])


def with_media_read(turn: UserTurn, rendered_text: str) -> UserTurn:
    """A media turn: the intake's rendered read is the text the turn reads (AC-1807), and one of
    its attachment reads; what the customer typed stays as it was."""
    own, quoted = _split(rendered_text)
    media = turn.media if not rendered_text or rendered_text in turn.media else (*turn.media, rendered_text)
    return replace(turn, own_text=own, quoted_text=quoted, media=media)


def own_line_of(message: Any) -> str | None:
    """The customer's own line for a text reader: the turn's UserTurn, or (a direct caller
    handing a bare message string) the same line read off that string. None for anything else."""
    if isinstance(message, UserTurn):
        return message.own_line
    if isinstance(message, str):
        own, _quoted = _split(message)
        return UserTurn(own_text=own).own_line
    return None
