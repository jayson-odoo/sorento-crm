"""CHATBOT-TOTALS-FILTERS round 7: the `Known companies:` parser user-block line (KC-1..4).

Mirrors the `Known account types:` line (test_sales_account_type_lane at36): data-built, gated on a phrase in the
prompt text, so the parser can tell which brand names are also companies. Fake data only."""
from __future__ import annotations

from tests.chatbot.test_sales_account_type_lane import (  # noqa: F401  (bot / console / _fresh_prompt_cache are fixtures)
    _fresh_prompt_cache,
    _sales,
    _sent_schema,
    _use_prompt,
    _word,
    bot,
    console,
)
from tests.chatbot.test_report_unify_company_lane import _two_companies

PHRASE_PROMPT = "Rules {{current_date}}. Known companies lists the companies the contact holds.\n"
PLAIN_PROMPT = "Rules {{current_date}}. Nothing about companies here.\n"


def _line(block: str) -> list[str]:
    return [ln for ln in block.splitlines() if ln.startswith("Known companies")]


def test_kc1_a_prompt_with_the_phrase_and_a_two_company_contact_gets_the_sorted_names_line(bot) -> None:
    sorento, mocha = _two_companies(bot)
    blocks = _use_prompt(bot, PHRASE_PROMPT)
    bot.say(_sales(_word()), "sales for cabana in Jan")
    want = f"Known companies: {', '.join(sorted([sorento, mocha], key=lambda n: (n.casefold(), n)))}"
    assert _line(blocks[-1]) == [want], blocks[-1]


def test_kc2_a_prompt_without_the_phrase_gets_no_line(bot) -> None:
    _two_companies(bot)
    blocks = _use_prompt(bot, PLAIN_PROMPT)
    bot.say(_sales(_word()), "sales for cabana in Jan")
    assert _line(blocks[-1]) == [], blocks[-1]
    assert "Known companies" not in blocks[-1], blocks[-1]


def test_kc3_a_one_company_contact_gets_no_line_even_with_the_phrase(bot) -> None:
    blocks = _use_prompt(bot, PHRASE_PROMPT)
    bot.say(_sales(_word()), "sales for cabana in Jan")
    assert _line(blocks[-1]) == [], blocks[-1]


def test_kc4_the_parser_config_flags_the_phrase(monkeypatch, session_factory) -> None:
    with_phrase, _s = _sent_schema(monkeypatch, session_factory, "Rules {{current_date}} compare_to by_words Known companies.\n")
    assert with_phrase.known_companies is True, with_phrase


def test_kc4_a_text_without_the_phrase_leaves_the_flag_false(monkeypatch, session_factory) -> None:
    without, _s = _sent_schema(monkeypatch, session_factory, "Rules {{current_date}} compare_to by_words.\n")
    assert without.known_companies is False, without
