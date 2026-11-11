"""Figure check leaves data text alone (F1) and accepts rounded figures (F2).

Plan: documentation/plans/chatbot/PLAN-agentic-unify-tools-1nov.md, section
"Fix round after crew's browser pass, 2 Nov". Pure unit tests, no DB, no LLM.

`final_reply` needs this turn's ledger to know which spans are data text; the redaction tests pass it
as `ledger=` via `_check_with_ledger` (the plan fixes the rule, not the keyword; the coder may rename
it there, in one place).
"""
from __future__ import annotations

import pytest

from app.services.chatbot.agent.loop import final_reply, verify_answer

TITLE = "ZZT browser 1613 recheck"
UUID = "8f14e45f-ceea-4d67-9f5e-0a1b2c3d4e5f"


def _ledger(data) -> dict:
    return {"c1": {"name": "crm_projects_list", "args": {}, "status": "ok", "data": data}}


def _projects(key: str = "title", value: str = TITLE) -> dict:
    return {"data": [{"id": UUID, key: value, "status": "Active"}]}


def _check(text: str, data, user_text: str = "show it"):
    """(unbacked numbers, redacted reply). The reply uses today's final_reply signature."""
    ledger = _ledger(data)
    bad, _ = verify_answer({"text": text}, ledger, user_text)
    reply, _ = final_reply({"text": text}, bad, [])
    return bad, reply


def _check_with_ledger(text: str, data):
    """As _check, but final_reply is handed the ledger (needed to know which spans are data text)."""
    ledger = _ledger(data)
    bad, _ = verify_answer({"text": text}, ledger, "show it")
    reply, _ = final_reply({"text": text}, bad, [], ledger=ledger)
    return bad, reply


def test_title_digits_in_text_are_not_reported_or_redacted():
    """F1: the title repeated verbatim is data text."""
    bad, reply = _check_with_ledger(f"The project is {TITLE}.", _projects())
    assert bad == []
    assert TITLE in reply and "could not check" not in reply


def test_title_in_other_letter_case_is_still_data_text():
    """F1: letter case does not matter."""
    bad, reply = _check_with_ledger("The project is zzt browser 1613 recheck.", _projects())
    assert bad == []
    assert "zzt browser 1613 recheck" in reply and "could not check" not in reply


def test_name_key_value_is_data_text_too():
    """F1: the key `name` is covered the same way."""
    bad, reply = _check_with_ledger("It is ZZT browser 1613 recheck.", _projects("name"))
    assert bad == []
    assert TITLE in reply and "could not check" not in reply


def test_standalone_figure_is_still_reported_and_only_it_is_redacted():
    """F1: a bad 1613 elsewhere is reported and redacted, the title's 1613 is kept."""
    bad, reply = _check_with_ledger(f"The project is {TITLE}. It has 1613 units.", _projects())
    assert bad == ["1613 units"]  # `_figures` writes the figure with its unit word
    assert TITLE in reply
    assert reply.count("could not check") == 1
    assert "1613 units" not in reply


def test_name_like_value_still_never_backs_a_figure_elsewhere():
    """F1 key rule stays: {"name": "Basin 600"} does not back "600 units"."""
    data = {"data": [{"name": "Basin 600"}]}
    bad, reply = _check("There are 600 units.", data)
    assert bad == ["600 units"]
    assert "600 units" not in reply and "could not check" in reply


def test_string_without_a_letter_is_a_plain_figure_source():
    """F1: "1613" under a non-name key backs "1613" as today."""
    bad, _ = _check("There are 1613 units.", {"data": [{"code": "1613"}]})
    assert bad == []


def test_string_with_letters_but_no_digit_protects_nothing():
    """F1: a value with no digit protects no digits (no change)."""
    bad, _ = _check("There are 1613 units.", {"data": [{"title": "Basin recheck"}]})
    assert bad == ["1613 units"]


SLA = {"average_response_time": 3.456789, "average_resolution_time": 26.04166,
       "escalation_rate": 12.345678, "total_trackings": 81}


@pytest.mark.parametrize("text", [
    "3.46 hours", "3.5 hours", "3 hours", "26.04 hours", "26 hours", "12.3%", "12%", "81 trackings",
])
def test_rounded_figure_is_backed(text):
    """F2: a source rounded half up to the written decimals backs the figure."""
    bad, reply = _check(f"It took {text}.", SLA)
    assert bad == []
    assert "could not check" not in reply


@pytest.mark.parametrize("text,written", [
    ("3.45 hours", "3.45"), ("3.47 hours", "3.47"), ("4 hours", "4"), ("12.4%", "12.4%"),
])
def test_wrongly_rounded_figure_is_reported_and_redacted(text, written):
    """F2: 3.456789 never backs 3.45, 3.47 or 4; 12.345678 never backs 12.4."""
    bad, reply = _check(f"It took {text}.", SLA)
    assert bad == [written]
    assert "could not check" in reply


def test_whole_source_never_backs_extra_precision():
    """F2: a whole 12 does not back 12.3."""
    bad, _ = _check("There are 12.3 of them.", {"count": 12})
    assert bad == ["12.3"]


def test_rounding_is_half_up():
    """F2 (narrowed): 2.225 has 3 places, so it backs 2.23 (half up) and not 2.22."""
    assert _check("It is 2.23.", {"value": 2.225})[0] == []
    assert _check("It is 2.22.", {"value": 2.225})[0] == ["2.22"]


def test_two_decimal_source_is_not_rounded():
    """F2 narrowed: 2.25 has only 2 places, so it does not back 2.3."""
    assert _check("It is 2.3.", {"value": 2.25})[0] == ["2.3"]
    assert _check("It is 2.25.", {"value": 2.25})[0] == []


