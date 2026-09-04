"""The parser prompt fallback IS the live n8n system message, not the export (AC-104).

S1 originally vendored the working-tree EXPORT of `sub-semantic-parser`. That export is
flagged `locally_edited` in its own MANIFEST and carries an UNPROMOTED lane change
(B-TEAM-1'), so it is 49,318 characters where the LIVE body is 46,942. A CRM turn must
parse the way a live n8n turn parses, so the live body is the only correct source.

Nothing here reaches n8n. The guard is a sha256 recorded beside the constant plus a set of
properties that only hold for the live text, so a future edit that reintroduces the export
(or quietly rewrites the fallback) fails here rather than in production.

The full live file is not vendored into this repo: it is 46 KB of prompt that already
exists once, as the constant. What IS pinned is its hash and the two mechanical edits that
derive the constant from it, so the derivation is reproducible by anyone holding the file.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from app.services.chatbot_parser_prompt import (
    LIVE_SYSTEM_MESSAGE_SHA256,
    SEMANTIC_PARSER_PROMPT,
)

# The one n8n expression the registry replaces. Everything else is byte-identical.
DATE_EXPR = "{{ $now.toUTC(8*60).format('cccc, dd MMMM yyyy') }}"

LIVE_CHARS = 46942  # the fetched file, leading `=` included
CONSTANT_CHARS = 46906  # after dropping `=` and swapping the date expression


def test_the_constant_has_the_live_size_not_the_export_size() -> None:
    """The export is 49,318 characters. Anything near that is the wrong body."""
    assert len(SEMANTIC_PARSER_PROMPT) == CONSTANT_CHARS, (
        f"parser prompt is {len(SEMANTIC_PARSER_PROMPT)} chars, expected {CONSTANT_CHARS}. "
        "The live body is 46,942 chars before the two mechanical edits; the working-tree "
        "export is 49,318 and carries the unpromoted B-TEAM-1' lane change."
    )


def test_the_constant_never_asks_for_team_source() -> None:
    """`team_source` is B-TEAM-1'. The live message does not mention it, and not one of
    the 488 captured raw emissions carries it."""
    assert "team_source" not in SEMANTIC_PARSER_PROMPT


def test_the_date_expression_became_the_registry_variable() -> None:
    assert SEMANTIC_PARSER_PROMPT.count("{{current_date}}") == 1
    assert DATE_EXPR not in SEMANTIC_PARSER_PROMPT
    assert not SEMANTIC_PARSER_PROMPT.startswith("=")


def test_the_output_block_declares_exactly_the_schema_keys() -> None:
    """The prompt and `parser.PARSE_OUTPUT_JSON_SCHEMA` must agree on the wire shape."""
    from app.services.chatbot.head.parser import DECLARED_KEYS

    missing = sorted(k for k in DECLARED_KEYS if f'"{k}"' not in SEMANTIC_PARSER_PROMPT)
    assert not missing, f"prompt does not declare: {', '.join(missing)}"


def _live_file() -> Path | None:
    raw = os.environ.get("CHATBOT_LIVE_SYSTEM_MESSAGE")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_file() else None


def test_the_constant_is_reproducible_from_the_live_file() -> None:
    """The derivation itself, when the fetched file is available.

    Opt-in via ``CHATBOT_LIVE_SYSTEM_MESSAGE`` because the file is not committed. The
    tests above hold everywhere; this one proves the two edits and nothing more, and it is
    what to run after any re-fetch.
    """
    path = _live_file()
    if path is None:
        pytest.skip(
            "set CHATBOT_LIVE_SYSTEM_MESSAGE to the fetched "
            "sub-semantic-parser.systemMessage.live.txt to verify the derivation"
        )
    raw = path.read_text(encoding="utf-8")
    assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == LIVE_SYSTEM_MESSAGE_SHA256, (
        "the file at CHATBOT_LIVE_SYSTEM_MESSAGE is not the body this constant was taken "
        "from; re-derive the constant rather than editing the hash"
    )
    assert len(raw) == LIVE_CHARS
    assert raw.startswith("=")
    assert raw.count(DATE_EXPR) == 1
    assert raw[1:].replace(DATE_EXPR, "{{current_date}}") == SEMANTIC_PARSER_PROMPT
