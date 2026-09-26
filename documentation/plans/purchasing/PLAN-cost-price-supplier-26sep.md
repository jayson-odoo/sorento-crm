# PLAN: Cost price from the supplier's price list, verified before it applies (#1288)

Status: draft plan + UAC, round 2 (26 Sep 2026). Owner rulings of 26 Sep 23:45 MYT applied for Q1,
Q2, Q5, Q6, Q7, Q9, Q10 (section 12); Q3, Q4 and Q8 answered in plain language on PR #1291 and
re-asked with a restated recommendation; Q11 to Q15 not yet answered. Track: full (two new
tables and a migration, new permissions, a new public ingest surface with uploads). Nothing
built; this lane is docs only (draft PR #1291).
UAC: `cost-price-supplier-acceptance-criteria.md` (same folder; the Journey is there and every AC
traces to a step in it).
Mockups: `mockups/cost-price-upload-review.html`, `mockups/cost-price-verification.html`,
`mockups/supplier-price-page.html`. They predate the round 2 rulings: the effective date field,
the "Scheduled" history row and the `SRT2800-GY` to `SRT2800-GR` one-edit suggestion in them are
superseded by section 12 (Q3, Q8) and are redrawn in Phase 1 once the owner answers.
Classification: CORE (suppliers and the procurement base are core, `PRINCIPLES.md` "Modular
architecture"); tables in `public`, routes under the existing `procurement` module guard.
Companions: #1280 unified identity (draft PR #1285: the supplier login that replaces the token
later, and the audit actor contract this plan writes to), #1281 audit trail.

All line refs are `origin/main` at 51d30ccc5. Paths are relative to `sorento_crm_backend/` (BE)
and `sorento_crm_frontend/` (FE) unless given in full. No database was reachable from the planning
session, so the row counts this plan needs are named as S1 pre-flight queries (section 3.8), not
stated as facts.

## Contents

0. Owner words
1. Why
2. The decision in one paragraph
3. What exists today (measured)
4. Data model
5. Parsing the supplier's Excel
6. Matching codes
7. Verification and apply
8. The supplier page and its link
9. Audit trail
10. Permissions and security
11. Slices, definitions of done, out of scope, risks
12. Grill questions for the owner

## 0. Owner words

Verbatim from #1288 (26 Sep 2026):

> "Looking at this Excel is the cost price of the product. So we need to allow the user to upload
> this. But I want to exploit a bit further with our current token capability, which is I want
> this to be a web page that can be access controlled because the supplier of Sorento is mainly
> from China. So probably they won't have WhatsApp, they will have WeChat. So I'm thinking instead
> of letting the user from Sorento upload the cost to our system, we can have a page for the
> supplier to maintain instead of them maintaining in the Excel. Of course, if they want to upload
> this Excel to the web page, it's also possible. But again, it needs to be more process control
> because we cannot let them directly upload and override our system cost price. There needs to be
> a verification process digitalized in the system. So I want first, the upload of this by the
> Sorento user is definitely a must. And I want us to also explore putting this process to the
> supplier and verify by Sorento internally before applying the change to the actual DB value. So
> which is why it's very important for the audit trail to exist for this also so that we can trace
> what happened."

The file: `TO SORENTO-19&12&22&28&25 series price list 20260917.xlsx`, from XIAMEN TAIYANG
TECHNOLOGY. One sheet per series (19, 12, 22, 28, 25; 40, 24, 18, 58, 118 rows). Rows 1 to 5 are the
letterhead and title (merged). Row 6 is the header: 序号 (no.), 型号 (model = our product code,
sometimes with a packaging note in full-width brackets, e.g. `CB2500SS-BL（彩盒）`), 产品配置
(configuration, Chinese, merged down across rows that share it), 价格 (price, a number, currency not
stated, presumably CNY).

Three things bind: the Sorento user's upload comes first; nothing the supplier sends may reach the
live price without a Sorento verification; every step is traceable.

## 1. Why

- **Supplier prices are typed by hand today, one link at a time.** The only staff write paths to
  a supplier's price are the product-supplier CRUD modal, the product Excel import, and side
  effects of PO and alias flows (section 3.2). A 258-row price list means 258 edits, and nothing
  records which price list a number came from.
- **Nothing stages a price change.** Every existing writer lands on the live value immediately;
  there is no pending state, no second person, no history beyond generic
  audit rows (and `product_suppliers` is not audited at all, section 3.6).
- **The supplier cannot reach us on WhatsApp**, which is what the customer portal's token and OTP
  are built on (`portal_tokens` is keyed to a Respond.io contact). The precedent for a Chinese
  supplier is a plain token link, already shipped read-only for supplier requests (section 3.5).
- **The reorder engine prices every recommendation from this value** (section 3.2), so a wrong
  or unverified price reaches purchasing decisions directly.

## 2. The decision in one paragraph

**The price is the existing `product_suppliers.unit_cost` + `currency` pair; nothing about it
moves.** Everything the supplier or a staff member proposes lands first in a **change set**: one
header row per batch (supplier, source channel, currency, status, source file, who submitted,
who applied and when) and one line per parsed row (the supplier's code verbatim, what it
matched, the price at parse time, the proposed price, the verifier's decision). A verifier who is
not the submitter accepts or rejects each line and clicks Apply, which writes the accepted prices
into `product_suppliers` in one transaction. **The applied lines are the history**: no third
table; a product's cost history is its accepted lines from applied sets. The supplier reaches the
same change set through a token link (a new small `supplier_price_links` table, modelled on
`SupplierNotice.public_token` and `OnboardingRequest`), delivered as a plain URL, a QR code and a
bilingual message to paste into WeChat; the supplier can only ever create or edit a Draft and
submit it. `products.cost_price` (MYR, used for stock valuation) is not touched (Q1).

Why a change set table and not the AutoCount pull's "job row plus JSONB phase" shape: that
precedent is justified by an immutable snapshot the same user reviews within minutes. Here a
different person decides per line, possibly days later, the supplier edits lines across visits,
and the lines must stay queryable per product as history. Those are three concrete needs the job
row does not meet, which is the evidence `PRINCIPLES.md` asks for before a new table.

## 3. What exists today (measured)

### 3.1 Where a cost lives

- **`products.cost_price`** `Numeric(12,2)`, nullable (`app/models/product.py:227`), sharing
  `products.currency` `String(3)` default `MYR` (`:229`) with `list_price` (`:226`) and
  `invoice_price` (`:228`). `Product` is audited (`__audit_track__`, `:187-188`); the activity
  timeline labels it "Cost price" (`app/services/activity_service.py:141`).
- **`product_suppliers`** (`app/models/procurement.py:96-123`): `unit_cost` `Numeric(12,2)`
  (`:110`), `currency` `String(3)` (`:111`), `moq`, `order_multiple`, `is_primary_supplier`,
  `standard_lead_time_days` **NOT NULL with no default** (`:106`), `created_at` only (no
  `updated_at`), unique on (product_id, supplier_id) (`:122`), company scoped. **Not audited.**
- **No cost history table.** Price advice is derived from PO lines by
  `app/services/scm/price_history_service.py:1-100`, which compares the last paid price against the
  "standing cost" `product_suppliers.unit_cost` (`:79-81`).
- Transactional `unit_cost` columns (PO lines, shipment lines, SPO allocations, picking lines,
  reorder recommendations, plan row decisions) are snapshots and are out of scope.

### 3.2 Who reads and writes it

- **Reorder engine (reads):** `load_supplier_candidates` reads `ps.unit_cost, ps.currency`
  (`app/services/scm/reorder_engine.py:837-845`); `last_purchase_costs` (`:783-822`) lets the
  last order win over the typed price. Also `decision_service.py:273,1460`,
  `reorder_level_service.py:473`, `summary_order_service.py:2313-2449`.
- **Writers of `product_suppliers.unit_cost`:** `procurement_service.py:6972`,
  `product_service.py:1021,1663` (product Excel import), `rules/product_rules.py:397`,
  `scm/supplier_code_alias_service.py:251`, `scm/product_supplier_service.py:75,84` (raw SQL),
  `scripts/backfill_product_supplier_from_last_po.py:321`, and the CRUD routes
  `app/api/v1/procurement/product_suppliers.py:61-95`, which need **only a login** although
  `procurement.product_suppliers.{view,add,edit,delete}` exist (`app/rbac/permission_registry.py:226`).
- **`products.cost_price` writers and readers:** the ESB masters push writes it only when present
  (`master_ingest_service.py:589-590`); the **AutoCount pull does not** (`autocount_pull_service.py:425-473`
  maps `list_price` only). Stock valuation reads it in MYR (`scm/dashboard_service.py:19,369,434`,
  `scm/analytics_service.py:414-418`). `PUT /master-data/products/{id}` needs only a login
  (`app/api/v1/master_data/products.py:329-343`). `ProductDetail.tsx:384-385` formats cost as MYR
  regardless of `product.currency`.
- **Kept out of cost on purpose:** price tags and the dealer kit (`dealer_kit/product_facts.py:14`),
  product dropdowns (`products_select.py:39`). The chatbot's last purchase cost comes from PO lines
  behind the per-contact reveal key `purchase_orders.cost`
  (`contact_field_reveal_service.py:45`); it does not read either column.
- **Staff RBAC on seeing cost:** none exists; no `view_cost` slug.

### 3.3 The supplier

- `suppliers` (`procurement.py:39-93`, audited): `supplier_code` (unique per company, arrives from
  AutoCount as the creditor code), `supplier_name`, one `contact_name` / `email` / `phone_number`,
  `country_id`, `is_active`. **No currency column and no Chinese name column.**
- Supplier currency is inferred: `currency_resolution.supplier_price_list_currency` returns the
  single distinct `product_suppliers.currency` for the supplier, else None
  (`app/services/scm/currency_resolution.py:128-150`); precedence there is upload form, document,
  supplier price list, nothing; no house default (`:1-13`).
- No supplier contacts table. WeChat recipients elsewhere are picked from `respond_contacts`
  (`scm/supplier_notice_service.py:970-1015`).

### 3.4 Parsing precedents

- `app/services/scm/outstanding_reader.py`: `sheet_rows` (`:227-238`), `sheet_merges`
  (`:245-265`, maps covered cells to their anchor; needs a non read-only workbook),
  `every_sheet_rows` (`:300`), `.xls` via xlrd (`:211`).
- `app/services/scm/supplier_inventory_reader.py`: a Chinese supplier file keyed on 型号. Headers
  resolve through `import_field_alias` (`:1-17,26`); merged cells fill down for body fields only
  (`_MERGE_FILL_FIELDS`, `:46-54`); `model_no` kept verbatim (`:68-71`); `letterhead` keeps the text
  above the header (`:81-84`).
- `import_field_alias` (`app/models/import_alias.py:26-60`): doc_type, field, alias, locale,
  optional supplier_id; `normalize_header` applies NFKC (`app/services/import_alias_service.py:37-44`).
- Currency from a price header: `currency_resolution.price_column_currency`, tokens rmb, 元, ¥ to
  CNY (`currency_resolution.py:24-45`), used by `proforma_invoice_reader.py:683-694`.
- Preview then apply is stateless everywhere (`scm/fulfilment.py:132-205`,
  `purchase_history.py:105-152` for the order inquiry import, which enqueues `order_inquiry_import`
  on `imports`); the 25 MB cap and retained upload are `scm/upload_intake.py:24,55`; the
  single-company guard is `api/v1/scm/outstanding_import.py:57-79`.
- There is no "low stock import": the low stock report is a workbook the system produces
  (`api/v1/scm/low_stock_report.py`, and `PLAN-excel-preview-26sep.md` is its viewer). The order
  inquiry import is the nearest upload precedent and is stateless, so neither gives a staging
  model to copy.

### 3.5 Token access precedents

- **Supplier request link (read-only, Chinese first):** `SupplierNotice.public_token` /
  `public_token_expires_at` (`app/models/supplier_notice.py:126-127`), open tracking
  (`:75-77`), minted with `secrets.token_urlsafe(32)` and a 30-day TTL
  (`supplier_notice_service.py:1161-1162,1228-1233`), older links expired on resend
  (`:1240-1270`), one 404 body for unknown, expired or retired (`:1273-1307`). Route
  `app/api/v1/public/supplier_request.py:28-51`; page
  `app/(public)/c/[company]/supplier-request/[token]/page.tsx` with hard-coded bilingual labels
  (`:6-8`).
- **Outside party edits rows, then internal review:** `OnboardingRequest`
  (`app/models/onboarding.py:132-192`): token, `expires_at`, `revoked_at`, status, reviewer,
  retained source file; public `PUT /rows` and `POST /submit` (`app/api/v1/public/onboarding.py`),
  no OTP by design (`:10-14`).
- **Customer portal:** `portal_tokens` + OTP over WhatsApp (`app/models/portal.py:26-62`), keyed to
  a Respond.io contact; not usable for a supplier with no WhatsApp. #1280 (PR #1285) replaces it
  with a user session; a supplier login rides on that later.
- **Rate limiting:** `app/services/rate_limit.py:41` `hit(bucket, ident, limit, window_seconds)`,
  Redis-backed, fails open; used only by the portal OTP and the low stock report.
- **QR:** `qrcode.react` is already a dependency (`package.json:66`), used as `QRCodeSVG` in
  `components/contacts/PortalLinkDialog.tsx:4`.
- **i18n:** `react-i18next` is installed but wired only into a test page; the shipped supplier page
  hard-codes both languages. This plan follows the shipped page (Q12).

### 3.6 Audit today

- `audit_logs` (`app/models/audit.py:9-46`): entity_type, entity_id, action, user_id, contact_id,
  old/new JSONB, description, ip, trace_id, company_id. The before-flush listener
  (`app/services/audit_service.py:323-429`) records CREATE/UPDATE/DELETE for `__audit_track__`
  models; a contact actor comes from `session.info["actor_contact_id"]` (`:403-410`); manual
  writers `log_audit` (`:109`) and `log_import_audit` (`:156`).
- #1280's plan section 8 adds `actor_type` (including `public_link`), `real_user_id`,
  `auth_method`, `session_id`, `job_id` to every row. This plan writes to that contract and does
  not wait for it (section 9).

### 3.7 Matching precedent

- `products.product_code` `String(100)`, unique per company (`product.py:195`).
- `scm.supplier_product_code_alias` (`app/models/scm.py:1344-1403`): supplier_id, verbatim
  `supplier_code`, product or product set, `source` auto / manual / dismissed, `matched_by`;
  unique on (company, supplier, upper(code)).
- `app/services/scm/supplier_code_matcher.py` `resolve(db, supplier_id, codes, *, remember=True,
  actor=None)` (`:196-215`): alias, exact, separator-normalised, token-set, trap-size drop, then
  product-set rungs (`:12-52`); `remember=False` writes nothing. `_norm` strips `[-\s]+` and
  lowercases (`:105-107`) with **no NFKC**, so `（彩盒）` would not fold.

### 3.8 S1 pre-flight queries (run on the prod copy before Phase 2)

1. Links per currency: `SELECT currency, count(*) FROM product_suppliers GROUP BY 1`.
2. TAIYANG's links: count, distinct currency, how many carry a `unit_cost`, most common
   `standard_lead_time_days`.
3. How many of the owner's file's codes match `products.product_code` exactly, after NFKC and
   bracket stripping, and via existing aliases (run the S1 reader against the file in a shell).
4. Suppliers holding links in more than one currency (these make the set currency ambiguous).
5. Which roles today can reach `/procurement/product-suppliers` writes (for the AC-S2-14 sweep).

Alembic head at 51d30ccc5: `sb3_company_stock_push_at` (single head).

## 4. Data model

Designed backwards from the Journey (UAC). Two tables for the change set, one for the link, one
column-free change to `product_suppliers` (it gains `__audit_track__`). One migration, chained on
the head at Phase 2 time via `./scripts/alembic-reparent.sh`; revision id under 32 characters
(`cpc1_cost_price_change_sets`).

### 4.1 `cost_price_change_sets` (CompanyScopedMixin, `__audit_track__`)

| Column | Type | Why (Journey step) |
| --- | --- | --- |
| `id` | UUID PK | |
| `code` | text, unique per company, `CPC-0001` from a sequence | J6, J12: the name people say and the supplier sees |
| `supplier_id` | FK `suppliers.id` ON DELETE RESTRICT, NOT NULL | J2 |
| `channel` | text: `staff_upload`, `supplier_page`, `supplier_upload` | J12, J14; check constraint |
| `status` | text: `draft`, `pending_verification`, `applied` | J5, J8, J9; check constraint. Return sends it back to `draft` with `returned_reason`; Discard is a hard delete of a draft. Three values, no status engine: nothing else branches on it |
| `currency` | char(3) NOT NULL | J2 (AC-S1-07) |
| `source_attachment_id` | FK `attachments.id`, nullable | J14: the retained file (null for a table-only supplier set) |
| `source_meta` | JSONB | file name, sheet names, header row per sheet, merged-cell fills, letterhead text |
| `created_by_user_id` | FK users, nullable | J1 (null for a supplier set) |
| `submitted_by_user_id`, `submitted_at` | FK users nullable, timestamp | J5 |
| `submitted_via_link_id` | FK `supplier_price_links.id`, nullable | J12 |
| `returned_reason`, `returned_by_user_id`, `returned_at` | | J9 |
| `applied_by_user_id`, `applied_at` | | J8 |
| `created_at`, `updated_at` | naive UTC | |

Partial unique index: one row per (company_id, supplier_id) WHERE status IN ('draft',
'pending_verification') (AC-S1-14, Q10).

### 4.2 `cost_price_change_lines` (`__audit_track__`)

| Column | Type | Why |
| --- | --- | --- |
| `id`, `change_set_id` (FK, ON DELETE CASCADE) | | |
| `sheet`, `row_no`, `line_no` (序号) | text, int, text | J4: where in the file |
| `supplier_code_raw`, `supplier_code`, `packaging_note` | text | AC-S1-04 |
| `configuration` | text | J4 (产品配置) |
| `flags` | text[]: `configuration_from_merge`, `price_from_merge` | AC-S1-03 |
| `match_outcome` | text: `exact`, `normalised`, `alias`, `near`, `unmatched`, `ambiguous` | AC-S1-08 |
| `candidate_product_id` | FK products, nullable | the near match on offer |
| `product_id` | FK products, nullable | bound or mapped product |
| `mapped_by_user_id` | FK users, nullable | AC-S1-12: a manual map; the alias is written at apply |
| `current_unit_cost`, `current_currency` | numeric(12,2), char(3), nullable | AC-S1-09: captured at parse, re-checked at apply (AC-S2-06) |
| `new_unit_cost` | numeric(12,2), nullable | |
| `line_state` | text: `changed`, `unchanged`, `new_link`, `needs_attention`, `pick_one`, `skipped` | J4 tabs and filters |
| `skip_reason` | text | |
| `new_link_lead_time_days` | int, nullable | AC-S2-05 |
| `decision` | text: `accepted`, `rejected`, null | J7 |
| `decision_reason`, `decided_by_user_id`, `decided_at` | | J7 |

Change percent is computed on read, never stored. Index on `(product_id)` WHERE decision =
'accepted' for the history read (AC-S2-11).

### 4.3 `supplier_price_links` (CompanyScopedMixin, `__audit_track__`)

`id`, `supplier_id`, `token` (text, unique; `secrets.token_urlsafe(32)`), `recipient_name`,
`expires_at`, `revoked_at`, `issued_by_user_id`, `revoked_by_user_id`, `last_opened_at`,
`open_count`, `created_at`. One active link per supplier, enforced in the service (revoke the old
one in the same transaction as the new one, AC-S3-01), not by an index, because "active" depends
on the clock.

Why not reuse `supplier_notices`: a notice is one message about one request, with a channel and a
send log; this is a standing credential for a price page. Why not `portal_tokens`: it is keyed to
a Respond.io contact and OTP over WhatsApp, which the supplier does not have.

### 4.4 Nothing else

- No history table: applied, accepted lines are the history (section 2).
- No effective date column (Q3, re-asked round 2): the date a price starts is `applied_at`. If
  the owner answers that history must show the supplier's own list date, `effective_date` (date,
  default the apply date, never future) comes back on the set and AC-S2-08 is restored.
- No price basis column (Q4, re-asked round 2): `product_suppliers.unit_cost` already is the
  price field; the basis (FOB, EXW, tax) is not recorded until suppliers differ.
- No supplier currency column: currency resolves from the links (Q2). Trigger to add one: a
  supplier with no links yet uploads a list in a currency the header does not state, more than
  once.
- No supplier Chinese name column or alias: the letterhead match uses the English name and code
  (section 5.4 names the trigger).

## 5. Parsing the supplier's Excel

One reader, `app/services/procurement/supplier_price_list_reader.py`, used by the staff upload and
the supplier upload alike. Synchronous in the request: 258 rows parse in well under a second, and
the D27 rule (long jobs advance on the server) is for multi-stage background jobs. Trigger to move
it onto the `imports` queue: a real file over 2,000 rows or a parse over 5 s in the logs.

### 5.1 Steps

1. Open with openpyxl (not read-only, because `sheet_merges` needs `merged_cells`); `.xls` through
   the existing xlrd path. Reject over 25 MB, over 5,000 total rows, or a workbook with a sheet
   over 20,000 cells before reading values (zip-bomb guard, AC-S1-15).
2. For each sheet, scan rows 1 to 20 for the header: the first row where at least two of the four
   fields resolve through `import_field_alias` with a new doc_type `supplier_price_list`
   (seeded aliases: 型号 / 型號 / model / item / code to `item_code`; 价格 / 單價 / 单价 / price /
   unit price to `unit_price`; 产品配置 / 配置 / description / specification to `description`;
   序号 / no / s/n to `line_no`). The owner's file puts it at row 6 on every sheet; nothing assumes
   6. A sheet with no header is recorded in `source_meta` and skipped (AC-S1-02).
3. Text above the header is kept as `letterhead` (for the supplier match, 5.4).
4. Body rows: stop at the first 5 consecutive empty rows. Merged cells fill down for
   `description` (always) and `unit_price` (flagged `price_from_merge`, AC-S1-03); `item_code` is
   never filled, because a merged code would silently price two models under one name.
5. Code cleaning (AC-S1-04): NFKC-fold (turns `（彩盒）` into `(彩盒)`), trim, collapse inner
   whitespace, then split a trailing bracket group `^(.*?)\s*\(([^()]+)\)$` into `supplier_code` and
   `packaging_note`. The verbatim cell is `supplier_code_raw`. NFKC is applied in this reader, not
   added to `supplier_code_matcher._norm`, so the matcher's other callers do not change.
6. Price cleaning (AC-S1-05): numbers as numbers; strings stripped of `¥ ￥ 元 RMB CNY ,` and
   spaces, then `Decimal`; anything else (面议, blank, negative) leaves the price null and the
   line `needs_attention`.
7. Currency (AC-S1-07): the price header's token via `price_column_currency` if present, else
   `supplier_price_list_currency(supplier)`, else required in the dialog. The owner's file states
   no currency in its header and the owner confirms most of its prices are CNY (Q2 ruling), so on
   the TAIYANG fixture the currency comes from TAIYANG's existing links (CNY), or the uploader
   picks CNY when those links carry none (pre-flight query 2 says which).

### 5.2 The parse probe

`POST /procurement/cost-price-changes/probe` (multipart) parses without storing and returns the
suggested supplier, currency, sheet list and counts, so the upload dialog can pre-fill (J2) before
the user clicks Upload. `POST /procurement/cost-price-changes` (same file plus the chosen supplier
and currency) parses again, matches, and stores the Draft set in one transaction. Two parses of a
sub-second file are simpler than holding an unconfirmed upload somewhere.

### 5.3 Fixture

The owner's file, with prices and the supplier name replaced by synthetic values and every
structural quirk kept (letterhead merges, row 6 header, merged 产品配置, bracketed packaging notes,
one priceless row), is committed as `tests/fixtures/cost_price/taiyang_price_list.xlsx` and is the
golden input for AC-S1-01 to AC-S1-05. The tester writes the expected row counts before the reader
exists. **Prerequisite:** the file is not in the repository; the owner attaches it to #1288 (or
hands it to the lane) before Phase 2. Phase 1 needs only the mockups.

