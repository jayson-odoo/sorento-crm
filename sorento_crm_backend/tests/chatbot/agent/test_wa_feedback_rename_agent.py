"""WA-COMPLAINT-INTAKE round 15 red tests (chatbot package): "idea" becomes "feedback" in the filing flow.

Contract: documentation/plans/chatbot/COPY-wa-feedback-rename.md, section "Code-built and agent text". The
internal names stay (tool names `crm_idea_*`, the `IDEA_*` constant names); only the text a user or the model
reads changes. The record number in the agent's confirm note goes through `submission_types.display_number`.

Reuses the harness of test_agent_writes_ideas.py (ss faked at httpx, Postgres blank schema, every test seeds
its own world). The core half of this round is tests/test_wa_feedback_rename.py.
"""
from __future__ import annotations

import pytest

from tests.chatbot.agent.test_agent_writes_ideas import (  # noqa: F401  (fixtures)
    CREATE,
    CREATE_PATH,
    FIELDS,
    LIST,
    PROBLEM,
    UPDATE,
    _fresh_token_cache,
    _listeners,
    confirm,
    db,
    make_world,
    propose,
    ss,
    store,
)
from tests.test_wa_feedback_rename import _fake_display, patch_display_number

ISSUE = {"problem": "The quotation page shows an error", "title": "Quotation page error"}


def _created(ss, number="IDEA-0184"):  # noqa: F811
    import uuid

    idea_id = str(uuid.uuid4())
    ss.route("POST", CREATE_PATH, json_body={"idea_id": idea_id, "idea_number": number, "status": "captured", "title": "t"})
    return idea_id


# --------------------------------------------------------------------------- #
# 4. The confirm note                                                         #
# --------------------------------------------------------------------------- #
def test_the_confirmed_create_note_starts_feedback(db, ss):  # noqa: F811
    w = make_world(db)
    _created(ss)
    _, row = store(db, w, [(CREATE, {"problem": PROBLEM})], live=True)
    outcome = confirm(db, w, row)
    assert outcome.steps[0]["status"] == "done"
    (note,) = outcome.notes
    assert note.startswith("Feedback IDEA-0184"), note
    assert not note.startswith("Idea "), note


def test_a_test_turn_note_says_test_feedback(db, ss):  # noqa: F811
    w = make_world(db)
    _created(ss)
    _, row = store(db, w, [(CREATE, {"problem": PROBLEM})])  # no origin stored: a test create
    outcome = confirm(db, w, row)
    (note,) = outcome.notes
    assert "test feedback" in note.lower(), note
    assert "test idea" not in note.lower(), note


def test_the_confirm_note_shows_the_number_through_display_number(db, ss, monkeypatch):  # noqa: F811
    patch_display_number(monkeypatch, _fake_display)
    w = make_world(db)
    _created(ss)
    _, row = store(db, w, [(CREATE, {"problem": PROBLEM})], live=True)
    outcome = confirm(db, w, row)
    (note,) = outcome.notes
    assert note.startswith("Feedback #0184"), note
    assert "IDEA-0184" not in note, note


# --------------------------------------------------------------------------- #
# 4. The proposal summary                                                     #
# --------------------------------------------------------------------------- #
def test_an_issue_proposal_reads_log_feedback_problem_report(db, ss):  # noqa: F811
    w = make_world(db)
    res, step = propose(db, w, CREATE, {**ISSUE, "type": "issue"})
    assert res.status == "proposed", res.message
    assert step["summary"].startswith(f'Log feedback (Problem report) "{ISSUE["title"]}"'), step["summary"]


@pytest.mark.parametrize("args_type", ["idea", None])
def test_an_idea_proposal_reads_log_feedback_feature_request(db, ss, args_type):  # noqa: F811
    w = make_world(db)
    args = dict(FIELDS) if args_type is None else {**FIELDS, "type": args_type}
    res, step = propose(db, w, CREATE, args)
    assert res.status == "proposed", res.message
    assert step["summary"].startswith(f'Log feedback (Feature request) "{FIELDS["title"]}"'), step["summary"]


# --------------------------------------------------------------------------- #
# 4. Model-facing messages, labels, schema                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["IDEA_NOT_CREATED", "IDEA_OWN_ONLY", "IDEA_ALREADY_CAPTURED", "IDEA_REFUSED"])
def test_the_idea_messages_say_feedback_not_idea(name):
    from app.services.chatbot.agent import writes

    text = getattr(writes, name)
    assert "idea" not in text.lower(), f"{name}: {text!r}"


@pytest.mark.parametrize("tool", [CREATE, UPDATE, LIST])
def test_the_tool_labels_say_feedback_not_idea(tool):
    from app.services.chatbot.agent import tools

    label = tools.TOOL_LABELS[tool]
    assert "feedback" in label.lower(), label
    assert "idea" not in label.lower(), label


def test_the_create_schema_description_names_feedback():
    from app.services.chatbot.agent import writes

    description = writes.WRITES[CREATE].schema["function"]["description"]
    assert "feedback" in description.lower(), description


# --------------------------------------------------------------------------- #
# 6. The ideate lane panel reply                                              #
# --------------------------------------------------------------------------- #
def test_the_panel_reply_says_feedback():
    from app.services.chatbot.lanes.ideate import PANEL_IDEAS_REPLY

    assert "feedback" in PANEL_IDEAS_REPLY.lower(), PANEL_IDEAS_REPLY
    assert not PANEL_IDEAS_REPLY.startswith("Love the idea"), PANEL_IDEAS_REPLY


# --------------------------------------------------------------------------- #
# 7. The canned access denial for the ideation agent                          #
# --------------------------------------------------------------------------- #
def test_the_ideation_access_denial_names_feedback(monkeypatch):
    from app.services.chatbot.copy import fallback_copy
    from app.services.chatbot.lanes import canned

    def _composer_failed(db, *, user_message, fallback_text):
        return fallback_text

    monkeypatch.setattr("app.services.ideation_turn_service.compose_ideate_denial_reply", _composer_failed)
    ctx = {
        "parse": {"output": {"routing": {"suggested_agent": "ideation"}}},
        "text": {"message": {"message": {"text": "the quote page is broken"}}},
    }
    out = canned.access_denied_text(None, ctx, fallback_copy())
    assert out.endswith("access feedback"), out
    assert "ideation" not in out.lower(), out
