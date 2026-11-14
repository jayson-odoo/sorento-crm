"""WA-COMPLAINT-INTAKE round 13: a filed item always carries a title.

Contract: documentation/plans/chatbot/PROMPT-wa-issue-ideate.md, "Round 13" (L3: a Malay bug report was
filed with NO title; owner: a title is always required). Two fixes, both at the one shared place:

* the extractor schema's `title` description says it is never empty once there is a problem statement,
  whatever the language;
* `ideation_capture_service.build_create_payload` (shared by the WhatsApp capture and the agent's
  `crm_idea_create`) falls back to the problem statement cut by `ideation_extractor.normalise_title` when
  the title is empty, so no item is ever filed untitled. The reply's title line uses the same value.

Postgres only (blank schema via tests/_pg_fixture.py, through the reused capture-turn `env` harness:
extractor, similar-own and create are patched there). Names are reached at call time.
"""
from __future__ import annotations

from types import SimpleNamespace

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.ideation_extractor import normalise_title
from tests.test_ideation_capture_turn import CRM, TITLE, Env, env  # noqa: F401  (fixture)

MALAY_PROBLEM = "Sistem CRM tak boleh buka page quotation, keluar eror"
MALAY_MESSAGE = "Salam, sistem CRM tak boleh buka page quotation, keluar eror"
IDEA_NUMBER = "IDEA-0184"


def _payload(*, title: str, problem: str = MALAY_PROBLEM, submission_type: str = "issue") -> dict:
    from app.services.ideation_capture_service import build_create_payload

    config = SimpleNamespace(product_id="prod-zzt")
    contact = SimpleNamespace(phone_number="+60120000001", submitter_tier=None)
    return build_create_payload(
        config,
        user_id="user-1",
        contact=contact,
        name="USER A",
        fields={"problem": problem},
        title=title,
        use_cases=[],
        source_text="raw text",
        intake_ref="ref-1",
        is_test=False,
        submission_type=submission_type,
    )


def _lines(reply: str) -> list[str]:
    return [line.strip() for line in reply.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# (a) / (b) the shared payload builder                                        #
# --------------------------------------------------------------------------- #
def test_R13_an_empty_title_falls_back_to_the_problem_cut_by_normalise_title():
    payload = _payload(title="")
    expected = normalise_title(MALAY_PROBLEM)
    assert expected, "fixture: the problem gives a title"
    assert payload.get("title"), payload
    assert payload["title"] == expected
    assert len(payload["title"].split()) <= 8


def test_R13_an_empty_title_falls_back_for_an_idea_too():
    payload = _payload(title="", submission_type="idea")
    assert payload.get("title") == normalise_title(MALAY_PROBLEM), payload


def test_R13_a_given_title_is_kept_unchanged():
    payload = _payload(title=TITLE)
    assert payload["title"] == TITLE


# --------------------------------------------------------------------------- #
# (c) the WhatsApp capture path: an untitled extraction still files a title    #
# --------------------------------------------------------------------------- #
def test_R13_a_malay_issue_with_no_extracted_title_is_filed_with_a_title(env):  # noqa: F811
    e: Env = env
    e.ready()
    idea_id = e.created()
    # ss echoes no title of its own: the reply's title line must come from what the CRM sent.
    e.create_result["title"] = ""
    e.extraction(MALAY_MESSAGE, fields={"problem": MALAY_PROBLEM}, title="", language="ms")
    e.extractions[MALAY_MESSAGE].type = "issue"

    out = e.turn(MALAY_MESSAGE)

    assert out["status"] == "complete", out
    (payload,) = e.create_calls
    assert payload["type"] == "issue"
    expected = normalise_title(payload["problem"])
    assert expected
    assert payload.get("title") == expected, payload
    reply = out["reply_text"]
    assert "\n\n" not in reply and not reply.startswith("\n"), repr(reply)
    lines = _lines(reply)
    assert any(IDEA_NUMBER in line for line in lines)
    assert f"Maklum balas anda telah direkodkan: Laporan masalah - {expected}" in lines, lines
    assert f"{CRM}/ideas/{idea_id}" in lines


# --------------------------------------------------------------------------- #
# (d) the extractor schema tells the model the title is never empty            #
# --------------------------------------------------------------------------- #
def test_R13_the_title_description_says_it_is_never_empty_once_there_is_a_problem():
    from app.services.ideation_extractor import IDEATE_EXTRACTION_JSON_SCHEMA as schema

    description = schema["properties"]["title"]["description"]
    assert "never empty" in description, description
