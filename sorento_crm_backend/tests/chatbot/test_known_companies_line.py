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


# ------------------------------------------------------------------------------------------ the contact-companies read


def _record_company_reads(bot) -> list[int]:
    """Counts the reads of the contact's companies that `engine._contact_companies` makes (one entry per read)."""
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.head import parser as parser_mod
    from app.services.chatbot.lanes.business import sales_company_ask

    mp = bot.console.monkeypatch
    reads: list[int] = []
    inside = {"on": False}
    real_inner, real_outer = sales_company_ask._companies, engine_mod._contact_companies

    def inner(*a, **k):
        if inside["on"]:
            reads.append(1)
        return real_inner(*a, **k)

    def outer(*a, **k):
        inside["on"] = True
        try:
            return real_outer(*a, **k)
        finally:
            inside["on"] = False

    mp.setattr(sales_company_ask, "_companies", inner)
    mp.setattr(engine_mod, "_contact_companies", outer)
    assert parser_mod.REPORT_ASK_LINE
    return reads


def _report_ask_prompt(extra: str) -> str:
    from app.services.chatbot.head import parser as parser_mod

    return f"Rules {{{{current_date}}}}.\n{parser_mod.REPORT_ASK_LINE}\n{extra}\n"


def test_kc5_a_text_with_the_report_ask_but_neither_said_as_nor_known_companies_never_reads_the_contact_companies(bot) -> None:
    _two_companies(bot)
    blocks = _use_prompt(bot, _report_ask_prompt("Nothing about the companies here."))
    reads = _record_company_reads(bot)
    bot.say(_sales(_word()), "sales for cabana in Jan")
    assert blocks and reads == [], f"KC-5: {len(reads)} contact-companies read(s) for a text that needs none"


def test_kc5_lock_a_text_with_said_as_reads_the_contact_companies_once_per_turn(bot) -> None:
    _two_companies(bot)
    _use_prompt(bot, _report_ask_prompt('Each entity carries "said_as".'))
    reads = _record_company_reads(bot)
    bot.say(_sales(_word()), "sales for cabana in Jan")
    assert len(reads) == 1, f"KC-5 lock (said_as): {len(reads)} reads"


def test_kc5_lock_a_text_with_known_companies_reads_the_contact_companies_once_per_turn(bot) -> None:
    _two_companies(bot)
    _use_prompt(bot, _report_ask_prompt("Known companies lists the companies the contact holds."))
    reads = _record_company_reads(bot)
    bot.say(_sales(_word()), "sales for cabana in Jan")
    assert len(reads) == 1, f"KC-5 lock (Known companies): {len(reads)} reads"
