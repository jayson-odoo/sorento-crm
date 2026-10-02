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

# The placeholder helpers live in a dependency-free core module (a staff edit is checked there
# too); the chatbot package may import core, never the reverse (AC-002).
from app.services.text_tokens import _TOKEN, tokens, tokens_match  # noqa: F401

logger = logging.getLogger(__name__)

LANGUAGES = ("en", "ms", "zh")

#: English source text -> {"ms": ..., "zh": ...}. `{name}` placeholders must survive translation.
# The presenter's own truncation sentence (`summary_intro`), which carries an em dash; escaped
# here so this source stays dash-free.
_NOT_EVERY_BREAKDOWN = "Not every breakdown is shown \u2014 add a customer, a product or a date range."

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
    # Slice 2: PO / SO / SPO / orders rows. PO, SO, SPO and GR stay as printed (owner Q3).
    "Order Number": {"ms": "No. Pesanan", "zh": "订单号"},
    "Customer": {"ms": "Pelanggan", "zh": "客户"},
    "Order Date": {"ms": "Tarikh Pesanan", "zh": "订单日期"},
    "Actual Delivery Date": {"ms": "Tarikh Penghantaran Sebenar", "zh": "实际送货日期"},
    "Status": {"ms": "Status", "zh": "状态"},
    "Pickup Time": {"ms": "Masa Pengambilan", "zh": "提货时间"},
    "Transporter": {"ms": "Pengangkut", "zh": "运输商"},
    "Driver": {"ms": "Pemandu", "zh": "司机"},
    "Lorry Plate": {"ms": "No. Plat Lori", "zh": "车牌号"},
    "Products": {"ms": "Produk", "zh": "产品"},
    "SO Number": {"ms": "No. SO", "zh": "SO 编号"},
    "Outstanding Qty": {"ms": "Kuantiti Tertunggak", "zh": "未交货数量"},
    "Requested Delivery Date": {"ms": "Tarikh Penghantaran Diminta", "zh": "要求送货日期"},
    "PO Number": {"ms": "No. PO", "zh": "PO 编号"},
    "Ordered Qty": {"ms": "Kuantiti Dipesan", "zh": "订购数量"},
    "PO Date": {"ms": "Tarikh PO", "zh": "PO 日期"},
    "Location": {"ms": "Lokasi", "zh": "位置"},
    "Supplier": {"ms": "Pembekal", "zh": "供应商"},
    "SPO Number": {"ms": "No. SPO", "zh": "SPO 编号"},
    "Container Number": {"ms": "No. Kontena", "zh": "货柜号"},
    "SPO Quantity": {"ms": "Kuantiti SPO", "zh": "SPO 数量"},
    "GR Quantity": {"ms": "Kuantiti GR", "zh": "GR 数量"},
    "SPO Date": {"ms": "Tarikh SPO", "zh": "SPO 日期"},
    "SPO Date (recorded)": {"ms": "Tarikh SPO (direkodkan)", "zh": "SPO 日期（已记录）"},
    "GR Date": {"ms": "Tarikh GR", "zh": "GR 日期"},
    "PO Quantity": {"ms": "Kuantiti PO", "zh": "PO 数量"},
    "Cost / unit": {"ms": "Kos / unit", "zh": "单位成本"},
    "Discount / unit": {"ms": "Diskaun / unit", "zh": "单位折扣"},
    "Cost after discount / unit": {"ms": "Kos selepas diskaun / unit", "zh": "折后单位成本"},
    "Here are the orders I found.": {"ms": "Berikut ialah pesanan yang saya temui.", "zh": "以下是我找到的订单。"},
    "Here is the PO placed I found.": {"ms": "Berikut ialah PO yang telah dibuat.", "zh": "以下是已下的 PO。"},
    "Here is the last SPO line per product.": {"ms": "Berikut ialah baris SPO terakhir bagi setiap produk.", "zh": "以下是每个产品最近的 SPO 记录。"},
    "Here is the last purchase cost per product and location.": {"ms": "Berikut ialah kos belian terakhir bagi setiap produk dan lokasi.", "zh": "以下是每个产品和位置最近一次的采购成本。"},
    "Here is the outstanding SO I found.": {"ms": "Berikut ialah SO belum dihantar yang saya temui.", "zh": "以下是我找到的未交货 SO。"},
    "Here are the outstanding orders I found.": {"ms": "Berikut ialah pesanan belum dihantar yang saya temui.", "zh": "以下是我找到的未交货订单。"},
    "Here are the delivered orders I found.": {"ms": "Berikut ialah pesanan yang telah dihantar.", "zh": "以下是我找到的已送货订单。"},
    "No matching results found.": {"ms": "Tiada hasil yang sepadan ditemui.", "zh": "未找到匹配的结果。"},
    "No matching results found for {companies}.": {"ms": "Tiada hasil yang sepadan ditemui untuk {companies}.", "zh": "在 {companies} 中未找到匹配的结果。"},
    "Here are the results I found.": {"ms": "Berikut ialah hasil yang saya temui.", "zh": "以下是我找到的结果。"},
    "EXPIRED": {"ms": "TAMAT TEMPOH", "zh": "已过期"},
    # The order summary block (presenter `_SUMMARY_FIELDS`) and its truncation notice. SO and DO
    # stay as printed (owner Q3).
    "Customers": {"ms": "Pelanggan", "zh": "客户"},
    "SO": {"ms": "SO", "zh": "SO"},
    "SO Date": {"ms": "Tarikh SO", "zh": "SO 日期"},
    "Ordered": {"ms": "Dipesan", "zh": "订购"},
    "Transferred to DO": {"ms": "Dipindahkan ke DO", "zh": "已转 DO"},
    "SO Outstanding": {"ms": "SO Tertunggak", "zh": "SO 未交货"},
    "DO": {"ms": "DO", "zh": "DO"},
    "DO Date": {"ms": "Tarikh DO", "zh": "DO 日期"},
    "Delivered": {"ms": "Dihantar", "zh": "已送货"},
    "Delivery Date": {"ms": "Tarikh Penghantaran", "zh": "送货日期"},
    "DO Outstanding": {"ms": "DO Tertunggak", "zh": "DO 未送达"},
    _NOT_EVERY_BREAKDOWN: {
        "ms": "Tidak semua pecahan dipaparkan. Tambah pelanggan, produk atau julat tarikh.",
        "zh": "并非所有明细都已显示，请加上客户、产品或日期范围。",
    },
    # compose's "No <domain label> found for {codes}." (policy_rows.py labels: orders :155,
    # last in :269, outstanding purchase orders :293, last purchase cost :307; stock :134 is
    # the slice 1 entry above).
    "No orders found for {codes}.": {
        "ms": "Tiada pesanan ditemui untuk {codes}.",
        "zh": "未找到 {codes} 的订单。",
    },
    "No last in found for {codes}.": {
        "ms": "Tiada SPO ditemui untuk {codes}.",
        "zh": "未找到 {codes} 的 SPO。",
    },
    "No outstanding purchase orders found for {codes}.": {
        "ms": "Tiada PO ditemui untuk {codes}.",
        "zh": "未找到 {codes} 的 PO。",
    },
    "No last purchase cost found for {codes}.": {
        "ms": "Tiada kos belian ditemui untuk {codes}.",
        "zh": "未找到 {codes} 的采购成本。",
    },
    "PENDING ALLOCATION": {"ms": "MENUNGGU PERUNTUKAN", "zh": "待分配"},
    "PARTIAL ALLOCATION": {"ms": "PERUNTUKAN SEBAHAGIAN", "zh": "部分分配"},
}

