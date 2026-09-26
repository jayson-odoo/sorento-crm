"""S3 parser prompt token ceiling - tester-first RED, from the UAC and the lane A
contract (section 6.3 "How the budget is enforced").

Covers AC-MEM061.

**Genuinely red today, not an import error**: `SEMANTIC_PARSER_PROMPT` plus its growth
addenda plus the policy-blocks seed already renders WAY over the 22,100 est. token
ceiling this file enforces (measured while writing this file: about 36-37k est. tokens,
against the plan's own "22.8k measured, 21.2k static + 0.9k policy" - the addenda this
repo has accumulated since are already the overshoot #1275 exists to find). This is the
real acceptance gate AC-MEM061 asks for: it is red until S3's cuts (contract section 6.4)
land, then green, then a REGRESSION on this file is a real, load-bearing failure - not a
missing-module placeholder.

**Ambiguity flagged to the captain**: the token estimator here is a LOCAL, self-contained
`ceil(utf8_bytes / 3)` (the contract's own formula, section 6.2), not imported from
`app.services.chatbot.turn.context` - that module is S3's own deliverable and does not
exist yet, and coupling THIS file's collection to its existence would turn a real,
meaningful "the prompt is over budget" assertion into an unrelated `ImportError`. Once
`context.est_tokens` exists, the coder is free to import it here instead (same formula,
same answer) - flagged as a choice, not a defect.

Pure Python: no database, no LLM. `render_prompt_blocks`/`prompt_blocks_hash` (which DO
need a database) are not used - "the policy blocks seed" is read from the already-
committed `tests/chatbot/fixtures/prompt_blocks_seed.txt`, the same fixture
`test_rearch_s4_prompt_blocks.py` renders and compares as its own golden file.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.services.chatbot_parser_prompt import (
    GROWTH_R1_ADDENDUM,
    LAST_COST_ADDENDUM,
    LOW_STOCK_ADDENDUM,
    SALES_REPORT_ADDENDUM,
    SEMANTIC_PARSER_PROMPT,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
POLICY_BLOCKS_SEED_FILE = FIXTURES_DIR / "prompt_blocks_seed.txt"
CEILING = 22_100


def _est_tokens(text: str) -> int:
    """`ceil(utf8_bytes / 3)` - contract section 6.2, verbatim. See module docstring
    for why this is a local copy rather than an import from `turn/context.py`."""
    return math.ceil(len(text.encode("utf-8")) / 3)


def _rendered_production_prompt(*, current_date: str = "Thursday, 25 September 2026") -> str:
    """The way `parser.resolve_config` builds the live call's system prompt: the
    registry's fallback body (here, the same fallback constant the registry falls back
    to, `_chatbot_semantic_parser_fallback()` -> `SEMANTIC_PARSER_PROMPT`) with its
    `{{current_date}}` variable substituted, PLUS every addendum this repo has already
    stacked onto it, PLUS the policy blocks (the domain/entity-kind paragraphs a real
    published version wraps in - the committed seed fixture stands in for a live
    `chatbot_domains` render, exactly as `test_rearch_s4_prompt_blocks.py`'s own golden
    file does)."""
    body = SEMANTIC_PARSER_PROMPT + GROWTH_R1_ADDENDUM + LAST_COST_ADDENDUM + LOW_STOCK_ADDENDUM + SALES_REPORT_ADDENDUM
    body = body.replace("{{current_date}}", current_date)
    policy_blocks = POLICY_BLOCKS_SEED_FILE.read_text(encoding="utf-8")
    return body + "\n" + policy_blocks


class TestPromptUnderCeiling:
    def test_production_prompt_is_at_most_22100_est_tokens(self) -> None:
        rendered = _rendered_production_prompt()
        tokens = _est_tokens(rendered)
        assert tokens <= CEILING, (
            f"the production parser prompt is {tokens} est. tokens, over the "
            f"{CEILING} ceiling (contract section 6.3 / AC-MEM061) - the S3 cuts of "
            f"section 6.4 (the dead `previous_conversation_state` description, the n8n "
            f"JS literal, and further cuts 8.2 shows are safe) have not landed yet"
        )

    def test_kill_test_appending_3000_chars_is_reported_over(self) -> None:
        """The SAME check function, fed a prompt padded with 3,000 extra chars, must
        report it over - proving the check function itself catches an overshoot rather
        than always passing (or always failing)."""
        rendered = _rendered_production_prompt() + ("z" * 3000)
        tokens = _est_tokens(rendered)
        assert tokens > CEILING, (
            f"padding by 3000 chars must push the estimate over {CEILING}, got {tokens} "
            f"- the check function is not sensitive to prompt growth"
        )


class TestDateAtTheEnd:
    """AC-MEM071: `CURRENT DATE: {{current_date}}` is the LAST section, so the first
    20,000 chars are byte-identical across two different dates.

    Genuinely red today: grepping the live constant shows the `CURRENT DATE` section
    sitting near the START of the body (right after the opening paragraph), not the
    end - swapping in two dates of DIFFERENT lengths shifts every byte after it, so the
    first 20,000 chars differ today. This is the position AC-MEM071 asks S3 to move.
    """

    def test_current_date_section_is_the_last_section_of_the_body(self) -> None:
        marker = "CURRENT DATE"
        last_marker_at = SEMANTIC_PARSER_PROMPT.rfind(marker)
        assert last_marker_at != -1, "CURRENT DATE section not found at all"
        tail_after = SEMANTIC_PARSER_PROMPT[last_marker_at:]
        # "Last section" - nothing of substance after the current-date sentence itself
        # (allow trailing whitespace only).
        assert len(tail_after) < 400, (
            f"CURRENT DATE must be the LAST section of the system prompt; found "
            f"{len(SEMANTIC_PARSER_PROMPT) - last_marker_at} chars after it"
        )

    def test_first_20000_chars_are_byte_identical_across_two_dates(self) -> None:
        short_date = "Mon, 5 May 2025"
        long_date = "Wednesday, 25 November 2026"
        rendered_a = _rendered_production_prompt(current_date=short_date)
        rendered_b = _rendered_production_prompt(current_date=long_date)
        assert rendered_a[:20000] == rendered_b[:20000], (
            "the first 20,000 chars must be byte-identical regardless of the current "
            "date - only true once CURRENT DATE sits at the END of a prompt whose "
            "static prefix is itself at least 20,000 chars"
        )
