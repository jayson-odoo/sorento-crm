# PLAN: Stock list - bare model codes composed from brand, type and trap size

Status: IN REVIEW - PR #1000 ready 18 Sep 2026, CI green, browser pass done on :3086; awaiting owner hand test + merge go
Domain: scm
Branch: feat/stock-list-bare-model-codes
UAC: stock-list-bare-model-codes-acceptance-criteria.md
Owner feedback: 17 Sep 2026, `SORENTO库存表20260914.xlsx` (CHAOZHOU CHAOAN FENGTANG DAFUYUAN),
already uploaded once: 44 rows stored, 2 bound.

## What the owner saw

1. Attachment preview, "Open" button on the stock list: a raw JSON page
   `{"detail":"Authentication required. Provide either Bearer token or X-API-Key header."}`.
2. The supplier's 型号 is a bare model number (`8613`, `8066-PP`, `-7055`). Our code is brand
   prefix + type + model + trap: `SRTWC8613-RL`, `SRTWC8066-S-150-NEW`, `SRTWB7055`. The
   brand sits in 商标, the type in 品名, the trap size in 规格. One 型号 spans several rows,
   sometimes as a merged cell. Nothing binds; the four `8613` rows collapse into one.

## Measured (0915 prod copy + the file)

| Fact | Evidence |
| --- | --- |
| Open 401 | `AttachmentPreviewModal.tsx:184` links `<a target=_blank>` to the same-origin `/download` route when the item has no CDN url; the anchor carries no Bearer. Download already fetches through `apiFetch` and opens a blob. |
| Bare 型号 (`^[-0-9]`) | DAFUYUAN 26 of 44 rows; JINBAICHUAN 5 of 701; ROYAL MIRROR 1 of 115. None of the 32 bound today. One dismissal alias exists on a bare code (`242`, JINBAICHUAN). |
| Letter-led 型号 | JINBAICHUAN 696 rows / 363 bound, ROYAL 114 / 36, DAFUYUAN 18 / 2. Every one with a trap 规格 already carries the size number inside 型号 (557 of 557). |
| 规格 vocabulary, all suppliers | `250` `200` `180横排` `180` `300` `150` `250UF` `250A` `250PP` `250-PP` `250NEW` `250对冲` `180A横排` `180横排对冲` (JIN + ROYAL); `250mm` `150mm` `横排180mm` + non-trap `600*450*200mm` `背部没有孔` `四面施釉` (DAFUYUAN). |
| 商标 vocabulary | JIN writes `S` `C` `M` `iB`; DAFUYUAN writes `SORENTO` `CABANA` `MOCHA` `BRAVAT`. `brands.brand_code` is `SORENTO`, not `SRT`: the prefix is not derivable. |
| 品名 vocabulary | 连体马桶 分体马桶 座头 分体座头 水箱 盆 盆小孔 2078盆 盖板 飞机 葫芦飞机 大四方飞机 挂盆 台下盆 台中盆 半嵌盆 台上盆. |
| Merged 型号 | B16:B17 (`7609对冲`), B20:B22 (`8605-RL`: 座头 250, 座头 横排180, 水箱), B23:B32 (`7604-RL高压`: five 座头 + 水箱 pairs across SORENTO / CABANA / 3 sizes), B33:B34. `item_code` is not in `_MERGE_FILL_FIELDS`, so covered rows drop; row 25 (CABANA 座头, 200 packed) becomes "no model number on a row with stock". |
| Negative numbers | `-7055` `-1264` `-7099` `-7249` `-7292` `-7018` `-244`: Excel stored the cell as a negative number. `_tokens("-7055")` already yields `["7055"]`. No catalogue code starts with `-` or carries CJK (0 of 15,317 products, 0 sets). 91 products DO start with a digit. |
| Catalogue shape | Size tokens vary per family: `SRTWC8318-200-RL`, `SRTWC8066-S-200-NEW`, `SRTWC8613-P-RL`, 250 omitted as the default. Pedestal `SRTWCX8605-P`, cistern `SRTWCY8605`, basin `SRTWB7055`, seat `SRTWC8613-SC`. |
| `apply` collapse | `supplier_inventory_service.apply` merges parsed rows by `item_code`, summing quantities. Four `8613` rows became one. |
| Alias admin | `system-management/import-field-aliases` page + API exist; `canonical_fields()` admits only `proforma_invoice` and `packing_list`, so today no other doc type is editable there. `import_field_alias` has no supplier column. |

## Owner rulings (17 Sep, Lavish)

- R1: the row key for a bare 型号 reads `SRTWC8613-150`. The joined, translated columns ARE
  the supplier code.
- R2: "Supplier says" shows that code as the supplier code, 品名 · 商标 beside it, as today.
- R3: word list per supplier.
- Earlier: no stripping of Chinese words, translate them; config on the Import field aliases
  page; Open fix in the same lane.

## Decisions

- **D1. Trigger = the supplier wrote a bare model number.** Composition runs only for a 型号
  matching `^[-0-9]`. A letter-led 型号 hands the matcher exactly the string it hands today.
  This is the regression guard: the 810 letter-led rows across the three existing lists take
  today's path byte for byte.