### 5.4 Supplier from the letterhead

Match the letterhead text (NFKC, uppercased, punctuation stripped) against active suppliers'
`supplier_code` and `supplier_name`. Exactly one hit pre-selects; otherwise the supplier field is
required, which costs one pick (AC-S1-06). The owner's file carries the English name, so it
pre-selects. Trigger for a Chinese-name alias per supplier: a supplier whose letterhead is Chinese
only has to be picked by hand on three uploads.

## 6. Matching codes

- Bind with `supplier_code_matcher.resolve(db, supplier_id, codes, remember=False)` on the cleaned
  `supplier_code`. Outcomes map onto `match_outcome` (AC-S1-08): alias, exact, separator-normalised
  bind; a single token-set candidate from the existing matcher is `near` (not bound, offered as
  `candidate_product_id`); several candidates are `ambiguous`; none is `unmatched`.
- No new matching rung (Q8, round 2 restated recommendation): the one-edit (Levenshtein) rung the
  round 1 draft proposed is dropped, because it is new code whose only output is a guess the user
  must confirm anyway. `near` comes only from what `supplier_code_matcher` already does; an
  `unmatched` line gets a product search picker. Trigger to add a one-edit rung: unmatched lines
  that turn out to be one-character typos of a real code are mapped by hand on three sets.
