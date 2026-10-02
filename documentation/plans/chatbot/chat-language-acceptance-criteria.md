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
