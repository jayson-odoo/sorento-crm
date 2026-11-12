"""AC-QTSO-CRM-2: an unknown outcome is looked up before any resend (owner rule, 11 Nov).

"Every failed write to AutoCount can be retried after fixing the cause: a refusal releases it, only
a confirmed success locks it, an unknown outcome is checked (look the document up) before
retrying."

Creates already hold their key and body on the record and replay them
(`test_project_autocount_retry.py`). These tests pin the same rule for the two edits:

* SO update (amendment): the order is read BEFORE the PATCH. When AutoCount already holds every
  change (an earlier press landed but its answer was lost), the amendment is recorded as sent with
  AutoCount's own stamp and nothing is written again. A failed read on an order with a stored stamp
  still sends, since the stamp check keeps a resend from landing on a changed order.
* QT update: the document is already read before the PATCH. When it already holds the revision's
  header remark and every line value, the PATCH is not sent again; the edit step is recorded done
  with AutoCount's stamp.
"""
from __future__ import annotations

import httpx

from tests._ac_write_support import (
    DTL_1,
    DTL_2,
    LAST_MODIFIED,
    add_amendment,
    add_issue,
    delay_row,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    order_row,
    put_in_autocount,
    refused_body,
)
from tests.test_project_autocount_qt_send import (  # noqa: F401  (fixtures)
    QT_DOC_PATH,
    _created,
    _mark_sent,
)
from tests.test_project_autocount_qt_send import _url as qt_url
from tests.test_project_autocount_qt_send import api as qt_api  # noqa: F401
from tests.test_project_autocount_so_update import DOC_PATH
from tests.test_project_autocount_so_update import _url as so_url
from tests.test_project_autocount_so_update import api as so_api  # noqa: F401

LANDED_STAMP = "2026-11-12T08:15:00"


def _so_amendment(db, world):
    put_in_autocount(db, world)
    amendment = add_amendment(
        db,
        world,
        [order_row(world, world.line1, "120"), delay_row(world, world.line2, "2027-01-07")],
    )
    db.commit()
    return amendment


def _so_landed(**kw):
    """The order as AutoCount holds it after the amendment's PATCH landed."""
    return done_body(
        details=[
            detail(DTL_1, "X1", "120", "392.85", "BRW-BB", "2026-07-01", 1),
            detail(DTL_2, "X2", "20", "50.00", "MWH-BB", "2027-01-07", 2),
        ],
        last_modified=LANDED_STAMP,
        **kw,
    )


def _so_before():
    return done_body(
        details=[
            detail(DTL_1, "X1", "100", "392.85", "BRW-BB", "2026-07-01", 1),
            detail(DTL_2, "X2", "20", "50.00", "MWH-BB", "2026-08-01", 2),
        ],
        last_modified=LAST_MODIFIED,
    )


def _lost(_request):
    raise httpx.ReadTimeout("lost reply")


# --------------------------------------------------------------------------- SO update


def test_a_lost_so_update_reply_is_looked_up_and_recorded_with_no_second_patch(so_api, fake_ss):
    client, db, world = so_api
    amendment = _so_amendment(db, world)
    fake_ss.answers[("GET", DOC_PATH)] = (200, _so_before())
    fake_ss.answers[("PATCH", DOC_PATH)] = _lost

    first = client.post(so_url(amendment)).json()
    assert first["outcome"] == "unreachable", first
    assert len(fake_ss.to("PATCH", DOC_PATH)) == 1

    # The PATCH had landed: AutoCount now holds both changes under a newer stamp.
    fake_ss.answers[("GET", DOC_PATH)] = (200, _so_landed())
    second = client.post(so_url(amendment)).json()

    assert second["outcome"] == "done", second
    assert second["message"] == "SO412345 updated in AutoCount"
    assert len(fake_ss.to("PATCH", DOC_PATH)) == 1, "looked up, never sent again"
    db.refresh(world.order)
    db.refresh(amendment)
    assert amendment.autocount_edit_sent_at is not None
    assert world.order.autocount_last_modified == LANDED_STAMP


def test_an_so_update_that_did_not_land_is_sent_after_the_lookup(so_api, fake_ss):
    client, db, world = so_api
    amendment = _so_amendment(db, world)
    fake_ss.answers[("GET", DOC_PATH)] = (200, _so_before())
    fake_ss.answers[("PATCH", DOC_PATH)] = (200, _so_landed())

    body = client.post(so_url(amendment)).json()

    assert body["outcome"] == "done", body
    paths = [(r.method, r.url.path) for r in fake_ss.writes()]
    assert paths.index(("GET", DOC_PATH)) < paths.index(("PATCH", DOC_PATH)), "read before the write"
    [patch] = fake_ss.to("PATCH", DOC_PATH)
    assert fake_ss.body(patch)["expectedLastModified"] == LAST_MODIFIED