- A bound product not linked to this supplier is `new_link` (AC-S1-09).
- Two lines bound to one product are both `pick_one` (AC-S1-10, Q9).
- A manual map is stored on the line; the alias (`source=manual`, `matched_by='cost_price_set'`)
  is written only at apply (AC-S1-12), so abandoned sets do not teach the matcher.
- A skipped unmatched code writes nothing. Trigger to add "remember this skip" (a `dismissed`
  alias): the same code is skipped on three consecutive sets for one supplier.

## 7. Verification and apply

- **Decide:** `PATCH .../lines/{id}` with `{decision, reason}`; `POST .../decide-all` with
  `{decision}` for every undecided changed or new-link line (AC-S2-01). A verifier may also map,
  pick and skip on a supplier set (AC-S3-06), because the supplier cannot.
- **One Sorento verifier (Q6, owner ruling 26 Sep 2026):** one Sorento staff member holding
  `verify` decides a set; there is no second approval level. That person may not be the one who
  uploaded or submitted the set: the uploader or submitter of a staff set cannot decide, return
  or apply it (AC-S2-03), superadmin included. On a supplier set the supplier submitted it, so
  any one verifier may map, pick and apply it.
- **Apply** `POST .../apply` (AC-S2-04 to AC-S2-08; no `effective_date` body while Q3 is
  re-asked, see section 12):
  1. `UPDATE cost_price_change_sets SET status='applied', ... WHERE id=:id AND
     status='pending_verification'`; zero rows means 409 (concurrent apply).
  2. Refuse with 422 if any changed or new-link line is undecided.
  3. For every accepted line, lock the `product_suppliers` row (`SELECT ... FOR UPDATE`) and compare
     its `unit_cost`/`currency` to the line's captured values; any mismatch rolls back with 409
     listing the stale lines (AC-S2-06).
  4. Write `unit_cost` and `currency` through the ORM (so the audit listener records old and new);
     create missing links with the lead time rule (AC-S2-05); write aliases for mapped lines.
  5. One `COST_SET_APPLY` audit row with the full change list (section 9).
  6. Post-commit, best-effort: the notification to the submitter (AC-S2-12).
  Apply is not destructive (the old price stays in the line and the audit row), so it is a single
  click with no dialog and no countdown; the button names the accepted count.
