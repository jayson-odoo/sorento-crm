"""S0 - the external contract (`TurnRequest`/`TurnResponse`/`CompleteRequest`/
`CompleteResponse`/`ACTION_KINDS`) is byte-identical to what shipped on `main` before
this lane started (AC-1507, PLAN-chatbot-turn-rearch.md).

The fixture (`tests/chatbot/fixtures/external_contract_main_3009b374c.json`) was
captured by the tester FROM `origin/main` (`model_json_schema()` on each class plus
`list(ACTION_KINDS)`), on this lane's branch point - `f14802a7c` at the time of writing,
not the `3009b374c` in the captain's brief; the filename is kept exactly as specified in
the brief regardless (see the tester's ambiguity list).

THIS AC IS EXPECTED GREEN RIGHT NOW, by design - it is the guard that later S0/S2/S3
slices must not silently reshape the outer-loop contract, not a red waiting on new work.
Said explicitly per the brief's own instruction.
"""
from __future__ import annotations

import json
import pathlib

from app.services.chatbot.contracts import (
    ACTION_KINDS,
    CompleteRequest,
    CompleteResponse,
    TurnRequest,
    TurnResponse,
)

FIXTURE = (
    pathlib.Path(__file__).resolve().parent
    / "fixtures"
    / "external_contract_main_3009b374c.json"
)


def _pinned() -> dict:
    return json.loads(FIXTURE.read_text())


def test_fixture_file_exists():
    assert FIXTURE.exists(), FIXTURE


def test_turn_request_schema_matches_pinned():
    assert TurnRequest.model_json_schema() == _pinned()["TurnRequest"]


def test_turn_response_schema_matches_pinned():
    assert TurnResponse.model_json_schema() == _pinned()["TurnResponse"]


def test_complete_request_schema_matches_pinned():
    assert CompleteRequest.model_json_schema() == _pinned()["CompleteRequest"]


def test_complete_response_schema_matches_pinned():
    assert CompleteResponse.model_json_schema() == _pinned()["CompleteResponse"]


def test_action_kinds_matches_pinned():
    assert list(ACTION_KINDS) == _pinned()["ACTION_KINDS"]
