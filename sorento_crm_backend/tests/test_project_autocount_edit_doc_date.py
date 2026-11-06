"""AutoCount edit (PATCH) bodies: docDate is the document's own date, top level, never header.

Live refusal (db3, 6 Nov): "FIELD_NOT_EDITABLE: docDate" (header.docDate). At the top level the
Shared Service uses docDate to FIND the existing document ("AutoCount reads documents by
date"), so it must be the DocDate read back from AutoCount, never today. No read, no docDate.
"""
from __future__ import annotations

import pytest

from tests._ac_write_support import (
    EDIT,
    caps_with,
    VIEW,
    WRITE,
    add_amendment,
    add_issue,
    api_fixture,
    done_body,
    order_row,
    fake_ss,  # noqa: F401  (fixture)
)
from tests.test_project_autocount_qt_send import QT_DOC_PATH, QT_KEY, _created, _mark_sent
from tests.test_project_autocount_qt_send import _read_back
from tests.test_project_autocount_qt_send import _url as _qt_url
from tests.test_project_autocount_so_update import DOC_PATH as SO_DOC_PATH
from tests.test_project_autocount_so_update import _adopt, _answer_edits, _setup_mixed
from tests.test_project_autocount_so_update import _url as _so_url


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def _dated(answer, doc_date):
    status, body = answer
    body["document"]["DocDate"] = doc_date
    return status, body


def test_quotation_update_sends_the_read_back_doc_date_not_today(qt_api, fake_ss):
    client, db, world = qt_api
    _mark_sent(db, world)
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    fake_ss.answers[("GET", QT_DOC_PATH)] = _dated(
        (200, _created(world)), "2026-10-01T00:00:00"
    )
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (
        200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=_read_back(world),
                       last_modified="2026-11-06T09:00:00"),
    )

    response = client.post(_qt_url(world))

    assert response.status_code == 200, response.text
    [patch] = fake_ss.to("PATCH", QT_DOC_PATH)
    body = fake_ss.body(patch)
    assert body["docDate"] == "2026-10-01"
    assert "docDate" not in body["header"]
    assert body["header"]["remark1"]


def test_sales_order_update_without_a_read_sends_no_doc_date(so_api, fake_ss):
    client, db, world = so_api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    response = client.post(_so_url(amendment))

    assert response.status_code == 200, response.text
    [patch] = fake_ss.to("PATCH", SO_DOC_PATH)
    body = fake_ss.body(patch)
    assert "docDate" not in body
    assert "docDate" not in (body.get("header") or {})


def test_adopted_sales_order_update_sends_the_read_back_doc_date(so_api, fake_ss):
    client, db, world = so_api
    _adopt(db, world)
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")])
    db.commit()
    fake_ss.answers[("GET", SO_DOC_PATH)] = _dated(
        (200, done_body(details=[], last_modified="2026-10-30T07:00:00")), "2026-10-01T00:00:00"
    )
    fake_ss.answers[("GET", "/api/v1/autocount/write-capabilities")] = (
        200, {"book": "AED_SRT", "capabilities": caps_with()}
    )
    _answer_edits(fake_ss)

    response = client.post(_so_url(amendment))

    assert response.status_code == 200, response.text
    [patch] = fake_ss.to("PATCH", SO_DOC_PATH)
    body = fake_ss.body(patch)
    assert body["docDate"] == "2026-10-01"
    assert "docDate" not in (body.get("header") or {})
