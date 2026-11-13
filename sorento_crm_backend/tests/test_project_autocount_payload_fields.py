"""AC-QTSO-CRM: the AutoCount state fields reach the screens through the REAL routes.

`response_model` silently drops any field it does not declare, and the service dict builders
(`serialize_row`, `serialize_document`) are separate from the schemas, so a field can exist in one
and vanish on the wire. These tests read the HTTP responses, never the builders.

* project SO list row and SO detail: `in_autocount` (False before, True once `autocount_doc_key`
  is set);
* quotation document detail and list: `in_autocount`, `autocount_doc_no`, `latest_issue_accepted`,
  `autocount_needs_update`, across the four states (not accepted, accepted and unsent, sent, a
  newer accepted issue);
* no docKey, and no last-modified stamp, ever appears in those payloads.
"""
from __future__ import annotations

import pytest

from tests._ac_write_support import (
    BASE,
    DOC_KEY,
    EDIT,
    VIEW,
    WRITE,
    add_issue,
    api_fixture,
    put_in_autocount,
)

QT_KEY = 5001
PERMS = [VIEW, EDIT, WRITE, "projects.projects.view_own", "projects.quotations.view"]
FORBIDDEN_KEYS = {"autocount_doc_key", "autocount_last_modified", "autocount_issue_id", "docKey", "dtlKey"}


def _scalars(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield ("key", key)
            yield from _scalars(value)
    elif isinstance(node, list):
        for value in node:
            yield from _scalars(value)
    else:
        yield ("value", node)


def assert_no_key_leak(payload, *keys_values):
    leaked_keys = {v for kind, v in _scalars(payload) if kind == "key"} & FORBIDDEN_KEYS
    assert not leaked_keys, f"internal AutoCount fields on the wire: {leaked_keys}"
    values = {str(v) for kind, v in _scalars(payload) if kind == "value"}
    for secret in keys_values:
        assert str(secret) not in values, f"docKey value {secret} on the wire"


@pytest.fixture
def so_api():
    yield from api_fixture("so", PERMS, switch=True)


@pytest.fixture
def qt_api():
    yield from api_fixture("qt", PERMS, switch=True)


@pytest.fixture
def qt_api_unaccepted():
    yield from api_fixture("qt", PERMS, switch=True, accepted=False)


# --------------------------------------------------------------------------- sales orders


def _so_row(client, world):
    response = client.get(f"{BASE}/projects/{world.project.id}/sales-orders")
    assert response.status_code == 200, response.text
    [row] = [r for r in response.json()["data"] if r["id"] == world.order.id]
    return row, response.json()


def _so_detail(client, world):
    response = client.get(f"{BASE}/sales-orders/{world.order.id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_so_list_row_and_detail_say_not_in_autocount_before_the_key_is_set(so_api):
    client, _db, world = so_api

    row, _ = _so_row(client, world)
    detail = _so_detail(client, world)

    assert row["in_autocount"] is False
    assert detail["in_autocount"] is False


def test_so_list_row_and_detail_say_in_autocount_once_the_key_is_set(so_api):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()

    row, whole = _so_row(client, world)
    detail = _so_detail(client, world)

    assert row["in_autocount"] is True
    assert detail["in_autocount"] is True
    assert row["autocount_doc_no"] == "SO412345"


def test_so_payloads_never_carry_the_doc_key(so_api):
    client, db, world = so_api
    put_in_autocount(db, world)
    db.commit()

    row, whole = _so_row(client, world)
    detail = _so_detail(client, world)

    assert_no_key_leak(whole, DOC_KEY)
    assert_no_key_leak(detail, DOC_KEY)


# --------------------------------------------------------------------------- quotation documents


def _qt_detail(client, world):
    response = client.get(f"{BASE}/projects/{world.project.id}/quotation-documents/{world.document.id}")
    assert response.status_code == 200, response.text
    return response.json()


def _qt_list_row(client, world):
    response = client.get(f"{BASE}/projects/{world.project.id}/quotation-documents")
    assert response.status_code == 200, response.text
    [row] = [r for r in response.json()["data"] if r["id"] == world.document.id]
    return row


def _mark_sent(db, world, issue):
    world.document.autocount_doc_no = "QT000777"
    world.document.autocount_doc_key = str(QT_KEY)
    world.document.autocount_last_modified = "2026-10-21T08:00:00"
    world.document.autocount_issue_id = issue.id
    db.commit()


def _state(body):
    return {
        "in_autocount": body["in_autocount"],
        "autocount_doc_no": body["autocount_doc_no"],
        "latest_issue_accepted": body["latest_issue_accepted"],
        "autocount_needs_update": body["autocount_needs_update"],
    }


def test_qt_not_accepted(qt_api_unaccepted):
    client, _db, world = qt_api_unaccepted

    assert _state(_qt_detail(client, world)) == {
        "in_autocount": False,
        "autocount_doc_no": None,
        "latest_issue_accepted": False,
        "autocount_needs_update": False,
    }


def test_qt_accepted_not_sent(qt_api):
    client, _db, world = qt_api

    assert _state(_qt_detail(client, world)) == {
        "in_autocount": False,
        "autocount_doc_no": None,
        "latest_issue_accepted": True,
        "autocount_needs_update": False,
    }


def test_qt_sent(qt_api):
    client, db, world = qt_api
    _mark_sent(db, world, world.issue)

    assert _state(_qt_detail(client, world)) == {
        "in_autocount": True,
        "autocount_doc_no": "QT000777",
        "latest_issue_accepted": True,
        "autocount_needs_update": False,
    }


def test_qt_a_newer_accepted_issue_needs_an_update(qt_api):
    client, db, world = qt_api
    _mark_sent(db, world, world.issue)
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()

    assert _state(_qt_detail(client, world)) == {
        "in_autocount": True,
        "autocount_doc_no": "QT000777",
        "latest_issue_accepted": True,
        "autocount_needs_update": True,
    }


def test_qt_a_newer_unaccepted_issue_is_not_accepted_and_needs_no_update(qt_api):
    client, db, world = qt_api
    _mark_sent(db, world, world.issue)
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=False)
    db.commit()

    state = _state(_qt_detail(client, world))

    assert state["latest_issue_accepted"] is False
    assert state["autocount_needs_update"] is False


def test_qt_list_rows_carry_the_same_fields(qt_api):
    client, db, world = qt_api
    _mark_sent(db, world, world.issue)

    assert _state(_qt_list_row(client, world))["in_autocount"] is True
    assert _qt_list_row(client, world)["autocount_doc_no"] == "QT000777"


def test_qt_payloads_never_carry_the_doc_key(qt_api):
    client, db, world = qt_api
    _mark_sent(db, world, world.issue)

    assert_no_key_leak(_qt_detail(client, world), QT_KEY)
    assert_no_key_leak(_qt_list_row(client, world), QT_KEY)
