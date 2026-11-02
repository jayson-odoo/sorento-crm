"""STOCK-INCOMING-FLOOR Fix B, AC-SIF11 (owner, 2 Nov 2026): the "(delayed)" marker a dealer's
stock check and ETA ask print after a past told date reads "(lewat)" in ms and "（延迟）" in zh.
Pure: no database. Fake codes and dates."""
from __future__ import annotations

import pytest

from app.services.chatbot import label_catalog
from app.services.chatbot.label_catalog import Localizer

MARKS = {"ms": "(lewat)", "zh": "（延迟）"}


def _loc(lang: str) -> Localizer:
    return Localizer(lang, label_catalog.defaults(lang))


def _mark() -> str:
    """The English marker, literal: these tests pin the translation, `test_incoming_contact_rules`
    pins the constant."""
    return "(delayed)"


def _assert_translated(out: str, lang: str) -> None:
    assert MARKS[lang] in out, out
    assert "(delayed)" not in out, out
    assert "15/10/2026" in out and "03/11/2026" in out, out


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_the_stock_line_translates_the_marker(lang):
    english = f"SRTZZ1 x 5: ❌ No stock, ETA 15/10/2026 {_mark()}, 03/11/2026."
    _assert_translated(_loc(lang).tail(english), lang)
    _assert_translated(_loc(lang).reply(f"No stock, ETA 15/10/2026 {_mark()}, 03/11/2026."), lang)


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_the_dealer_eta_line_translates_the_marker(lang):
    english = f"SRTZZ1: ✅ ETA 15/10/2026 {_mark()}, 03/11/2026"
    _assert_translated(_loc(lang).tail(english), lang)
    _assert_translated(_loc(lang).reply(english), lang)


def test_english_keeps_the_marker():
    english = f"SRTZZ1: ✅ ETA 15/10/2026 {_mark()}"
    assert label_catalog.IDENTITY.tail(english) == english
