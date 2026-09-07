"""`warehouse_arrival_date` needs its own cue, or `estimated_arrival_date` steals it.

Evidence (local turns 24756873, 60fe40f4, a0ce7626, 202510dc, 851c9c93): "IBWB248什么时候会到
仓库？", "when will IBWB248 arrive at the warehouse" and "bila IBWB248 sampai gudang" ALL parsed
to `requested_attributes: ["estimated_arrival_date"]` instead of the owner's expected
`["warehouse_arrival_date"]` (the backend then expands backwards through every earlier
checkpoint). The cause: the SLIM prompt's vocabulary line for `warehouse_arrival_date` carried
no cue at all, while `estimated_arrival_date` owned the bare word "arrival" in both prompts, so
any "arrival"/"arrive" mention resolved to the port ETA instead of the warehouse checkpoint.

This asserts the fix directly on both prompt constants rather than re-running the parser LLM
(non-deterministic, costs a real call): `warehouse_arrival_date` must carry the warehouse/CJK/
Malay cue, and `estimated_arrival_date` must no longer carry the bare word "arrival" unqualified
by "port" or "no warehouse".
"""
from __future__ import annotations

from app.services.chatbot_parser_prompt import (
    SEMANTIC_PARSER_PROMPT,
    SEMANTIC_PARSER_PROMPT_SLIM,
)


def _line_for(text: str, key: str) -> str:
    """The single vocabulary line naming `key`, isolated by its surrounding newlines/pipes."""
    idx = text.find(f'"{key}"')
    assert idx != -1, f'"{key}" not found in prompt'
    start = text.rfind("\n", 0, idx) + 1
    end = text.find("\n", idx)
    return text[start:end]


def _worked_examples(text: str) -> str:
    """The WORKED EXAMPLES paragraph, isolated between its own heading and FULL TIMELINE."""
    start = text.find("WORKED EXAMPLES")
    assert start != -1, "WORKED EXAMPLES paragraph not found in prompt"
    end = text.find("FULL TIMELINE", start)
    assert end != -1, "FULL TIMELINE paragraph not found after WORKED EXAMPLES"
    return text[start:end]


class TestWarehouseArrivalCue:
    def test_full_prompt_warehouse_line_has_the_new_cue(self) -> None:
        line = _line_for(SEMANTIC_PARSER_PROMPT, "warehouse_arrival_date")
        assert "warehouse" in line.lower()
        assert "到仓库" in line
        assert "sampai gudang" in line

    def test_slim_prompt_warehouse_line_has_the_new_cue(self) -> None:
        line = _line_for(SEMANTIC_PARSER_PROMPT_SLIM, "warehouse_arrival_date")
        assert "warehouse" in line.lower()
        assert "到仓库" in line
        assert "sampai gudang" in line

    def test_full_prompt_estimated_arrival_line_no_longer_owns_bare_arrival(self) -> None:
        line = _line_for(SEMANTIC_PARSER_PROMPT, "estimated_arrival_date")
        assert "ETA, port arrival, \"when does it arrive / come in\" (no warehouse named)" in line

    def test_slim_prompt_estimated_arrival_line_no_longer_owns_bare_arrival(self) -> None:
        line = _line_for(SEMANTIC_PARSER_PROMPT_SLIM, "estimated_arrival_date")
        assert "ETA, port arrival, no warehouse named" in line


class TestWorkedExamplesParagraph:
    """The cue alone did not resolve zh/ms phrasings against the FULL TIMELINE sentinel
    (owner evidence, 7 Sep 2026): a WORKED EXAMPLES paragraph pins the three example
    phrasings the owner tested against, in both prompts."""

    def test_full_prompt_worked_examples_has_all_three_phrases(self) -> None:
        paragraph = _worked_examples(SEMANTIC_PARSER_PROMPT)
        assert "什么时候会到仓库" in paragraph
        assert "sampai gudang" in paragraph
        assert "arrive at the warehouse" in paragraph

    def test_slim_prompt_worked_examples_has_all_three_phrases(self) -> None:
        paragraph = _worked_examples(SEMANTIC_PARSER_PROMPT_SLIM)
        assert "什么时候会到仓库" in paragraph
        assert "sampai gudang" in paragraph
        assert "arrive at the warehouse" in paragraph
