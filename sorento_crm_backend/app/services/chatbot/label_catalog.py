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
    "Outstanding": {"ms": "Tertunggak", "zh": "未交货"},
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
    "Here is the outstanding SO I found.": {"ms": "Berikut ialah SO tertunggak yang saya temui.", "zh": "以下是我找到的未交货 SO。"},
    "Here are the outstanding orders I found.": {"ms": "Berikut ialah pesanan tertunggak yang saya temui.", "zh": "以下是我找到的未交货订单。"},
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
    # Slice 3: the outstanding report and top selling (finished text, `Localizer.lines`). The
    # singular titles are the presenter's `Top 1 selling item` forms.
    "Sales orders": {"ms": "Pesanan jualan", "zh": "销售订单"},
    "Order date range": {"ms": "Julat tarikh pesanan", "zh": "订单日期范围"},
    "Delivery orders": {"ms": "Pesanan penghantaran", "zh": "送货单"},
    "DO qty": {"ms": "Kuantiti DO", "zh": "DO 数量"},
    "DO date range": {"ms": "Julat tarikh DO", "zh": "DO 日期范围"},
    "Product": {"ms": "Produk", "zh": "产品"},
    "Order date": {"ms": "Tarikh pesanan", "zh": "订单日期"},
    "Brand": {"ms": "Jenama", "zh": "品牌"},
    "DO Number": {"ms": "No. DO", "zh": "DO 编号"},
    "DO Qty": {"ms": "Kuantiti DO", "zh": "DO 数量"},
    "Category": {"ms": "Kategori", "zh": "类别"},
    "Sales agent": {"ms": "Ejen jualan", "zh": "销售代理"},
    "Channel": {"ms": "Saluran", "zh": "渠道"},
    "Delivery date": {"ms": "Tarikh penghantaran", "zh": "送货日期"},
    "Ranked by": {"ms": "Disusun mengikut", "zh": "排名依据"},
    "Basis": {"ms": "Asas", "zh": "统计口径"},
    "Items with sales": {"ms": "Item dengan jualan", "zh": "有销售的项目"},
    "Categories with sales": {"ms": "Kategori dengan jualan", "zh": "有销售的类别"},
    "all": {"ms": "semua", "zh": "全部"},
    "{from} to {to}": {"ms": "{from} hingga {to}", "zh": "{from} 至 {to}"},
    "Amount": {"ms": "Amaun", "zh": "金额"},
    "Quantity": {"ms": "Kuantiti", "zh": "数量"},
    "Delivered (transferred to DO)": {"ms": "Dihantar (dipindahkan ke DO)", "zh": "已送货（已转 DO）"},
    "Sales order outstanding": {"ms": "Pesanan jualan tertunggak", "zh": "未交货销售订单"},
    "Delivery order outstanding": {"ms": "Pesanan penghantaran tertunggak", "zh": "未送达送货单"},
    "By location": {"ms": "Mengikut lokasi", "zh": "按位置"},
    "By customer": {"ms": "Mengikut pelanggan", "zh": "按客户"},
    "By product": {"ms": "Mengikut produk", "zh": "按产品"},
    "By month": {"ms": "Mengikut bulan", "zh": "按月份"},
    "Sales order list": {"ms": "Senarai pesanan jualan", "zh": "销售订单列表"},
    "Delivery order list": {"ms": "Senarai pesanan penghantaran", "zh": "送货单列表"},
    "Both lists": {"ms": "Kedua-dua senarai", "zh": "两个列表"},
    "No open sales order.": {"ms": "Tiada pesanan jualan terbuka.", "zh": "没有未完成的销售订单。"},
    "No outstanding delivery order.": {"ms": "Tiada pesanan penghantaran tertunggak.", "zh": "没有未送达的送货单。"},
    "Sales order figures are not enabled for your account.": {"ms": "Angka pesanan jualan tidak diaktifkan untuk akaun anda.", "zh": "您的账户未开通销售订单数据。"},
    "Reply with a number for detail:": {"ms": "Balas dengan nombor untuk butiran:", "zh": "回复数字查看详情："},
    "Reply 1 for the sales order list.": {"ms": "Balas 1 untuk senarai pesanan jualan.", "zh": "回复 1 查看销售订单列表。"},
    "Reply 1 for the delivery order list.": {"ms": "Balas 1 untuk senarai pesanan penghantaran.", "zh": "回复 1 查看送货单列表。"},
    "No sales found.": {"ms": "Tiada jualan ditemui.", "zh": "未找到销售记录。"},
    "By quantity or by amount?": {"ms": "Mengikut kuantiti atau amaun?", "zh": "按数量还是按金额？"},
    "Do you want the top items inside one category, or the categories ranked against each other?": {"ms": "Anda mahu item teratas dalam satu kategori, atau kategori disusun antara satu sama lain?", "zh": "您要看某一类别内的热销项目，还是各类别之间的排名？"},
    "Delivered (transferred to DO) or ordered?": {"ms": "Dihantar (dipindahkan ke DO) atau dipesan?", "zh": "已送货（已转 DO）还是已订购？"},
    "Sorry, I can only share sales figures for your own account.": {"ms": "Maaf, saya hanya boleh berkongsi angka jualan untuk akaun anda sendiri.", "zh": "抱歉，我只能提供您本人账户的销售数据。"},
    "Items with no sale in this period are not ranked.": {"ms": "Item tanpa jualan dalam tempoh ini tidak disenaraikan.", "zh": "此期间没有销售的项目不参与排名。"},
    "Categories with no sale in this period are not ranked.": {"ms": "Kategori tanpa jualan dalam tempoh ini tidak disenaraikan.", "zh": "此期间没有销售的类别不参与排名。"},
    "Reply with a rank number to see that category's top items.": {"ms": "Balas dengan nombor kedudukan untuk melihat item teratas kategori itu.", "zh": "回复排名数字查看该类别的热销项目。"},
    "Reply with a rank number to see that item's customers and months.": {"ms": "Balas dengan nombor kedudukan untuk melihat pelanggan dan bulan bagi item itu.", "zh": "回复排名数字查看该项目的客户和月份。"},
    "Sales report is not enabled for your account.": {"ms": "Laporan jualan tidak diaktifkan untuk akaun anda.", "zh": "您的账户未开通销售报告。"},
    "Note: only {pct}% of sales orders in this period carry a sales agent.": {"ms": "Nota: hanya {pct}% pesanan jualan dalam tempoh ini mempunyai ejen jualan.", "zh": "注：此期间只有 {pct}% 的销售订单带有销售代理。"},
    "Top {n} selling items": {"ms": "{n} item paling laris", "zh": "最畅销的 {n} 个项目"},
    "Top {n} selling categories": {"ms": "{n} kategori paling laris", "zh": "最畅销的 {n} 个类别"},
    "Bottom {n} selling items": {"ms": "{n} item paling kurang laris", "zh": "最滞销的 {n} 个项目"},
    "Bottom {n} selling categories": {"ms": "{n} kategori paling kurang laris", "zh": "最滞销的 {n} 个类别"},
    "Top selling items": {"ms": "Item paling laris", "zh": "最畅销项目"},
    "Top selling categories": {"ms": "Kategori paling laris", "zh": "最畅销类别"},
    "Least sold items": {"ms": "Item paling kurang dijual", "zh": "销量最少的项目"},
    "Least sold categories": {"ms": "Kategori paling kurang dijual", "zh": "销量最少的类别"},
    "{code}: customers and months": {"ms": "{code}: pelanggan dan bulan", "zh": "{code}：客户和月份"},
    "How many items do you want to see? Reply with a number from 1 to {max}.": {"ms": "Berapa banyak item yang anda mahu lihat? Balas dengan nombor dari 1 hingga {max}.", "zh": "您想看多少个项目？请回复 1 到 {max} 之间的数字。"},
    "How many categories do you want to see? Reply with a number from 1 to {max}.": {"ms": "Berapa banyak kategori yang anda mahu lihat? Balas dengan nombor dari 1 hingga {max}.", "zh": "您想看多少个类别？请回复 1 到 {max} 之间的数字。"},
    "I can list at most the top {n} in one reply.": {"ms": "Saya boleh senaraikan paling banyak {n} teratas dalam satu balasan.", "zh": "我一次最多只能列出前 {n} 个。"},
    "Top {n} selling item": {"ms": "{n} item paling laris", "zh": "最畅销的 {n} 个项目"},
    "Top {n} selling category": {"ms": "{n} kategori paling laris", "zh": "最畅销的 {n} 个类别"},
    "Bottom {n} selling item": {"ms": "{n} item paling kurang laris", "zh": "最滞销的 {n} 个项目"},
    "Bottom {n} selling category": {"ms": "{n} kategori paling kurang laris", "zh": "最滞销的 {n} 个类别"},
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


