"""WA-COMPLAINT-INTAKE P-3 through the real turn tail (round 4, lead).

The chatbot tail (`chatbot/turn/tail.write_merged`) rewrites the contact's `session_vars` with its own
key set after every turn, so "already sent" must not live there: a photo that landed on an item must
never be sent again on the contact's next filing, whatever the tail wrote in between.

Lives under tests/chatbot because it imports the chatbot package (tests/chatbot/test_import_boundary.py).
"""
from __future__ import annotations

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests.test_ideation_capture_turn import Env, env  # noqa: F401  (fixture)
from tests.test_wa_issue_submissions import ISSUE_MSG, install_photo_seam, seed_chat_photo


def _issue(e: Env, text: str) -> str:
    e.idea_message(text, language="en")
    e.extractions[text].type = "issue"
    return text


def test_P3_a_tail_write_between_filings_does_not_resend_photos(env, monkeypatch):  # noqa: F811
    from app.services.chatbot.turn.tail import write_merged

    photos = install_photo_seam(monkeypatch, env.svc)
    env.ready()
    first_id = env.created()
    seed_chat_photo(env.db, contact_pk=env.contact.id, respond_id=env.rio, minutes_ago=2)
    seed_chat_photo(env.db, contact_pk=env.contact.id, respond_id=env.rio, minutes_ago=3)
    first = env.turn(_issue(env, ISSUE_MSG))
    assert first["status"] == "complete" and len(photos.uploads) == 2
    assert photos.idea_ids() == {first_id}

    # The turn tail writes its own five keys, exactly as a live turn ends.
    write_merged(
        env.db,
        respond_io_id=env.rio,
        payload={"focus": None, "open_question": None, "ideation": None, "access_levels": [],
                 "contains_flyer": False, "reply_language": "en"},
        base=None,
        turn_id=None,
    )

    photos.uploads.clear()
    env.created()
    second = env.turn(_issue(env, "the search box also freezes on the order page"))
    assert second["status"] == "complete"
    assert photos.uploads == [], "photos that already landed on an item were sent again"
