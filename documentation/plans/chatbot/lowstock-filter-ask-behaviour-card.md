# Behaviour card: the low stock report asks for its filters before it runs (LOWSTOCK-FILTER-ASK)

Status: ASKED (2 Oct 2026), waiting on owner answers Q1-Q5. No code until answered.
Plan: `PLAN-lowstock-filter-ask-2oct.md`.

## Step 1 - what happens today (trace, `main` 6864cd0b)

"Sorento water tap low stock list":

1. **Parser.** `LOW_STOCK_ADDENDUM` (`app/services/chatbot_parser_prompt.py:118`) sets
   `intent_hint "low_stock_report"`, `domain_hint "inventory"`. It teaches only warehouse,
   product and date words, and says a bare token here "usually is" a product. The
   brand + category split ("sorento water closet" -> brand + category) is taught only inside
   the top selling block (`:537`). Most likely output: `{raw:"Sorento", hint:"brand"}`,
   `{raw:"water tap", hint:"category"}`; risk: one product entity "Sorento water tap".
2. **Runtime.** The inventory domain is kept (`turn_runtime.py:1409-1422`); an empty
   subject is allowed for this intent only (`gate.py:135`); category and brand are
   `optional_filter` under inventory (`turn/policy_rows.py:146`), so nothing asks a question.
   The shared resolver sends brand/category to the promotion type (`entity_resolver.py:113-145`).
   If neither word is placed, `would_be_unfiltered` (`turn_runtime.py:2864-2871`) can end the
   turn in the generic inventory miss instead of the report.
3. **Lane.** `run_fetch` (`lanes/business/__init__.py:1505-1585`) checks the
   `scm.low_stock_report` grant, resolves only a WAREHOUSE word, then prunes entities to ones
   whose code contains a typed word. `fetch.py:935-955` builds `product_codes` from product
   entities only. Brand and category never become arguments.
4. **Route.** `GET /api/v1/scm/low-stock-report` (`app/api/v1/scm/low_stock_report.py:537-543`)
   takes `warehouse_codes, product_codes, date_from, date_to, contact_id, space_id`, and
   `_prepare` (`:451-497`) creates the reorder run (`create_run`, whole book when no codes)
   and enqueues `generate_low_stock_report(...)` with NO `split`, `suppliers`, `categories`.
   The MCP tool declares the same six params (`sorento_crm_mcp/catalog.py:550-553`).
5. **Reply.** The MCP presenter (`presenters.py:2281-2362`): "Low stock report - as of
   dd/mm/yyyy" / "Low: X of Y planned products" + the whole-book workbook. Nothing says
   "Sorento" or "water tap" was ignored.

What the report service ALREADY supports (built for the in-app page, PLAN-excel-preview-26sep):

| filter | where | key |
| --- | --- | --- |
| category | `build_low_stock_view(categories=)` `low_stock_report_service.py:271-320` | master `category_code`, "No category" for blank |
| supplier | same, `suppliers=` | the run row's frozen `supplier_name`, "No supplier" for blank |
| group by | `split` = `none` / `supplier` / `category` / `supplier_category`, one "<key> - Low" + "<key>" sheet pair per group | same keys |
| brand | **none** (no brand column; categories carry a decoded `brand_hint`, `models/product.py:53`) | - |
| location | the RUN's `warehouse_codes` (already wired from chat) | warehouse code |

`generate_low_stock_report` (`app/tasks/export_tasks.py:1102`) already takes `split`,
`suppliers`, `categories`; only the chat route never sends them. A supplier split is refused
422 for a contact without the `purchase_orders.supplier` key (the sheet titles would leak the
names the hidden column hides).

Already resolvable from chat: category words (`resolve_category_token` / `resolve_category_class`,
`lanes/business/services.py:627,758`, "water tap" -> its class's categories), brand words
(`turn_runtime.active_brands` / `brand_rows_for_word`). **No supplier resolver** exists for chat.

Prior work: LOWSTOCK-SHOW-ALL #1382 (Low = on hand below reorder level, All = every planned
product), TOP-N-UNCAP #1407 (unrelated mechanism, top selling ranking). Backlog BL-065
("Category as a run scope ... Trigger: the owner asks to scope the report by category") is
this trigger arriving.

## Proposed behaviour

The bot runs NOTHING until three things are settled: **category**, **supplier**, **group by**.
What the message already names is used, and only what is missing is asked, ONE question per
reply, in that order. "all" (also "any", "semua", "全部", "skip") settles an axis as "no
filter". The reorder run starts only on the turn that settles the last one.

