"""PS-QUOTE-MATRIX customer feedback: notes per item or per cell, handled by staff, never applied.

Written BEFORE the implementation (Phase 2, test-first). Contract section "Customer feedback" of
``documentation/plans/project-sales/PLAN-ps-quote-matrix-02nov.md``. It replaces Accept / Reject /
Apply (``test_quotation_amendment.py``) for every quotation.

World: ``grid_world`` from ``test_quote_matrix_service.py``, signed and issued:

    UNIT (grid)  trap   45.00  ta_bh 120, ta_kit 120, tb_bh 500, tb_kit 250   (quantity 990)
                 sink  100.00  ta_bh 2                                         (quantity 2)
    GUARD HOUSE  plain  80.00  quantity 5
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ._pg_fixture import blank_session
from .test_quote_matrix_service import BASE, COLUMNS, MARKER, grid_world

PUBLIC = "/api/v1/public/quotation-sign"
SIGNATURE = "data:image/png;base64,zzt-strokes"
CUSTOMER = f"{MARKER} Kelly"


# ------------------------------------------------------------------ fixture


@pytest.fixture()
def fb(monkeypatch):
    """One TestClient for the customer link and the staff routes, on a signed, issued world."""
    from app.models.base import company_scope
    from app.services import project_quotation_document_service as qdocs
    from app.services import rate_limit

    from .test_project_quotation_approval_routes import _client, _restore

    monkeypatch.setattr(
        rate_limit, "hit", lambda bucket, ident, *, limit, window_seconds: rate_limit.RateResult(allowed=True)
    )
    with blank_session() as db:
        w = grid_world(db)
        token = qdocs.issue_sign_link(db, record=w.record)
        db.commit()
        client, originals = _client(db, w.owner)
        try:
            with company_scope(db, frozenset({w.company_id})):
                yield SimpleNamespace(client=client, db=db, w=w, token=token)
        finally:
            _restore(originals)


def _send(fb, items, **extra):
    body = {"items": items, **extra}
    return fb.client.post(f"{PUBLIC}/{fb.token}/amendment-request", json=body)


def _item(line, kind, **fields):
    return {"line_id": str(line.id), "kind": kind, **fields}


def _root(fb):
    return f"{BASE}/projects/{fb.w.project.id}/quotation-documents/{fb.w.document.id}"


def _rows(fb):
    from app.models.projects import QuotationAmendmentRequestRow

    fb.db.expire_all()
    return fb.db.query(QuotationAmendmentRequestRow).all()


def _row(fb, line, field, cell_key=None):
    found = [
        r
        for r in _rows(fb)
        if str(r.line_id) == str(line.id) and r.field == field and (r.cell_key or None) == cell_key
    ]
    assert len(found) == 1, (field, cell_key, [(r.field, r.cell_key) for r in _rows(fb)])
    return found[0]


def _snapshot(fb):
    from app.models.projects import ProjectQuotationLine, ProjectQuotationVersion

    fb.db.expire_all()
    lines = sorted(
        (
            str(line.id),
            Decimal(line.quantity),
            Decimal(line.unit_price),
            Decimal(line.line_total),
            line.qty_cells,
        )
        for line in fb.db.query(ProjectQuotationLine).all()
    )
    versions = sorted(
        (str(v.id), Decimal(v.total_amount), v.matrix_columns)
        for v in fb.db.query(ProjectQuotationVersion).all()
    )
    return lines, versions


def _count_requests(fb) -> int:
    from app.models.projects import QuotationAmendmentRequest

    fb.db.expire_all()
    return fb.db.query(QuotationAmendmentRequest).count()


# ------------------------------------------------------------------ public POST: every kind stored


def test_items_of_every_kind_are_stored_with_field_cell_values_hint_and_note(fb):
    w = fb.w
    items = [
        _item(w.trap, "note", note="Check the rate with site."),
        _item(w.sink, "note", cell_key="ta_bh", note="Needs 140 here."),
        _item(w.trap, "quantity", cell_key="ta_kit", value="140", note="more please"),
        _item(w.plain, "quantity", value="6"),
        _item(w.sink, "unit_price", value="90.00"),
        _item(w.plain, "remove"),
        _item(w.trap, "model_swap", model="Alt Model 77", value="55.00", note="cheaper one"),
    ]
    response = _send(fb, items, requester_name=CUSTOMER, note="General remark.")
    assert response.status_code == 200, response.text
    assert len(_rows(fb)) == 7

    note_item = _row(fb, w.trap, "note")
    assert note_item.note == "Check the rate with site."
    assert note_item.value_from is None and note_item.value_to is None and note_item.hint_text is None

    note_cell = _row(fb, w.sink, "note", "ta_bh")
    assert note_cell.note == "Needs 140 here."

    qty_cell = _row(fb, w.trap, "quantity", "ta_kit")
    assert Decimal(qty_cell.value_from) == Decimal("120.00")  # today's value of that cell
    assert Decimal(qty_cell.value_to) == Decimal("140.00")
    assert qty_cell.note == "more please"

    qty_line = _row(fb, w.plain, "quantity")
    assert qty_line.cell_key is None
    assert Decimal(qty_line.value_from) == Decimal("5")  # today's line quantity
    assert Decimal(qty_line.value_to) == Decimal("6.00")

    price = _row(fb, w.sink, "unit_price")
    assert Decimal(price.value_from) == Decimal("100.00")
    assert Decimal(price.value_to) == Decimal("90.00")

    remove = _row(fb, w.plain, "remove")
    assert remove.value_from is None and remove.value_to is None

    swap = _row(fb, w.trap, "model_swap")
    assert swap.hint_text == "Alt Model 77"
    assert Decimal(swap.value_to) == Decimal("55.00")
    assert swap.value_from is None
    assert swap.note == "cheaper one"


def test_a_cell_with_no_value_in_it_yet_has_value_from_zero_or_null(fb):
    response = _send(fb, [_item(fb.w.sink, "quantity", cell_key="tb_kit", value="3")])
    assert response.status_code == 200, response.text
    row = _row(fb, fb.w.sink, "quantity", "tb_kit")
    assert row.value_from is None or Decimal(row.value_from) == Decimal("0")


def test_the_requester_and_the_top_level_note_land_on_the_request(fb):
    from app.models.projects import QuotationAmendmentRequest

    response = _send(fb, [_item(fb.w.trap, "remove")], requester_name=CUSTOMER, note="Hello.")
    assert response.status_code == 200, response.text
    fb.db.expire_all()
    (request,) = fb.db.query(QuotationAmendmentRequest).all()
    assert request.requester_name == CUSTOMER
    assert request.note == "Hello."


def test_a_top_level_note_alone_is_accepted(fb):
    response = _send(fb, [], note="Just a thought.")
    assert response.status_code == 200, response.text
    assert _count_requests(fb) == 1
    assert _rows(fb) == []


# ------------------------------------------------------------------ public POST: refusals


def _bad_items(w):
    return {
        "line_unknown": (
            [{"line_id": str(uuid.uuid4()), "kind": "remove"}],
            "quotation_amendment_line_unknown",
        ),
        "cell_unknown": (
            [_item(w.trap, "quantity", cell_key="ghost", value="1")],
            "quotation_feedback_cell_unknown",
        ),
        "cell_on_a_header_that_has_cols": (
            [_item(w.trap, "note", cell_key="ta", note="x")],
            "quotation_feedback_cell_unknown",
        ),
        "cell_on_a_plain_line": (
            [_item(w.plain, "note", cell_key="ta_bh", note="x")],
            "quotation_feedback_cell_unknown",
        ),
        "empty": ([], "quotation_feedback_empty"),
        "duplicate": (
            [_item(w.trap, "remove"), _item(w.trap, "remove")],
            "quotation_amendment_line_duplicate",
        ),
        "duplicate_cell": (
            [
                _item(w.trap, "quantity", cell_key="ta_bh", value="1"),
                _item(w.trap, "quantity", cell_key="ta_bh", value="2"),
            ],
            "quotation_amendment_line_duplicate",
        ),
    }


@pytest.mark.parametrize(
    "case",
    [
        "line_unknown",
        "cell_unknown",
        "cell_on_a_header_that_has_cols",
        "cell_on_a_plain_line",
        "empty",
        "duplicate",
        "duplicate_cell",
    ],
)
def test_contract_422_codes(fb, case):
    items, code = _bad_items(fb.w)[case]
    before = _snapshot(fb)
    response = _send(fb, items)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == code
    assert _count_requests(fb) == 0
    assert _rows(fb) == []
    assert _snapshot(fb) == before


def _plain_bad(w):
    return {
        "cell_with_unit_price": _item(w.trap, "unit_price", cell_key="ta_bh", value="10"),
        "cell_with_remove": _item(w.trap, "remove", cell_key="ta_bh"),
        "cell_with_model_swap": _item(w.trap, "model_swap", cell_key="ta_bh", model="X"),
        "qty_negative": _item(w.trap, "quantity", value="-1"),
        "qty_too_large": _item(w.trap, "quantity", value="10000000"),
        "qty_missing": _item(w.trap, "quantity"),
        "price_zero": _item(w.trap, "unit_price", value="0"),
        "price_negative": _item(w.trap, "unit_price", value="-5"),
        "price_missing": _item(w.trap, "unit_price"),
        "remove_with_value": _item(w.trap, "remove", value="1"),
        "swap_without_model": _item(w.trap, "model_swap", value="5"),
        "swap_blank_model": _item(w.trap, "model_swap", model=""),
        "swap_model_too_long": _item(w.trap, "model_swap", model="m" * 201),
        "note_kind_without_note": _item(w.trap, "note"),
        "note_too_long": _item(w.trap, "note", note="n" * 1001),
        "unknown_kind": _item(w.trap, "accept"),
    }


@pytest.mark.parametrize(
    "case",
    [
        "cell_with_unit_price",
        "cell_with_remove",
        "cell_with_model_swap",
        "qty_negative",
        "qty_too_large",
        "qty_missing",
        "price_zero",
        "price_negative",
        "price_missing",
        "remove_with_value",
        "swap_without_model",
        "swap_blank_model",
        "swap_model_too_long",
        "note_kind_without_note",
        "note_too_long",
        "unknown_kind",
    ],
)
def test_invalid_item_values_are_422_and_store_nothing(fb, case):
    response = _send(fb, [_plain_bad(fb.w)[case]])
    assert response.status_code == 422, response.text
    assert _count_requests(fb) == 0
    assert _rows(fb) == []


def test_the_bounds_are_inclusive_and_a_note_may_be_1000_characters(fb):
    w = fb.w
    response = _send(
        fb,
        [
            _item(w.trap, "quantity", value="0"),
            _item(w.sink, "quantity", value="9999999.99"),
            _item(w.plain, "note", note="n" * 1000),
            _item(w.plain, "model_swap", model="m" * 200),
        ],
    )
    assert response.status_code == 200, response.text
    assert Decimal(_row(fb, w.trap, "quantity").value_to) == Decimal("0")
    assert Decimal(_row(fb, w.sink, "quantity").value_to) == Decimal("9999999.99")


def test_a_swap_may_carry_no_price(fb):
    response = _send(fb, [_item(fb.w.trap, "model_swap", model="Alt")])
    assert response.status_code == 200, response.text
    assert _row(fb, fb.w.trap, "model_swap").value_to is None


def test_the_same_line_may_carry_different_kinds_and_different_cells(fb):
    w = fb.w
    response = _send(
        fb,
        [
            _item(w.trap, "note", note="a"),
            _item(w.trap, "remove"),
            _item(w.trap, "quantity", cell_key="ta_bh", value="1"),
            _item(w.trap, "quantity", cell_key="tb_bh", value="2"),
            _item(w.trap, "note", cell_key="ta_bh", note="b"),
        ],
    )
    assert response.status_code == 200, response.text
    assert len(_rows(fb)) == 5


def test_an_unknown_or_expired_link_is_404(fb):
    missing = fb.client.post(
        f"{PUBLIC}/zzt-not-a-token/amendment-request", json={"items": [], "note": "x"}
    )
    assert missing.status_code == 404
    from app.services import project_quotation_document_service as qdocs  # noqa: F401

    fb.w.record.sign_token_expires_at = datetime.utcnow() - timedelta(days=1)
    fb.db.commit()
    expired = _send(fb, [], note="x")
    assert expired.status_code == 404


# ------------------------------------------------------------------ earlier feedback never blocks


def test_a_second_submission_on_the_same_issue_is_accepted(fb):
    w = fb.w
    first = _send(fb, [_item(w.trap, "note", note="first")], requester_name=CUSTOMER)
    assert first.status_code == 200, first.text
    second = _send(fb, [_item(w.trap, "note", note="second")], requester_name=CUSTOMER)
    assert second.status_code == 200, second.text
    assert _count_requests(fb) == 2
    assert len(_rows(fb)) == 2


def test_an_accepted_issue_refuses_feedback_with_409(fb):
    signed = fb.client.post(
        f"{PUBLIC}/{fb.token}/accept",
        json={"signer_name": CUSTOMER, "mode": "draw", "image_data_uri": SIGNATURE},
    )
    assert signed.status_code == 200, signed.text
    late = _send(fb, [_item(fb.w.trap, "remove")])
    assert late.status_code == 409
    assert late.json()["code"] == "quotation_already_accepted"
    assert _count_requests(fb) == 0


def test_a_superseded_issue_refuses_feedback_with_409(fb):
    from app.services import project_quotation_document_service as qdocs

    qdocs.issue(fb.db, document=fb.w.document, actor_user_id=fb.w.owner)
    fb.db.commit()
    late = _send(fb, [_item(fb.w.trap, "remove")])
    assert late.status_code == 409
    assert late.json()["code"] == "quotation_superseded"


def test_the_sign_page_never_reports_open_feedback_as_a_block_and_signing_works(fb):
    before = fb.client.get(f"{PUBLIC}/{fb.token}").json()
    assert before["can_sign"] is True and before["sign_blocked_reason"] is None

    assert _send(fb, [_item(fb.w.trap, "remove")], note="hmm").status_code == 200
    page = fb.client.get(f"{PUBLIC}/{fb.token}").json()
    assert page["sign_blocked_reason"] is None
    assert page["sign_blocked_reason"] not in ("amendment_open", "amendment_applied")
    assert page["can_sign"] is True

    signed = fb.client.post(
        f"{PUBLIC}/{fb.token}/accept",
        json={"signer_name": CUSTOMER, "mode": "draw", "image_data_uri": SIGNATURE},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["is_accepted"] is True
    assert signed.json()["sign_blocked_reason"] == "accepted"


def test_the_sign_page_scopes_carry_matrix_columns_and_lines_carry_qty_cells(fb):
    page = fb.client.get(f"{PUBLIC}/{fb.token}").json()
    by_label = {scope["scope_label"]: scope for scope in page["scopes"]}
    unit = next(s for label, s in by_label.items() if "Townhouse" in label)
    guard = next(s for label, s in by_label.items() if "GUARD" in label)
    assert unit["matrix_columns"] == COLUMNS
    assert guard["matrix_columns"] in ([], None)
    cells = {line["id"]: line["qty_cells"] for line in unit["lines"]}
    assert cells[str(fb.w.trap.id)] == {
        "ta_bh": "120.00",
        "ta_kit": "120.00",
        "tb_bh": "500.00",
        "tb_kit": "250.00",
    }
    assert guard["lines"][0]["qty_cells"] in ({}, None)


# ------------------------------------------------------------------ staff GET /feedback


def _seed_two_requests(fb):
    """An older request (note on the sink cell) and a newer one (trap item + trap cell)."""
    from app.models.projects import QuotationAmendmentRequest

    w = fb.w
    first = _send(
        fb,
        [_item(w.sink, "quantity", cell_key="ta_bh", value="140", note="needs 140")],
        requester_name="Older Customer",
    )
    assert first.status_code == 200, first.text
    fb.db.expire_all()
    older = fb.db.query(QuotationAmendmentRequest).one()
    older.submitted_at = datetime.utcnow() - timedelta(hours=2)
    fb.db.commit()

    second = _send(
        fb,
        [
            _item(w.plain, "remove"),
            _item(w.sink, "unit_price", value="90.00"),
            _item(w.trap, "note", cell_key="tb_kit", note="check this cell"),
            _item(w.trap, "note", note="whole item"),
        ],
        requester_name="Newer Customer",
        note="Top note",
    )
    assert second.status_code == 200, second.text


def test_staff_get_feedback_shape_ordering_and_cell_labels(fb):
    _seed_two_requests(fb)
    w = fb.w
    response = fb.client.get(f"{_root(fb)}/feedback")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["open_count"] == 5
    assert [r["requester_name"] for r in body["requests"]] == ["Newer Customer", "Older Customer"]

    newer, older = body["requests"]
    assert newer["note"] == "Top note"
    assert newer["submitted_at"]
    assert newer["issue_label"] in (w.record.revision_label, w.record.our_ref_text)
    assert set(newer) >= {"id", "issue_label", "submitted_at", "requester_name", "note", "rows"}

    # Rows come in line order: trap, sink, plain.
    order = [r["line_id"] for r in newer["rows"]]
    expected = [str(w.trap.id), str(w.trap.id), str(w.sink.id), str(w.plain.id)]
    assert order == expected

    for row in newer["rows"]:
        assert set(row) >= {
            "id",
            "line_id",
            "scope_label",
            "line_description",
            "cell_key",
            "cell_label",
            "kind",
            "value_from",
            "value_to",
            "model",
            "note",
            "handled_at",
            "handled_by_name",
        }
        assert row["handled_at"] is None and row["handled_by_name"] is None

    cell_row = next(r for r in newer["rows"] if r["cell_key"] == "tb_kit")
    assert cell_row["cell_label"] == "TYPE B / KITCHEN"
    assert cell_row["kind"] == "note"
    assert cell_row["note"] == "check this cell"
    assert "Townhouse" in cell_row["scope_label"]
    assert cell_row["line_description"] == w.trap.description_snapshot

    item_row = next(r for r in newer["rows"] if r["kind"] == "note" and r["cell_key"] is None)
    assert item_row["cell_label"] is None
    assert item_row["note"] == "whole item"

    price_row = next(r for r in newer["rows"] if r["kind"] == "unit_price")
    assert Decimal(str(price_row["value_from"])) == Decimal("100.00")
    assert Decimal(str(price_row["value_to"])) == Decimal("90.00")

    remove_row = next(r for r in newer["rows"] if r["kind"] == "remove")
    assert "GUARD" in remove_row["scope_label"]

    (qty_row,) = older["rows"]
    assert qty_row["kind"] == "quantity"
    assert qty_row["cell_label"] == "TYPE A / 1 BH"
    assert Decimal(str(qty_row["value_from"])) == Decimal("2")
    assert Decimal(str(qty_row["value_to"])) == Decimal("140")


def test_a_header_with_no_cols_labels_its_cell_with_the_header_alone(fb):
    assert _send(fb, [_item(fb.w.trap, "quantity", cell_key="tank", value="4")]).status_code == 200
    (request,) = fb.client.get(f"{_root(fb)}/feedback").json()["requests"]
    (row,) = request["rows"]
    assert row["cell_label"] == "BREAK TANK"


def test_a_model_swap_row_reports_the_model_name(fb):
    assert _send(
        fb, [_item(fb.w.trap, "model_swap", model="Alt Model 77", value="55.00")]
    ).status_code == 200
    (request,) = fb.client.get(f"{_root(fb)}/feedback").json()["requests"]
    (row,) = request["rows"]
    assert row["kind"] == "model_swap"
    assert row["model"] == "Alt Model 77"
    assert Decimal(str(row["value_to"])) == Decimal("55.00")


def test_staff_get_with_no_feedback_is_empty_not_an_error(fb):
    response = fb.client.get(f"{_root(fb)}/feedback")
    assert response.status_code == 200, response.text
    assert response.json() == {"open_count": 0, "requests": []}


# ------------------------------------------------------------------ staff PATCH handled


def _first_row_id(fb):
    body = fb.client.get(f"{_root(fb)}/feedback").json()
    return body["requests"][0]["rows"][0]["id"]


def test_handled_true_sets_who_and_when_and_false_clears_them(fb):
    assert _send(fb, [_item(fb.w.trap, "remove"), _item(fb.w.sink, "remove")]).status_code == 200
    row_id = _first_row_id(fb)
    assert fb.client.get(f"{_root(fb)}/feedback").json()["open_count"] == 2

    done = fb.client.patch(f"{_root(fb)}/feedback/{row_id}", json={"handled": True})
    assert done.status_code == 200, done.text
    body = fb.client.get(f"{_root(fb)}/feedback").json()
    assert body["open_count"] == 1
    row = next(r for rq in body["requests"] for r in rq["rows"] if r["id"] == row_id)
    assert row["handled_at"] is not None
    assert row["handled_by_name"] == f"{MARKER} Baser"
    other = next(r for rq in body["requests"] for r in rq["rows"] if r["id"] != row_id)
    assert other["handled_at"] is None

    reopened = fb.client.patch(f"{_root(fb)}/feedback/{row_id}", json={"handled": False})
    assert reopened.status_code == 200, reopened.text
    body = fb.client.get(f"{_root(fb)}/feedback").json()
    assert body["open_count"] == 2
    row = next(r for rq in body["requests"] for r in rq["rows"] if r["id"] == row_id)
    assert row["handled_at"] is None and row["handled_by_name"] is None


def test_handled_is_required_and_a_made_up_row_is_404(fb):
    assert _send(fb, [_item(fb.w.trap, "remove")]).status_code == 200
    row_id = _first_row_id(fb)
    missing = fb.client.patch(f"{_root(fb)}/feedback/{row_id}", json={})
    assert missing.status_code == 422
    ghost = fb.client.patch(f"{_root(fb)}/feedback/{uuid.uuid4()}", json={"handled": True})
    assert ghost.status_code == 404


def test_a_row_of_another_document_is_404_and_stays_open(fb):
    from app.services import project_quotation_document_service as qdocs

    assert _send(fb, [_item(fb.w.trap, "remove")]).status_code == 200
    row_id = _first_row_id(fb)
    other = qdocs.create_document(fb.db, project=fb.w.project, actor_user_id=fb.w.owner)
    fb.db.commit()
    url = (
        f"{BASE}/projects/{fb.w.project.id}/quotation-documents/{other.id}/feedback/{row_id}"
    )
    refused = fb.client.patch(url, json={"handled": True})
    assert refused.status_code == 404, refused.text
    assert fb.client.get(f"{_root(fb)}/feedback").json()["open_count"] == 1


def test_issuing_a_revision_does_not_close_feedback(fb):
    from app.services import project_quotation_document_service as qdocs

    assert _send(fb, [_item(fb.w.trap, "remove")]).status_code == 200
    qdocs.issue(fb.db, document=fb.w.document, actor_user_id=fb.w.owner)
    fb.db.commit()
    assert fb.client.get(f"{_root(fb)}/feedback").json()["open_count"] == 1


# ------------------------------------------------------------------ retired and untouched


def test_the_decide_apply_and_old_staff_read_routes_are_gone(fb):
    assert _send(fb, [_item(fb.w.trap, "remove")], note="x").status_code == 200
    from app.models.projects import QuotationAmendmentRequest

    fb.db.expire_all()
    request_id = str(fb.db.query(QuotationAmendmentRequest).one().id)
    row_id = str(_rows(fb)[0].id)
    decide = fb.client.put(
        f"{_root(fb)}/amendment-requests/{request_id}/rows/{row_id}",
        json={"decision": "accepted"},
    )
    apply = fb.client.post(f"{_root(fb)}/amendment-requests/{request_id}/apply")
    old_read = fb.client.get(f"{_root(fb)}/amendment-request")
    assert decide.status_code in (404, 405), decide.text
    assert apply.status_code in (404, 405), apply.text
    assert old_read.status_code in (404, 405), old_read.text


def test_the_retired_service_functions_no_longer_exist():
    from app.services import quotation_amendment_service as amend

    assert not hasattr(amend, "decide_row")
    assert not hasattr(amend, "apply_request")


def test_no_feedback_endpoint_changes_a_quotation_line_or_a_total(fb):
    w = fb.w
    before = _snapshot(fb)
    assert _send(
        fb,
        [
            _item(w.trap, "quantity", cell_key="ta_kit", value="999"),
            _item(w.sink, "unit_price", value="1.00"),
            _item(w.plain, "remove"),
            _item(w.trap, "model_swap", model="Alt", value="5"),
        ],
        note="all of it",
    ).status_code == 200
    assert _snapshot(fb) == before

    row_id = _first_row_id(fb)
    assert fb.client.patch(f"{_root(fb)}/feedback/{row_id}", json={"handled": True}).status_code == 200
    assert fb.client.patch(f"{_root(fb)}/feedback/{row_id}", json={"handled": False}).status_code == 200
    assert fb.client.get(f"{_root(fb)}/feedback").status_code == 200
    assert _snapshot(fb) == before