def test_only_part_of_the_so_update_held_still_sends_the_whole_patch(so_api, fake_ss):
    client, db, world = so_api
    amendment = _so_amendment(db, world)
    half = done_body(
        details=[
            detail(DTL_1, "X1", "120", "392.85", "BRW-BB", "2026-07-01", 1),
            detail(DTL_2, "X2", "20", "50.00", "MWH-BB", "2026-08-01", 2),
        ],
        last_modified=LAST_MODIFIED,
    )
    fake_ss.answers[("GET", DOC_PATH)] = (200, half)
    fake_ss.answers[("PATCH", DOC_PATH)] = (200, _so_landed())

    assert client.post(so_url(amendment)).json()["outcome"] == "done"
    [patch] = fake_ss.to("PATCH", DOC_PATH)
    assert {line["dtlKey"] for line in fake_ss.body(patch)["lines"]} == {DTL_1, DTL_2}


def test_a_failed_lookup_on_an_order_with_a_stamp_still_sends_under_the_stamp(so_api, fake_ss):
    client, db, world = so_api
    amendment = _so_amendment(db, world)
    fake_ss.answers[("GET", DOC_PATH)] = (503, {"detail": "down"})
    fake_ss.answers[("PATCH", DOC_PATH)] = (200, _so_landed())

    assert client.post(so_url(amendment)).json()["outcome"] == "done"
    [patch] = fake_ss.to("PATCH", DOC_PATH)
    assert fake_ss.body(patch)["expectedLastModified"] == LAST_MODIFIED


# --------------------------------------------------------------------------- QT update


def _qt_revision(db, world):
    _mark_sent(db, world)
    issue2 = add_issue(
        db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True
    )
    db.commit()
    return issue2


def _qt_held(world, remark, stamp):
    held = _created(world, last_modified=stamp)
    held["document"]["Remark1"] = remark
    return held


def test_a_lost_qt_update_reply_is_looked_up_and_recorded_with_no_second_patch(qt_api, fake_ss):
    client, db, world = qt_api
    issue2 = _qt_revision(db, world)
    remark = f"{world.document.document_no} (R2)"
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, _qt_held(world, f"{world.document.document_no} (R1)", "2026-10-21T08:00:00"))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = _lost

    first = client.post(qt_url(world)).json()
    assert first["outcome"] == "unreachable", first

    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, _qt_held(world, remark, LANDED_STAMP))
    second = client.post(qt_url(world)).json()

    assert second["outcome"] == "done", second
    assert len(fake_ss.to("PATCH", QT_DOC_PATH)) == 1, "looked up, never sent again"
    db.refresh(world.document)
    assert world.document.autocount_issue_id == issue2.id
    assert world.document.autocount_edit_issue_id == issue2.id
    assert world.document.autocount_last_modified == LANDED_STAMP


def test_a_qt_update_whose_remark_differs_is_still_sent(qt_api, fake_ss):
    client, db, world = qt_api
    _qt_revision(db, world)
    fake_ss.answers[("GET", QT_DOC_PATH)] = (
        200, _qt_held(world, f"{world.document.document_no} (R1)", "2026-10-21T08:00:00")
    )
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (200, _created(world, last_modified=LANDED_STAMP))

    assert client.post(qt_url(world)).json()["outcome"] == "done"
    assert len(fake_ss.to("PATCH", QT_DOC_PATH)) == 1


def test_a_qt_update_with_a_changed_line_value_is_still_sent(qt_api, fake_ss):
    client, db, world = qt_api
    _qt_revision(db, world)
    held = _qt_held(world, f"{world.document.document_no} (R2)", "2026-10-21T08:00:00")
    held["document"]["Details"][0]["Qty"] = 9.0
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, held)
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (200, _created(world, last_modified=LANDED_STAMP))

    assert client.post(qt_url(world)).json()["outcome"] == "done"
    [patch] = fake_ss.to("PATCH", QT_DOC_PATH)
    assert fake_ss.body(patch)["lines"], "the changed row is sent"


def test_doc_stale_message_is_unchanged_when_autocount_does_not_hold_the_change(so_api, fake_ss):
    """Guard: a real change in AutoCount (not ours) still reads as DOC_STALE."""
    client, db, world = so_api
    amendment = _so_amendment(db, world)
    fake_ss.answers[("GET", DOC_PATH)] = (200, _so_before())
    fake_ss.answers[("PATCH", DOC_PATH)] = (409, refused_body("DOC_STALE", "changed"))

    body = client.post(so_url(amendment)).json()

    assert body["outcome"] == "refused"
    assert body["message"].startswith("Changed in AutoCount since 01/10/2026.")
