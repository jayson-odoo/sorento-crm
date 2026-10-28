"""FILTER-MULTISELECT PR2: the contacts list's Region filter takes several values (OR within the
filter, AND across). A contact holds one or both regions. Red first; Postgres only; rows seeded here.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import RespondContact
from tests._multi_filter_client import get, open_client, ok_ids
from tests._pg_fixture import blank_session, unique_code

CONTACTS = "/api/v1/user-management/contacts/"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _contact(db, tag, label, regions, tier):
    row = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"60{uuid.uuid4().int % 10**8 + 10**8}",
        name=f"ZZT {tag}-{label} {unique_code('c')}",
        chatbot_profile={"language": "en", "tier": tier},
        regions=regions,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seeded(db):
    tag = unique_code("R", alpha=True)
    return dict(
        tag=tag,
        w=_contact(db, tag, "w", ["west"], "dealer"),
        e=_contact(db, tag, "e", ["east"], "office"),
        b=_contact(db, tag, "b", ["west", "east"], "dealer"),
    )


def _ids(client, tag, pairs):
    return ok_ids(get(client, CONTACTS, [("limit", 1000), ("query", tag), *pairs]))


def test_region_two_values_are_the_union(client, seeded):
    s = seeded
    assert _ids(client, s["tag"], [("region", "west,east")]) == {s["w"].id, s["e"].id, s["b"].id}


def test_region_single_value_still_works(client, seeded):
    s = seeded
    assert _ids(client, s["tag"], [("region", "west")]) == {s["w"].id, s["b"].id}
    assert _ids(client, s["tag"], [("region", "east")]) == {s["e"].id, s["b"].id}


def test_region_repeated_param_is_the_union(client, seeded):
    s = seeded
    got = _ids(client, s["tag"], [("region", "west"), ("region", "east")])
    assert got == {s["w"].id, s["e"].id, s["b"].id}


def test_region_unknown_value_is_422(client, seeded):
    assert get(client, CONTACTS, [("region", "north")]).status_code == 422
    assert get(client, CONTACTS, [("region", "west,north")]).status_code == 422


def test_region_and_across_tier(client, seeded):
    s = seeded
    got = _ids(client, s["tag"], [("region", "west,east"), ("tier", "dealer")])
    assert got == {s["w"].id, s["b"].id}
