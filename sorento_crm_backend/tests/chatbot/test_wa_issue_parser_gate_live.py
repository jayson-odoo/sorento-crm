"""WA-COMPLAINT-INTAKE round 12: the frozen gate turns, run through the LIVE parser.

Opt-in, never in CI: `CHATBOT_LIVE_LLM=1` (the suite's `live_external` marker). Model
`WA_ISSUE_LIVE_MODEL`, default `gpt-5.4-mini` (the production parser model); key `OPENAI_API_KEY`,
or a placeholder where an egress proxy injects it.

The prompt is `WA_ISSUE_PROMPT_FILE` when set (crew points it at a stored version's exported text),
else the committed candidate `documentation/plans/chatbot/prompt-wa-issue-ideate.txt`, with
`{{current_date}}` and `{{find_filters}}` rendered as `ai_prompt_registry.render` does at run time.
The turns are `tests/chatbot/fixtures/wa_issue_gate_turns.json` (structure pinned offline by
`test_wa_issue_gate_offline.py`). Contract: documentation/plans/chatbot/PROMPT-wa-issue-ideate.md, "Round 12"
and "Round 13" (`entity_raw_contains`: some entity's `raw` contains that text, case-insensitive).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.live_external

TODAY = "Saturday, 14 November 2026"
_PLANS = Path(__file__).resolve().parents[3] / "documentation" / "plans" / "chatbot"
CANDIDATE_PATH = _PLANS / "prompt-wa-issue-ideate.txt"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wa_issue_gate_turns.json"
#: The parser has no staff/dealer slot of its own; the contact reaches it as the profile tier line.
_TIER = {"staff": "office", "dealer": "dealer"}


def _turns() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _system() -> str:
    from app.services import product_find
    from app.services.chatbot_find_prompt import TOKEN

    path = os.environ.get("WA_ISSUE_PROMPT_FILE")
    text = Path(path).read_text(encoding="utf-8") if path else CANDIDATE_PATH.read_text(encoding="utf-8")
    return text.replace(TOKEN, product_find.parser_vocabulary()).replace("{{current_date}}", TODAY)


def _parse(system_text: str, message: str, previous: str, contact: str) -> dict[str, Any]:
    from app.services.chatbot.head import parser

    config = parser.ParserConfig(
        system_prompt=system_text,
        prompt_version=0,
        provider="openai",
        model=os.environ.get("WA_ISSUE_LIVE_MODEL", "gpt-5.4-mini"),
        api_key=os.environ.get("OPENAI_API_KEY") or "sk-proxy-injected",
    )
    block = parser.build_user_block(
        previous_response=previous,
        latest_user_message=message,
        pending_kind=None,
        focus=None,
        recent_exchanges=None,
        profile_block=f"Profile:\ntier: {_TIER[contact]}",
    )
    out = dict(parser.parse(config, block))
    print(
        json.dumps(
            {
                "message": message,
                "contact": contact,
                "message_type": out.get("message_type"),
                "domain_hint": out.get("domain_hint"),
                "intent_hint": out.get("intent_hint"),
                "routing": out.get("routing"),
                "entities": out.get("entities"),
            },
            ensure_ascii=False,
        )
    )
    return out


@pytest.mark.parametrize("turn", _turns(), ids=lambda t: t["id"])
def test_R12_gate_turn_live(turn):
    out = _parse(_system(), turn["message"], turn["previous_response"], turn["contact"])
    expect = turn["expect"]
    if "domain_hint" in expect:
        assert out.get("domain_hint") == expect["domain_hint"], out
    if "domain_hint_not" in expect:
        assert out.get("domain_hint") != expect["domain_hint_not"], out
    if "message_type" in expect:
        assert out.get("message_type") == expect["message_type"], out
    if "message_type_not" in expect:
        assert out.get("message_type") != expect["message_type_not"], out
    if "suggested_team" in expect:
        routing = out.get("routing") if isinstance(out.get("routing"), dict) else {}
        assert routing.get("suggested_team") == expect["suggested_team"], out
    if "entity_raw_contains" in expect:
        needle = str(expect["entity_raw_contains"]).lower()
        entities = out.get("entities") if isinstance(out.get("entities"), list) else []
        raws = [str(e.get("raw") or "") for e in entities if isinstance(e, dict)]
        assert any(needle in raw.lower() for raw in raws), out