- **D2. Composition happens in the READER, and the composed code is the row's `item_code`.**
  The matcher is not changed at all: it receives `SRTWC8613-150` and walks rungs 0 to 7 as it
  does for any code today (alias, exact, separator, token set, size drop with the `250MM`
  description check, then sets). Alias key, `apply` merge key and "Supplier says" are all that
  string. Four `8613` rows become `SRTWC8613-P-180`, `SRTWC8613-150`, `SRTWC8613-200`,
  `SRTWC8613-250`; the SORENTO and CABANA pedestal pairs become `SRTWCX...` and `CWCX...`.
  Answer to the owner's question "will it affect the logic that already works": no, because the
  matcher never learns anything changed, and letter-led codes reach it unchanged.
- **D3. No stripping. Chinese words are translated, never dropped.** Every CJK run in 型号 and
  规格, and the whole 商标 and 品名 cell, resolves through the word list. A run with no entry
  aborts composition for that row; the row's key is then the raw join of what the supplier wrote
  (`7609对冲 150mm 连体马桶`, so the four `8613`-style siblings still stay apart), it walks the
  ladder as that string, misses, and waits in the Supplier codes picker. An unknown word costs
  one human pick, never a wrong bind (`7609对冲` must not become `7609`).
- **D4. Trap size is the matcher's existing rule, not "mm".** `_size_of` (3 digits, 100 to
  499) decides. `parse_spec` over 规格: `mm` removed; `横排` anywhere = `P`; first in-range
  3-digit number = size; leftover ASCII letter groups (`UF` `A` `PP` `NEW`) become trailing
  tokens; leftover CJK goes through the word list (abort on a miss) and is replaced by a
  separator, never by nothing; any leftover DIGIT run after the size is taken aborts (a `500`
  or a second number is not a trap spec we understand, so the row keeps its raw key rather
  than composing to a sibling's code); two or more numbers joined by `*` `x` `X` `×` are a
  dimension string, no trap tokens at all. The first model token must be at least two
  characters. A composed or raw key over 100 characters is a `RowProblem`, never a 500.
- **D5. Candidate string = prefix + model tokens + trap tokens, joined by `-`.** prefix =
  word(商标) + word(品名); model tokens = `_tokens(型号)` (sign already dropped) with CJK runs
  translated; trap = `P` then size then extras. `SRTWC8613-P-180`, `SRTWC8066-PP-150`,
  `SRTWB7055`, `SRTWCX8605-P-180`, `SRTWCY8605-RL`. The existing rungs then do the rest:
  `SRTWB7055` exact; `SRTWC8613-250` size-drops to `SRTWC8613` only if its description says
  `250MM`; `SRTWC8613-P-180` binds nothing while three `SRTWC8613-P*` products tie, so the
  owner picks once and the alias remembers.
- **D6. Word list = `import_field_alias`, doc type `supplier_inventory_word`, per supplier.**
  `field` = our token, `alias` = their word. A token is any string matching
  `^[A-Z0-9]{1,10}$` (uppercased on write, `WORD_TOKEN_RE` in the composer); the admin API
  validates the shape for this doc type instead of a closed list, so the owner can add
  `高压 -> HP` or `飞机 -> UR` from the page with no code change (review round 1 replaced the
  closed `WORD_TOKENS` list: a closed list made D7's "owner types the rest" and D11
  undeliverable). The form shows a plain uppercase text input for the token on this doc type.
  Per supplier (R3): one nullable `supplier_id` column on `import_field_alias` (migration),
  `NULL` = shared row. The original unique triple (doc_type, field, alias) STAYS: a supplier's
  own row differs from the shared row by its token (`S -> SRTX` for one supplier while the
  shared row says `S -> SRT`), never by repeating a pair that already exists, and a second
  supplier wanting the same pair is told to use the shared row (409 names the existing row's
  scope). Review round 3 tried two partial unique indexes instead and CI failed: 23 seeders,
  migration 311's `seed_import_field_aliases` among them, insert with
  `ON CONFLICT (doc_type, field, alias)`, which needs exactly that unique index to exist.
  Lookup: the supplier's own row for a word wins, else the shared row. The page gains a clearable,
  server-searched `Supplier` select (the paged fulfilment supplier lookup, not the 100-row
  bare select) shown for this doc type only, and the list shows the supplier's name as a
  second muted badge beside a scoped alias.
- **D7. Seed only what the data states, as shared rows; the owner types the rest.**
  Migration seeds (supplier NULL), six brand rows and nine type/trap rows: `SORENTO` `S` ->
  `SRT`; `CABANA` `C` -> `C`; `MOCHA` `M` -> `M`; `连体马桶` `分体马桶` -> `WC`; `座头` `分体座头` -> `WCX`; `水箱` -> `WCY`; `盆`
  `盆小孔` -> `WB`; `盖板` -> `SC`; `横排` -> `P`. NOT seeded: `对冲` `高压` `上线` `薄边` `新`
  `飞机` `葫芦飞机` `大四方飞机` `2078盆` `iB` `BRAVAT` and the BRAVAT basin kinds.
- **D8. Merged 型号 fills through.** `item_code` joins `_MERGE_FILL_FIELDS` with the same
  header-anchored guard. Quantities still never fill.
- **D9. One known re-key.** JINBAICHUAN's dismissal alias on bare `242` stops applying once
  that row composes (to `SRTWB242` if 商标 `S` and 品名 `盆`); it is one row, re-dismissed once
  from the picker if the ladder does not bind it. No other alias is on a bare code.
- **D10. Open = same fetch as Download, then a new tab.** When the item has no CDN url, the
  Open button fetches through `fetchBytes`, creates a blob url and `window.open`s it. With a
  CDN url the plain link stays. No backend change.
- **D11. Word edits re-key.** Adding `高压 -> HP` later turns `7604-RL高压 横排180mm SORENTO 座头`
  into `SRTWCX7604-RL-HP-P-180` on the next upload; a manual alias recorded under the raw-join
  key no longer applies and the row asks once more. Accepted: the alternative (a key that never
  changes) is the raw join for every row, which the owner rejected in R1.

## Honest expectation

Composition binds the plain rows (`SRTWB7055`, `SRTWB888`, `SRTWB1264`, `SRTWCY8605`,
`SRTWCX8605-P`, `SRTWC8066-SH-UF`). Rows whose catalogue code carries a token the sheet does
not state (`-RL`, `-NEW`, `-PJ`) stay unbound until the owner picks once; the alias then
answers the next upload. Same road JINBAICHUAN took (79 unbound on first upload).

## Out of scope

Editing the word list from the Supplier codes tab; translating 备注; `.xls` merged cells;
any change to `supplier_code_matcher.py`.

## Slices (one PR)

- **S1 Reader + composer** - `supplier_inventory_reader.py`: `item_code` fill-through (D8);
  bare rows composed through a `WordList` built for the supplier (no `model_no` field: nothing
  downstream reads the raw 型号, the key is the code). New
  `app/services/scm/supplier_code_composer.py`: `WORD_TOKEN_RE`, `MAX_KEY_LENGTH`,
  `parse_spec()`, `compose(model_no, spec, brand, product_name, words) -> Optional[str]`,
  `raw_key(...)`.
  `read_workbook` gains `words: Optional[WordList]` (injectable like `resolver`; built from
  `db` + `supplier_id` on the normal path). Tests: `test_supplier_inventory_reader*.py`, new
  `test_supplier_code_composer.py`.
- **S2 Word list storage** - migration: `import_field_alias.supplier_id` nullable FK; the
  unique triple is kept; seed rows; downgrade removes every word row and every scoped row.
  `canonical_fields()` branch; `AliasResolver`-style `WordList.for_supplier(db, supplier_id)`.
  Admin API: `supplier_id` accepted on create and returned on list, validated to exist.
  Alembic id <= 32 chars; `down_revision` re-parented at PR time via `scripts/alembic-reparent.sh`.
  Tests: `test_import_field_aliases*.py`.
- **S3 Service** - `supplier_inventory_service.preview/validate/apply` build the word list
  for the chosen supplier and pass it to the reader; nothing else changes. Tests:
  `test_supplier_inventory_service.py` (a bare-code file binds `SRTWB7055`; a letter-led file
  produces the same rows and binds as before).
- **S4 FE** - Import field aliases page: `Stock list words` doc type, clearable server-searched
  Supplier select + uppercase token input on the form, supplier badge in the list; Open fix in
  `AttachmentPreviewModal.tsx` (security round 1: only PDF, PNG, JPEG, GIF, WebP and plain text
  open inline, anything else is re-typed as octet-stream so an uploaded HTML or SVG cannot run
  in the app origin; the tab is opened synchronously with `window.open('', '_blank')` and its
  `opener` nulled afterwards, never with a `noopener` feature string, which makes `window.open`
  return null by spec; a non-inline type such as xlsx closes the blank tab and downloads with one
  toast; the blob URL is revoked; the button shows a busy state).
  Supplier codes tab (`SupplierCodesTab.tsx`): a `Stock list words` link (icon button with
  label, `PageHeader`-adjacent toolbar) to `/system-management/import-field-aliases?doc_type=supplier_inventory_word`,
  the page honouring that query param as its initial doc type.
  Tests: `AttachmentPreviewModal.test.tsx`, `ImportFieldAliasesList.test.tsx`,
  `ImportFieldAliasFormDialog.test.tsx`, `SupplierCodesTab.test.tsx`.
- **S5 Browser** - owner file re-uploaded on a DAFUYUAN plan on a prod copy; JINBAICHUAN plan
  re-uploaded, bound count unchanged (363); Open on the stock list attachment opens the sheet.

## Lane

Worktree `.claude/worktrees/stock-list-bare-codes`, test DB `sorento_slbc_ci`. Both stack
slots (:3080 board-undo, :3082 oi-cascade) are taken on 17 Sep; boot the S5 stack when one
frees. Pipeline: tester reds first (S1 to S4 test lists in the UAC), one coder for the lane,
reviewer + security-reviewer (word list is an admin-edited surface that shapes matching) +
tester browser pass in parallel, guide-writer, DoD, PR.
