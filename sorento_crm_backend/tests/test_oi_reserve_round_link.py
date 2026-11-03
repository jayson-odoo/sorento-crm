"""OI-RESERVE-ROUND: a reserve email's button opens THAT email's lines.

Contract: `documentation/plans/scm/oi-reserve-round-acceptance-criteria.md` (AC-1..AC-5).
TEST-FIRST. AC-1..AC-3 pin `merged_context`'s `reserve.link`; AC-4/AC-5 pin the worklist's
`reserve_request` filter (list, summary, export request, matrix).
"""
from __future__ import annotations

import uuid

import pytest

from app.services.automation_triggers import build_order_inquiry_link
from app.services.order_inquiry_reserve_service import merged_context

from .test_oi_reserve_email_full_table import _ask, _line, _oi
from .test_oi_staged_notify import _commit, _ok, _reserve, sn  # noqa: F401  (fixture)
from .test_order_inquiry_reserve import _captured_dispatches, _register
from .test_order_inquiry_worklist import LIST

SUMMARY = f"{LIST}/summary"


def _context(inquiry_no: str, request_id: str, *, link_ids: str | None = None) -> dict:
    """The shape `_build_context` / `_build_commit_context` hand `merged_context`."""
    oi_link = f"{build_order_inquiry_link(f'oi-{inquiry_no}')}"
    return {
        "actor": None,
        "reserve": {
            "inquiry_no": inquiry_no,
            "request_id": request_id,
            "ordinal": 1,
            "so_number": "SO-1",
            "oi_link": oi_link,
            "link": f"{oi_link}?reserve={request_id}",
            "rows": [
                {"item_code": "A", "qty": "1", "status_kind": "reserved", "status": "Reserved"}
            ],
        },
    }


def _oi_link(inquiry_no: str) -> str:
    return build_order_inquiry_link(f"oi-{inquiry_no}")


# --------------------------------------------------------------------------------- #
# AC-1..AC-3: the link                                                               #
# --------------------------------------------------------------------------------- #


def test_ac_1_one_context_links_its_request():
    ctx = _context("OI-1", "req-a")
    assert merged_context([ctx])["reserve"]["link"] == f"{_oi_link('OI-1')}?reserve=req-a"


def test_ac_2_two_requests_of_one_oi_link_both_in_first_seen_order():
    contexts = [_context("OI-1", "req-b"), _context("OI-1", "req-a")]
    assert merged_context(contexts)["reserve"]["link"] == f"{_oi_link('OI-1')}?reserve=req-b,req-a"


def test_ac_2_two_contexts_of_the_same_request_give_one_id():
    contexts = [_context("OI-1", "req-a"), _context("OI-1", "req-a")]
    assert merged_context(contexts)["reserve"]["link"] == f"{_oi_link('OI-1')}?reserve=req-a"


def test_ac_3_two_ois_link_the_lines_view_with_their_requests_in_oi_order():
    contexts = [_context("OI-2", "req-2"), _context("OI-1", "req-1")]
    link = merged_context(contexts)["reserve"]["link"]
    assert link == (
        f"{build_order_inquiry_link(None)}?display=lines&inquiry_no=OI-1,OI-2"
        "&reserve_request=req-1,req-2"
    )


def test_ac_3_twenty_one_ois_carry_twenty_one_ids_no_cap():
    contexts = [_context(f"OI-{n:02d}", f"req-{n:02d}") for n in range(21)]
    link = merged_context(contexts)["reserve"]["link"]
    ids = link.split("&reserve_request=")[1].split(",")
    assert ids == [f"req-{n:02d}" for n in range(21)]


def test_request_context_builders_carry_the_request_id(sn, monkeypatch):
    client, world = sn
    _register()
    _captured_dispatches(monkeypatch)
    inquiry, rows = _oi(world, world.requester, [_line("A"), _line("B")])
    request_id = _ask(client, world, inquiry, rows[:1], [_line("A")], park=False)
    from app.models.project_so import OrderInquiryReserveRequest
    from app.services.order_inquiry_reserve_service import _build_context

    request = world.db.get(OrderInquiryReserveRequest, request_id)
    context = _build_context(world.db, request, [], actor_user_id=None)
    assert context["reserve"]["request_id"] == str(request_id)


# --------------------------------------------------------------------------------- #
# AC-4 / AC-5: the filter                                                            #
# --------------------------------------------------------------------------------- #


def _round_world(client, world):
    """One OI, rows A..D. Request 1 asks A, B, C (answered: full, partial, rejected); D is never
    asked in it. Request 2 asks D only (left open). Returns (ids by item, request 1, request 2)."""
    lines = [_line(item=i, qty="100", ask="100") for i in "ABCD"]
    inquiry, rows = _oi(world, world.requester, lines)
    first = _ask(client, world, inquiry, rows[:3], lines[:3], park=False)
    a_entry = _reserve(world, rows[0], "100")
    b_entry = {**_reserve(world, rows[1], "40"), "reason": "short stock"}
    c_entry = {**_reserve(world, rows[2], "0"), "reason": "none left"}
    _commit(world, inquiry, reserves=[a_entry, b_entry, c_entry])
    second = _ask(client, world, inquiry, rows[3:], lines[3:], park=False)
    return {r.item_code.rsplit("-", 1)[1]: r.id for r in rows}, first, second


def _ids(client, url, **params):
    return _ok(client.get(url, params={"limit": 100, **params}))


def test_ac_4_reserve_request_returns_exactly_that_requests_rows_in_any_answer(sn, monkeypatch):
    client, world = sn
    _register()
    _captured_dispatches(monkeypatch)
    by_item, first, second = _round_world(client, world)
    ours = set(by_item.values())

    def listed(**params):
        return {r["id"] for r in _ids(client, LIST, **params)["data"]} & ours

    assert listed(reserve_request=first) == {by_item[k] for k in "ABC"}
    assert listed(reserve_request=second) == {by_item["D"]}
    assert listed(reserve_request=f"{first},{second}") == ours
    assert listed() == ours

    summary = _ids(client, SUMMARY, reserve_request=first)
    assert summary["total_rows"] == 3


def test_ac_4_matrix_and_export_honour_reserve_request(sn, monkeypatch):
    client, world = sn
    _register()
    _captured_dispatches(monkeypatch)
    _by_item, first, _second = _round_world(client, world)
    matrix = client.get(f"{LIST}/matrix", params={"reserve_request": first, "axis": "product"})
    assert matrix.status_code == 200, matrix.text
    export = client.get(f"{LIST}/export", params={"reserve_request": first})
    assert export.status_code == 200, export.text
    # A bad id is refused on these routes too.
    assert client.get(f"{LIST}/export", params={"reserve_request": "nope"}).status_code == 422
    assert client.get(f"{LIST}/matrix", params={"reserve_request": "nope", "axis": "product"}).status_code == 422


def test_ac_5_reserve_request_that_is_not_a_uuid_is_422(sn):
    client, _world = sn
    assert client.get(LIST, params={"reserve_request": "not-a-uuid"}).status_code == 422
    assert client.get(SUMMARY, params={"reserve_request": "not-a-uuid"}).status_code == 422
    good = str(uuid.uuid4())
    assert client.get(LIST, params={"reserve_request": f"{good},not-a-uuid"}).status_code == 422
