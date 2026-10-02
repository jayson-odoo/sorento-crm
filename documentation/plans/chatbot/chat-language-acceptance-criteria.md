# CHAT-LANGUAGE acceptance criteria (slice 1: stock)

Plan: `PLAN-chat-language-2oct.md`. Card: `chat-language-behaviour-card.md` (Q1-Q5 written to recs).

## Contract (what the tests bind to)

`app/services/chatbot/label_catalog.py` (pure, except `resolve`):
- `LANGUAGES = ("en", "ms", "zh")`
- `LABELS: dict[str, dict[str, str]]`: English source text -> `{"ms": ..., "zh": ...}`.
- `FIELD_KEYS: dict[str, str]`: presenter field key -> English label.
- `tokens(text) -> list[str]`: sorted `{name}` placeholders. `tokens_match(a, b) -> bool`.
- `defaults(lang) -> dict[str, str]`: English -> target for every catalog entry whose
  translation passes `tokens_match`; `{}` for `en`.
- `class Localizer(language: str, table: dict[str, str])`:
  - `label(field: dict) -> str`: by `field["key"]` via `FIELD_KEYS` when the key is
    catalogued AND the field's label equals that English label; else by the exact label text;
    else the label unchanged.
  - `text(s: str) -> str`: an exact entry, else a `{token}` template whose English shape
    matches the whole string (values re-inserted verbatim); else `s` unchanged.
  - `tail(title: str) -> str`: for `"<code> x <qty>: <sentence>"` translates the sentence
    only, keeping everything before the first `": "`; else `text(title)`.
- `IDENTITY`: `Localizer("en", {})`.
- `resolve(db, lang) -> Localizer`:
  - `en`/unknown -> `IDENTITY` (no DB read).
  - Otherwise one read of `translation_memory` rows where `source_lang='en'`,
    `target_lang=lang` and `source_text` is in the catalog. A row's `target_text` wins if it
    passes `tokens_match`.
  - Every catalog default with no row is inserted as `source='ai'` (idempotent; a second
    resolve inserts nothing).
  - A `manual` row is never overwritten.

`app/services/chatbot/language.py` (pure):
- `detect(message, *, strip=()) -> "en"|"ms"|"zh"|None`: rules in the behaviour card.
- `choose(detected, conversation, saved) -> str`: the first of those in `LANGUAGES`, else `"en"`.
- `for_turn(message, session_vars: dict, saved, *, strip=()) -> str`: `choose(detect(...),
  session_vars.get("reply_language"), saved)`. It writes the result to
  `session_vars["reply_language"]` and returns it.

Rendering:
- `lanes/business/fetch.py::output_structurer(result, ctx)` reads `ctx["localizer"]`
  (absent -> identity, byte-identical to today) for: field labels, the summary-item labels,
  the intro, availability titles (`tail`), flag words, and the `Data last updated: {ts}` footer.
- `turn/compose.py::compose(..., ctx)` reads `getattr(ctx, "localizer", None)` for
  "No stock found for {codes}.".

## Slice-1 catalog content (exact)

| English | ms | zh |
|---|---|---|
| Company | Syarikat | 公司 |
| Product Code | Kod Produk | 产品代码 |
| Product Name | Nama Produk | 产品名称 |
| Warehouse | Gudang | 仓库 |
| System Location | Lokasi Sistem | 系统位置 |
| Quantity On Hand | Kuantiti Ada | 现有数量 |
| Outstanding | Belum Dihantar | 未交货 |
| Total | Jumlah | 总数 |
| Stock summary for the requested products. | Ringkasan stok untuk produk yang diminta. | 所请求产品的库存摘要。 |
| Stock details found for the requested products. | Butiran stok untuk produk yang diminta. | 所请求产品的库存详情。 |
| How many units do you need? | Berapa unit yang anda perlukan? | 您需要多少件？ |
| yes, we have stock. Please refer to your salesman. | ya, stok ada. Sila rujuk jurujual anda. | 有库存。请联系您的销售员。 |
| no stock and no incoming at the moment. Please refer to your salesman. | tiada stok dan tiada barang masuk buat masa ini. Sila rujuk jurujual anda. | 目前没有库存，也没有到货。请联系您的销售员。 |
| the quantity is more than what I can confirm here. Please refer to your salesman. | kuantiti ini melebihi apa yang boleh saya sahkan di sini. Sila rujuk jurujual anda. | 这个数量超出我在这里可以确认的范围。请联系您的销售员。 |
| no stock at the moment, ETA {eta}. | tiada stok buat masa ini, ETA {eta}. | 目前没有库存，ETA {eta}。 |
| Data last updated: {ts} | Data dikemas kini: {ts} | 数据更新时间: {ts} |
| No stock found for {codes}. | Tiada stok ditemui untuk {codes}. | 未找到 {codes} 的库存。 |
| Here are the results. | Berikut ialah hasilnya. | 以下是结果。 |
| PRODUCT DISCONTINUED | PRODUK DIHENTIKAN | 产品已停产 |

