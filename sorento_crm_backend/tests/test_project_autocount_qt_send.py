"""AC-QTSO-CRM Phase 2, RED: send a project quotation to AutoCount (create, then update).

UAC U15, U16, U17, R5, R6. Route: `POST /api/v1/project-sales/quotation-documents/{document_id}/autocount`.

Plan, "Routes": the document must be `kind = quotation` and its LATEST issue must carry
`accepted_at`, else 409 "The customer has not accepted this quotation yet."; nothing new to send
(the latest accepted issue is the one last sent) -> 409 "Already in AutoCount.".
`send_quotation` creates when the document has no `autocount_doc_key`, else updates.
Idempotency-Key: `crm-qt-{document_id}-{issue_id}-create|update`.

R6 lines (rate-only skipped, sets exploded) are pinned at builder level by
`tests/test_project_autocount_qt_payload.py`; here they are pinned on the wire and in the result
note. The quotation has no order to derive a location from, so the location is the recipient
customer's derived one (agent group BB -> BRW-BB); that reading of the plan is flagged in the report.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from tests._ac_write_support import (
    BOOK,
    BASE,
    QT_CREATE_PATH,
    EDIT,
    VIEW,
    WRITE,
    WAITING,
    add_issue,
    api_fixture,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    find_dicts,
    myt_today_candidates,
    refused_body,
)

QT_KEY = 5001
QT_DOC_PATH = f"{QT_CREATE_PATH}/{QT_KEY}"
NOT_ACCEPTED = "The customer has not accepted this quotation yet."
ALREADY = "Already in AutoCount."


def D(value) -> Decimal:
    return Decimal(str(value))


@pytest.fixture
def api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def api_unaccepted(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True, accepted=False)


@pytest.fixture
def api_proposal(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True, kind="proposal")


@pytest.fixture
def api_blank_debtor(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True, debtor_code="  ")


def _url(world) -> str:
    return f"{BASE}/quotation-documents/{world.document.id}/autocount"


def _read_back(world):
    return [
        detail(1, world.p1.product_code, "10", "180.00", "BRW-BB", None, 1),
        detail(2, world.p_wc.product_code, "2", "950.00", "BRW-BB", None, 2),
        detail(3, world.p_av.product_code, "4", "0.00", "BRW-BB", None, 3),
    ]


def _created(world, **kw):
    return done_body(doc_no="QT000777", doc_key=QT_KEY, details=_read_back(world), **kw)


def _mark_sent(db, world, issue=None):
    world.document.autocount_doc_no = "QT000777"
    world.document.autocount_doc_key = str(QT_KEY)
    world.document.autocount_last_modified = "2026-10-21T08:00:00"
    world.document.autocount_issue_id = (issue or world.issue).id
    world.document.autocount_book = BOOK
    db.commit()


# --------------------------------------------------------------------------- U15: only an accepted quotation


def test_a_quotation_not_yet_accepted_gets_409_with_the_exact_message_and_no_call(api_unaccepted, fake_ss):
    client, _db, world = api_unaccepted

    response = client.post(_url(world))

    assert response.status_code == 409, response.text
    assert response.json()["message"] == NOT_ACCEPTED
    assert fake_ss.calls == []


def test_a_proposal_never_goes_even_when_its_issue_is_accepted(api_proposal, fake_ss):
    client, _db, world = api_proposal

    response = client.post(_url(world))

    assert response.status_code == 409, response.text
    assert fake_ss.calls == []


def test_a_newer_unaccepted_revision_blocks_the_send(api, fake_ss):
    """The LATEST issue decides: R1 accepted, R2 issued but not yet accepted -> not accepted yet."""
    client, db, world = api
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=False)
    db.commit()

    response = client.post(_url(world))

    assert response.status_code == 409, response.text
    assert response.json()["message"] == NOT_ACCEPTED
    assert fake_ss.calls == []


def test_an_unknown_document_is_an_application_404(api, fake_ss):
    import uuid

    client, _db, _world = api

    response = client.post(f"{BASE}/quotation-documents/{uuid.uuid4()}/autocount")

    assert response.status_code == 404
    assert response.json().get("code"), response.text
    assert fake_ss.calls == []


def test_a_missing_debtor_code_is_refused_naming_the_customer_with_no_call(api_blank_debtor, fake_ss):
    client, _db, world = api_blank_debtor

    response = client.post(_url(world))

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "ac_missing_debtor"
    assert response.json()["message"] == f"No debtor code on {world.customer.customer_name}."
    assert fake_ss.calls == []


# --------------------------------------------------------------------------- create


def test_an_accepted_quotation_creates_with_the_header_and_the_r6_lines(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, _created(world))

    response = client.post(_url(world))

    assert response.status_code == 200, response.text
    [request] = fake_ss.to("POST", QT_CREATE_PATH)
    body = fake_ss.body(request)
    header = body["header"]
    assert body["companyCode"] == "SRT"
    assert header["debtorCode"] == world.customer.customer_code == "ZZT-DEBT-QT"
    assert header["docDate"] in myt_today_candidates()
    assert header["currencyCode"] == "MYR" and D(header["currencyRate"]) == 1
    assert header["yourPONo"] == "YR-QT-77"
    assert header["ref"] == world.project.title
    assert header["salesAgent"] == world.agent.sales_agent
    assert header["remark1"] == f"{world.document.document_no} (R1)"
    # Free-text payment terms cannot become "Net N days": the quotation sends none.
    assert not header.get("displayTerm")

    lines = body["lines"]
    assert [l["itemCode"] for l in lines] == [
        world.p1.product_code, world.p_wc.product_code, world.p_av.product_code,
    ]
    assert [D(l["qty"]) for l in lines] == [D(10), D(2), D(4)]
    assert [D(l["unitPrice"]) for l in lines] == [D("180.00"), D("950.00"), D(0)]
    assert {l["location"] for l in lines} == {"BRW-BB"}
    assert world.pset.set_code not in [l["itemCode"] for l in lines]
    assert world.p_alt.product_code not in [l["itemCode"] for l in lines]


def test_the_idempotency_key_names_the_document_and_the_issue(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, _created(world))

    client.post(_url(world))

    [request] = fake_ss.to("POST", QT_CREATE_PATH)
    assert request.headers["Idempotency-Key"] == f"crm-qt-{world.document.id}-{world.issue.id}-create"


def test_the_result_note_names_the_skipped_line_and_the_exploded_set(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, _created(world))

    body = client.post(_url(world)).json()

    assert body["outcome"] == "done"
    assert body["doc_no"] == "QT000777"
    assert [s["code"] for s in body["skipped"]] == [world.p_alt.product_code]
    [exploded] = body["exploded"]
    assert exploded["code"] == world.pset.set_code
    assert [(c["code"], D(c["qty"])) for c in exploded["components"]] == [
        (world.p_wc.product_code, D(2)),
        (world.p_av.product_code, D(4)),
    ]
    assert [l["item_code"] for l in body["lines"]] == [
        world.p1.product_code, world.p_wc.product_code, world.p_av.product_code,
    ]


def test_done_writes_the_number_key_last_modified_and_the_issue_sent(api, fake_ss):
    client, db, world = api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, _created(world, last_modified="2026-11-05T12:00:00"))

    client.post(_url(world))

    db.refresh(world.document)
    assert world.document.autocount_doc_no == "QT000777"
    assert world.document.autocount_doc_key == str(QT_KEY)
    assert world.document.autocount_last_modified == "2026-11-05T12:00:00"
    assert world.document.autocount_issue_id == world.issue.id


def test_a_refusal_writes_nothing_to_the_quotation(api, fake_ss):
    client, db, world = api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (422, refused_body("ITEM_NOT_FOUND", "Item ZZT is not in AutoCount"))

    body = client.post(_url(world)).json()

    assert body["outcome"] == "refused"
    assert body["message"] == "AutoCount refused: Item ZZT is not in AutoCount. Nothing was changed."
    db.refresh(world.document)
    assert world.document.autocount_doc_no is None
    assert world.document.autocount_doc_key is None
    assert world.document.autocount_issue_id is None


# --------------------------------------------------------------------------- U17: a later revision updates


def test_the_same_issue_again_is_409_already_in_autocount_with_no_call(api, fake_ss):
    client, db, world = api
    _mark_sent(db, world)

    response = client.post(_url(world))

    assert response.status_code == 409, response.text
    assert response.json()["message"] == ALREADY
    assert fake_ss.calls == []


def test_a_later_accepted_issue_updates_the_document_already_in_autocount(api, fake_ss):
    client, db, world = api
    _mark_sent(db, world)
    issue2 = add_issue(
        db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True
    )
    db.commit()
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, _created(world))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (
        200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=_read_back(world),
                       last_modified="2026-11-06T09:00:00")
    )

    response = client.post(_url(world))

    assert response.status_code == 200, response.text
    assert fake_ss.to("POST", QT_CREATE_PATH) == [], "an existing document is updated, never created twice"
    [patch] = fake_ss.to("PATCH", QT_DOC_PATH)
    body = fake_ss.body(patch)
    assert body["companyCode"] == "SRT"
    assert "docDate" not in body and "docDate" not in body["header"]
    assert body["expectedLastModified"] == "2026-10-21T08:00:00"
    assert patch.headers["Idempotency-Key"] == f"crm-qt-{world.document.id}-{issue2.id}-update-edit"
    db.refresh(world.document)
    assert world.document.autocount_issue_id == issue2.id
    assert world.document.autocount_last_modified == "2026-11-06T09:00:00"


def test_a_stale_quotation_update_keeps_autocounts_stamp_for_the_next_press(api, fake_ss):
    """B10: the document read just before the PATCH carries AutoCount's own LastModified; a
    DOC_STALE keeps it, so the next press is not refused for good."""
    client, db, world = api
    _mark_sent(db, world)
    issue2 = add_issue(
        db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True
    )
    db.commit()
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, _created(world, last_modified="2026-11-06T18:04:00"))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (409, refused_body("DOC_STALE", "changed"))

    body = client.post(_url(world)).json()

    assert body["outcome"] == "refused"
    assert body["message"] == (
        "Changed in AutoCount since 21/10/2026. Nothing was changed; "
        "check it in AutoCount, then press Update again."
    )
    assert len(fake_ss.to("GET", QT_DOC_PATH)) == 1, "the read before the PATCH is reused"
    db.refresh(world.document)
    assert world.document.autocount_last_modified == "2026-11-06T18:04:00"
    assert world.document.autocount_edit_issue_id != issue2.id

    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (200, _created(world, last_modified="2026-11-07T09:00:00"))
    second = client.post(_url(world)).json()

    assert second["outcome"] == "done", second
    patches = fake_ss.to("PATCH", QT_DOC_PATH)
    assert fake_ss.body(patches[-1])["expectedLastModified"] == "2026-11-06T18:04:00"
    db.refresh(world.document)
    assert world.document.autocount_last_modified == "2026-11-07T09:00:00"


def test_a_quotation_refusal_other_than_doc_stale_keeps_the_stored_stamp(api, fake_ss):
    client, db, world = api
    _mark_sent(db, world)
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, _created(world, last_modified="2026-11-06T18:04:00"))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (409, refused_body("FIELD_REQUIRED", "x"))

    assert client.post(_url(world)).json()["outcome"] == "refused"

    db.refresh(world.document)
    assert world.document.autocount_last_modified == "2026-10-21T08:00:00"


# --------------------------------------------------------------------------- U17: how an update matches lines


def test_an_update_matches_lines_by_item_code_in_order(api, fake_ss):
    """Coordinator ruling (Q8): quotation lines are matched to the AutoCount document by itemCode.

    * a matched line whose qty or price changed goes in the PATCH (by its dtlKey);
    * a matched line that did not change is not sent;
    * a new item code goes to POST lines;
    * a code AutoCount holds that the new revision no longer quotes goes to `waiting`
      (there is no delete_line), and is never deleted.

    The CRM learns what AutoCount holds from a GET of the document (path assumed to be
    `GET /documents/quotations/{docKey}` answering the usual `document` envelope).
    """
    from app.models.projects import ProjectQuotationLine

    client, db, world = api
    _mark_sent(db, world)
    p_new = _new_product(db, world)
    lines = {
        l.product_code_snapshot: l
        for l in db.query(ProjectQuotationLine).filter(ProjectQuotationLine.version_id == world.version.id)
    }
    lines[world.p1.product_code].quantity = Decimal("12")           # qty 10 -> 12: PATCH
    db.add(
        ProjectQuotationLine(
            id=str(__import__("uuid").uuid4()), company_id=world.company_id, version_id=world.version.id,
            product_id=p_new.id, product_code_snapshot=p_new.product_code, description_snapshot="New item",
            unit_price=Decimal("75.00"), quantity=Decimal("3"), uom="UNIT",
            line_total=Decimal("225.00"), sort_order=9,
        )
    )
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()

    held = _read_back(world) + [detail(4, "ZZT-OLD-CODE", "1", "10.00", "BRW-BB", None, 4)]
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=held))
    after = held + [detail(5, p_new.product_code, "3", "75.00", "BRW-BB", None, 5)]
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (200, done_body(doc_key=QT_KEY, details=after))
    fake_ss.answers[("POST", f"{QT_DOC_PATH}/lines")] = (200, done_body(doc_key=QT_KEY, details=after))

    body = client.post(_url(world)).json()

    [patch] = fake_ss.to("PATCH", QT_DOC_PATH)
    patched = fake_ss.body(patch)["lines"]
    assert [(str(l["dtlKey"]), D(l["qty"])) for l in patched] == [("1", D(12))], (
        "only the matched line that changed rides the PATCH"
    )
    [post] = fake_ss.to("POST", f"{QT_DOC_PATH}/lines")
    assert find_dicts(fake_ss.body(post), itemCode=p_new.product_code, qty="3"), fake_ss.body(post)
    assert "ZZT-OLD-CODE" in str(body["waiting"])
    assert WAITING in str(body["waiting"])
    assert all("ZZT-OLD-CODE" not in r.content.decode() for r in fake_ss.writes())
    assert [r for r in fake_ss.calls if r.method == "DELETE"] == []


def _new_product(db, world):
    from tests.test_project_so_draft import _product, _uid

    return _product(db, f"ZZT-NEW-{_uid()[:6]}")


# --------------------------------------------------------------------------- fix round 1: steps, retry, waiting


def _second_issue_with_new_item(db, world):
    """R2 accepted on top of an R1 already in AutoCount; R2 adds one new item code."""
    from app.models.projects import ProjectQuotationLine

    _mark_sent(db, world)
    p_new = _new_product(db, world)
    db.add(
        ProjectQuotationLine(
            id=str(__import__("uuid").uuid4()), company_id=world.company_id, version_id=world.version.id,
            product_id=p_new.id, product_code_snapshot=p_new.product_code, description_snapshot="New item",
            unit_price=Decimal("75.00"), quantity=Decimal("3"), uom="UNIT",
            line_total=Decimal("225.00"), sort_order=9,
        )
    )
    issue2 = add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    return issue2, p_new


def _answer_update(fake_ss, world, *, post=None, held_extra=()):
    held = _read_back(world) + list(held_extra)
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=held))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = (
        200, done_body(doc_key=QT_KEY, details=held, last_modified="2026-11-06T09:00:00")
    )
    fake_ss.answers[("POST", f"{QT_DOC_PATH}/lines")] = post or (
        200, done_body(doc_key=QT_KEY, details=held, last_modified="2026-11-06T09:05:00")
    )


def test_a_partial_update_says_what_was_made_and_never_nothing_was_changed(api, fake_ss):
    client, db, world = api
    issue2, _p = _second_issue_with_new_item(db, world)
    _answer_update(fake_ss, world, post=(422, refused_body("ITEM_NOT_FOUND", "Item is not in AutoCount")))

    body = client.post(_url(world)).json()

    assert body["outcome"] == "refused"
    assert body["message"].startswith("The other changes were made. AutoCount refused the added line ")
    assert body["message"].endswith(": Item is not in AutoCount.")
    assert "Nothing was changed" not in body["message"]
    db.refresh(world.document)
    assert world.document.autocount_edit_issue_id == issue2.id
    assert world.document.autocount_lines_issue_id is None
    assert world.document.autocount_issue_id != issue2.id
    assert world.document.autocount_last_modified == "2026-11-06T09:00:00"


def test_a_retry_after_a_partial_sends_only_the_remaining_step_with_the_same_key(api, fake_ss):
    client, db, world = api
    issue2, p_new = _second_issue_with_new_item(db, world)
    _answer_update(fake_ss, world, post=(422, refused_body("ITEM_NOT_FOUND", "Item is not in AutoCount")))
    client.post(_url(world))
    _answer_update(fake_ss, world)

    body = client.post(_url(world)).json()

    assert body["outcome"] == "done"
    assert len(fake_ss.to("PATCH", QT_DOC_PATH)) == 1, "the PATCH step is done and is not sent again"
    first, second = fake_ss.to("POST", f"{QT_DOC_PATH}/lines")
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert first.headers["Idempotency-Key"] == f"crm-qt-{world.document.id}-{issue2.id}-update-lines-3"
    assert first.content == second.content
    db.refresh(world.document)
    assert world.document.autocount_issue_id == issue2.id


def test_a_stale_add_lines_step_alone_keeps_the_read_stamp_for_the_next_press(api, fake_ss):
    """B10, add-lines step: the header went on an earlier press, so the read before this press
    is the newest stamp the CRM holds; a DOC_STALE keeps it and the next press sends it."""
    client, db, world = api
    issue2, _p = _second_issue_with_new_item(db, world)
    world.document.autocount_edit_issue_id = issue2.id
    db.commit()
    _answer_update(fake_ss, world, post=(409, refused_body("DOC_STALE", "changed")))
    held = _read_back(world)
    fake_ss.answers[("GET", QT_DOC_PATH)] = (
        200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=held, last_modified="2026-11-06T18:04:00")
    )

    body = client.post(_url(world)).json()

    assert body["outcome"] == "refused"
    assert fake_ss.to("PATCH", QT_DOC_PATH) == []
    db.refresh(world.document)
    assert world.document.autocount_last_modified == "2026-11-06T18:04:00"

    fake_ss.answers[("POST", f"{QT_DOC_PATH}/lines")] = (
        200, done_body(doc_key=QT_KEY, details=held, last_modified="2026-11-07T09:00:00")
    )
    second = client.post(_url(world)).json()

    assert second["outcome"] == "done", second
    posts = fake_ss.to("POST", f"{QT_DOC_PATH}/lines")
    assert fake_ss.body(posts[0])["expectedLastModified"] == "2026-10-21T08:00:00"
    assert fake_ss.body(posts[-1])["expectedLastModified"] == "2026-11-06T18:04:00"


def test_a_stale_add_lines_step_after_a_done_patch_keeps_the_patch_stamp(api, fake_ss):
    """The PATCH answered this press with a newer stamp than the read before it: that stamp
    stays, the older read never replaces it."""
    client, db, world = api
    _issue2, _p = _second_issue_with_new_item(db, world)
    _answer_update(fake_ss, world, post=(409, refused_body("DOC_STALE", "changed")))
    held = _read_back(world)
    fake_ss.answers[("GET", QT_DOC_PATH)] = (
        200, done_body(doc_no="QT000777", doc_key=QT_KEY, details=held, last_modified="2026-11-06T08:00:00")
    )

    body = client.post(_url(world)).json()

    assert body["outcome"] == "refused"
    assert len(fake_ss.to("PATCH", QT_DOC_PATH)) == 1
    db.refresh(world.document)
    assert world.document.autocount_last_modified == "2026-11-06T09:00:00"


# --------------------------------------------------------------------------- B11: fields AutoCount ignored


def _ignored_answer(world, message, code="FIELD_IGNORED"):
    body = done_body(
        doc_no="QT000777", doc_key=QT_KEY, details=_read_back(world), last_modified="2026-11-06T18:08:00"
    )
    body.update({"outcome": "mismatch", "errorCode": code, "message": message})
    return (502, body)


def _issue2_sent_with_patch_answer(db, world, fake_ss, answer):
    _mark_sent(db, world)
    issue2 = add_issue(
        db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True
    )
    db.commit()
    fake_ss.answers[("GET", QT_DOC_PATH)] = (200, _created(world))
    fake_ss.answers[("PATCH", QT_DOC_PATH)] = answer
    return issue2


def test_fields_we_did_not_send_ignored_by_autocount_still_count_as_updated(api, fake_ss):
    """B11 (db3, QT-000006): SS echoes Remark2-4 and AutoCount mirrors Remark1 into them, so
    SS answers mismatch FIELD_IGNORED on fields this call never asked to change."""
    client, db, world = api
    issue2 = _issue2_sent_with_patch_answer(
        db, world, fake_ss, _ignored_answer(world, "ignored: Remark2, Remark3, Remark4")
    )

    body = client.post(_url(world)).json()

    assert body["outcome"] == "done", body
    assert body["message"] == "QT000777 updated in AutoCount"
    db.refresh(world.document)
    assert world.document.autocount_edit_issue_id == issue2.id
    assert world.document.autocount_issue_id == issue2.id
    assert world.document.autocount_last_modified == "2026-11-06T18:08:00"

    calls = len(fake_ss.calls)
    again = client.post(_url(world))
    assert again.status_code == 409 and again.json()["message"] == ALREADY
    assert len(fake_ss.calls) == calls


def test_a_field_we_sent_being_ignored_is_not_updated(api, fake_ss):
    client, db, world = api
    issue2 = _issue2_sent_with_patch_answer(
        db, world, fake_ss, _ignored_answer(world, "ignored: Remark1, Remark2")
    )

    body = client.post(_url(world)).json()

    assert body["outcome"] != "done"
    db.refresh(world.document)
    assert world.document.autocount_edit_issue_id != issue2.id
    assert world.document.autocount_issue_id != issue2.id
    assert world.document.autocount_last_modified == "2026-10-21T08:00:00"


@pytest.mark.parametrize(
    "message,code",
    [
        ("ignored:", "FIELD_IGNORED"),                       # no names: cannot tell, not done
        ("Qty differs after write", "FIELD_IGNORED"),        # no "ignored:" list
        ("ignored: Remark2", "VALUE_MISMATCH"),               # another mismatch code
        # B11 review: only the measured Remark2-4 mirror counts; any other name stays a mismatch.
        ("ignored: Remark2, Details[0].Qty", "FIELD_IGNORED"),
        ("ignored: Remark2, lines[0].qty", "FIELD_IGNORED"),
        ("ignored: Remark2, Unit Price", "FIELD_IGNORED"),
        ("ignored: Remark2 and Qty", "FIELD_IGNORED"),
        ("ignored: Remark2, DocDate", "FIELD_IGNORED"),
        ("ignored: Remark1 (QT-2026-0001 (R2)), Remark2", "FIELD_IGNORED"),
        ("Remark1, Remark2 ignored: Remark3", "FIELD_IGNORED"),
        ("ignored: Remark2, Remark3, Remark4, Remark5", "FIELD_IGNORED"),
    ],
)
def test_any_other_mismatch_is_not_updated(api, fake_ss, message, code):
    client, db, world = api
    issue2 = _issue2_sent_with_patch_answer(db, world, fake_ss, _ignored_answer(world, message, code))

    assert client.post(_url(world)).json()["outcome"] != "done"
    db.refresh(world.document)
    assert world.document.autocount_issue_id != issue2.id


def test_a_press_after_a_complete_update_is_409_already_with_no_call(api, fake_ss):
    client, db, world = api
    _second_issue_with_new_item(db, world)
    _answer_update(fake_ss, world)
    assert client.post(_url(world)).status_code == 200
    calls = len(fake_ss.calls)

    again = client.post(_url(world))

    assert again.status_code == 409 and again.json()["message"] == ALREADY
    assert len(fake_ss.calls) == calls


def test_waiting_rows_keep_the_issue_unsent_so_needs_update_stays_true(api, fake_ss):
    client, db, world = api
    _mark_sent(db, world)
    issue2 = add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    _answer_update(fake_ss, world, held_extra=[detail(4, "ZZT-OLD-CODE", "1", "10.00", "BRW-BB", None, 4)])

    body = client.post(_url(world)).json()

    assert body["outcome"] == "done" and "ZZT-OLD-CODE" in str(body["waiting"])
    db.refresh(world.document)
    assert world.document.autocount_issue_id != issue2.id, "needs-update must stay true while rows wait"
    assert world.document.autocount_edit_issue_id == issue2.id


def test_a_second_press_with_only_waiting_rows_left_makes_no_write_call(api, fake_ss):
    client, db, world = api
    _mark_sent(db, world)
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()
    _answer_update(fake_ss, world, held_extra=[detail(4, "ZZT-OLD-CODE", "1", "10.00", "BRW-BB", None, 4)])
    client.post(_url(world))
    def sent():
        return [r for r in fake_ss.writes() if r.method != "GET"]

    writes = len(sent())

    body = client.post(_url(world)).json()

    assert len(sent()) == writes, "no line edits and no header change: no PATCH"
    assert "ZZT-OLD-CODE" in str(body["waiting"])


def test_a_recovered_answer_writes_nothing_to_the_quotation(api, fake_ss):
    client, db, world = api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, {**_created(world), "outcome": "recovered"})

    body = client.post(_url(world)).json()

    assert body["outcome"] != "done"
    db.refresh(world.document)
    assert world.document.autocount_doc_key is None and world.document.autocount_issue_id is None


def test_a_bad_doc_key_never_reaches_a_path(api, fake_ss):
    client, db, world = api
    _mark_sent(db, world)
    world.document.autocount_doc_key = "5001/../x"
    add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()

    response = client.post(_url(world))

    assert response.status_code == 409
    assert fake_ss.calls == []


def test_ss_messages_are_capped_at_500_characters(api, fake_ss):
    client, _db, world = api
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (422, refused_body("X", "y" * 900))

    body = client.post(_url(world)).json()

    assert len(body["message"]) < 600
