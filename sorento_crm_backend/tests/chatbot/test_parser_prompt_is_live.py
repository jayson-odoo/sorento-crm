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
A third, content-only edit (migration `487_chatbot_warehouse_cue`) sits inside the
requested-attributes block and is deliberately excluded from that reproducibility check -
see `test_the_constant_is_reproducible_from_the_live_file`'s own docstring.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from app.services.chatbot_parser_prompt import (
    GROWTH_R1_ADDENDUM,
    LIVE_SYSTEM_MESSAGE_SHA256,
    SEMANTIC_PARSER_PROMPT,
)

# The one n8n expression the registry replaces. Everything else is byte-identical.
DATE_EXPR = "{{ $now.toUTC(8*60).format('cccc, dd MMMM yyyy') }}"

LIVE_CHARS = 46942  # the fetched file, leading `=` included
# 46906 after dropping `=` and swapping the date expression; +63 chars from migration
# 487_chatbot_warehouse_cue (owner report, 7 Sep 2026), which gave `warehouse_arrival_date`
# its own warehouse/CJK/Malay cue and narrowed `estimated_arrival_date` so it no longer owns
# the bare word "arrival"; +513 chars from a follow-up to the same migration (7 Sep 2026),
# which added a WORKED EXAMPLES paragraph because the cue alone did not resolve zh/ms
# phrasings against the FULL TIMELINE sentinel; +262 chars from a review pass on the same
# migration (F1, 7 Sep 2026), which rewrote that paragraph so a bare container/shipment ask
# ("incoming TIIU6323920") reads as the full timeline and an explicit ETA ask about a
# container ("ETA of X") still resolves to `estimated_arrival_date` alone. All four edits
# are intentional content, not drift from this guard.
#
# Growth r1 (migration 490) adds a fifth: `GROWTH_R1_ADDENDUM`, appended WHOLE at the end
# rather than woven in, so it is subtracted rather than sliced - see
# `_without_growth_r1_addendum`. CONSTANT_CHARS is the body BEFORE that append, which is
# what keeps this number a guard against drift in the live-derived text rather than a
# number that moves every time growth r1's vocabulary is edited.
# +367 chars (8 Sep 2026, owner turn 2d903c96 "delivery to hanlim"): one sentence appended to
# the request_for_help definition inside the MESSAGE TYPE block - a request_for_help is
# ONLY a request for a human; a customer or product beside a delivery word is an order ask.
# Intentional content, woven in where the definition lives, not drift.
# +197 chars (item 8, 8 Sep 2026): one line in REQUESTED ATTRIBUTES - the customer's
# attribute phrase is emitted whole, and a base property is a requested attribute too.
# +262 chars (D6, 8 Sep 2026): the requested_attributes line scoped to that key, one
# attachment_type canonical_code sentence in ATTACHMENT TYPE EXTRACTION, and "image" removed
# from the canonical enum (it is "photo"). Intentional content.
# +123 chars (D10, 8 Sep 2026, turn 69d9900e): one sentence in the incoming domain
# description, in both bodies - the code in an incoming ask is the product, and only a
# 4-letter + 7-digit token (a real container number) is a container. Intentional content.
# +99 chars (D12, 8 Sep 2026, turn 8f4a8526): one sentence in REQUESTED ATTRIBUTES, both
# bodies - "details" / "product details" / "info" / "tell me about X" name no property.
# +204 chars (E2, 8 Sep 2026, turn b377b18e "Catalog Sorento"): one sentence in the
# resource_attachment domain description, both bodies - a document-class word plus a
# brand or company name is get_resource_attachment with the attachment entity, never
# promotion.
CONSTANT_CHARS = 48996


def _without_growth_r1_addendum(text: str) -> str:
    """The body as it was before growth r1 appended its vocabulary block (migration 490).

    An APPENDED block, so it comes off with a `removesuffix` rather than the index slice the
    warehouse-arrival edit needs - that one sits INSIDE the requested-attributes section. The
    assertion that it really is a suffix lives in
    `test_parser_growth_r1_reachability.py::test_the_addendum_is_appended_to_both_bodies`.
    """
    assert text.endswith(GROWTH_R1_ADDENDUM), (
        "GROWTH_R1_ADDENDUM is no longer the tail of the prompt. It is appended rather than "
        "woven in on purpose (the FULL body has to stay a mechanical derivation of the live "
        "n8n message); moving it into the body means this file needs a second slice-out, not "
        "a bigger character count."
    )
    return text[: -len(GROWTH_R1_ADDENDUM)]


