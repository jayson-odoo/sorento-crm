"""MODEL-PER-CONTACT slice 2 (backend, red): tag `llm` leaf, contact override, resolver, tag panel.

UAC AC-M-1, 3, 4, 5, 6, 7, 8 (resolver half), 9, 14. Contract: `contact_llm_choice.ContactLLMChoice` /
`contact_llm_choice(db, contact)`; tag leaf `settings.chatbot.llm = {provider, model}`; contact columns
`chatbot_llm_provider` / `chatbot_llm_model`; `PUT /contacts/{id}/chatbot` field `llm`; contact read
field `chatbot_llm = {provider, model, source, tags}`. Fixtures are the CONTACT-TAGS ones (private blank
schema, mocked permissions). Postgres only; every row seeded here.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services import contact_tag_settings as cts
from app.services.error_handler import AppException

from tests.test_contact_tags_s1 import (  # noqa: F401
    CONTACTS, EDIT, TAGS, VIEW, _contact, _set_tags, _tag, client, db, perms,
)
from tests.test_contact_tags_s2 import _holder, _read, _stag, all_perms  # noqa: F401

GEMINI = {"provider": "gemini", "model": "gemini-3.5-flash-lite"}
OPENAI = {"provider": "openai", "model": "gpt-4.1-mini"}


def _llm_tag(client, db, llm=None, name=None, **extra_chatbot):
    return _stag(client, db, {"chatbot": {"llm": llm or GEMINI, **extra_chatbot}}, name)


def _choice(db, contact):
    from app.services.contact_llm_choice import contact_llm_choice

    db.expire_all()
    return contact_llm_choice(db, contact)


def _stored(db, contact_id):
    return db.execute(
        text("SELECT chatbot_llm_provider, chatbot_llm_model FROM respond_contacts WHERE id = :i"),
        {"i": contact_id},
    ).one()


def _override(db, contact, provider, model):
    db.execute(
        text("UPDATE respond_contacts SET chatbot_llm_provider = :p, chatbot_llm_model = :m WHERE id = :i"),
        {"p": provider, "m": model, "i": contact.id},
    )
    db.flush()
    db.expire_all()


def _put(client, contact_id, body):
    return client.put(f"{CONTACTS}/{contact_id}/chatbot", json=body)


# ---------------------------------------------------------------- AC-M-1 validation


def test_ac_m_1_a_valid_llm_is_accepted(db):
    for llm in (GEMINI, OPENAI, {"provider": "anthropic", "model": "x" * 100}):
        assert cts.validate_settings(db, {"chatbot": {"llm": llm}}) == {"chatbot": {"llm": llm}}


@pytest.mark.parametrize(
    "llm,named",
    [
        ({"provider": "mistral", "model": "m"}, "provider"),
        ({"provider": "gemini", "model": ""}, "model"),
        ({"provider": "gemini", "model": "   "}, "model"),
        ({"provider": "gemini", "model": "x" * 101}, "model"),
        ({"provider": "gemini"}, "model"),
        ("gemini", "llm"),
        (["gemini"], "llm"),
    ],
)
def test_ac_m_1_a_bad_llm_is_422_naming_the_field(db, llm, named):
    with pytest.raises(AppException) as exc:
        cts.validate_settings(db, {"chatbot": {"llm": llm}})
    assert exc.value.status_code == 422
    assert named in str(exc.value.detail)


def test_ac_m_1_the_tag_patch_route_rejects_it_and_stores_nothing(client, all_perms):
    tag = _tag(client)
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": {"chatbot": {"llm": {"provider": "mistral", "model": "m"}}}})
    assert resp.status_code == 422, resp.text
    ok = client.patch(f"{TAGS}/{tag['id']}", json={"settings": {"chatbot": {"llm": GEMINI}}})
    assert ok.status_code == 200, ok.text
    assert client.get(f"{TAGS}/{tag['id']}").json()["settings"] == {"chatbot": {"llm": GEMINI}}


# ---------------------------------------------------------------- AC-M-3 PUT /contacts/{id}/chatbot


def test_ac_m_3_put_llm_sets_both_columns(client, db, all_perms):
    c = _contact(db)
    resp = _put(client, c.id, {"llm": OPENAI})
    assert resp.status_code == 200, resp.text
    assert tuple(_stored(db, c.id)) == ("openai", "gpt-4.1-mini")
    assert resp.json()["chatbot_llm"]["provider"] == "openai"


def test_ac_m_3_put_llm_null_clears_both(client, db, all_perms):
    c = _contact(db)
    _override(db, c, "openai", "gpt-4.1-mini")
    resp = _put(client, c.id, {"llm": None})
    assert resp.status_code == 200, resp.text
    assert tuple(_stored(db, c.id)) == (None, None)


def test_ac_m_3_absent_llm_leaves_it_alone(client, db, all_perms):
    c = _contact(db)
    _override(db, c, "openai", "gpt-4.1-mini")
    resp = _put(client, c.id, {"notify_salesman": True})
    assert resp.status_code == 200, resp.text
    assert tuple(_stored(db, c.id)) == ("openai", "gpt-4.1-mini")


@pytest.mark.parametrize(
    "llm", [{"provider": "mistral", "model": "m"}, {"provider": "openai", "model": ""},
            {"provider": "openai", "model": "  "}, {"provider": "openai"}, {"model": "gpt"}]
)
def test_ac_m_3_a_bad_llm_is_422_and_writes_nothing(client, db, all_perms, llm):
    c = _contact(db)
    resp = _put(client, c.id, {"llm": llm})
    assert resp.status_code == 422, resp.text
    assert tuple(_stored(db, c.id)) == (None, None)


def test_ac_m_3_the_gate_is_unchanged(client, db, perms):
    perms["granted"] = {VIEW}
    c = _contact(db)
    assert _put(client, c.id, {"llm": OPENAI}).status_code == 403


# ---------------------------------------------------------------- AC-M-4 contact read


def _read_llm(client, contact):
    resp = client.get(f"{CONTACTS}/{contact.id}")
    assert resp.status_code == 200, resp.text
    assert "chatbot_llm" in resp.json(), "contact read has no chatbot_llm"
    return resp.json()["chatbot_llm"]


def test_ac_m_4_source_contact(client, db, all_perms):
    tag = _llm_tag(client, db)
    c = _holder(client, db, [tag])
    _override(db, c, "openai", "gpt-4.1-mini")
    got = _read_llm(client, c)
    assert (got["provider"], got["model"], got["source"]) == ("openai", "gpt-4.1-mini", "contact")


def test_ac_m_4_source_tag(client, db, all_perms):
    tag = _llm_tag(client, db, name="ZZT tag one")
    c = _holder(client, db, [tag])
    got = _read_llm(client, c)
    assert (got["provider"], got["model"], got["source"]) == ("gemini", "gemini-3.5-flash-lite", "tag")
    assert got["tags"] == ["ZZT tag one"]


def test_ac_m_4_source_tag_conflict(client, db, all_perms):
    a = _llm_tag(client, db, GEMINI, name="ZZT tag a")
    b = _llm_tag(client, db, OPENAI, name="ZZT tag b")
    got = _read_llm(client, _holder(client, db, [a, b]))
    assert got["source"] == "tag_conflict"
    assert got["provider"] is None and got["model"] is None
    assert len(got["tags"]) == 2
    assert "ZZT tag a" in json.dumps(got["tags"]) and "ZZT tag b" in json.dumps(got["tags"])


def test_ac_m_4_source_none(client, db, all_perms):
    got = _read_llm(client, _holder(client, db, []))
    assert got["source"] == "none" and got["provider"] is None and got["model"] is None


# ---------------------------------------------------------------- AC-M-5..9 the resolver


def test_ac_m_5_the_override_beats_a_tag(client, db, all_perms):
    c = _holder(client, db, [_llm_tag(client, db, GEMINI)])
    _override(db, c, "openai", "gpt-4.1-mini")
    got = _choice(db, c)
    assert (got.provider, got.model, got.source) == ("openai", "gpt-4.1-mini", "contact")


def test_ac_m_6_one_tag(client, db, all_perms):
    c = _holder(client, db, [_llm_tag(client, db, GEMINI, name="ZZT only")])
    got = _choice(db, c)
    assert (got.provider, got.model, got.source) == ("gemini", "gemini-3.5-flash-lite", "tag")
    assert got.tags == ["ZZT only"]


def test_ac_m_6_two_tags_same_model(client, db, all_perms):
    a = _llm_tag(client, db, GEMINI, name="ZZT same a")
    b = _llm_tag(client, db, dict(GEMINI), name="ZZT same b")
    got = _choice(db, _holder(client, db, [a, b]))
    assert (got.provider, got.model, got.source) == ("gemini", "gemini-3.5-flash-lite", "tag")
    assert sorted(got.tags) == ["ZZT same a", "ZZT same b"]


def test_ac_m_7_two_tags_different_models_conflict(client, db, all_perms):
    a = _llm_tag(client, db, GEMINI, name="ZZT diff a")
    b = _llm_tag(client, db, OPENAI, name="ZZT diff b")
    got = _choice(db, _holder(client, db, [a, b]))
    assert got.source == "tag_conflict"
    assert got.provider is None and got.model is None
    assert sorted(got.tags) == ["ZZT diff a", "ZZT diff b"]


def test_ac_m_7_same_provider_different_model_is_still_a_conflict(client, db, all_perms):
    a = _llm_tag(client, db, GEMINI)
    b = _llm_tag(client, db, {"provider": "gemini", "model": "gemini-2.5-flash"})
    assert _choice(db, _holder(client, db, [a, b])).source == "tag_conflict"


def test_ac_m_8_untagged_is_none(client, db, all_perms):
    got = _choice(db, _holder(client, db, []))
    assert (got.provider, got.model, got.source, got.tags) == (None, None, "none", [])


def test_ac_m_8_a_tag_with_a_chatbot_section_but_no_llm_is_none(client, db, all_perms):
    tag = _stag(client, db, {"chatbot": {"chatbot_stock_allowed": False}})
    got = _choice(db, _holder(client, db, [tag]))
    assert (got.provider, got.model, got.source) == (None, None, "none")


def test_ac_m_9_a_tag_edit_applies_to_the_next_call_with_no_apply(client, db, all_perms):
    tag = _llm_tag(client, db, GEMINI)
    c = _holder(client, db, [tag])
    assert _choice(db, c).model == "gemini-3.5-flash-lite"
    db.execute(
        text("UPDATE contact_tags SET settings = CAST(:s AS jsonb) WHERE id = :i"),
        {"s": json.dumps({"chatbot": {"llm": OPENAI}}), "i": tag["id"]},
    )
    got = _choice(db, c)
    assert (got.provider, got.model) == ("openai", "gpt-4.1-mini")


def test_ac_m_9_removing_the_tag_or_the_override_applies_at_once(client, db, all_perms):
    tag = _llm_tag(client, db, GEMINI)
    c = _holder(client, db, [tag])
    _override(db, c, "openai", "gpt-4.1-mini")
    assert _choice(db, c).source == "contact"
    _override(db, c, None, None)
    assert _choice(db, c).source == "tag"
    _set_tags(client, c, [])
    assert _choice(db, c).source == "none"


# ---------------------------------------------------------------- AC-M-14 tag panel and Apply


def _llm_item(body):
    found = [i for i in body["items"] if i["section"] == "chatbot" and i["key"] == "llm"]
    assert len(found) == 1, body["items"]
    return found[0]


def test_ac_m_14_the_panel_lists_ai_model_decided_by_the_tags(client, db, all_perms):
    a = _llm_tag(client, db, GEMINI, name="ZZT panel a")
    b = _llm_tag(client, db, dict(GEMINI), name="ZZT panel b")
    body = _read(client, _holder(client, db, [a, b]))
    item = _llm_item(body)
    assert sorted(item["decided_by"]) == ["ZZT panel a", "ZZT panel b"]
    assert item["conflict"] is False
    assert item["differs"] is False
    assert body["status"] == "matches"


def test_ac_m_14_a_conflict_lists_both_tags_and_never_differs(client, db, all_perms):
    a = _llm_tag(client, db, GEMINI, name="ZZT cf a")
    b = _llm_tag(client, db, OPENAI, name="ZZT cf b")
    item = _llm_item(_read(client, _holder(client, db, [a, b])))
    assert item["conflict"] is True
    assert sorted(t["name"] for t in item["conflict_tags"]) == ["ZZT cf a", "ZZT cf b"]
    assert item["differs"] is False


def test_ac_m_14_an_override_that_differs_from_the_tags_is_not_a_difference(client, db, all_perms):
    tag = _llm_tag(client, db, GEMINI)
    c = _holder(client, db, [tag])
    _override(db, c, "openai", "gpt-4.1-mini")
    body = _read(client, c)
    assert _llm_item(body)["differs"] is False
    assert body["status"] == "matches"


def test_ac_m_14_apply_preview_and_write_never_touch_the_override(client, db, all_perms):
    tag = _stag(client, db, {"chatbot": {"llm": GEMINI, "chatbot_stock_allowed": False}})
    c = _holder(client, db, [tag], chatbot_stock_allowed=True)
    _override(db, c, "openai", "gpt-4.1-mini")
    plain = _holder(client, db, [tag], chatbot_stock_allowed=True)
    url = f"{CONTACTS}/bulk-apply-tag-settings"
    for dry_run in (True, False):
        resp = client.post(url, json={"contact_ids": [c.id, plain.id], "dry_run": dry_run})
        assert resp.status_code == 200, resp.text
        for row in resp.json()["results"]:
            assert all(ch.get("key") != "llm" for ch in row["changes"]), row
    db.expire_all()
    assert tuple(_stored(db, c.id)) == ("openai", "gpt-4.1-mini")
    assert tuple(_stored(db, plain.id)) == (None, None)
    # the write really ran for the other setting, so the llm item was skipped on purpose
    assert db.execute(text("SELECT chatbot_stock_allowed FROM respond_contacts WHERE id = :i"), {"i": c.id}).scalar() is False


# ---------------------------------------------------------------- one provider label (D3)


def test_d3_conflict_values_use_the_frontend_provider_labels(client, db, all_perms):
    a = _llm_tag(client, db, GEMINI, name="ZZT lbl a")
    b = _llm_tag(client, db, {"provider": "openai", "model": "gpt-5.4-mini"}, name="ZZT lbl b")
    item = _llm_item(_read(client, _holder(client, db, [a, b])))
    assert item["conflict"] is True
    values = {t["name"]: t["value"] for t in item["conflict_tags"]}
    assert values == {
        "ZZT lbl a": "Google Gemini gemini-3.5-flash-lite",
        "ZZT lbl b": "OpenAI gpt-5.4-mini",
    }


def test_d3_single_tag_display_uses_the_frontend_provider_label(client, db, all_perms):
    tag = _llm_tag(client, db, GEMINI, name="ZZT lbl single")
    item = _llm_item(_read(client, _holder(client, db, [tag])))
    assert item["expected"] == "Google Gemini gemini-3.5-flash-lite"