- **Return** `POST .../return` with a required reason: status back to `draft`, decisions cleared,
  submitter and supplier page can edit again (AC-S2-09).
- **History read** `GET /procurement/products/{id}/supplier-cost-history` (AC-S2-11) joins accepted
  lines of applied sets to their set.
- **Other write paths (Q13):** the CRUD routes get their existing permission slugs enforced
  (AC-S2-14); the PO, alias, rules and import writers stay as they are (internal and staff-driven)
  but are now audited because `product_suppliers` gains `__audit_track__`. The owner's rule
  ("cannot let them directly upload and override") is about the supplier, and the supplier has no
  other path.

## 8. The supplier page and its link

### 8.1 Issuing (staff)

Supplier record gear menu, Share price page (permission `procurement.suppliers.price_link`):
`POST /procurement/suppliers/{id}/price-link` issues (and revokes the previous), `GET` returns the
current one with open stats, `DELETE` revokes through the 5 s deferred action (reversible in the
sense that a new link can be issued). The modal (Frame A of the S3 mockup) shows the URL, a
`QRCodeSVG`, Copy link, Save QR image (the SVG rendered to PNG in the browser) and Copy message:

```
Sorento 价格维护 / Sorento price page
请在此更新贵司的产品价格:
<url>
(<expiry date> 前有效 / valid until <expiry date>)
```