def test_the_constant_has_the_live_size_not_the_export_size() -> None:
    """The export is 49,318 characters. Anything near that is the wrong body."""
    body = _without_growth_r1_addendum(SEMANTIC_PARSER_PROMPT)
    assert len(body) == CONSTANT_CHARS, (
        f"parser prompt is {len(body)} chars before the growth r1 addendum, expected "
        f"{CONSTANT_CHARS}. "
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
    """The prompt and `parser.PARSE_OUTPUT_JSON_SCHEMA` must agree on the wire shape.

    Minus the three keys prompt v3 introduced (growth r1 slice B2). The schema is ONE
    wire shape shared by every published version, so it is a superset of what the LIVE
    v1 body asks for and equal to what the newest one asks for - the equality half is
    `test_parser.py::TestStrictSchema::test_it_declares_the_keys_the_NEWEST_prompt_declares`.
    Naming the three here rather than loosening the assertion is what keeps this guard:
    a FOURTH key appearing in the schema and not in this constant still fails.
    """
    from app.services.chatbot.head.output_exchange import V3_EMISSION_KEYS
    from app.services.chatbot.head.parser import DECLARED_KEYS

    expected = DECLARED_KEYS - set(V3_EMISSION_KEYS)
    missing = sorted(k for k in expected if f'"{k}"' not in SEMANTIC_PARSER_PROMPT)
    assert not missing, f"prompt does not declare: {', '.join(missing)}"
    for key in V3_EMISSION_KEYS:
        assert f'"{key}"' not in SEMANTIC_PARSER_PROMPT, (
            f"{key} belongs to prompt v3; the live v1 body must not mention it"
        )


def _live_file() -> Path | None:
    raw = os.environ.get("CHATBOT_LIVE_SYSTEM_MESSAGE")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_file() else None


def _requested_attributes_block(text: str) -> tuple[int, int]:
    """The span from the `estimated_arrival_date` vocabulary line through the end of the
    WORKED EXAMPLES paragraph.

    F5 (review, 7 Sep 2026): migration `487_chatbot_warehouse_cue` put NEW prompt content
    inside this span - it is not a transform of the live text, so it is not byte-for-byte
    reproducible from it. `test_the_constant_is_reproducible_from_the_live_file` slices this
    one block out of both sides before comparing; everything outside it must still match.
    """
    start = text.find('"estimated_arrival_date"')
    assert start != -1, '"estimated_arrival_date" not found in prompt'
    worked = text.find("WORKED EXAMPLES", start)
    assert worked != -1, "WORKED EXAMPLES paragraph not found after estimated_arrival_date"
    end = text.find("FULL TIMELINE", worked)
    assert end != -1, "FULL TIMELINE paragraph not found after WORKED EXAMPLES"
    return start, end


def test_the_constant_is_reproducible_from_the_live_file() -> None:
    """The derivation itself, when the fetched file is available.

    Opt-in via ``CHATBOT_LIVE_SYSTEM_MESSAGE`` because the file is not committed. The
    tests above hold everywhere; this one proves the two MECHANICAL edits and nothing
    more, and it is what to run after any re-fetch.

    F5: the constant also carries a THIRD, content-only edit inside the REQUESTED
    ATTRIBUTES block (the warehouse-arrival vocabulary + its WORKED EXAMPLES paragraph),
    which by construction cannot come out of the live file by a mechanical transform - it
    is new text the owner asked for, published as its own prompt version rather than
    promoted straight to production. So this test derives the constant from the live file
    the same two-edit way as before, then asserts it against `SEMANTIC_PARSER_PROMPT` with
    that one block cut out of BOTH sides, rather than expecting the two to be byte-equal
    end to end.
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
    derived = raw[1:].replace(DATE_EXPR, "{{current_date}}")

    body = _without_growth_r1_addendum(SEMANTIC_PARSER_PROMPT)
    d_start, d_end = _requested_attributes_block(derived)
    c_start, c_end = _requested_attributes_block(body)
    assert derived[:d_start] == body[:c_start], (
        "everything BEFORE the requested-attributes block must still be a pure mechanical "
        "derivation of the live file"
    )
    assert derived[d_end:] == body[c_end:], (
        "everything AFTER the requested-attributes block, and before the growth r1 addendum, "
        "must still be a pure mechanical derivation of the live file"
    )
