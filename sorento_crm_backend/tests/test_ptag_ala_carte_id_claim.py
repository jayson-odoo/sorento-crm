"""PRICETAG-ALA-CARTE review findings: a line id is a claim on ONE saved line, never a free pass.

Contract: `documentation/plans/dealer-kit/pricetag-ala-carte-acceptance-criteria.md` AC-12
(a payload line carries the tags of the saved line its `id` names), narrowed by the review of
the lane (reviewer + security-reviewer, blocking):

A. An `id` naming a saved line of a DIFFERENT product (or set) than the payload line is not a
   claim: the new line gets fresh tags (no marketing override, no reason, printed, new tag id)
   and no carried template pick. Both paths: staff/portal `replace_lines` and portal revise.
   An id with the SAME product still carries (guard).
B. An `id` naming a line of ANOTHER request is never honoured; the other request is untouched.
C. Schema limits: at most 500 lines a request ("A request holds at most 500 lines.") on create,
   update and portal revise; at most 100 parts a line ("A line holds at most 100 parts.").

Written test-FIRST. Red today: `_add_lines` (price_tag_request_service.py, the id claim loop)
and `_apply_price_tag_lines` (portal_revision_service.py, `by_id`) honour any id of this
request whatever product it names, and no schema caps lines or parts.

Postgres only (`tests/_pg_fixture.blank_session`); every row seeded here. Synthetic codes.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.price_tag import PriceTagRequestLine
from app.services.price_tag_request_service import PriceTagRequestService

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session

LINES_MESSAGE = "A request holds at most 500 lines."
PARTS_MESSAGE = "A line holds at most 100 parts."


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


def _lines_of(db, request_id):
    db.expire_all()
    return (
        db.query(PriceTagRequestLine)
        .filter(PriceTagRequestLine.request_id == request_id)
        .order_by(PriceTagRequestLine.sort_order.asc(), PriceTagRequestLine.id.asc())
        .all()
    )


def _by_remark(db, request_id) -> dict:
    return {line.remarks: line for line in _lines_of(db, request_id)}


def _message_of(exc) -> str:
    message = getattr(exc, "message", None)
    if message:
        return message
    detail = getattr(exc, "detail", None)
    return str(detail.get("message")) if isinstance(detail, dict) else str(exc)


def _tag_state(line) -> list[tuple]:
    """A line's tags as (id, override, reason, print_excluded), print order."""
    return [
        (
            tag.id,
            None if tag.marketing_price_override is None else Decimal(str(tag.marketing_price_override)),
            tag.marketing_override_reason,
            bool(tag.print_excluded),
        )
        for tag in r9.tags_of(line)
    ]


def _mark(line, figure: str, reason: str) -> None:
    """Marketing's work on a line's tags: an override, its reason, and Not printed."""
    for tag in r9.tags_of(line):
        tag.marketing_price_override = Decimal(figure)
        tag.marketing_override_reason = reason
        tag.print_excluded = True


def _assert_fresh(line, old_tag_ids: set) -> None:
    tags = _tag_state(line)
    assert len(tags) == 1, tags
    tag_id, override, reason, excluded = tags[0]
    assert tag_id not in old_tag_ids, "the old line's tag row was carried onto another product"
    assert (override, reason, excluded) == (None, None, False)


def _set_line(product_set, **extra):
    return {"line_type": "product_set", "product_set_id": product_set.id, "quantity": 1, **extra}


# =========================================================================== A. staff replace_lines


def _marked_request(db, lines):
    """Submit `lines` (each with a distinct remark), mark every line's tags, return
    (request, {remark: line id}, {remark: tag ids})."""
    request = seed.submit(db, lines)
    by_remark = _by_remark(db, request.id)
    for remark, line in by_remark.items():
        _mark(line, "11.00", f"ZZT override {remark}")
    db.flush()
    by_remark = _by_remark(db, request.id)
    ids = {remark: line.id for remark, line in by_remark.items()}
    tag_ids = {remark: {t.id for t in r9.tags_of(line)} for remark, line in by_remark.items()}
    return request, ids, tag_ids


def test_a_replace_lines_id_of_another_product_gets_fresh_tags(db):
    host = seed.product(db, "P-IDC-A")
    other = seed.product(db, "P-IDC-B")
    request, ids, tag_ids = _marked_request(db, [seed.line_dict(host, None, remarks="L1")])

    PriceTagRequestService.replace_lines(
        db, request, [seed.line_dict(other, None, remarks="L1", id=ids["L1"])]
    )
    db.flush()

    (line,) = _lines_of(db, request.id)
    assert line.product_id == other.id
    _assert_fresh(line, tag_ids["L1"])