Staff paste it into their own WeChat chat with the supplier (Q14). No WeChat API, no sending
from the server.

### 8.2 Public routes (`app/api/v1/public/supplier_prices.py`, mounted under `/api/v1/public`)

Token in the path, as the supplier-request route does. Each resolves the link with company scope
opened then pinned to the link's company (`supplier_notice_service.py:1273-1307` pattern), and
returns the one 404 body on any failure.

| Route | Does | AC |
| --- | --- | --- |
| `GET /supplier-prices/{token}` | supplier display name, currency, linked products with current price, the open set if any | AC-S3-03 |
| `PUT /supplier-prices/{token}/lines` | upsert edited prices into the open Draft set (created on first edit) | AC-S3-04 |
| `POST /supplier-prices/{token}/upload` | parse with the S1 reader into the Draft set | AC-S3-05 |
| `POST /supplier-prices/{token}/submit` | Draft to Pending | AC-S3-06, AC-S3-07 |
| `GET /supplier-prices/{token}/history` | own sets and per-line outcomes, no reasons | AC-S3-08 |

Every route calls `rate_limit.hit` on both the token and the client IP (AC-S3-09). What the supplier
sees is its own price for its own linked products; that is information it already holds, so
exposing it is safe. Nothing else is serialised (an explicit response model, asserted as a whole
key set in a test, per the lesson on allowlists and manual serialisers).