def test_column_total_is_rounded_too():
    """F2: rows 1.004 + 2.003 total 3.007: backs 3.01, 3.0 and 3, not 3.00 or 3.1."""
    data = {"data": [{"amount": 1.004}, {"amount": 2.003}]}
    assert _check("Total 3.01.", data)[0] == []
    assert _check("Total 3.", data)[0] == []
    assert _check("Total 3.00.", data)[0] == ["3.00"]
    assert _check("Total 3.0.", data)[0] == []
    assert _check("Total 3.1.", data)[0] == ["3.1"]


def test_users_own_figure_stays_exact():
    """F2: the user's 3.456789 does not back a rounded 3.46."""
    bad, _ = verify_answer({"text": "It is 3.46."}, _ledger({"data": []}), "is it 3.456789?")
    assert bad == ["3.46"]


# ------------------------------------------------------------------ review round 2: F1 edges


def _edge(text: str, data):
    """(unbacked, redacted reply) through verify_answer then final_reply with the ledger."""
    return _check_with_ledger(text, data)


@pytest.mark.parametrize("value,key,text,written", [
    ("RM 12", "description", "RM 12.75", "RM 12.75"),
    ("RM 1250", "description", "RM 1250.50", "RM 1250.50"),
    ("RM 600", "description", "RM 600,000", "RM 600,000"),
])
def test_data_string_does_not_cover_a_longer_figure_to_its_right(value, key, text, written):
    """F1 edges: a data string is data text only where it stands whole (not followed by `.` or `,` and a digit)."""
    bad, reply = _edge(f"It costs {text} each.", {"data": [{key: value}]})
    assert bad == [written]
    assert written not in reply and "could not check" in reply


def test_title_does_not_cover_a_thousands_figure_to_its_right():
    """F1 edges: "Tower 2" never covers "Tower 2,000 units"."""
    bad, reply = _edge("Tower 2,000 units sold.", {"data": [{"title": "Tower 2"}]})
    assert bad and any("2,000" in b for b in bad), bad
    assert "2,000" not in reply


def test_data_string_does_not_cover_a_figure_with_more_digits_to_its_left():
    """F1 edges: "5 pcs" and "10 pcs" in the rows never cover "Total 25 pcs"."""
    data = {"data": [{"qty": "5 pcs"}, {"qty": "10 pcs"}]}
    bad, reply = _edge("Total 25 pcs.", data)
    assert bad == ["25 pcs"]
    assert "25 pcs" not in reply


def test_data_string_does_not_cover_a_longer_number_before_it():
    """F1 edges: "51 (O/S: 36)" in the data never covers "151 (O/S: 36)"."""
    bad, reply = _edge("Stock is 151 (O/S: 36).", {"data": [{"stock": "51 (O/S: 36)"}]})
    assert bad == ["151"]
    assert "151" not in reply


def test_whole_title_with_punctuation_and_spaces_around_it_is_still_protected():
    """F1 edges guard: punctuation and spaces around the title are fine."""
    bad, reply = _edge(f"Project {TITLE}, done.", _projects())
    assert bad == []
    assert TITLE in reply and "could not check" not in reply


def test_redaction_keeps_the_title_when_the_standalone_figure_is_written_alike():
    """F1 redaction: "1613" standing alone is redacted once, the title's own 1613 stays."""
    bad, reply = _edge(f"The project is {TITLE}. It has 1613 open.", _projects())
    assert bad == ["1613"]
    assert TITLE in reply
    assert reply.count("could not check") == 1


def test_data_text_blanker_is_none_when_the_answer_repeats_no_data_string():
    """F1 cost: `_data_text_blank(ledger, text)` takes the answer text and compiles only strings that occur
    in it; 2,000 rows the answer never repeats give None. (The coder adds the second argument.)"""
    from app.services.chatbot.agent.loop import _data_text_blank

    rows = [{"title": f"Item X{i:04d}"} for i in range(2000)]
    assert _data_text_blank(_ledger({"data": rows}), "There are 5 open.") is None


# ------------------------------------------------------------------ review round 2: F2 narrowed


def test_money_stays_exact():
    """F2 narrowed: 44.80 backs 44.80 and 44.8 only, never 45 or 44.5."""
    data = {"price": 44.80}
    assert _check("It is 44.80.", data)[0] == []
    assert _check("It is 44.8.", data)[0] == []
    assert _check("It is 45.", data)[0] == ["45"]
    assert _check("It is 44.5.", data)[0] == ["44.5"]


def test_a_list_of_two_decimal_prices_backs_only_exact_figures():
    """F2 narrowed: 100 prices 10.05 ... 19.95 do not back an invented whole 15."""
    prices = [{"price": round(10.05 + 0.1 * i, 2)} for i in range(100)]
    data = {"data": prices}
    assert _check("It is 15.05.", data)[0] == []
    assert _check("It is 15.", data)[0] == ["15"]


def test_no_rounding_for_a_unit_multiplier():
    """F2 narrowed: 1.2345 does not back "1.2k units"."""
    assert _check("About 1.2k units.", {"rate": 1.2345})[0] == ["1.2k"]


def test_non_finite_numbers_back_nothing_and_do_not_raise():
    """F2 narrowed: NaN and infinity among the numbers: no exception, an unbacked 7.5 is reported."""
    data = {"a": float("nan"), "b": float("inf"), "c": 2.5, "d": float("-inf")}
    bad, _ = verify_answer({"text": "It is 7.5."}, _ledger(data), "show it")
    assert bad == ["7.5"]
