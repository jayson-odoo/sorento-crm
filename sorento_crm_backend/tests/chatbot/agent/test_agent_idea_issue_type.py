"""WA-COMPLAINT-INTAKE red tests (agent): `crm_idea_create` takes a type (UAC T-2, T-3, I-1, I-4, I-5, P-1).

UAC: documentation/plans/chatbot/wa-complaint-intake-acceptance-criteria.md. Owner answer Q1: the type is
the real Shared Service `type` field, no department bridge.

* The tool schema has `type` (enum idea | issue, optional): the model reads it by meaning, no keywords.
* The proposal summary reads "Log issue ..." for an issue and "Log idea ..." unchanged for an idea.
* Execute builds the create through `build_create_payload`: an issue carries `"type": "issue"` and no
  `department`; an idea payload is unchanged (no `type`, no `department`).
* A live (not test) execute attaches the contact's recent chat photos through
  `ideation_gateway_service.upload_idea_attachment`; a test (console) execute attaches none.

Reuses the harness of test_agent_writes_ideas.py (ss faked at httpx, Postgres blank schema) and the photo
seam of tests/test_wa_issue_submissions.py.
"""
from __future__ import annotations

import uuid

import pytest

from tests.chatbot.agent.test_agent_writes_ideas import (  # noqa: F401  (fixtures)
    CREATE,
    CREATE_PATH,
    FIELDS,
    UUID_RE,
    _fresh_token_cache,
    _listeners,
    confirm,
    db,
    make_world,
    posts,
    propose,
    ss,
    store,
)
from tests.test_wa_issue_submissions import install_photo_seam, seed_chat_photo

ISSUE = {
    "problem": "The stock page shows a blank screen on my phone",
    "title": "Blank stock page on phones",
}


def _schema_props():
    from app.services.chatbot.agent import writes

    params = writes.WRITES[CREATE].schema["function"]["parameters"]
    return params


def test_T3_the_tool_schema_has_an_optional_type_enum():
    params = _schema_props()
    prop = params["properties"]["type"]
    assert prop["type"] == "string"
    assert sorted(prop["enum"]) == ["idea", "issue"]
    assert "type" not in params.get("required", [])
    assert params["required"] == ["problem"]


def test_I4_an_issue_proposal_reads_log_issue(db, ss):  # noqa: F811
    w = make_world(db)
    res, step = propose(db, w, CREATE, {**ISSUE, "type": "issue"})
    assert res.status == "proposed", res.message
    assert step["summary"].startswith("Log issue")
    assert ISSUE["title"] in step["summary"]
    assert not UUID_RE.search(step["summary"])
    assert posts(ss, CREATE_PATH) == []


@pytest.mark.parametrize("args_type", ["idea", None])
def test_I4_an_idea_proposal_still_reads_log_idea(db, ss, args_type):  # noqa: F811
    w = make_world(db)
    args = dict(FIELDS) if args_type is None else {**FIELDS, "type": args_type}
    res, step = propose(db, w, CREATE, args)
    assert res.status == "proposed", res.message
    assert step["summary"].startswith(f'Log idea "{FIELDS["title"]}"')


def test_T3_an_unknown_type_is_invalid(db, ss):  # noqa: F811
    w = make_world(db)
    res, step = propose(db, w, CREATE, {**ISSUE, "type": "complaint"})
    assert res.status == "invalid" and step is None


def test_I1_confirming_an_issue_creates_it_with_the_ss_type_field(db, ss):  # noqa: F811
    w = make_world(db)
    _, row = store(db, w, [(CREATE, {**ISSUE, "type": "issue"})], live=True)
    outcome = confirm(db, w, row)
    assert [s["status"] for s in outcome.steps] == ["done"], outcome.steps
    (call,) = posts(ss, CREATE_PATH)
    body = call["json"]
    assert body["type"] == "issue"
    assert "department" not in body
    assert body["problem"] == ISSUE["problem"]


