"""AGENT-FIELD-MULTI (20 Oct): a tag's Agent field access never stores the same field twice, and
every place the section is labelled reads the field's admin-facing name, not its column key.
Plan: documentation/plans/contacts/PLAN-agent-field-multi-20oct.md. Same harness as the S2/S3 files.
"""
from __future__ import annotations

from app.models.access import AccessAgent

from tests.test_contact_tags_s1 import TAGS, _tag, client, db, perms  # noqa: F401
from tests.test_contact_tags_s2 import _holder, _item, _read, _stag, all_perms  # noqa: F401

OWNER = "incoming_stock_enquiries"


def _owner(db) -> AccessAgent:
    row = AccessAgent(code=OWNER, name="ZZT Incoming Stock Enquiries")
    db.add(row)
    db.flush()
    return row


def _entry(field_key: str, is_allowed: bool = True) -> dict:
    return {"agent_code": OWNER, "resource": "incoming_stock", "field_key": field_key, "is_allowed": is_allowed}


def test_the_same_field_listed_twice_is_refused(client, db, all_perms):
    _owner(db)
    tag = _tag(client)
    url = f"{TAGS}/{tag['id']}"

    twice = client.patch(url, json={"settings": {"agent_fields": [_entry("estimated_arrival_date")] * 2}})
    assert twice.status_code == 422, twice.text
    assert "listed twice" in twice.text

    # Allow and Deny on one field is the same field twice too: the tag cannot say both.
    both = client.patch(url, json={"settings": {"agent_fields": [
        _entry("estimated_arrival_date", True), _entry("estimated_arrival_date", False),
    ]}})
    assert both.status_code == 422, both.text

    ok = client.patch(url, json={"settings": {"agent_fields": [
        _entry("estimated_arrival_date", True), _entry("eta_delay_date", False),
    ]}})
    assert ok.status_code == 200, ok.text
    assert len(ok.json()["settings"]["agent_fields"]) == 2


def test_catalog_offers_each_gated_field_with_its_readable_name(client, db, all_perms):
    _owner(db)
    cat = client.get(f"{TAGS}/settings-catalog").json()
    by_key = {f["field_key"]: f for f in cat["agent_fields"]}
    assert by_key["eta_delay_date"]["label"] == "ETA delay"
    assert by_key["estimated_arrival_date"]["label"] == "ETA"
    assert by_key["informed_collection_date"]["label"] == "Collection informed"


def test_preview_names_the_field_not_its_column(client, db, all_perms):
    agent = _owner(db)
    tag = _stag(client, db, {"agent_fields": [_entry("eta_delay_date")]}, "ZZT-afm")
    contact = _holder(client, db, [tag])
    item = _item(_read(client, contact), "agent_fields", "eta_delay_date")
    assert item["label"] == f"{agent.name}: ETA delay"
