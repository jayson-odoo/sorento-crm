"""AutoCount edit (PATCH) bodies carry docDate at the top level, never inside header.

Live refusal (db3, 6 Nov): "FIELD_NOT_EDITABLE: docDate". The Shared Service takes docDate only
at the top level of an edit body; header holds editable fields only (QT: remark1).
"""
from __future__ import annotations

import pytest

from tests._ac_write_support import (
    EDIT,
    VIEW,
    WRITE,
    add_issue,
    api_fixture,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    myt_today_candidates,
)
from tests.test_project_autocount_qt_send import QT_DOC_PATH, QT_KEY, _created, _mark_sent
from tests.test_project_autocount_qt_send import _read_back
from tests.test_project_autocount_qt_send import _url as _qt_url
from tests.test_project_autocount_so_update import DOC_PATH as SO_DOC_PATH
from tests.test_project_autocount_so_update import _answer_edits, _setup_mixed
from tests.test_project_autocount_so_update import _url as _so_url


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def test_quotation_update_patch_has_top_level_doc_date_and_remark_in_header(qt_api, fake_ss):
    client, db, world = qt_api
    _mark_sent(db, world)
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, _created(world))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (
        200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=_read_back(world),
                       last_modified="2026-11-06T09:00:00"),
    )

    response = client.post(_qt_url(world))

    assert response.status_code == 200, response.text
    [patch] = fake_ss.to("PATCH", QT_DOC_PATH)
    body = fake_ss.body(patch)
    assert body["docDate"] in myt_today_candidates()
    assert "docDate" not in body["header"]
    assert body["header"]["remark1"]


def test_sales_order_update_patch_has_top_level_doc_date_and_no_header_doc_date(so_api, fake_ss):
    client, db, world = so_api
    amendment, _line3 = _setup_mixed(db, world)
    _answer_edits(fake_ss)

    response = client.post(_so_url(amendment))

    assert response.status_code == 200, response.text
    [patch] = fake_ss.to("PATCH", SO_DOC_PATH)
    body = fake_ss.body(patch)
    assert body["docDate"] in myt_today_candidates()
    assert "docDate" not in (body.get("header") or {})
