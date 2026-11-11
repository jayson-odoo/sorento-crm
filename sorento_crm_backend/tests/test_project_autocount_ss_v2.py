"""AC-QTSO-CRM-2: the CRM side of SS AutoCount write API v2 (SS plan 61 section 6).

SS v2 turns on `delete_line` and `cancel_doc` for quotations and sales orders. So:

* the gateway is unchanged (crew, SS 4193fdc4): the PATCH takes changed rows (dtlKey >= 1) only,
  and a new row is `POST .../lines {line{}}`, ONE per call (the CRM sent `{lines[]}` before);
* a row AutoCount holds that the accepted revision no longer quotes is removed with the delete-line
  route when the feed offers `delete_line`, the last line included (owner: no extra guards); with
  `delete_line` off it still waits;
* a sales order amendment row CANCEL BALANCE is never written to AutoCount, whatever the feed
  offers (owner, 11 Nov): it waits;
* the new codes read in plain words: DOC_HAS_TRANSFERS, DOC_CANCELLED, CANCEL_IGNORED,
  ROW_HAS_TRANSFERS (refusals / mismatch). LOCATION_NOT_MOVED / ROW_VALUES_NOT_KEPT come only from
  link / relink (the Stock Debt lane), never from a QT / SO write.

Everything stays behind the admin switch (the existing switch tests pin that).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests._ac_write_support import (
    BASE,
    BOOK,
    CAPS_PATH,
    DOC_KEY,
    DTL_1,
    EDIT,
    LAST_MODIFIED,
    SO_CREATE_PATH,
    VIEW,
    WAITING,
    WRITE,
    add_amendment,
    add_issue,
    api_fixture,
    cancel_balance_row,
    caps_with,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    order_row,
    put_in_autocount,
    refused_body,
)
from tests.test_project_autocount_qt_send import (
    QT_DOC_PATH,
    QT_KEY,
    _mark_sent,
    _new_product,
    _read_back,
)
from tests.test_project_autocount_so_update import DTL_3, _third_line

SO_DOC_PATH = f"{SO_CREATE_PATH}/{DOC_KEY}"
DELETE_ON = {"book": BOOK, "capabilities": caps_with(delete_line=(True, None))}
CANCEL_ON = {"book": BOOK, "capabilities": caps_with(cancel_doc=(True, None))}
TRANSFERRED_LINE = "has already been delivered or copied to another document in AutoCount"


def D(value) -> Decimal:
    return Decimal(str(value))


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


def _qt_url(world) -> str:
    return f"{BASE}/quotation-documents/{world.document.id}/autocount"


def _qt_delete_path(dtl) -> str:
    return f"{QT_DOC_PATH}/lines/{dtl}/delete"


def _so_delete_path(dtl) -> str:
    return f"{SO_DOC_PATH}/lines/{dtl}/delete"


def _issue2(db, world):
    _mark_sent(db, world)
    issue2 = add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    return issue2


def _answer_qt(fake_ss, world, *, held_extra=(), patch=None, deletes=None):
    held = _read_back(world) + list(held_extra)
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=held))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = patch or (
        200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=held, last_modified="2026-11-10T09:00:00")
    )
    for dtl, answer in (deletes or {}).items():
        fake_ss.answers[("POST", _qt_delete_path(dtl))] = answer
    return held


def _deleted(doc_no="QT000777", doc_key=QT_KEY, last_modified="2026-11-10T09:05:00"):
    return (200, done_body(doc_no=doc_no, doc_key=doc_key, details=[], last_modified=last_modified))


# =========================================================================== quotation: added lines


def _add_new_line(db, world):
    from app.models.projects import ProjectQuotationLine

    p_new = _new_product(db, world)
    db.add(
        ProjectQuotationLine(
            id=str(__import__("uuid").uuid4()), company_id=world.company_id, version_id=world.version.id,
            product_id=p_new.id, product_code_snapshot=p_new.product_code, description_snapshot="New item",
            unit_price=Decimal("75.00"), quantity=Decimal("3"), uom="UNIT",
            line_total=Decimal("225.00"), sort_order=9,
        )
    )
    db.commit()
    return p_new


def test_a_new_row_goes_as_one_add_line_call_in_the_gateways_line_shape(qt_api, fake_ss):
    """Crew, SS 4193fdc4: the PATCH takes dtlKey >= 1 only (0 answers 422); a new row is
    `POST .../{docKey}/lines {companyCode, line{}}`, one per call."""
    client, db, world = qt_api
    issue2 = _issue2(db, world)
    p_new = _add_new_line(db, world)
    _answer_qt(fake_ss, world)
    fake_ss.answers[("POST", f"{QT_DOC_PATH}/lines")] = _deleted(last_modified="2026-11-10T09:01:00")

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "done", body
    [patch] = fake_ss.to("PATCH", QT_DOC_PATH)
    assert all(int(l["dtlKey"]) >= 1 for l in fake_ss.body(patch).get("lines", []))
    [post] = fake_ss.to("POST", f"{QT_DOC_PATH}/lines")
    sent = fake_ss.body(post)
    assert sent["companyCode"] == "SRT" and "lines" not in sent
    assert sent["line"]["itemCode"] == p_new.product_code and D(sent["line"]["qty"]) == 3
    assert post.headers["Idempotency-Key"].startswith(f"crm-qt-{world.document.id}-{issue2.id}-update-lines-")
    db.refresh(world.document)
    assert world.document.autocount_issue_id == issue2.id
    assert world.document.autocount_last_modified == "2026-11-10T09:01:00"


def test_a_refused_added_line_keeps_the_done_patch_and_the_retry_resends_only_that_line(qt_api, fake_ss):
    client, db, world = qt_api
    issue2 = _issue2(db, world)
    p_new = _add_new_line(db, world)
    _answer_qt(fake_ss, world)
    fake_ss.answers[("POST", f"{QT_DOC_PATH}/lines")] = (422, refused_body("ITEM_NOT_FOUND", "Item is not in AutoCount"))

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "refused"
    assert body["message"] == (
        f"The other changes were made. AutoCount refused the added line {p_new.product_code}: "
        "Item is not in AutoCount."
    )
    db.refresh(world.document)
    assert world.document.autocount_edit_issue_id == issue2.id
    assert world.document.autocount_issue_id != issue2.id

    fake_ss.answers[("POST", f"{QT_DOC_PATH}/lines")] = _deleted()
    assert client.post(_qt_url(world)).json()["outcome"] == "done"
    assert len(fake_ss.to("PATCH", QT_DOC_PATH)) == 1
    first, second = fake_ss.to("POST", f"{QT_DOC_PATH}/lines")
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]


# =========================================================================== quotation: remove line


def test_a_row_the_revision_no_longer_quotes_is_removed_when_delete_line_is_on(qt_api, fake_ss):
    client, db, world = qt_api
    issue2 = _issue2(db, world)
    fake_ss.answers[("GET", CAPS_PATH)] = (200, DELETE_ON)
    _answer_qt(
        fake_ss, world,
        held_extra=[detail(4, "ZZT-OLD-CODE", "1", "10.00", "BRW-BB", None, 4)],
        deletes={4: _deleted()},
    )

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "done", body
    assert body["waiting"] == []
    assert "ZZT-OLD-CODE" in body["message"], "the done note names the removed line"
    [delete] = fake_ss.to("POST", _qt_delete_path(4))
    assert delete.headers["Idempotency-Key"] == f"crm-qt-{world.document.id}-{issue2.id}-update-delete-4"
    assert fake_ss.body(delete)["companyCode"] == "SRT"
    writes = [r for r in fake_ss.writes() if r.method != "GET"]
    assert [r.method for r in writes] == ["PATCH", "POST"], "the edit goes first, then the removal"
    db.refresh(world.document)
    assert world.document.autocount_issue_id == issue2.id
    assert world.document.autocount_last_modified == "2026-11-10T09:05:00"


def test_with_delete_line_off_the_row_still_waits_and_nothing_is_removed(qt_api, fake_ss):
    client, db, world = qt_api
    issue2 = _issue2(db, world)
    _answer_qt(fake_ss, world, held_extra=[detail(4, "ZZT-OLD-CODE", "1", "10.00", "BRW-BB", None, 4)])

    body = client.post(_qt_url(world)).json()

    assert [w["reason"] for w in body["waiting"]] == [WAITING]
    assert fake_ss.to("POST", _qt_delete_path(4)) == []
    db.refresh(world.document)
    assert world.document.autocount_issue_id != issue2.id


def test_removing_every_line_is_allowed_on_an_update(qt_api, fake_ss):
    """Owner (10 Nov): removing the LAST line is allowed, no extra guards."""
    from app.models.projects import ProjectQuotationLine

    client, db, world = qt_api
    issue2 = _issue2(db, world)
    db.query(ProjectQuotationLine).filter(ProjectQuotationLine.version_id == world.version.id).delete()
    db.commit()
    fake_ss.answers[("GET", CAPS_PATH)] = (200, DELETE_ON)
    _answer_qt(fake_ss, world, deletes={1: _deleted(), 2: _deleted(), 3: _deleted()})

    response = client.post(_qt_url(world))

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "done", response.json()
    for dtl in (1, 2, 3):
        assert len(fake_ss.to("POST", _qt_delete_path(dtl))) == 1
    db.refresh(world.document)
    assert world.document.autocount_issue_id == issue2.id


def test_a_row_with_transfers_is_refused_in_plain_words_and_the_retry_skips_the_done_patch(qt_api, fake_ss):
    client, db, world = qt_api
    issue2 = _issue2(db, world)
    fake_ss.answers[("GET", CAPS_PATH)] = (200, DELETE_ON)
    _answer_qt(
        fake_ss, world,
        held_extra=[detail(4, "ZZT-OLD-CODE", "1", "10.00", "BRW-BB", None, 4)],
        deletes={4: (409, refused_body("ROW_HAS_TRANSFERS", "row 4 has transfers"))},
    )

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "refused"
    assert "ZZT-OLD-CODE" in body["message"] and TRANSFERRED_LINE in body["message"]
    assert "row 4 has transfers" not in body["message"], "the code is read, not SS's text"
    db.refresh(world.document)
    assert world.document.autocount_edit_issue_id == issue2.id
    assert world.document.autocount_issue_id != issue2.id

    _answer_qt(
        fake_ss, world,
        held_extra=[detail(4, "ZZT-OLD-CODE", "1", "10.00", "BRW-BB", None, 4)],
        deletes={4: _deleted()},
    )
    assert client.post(_qt_url(world)).json()["outcome"] == "done"
    assert len(fake_ss.to("PATCH", QT_DOC_PATH)) == 1, "the edit is done and not sent again"
    assert len(fake_ss.to("POST", _qt_delete_path(4))) == 2


def test_a_row_already_gone_counts_as_removed(qt_api, fake_ss):
    client, db, world = qt_api
    issue2 = _issue2(db, world)
    fake_ss.answers[("GET", CAPS_PATH)] = (200, DELETE_ON)
    _answer_qt(
        fake_ss, world,
        held_extra=[detail(4, "ZZT-OLD-CODE", "1", "10.00", "BRW-BB", None, 4)],
        deletes={4: (409, refused_body("ROW_NOT_FOUND", "no row 4"))},
    )

    assert client.post(_qt_url(world)).json()["outcome"] == "done"
    db.refresh(world.document)
    assert world.document.autocount_issue_id == issue2.id


# =========================================================================== sales order: CANCEL BALANCE


def _so_url(amendment) -> str:
    return f"{BASE}/sales-orders/amendments/{amendment.id}/autocount"


@pytest.mark.parametrize("to_qty", ["0", "2"])
def test_cancel_balance_sends_nothing_even_with_delete_line_on(so_api, fake_ss, to_qty):
    """Owner, 11 Nov ("cancel balance don't do much about it"): no AutoCount write for a CANCEL
    BALANCE row, whether it cuts the line to zero or lowers it; it waits, and the edits beside it
    still go."""
    client, db, world = so_api
    put_in_autocount(db, world)
    line3 = _third_line(db, world)
    amendment = add_amendment(
        db, world, [order_row(world, world.line1, "120"), cancel_balance_row(world, line3, to_qty)]
    )
    db.commit()
    fake_ss.answers[("GET", CAPS_PATH)] = (200, DELETE_ON)
    fake_ss.answers[("PATCH", SO_DOC_PATH)] = (200, done_body(last_modified="2026-11-11T10:00:00"))

    body = client.post(_so_url(amendment)).json()

    assert body["outcome"] == "done", body
    assert [(w["verb"], w["reason"]) for w in body["waiting"]] == [("CANCEL BALANCE", WAITING)]
    assert fake_ss.to("POST", _so_delete_path(DTL_3)) == []
    [patch] = fake_ss.to("PATCH", SO_DOC_PATH)
    assert [str(l["dtlKey"]) for l in fake_ss.body(patch)["lines"]] == [str(DTL_1)]
    assert all(str(DTL_3) not in r.content.decode() for r in fake_ss.writes())

    rows = client.get(f"{BASE}/amendments/{amendment.id}/autocount-change-list").json()["rows"]
    assert [(r["verb"], r["autocount_sendable"]) for r in rows] == [("ORDER", True), ("CANCEL BALANCE", False)]


# =========================================================================== codes in plain words


def _qt_cancel(db, world, fake_ss, answer):
    _mark_sent(db, world)
    fake_ss.answers[("GET", CAPS_PATH)] = (200, CANCEL_ON)
    fake_ss.answers[("POST", f"{QT_DOC_PATH}/cancel")] = answer


def _cancel_url(world) -> str:
    return f"{BASE}/quotation-documents/{world.document.id}/autocount/cancel"


def test_doc_has_transfers_on_cancel_reads_in_plain_words(qt_api, fake_ss):
    client, db, world = qt_api
    _qt_cancel(db, world, fake_ss, (409, refused_body("DOC_HAS_TRANSFERS", "QT has ToDocType SO")))

    body = client.post(_cancel_url(world)).json()

    assert body["outcome"] == "refused"
    assert body["message"] == (
        "AutoCount will not cancel it: it has already been delivered or copied to another document. "
        "Nothing was changed."
    )
    db.refresh(world.document)
    assert world.document.autocount_cancelled_at is None


def test_doc_cancelled_on_cancel_records_it_as_cancelled(qt_api, fake_ss):
    client, db, world = qt_api
    _qt_cancel(db, world, fake_ss, (409, refused_body("DOC_CANCELLED", "cancelled")))

    body = client.post(_cancel_url(world)).json()

    assert body["message"] == "Already cancelled in AutoCount."
    db.refresh(world.document)
    assert world.document.autocount_cancelled_at is not None


def test_doc_cancelled_on_an_update_reads_in_plain_words(qt_api, fake_ss):
    client, db, world = qt_api
    _issue2(db, world)
    _answer_qt(fake_ss, world, patch=(409, refused_body("DOC_CANCELLED", "cancelled")))

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "refused"
    assert body["message"] == "It is cancelled in AutoCount, so it cannot be changed. Nothing was changed."


def test_cancel_ignored_is_not_cancelled_and_says_so(qt_api, fake_ss):
    client, db, world = qt_api
    answer = refused_body("CANCEL_IGNORED", "Cancelled reads F", outcome="mismatch")
    _qt_cancel(db, world, fake_ss, (502, answer))

    body = client.post(_cancel_url(world)).json()

    assert body["outcome"] != "done"
    assert body["message"] == "AutoCount did not cancel it. Check it in AutoCount."
    db.refresh(world.document)
    assert world.document.autocount_cancelled_at is None


def test_an_existing_so_patch_key_and_body_shape_are_unchanged(so_api, fake_ss):
    """Regression guard: an edit-only amendment is still one PATCH with the stored stamp."""
    client, db, world = so_api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")])
    db.commit()
    fake_ss.answers[("PATCH", SO_DOC_PATH)] = (200, done_body(last_modified="2026-11-11T10:00:00"))

    client.post(_so_url(amendment))

    [patch] = fake_ss.to("PATCH", SO_DOC_PATH)
    assert fake_ss.body(patch)["expectedLastModified"] == LAST_MODIFIED
    assert patch.headers["Idempotency-Key"] == f"crm-amd-{amendment.id}-update-edit"



@pytest.mark.parametrize("code", ["SOME_NEW_CODE", None])
def test_a_refusal_with_no_message_never_shows_a_blank_reason(qt_api, fake_ss, code):
    """AC-E2E-DB3 B14 (11 Nov, db3): the dialog read "AutoCount refused: . Nothing was changed."
    A refusal SS sends with an empty message names its code, or says no reason was given."""
    client, db, world = qt_api
    _issue2(db, world)
    _answer_qt(fake_ss, world, patch=(409, refused_body(code, "")))

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "refused"
    assert "refused: ." not in body["message"]
    expected = f"AutoCount refused ({code}). Nothing was changed." if code else (
        "AutoCount refused with no reason given. Nothing was changed."
    )
    assert body["message"] == expected


def test_a_refused_write_is_logged_with_its_outcome_and_code(qt_api, fake_ss, caplog):
    import logging

    client, db, world = qt_api
    _issue2(db, world)
    _answer_qt(fake_ss, world, patch=(409, refused_body("DOC_STALE", "")))

    with caplog.at_level(logging.WARNING, logger="app.services.project_autocount_write_service"):
        client.post(_qt_url(world))

    line = " ".join(r.getMessage() for r in caplog.records)
    assert "outcome=refused" in line and "errorCode=DOC_STALE" in line


def test_a_styled_line_description_goes_to_autocount_as_plain_text(qt_api, fake_ss):
    """#2326 / #2329: a quotation line's description is stored as markup; AutoCount gets the plain
    reading (`project_quotation_service.line_text`), never the raw markup."""
    from app.models.projects import ProjectQuotationLine
    from tests.test_quotation_line_description_rich import PLAIN_SENTENCE, STYLED

    client, db, world = qt_api
    line = (
        db.query(ProjectQuotationLine)
        .filter(
            ProjectQuotationLine.version_id == world.version.id,
            ProjectQuotationLine.product_code_snapshot == world.p1.product_code,
        )
        .one()
    )
    line.description_snapshot = STYLED
    db.commit()
    fake_ss.answers[("POST", "/api/v1/autocount/documents/quotations")] = (
        200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=_read_back(world))
    )

    client.post(_qt_url(world))

    [create] = fake_ss.to("POST", "/api/v1/autocount/documents/quotations")
    [sent] = [l for l in fake_ss.body(create)["lines"] if l["itemCode"] == world.p1.product_code]
    assert sent["description"] == PLAIN_SENTENCE


# =========================================================================== B14: a key SS holds for an older body


def _conflict_on_base(base_suffix, then):
    """SS holds the base key for an older body (B14: a 6 Nov edit), so it answers
    IDEMPOTENCY_CONFLICT to it; any other key gets `then`."""

    def answer(request):
        if request.headers["Idempotency-Key"].endswith(base_suffix):
            return (409, refused_body("IDEMPOTENCY_CONFLICT", ""))
        return then

    return answer


def test_a_quotation_edit_whose_key_ss_holds_for_an_older_body_goes_under_a_fresh_key(qt_api, fake_ss):
    """AC-E2E-DB3 B14 (db3, 11 Nov): an edit sets absolute values, so it can be re-sent under a
    new key; without that every press answered IDEMPOTENCY_CONFLICT for good."""
    client, db, world = qt_api
    issue2 = _issue2(db, world)
    held = _answer_qt(fake_ss, world)
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = _conflict_on_base(
        "-update-edit",
        (200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=held, last_modified="2026-11-11T12:00:00")),
    )

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "done", body
    first, second = fake_ss.to("PATCH", QT_DOC_PATH)
    base = f"crm-qt-{world.document.id}-{issue2.id}-update-edit"
    assert first.headers["Idempotency-Key"] == base
    assert second.headers["Idempotency-Key"] == f"{base}-r"
    assert first.content == second.content
    db.refresh(world.document)
    assert world.document.autocount_issue_id == issue2.id


def test_a_sales_order_edit_whose_key_ss_holds_for_an_older_body_goes_under_a_fresh_key(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    amendment = add_amendment(db, world, [order_row(world, world.line1, "120")])
    db.commit()
    fake_ss.answers[("PATCH", SO_DOC_PATH)] = _conflict_on_base(
        "-update-edit", (200, done_body(last_modified="2026-11-11T12:00:00"))
    )

    body = client.post(f"{BASE}/sales-orders/amendments/{amendment.id}/autocount").json()

    assert body["outcome"] == "done", body
    keys = [r.headers["Idempotency-Key"] for r in fake_ss.to("PATCH", SO_DOC_PATH)]
    assert keys == [f"crm-amd-{amendment.id}-update-edit", f"crm-amd-{amendment.id}-update-edit-r"]


def test_a_create_whose_key_ss_holds_is_never_re_sent_under_another_key(qt_api, fake_ss):
    """A create could land twice under a new key, so a conflict on it stays a refusal."""
    client, _db, world = qt_api
    fake_ss.answers[("POST", "/api/v1/autocount/documents/quotations")] = (
        409, refused_body("IDEMPOTENCY_CONFLICT", "")
    )

    body = client.post(_qt_url(world)).json()

    assert body["outcome"] == "refused"
    assert len(fake_ss.to("POST", "/api/v1/autocount/documents/quotations")) == 1


# =========================================================================== B15: AutoCount's own refusal of a create


@pytest.fixture
def attempts(monkeypatch):
    from app.services import project_autocount_write_service as svc
    from tests.test_project_autocount_idem_keys import DictStore

    s = DictStore()
    monkeypatch.setattr(svc, "attempt_store", lambda: s)
    return s


def test_a_create_autocount_refused_goes_under_a_new_key_after_the_fix(qt_api, fake_ss, attempts):
    """AC-E2E-DB3 B15 (db3, 11 Nov): AutoCount refused a create (vendor_error / VENDOR_REFUSED,
    a unit not in its master file), the unit was fixed, and every later press answered
    IDEMPOTENCY_CONFLICT. VENDOR_REFUSED is AutoCount saying no with nothing written (SS plan 57),
    so the next press takes a new attempt key."""
    from app.services.autocount_idempotency import attempt_key

    client, db, world = qt_api
    path = "/api/v1/autocount/documents/quotations"
    refused = refused_body("VENDOR_REFUSED", "itemCode and uom do not exist in its master file", outcome="vendor_error")
    fake_ss.answers[("POST", path)] = (502, refused)
    first = client.post(_qt_url(world)).json()
    assert first["outcome"] != "done"

    fake_ss.answers[("POST", path)] = (200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=_read_back(world)))
    second = client.post(_qt_url(world)).json()

    assert second["outcome"] == "done", second
    base = f"crm-qt-{world.document.id}-{world.issue.id}-create"
    keys = [r.headers["Idempotency-Key"] for r in fake_ss.to("POST", path)]
    assert keys == [base, attempt_key(base, 1)]


def test_a_bare_vendor_error_keeps_the_key(qt_api, fake_ss, attempts):
    """VENDOR_ERROR is a failure with no text: it may have landed, so a retry only replays."""
    client, db, world = qt_api
    path = "/api/v1/autocount/documents/quotations"
    fake_ss.answers[("POST", path)] = (502, refused_body("VENDOR_ERROR", "", outcome="vendor_error"))
    client.post(_qt_url(world))
    client.post(_qt_url(world))

    keys = [r.headers["Idempotency-Key"] for r in fake_ss.to("POST", path)]
    assert len(set(keys)) == 1, keys
