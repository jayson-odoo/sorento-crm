"""S3 parser prompt token ceiling - tester-first RED, from the UAC and the lane A
contract (section 6.3 "How the budget is enforced").

Covers AC-MEM061.

**Ceiling baseline, coordinator ruling 26 Sep 2026**: `CEILING = 37_153`, not the plan's
own 22,100. The plan's number is a `chars / 4` estimate over a DIFFERENT rendering (the
live n8n text alone, before this repo's own growth addenda and before this file's own
`bytes / 3` formula); 37,153 is what THIS file's own `_rendered_production_prompt()`
measures at commit `232182ae` (`SEMANTIC_PARSER_PROMPT` + every growth addendum + the
policy-blocks seed, `est_tokens = ceil(utf8_bytes / 3)`). The rule that matters is
unchanged - **the static prompt may not grow** - so the ceiling is pinned to today's
measured value rather than to the plan's figure for a different measurement. Any
S3 cut lowers the real number without needing a matching CEILING edit; a genuine new
addendum that must land raises CEILING in the same commit, with the new measured value
named the same way this one is.

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
# Measured baseline (coordinator ruling, 26 Sep 2026), not the plan's 22,100 - see the
# module docstring for why the two numbers measure different things.
CEILING = 37_153


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
    def test_production_prompt_is_at_most_the_measured_ceiling(self) -> None:
        rendered = _rendered_production_prompt()
        tokens = _est_tokens(rendered)
        assert tokens <= CEILING, (
            f"the production parser prompt is {tokens} est. tokens, over the "
            f"{CEILING} ceiling (contract section 6.3 / AC-MEM061, baseline pinned by "
            f"coordinator ruling 26 Sep 2026) - the static prompt may not grow"
        )

    def test_kill_test_appending_extra_text_is_reported_over(self) -> None:
        """The SAME check function, fed a prompt padded with extra chars, must report
        it over - proving the check function itself catches an overshoot rather than
        always passing (or always failing). 3,000 chars is about +1,000 est. tokens,
        comfortably over the measured baseline whether or not it sits exactly at
        CEILING."""
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
