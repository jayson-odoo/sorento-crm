"""PRICETAG-COMBO-RENDER N1: Approve checks the chosen template's needs, not the rows present.

Deleting a choice group's whole row left nothing to check, so a tag with empty pick spaces was
approved. The server now compares the line's picks per group (and its fixed parts) with what the
line's template reads and refuses with TEMPLATE_POSITIONS_MISSING, detail `line:<index>`.
"""
from __future__ import annotations

import os

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.error_handler import AppException
from app.services.price_tag_request_service import STATUS_PROOF_READY, PriceTagRequestService

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests import _ptag_shapes_seed as shapes
from tests._pg_fixture import blank_session
from tests.test_product_tag_templates import env  # noqa: F401  (loads the same templates harness)
from tests.test_template_needs_in_lists import _doc, _published

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

TWO_PICKS = ({"kind": "pick", "group": 0, "index": 0}, {"kind": "pick", "group": 0, "index": 1})


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)


def _request(db, s, parts, template_slots, *, combo=True):
    request = seed.submit_one(db, s["host"], s["combo"] if combo else None, parts, price_mode="list")
    request.lines[0].tag_template_id = _published(db, "ZZT N1", _doc(*template_slots))
    request.status = STATUS_PROOF_READY
    request.assigned_to_id = None
    db.flush()
    return request


def test_a_deleted_group_row_is_refused_with_the_picks_it_owes(db):
    s = shapes.s3(db)
    request = _request(db, s, [], TWO_PICKS)
    with pytest.raises(AppException) as raised:
        PriceTagRequestService.require_template_positions(db, request)
    error = raised.value
    assert error.status_code == 422
    assert error.detail["code"] == "TEMPLATE_POSITIONS_MISSING"
    assert error.detail["detail"] == "line:0"
    assert error.detail["message"] == f"{s['group']}: pick 2 more."


def test_the_right_picks_are_approved(db):
    s = shapes.s3(db)
    request = _request(db, s, shapes.pick_parts(s["group"], *s["options"]), TWO_PICKS)
    PriceTagRequestService.require_template_positions(db, request)


def test_a_line_whose_template_reads_no_group_is_not_refused(db):
    s = shapes.s3(db)
    request = _request(db, s, [], ({"kind": "main"},))
    PriceTagRequestService.require_template_positions(db, request)


def test_an_a_la_carte_line_is_never_refused(db):
    s = shapes.s3(db)
    request = _request(db, s, shapes.pick_parts(s["group"], s["options"][0]), TWO_PICKS, combo=False)
    PriceTagRequestService.require_template_positions(db, request)


def test_a_missing_fixed_part_the_template_reads_is_named(db):
    s = shapes.s4(db)
    request = _request(db, s, shapes.fixed_parts(s["fixed"][1]), ({"kind": "fixed", "index": 0},))
    with pytest.raises(AppException) as raised:
        PriceTagRequestService.require_template_positions(db, request)
    assert raised.value.detail["code"] == "TEMPLATE_POSITIONS_MISSING"
    assert raised.value.detail["message"].startswith("Template needs ")


def test_self_approve_refuses_it_before_anything_is_written(db):
    s = shapes.s3(db)
    request = _request(db, s, [], TWO_PICKS)
    with pytest.raises(AppException) as raised:
        PriceTagRequestService.self_approve(db, request, {"kind": "tag_sheet"}, "Sales")
    assert raised.value.detail["code"] in ("TEMPLATE_POSITIONS_MISSING", "COMBO_PRICE_MISSING")