def test_I1_confirming_an_idea_sends_todays_payload(db, ss):  # noqa: F811
    w = make_world(db)
    _, row = store(db, w, [(CREATE, {**FIELDS, "type": "idea"})], live=True)
    outcome = confirm(db, w, row)
    assert [s["status"] for s in outcome.steps] == ["done"], outcome.steps
    (call,) = posts(ss, CREATE_PATH)
    assert "type" not in call["json"] and "department" not in call["json"]


def _fixed_create(ss):  # noqa: F811
    idea_id = str(uuid.uuid4())
    ss.route("POST", CREATE_PATH, json_body={
        "idea_id": idea_id, "idea_number": "IDEA-0300", "status": "captured", "title": ISSUE["title"],
    })
    return idea_id


def _photo_seam(monkeypatch):
    from app.services import ideation_capture_service
    from app.services.chatbot.agent import writes

    return install_photo_seam(monkeypatch, writes, ideation_capture_service)


def test_P1_a_live_issue_attaches_the_recent_chat_photos(db, ss, monkeypatch):  # noqa: F811
    seam = _photo_seam(monkeypatch)
    w = make_world(db)
    a = seed_chat_photo(db, contact_pk=w.contact["pk"], respond_id=w.respond_id, minutes_ago=2)
    b = seed_chat_photo(db, contact_pk=w.contact["pk"], respond_id=w.respond_id, minutes_ago=6)
    old = seed_chat_photo(db, contact_pk=w.contact["pk"], respond_id=w.respond_id, minutes_ago=50)
    pdf = seed_chat_photo(
        db, contact_pk=w.contact["pk"], respond_id=w.respond_id, minutes_ago=3, mime="application/pdf"
    )
    db.commit()
    idea_id = _fixed_create(ss)

    _, row = store(db, w, [(CREATE, {**ISSUE, "type": "issue"})], live=True)
    outcome = confirm(db, w, row)

    assert [s["status"] for s in outcome.steps] == ["done"], outcome.steps
    assert sorted(seam.filenames()) == sorted([a.original_filename, b.original_filename])
    assert old.original_filename not in seam.filenames() and pdf.original_filename not in seam.filenames()
    assert seam.idea_ids() == {idea_id}
    for call in seam.uploads:
        user = call["user"]
        assert str(user["id"] if isinstance(user, dict) else user.id) == w.user_id


def test_P2_a_failed_photo_upload_still_creates(db, ss, monkeypatch):  # noqa: F811
    seam = _photo_seam(monkeypatch)
    seam.fail_first = True
    w = make_world(db)
    seed_chat_photo(db, contact_pk=w.contact["pk"], respond_id=w.respond_id, minutes_ago=2)
    seed_chat_photo(db, contact_pk=w.contact["pk"], respond_id=w.respond_id, minutes_ago=4)
    db.commit()
    _fixed_create(ss)

    _, row = store(db, w, [(CREATE, {**ISSUE, "type": "issue"})], live=True)
    outcome = confirm(db, w, row)

    assert [s["status"] for s in outcome.steps] == ["done"], outcome.steps
    assert len(seam.uploads) == 2
    assert len(posts(ss, CREATE_PATH)) == 1


def test_I5_a_test_execute_attaches_no_photos(db, ss, monkeypatch):  # noqa: F811
    seam = _photo_seam(monkeypatch)
    w = make_world(db)
    seed_chat_photo(db, contact_pk=w.contact["pk"], respond_id=w.respond_id, minutes_ago=2)
    db.commit()
    _fixed_create(ss)

    _, row = store(db, w, [(CREATE, {**ISSUE, "type": "issue"})], live=False)
    outcome = confirm(db, w, row)

    assert [s["status"] for s in outcome.steps] == ["done"], outcome.steps
    (call,) = posts(ss, CREATE_PATH)
    assert call["json"]["is_test"] is True
    assert call["json"]["type"] == "issue"
    assert seam.uploads == []