### 8.3 Page (`app/(public)/c/[company]/supplier-prices/[token]/page.tsx`)

Mobile first (375px is the design width, 1280px must not clip). Chinese first with English
beneath, hard-coded in a `labels.ts` beside the page like the supplier-request page; a 中文 / EN
toggle swaps the lead language and is remembered per browser in guarded `localStorage` (Q12).
Tabs 价格表 Prices, 上传Excel Upload, 记录 History (Frames B to E); a pending set makes the table
read-only (Frame D); an expired link shows only Frame F. Layering holds on the public page too:
component, hook, `publicSupplierPriceService.ts`, `lib/api-client`.

### 8.4 Later: the supplier login (#1280)

When #1280 lands a user for an outside party, a supplier user holding a link to its supplier row
replaces the token: the same routes move behind the session, `submitted_via_link_id` gains a
sibling `submitted_by_user_id` value, and the audit rows become `actor_type = user`. Nothing in
this plan's tables blocks that; the link table simply stops being issued.

## 9. Audit trail

Written to #1281's standard and #1280's actor contract (PR #1285, section 8):

- **Row changes:** the four tables (`cost_price_change_sets`, `cost_price_change_lines`,
  `supplier_price_links`, `product_suppliers`) are `__audit_track__`, so every create, update and
  delete carries old and new values (AC-AU-01). `product_suppliers` gaining it is the single most
  valuable line in this plan: today a price can change with no trace at all.
- **Named events** (AC-AU-02), written with `log_audit` against the set or the link:
  `COST_SET_UPLOAD` (file, sheets, counts), `COST_SET_SUBMIT`, `COST_SET_RETURN` (reason),
  `COST_SET_APPLY` (applied date, accepted and rejected counts, and the list of product code,
  old price, new price, currency), `SUPPLIER_PRICE_LINK_ISSUE`, `SUPPLIER_PRICE_LINK_REVOKE`.
  One `trace_id` ties the apply event to the row updates it caused (AC-AU-03).
- **The supplier as actor** (AC-S3-10): before #1280 S0 ships, a public write sets
  `session.info["actor_link_id"]` and the listener writes `user_id = NULL`, the link id and the
  recipient name into `new_values["_actor"]` and `description`. When #1280 S0 ships, the same hook
  fills `actor_type = public_link`. One place, no per-route code.
- **Opens are counters, not audit rows** (AC-S3-11): an audit row per page view would bury the
  events that matter.
- **Where it shows:** the set's History tab (Frame B of the S2 mockup), built from the audit rows
  for the set and its lines; the product's Suppliers tab cost history (Frame C); the generic
  audit screen for everything.

## 10. Permissions and security

New slugs in `app/rbac/permission_registry.py`, seeded with a grant sweep in the migration
(`_PERMISSIONS` + `_SWEEP`, pattern `alembic/versions/522_autocount_pull_perms.py`), roles per Q5
and Q6 (owner rulings 26 Sep 2026).

**Purchasing roles**, as this plan uses the term: every role that holds
`scm.proforma_invoice.upload` today (the PI uploaders; migration 375 swept it onto every role
holding `scm.reorder.run`), excluding `integration\_%` roles, which are API-key principals and
never operators. The sweep source is that slug, so no role name is hard-coded; `admin` and
`superadmin` are granted by name as in 522.

| Slug | Grants | Seeded to |
| --- | --- | --- |
| `procurement.cost_price_changes.upload` | probe, upload, map, pick, skip, submit, discard a draft | purchasing roles + admin, superadmin (Q5 ruling: one new permission for uploading) |
| `procurement.cost_price_changes.view` | list, detail, history, source file | the same roles (an uploader must see their own sets; a verifier needs it too) |
| `procurement.cost_price_changes.verify` | decide, return, apply | purchasing roles + admin, superadmin (Q6 ruling: one Sorento person verifies) |
| `procurement.suppliers.price_link` | issue, view, revoke the supplier link | purchasing roles + admin, superadmin (Lane B; not ruled yet, Q11) |

**Verify is a Sorento staff permission** (Q6): it is granted only to staff roles, never to an
`integration\_%` role, and the public supplier routes carry no user at all, so a supplier can
never hold it. One verifier's decision is final. The four-eyes rule is not a role split: the
same purchasing roles hold both `upload` and `verify`, and the service refuses a verify action
by the set's uploader or submitter (AC-S2-03). On a team of one purchasing user, an admin
verifies. Trigger to split verify onto a lead-only role: the owner names who should not verify.

