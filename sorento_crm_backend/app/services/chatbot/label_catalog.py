"""CHAT-LANGUAGE: the label catalog and the `Localizer` (plan `PLAN-chat-language-2oct.md`).

Only labels and fixed sentences are translated, and only the ones listed here (an allowlist):
a value, a code, a number or an uncatalogued label comes back unchanged. The key is the ENGLISH
source text, the same key `translation_memory.source_text` uses, so staff correct the wording on
the Translations page and a `manual` row wins. Pure apart from `resolve`, the one DB seam.
"""
from __future__ import annotations

import logging
import re
from typing import Any

# The one spelling of the refer line (CUSTOMER-ASKS-REFER-ONLY guards): the verdict keys below
# are built from it, never spelled out.
from app.services.chatbot.turn.task import REFER_TO_SALESMAN

logger = logging.getLogger(__name__)

LANGUAGES = ("en", "ms", "zh")

#: English source text -> {"ms": ..., "zh": ...}. `{name}` placeholders must survive translation.
LABELS: dict[str, dict[str, str]] = {
    "Company": {"ms": "Syarikat", "zh": "公司"},
    "Product Code": {"ms": "Kod Produk", "zh": "产品代码"},
    "Product Name": {"ms": "Nama Produk", "zh": "产品名称"},
    "Warehouse": {"ms": "Gudang", "zh": "仓库"},
    "System Location": {"ms": "Lokasi Sistem", "zh": "系统位置"},
    "Quantity On Hand": {"ms": "Kuantiti Ada", "zh": "现有数量"},
    "Outstanding": {"ms": "Belum Dihantar", "zh": "未交货"},
    "Total": {"ms": "Jumlah", "zh": "总数"},
    "Stock summary for the requested products.": {
        "ms": "Ringkasan stok untuk produk yang diminta.",
        "zh": "所请求产品的库存摘要。",
    },
    "Stock details found for the requested products.": {
        "ms": "Butiran stok untuk produk yang diminta.",
        "zh": "所请求产品的库存详情。",
    },
    "How many units do you need?": {
        "ms": "Berapa unit yang anda perlukan?",
        "zh": "您需要多少件？",
    },
    f"yes, we have stock. {REFER_TO_SALESMAN}": {
        "ms": "ya, stok ada. Sila rujuk jurujual anda.",
        "zh": "有库存。请联系您的销售员。",
    },
    f"no stock and no incoming at the moment. {REFER_TO_SALESMAN}": {
        "ms": "tiada stok dan tiada barang masuk buat masa ini. Sila rujuk jurujual anda.",
        "zh": "目前没有库存，也没有到货。请联系您的销售员。",
    },
    f"the quantity is more than what I can confirm here. {REFER_TO_SALESMAN}": {
        "ms": "kuantiti ini melebihi apa yang boleh saya sahkan di sini. Sila rujuk jurujual anda.",
        "zh": "这个数量超出我在这里可以确认的范围。请联系您的销售员。",
    },
    "no stock at the moment, ETA {eta}.": {
        "ms": "tiada stok buat masa ini, ETA {eta}.",
        "zh": "目前没有库存，ETA {eta}。",
    },
    "Data last updated: {ts}": {
        "ms": "Data dikemas kini: {ts}",
        "zh": "数据更新时间: {ts}",
    },
    "No stock found for {codes}.": {
        "ms": "Tiada stok ditemui untuk {codes}.",
        "zh": "未找到 {codes} 的库存。",
    },
    "Here are the results.": {"ms": "Berikut ialah hasilnya.", "zh": "以下是结果。"},
    "PRODUCT DISCONTINUED": {"ms": "PRODUK DIHENTIKAN", "zh": "产品已停产"},
}

#: Presenter field key -> English label (slice 1: the stock fields).
FIELD_KEYS: dict[str, str] = {
    "company_name": "Company",
    "product_code": "Product Code",
    "product_name": "Product Name",
    "warehouse": "Warehouse",
    "system_location": "System Location",
    "quantity_on_hand": "Quantity On Hand",
    "open_so_qty": "Outstanding",
    "total_on_hand": "Total",
}

FOOTER = "Data last updated: {ts}"

_TOKEN = re.compile(r"\{(\w+)\}")


def tokens(text: str) -> list[str]:
    """The sorted `{name}` placeholders of `text`."""
    return sorted(_TOKEN.findall(text))


def tokens_match(a: str, b: str) -> bool:
    return tokens(a) == tokens(b)


def footer_leads() -> tuple[str, ...]:
    """The footer's lead-in ("Data last updated:") in every language, for the text matchers
    that must recognise it wherever it prints."""
    texts = (FOOTER, *(LABELS[FOOTER][lang] for lang in LANGUAGES if lang != "en"))
    return tuple(dict.fromkeys(t.split("{ts}")[0].rstrip() for t in texts))