def test_a_replace_lines_id_of_another_set_gets_fresh_tags(db):
    first = r9.seed_product_set(db)
    second = r9.seed_product_set(db)
    request, ids, tag_ids = _marked_request(db, [_set_line(first, remarks="S1")])

    PriceTagRequestService.replace_lines(
        db, request, [_set_line(second, remarks="S1", id=ids["S1"])]
    )
    db.flush()

    (line,) = _lines_of(db, request.id)
    assert line.product_set_id == second.id
    _assert_fresh(line, tag_ids["S1"])


def test_a_replace_lines_id_of_a_product_line_sent_as_a_set_gets_fresh_tags(db):
    host = seed.product(db, "P-IDC-C")
    product_set = r9.seed_product_set(db)
    request, ids, tag_ids = _marked_request(db, [seed.line_dict(host, None, remarks="L1")])

    PriceTagRequestService.replace_lines(
        db, request, [_set_line(product_set, remarks="L1", id=ids["L1"])]
    )
    db.flush()

    (line,) = _lines_of(db, request.id)
    assert line.product_set_id == product_set.id
    _assert_fresh(line, tag_ids["L1"])


def test_a_guard_replace_lines_id_of_the_same_product_still_carries(db):
    """Guard (passes today): the review narrows the claim, it must not drop it."""
    host = seed.product(db, "P-IDC-D")
    other = seed.product(db, "P-IDC-E")
    request, ids, _tag_ids = _marked_request(
        db, [seed.line_dict(host, None, remarks="L1"), seed.line_dict(other, None, remarks="L2")]
    )
    before = {remark: _tag_state(line) for remark, line in _by_remark(db, request.id).items()}

    # Swapped order, new remark text on neither key: each id names a line of its own product.
    PriceTagRequestService.replace_lines(
        db,
        request,
        [
            seed.line_dict(other, None, remarks="L2", id=ids["L2"]),
            seed.line_dict(host, None, remarks="L1", id=ids["L1"]),
        ],
    )
    db.flush()

    after = {remark: _tag_state(line) for remark, line in _by_remark(db, request.id).items()}
    assert after == before


# =========================================================================== B. staff, another request's id


def test_b_replace_lines_id_of_another_requests_line_is_not_honoured(db):
    host = seed.product(db, "P-IDC-F")
    foreign_product = seed.product(db, "P-IDC-G")
    request, _ids, _tags = _marked_request(db, [seed.line_dict(host, None, remarks="L1")])
    foreign, foreign_ids, foreign_tag_ids = _marked_request(
        db, [seed.line_dict(foreign_product, None, remarks="F1")]
    )
    foreign_before = {r: _tag_state(line) for r, line in _by_remark(db, foreign.id).items()}

    PriceTagRequestService.replace_lines(
        db, request, [seed.line_dict(foreign_product, None, remarks="N1", id=foreign_ids["F1"])]
    )
    db.flush()

    (line,) = _lines_of(db, request.id)
    assert line.id != foreign_ids["F1"]
    _assert_fresh(line, foreign_tag_ids["F1"])
    assert {r: _tag_state(l) for r, l in _by_remark(db, foreign.id).items()} == foreign_before


# =========================================================================== portal revise harness


def _revise_setup(db, lines):
    from tests.test_portal_price_tag_revise import (
        _seed_contact,
        _seed_ptag_config,
        _seed_system_settings,
        _seed_token,
    )

    _seed_system_settings(db, cap=3)
    _seed_ptag_config(db, max_revisions=None)
    contact = _seed_contact(db)
    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=seed.SORENTO,
        data={"debtor_name": "ZZT Original Dealer", "lines": lines},
    )
    request.status = "proof_ready"
    request.portal_draft_at = None
    request.print_by = "office"
    request.revision_no = 0
    db.commit()
    return request, _seed_token(contact)


def _revise(db, token, request, products):
    from app.services.portal_revision_service import PortalRevisionService

    return PortalRevisionService(db).revise(
        token, "price_tag_request", str(request.id), {"products": products}, "Reason", 0
    )