FIELD_KEYS (slice 1): company_name, product_code, product_name, warehouse, system_location,
quantity_on_hand, open_so_qty -> Outstanding, total_on_hand -> Total.

## Criteria

- **AC-CL01:** every catalog entry has ms and zh, and each passes `tokens_match`.
- **AC-CL02:** every stock-path label and sentence the presenter emits is catalogued. Pinned
  list: the 8 labels above, the 3 intros and the 4 verdict tails; the tails are pinned against
  `sorento_crm_mcp.presenters._AVAILABILITY_TAILS` and `REFER_TO_SALESMAN`.
- **AC-CL03:** a `Localizer` never changes a value. A location-code label (`"BRW-BB"`), a
  product code, a number or an uncatalogued label comes back unchanged.
- **AC-CL04:** a template whose translation drops or adds a `{token}` is rejected: `defaults`
  omits it, and `resolve` ignores such a memory row and falls back to the default.
- **AC-CL05:** detection table:

  | Message | Expected |
  |---|---|
  | "SRTSWT3001 有货吗" | zh |
  | "ada stok SRTSWT3001?" | ms |
  | "SRTSWT3001 ada stock tak" | ms |
  | "berapa unit kat PKL?" | ms |
  | "can check stock SRTSWT3001 ah" | en |
  | "how many SRTSWT3001 in stock" | en |
  | "SRTSWT3001" | None |
  | "1" | None |
  | "ok" | None |
  | "stock ada?" (tie) | None |
  | "ADA HARDWARE stock please" with strip ["ADA HARDWARE"] | en |

- **AC-CL06:** `choose`/`for_turn`: example E. "stock SRTSWT3001" gives en. "berapa unit kat
  PKL?" gives ms. "1" gives ms (carried). With no carry and saved "zh", "1" gives zh. With
  nothing at all, en.
- **AC-CL07:** `output_structurer` with no localizer is byte-identical to today (existing
  suite stays green).
- **AC-CL08:** `output_structurer` on a compact stock envelope with the ms localizer contains
  "Ringkasan stok untuk produk yang diminta.", "*Kod Produk:* SRTSWT3001", "*Jumlah:* 51",
  "*BRW-BB:* 30" and "_Data dikemas kini: ". It contains none of "Product Code", "Total:" or
  "Data last updated". zh is the same with the zh strings.
- **AC-CL09:** availability, answered, zh: `"SRTSWT3001 x 10: 有库存。请联系您的销售员。"`.
  Incoming: `"SRTSWT3001 x 10: 目前没有库存，ETA 15/10/2026。"`.
- **AC-CL10:** detailed staff row, zh: "*公司:*", "*产品代码:* BRBC22102W", "*仓库:* BUKIT RAJA",
  "*系统位置:* BRW-BB" and "*现有数量:* 40". A discontinued flag line reads "产品已停产".
- **AC-CL11:** `compose` with an ms localizer prints "Tiada stok ditemui untuk SRTSWT3001-GM.";
  figures are not mutated (`_codes_without_rows` still matches "Product Code").
- **AC-CL12:** `resolve(db, "ms")`:
  - The first call inserts one `ai` row per catalog entry.
  - A second call inserts 0 rows.
  - A pre-existing `manual` row with different text wins and is unchanged afterwards.
  - `resolve(db, "en")` reads nothing and returns `IDENTITY`.

# Slice 2: PO / SO / SPO / orders rows

Tools localized (added to `fetch._LOCALIZED_TOOLS`): `crm_order_management_orders_list`,
`crm_order_management_orders_by_product_list`, `crm_procurement_po_placed_list`,
`crm_procurement_spo_allocations_last_receipt_list`, `crm_procurement_po_last_cost_list`.
Presenter literals: `presenters.py` `_orders_list` (:411), `_orders_so_outstanding` (:441),
`_purchase_orders_placed` (:471), `_spo_last_receipt` (:503), `_po_last_cost` (:553),
`_orders_by_product` (:614), `_DEFAULT_INTRO` (:67-84), the intros at :1815-1836, and
`fetch.py` order-status intros (:2960-2962) plus the flag lines (:3034-3040).
Abbreviations PO / SO / SPO / GR stay as printed (owner Q3). Order STATUS values are data and
are never translated.

