"""PS-SAMPLE-TRACKING, red-first: the two stages and the Stage 1 date answer.

Plan + behaviour card: documentation/plans/project-sales/PLAN-sample-tracking-02nov.md
(rules 1-3). Route level, Postgres only; the `world` fixture and helpers are the SR-CORE
suite's own, so both suites seed the same chain.
"""
from __future__ import annotations

import pytest

from .test_sample_requests_core import (  # noqa: F401  (world is a fixture)
    _link_consignment,
    SR,
    _draft,
    _get,
    _submit,
    _submitted,
    world,
)

FUTURE = "2099-01-15"
PAST = "2000-01-01"


def _move(w, rid, to, user=None, **extra):
    return w.api.as_(user or w.coord).post(f"{SR}/{rid}/move", json={"to": to, **extra})


def _answer(w, rid, user=None, **body):
    return w.api.as_(user or w.coord).put(f"{SR}/{rid}/date-answer", json=body)


def _code(res):
    body = res.json()
    return body.get("code") or (body.get("error") or {}).get("code") or body.get("detail")


def _field(res):
    body = res.json()
    details = body.get("details") or (body.get("error") or {}).get("details") or {}
    return details.get("field")


# ------------------------------------------------------------------ rule 2: the answer is required


def test_start_processing_needs_a_date_answer(world):
    rid = _submitted(world)
    res = _move(world, rid, "processing")
    assert res.status_code == 422, res.text
    assert _code(res) == "SAMPLE_REQUEST_DATE_ANSWER_REQUIRED"
    assert _field(res) == "date_feasible"
    assert _get(world, rid)["status"] == "submitted"


def test_start_processing_can_meet_the_date(world):
    rid = _submitted(world)
    res = _move(world, rid, "processing", date_feasible=True)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "processing"
    assert body["stage"] == "processing"
    assert body["date_feasible"] is True
    assert body["proposed_delivery_date"] is None
    assert body["date_answered_at"]
    assert body["date_answered_by_name"].endswith("coordinator")


def test_cannot_meet_needs_a_proposed_date(world):
    rid = _submitted(world)
    res = _move(world, rid, "processing", date_feasible=False)
    assert res.status_code == 422, res.text
    assert _code(res) == "SAMPLE_REQUEST_PROPOSED_DATE_REQUIRED"
    assert _field(res) == "proposed_delivery_date"


def test_proposed_date_cannot_be_in_the_past(world):
    rid = _submitted(world)
    res = _move(
        world, rid, "processing", date_feasible=False, proposed_delivery_date=PAST
    )
    assert res.status_code == 422, res.text
    assert _code(res) == "SAMPLE_REQUEST_PROPOSED_DATE_PAST"
    assert _field(res) == "proposed_delivery_date"


def test_feasible_drops_a_stray_proposed_date(world):
    rid = _submitted(world)
    res = _move(
        world, rid, "processing", date_feasible=True, proposed_delivery_date=FUTURE
    )
    assert res.status_code == 200, res.text
    assert res.json()["proposed_delivery_date"] is None


# ------------------------------------------------------------------ rule 3: the salesperson sees it


def test_salesperson_sees_the_proposed_date_on_detail_and_list(world):
    rid = _submitted(world)
    res = _move(
        world,
        rid,
        "processing",
        date_feasible=False,
        proposed_delivery_date=FUTURE,
        date_note="Stock from KL",
    )
    assert res.status_code == 200, res.text

    detail = _get(world, rid, user=world.sales)
    assert detail["date_feasible"] is False
    assert detail["proposed_delivery_date"] == FUTURE
    assert detail["date_note"] == "Stock from KL"
    assert detail["delivery_date"] == "2026-12-01"

    rows = world.api.as_(world.sales).get(SR).json()
    rows = rows.get("data", rows.get("items", rows)) if isinstance(rows, dict) else rows
    row = next(r for r in rows if r["id"] == rid)
    assert row["date_feasible"] is False
    assert row["proposed_delivery_date"] == FUTURE
    assert row["stage"] == "processing"


# ------------------------------------------------------------------ rule 2: change the answer in Stage 1


