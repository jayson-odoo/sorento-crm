"""FULFIL-SO-REMARK rules module (AC-3..AC-6) and the card cases, pure functions."""
from __future__ import annotations

import pytest

from app.services import so_remark_rules as r


def test_mockup_word():
    assert r.MOCKUP_WORD == "Mockup"


# AC-3
@pytest.mark.parametrize("text", ["***FOR MOCKUP", "mock up", "MOCK-UP", "Mockup", "mock"])
def test_ac3_each_source_marks_a_mockup_line(text):
    assert r.is_mockup_line(text, None, None) is True
    assert r.is_mockup_line(None, text, None) is True
    assert r.is_mockup_line(None, None, text) is True


def test_ac3_nothing_mock_is_not_a_mockup_line():
    assert r.is_mockup_line(None, None, None) is False
    assert r.is_mockup_line("Deliver to site", "ship Friday", "BLOCK 1 & 3 - JUL 27") is False


# AC-4
@pytest.mark.parametrize(
    "ship_info,expected",
    [
        ("SPONSORSHIP", "Sponsorship"),
        ("sponsorship", "Sponsorship"),
        ("PURCHASE REQUEST", "Purchase Request"),
        ("purchase req", "Purchase Request"),
        ("PR26-0375", "Purchase Request"),
        ("  pr26-0375", "Purchase Request"),
        ("PRR26-0120", None),
        ("OT06/2702", None),
        ("PRIORITY", None),
        ("", None),
        (None, None),
    ],
)
def test_ac4_remark_type(ship_info, expected):
    assert r.remark_type(ship_info) == expected


def test_ac4_sponsorship_wins_over_purchase_request():
    assert r.remark_type("SPONSORSHIP PURCHASE REQUEST") == "Sponsorship"


# AC-5
def test_ac5_remark_type_beats_mockup():
    assert r.default_remark("Sponsorship", [True]) == "Sponsorship"
    assert r.default_remark("Purchase Request", [True, False]) == "Purchase Request"


def test_ac5_mockup_when_any_chosen_line_is_mockup():
    assert r.default_remark(None, [False, True, False]) == "Mockup"


def test_ac5_blank_otherwise():
    assert r.default_remark(None, [False, False]) == ""
    assert r.default_remark(None, []) == ""


# AC-6
def test_ac6_label_only_when_mixed():
    assert r.label_lines([True, False]) is True
    assert r.label_lines([True, True]) is False
    assert r.label_lines([False, False]) is False
    assert r.label_lines([]) is False


# Card cases
def test_card_so419417_all_24_chosen():
    flags = [True] * 3 + [False] * 21
    assert r.default_remark(r.remark_type("U 2603-00010"), flags) == "Mockup"
    assert r.label_lines(flags) is True


def test_card_so419417_only_the_3_mockup_lines():
    flags = [True] * 3
    assert r.default_remark(None, flags) == "Mockup"
    assert r.label_lines(flags) is False


def test_card_so419417_only_the_21_other_lines():
    flags = [False] * 21
    assert r.default_remark(None, flags) == ""
    assert r.label_lines(flags) is False


def test_card_so427088_note_mock_whole_so():
    flags = [r.is_mockup_line("***FOR MOCKUP", None, None) for _ in range(4)]
    assert r.default_remark(r.remark_type("OT06/2702"), flags) == "Mockup"
    assert r.label_lines(flags) is False


def test_card_so421287_sponsorship_plus_note_mock():
    flags = [r.is_mockup_line("***SPONSORSHIP (MOCKUP)***", None, None)]
    assert r.default_remark(r.remark_type("SPONSORSHIP"), flags) == "Sponsorship"


def test_card_purchase_request_shapes():
    assert r.default_remark(r.remark_type("PURCHASE REQUEST"), [False]) == "Purchase Request"
    assert r.default_remark(r.remark_type("PR26-0375"), [False]) == "Purchase Request"
    assert r.default_remark(r.remark_type("PRR26-0120"), [False]) == ""


def test_card_so421072_only_items_between_headings_are_mockup():
    # items under heading "MOCK UP - BLOCK 1" carry that section_heading; items after the
    # next heading carry "BLOCK 1 & 3 - JUL 27" (the nearest text-only line before them).
    lines = [("MOCK UP - BLOCK 1", 2), ("BLOCK 1 & 3 - JUL 27", 3)]
    flags = [r.is_mockup_line(None, None, heading) for heading, n in lines for _ in range(n)]
    assert flags == [True, True, False, False, False]
    assert r.default_remark(None, flags) == "Mockup"
    assert r.label_lines(flags) is True