#: Presenter field key -> English label (slices 1 and 2).
FIELD_KEYS: dict[str, str] = {
    "company_name": "Company",
    "product_code": "Product Code",
    "product_name": "Product Name",
    "warehouse": "Warehouse",
    "system_location": "System Location",
    "quantity_on_hand": "Quantity On Hand",
    "open_so_qty": "Outstanding",
    "total_on_hand": "Total",
    # Slice 2 summary block (`order_date` is a DO Date there; by-label lookup covers it).
    "customers": "Customers",
    "so_count": "SO",
    "so_date": "SO Date",
    "so_ordered_qty": "Ordered",
    "so_transferred_qty": "Transferred to DO",
    "so_outstanding_qty": "SO Outstanding",
    "order_count": "DO",
    "delivered_quantity": "Delivered",
    "delivered_between": "Delivery Date",
    "pending_quantity": "DO Outstanding",
    # Slice 2.
    "so_number": "SO Number",
    "outstanding_qty": "Outstanding Qty",
    "order_date": "Order Date",
    "customer": "Customer",
    "requested_delivery_date": "Requested Delivery Date",
    "po_number": "PO Number",
    "ordered_qty": "Ordered Qty",
    "po_date": "PO Date",
    "location": "Location",
    "supplier": "Supplier",
    "spo_number": "SPO Number",
    "container_number": "Container Number",
    "spo_quantity": "SPO Quantity",
    "gr_quantity": "GR Quantity",
    "spo_date": "SPO Date",
    "gr_date": "GR Date",
    "po_quantity": "PO Quantity",
    "unit_cost": "Cost / unit",
    "discount_per_unit": "Discount / unit",
    "unit_cost_after_discount": "Cost after discount / unit",
}

FOOTER = "Data last updated: {ts}"



def footer_leads(localizer: Any = None) -> tuple[str, ...]:
    """The footer's lead-in ("Data last updated:") in every language, for the text matchers
    that must recognise it wherever it prints. `localizer` adds its own (staff-edited) wording."""
    texts = [FOOTER, *(LABELS[FOOTER][lang] for lang in LANGUAGES if lang != "en")]
    if localizer is not None and FOOTER in localizer.table:
        texts.append(localizer.table[FOOTER])
    leads = (t.split("{ts}")[0].rstrip() for t in texts)
    return tuple(dict.fromkeys(lead for lead in leads if lead))


def refer_sentences(localizer: Any = None) -> tuple[str, ...]:
    """The refer line in every language: the English constant, and the last sentence of each
    translated verdict that ends with it. For the text matchers that ask "was it printed?".
    `localizer` adds its own (staff-edited) wording of the same verdicts."""
    found = [REFER_TO_SALESMAN]
    for english, entry in LABELS.items():
        if english.endswith(REFER_TO_SALESMAN):
            texts = [entry[lang] for lang in LANGUAGES if lang in entry]
            if localizer is not None and english in localizer.table:
                texts.append(localizer.table[english])
            for text in texts:
                pieces = [p for p in re.split(r"(?<=[.。])\s*", text.strip()) if p]
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
        """The field's label: by its key when it has a catalogued one and still carries that
        English label, else by the exact label text. A value is never read."""
        label = field.get("label")
        if not isinstance(label, str):
            return label
        key = field.get("key")
        english = FIELD_KEYS.get(key) if isinstance(key, str) else None
        if english is not None and label == english:
            return self.table.get(english, label)
        return self.table.get(label, label)

    def text(self, s: str) -> str:
        if s in self.table:
            return self.table[s]
        for regex, target in self._templates:
            m = regex.fullmatch(s)
            if m:
                values = m.groupdict()
                return _TOKEN.sub(lambda t: values.get(t.group(1), t.group(0)), target)
        return s

    def sentence(self, s: str) -> str:
        """`text`, under a name `turn/` source may use (the apply-purity grep bans `.text`)."""
        return self.text(s)

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
