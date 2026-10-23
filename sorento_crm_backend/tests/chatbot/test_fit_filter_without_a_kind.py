"""P5: a `fits` filter with no link kind that links nothing is no fit ask.

Live (v92, TRAIN): "can send photo of srtwb1610 basin" parsed correctly (product, category,
attachment_type product_photos) but also carried a find filter {key fits, value "basin", kind null,
file_word "photo"}. The kind-less filter is every kind; with no link on record the lane built the
no-link line from the first kind ("No seat cover is on record for SRTWB1610.") and that line was
the whole reply, so the photo was never fetched. A kind-less fit ask that links nothing leaves the
turn as typed; a NAMED kind keeps its no-link line.
"""
from __future__ import annotations

from tests.chatbot.test_chat_fit_line import CAB1, MIRROR1, SHELF1, WC_NONE, _seed, fits
from tests.chatbot.test_seat_as_product import _codes, _scoped, _verdict


def _linked(session_factory, code, find):
    from app.services.chatbot.lanes.business import find as find_lane

    _seed(session_factory)
    return find_lane.as_linked_products(_scoped(session_factory), _verdict(code, find=find))


def test_a_kindless_fit_filter_over_an_unlinked_code_is_no_fit_ask(session_factory):
    out, lines = _linked(session_factory, WC_NONE, fits(None, "basin", file_word="photo"))
    assert lines == [], lines
    assert out["find"] is None
    assert _codes(out) == [WC_NONE]


def test_guard_a_named_kind_over_an_unlinked_code_still_gives_the_no_link_line(session_factory):
    _out, lines = _linked(session_factory, WC_NONE, fits("seat_cover", "seat cover"))
    assert lines == [f"No seat cover is on record for {WC_NONE}."]


def test_guard_a_kindless_fit_ask_over_a_linked_code_still_answers_the_links(session_factory):
    out, lines = _linked(session_factory, CAB1, fits(None, "goes with"))
    assert _codes(out) == [MIRROR1, SHELF1] and lines == []


def test_p5b_a_kindless_fit_ask_with_no_file_word_keeps_the_no_link_line(session_factory):
    """"what goes with <WC>" / "what accessories fit <WC>": no kind and no file word is a real fit
    ask over a code that links nothing, so it still gets its no-link line."""
    from app.services.chatbot.lanes.business import find as find_lane

    _seed(session_factory)
    for value in ("goes with", "accessories"):
        _out, lines = find_lane.as_linked_products(_scoped(session_factory), _verdict(WC_NONE, find=fits(None, value)))
        assert lines == [f"No seat cover is on record for {WC_NONE}."], (value, lines)