Plus enforcing the existing `procurement.product_suppliers.add|edit|delete` on the CRUD routes
(AC-S2-14), with a sweep so no role that writes links today loses it on deploy.

Security surface (security-reviewer runs on the S3 lane, and on the S1+S2 lane for the upload and
the RBAC change):

- Public, unauthenticated writes by token: 256-bit token, 30-day expiry, revocable, one active per
  supplier, rate limited, one 404 body, `no-referrer` and `noindex`, token masked in logs
  (AC-S3-01, -02, -09, -16).
- A supplier can never change a live price: the only public transitions are into `draft` lines
  and `draft` to `pending_verification` (a test asserts no public route touches
  `product_suppliers`).
- Uploads: size, row and cell caps before values are read; openpyxl only (no formulas evaluated,
  no macros; `.xlsm` refused); the retained file is stored through the storage router like every
  attachment.
- Company scope: every table is company scoped; the public route pins scope to the link's
  company; the staff upload refuses a multi-company session.
- No OTP (Q11): the supplier has no WhatsApp, and SMS to a Chinese number is not something the
  stack sends today. The compensating control is that the link can only propose.

## 11. Slices, definitions of done, out of scope, risks

Two lanes, one PR each (`CLAUDE.md` "Lane merge discipline"). S1 and S2 share a lane because an
upload that can never apply delivers nothing the owner can use, and they share one migration. S3
is its own lane: it adds a public ingest surface and can merge a week later without holding the
staff flow back. Each lane runs `/feature` Phases 1 to 3 in order: the FE against mocks first
(the three mockups are the target), then the `tester` writes the red tests from these ACs, then
one `coder` makes them green, then `reviewer`, `security-reviewer` and the browser pass in
parallel.

### Lane A: S1 + S2, "upload, verify, apply" (branch `feat/cost-price-change-sets`)

**S1: staff upload into a pending change set.** UAC AC-S1-01 to AC-S1-25, AC-AU-01, AC-AU-02
(upload and submit events), AC-AU-04.

- BE: migration (the two change-set tables, `supplier_price_links` created empty so Lane B needs
  no second migration, the partial unique index, the permission seed and sweep, the
  `supplier_price_list` alias seed); models; `supplier_price_list_reader.py`; the one-edit near
  match; service and routes under `/procurement/cost-price-changes` (probe, upload, list, detail,
  line map / pick / skip, submit, discard, source file); `product_suppliers.__audit_track__`.
- FE: sidebar entry under Purchasing (permission gated), list page, upload modal, set detail
  (stat filters, sheet tabs, grid, resolve actions, header actions, History tab), services and
  hooks per the layering rule.
- Done when: the owner's file (anonymised fixture) parses to the stated row counts; the golden
  tests for header scan, merges, bracket split and price cleaning are green; a real upload of the
  owner's file on the lane stack lands a Draft set with the near, unmatched and pick-one rows
  listed apart; submit refuses unresolved rows; the live price is unchanged; 375px and 1280px
  screenshots; pre-flight queries 1 to 5 answered in the PR body.

**S2: verification and apply.** UAC AC-S2-01 to AC-S2-19, AC-AU-02 (return and apply events),
AC-AU-03.

- BE: decide, decide-all, return, apply (conditional update, stale check under row lock, link
  creation, alias write-back), history read, notifications, the CRUD permission enforcement and
  its sweep.
- FE: decision column and apply bar on the same detail page (same tabs, same order: View and
  Edit are one layout), product Suppliers tab cost history, the currency fix on the supplier price.
- Done when: a second user applies a set and the product's Suppliers tab and the reorder screen
  show the new price; the same user who submitted cannot apply (API and disabled button); a stale
  line blocks apply; the audit screen shows the `product_suppliers` before and after with the
  apply's trace id; the kill test turns red on the four-eyes and stale-check branches.

### Lane B: S3, "the supplier page" (branch `feat/supplier-price-page`, after Lane A merges)

UAC AC-S3-01 to AC-S3-17, AC-AU-02 (link events), AC-S3-10.

- BE: link issue, current, revoke; the five public routes; rate limits; the actor stamp; response
  headers and log masking.
- FE: the Share price page modal with QR and message; the public page (tabs, table edit, upload,
  submitted state, history, expired state, language toggle).
- Done when: a second browser context at 375px edits and submits through a real link; the set is
  Pending with channel Supplier page; a verifier applies it; the supplier page shows Applied; an
  expired and a revoked link both show only the invalid-link state; a test asserts no public route
  writes `product_suppliers`; security-reviewer clean.

### Later (not in either lane)

- **S4, supplier login:** when #1280 ships users for outside parties (section 8.4).

### Out of scope, each with the trigger that would bring it in

| Not built | Trigger |
| --- | --- |
| An effective date separate from the apply date, and future-dated prices applied by a scheduler tick | Q3: the owner answers that history must show the supplier's list date, or asks for a price to change on a later date, twice |
| FX conversion, or a MYR landed cost derived from the supplier price | The owner rules that `products.cost_price` should follow supplier prices (Q1, Q2) |
| Writing `products.cost_price` | Same |
| OTP on the supplier page | A link is found forwarded outside the supplier, or the owner asks |
| Server-sent WeChat messages | Sorento connects a WeChat channel (Respond.io or WeCom) with an API |
| Creating a product from an unmatched code | Unmatched rows are routinely new products the owner wants in the master |
| More than one open set per supplier | Staff and supplier sets collide in practice (a 409 seen more than once a month) |
| An i18n framework | A third public page needs Chinese, or a third language arrives |
| Remembered skips | Section 6 trigger |
| Parsing on the `imports` queue | Section 5 trigger |

### Risks

- **The one-edit near match suggests a wrong sibling** (`-GY` vs `-GR` are both real colours).
  It never binds; the user must map it, and the suggestion shows the candidate's description.