#: Report value words `Localizer.lines` translates after a catalogued label. An explicit set, never
#: "any catalog key", so data that happens to read like a label (a status named "Status") is safe.
VALUE_WORDS = frozenset({"all", "Amount", "Quantity", "Ordered", "Delivered (transferred to DO)"})
RANGE = "{from} to {to}"
_DATE_RANGE = re.compile(r"(?P<from>\d{2}/\d{2}/\d{4}) to (?P<to>\d{2}/\d{2}/\d{4})")
_BREAKDOWN_VALUE = re.compile(r"\d[\d,]* \(O/S: ")
_NUMBERED = re.compile(r"\d+\. ")
_WRAPPERS = (("*_", "_*"), ("*", "*"), ("_", "_"))


class Localizer:
    """Rewrites catalogued labels and sentences for `language`; everything else is untouched."""

    def __init__(self, language: str, table: dict[str, str]) -> None:
        self.language = language
        self.table = table
        # `{token}` entries as (whole-string regex over the English shape, target).
        self._templates: list[tuple[re.Pattern[str], str]] = []
        for english, target in table.items():
            if not tokens(english) or english == RANGE:
                continue  # the date range is a VALUE template, applied by `lines` only
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

    def lines(self, text: str) -> str:
        """Finished report text, line by line: the first rule that matches wins.

        1. a catalogued sentence, bare or inside one wrapper (`*x*`, `*_x_*`, `_x_`);
        2. `"<n>. <sentence>"`;
        3. a label line (`"<label>: <value>"`, bold `"*<label>:* <value>"`, optionally led by
           `"<n>. "`) whose label is catalogued: the label translates, and the value only when
           it is exactly a `VALUE_WORDS` entry or a `dd/mm/yyyy to dd/mm/yyyy` range;
        4. anything else, unchanged (rank lines, months, codes, `Unassigned`).
        The join is byte-exact."""
        if not self.table or not text:
            return text
        return "\n".join(self._line(line) for line in text.split("\n"))

    def _line(self, line: str) -> str:
        for left, right in _WRAPPERS:
            if len(line) > len(left) + len(right) and line.startswith(left) and line.endswith(right):
                inner = line[len(left) : len(line) - len(right)]
                done = self.text(inner)
                if done != inner:
                    return left + done + right
        done = self.text(line)
        if done != line:
            return done
        number = _NUMBERED.match(line)
        prefix, rest = (number.group(0), line[number.end() :]) if number else ("", line)
        if prefix:
            done = self.text(rest)
            if done != rest:
                return prefix + done
        for left, sep in (("*", ":* "), ("", ": ")):
            if not rest.startswith(left):
                continue
            head, found, value = rest[len(left) :].partition(sep)
            if not found or head not in self.table or _BREAKDOWN_VALUE.match(value):
                continue  # a breakdown row (`5 (O/S: 2)`) whose name collides with a label is data
            return prefix + left + self.table[head] + sep + self._value(value)
        return line

    def _value(self, value: str) -> str:
        if value in VALUE_WORDS and value in self.table:
            return self.table[value]
        m = _DATE_RANGE.fullmatch(value)
        if m and RANGE in self.table:
            values = m.groupdict()
            return _TOKEN.sub(lambda t: values.get(t.group(1), t.group(0)), self.table[RANGE])
        return value

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
