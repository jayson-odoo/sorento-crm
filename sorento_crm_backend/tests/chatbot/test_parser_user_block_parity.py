"""The CRM hands the parser exactly the bytes n8n handed it (D8, AC-153 style).

On 5 Sep 2026 a production turn - "What is the weather in KL today" - came back
`message_type: clarification` from the CRM (twice, reproduced) and `unknown` from
the pre-S1 n8n reformulator. Two prompt-bytes explanations were proposed on the
n8n side and this file settles both against the captured run, byte for byte:

1. n8n's `latest_user_message` expression ends with a literal newline, the
   `reply to:` clause and another newline, so the baseline user block carried a
   trailing `"\\n\\n"`. **It does not diverge:** `build_latest_user_message`
   returns `f"{line1}\\n{line2}\\n"`, which is the same two newlines when nothing
   was quoted. Both blocks are 211 bytes.
2. the baseline's resolved reformulator input carried no `referenced_result_set`
   key at all, so a CRM rendering `referenced_result_set: []` would be a
   difference. **It cannot be:** `referenced_result_set` never enters the user
   block. It goes to `output_exchange.post_process` as part of `parent_input`,
   which is post-processing, not prompt.

The remaining divergence is in the SYSTEM message and the model, not here; the
measurement is written up in
`documentation/plans/chatbot/parser-prompt-inventory.md` ("Turn 6").

The fixture is the captured run, not a hand-written expectation: the n8n side of
the comparison is COMPUTED in the test by applying the AI Agent node's own `text`
expression to the workflow inputs the sub was actually handed, so neither half of
the assertion can be edited into agreement with the other.

Offline: no database, no LLM, no n8n.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope
from app.services.chatbot.head import parser as parser_mod

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "chatbot"
    / "parser-user-block"
    / "turn6-weather-kl.json"
)


@pytest.fixture(scope="module")
def turn6() -> dict:
    return json.loads(FIXTURE.read_text())


def _n8n_user_block(inputs: dict) -> str:
    """`sub-semantic-parser`'s AI Agent `text` expression, evaluated.

    Two interpolations and one `\\n` between them, which is the whole node. The
    `replace` is the same regex `build_user_block` ports, kept here as n8n's own
    JavaScript rather than by calling the port, or the test would be comparing a
    function with itself.
    """
    previous = str(inputs["previous_conversation_state"].get("response") or "")
    previous = re.sub(r"^Previous turn \([a-z_]+\)", "Previous turn", previous, flags=re.I)
    return f"Previous response: {previous}\nCurrent user message: {inputs['latest_user_message']}"


def _crm_user_block(fixture: dict) -> str:
    envelope = Envelope(**fixture["envelope"])
    session_block = fixture["session_block"]
    variables = session_block["session_vars"]["variables"]
    return parser_mod.build_user_block(
        previous_response=variables.get("response"),
        latest_user_message=engine_mod.build_latest_user_message(envelope, session_block),
        pending_kind=engine_mod._pending_kind(variables),
    )


def test_the_user_block_is_byte_identical_to_the_one_n8n_sent(turn6) -> None:
    crm = _crm_user_block(turn6)
    n8n = _n8n_user_block(turn6["baseline_workflow_inputs"])

    assert crm == n8n
    assert len(crm.encode("utf-8")) == len(n8n.encode("utf-8"))


def test_the_trailing_blank_line_survives(turn6) -> None:
    """Lead 1, pinned as a property rather than as a string.

    Several ported blocks split the quoted-message clause back off with
    `/\\s*reply to:/i`, so the shape of the tail is load-bearing and a tidy-up
    that stripped it would be a silent prompt change.
    """
    crm = _crm_user_block(turn6)

    assert crm.endswith("What is the weather in KL today\n\n")
    assert turn6["baseline_workflow_inputs"]["latest_user_message"].endswith("\n\n")


def test_the_user_block_says_nothing_about_a_result_set(turn6) -> None:
    """Lead 2. `referenced_result_set` is post-processor input, never prompt."""
    crm = _crm_user_block(turn6)

    assert "referenced_result_set" not in crm
    # Two labelled parts and nothing else. The previous response carries its own
    # newlines, so counting them proves nothing; splitting on the second label does.
    head, tail = crm.split("\nCurrent user message: ")
    assert head.startswith("Previous response: ")
    assert tail == "What is the weather in KL today\n\n"


def test_no_pending_line_is_added_on_this_turn(turn6) -> None:
    """R3's marker is the ONE addition S1 makes to this prompt, and it is a real
    divergence whenever it fires - so the turn that produced the divergence had
    better not be one where it did. This session carries no `pending` key, so it
    does not."""
    variables = turn6["session_block"]["session_vars"]["variables"]

    assert "pending" not in variables
    assert engine_mod._pending_kind(variables) is None
    assert "Pending:" not in _crm_user_block(turn6)