def test_coordinator_changes_the_answer_while_processing(world):
    rid = _submitted(world)
    assert _move(world, rid, "processing", date_feasible=True).status_code == 200

    res = _answer(world, rid, date_feasible=False, proposed_delivery_date=FUTURE, date_note="Late")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["date_feasible"] is False
    assert body["proposed_delivery_date"] == FUTURE
    assert body["date_note"] == "Late"

    back = _answer(world, rid, date_feasible=True)
    assert back.status_code == 200, back.text
    assert back.json()["proposed_delivery_date"] is None
    assert back.json()["date_note"] is None


def test_answer_change_is_validated_like_the_move(world):
    rid = _submitted(world)
    assert _move(world, rid, "processing", date_feasible=True).status_code == 200
    res = _answer(world, rid, date_feasible=False)
    assert res.status_code == 422, res.text
    assert _code(res) == "SAMPLE_REQUEST_PROPOSED_DATE_REQUIRED"


def test_salesperson_cannot_answer(world):
    rid = _submitted(world)
    assert _move(world, rid, "processing", date_feasible=True).status_code == 200
    res = _answer(world, rid, user=world.sales, date_feasible=False, proposed_delivery_date=FUTURE)
    assert res.status_code == 403, res.text


def test_answer_only_in_stage_one(world):
    """Before Start processing there is nothing to change; after Delivered it is closed."""
    rid = _submitted(world)
    early = _answer(world, rid, date_feasible=True)
    assert early.status_code == 409, early.text
    assert _code(early) == "SAMPLE_REQUEST_DATE_ANSWER_CLOSED"

    assert _move(world, rid, "processing", date_feasible=True).status_code == 200
    assert _answer(world, rid, date_feasible=True).status_code == 200  # still Stage 1
    assert _link_consignment(world, rid).status_code == 200
    late = _answer(world, rid, date_feasible=True)
    assert late.status_code == 409, late.text
    assert _code(late) == "SAMPLE_REQUEST_DATE_ANSWER_CLOSED"


# ------------------------------------------------------------------ rule 1: stage mapping


@pytest.mark.parametrize(
    "key,stage",
    [
        ("draft", None),
        ("submitted", "processing"),
        ("processing", "processing"),
        ("customer_confirmed", "processing"),
        ("delivered", "delivery"),
        ("cancelled", None),
        ("some_admin_added_key", None),
        (None, None),
    ],
)
def test_stage_for_status_key(key, stage):
    from app.services.sample_request_service import stage_for

    assert stage_for(key) == stage


def test_stage_on_detail_through_the_flow(world):
    d = _draft(world)
    assert _get(world, d["id"])["stage"] is None
    assert _submit(world, d["id"]).status_code in (200, 201)
    assert _get(world, d["id"])["stage"] == "processing"
    assert _move(world, d["id"], "processing", date_feasible=True).status_code == 200
    assert _link_consignment(world, d["id"]).status_code == 200
    assert _get(world, d["id"])["stage"] == "delivery"


# ------------------------------------------------------------------ list: stage filter + sort


def _rows(w, **params):
    res = w.api.as_(w.coord).get(SR, params=params)
    assert res.status_code == 200, res.text
    return res.json()["data"]


def test_stage_filter_is_multi_select_and_finds_delivered(world):
    from .test_sample_requests_core import _delivered

    submitted = _submitted(world)
    done = _delivered(world)
    draft = _draft(world)["id"]

    processing = {r["id"] for r in _rows(world, stage="processing", limit=200)}
    assert submitted in processing and done not in processing and draft not in processing

    delivery = {r["id"] for r in _rows(world, stage="delivery", limit=200)}
    assert done in delivery and submitted not in delivery

    both = {r["id"] for r in _rows(world, stage=["processing", "delivery"], limit=200)}
    assert {submitted, done} <= both and draft not in both


def test_delivery_date_sort_follows_the_proposed_date(world):
    early = _submitted(world, delivery_date="2026-12-01")
    late = _submitted(world, delivery_date="2026-12-05")
    # The team pushes the early one past the late one.
    assert _move(
        world, early, "processing", date_feasible=False, proposed_delivery_date=FUTURE
    ).status_code == 200

    ids = [r["id"] for r in _rows(world, sort="delivery_date", dir="asc", limit=200)]
    assert ids.index(late) < ids.index(early)


def test_a_bare_stage_param_keeps_the_open_default(world):
    """Review nit: `?stage=` with no value is no stage filter; drafts stay out."""
    draft = _draft(world)["id"]
    open_one = _submitted(world)
    ids = {r["id"] for r in _rows(world, stage="", limit=200)}
    assert open_one in ids and draft not in ids