| English | ms | zh |
|---|---|---|
| Order Number | No. Pesanan | 订单号 |
| Customer | Pelanggan | 客户 |
| Order Date | Tarikh Pesanan | 订单日期 |
| Actual Delivery Date | Tarikh Penghantaran Sebenar | 实际送货日期 |
| Status | Status | 状态 |
| Pickup Time | Masa Ambil | 提货时间 |
| Transporter | Pengangkut | 运输商 |
| Driver | Pemandu | 司机 |
| Lorry Plate | No. Plat Lori | 车牌号 |
| Products | Produk | 产品 |
| SO Number | No. SO | SO 编号 |
| Outstanding Qty | Kuantiti Belum Dihantar | 未交货数量 |
| Requested Delivery Date | Tarikh Penghantaran Diminta | 要求送货日期 |
| PO Number | No. PO | PO 编号 |
| Ordered Qty | Kuantiti Dipesan | 订购数量 |
| PO Date | Tarikh PO | PO 日期 |
| Location | Lokasi | 位置 |
| Supplier | Pembekal | 供应商 |
| SPO Number | No. SPO | SPO 编号 |
| Container Number | No. Kontena | 货柜号 |
| SPO Quantity | Kuantiti SPO | SPO 数量 |
| GR Quantity | Kuantiti GR | GR 数量 |
| SPO Date | Tarikh SPO | SPO 日期 |
| SPO Date (recorded) | Tarikh SPO (direkodkan) | SPO 日期（已记录） |
| GR Date | Tarikh GR | GR 日期 |
| PO Quantity | Kuantiti PO | PO 数量 |
| Cost / unit | Kos / unit | 单位成本 |
| Discount / unit | Diskaun / unit | 单位折扣 |
| Cost after discount / unit | Kos selepas diskaun / unit | 折后单位成本 |
| Here are the orders I found. | Berikut ialah pesanan yang saya temui. | 以下是我找到的订单。 |
| Here is the PO placed I found. | Berikut ialah PO yang telah dibuat. | 以下是已下的 PO。 |
| Here is the last SPO line per product. | Berikut ialah baris SPO terakhir bagi setiap produk. | 以下是每个产品的最后一行 SPO。 |
| Here is the last purchase cost per product and location. | Berikut ialah kos belian terakhir bagi setiap produk dan lokasi. | 以下是每个产品和位置的最后采购成本。 |
| Here is the outstanding SO I found. | Berikut ialah SO belum dihantar yang saya temui. | 以下是我找到的未交货 SO。 |
| Here are the outstanding orders I found. | Berikut ialah pesanan belum dihantar yang saya temui. | 以下是我找到的未交货订单。 |
| Here are the delivered orders I found. | Berikut ialah pesanan yang telah dihantar. | 以下是我找到的已送货订单。 |
| No matching results found. | Tiada hasil yang sepadan ditemui. | 未找到匹配的结果。 |
| No matching results found for {companies}. | Tiada hasil yang sepadan ditemui untuk {companies}. | 在 {companies} 中未找到匹配的结果。 |
| Here are the results I found. | Berikut ialah hasil yang saya temui. | 以下是我找到的结果。 |
| EXPIRED | TAMAT TEMPOH | 已过期 |
| PENDING ALLOCATION | MENUNGGU PERUNTUKAN | 待分配 |
| PARTIAL ALLOCATION | PERUNTUKAN SEBAHAGIAN | 部分分配 |

FIELD_KEYS additions: so_number, outstanding_qty -> Outstanding Qty, order_date, customer,
requested_delivery_date, po_number, ordered_qty, po_date, location, supplier, spo_number,
container_number, spo_quantity, gr_quantity, spo_date (label "SPO Date" or "SPO Date (recorded)":
by-label match covers both), gr_date, warehouse, po_quantity, unit_cost -> Cost / unit,
discount_per_unit, unit_cost_after_discount.

- **AC-CL20:** every label/intro literal of the five tools' presenters is catalogued (pinned
  list above; presenter source is read where importable, as slice 1 does).
- **AC-CL21:** a PO placed envelope rendered with the ms localizer: "*No. PO:* <po>",
  "*Kuantiti Dipesan:* <n>", "*Pembekal:*" only when granted (restricted drop unchanged), intro
  "Berikut ialah PO yang telah dibuat.". Every value byte-identical to the en render.
- **AC-CL22:** SPO last-receipt zh: "*SPO 编号:*", "*货柜号:*", "*SPO 日期（已记录）:*" for a
  recorded date; values unchanged.
- **AC-CL23:** orders list ms: "*No. Pesanan:*", "*Pelanggan:*", "*Status:* <status value
  unchanged>", the outstanding-orders intro when `order_status == "outstanding"`, and the flag
  lines EXPIRED / PENDING ALLOCATION / PARTIAL ALLOCATION translated.
- **AC-CL24:** PO last cost zh restricted cost fields: dropped without grant, translated labels
  with grant ("*单位成本:*"); money values unchanged.
- **AC-CL25:** "No matching results found for {companies}." localizes with the company names
  re-inserted verbatim.
- **AC-CL26:** tools outside slices 1-2 (outstanding report, top selling, promotions,
  attachments) still render English with an ms localizer in ctx.