Wording the user sees (exact):

- Category missing: `Low stock report: which category? Reply with a category (e.g. water tap) or "all".`
- Supplier missing: `Low stock report for water tap: which supplier? Reply with a supplier name or "all".`
- Group by missing: `Group the report by: 1. Supplier  2. Category  3. No grouping`
- A brand named is shown in the header line: `Low stock report for Sorento water tap: ...`
- Several categories match: `Which category do you mean? Reply with one code: SRT-FT, MOC-FT` (the top selling wording).
- Several suppliers match: `Which supplier do you mean? 1. JINBAICHUAN  2. JINBAICHUAN HARDWARE`.
- Nothing matches: `I don't know 'xyz' as a category. Reply with a category or "all".` (re-asks the same axis).
- Settled, then the existing ready/pending/busy/error lines, with the filters on the first line:
  `Low stock report (water tap, all suppliers, by supplier) - as of 02/10/2026` / `Low: 12 of 40 planned products`.
- Filters keep nothing: `No products in the low stock report for water tap, JINBAICHUAN.` (no file).

Examples (the dev data is not in this cloud sandbox; codes are the category codes in the repo's
evidence files, SRT-FT / SRT-WC / SRT-KS, and supplier names from committed fixtures):

1. "Sorento water tap low stock list" -> brand Sorento + category water tap (Sorento's
   categories of class water tap) -> asks supplier -> "all" -> asks group by -> "1" -> runs,
   workbook keeps those categories, split by supplier.
2. "low stock report" -> asks category -> "water closet" -> asks supplier -> "JINBAICHUAN"
   -> asks group by -> "2" -> runs.
3. "low stock all categories all suppliers by category" -> nothing to ask -> runs at once.
4. "low stock for SRTWT7408" (a product code) -> the product IS the scope: no category or
   supplier asked; group by asked? (see Q2).
5. "low stock BRW" -> warehouse is a RUN scope, not a filter: still asks category, supplier,
   group by.

Edge cases:

- A contact without `purchase_orders.supplier`: the supplier question is never asked (the
  column is hidden for them), and group by offers only `1. Category  2. No grouping`.
- A message mid-questions that is a different ask ("stock for CB100") drops the pending
  questions and is answered normally; "cancel" ends with `Low stock report cancelled.`
- Unknown word twice in a row on the same axis: the second miss ends with
  `I could not place 'xyz'. Ask again with a category or "all".` (never-stuck: no loop).
- A grant refusal, rate limit, a plan already running, a failed run: unchanged lines.

## Questions (at most 5, each with a recommendation)

- **Q1. Where do category / supplier apply?** (a) A WORKBOOK filter: the run still plans the
  whole book (as today) and the file keeps only the matching rows, through the `categories` /
  `suppliers` / `split` the in-app page already uses. (b) A RUN scope: add a category
  narrower to `create_run` (BL-065), so the plan itself covers only those products.
  **Recommend (a)**: already built and tested end to end, no migration, and a product's
  low/All figures do not depend on which other products the run covered. (b) only buys a
  faster run.
- **Q2. Ask one question per reply, or all missing ones in one message?** (a) one per reply,
  in order category -> supplier -> group by (a bare "low stock report" is three short
  questions); (b) one message listing all missing items, answered in one line ("water tap,
  all, supplier"). **Recommend (a)**: each answer is read without the parser guessing which
  word belongs to which axis; a message that names things up front skips straight past them.
  For a product-code ask (example 4) ask only group by.
- **Q3. Brand.** The workbook has no brand column. (a) A brand narrows the categories
  (category `brand_hint`, e.g. Sorento + water tap -> Sorento's water tap categories; brand
  alone -> all of that brand's categories, and the category question is skipped);
  (b) ignore the brand and say so. **Recommend (a)**: categories already carry the brand
  (SRT-xx), so it is the same filter, no new column.
- **Q4. Group by options.** (a) `1. Supplier  2. Category  3. No grouping`; (b) only
  supplier | category (no "no grouping"); (c) add `Supplier x Category` too.
  **Recommend (a)**: "no grouping" is today's two-sheet file and the natural answer to "all".
- **Q5. Supplier matching.** A typed word matches suppliers whose name contains it as a whole
  word, case-insensitive (several -> numbered pick, none -> "I don't know ... as a supplier").
  (a) match against the supplier master list; (b) match only suppliers that appear on the
  low stock rows (needs the run first, which breaks "no run before filters").
  **Recommend (a)**.
