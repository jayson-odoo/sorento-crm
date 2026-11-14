"""Lane AGENT-MODE-TAG: agent mode (`respond_contacts.chatbot_agent_enabled`) as a tag chatbot setting
and in the contacts list bulk actions.

Plan `documentation/plans/contacts/PLAN-agent-mode-tag-14nov.md`. Agent mode rides the same code as
every other chatbot switch (AI replies included): the tag key is one more `CHATBOT_BOOLS` entry, the
bulk Copy access switch is one more `SWITCHES` entry. Postgres only, every row seeded here.
"""
from __future__ import annotations

from tests.test_contact_tags_s1 import (  # noqa: F401
    CONTACTS,
    TAGS,
    _contact,
    _tag,
    client,
    db,
    perms,
)
from tests.test_contact_tags_union import _fresh, _stag, _tags, su  # noqa: F401

KEY = "chatbot_agent_enabled"


def test_a_tag_saves_agent_mode_as_a_chatbot_setting(client, db, su):
    resp = client.post(TAGS, json={"name": "ZZT AMT save", "settings": {"chatbot": {KEY: True}}})
    assert resp.status_code == 201, resp.text
    assert resp.json()["settings"]["chatbot"][KEY] is True


def test_agent_mode_must_be_true_or_false_on_a_tag(client, db, su):
    resp = client.post(TAGS, json={"name": "ZZT AMT bad", "settings": {"chatbot": {KEY: "yes"}}})
    assert resp.status_code == 422, resp.text
    assert resp.json()["message"] == "Tag setting 'chatbot_agent_enabled': must be true or false"


def test_a_tag_with_agent_mode_switches_it_on_for_its_contacts(client, db, su):
    tag = _stag(client, db, {"chatbot": {KEY: True}}, "ZZT AMT on")
    c = _contact(db)
    assert _fresh(db, c).chatbot_agent_enabled is False
    _tags(client, c, [tag])
    assert _fresh(db, c).chatbot_agent_enabled is True


def test_agent_mode_adds_up_across_tags_like_ai_replies(client, db, su):
    off = _stag(client, db, {"chatbot": {KEY: False, "chatbot_allowed": False}}, "ZZT AMT off")
    on = _stag(client, db, {"chatbot": {KEY: True, "chatbot_allowed": True}}, "ZZT AMT on2")
    c = _contact(db)
    _tags(client, c, [off, on])
    row = _fresh(db, c)
    assert row.chatbot_agent_enabled is True
    assert row.chatbot_allowed is True


def test_contact_tag_settings_name_the_tag_that_decides_agent_mode(client, db, su):
    tag = _stag(client, db, {"chatbot": {KEY: True}}, "ZZT AMT decides")
    c = _contact(db)
    _tags(client, c, [tag])
    resp = client.get(f"{CONTACTS}/{c.id}/tag-settings")
    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if (i["section"], i["key"]) == ("chatbot", KEY))
    assert item["label"] == "Agent mode"
    assert item["decided_by"] == ["ZZT AMT decides"]
    assert item["expected"] is True and item["current"] is True and item["differs"] is False


def test_copy_access_carries_agent_mode_like_ai_replies(client, db, su):
    from app.services import contact_access_copy_service as svc

    assert (KEY, "Agent mode") in svc.SWITCHES
    source, target = _contact(db, "src"), _contact(db, "dst")
    source.chatbot_agent_enabled = True
    db.flush()

    dry = client.post(
        f"{CONTACTS}/bulk-copy-access",
        json={"source_contact_id": source.id, "target_contact_ids": [target.id], "dry_run": True},
    )
    assert dry.status_code == 200, dry.text
    (row,) = dry.json()["results"]
    change = next(c for c in row["changes"] if c["facet"] == KEY)
    assert (change["label"], change["before"], change["after"]) == ("Agent mode", False, True)

    resp = client.post(
        f"{CONTACTS}/bulk-copy-access",
        json={"source_contact_id": source.id, "target_contact_ids": [target.id], "dry_run": False},
    )
    assert resp.status_code == 200, resp.text
    assert _fresh(db, target).chatbot_agent_enabled is True
