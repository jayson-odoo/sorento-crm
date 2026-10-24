"""REPORT-SMART-L one ranking, round R3d (AC-OR3d): an ms / zh contact reads the ranking's head line, the
miss line, the route refusals and the Period range in the contact's language. The presenter (shared
with n8n) stays English; the backend's `label_catalog` is the only place that translates. Fake names only."""
from __future__ import annotations

import pytest

from app.services.chatbot import engine, label_catalog
from app.services.chatbot.label_catalog import Localizer
from tests.chatbot.test_one_ranking_r3a import _body, _structure
from tests.chatbot.test_one_ranking_r1 import (  # noqa: F401 - fixtures + helpers
    _top_selling,
    console,
    stub_access,
)
from tests.chatbot.test_report_ask_lane import _say_all, DIMENSION_REFUSAL

OWN_ACCOUNT = "You can only see sales for your own account."


def _lines(body, lang):
    return _structure(body, lang)["response"].split("\n")


def _head(lang, **over):
    return _lines(_body(**over), lang)[0]


def _head_en(**over):
    return _head(None, **over)


NOUNS = {
    "ms": {"product": "produk", "category": "kategori", "customer": "pelanggan", "brand": "jenama",
           "sales_agent": "ejen jualan", "location": "lokasi", "channel": "saluran", "month": "bulan"},
    "zh": {"product": "产品", "category": "类别", "customer": "客户", "brand": "品牌",
           "sales_agent": "销售代理", "location": "位置", "channel": "渠道", "month": "月份"},
}


def _more(group_by, n=2, total=None):
    rows = [{"rank": i + 1, "name": f"ZZT-ROW-{i + 1}", "qty": 10, "amount": 100.0, "count": 3} for i in range(n)]
    over = {"group_by": group_by, "group_label": group_by.replace("_", " ").title(), "rows": rows}
    if total:
        over.update(total_count=total, more=total - n)
    return over


# ---------------------------------------------------------------- a. the head line


@pytest.mark.parametrize("lang", ["ms", "zh"])
@pytest.mark.parametrize("group_by", ["product", "category", "customer", "brand", "sales_agent", "location", "channel", "month"])
def test_r3d_a_every_sales_group_by_head_is_translated(lang, group_by) -> None:
    english = _head_en(**_more(group_by))
    head = _head(lang, **_more(group_by))
    assert head != english, head
    assert NOUNS[lang][group_by] in head, head
    assert "Top" not in head and "delivered" not in head and " by " not in head, head
    assert "2" in head, head


@pytest.mark.parametrize("lang, top, bottom, basis", [
    ("ms", "teratas", "terbawah", "jualan dihantar"),
    ("zh", "前", "后", "已送货销售"),
])
def test_r3d_a_top_bottom_and_the_basis_translate(lang, top, bottom, basis) -> None:
    assert top in _head(lang, **_more("product")) and basis in _head(lang, **_more("product"))
    asc = _head(lang, sort="asc", basis_label="ordered sales", **_more("category"))
    assert bottom in asc and NOUNS[lang]["category"] in asc, asc
    assert "Bottom" not in asc and "ordered" not in asc, asc
    out = _head(lang, basis_label="outstanding orders", **_more("customer"))
    assert "outstanding" not in out, out


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_r3d_a_of_total_keeps_both_numbers(lang) -> None:
    head = _head(lang, **_more("product", 2, 37))
    assert "37" in head and "2" in head and "Top" not in head and " of " not in head, head
    big = _head(lang, **_more("product", 2, 1234))
    assert "1,234" in big, big


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_r3d_a_a_one_row_head_is_singular_and_translated(lang) -> None:
    head = _head(lang, **_more("product", 1))
    assert NOUNS[lang]["product"] in head and "Top" not in head and "product" not in head, head


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_r3d_a_a_count_measure_head_is_translated(lang) -> None:
    head = _head(lang, measure="customers", **_more("product", 2, 37))
    assert "Top" not in head and "customers" not in head and "delivered" not in head, head
    assert "37" in head and ("bilangan pelanggan" if lang == "ms" else "客户数") in head, head
    one = _head(lang, measure="customers", **_more("product", 1, 2))
    assert "Top" not in one and "customers" not in one and "customer" not in one, one


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_r3d_a_the_number_shape_head_is_translated(lang) -> None:
    out = _lines(_body(group_by="", group_label="", rows=[], total={"qty": 45, "amount": 1800.0}), lang)[0]
    assert "Sales by" not in out and "delivered" not in out, out


# ---------------------------------------------------------------- b. the miss line


@pytest.mark.parametrize("lang, word", [("ms", "Tiada"), ("zh", "未找到")])
@pytest.mark.parametrize("basis_label", ["delivered sales", "ordered sales", "outstanding orders"])
def test_r3d_b_the_miss_line_translates_per_basis(lang, word, basis_label) -> None:
    first = _lines(_body(rows=[], basis_label=basis_label, total_count=0), lang)[0]
    assert word in first and "found" not in first and "sales" not in first and "orders" not in first, first


# ---------------------------------------------------------------- c. route refusals, end to end


