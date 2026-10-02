"""CHAT-LANGUAGE fix round 1, items 4 to 6: text matchers, the refer line, the stock-only scope."""
from __future__ import annotations

from app.services.chatbot import label_catalog
from app.services.chatbot.label_catalog import Localizer
from app.services.chatbot.lanes.business import answer as answer_mod
from app.services.chatbot.lanes.business import fetch

TS = "2026-10-02T09:15:30"


def _loc(lang: str) -> Localizer:
    return Localizer(lang, label_catalog.defaults(lang))


# --------------------------------------------------------------------------- #
# Item 4 (S1): the footer matchers recognise the localized footer
# --------------------------------------------------------------------------- #


def test_item4_a_counted_set_with_other_brands_keeps_the_ms_footer_last():
    envelope = {
        "result_type": "stock",
        "intro": "Stock summary for the requested products.",
        "items": [
            {
                "title": "SRTTP1",
                "fields": [{"key": "product_code", "label": "Product Code", "value": "SRTTP1"}],
                "flags": {},
            }
        ],
        "has_result": True,
        "last_updated_at": TS,
    }
    ctx = {
        "semantic_input": {},
        "tool": "crm_inventory_stock_balance_list",
        "localizer": _loc("ms"),
        "predicate": {
            "qualifying_total": 1,
            "require": {"stock": True},
            "class_labels": ["tap"],
            "other_brands": [{"brand": "Bravat", "count": 79}],
        },
    }
    text = fetch.output_structurer(envelope, ctx)["response"]
    footer = "_Data dikemas kini: 02/10/2026 09:15:30_"
    assert text.endswith(footer), text
    assert text.index("Other brands") < text.index(footer), text


def test_item4_the_promo_footer_regex_matches_every_language():
    for lang in ("ms", "zh"):
        footer = _loc(lang).text("Data last updated: 02/10/2026 09:15:30")
        match = answer_mod._DATA_LAST_UPDATED_RE.search(f"intro\n\n_{footer}_")
        assert match and match.group(0) == f"_{footer}_", lang
    english = answer_mod._DATA_LAST_UPDATED_RE.search("x\n_Data last updated: 02/10/2026 09:15:30_")
    assert english is not None


# --------------------------------------------------------------------------- #
# Item 5 (S4): the refer line is recognised in every language
# --------------------------------------------------------------------------- #


def test_item5_refer_sentences_cover_the_three_languages():
    sentences = label_catalog.refer_sentences()
    assert "Sila rujuk jurujual anda." in sentences
    assert "请联系您的销售员。" in sentences
    assert len(sentences) == 3


def test_item5_an_ms_verdict_plus_an_escalation_offer_does_not_double_the_refer_line():
    from app.services.chatbot import dealer_stock

    ms = "A1 x 1: ya, stok ada. Sila rujuk jurujual anda."
    text, question = dealer_stock.without_escalation(
        f"{ms}\n\nWould you like me to escalate to the warehouse team?", None
    )
    assert text == ms
    assert question is None
    zh = "A1 x 1: 有库存。请联系您的销售员。"
    text, _ = dealer_stock.without_escalation(
        f"{zh}\n\nWould you like me to escalate to the warehouse team?", None
    )
    assert text == zh


# --------------------------------------------------------------------------- #
# Item 6 (S5): only the stock tool is localized in this slice
# --------------------------------------------------------------------------- #


def test_item6_a_po_placed_envelope_with_an_ms_localizer_stays_english():
    envelope = {
        "result_type": "po_placed",
        "intro": "Stock summary for the requested products.",
        "items": [
            {
                "title": "PO-1",
                "fields": [
                    {"key": "product_code", "label": "Product Code", "value": "SRTSWT3001"},
                    {"label": "Total", "value": 51},
                ],
                "flags": {"discontinued": True},
            }
        ],
        "has_result": True,
        "last_updated_at": TS,
    }
    ctx = {"semantic_input": {}, "tool": "crm_procurement_po_placed_list", "localizer": _loc("ms")}
    text = fetch.output_structurer(envelope, ctx)["response"]
    assert "*Product Code:* SRTSWT3001" in text
    assert "*Total:* 51" in text
    assert "PRODUCT DISCONTINUED" in text
    assert "_Data last updated: 02/10/2026 09:15:30_" in text
    assert "Jumlah" not in text and "Ringkasan" not in text and "dikemas" not in text