- **Packaging variants may be real separate products for Sorento** (Q9). If the owner says so,
  `pick_one` becomes "map to a different product" and nothing else changes.
- **The reorder engine starts using verified prices immediately.** That is the intent, but a
  large price rise changes recommendations the same hour; the apply bar surfaces the largest rise
  so the verifier sees it.
- **Other writers of `unit_cost` still bypass verification** (PO flows, product import, rules).
  They are staff paths and now audited; Q13 asks whether the owner wants more.
- **CI has no data** (lesson): every test seeds its own supplier, products and links; the fixture
  file is committed, not read from a local path.

## 12. Grill questions for the owner

Round 1 asked fifteen questions (26 Sep 2026). The owner ruled on Q1 to Q10 at 23:45 MYT the same
day (verbatim on PR #1291, comment "Owner rulings on the cost price plan grill questions").
Rulings are recorded here as dated lines; the UAC is written to them. Q3, Q4 and Q8 came back as
questions and are answered in plain language on PR #1291 (comment "Answers to the owner's
questions (round 2)"), with the recommendation restated and re-asked. Q11 to Q15 are unanswered
and the UAC stays written to their round 1 recommendations.

1. **Which price is "the cost price" this updates?** The supplier's price per product,
   `product_suppliers.unit_cost` + currency, which the reorder engine reads. `products.cost_price`
   (MYR, stock valuation) is not touched.
   **Owner ruling (26 Sep 2026): "yeah correct". Applied: AC-S2-13 and the section 2 decision
   stand as written.**
2. **Currency and exchange rate.** Keep the supplier's currency, no conversion. The set's currency
   comes from the price header if it says (RMB, 元), else from the currency this supplier's prices
   already carry, else the uploader must pick; there is no house default and no FX rate.
   **Owner ruling (26 Sep 2026): "yeah correct, most is cny i believe in the file provided".
   Applied: section 5.1 step 7 and AC-S1-07; the TAIYANG fixture's expected currency is CNY.**
3. **Effective dates.** Round 1 recommended an effective date on Apply (default today, up to 90
   days back). The owner asked "why need this?". **Re-asked, round 2, with a simpler
   recommendation: no separate effective date; a price takes effect the moment it is applied and
   history shows the apply date.** The plan and UAC are written to that (section 4.4, AC-S2-08).
4. **Price basis.** The owner asked whether the supplier product table has a price field. It does
   (`product_suppliers.unit_cost` + `currency`), and it is the field this plan writes. The
   question was what the number includes (shipping, tax). **Re-asked, round 2, recommendation
   unchanged: treat it as the supplier's usual unit price and record nothing extra.**
5. **Who may upload.** **Owner ruling (26 Sep 2026): "just give it a new permission and seed it
   for purchasing roles". Applied: one new permission, `procurement.cost_price_changes.upload`,
   seeded to the purchasing roles (defined in section 10: holders of
   `scm.proforma_invoice.upload`, integration roles excluded) plus admin and superadmin, with
   `.view` seeded alongside (AC-S1-16, AC-S1-25).**
6. **Who may verify, and must it be a second person?** **Owner ruling (26 Sep 2026): "1 person
   from sorento". Applied: `procurement.cost_price_changes.verify` is a Sorento staff permission
   (never an integration role, never the supplier), seeded to the purchasing roles plus admin and
   superadmin. One verifier's decision is final (no second approval level), and the uploader or
   submitter may not verify their own set, superadmin included; a supplier set needs one
   verifier (section 7, section 10, AC-S2-03, AC-S2-19).**
7. **Partial acceptance and returns.** Per-line accept or reject, Accept all as one click, an
   optional reason per rejection, Apply writes only accepted lines; Return to submitter (reason
   required) sends the whole set back.
   **Owner ruling (26 Sep 2026): "yeap". Applied: AC-S2-01, AC-S2-02, AC-S2-09 stand.**
8. **Codes we do not know.** The owner asked what near matches are and why they exist.
   **Re-asked, round 2, with a simpler recommendation: a near match is only a suggestion, never
   applied by itself; it comes from the code matcher that already exists, and the new one-edit
   rule is dropped (section 6).** The rest of round 1 stands pending the answer: a map teaches
   the matcher only once the set is applied; no product is created here; a known product not yet
   linked becomes a new link on apply with the supplier's usual lead time.
9. **Packaging variants (`CB2500SS-BL（彩盒）` vs `（白盒）`).** One price per product per supplier;
   when two variants land on one product the user picks which price applies and the other is
   skipped with a reason.
   **Owner ruling (26 Sep 2026): "yeah correct". Applied: AC-S1-10 stands; variants are not
   separate products.**
10. **One open set per supplier.** At most one Draft or Pending set per supplier at a time, from
    any channel; a second upload is refused with a link to the open set.
    **Owner ruling (26 Sep 2026): "yeah correct". Applied: the partial unique index (section
    4.1) and AC-S1-14 stand.**
11. **Supplier identity, what they see, and link expiry.** Not yet answered. Recommend: one link
    per supplier, 30 days, revocable, no OTP; the supplier sees only its own linked products,
    its own prices and per-line outcomes, never our reasons, our MYR cost or other suppliers; a
    supplier login replaces the link when #1280 lands.
12. **Language.** Not yet answered. Recommend Chinese first with English beneath and a 中文 / EN
    switch; staff screens stay English.
13. **Other ways a supplier price changes today.** Not yet answered. Recommend enforcing the
    existing product-supplier edit permission and auditing every supplier price change; PO and
    import flows stay as they are, now traced.
14. **Delivering the link over WeChat.** Not yet answered. Recommend staff send it from their own
    WeChat; the dialog gives a link, a QR image and a ready bilingual message.
15. **Who hears about a submission.** Not yet answered. Recommend an in-app notification to
    verifiers on submit, and to the submitter on apply or return.