@pytest.mark.parametrize("lang, expect", [("ms", "akaun anda"), ("zh", "")])
@pytest.mark.parametrize("message", [OWN_ACCOUNT, DIMENSION_REFUSAL])
def test_r3d_c_a_route_refusal_is_translated_by_the_final_reply_pass(console, monkeypatch, lang, expect, message) -> None:
    console.refuse = {"message": message, "detail": None, "code": "customer_not_permitted"}
    text, log = _say_all(console, monkeypatch, _top_selling(top_n=5, measure="qty", basis="delivered"), "top 5 items this year")
    assert text.strip() == message, text  # the lane says the route's message (English, the engine pass localizes)
    done = Localizer(lang, label_catalog.defaults(lang)).reply(text)
    assert done != text and message not in done, done
    assert len(done.strip()) > 8 and "account" not in done, done
    assert (expect in done) if expect else any("\u4e00" <= ch <= "\u9fff" for ch in done), done


# ---------------------------------------------------------------- d. the period range


@pytest.mark.parametrize("lang, joiner", [("ms", "hingga"), ("zh", "至")])
def test_r3d_d_the_period_range_is_localized(lang, joiner) -> None:
    line = next(ln for ln in _lines(_body(), lang) if ln.startswith(("Tempoh", "期间")))
    assert joiner in line and " to " not in line, line
    assert "1 Sep 2026" in line and "30 Sep 2026" in line, line


# ---------------------------------------------------------------- e. guards


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_r3d_e_rank_lines_names_and_codes_are_unchanged(lang) -> None:
    english = _lines(_body(**_more("product", 2, 37)), None)
    translated = _lines(_body(**_more("product", 2, 37)), lang)
    rows = [ln for ln in english if ln.startswith(("1. ", "2. ", "Total", "and "))]
    assert rows and all(r in translated for r in rows if not r.startswith("and ")), translated


def test_r3d_e_english_with_the_localizer_is_byte_identical_to_no_localizer() -> None:
    # Pins the en path: `defaults("en")` is empty, so the localizer must be a pass-through.
    for over in (_more("product", 2, 37), {"rows": [], "total_count": 0}, {"sort": "asc"}):
        assert _structure(_body(**over), "en")["response"] == _structure(_body(**over), None)["response"]


@pytest.mark.parametrize("lang", ["ms", "zh"])
@pytest.mark.parametrize("line", [
    "Top 2 widgets by delivered sales",
    "Top 2 products by shipped sales",
    "Top 2 products by customers, shipped sales",
    "Top 2 products by shipped, delivered sales",
    "No shipped sales found",
])
def test_r3d_e_a_head_shaped_line_with_an_unknown_word_is_unchanged(lang, line) -> None:
    localizer = Localizer(lang, label_catalog.defaults(lang))
    assert localizer.lines(line) == line and localizer.reply(line) == line


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_r3d_e_a_long_ranking_keeps_its_part_markers_after_localization(lang) -> None:
    body = _body(**_more("product", 259))
    english = _structure(body, None)["response"]
    translated = _structure(body, lang)["response"]
    en_parts, tr_parts = engine.split_marked_message(english), engine.split_marked_message(translated)
    assert len(en_parts) > 1 and len(tr_parts) == len(en_parts), (len(en_parts), len(tr_parts))
    head = next(ln for ln in translated.split("\n") if not ln.startswith("("))
    assert head != next(ln for ln in english.split("\n") if not ln.startswith("(")), head


# ---------------------------------------------------------------- f. the one question, end to end


@pytest.mark.parametrize("lang, marker", [("ms", "Mengikut kuantiti atau amaun?"), ("zh", "按数量还是按金额？")])
def test_r3d_f_the_one_ranking_question_renders_in_the_contacts_language(console, monkeypatch, lang, marker) -> None:
    text, log = _say_all(console, monkeypatch, _top_selling(), "top selling items")
    done = Localizer(lang, label_catalog.defaults(lang)).reply(text)
    assert marker in done, done
    assert "By quantity or by amount?" not in done, done


# ---------------------------------------------------------------- review follow-ups


@pytest.mark.parametrize("lang", ["ms", "zh"])
@pytest.mark.parametrize("text", ["products", "1. month", "*customer*", "delivered sales", "category", "customers (count)"])
def test_r3d_g_the_vocabulary_words_alone_are_never_rewritten(lang, text) -> None:
    localizer = Localizer(lang, label_catalog.defaults(lang))
    assert localizer.reply(text) == text and localizer.sentence(text) == text
    assert localizer.lines(text) == text


@pytest.mark.parametrize("lang, word", [("ms", "bilangan"), ("zh", "数")])
def test_r3d_g_a_count_measure_reads_as_a_count_not_a_grouping(lang, word) -> None:
    for measure in ("customers", "orders", "products"):
        head = _head(lang, measure=measure, **_more("product", 2, 37))
        assert word in head and measure not in head, head


@pytest.mark.parametrize("lang, label, joiner", [("ms", "Berbanding dengan", "hingga"), ("zh", "对比期间", "至")])
def test_r3d_g_the_compared_with_line_is_localized(lang, label, joiner) -> None:
    body = _body(compare_to="previous", compare_from="2026-08-01", compare_until="2026-08-31")
    line = next(ln for ln in _lines(body, lang) if ln.startswith(label))
    assert joiner in line and " to " not in line and "1 Aug 2026" in line, line


@pytest.mark.parametrize("lang", ["ms", "zh"])
def test_r3d_g_the_orders_refusal_is_translated(lang) -> None:
    msg = "You can only see orders for your own account."
    done = Localizer(lang, label_catalog.defaults(lang)).reply(msg)
    assert done != msg and "orders" not in done, done
