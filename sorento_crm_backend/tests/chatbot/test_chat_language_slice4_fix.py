"""CHAT-LANGUAGE slice 4 fix round: composer sentences with the domain label and the joiners,
rendered from the REAL compose output, then the final reply pass."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.chatbot import label_catalog
from app.services.chatbot.label_catalog import Localizer
from app.services.chatbot.turn.compose import compose
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.state import Focus, Profile, State

from tests.chatbot._turn_helpers import TIER_ORDER_FIXTURE, _domain_row


def _loc(lang: str) -> Localizer:
    return Localizer(lang, label_catalog.defaults(lang))


def _policy() -> Policy:
    rows = [
        {**_domain_row("inventory", narrowing={"product": "list_all"}), "label": "stock"},
        {**_domain_row("order", narrowing={"product": "list_all"}), "label": "orders"},
    ]
    return Policy.from_rows(domains=rows, kinds=[], tier_order=TIER_ORDER_FIXTURE)


def _state() -> State:
    return State(focus=Focus(), pending=None, profile=Profile(), turn_no=2)


def _env(**over) -> dict:
    env = {
        "domain": "inventory",
        "denied": False,
        "entities": ["ABC123"],
        "product_codes": ["ABC123"],
        "figures": [],
        "files": [],
        "miss": [],
        "has_result": False,
        "tool_has_result": False,
        "unresolved": [],
        "error": None,
        "lane_text": None,
    }
    env.update(over)
    return env


def _final(env: dict, lang: str) -> list[str]:
    loc = _loc(lang)
    text = compose([env], _state(), _policy(), ctx=SimpleNamespace(localizer=loc)).text
    return loc.reply(text).split("\n")


@pytest.mark.parametrize(
    "lang, header, fetch",
    [
        ("ms", "*stok* untuk ABC123:", "Saya tidak dapat mendapatkan stok sekarang, sila cuba lagi."),
        ("zh", "ABC123 的*库存*：", "暂时无法获取库存，请稍后再试。"),
    ],
)
def test_the_domain_label_reads_in_the_reply_language_in_header_and_fetch_error(lang, header, fetch):
    lines = _final(_env(error="timeout"), lang)
    assert header in lines
    assert fetch in lines


def test_the_not_enabled_line_uses_the_translated_label():
    assert "*stok*: ini tidak diaktifkan untuk akaun anda." in _final(_env(denied=True), "ms")
    assert "*库存*：您的账户未开通此功能。" in _final(_env(denied=True), "zh")


def test_the_rung_line_translates_the_labels_and_the_joiner():
    env = _env(rungs_tried=["inventory", "order"])
    assert "Tiada juga untuk stok atau pesanan." in _final(env, "ms")
    assert "库存或订单 也没有。" in _final(env, "zh")


def test_the_unplaced_line_translates_the_joiner_only_in_the_composer_list():
    env = _env(unresolved=["X", "Y"], error="timeout")
    assert "Saya tidak dapat menemui X atau Y." in _final(env, "ms")
    assert "找不到 X或Y。" in _final(env, "zh")


def test_an_or_inside_a_presenter_value_or_a_names_token_is_never_split():
    loc = _loc("ms")
    # Not a compose-joined list: the same words arrive in a value and stay as they are.
    assert loc.reply("I could not find ZZT tray or stock.") == "Saya tidak dapat menemui ZZT tray or stock."
    assert loc.reply("Nothing on stock or orders either.") == "Tiada juga untuk stock or orders."
    assert loc.reply("*stock* for A:") == "*stock* untuk A:"