def refer_sentences() -> tuple[str, ...]:
    """The refer line in every language: the English constant, and the last sentence of each
    translated verdict that ends with it. For the text matchers that ask "was it printed?"."""
    found = [REFER_TO_SALESMAN]
    for english, entry in LABELS.items():
        if english.endswith(REFER_TO_SALESMAN):
            for lang in LANGUAGES:
                if lang in entry:
                    pieces = [p for p in re.split(r"(?<=[.。])\s*", entry[lang].strip()) if p]
                    found.append(pieces[-1])
    return tuple(dict.fromkeys(found))


def defaults(lang: str) -> dict[str, str]:
    """English -> `lang` for every catalog entry whose translation keeps the English tokens."""
    if lang == "en":
        return {}
    return {
        english: entry[lang]
        for english, entry in LABELS.items()
        if lang in entry and tokens_match(english, entry[lang])
    }


class Localizer:
    """Rewrites catalogued labels and sentences for `language`; everything else is untouched."""

    def __init__(self, language: str, table: dict[str, str]) -> None:
        self.language = language
        self.table = table
        # `{token}` entries as (whole-string regex over the English shape, target).
        self._templates: list[tuple[re.Pattern[str], str]] = []
        for english, target in table.items():
            if not tokens(english):
                continue
            pattern = ""
            pos = 0
            for m in _TOKEN.finditer(english):
                pattern += re.escape(english[pos : m.start()]) + f"(?P<{m.group(1)}>.+?)"
                pos = m.end()
            pattern += re.escape(english[pos:])
            self._templates.append((re.compile(pattern, re.DOTALL), target))

    def label(self, field: dict) -> str:
        """The field's label, translated by its exact English text; a value is never read."""
        label = field.get("label")
        if isinstance(label, str):
            return self.table.get(label, label)
        return label

    def text(self, s: str) -> str:
        if s in self.table:
            return self.table[s]
        for regex, target in self._templates:
            m = regex.fullmatch(s)
            if m:
                values = m.groupdict()
                return _TOKEN.sub(lambda t: values.get(t.group(1), t.group(0)), target)
        return s

    # `loc("...")` is `loc.text("...")`; `turn/` source may not spell the attribute (apply-purity grep).
    __call__ = text

    def tail(self, title: str) -> str:
        """`"<code> x <qty>: <sentence>"`: only the sentence is translated."""
        whole = self.text(title)
        if whole != title:
            return whole
        prefix, sep, sentence = title.partition(": ")
        return prefix + sep + self.text(sentence) if sep else title


IDENTITY = Localizer("en", {})


def resolve(db: Any, lang: str, *, dry_run: bool = False) -> Localizer:
    """One read of this language's memory rows, a catalog default for each gap.

    A memory row wins (staff `manual` or a stored `ai` default) when it keeps the English
    tokens; a missing default is inserted as `ai`, never overwriting. A chat turn must never
    fail on this, so a database error logs and the code defaults serve.

    The read runs in a savepoint, so a failed SELECT never aborts the turn's transaction. The
    seed is written on its own short session and committed at once: the turn's session may not
    commit before the reply, and no lock may be held across the turn. A dry run seeds nothing.
    """
    if lang not in LANGUAGES or lang == "en":
        return IDENTITY
    from sqlalchemy.orm import Session

    from app.models.translation_memory import TranslationMemory

    base = defaults(lang)
    table = dict(base)
    try:
        with db.begin_nested():
            rows = (
                db.query(TranslationMemory)
                .filter(
                    TranslationMemory.source_lang == "en",
                    TranslationMemory.target_lang == lang,
                    TranslationMemory.source_text.in_(list(LABELS)),
                )
                .all()
            )
            have = {row.source_text for row in rows}
            for row in rows:
                if tokens_match(row.source_text, row.target_text):
                    table[row.source_text] = row.target_text
        missing = {english: target for english, target in base.items() if english not in have}
        if missing and not dry_run:
            _seed(Session(bind=db.get_bind()), lang, missing)
    except Exception:
        logger.warning("label_catalog.resolve failed for %s; using code defaults", lang, exc_info=True)
    return Localizer(lang, table)


def _seed(seed_db: Any, lang: str, missing: dict[str, str]) -> None:
    """Insert catalog defaults as `ai` rows on `seed_db`, never overwriting, then commit."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.translation_memory import SOURCE_AI, TranslationMemory

    try:
        seed_db.execute(
            pg_insert(TranslationMemory)
            .values(
                [
                    {
                        "source_text": english,
                        "source_lang": "en",
                        "target_lang": lang,
                        "target_text": target,
                        "source": SOURCE_AI,
                    }
                    for english, target in missing.items()
                ]
            )
            .on_conflict_do_nothing(constraint="uq_translation_memory_phrase")
        )
        seed_db.commit()
    finally:
        seed_db.close()