def _marked_revise_request(db, lines):
    request, token = _revise_setup(db, lines)
    by_remark = _by_remark(db, request.id)
    for remark, line in by_remark.items():
        _mark(line, "11.00", f"ZZT override {remark}")
    ids = {remark: line.id for remark, line in by_remark.items()}
    tag_ids = {remark: {t.id for t in r9.tags_of(line)} for remark, line in by_remark.items()}
    db.commit()
    return request, token, ids, tag_ids


# =========================================================================== A. portal revise


def test_a_portal_revise_id_of_another_product_gets_fresh_tags(db):
    host = seed.product(db, "P-IDC-H")
    other = seed.product(db, "P-IDC-I")
    request, token, ids, tag_ids = _marked_revise_request(
        db, [seed.line_dict(host, None, remarks="L1")]
    )

    _revise(db, token, request, [{"id": ids["L1"], "product_id": other.id, "quantity": 1, "remarks": "L1"}])

    (line,) = _lines_of(db, request.id)
    assert line.product_id == other.id
    _assert_fresh(line, tag_ids["L1"])


def test_a_portal_revise_id_of_another_set_gets_fresh_tags(db):
    first = r9.seed_product_set(db)
    second = r9.seed_product_set(db)
    request, token, ids, tag_ids = _marked_revise_request(db, [_set_line(first, remarks="S1")])

    _revise(
        db, token, request, [{"id": ids["S1"], "product_set_id": second.id, "quantity": 1, "remarks": "S1"}]
    )

    (line,) = _lines_of(db, request.id)
    assert line.product_set_id == second.id
    _assert_fresh(line, tag_ids["S1"])


def _template(db, name: str) -> str:
    from tests.test_product_tag_templates import _template as make

    return make(db, name)


def _link(db, product_id: str, template_id: str, *, default_list: bool = False) -> None:
    from app.models.dealer_kit import ProductTagTemplate

    flags = {"default_list": True} if default_list else {}
    db.add(ProductTagTemplate(product_id=product_id, template_id=template_id, **flags))
    db.flush()


def test_a_portal_revise_id_of_another_product_does_not_carry_the_template_pick(db):
    """The old line (product A) printed on T2. Product B links T1 (its LP default) and T2.
    A revise entry naming A's line id but product B, sending no pick, is a NEW line of B:
    it starts on B's default T1, not on A's T2."""
    first = seed.product(db, "P-IDC-J")
    second = seed.product(db, "P-IDC-K")
    t1 = _template(db, "ZZT IDC T1")
    t2 = _template(db, "ZZT IDC T2")
    _link(db, first.id, t2)
    _link(db, second.id, t1, default_list=True)
    _link(db, second.id, t2)
    request, token, ids, _tag_ids = _marked_revise_request(
        db, [seed.line_dict(first, None, remarks="L1", tag_template_id=t2)]
    )
    assert str(_lines_of(db, request.id)[0].tag_template_id) == t2

    _revise(db, token, request, [{"id": ids["L1"], "product_id": second.id, "quantity": 1, "remarks": "L1"}])

    (line,) = _lines_of(db, request.id)
    assert line.product_id == second.id
    assert str(line.tag_template_id) == t1


def test_a_guard_portal_revise_id_of_the_same_product_still_carries(db):
    """Guard (passes today)."""
    host = seed.product(db, "P-IDC-L")
    request, token, ids, tag_ids = _marked_revise_request(
        db, [seed.line_dict(host, None, remarks="L1")]
    )
    before = _tag_state(_lines_of(db, request.id)[0])

    _revise(db, token, request, [{"id": ids["L1"], "product_id": host.id, "quantity": 1, "remarks": "L1 edited"}])

    (line,) = _lines_of(db, request.id)
    assert line.remarks == "L1 edited"
    assert _tag_state(line) == before


# =========================================================================== B. portal revise, another request's id


def test_b_portal_revise_id_of_another_requests_line_is_not_honoured(db):
    host = seed.product(db, "P-IDC-M")
    foreign_product = seed.product(db, "P-IDC-N")
    request, token, _ids, _tags = _marked_revise_request(
        db, [seed.line_dict(host, None, remarks="L1")]
    )
    foreign, foreign_ids, foreign_tag_ids = _marked_request(
        db, [seed.line_dict(foreign_product, None, remarks="F1")]
    )
    db.commit()
    foreign_before = {r: _tag_state(line) for r, line in _by_remark(db, foreign.id).items()}

    _revise(
        db,
        token,
        request,
        [{"id": foreign_ids["F1"], "product_id": foreign_product.id, "quantity": 1, "remarks": "N1"}],
    )

    (line,) = _lines_of(db, request.id)
    assert line.id != foreign_ids["F1"]
    _assert_fresh(line, foreign_tag_ids["F1"])
    assert {r: _tag_state(l) for r, l in _by_remark(db, foreign.id).items()} == foreign_before


# =========================================================================== C. schema limits


def _schema_line(**extra) -> dict:
    return {"line_type": "product", "product_id": str(uuid.uuid4()), **extra}


def _parts(count: int) -> list[dict]:
    return [{"product_id": str(uuid.uuid4())} for _ in range(count)]


def test_c_create_with_501_lines_is_refused_naming_the_limit():
    from app.schemas.price_tag import PriceTagRequestCreate

    with pytest.raises(ValidationError) as exc_info:
        PriceTagRequestCreate(lines=[_schema_line() for _ in range(501)])

    assert LINES_MESSAGE in str(exc_info.value)


def test_c_create_with_500_lines_is_accepted():
    from app.schemas.price_tag import PriceTagRequestCreate

    assert len(PriceTagRequestCreate(lines=[_schema_line() for _ in range(500)]).lines) == 500


def test_c_update_with_501_lines_is_refused_naming_the_limit():
    from app.schemas.price_tag import PriceTagRequestUpdate

    with pytest.raises(ValidationError) as exc_info:
        PriceTagRequestUpdate(lines=[_schema_line() for _ in range(501)])

    assert LINES_MESSAGE in str(exc_info.value)


def test_c_update_with_500_lines_is_accepted():
    from app.schemas.price_tag import PriceTagRequestUpdate

    assert len(PriceTagRequestUpdate(lines=[_schema_line() for _ in range(500)]).lines) == 500


def test_c_a_line_with_101_parts_is_refused_naming_the_limit():
    from app.schemas.price_tag import PriceTagRequestCreate

    with pytest.raises(ValidationError) as exc_info:
        PriceTagRequestCreate(lines=[_schema_line(parts=_parts(101))])

    assert PARTS_MESSAGE in str(exc_info.value)


def test_c_a_line_with_100_parts_is_accepted():
    from app.schemas.price_tag import PriceTagRequestCreate

    assert len(PriceTagRequestCreate(lines=[_schema_line(parts=_parts(100))]).lines[0].parts) == 100


def test_c_revise_line_with_101_parts_is_a_422_naming_the_limit():
    """The revise entry runs through `PriceTagReviseLineIn` in `_convert_ptag_revise_line`."""
    from app.services.portal_revision_service import _convert_ptag_revise_line

    with pytest.raises(HTTPException) as exc_info:
        _convert_ptag_revise_line({"product_id": str(uuid.uuid4()), "parts": _parts(101)}, 0)

    assert exc_info.value.status_code == 422
    assert PARTS_MESSAGE in _message_of(exc_info.value)


def test_c_revise_line_with_100_parts_is_accepted():
    from app.services.portal_revision_service import _convert_ptag_revise_line

    converted = _convert_ptag_revise_line({"product_id": str(uuid.uuid4()), "parts": _parts(100)}, 0)

    assert len(converted["parts"]) == 100


def test_c_portal_revise_with_501_lines_is_a_422_naming_the_limit(db):
    """Entries carry no product on purpose: refused cheaply (EMPTY_LINE) if the cap is missing,
    so the red run does not insert 501 rows."""
    host = seed.product(db, "P-IDC-O")
    request, token = _revise_setup(db, [seed.line_dict(host, None)])

    with pytest.raises(HTTPException) as exc_info:
        _revise(db, token, request, [{"quantity": 1} for _ in range(501)])

    assert exc_info.value.status_code == 422
    assert _message_of(exc_info.value) == LINES_MESSAGE


def test_c_portal_revise_with_500_lines_is_not_refused_for_its_count(db):
    """500 passes the cap; the same empty entries are then refused for what they are."""
    host = seed.product(db, "P-IDC-P")
    request, token = _revise_setup(db, [seed.line_dict(host, None)])

    with pytest.raises(HTTPException) as exc_info:
        _revise(db, token, request, [{"quantity": 1} for _ in range(500)])

    assert _message_of(exc_info.value) != LINES_MESSAGE
