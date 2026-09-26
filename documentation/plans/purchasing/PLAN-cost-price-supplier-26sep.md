# PLAN: Cost price from the supplier's price list, as dated cost lists, verified when suppliers submit (#1288)

Status: draft plan + UAC, round 3 (27 Sep 2026). Owner rulings of 26 Sep 23:45 MYT (Q1, Q2, Q5,
Q6, Q7, Q9, Q10), 27 Sep 00:10 MYT (Q3, Q4), 27 Sep 00:45 MYT (verification off for the first
rollout, reuse the existing matching engine, search on every page, mockups) and 27 Sep 00:50 MYT
(final mockups on the alignment page) are applied (section 12). Q8 and the packaging variants
question are answered on PR #1291 (issuecomment-5848210931, "Answers to the owner's questions
(round 3)"): both features are dropped. Q11 to Q15 and the new Q16 are not yet answered. Track: full (new tables and a
migration, new permissions, a new public ingest surface with uploads). Nothing built; this lane
is docs only (draft PR #1291).
UAC: `cost-price-supplier-acceptance-criteria.md` (same folder; the Journey is there and every AC
traces to a step in it).
Mockups (final, round 3; each file shows every screen at 1280 and at 375):
`mockups/cost-price-uploads.html` (list, search, upload dialog), `mockups/cost-price-review.html`
(the review page with verification off, and the same page with verification on),
`mockups/supplier-cost-lists.html` (the supplier's Prices tab with its cost lists and date
ranges, the product's Suppliers tab, the verification setting), `mockups/supplier-price-page.html`
(the supplier's own page and the Share price page dialog). The round 1 files
`cost-price-upload-review.html` and `cost-price-verification.html` are deleted: they drew near
matches, packaging picks and a mandatory second person, all of which are gone.
Alignment page: `alignment-cost-price-supplier-27sep.html` (same folder as this plan).
Classification: CORE (suppliers and the procurement base are core, `PRINCIPLES.md` "Modular
architecture"); tables in `public`, routes under the existing `procurement` module guard.
Companions: #1280 unified identity (draft PR #1285: the supplier login that replaces the token
later, and the audit actor contract this plan writes to), #1281 audit trail.

All line refs are `origin/main` at 232182ae unless stated. Paths are relative to
`sorento_crm_backend/` (BE) and `sorento_crm_frontend/` (FE) unless given in full. No database
was reachable from the planning session, so the row counts this plan needs are named as S1
pre-flight queries (section 3.8), not stated as facts.

## Contents

0. Owner words
1. Why
2. The decision in one paragraph
3. What exists today (measured)
4. Data model
5. Parsing the supplier's Excel
6. Matching codes
7. Apply, and verification when it is switched on
8. The supplier page and its link
9. Audit trail
10. Permissions and security
11. Slices, definitions of done, out of scope, risks
12. Owner rulings and open questions

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

Round 2 and 3 rulings, verbatim (PR #1291):

> Q3: "oh okay yeah we need that, like a date range, there will be end also if there needs to be,
> so it is like price list function in ERP system including Odoo, where 1 product can have
> different price list, so this is like 1 product supplier can have different cost list and the
> cost list can have start and end (optional), if both null then means always, if got start only
> then means no end, concept like that"
>
> Q4: "oh this is raw price only, no include shipping tax terms"
>
> Q8: "hmm i don't think this will happen, is this overdesign?"
>
> Lavish, 27 Sep 00:45: "i need UI mockups, why got packaging variants de" / "initially i will
> roll out to them is sorento upload so don't really need verification, this verification we need
> to do now, but will enable when the supplier comes into the picture" / "use the same matching
> engine as we use in loading plan upload and packing list / supplier invoice upload thanks" / "ok
> this is good, need to have search everywhere, correct, this applies to the pages that we do,
> must have search capability"
>
> 27 Sep 00:50: "cost price yeah need final mockup ya"

The file: `TO SORENTO-19&12&22&28&25 series price list 20260917.xlsx`, from XIAMEN TAIYANG
TECHNOLOGY. One sheet per series (19, 12, 22, 28, 25; 40, 24, 18, 58, 118 rows). Rows 1 to 5 are the
letterhead and title (merged). Row 6 is the header: 序号 (no.), 型号 (model = our product code,
sometimes with a note in full-width brackets, e.g. `CB2500SS-BL（彩盒）`), 产品配置
(configuration, Chinese, merged down across rows that share it), 价格 (price, a number, currency not
stated; CNY per the Q2 ruling). The two codes quoted in #1288 are `SRTWT1900-BL-DIY` and
`CB2500SS-BL（彩盒）`. The file itself is not in the repository or on the PR (section 5.3).

Four things bind: the Sorento user's upload comes first; nothing the supplier sends may reach the
live price without a Sorento verification; every step is traceable; every page has search.

## 1. Why

- **Supplier prices are typed by hand today, one link at a time.** The only staff write paths to
  a supplier's price are the product-supplier CRUD modal, the product Excel import, and side
  effects of PO and alias flows (section 3.2). A 258-row price list means 258 edits, and nothing
  records which price list a number came from.
- **A supplier price has no dates.** `product_suppliers` holds one number per product per
  supplier with no start or end, so a price list "from 1 Oct" or a promotion "until 31 Dec"
  cannot be recorded at all (Q3 ruling).
- **Nothing stages a price change.** Every existing writer lands on the live value immediately;
  there is no pending state, no second person, no history beyond generic audit rows (and
  `product_suppliers` is not audited at all, section 3.6). That is fine while only Sorento staff
  upload; it is not fine once the supplier can (the owner's binding rule).
- **The supplier cannot reach us on WhatsApp**, which is what the customer portal's token and OTP
  are built on (`portal_tokens` is keyed to a Respond.io contact). The precedent for a Chinese
  supplier is a plain token link, already shipped read-only for supplier requests (section 3.5).
- **The reorder engine prices every recommendation from this value** (section 3.2), so a wrong
  price reaches purchasing decisions directly.

## 2. The decision in one paragraph

**Each product-supplier link gets cost lists, the same shape as an ERP price list (Q3 ruling):
any number of rows, each a raw unit price (Q4 ruling) in the supplier's currency with an optional
start date and an optional end date.** Both empty means always; a start with no end means from
that day on. The price in force today is the matching row with the latest start; the existing
`product_suppliers.unit_cost` + `currency` keep holding that price-in-force, refreshed on every
apply and by a daily tick, so the reorder engine and every other reader keep working unchanged.
A staff upload lands first in a **change set** (one header per upload, one line per parsed row)
so the user can review what changed before anything is written. **Verification is built now and
switched off** (owner ruling 27 Sep 00:45): with the setting off, the uploader reviews and clicks
Apply; with it on, a different Sorento person verifies first. **A supplier's submission always
waits for a Sorento verifier, whatever the setting** (the owner's words in #1288). Codes are
matched by the engine the proforma invoice, packing list and loading plan uploads already share;
whatever it cannot match is mapped by hand from a product dropdown. The supplier reaches its own
page through a token link (`supplier_price_links`) sent over WeChat. `products.cost_price` (MYR,
used for stock valuation) is not touched (Q1).

Why a change set table and not a stateless preview: the upload is reviewed on its own page with
search, sheet tabs and manual maps that survive a page reload, a supplier set waits days for a
verifier, and the applied lines are the record of which file set which price. Those are three
concrete needs a stateless preview does not meet, which is the evidence `PRINCIPLES.md` asks for
before a new table.

## 3. What exists today (measured)

### 3.1 Where a cost lives

- **`products.cost_price`** `Numeric(12,2)`, nullable (`app/models/product.py:227`), sharing
  `products.currency` `String(3)` default `MYR` (`:229`) with `list_price` (`:226`) and
  `invoice_price` (`:228`). `Product` is audited (`__audit_track__`, `:187-188`); the activity
  timeline labels it "Cost price" (`app/services/activity_service.py:141`).
- **`product_suppliers`** (`app/models/procurement.py:96-123`): `unit_cost` `Numeric(12,2)`
  (`:110`), `currency` `String(3)` (`:111`), `moq`, `order_multiple`, `is_primary_supplier`,
  `standard_lead_time_days` **NOT NULL with no default** (`:106`), `created_at` only (no
  `updated_at`), unique on (product_id, supplier_id) (`:122`), company scoped. **Not audited. No
  dates.**
- **No cost history table.** Price advice is derived from PO lines by
  `app/services/scm/price_history_service.py:1-100`, which compares the last paid price against the
  "standing cost" `product_suppliers.unit_cost` (`:79-81`).
- Transactional `unit_cost` columns (PO lines, shipment lines, SPO allocations, picking lines,
  reorder recommendations, plan row decisions) are snapshots and are out of scope.

### 3.2 Who reads and writes it

- **Reorder engine (reads):** `load_supplier_candidates` reads `ps.unit_cost, ps.currency`
  (`app/services/scm/reorder_engine.py:837-845`); `last_purchase_costs` (`:783-822`) lets the
  last order win over the typed price. Also `decision_service.py:273,1460`,
  `reorder_level_service.py:473`, `summary_order_service.py:2313-2449`. Several are raw SQL, which
  is why this plan keeps `unit_cost` as the price-in-force rather than teaching every reader the
  date rule (section 4.2).
- **Writers of `product_suppliers.unit_cost`:** `procurement_service.py:6972`,
  `product_service.py:1021,1663` (product Excel import), `rules/product_rules.py:397`,
  `scm/supplier_code_alias_service.py:251`, `scm/product_supplier_service.py:75,84` (raw SQL),
  `scripts/backfill_product_supplier_from_last_po.py:321`, and the CRUD routes
  `app/api/v1/procurement/product_suppliers.py:61-95`, which need **only a login** although
  `procurement.product_suppliers.{view,add,edit,delete}` exist (`app/rbac/permission_registry.py:226`).
- **`products.cost_price` writers and readers:** the ESB masters push writes it only when present
  (`master_ingest_service.py:589-590`); the **AutoCount pull does not** (`autocount_pull_service.py:425-473`
  maps `list_price` only). Stock valuation reads it in MYR (`scm/dashboard_service.py:19,369,434`,
  `scm/analytics_service.py:414-418`). `ProductDetail.tsx:384-385` formats cost as MYR regardless
  of `product.currency`.
- **Kept out of cost on purpose:** price tags and the dealer kit (`dealer_kit/product_facts.py:14`),
  product dropdowns (`products_select.py:39`). The chatbot's last purchase cost comes from PO lines
  behind the per-contact reveal key `purchase_orders.cost`
  (`contact_field_reveal_service.py:45`); it does not read either column.

### 3.3 The supplier

- `suppliers` (`procurement.py:39-93`, audited): `supplier_code` (unique per company, arrives from
  AutoCount as the creditor code), `supplier_name`, one `contact_name` / `email` / `phone_number`,
  `country_id`, `is_active`. **No currency column and no Chinese name column.**
- Supplier currency is inferred: `currency_resolution.supplier_price_list_currency` returns the
  single distinct `product_suppliers.currency` for the supplier, else None
  (`app/services/scm/currency_resolution.py:128-150`); no house default (`:1-13`).

### 3.4 Parsing precedents

- `app/services/scm/outstanding_reader.py`: `sheet_rows` (`:227-238`), `sheet_merges`
  (`:245-265`, maps covered cells to their anchor; needs a non read-only workbook),
  `every_sheet_rows` (`:300`), `.xls` via xlrd (`:211`).
- `app/services/scm/supplier_inventory_reader.py`: a Chinese supplier file keyed on 型号. Headers
  resolve through `import_field_alias` (`:1-17,26`); merged cells fill down for body fields only
  (`_MERGE_FILL_FIELDS`, `:46-54`); `model_no` kept verbatim (`:68-71`); `letterhead` keeps the text
  above the header (`:81-84`).
- `import_field_alias` (`app/models/import_alias.py:26-60`); `normalize_header` applies NFKC
  (`app/services/import_alias_service.py:37-44`).
- Currency from a price header: `currency_resolution.price_column_currency`, tokens rmb, 元, ¥ to
  CNY (`currency_resolution.py:24-45`).
- The 25 MB cap and retained upload are `scm/upload_intake.py:24,55`; the single-company guard is
  `api/v1/scm/outstanding_import.py:57-79`.

### 3.5 Token access precedents

- **Supplier request link (read-only, Chinese first):** `SupplierNotice.public_token` /
  `public_token_expires_at` (`app/models/supplier_notice.py:126-127`), minted with
  `secrets.token_urlsafe(32)` and a 30-day TTL (`supplier_notice_service.py:1161-1162,1228-1233`),
  one 404 body for unknown, expired or retired (`:1273-1307`). Route
  `app/api/v1/public/supplier_request.py:28-51`; page
  `app/(public)/c/[company]/supplier-request/[token]/page.tsx` with hard-coded bilingual labels
  (`:6-8`).
- **Outside party edits rows, then internal review:** `OnboardingRequest`
  (`app/models/onboarding.py:132-192`), public `PUT /rows` and `POST /submit`
  (`app/api/v1/public/onboarding.py`), no OTP by design (`:10-14`).
- **Rate limiting:** `app/services/rate_limit.py:41` `hit(bucket, ident, limit, window_seconds)`.
- **QR:** `qrcode.react` (`package.json:66`), used as `QRCodeSVG` in
  `components/contacts/PortalLinkDialog.tsx:4`.

### 3.6 Audit today

- `audit_logs` (`app/models/audit.py:9-46`); the before-flush listener
  (`app/services/audit_service.py:323-429`) records CREATE/UPDATE/DELETE for `__audit_track__`
  models; a contact actor comes from `session.info["actor_contact_id"]` (`:403-410`); manual
  writers `log_audit` (`:109`) and `log_import_audit` (`:156`).
- #1280's plan section 8 adds `actor_type` (including `public_link`) and friends to every row.
  This plan writes to that contract and does not wait for it (section 9).

### 3.7 The matching engine the uploads already share (owner ruling 27 Sep 00:45)

The proforma invoice, packing list and loading plan uploads all bind supplier codes through one
two-step engine, and this plan calls the same one:

1. **Exact code, company scoped:** `proforma_invoice_service._products_by_code`
   (`app/services/scm/proforma_invoice_service.py:227-247`).
2. **The supplier code ladder for what step 1 missed:** `_with_supplier_codes`
   (`proforma_invoice_service.py:250-300`), which calls
   `supplier_code_matcher.resolve(db, supplier_id, codes, *, remember, actor)`
   (`app/services/scm/supplier_code_matcher.py:196-215`). The ladder (`:1-52`): an alias already
   recorded for this supplier (including a dismissal), exact, separator-normalised, token-set
   reorder, trap size dropped where the base product's description confirms it, then the same
   rungs against product sets. An ambiguous rung binds nothing. Measured on the JINBAICHUAN stock
   list, 79 codes missed an exact match for exactly these reasons (`:3-11`).

Callers today: the PI apply (`proforma_invoice_service.py:933-941`), the packing list written
onto a PI (`proforma_invoice_packing_service.py:122-126`), and the loading plan's supplier stock
upload (`api/v1/scm/fulfilment.py:180-200` into `supplier_inventory_service._products_by_code`,
`supplier_inventory_service.py:82-120`, which previews with `remember=False` at `:147`). The
ladder's `_norm` strips `[-\s]+` and lowercases (`supplier_code_matcher.py:105-107`) and `_tokens`
splits on the same (`:110-111`), with **no NFKC and no bracket handling**, so
`CB2500SS-BL（彩盒）` would not bind; the reader cleans the cell first (section 5.1 step 5).

### 3.8 S1 pre-flight queries (run on the prod copy before Phase 2)

1. Links per currency: `SELECT currency, count(*) FROM product_suppliers GROUP BY 1`.
2. TAIYANG's links: count, distinct currency, how many carry a `unit_cost`, most common
   `standard_lead_time_days`.
3. How many of the owner's file's codes bind exactly, how many through the ladder (and on which
   rung), and how many stay unmatched: run the S1 reader and the engine above against the file
   with `remember=False`. This is the number that settles whether manual mapping is rare (Q8).
   Also: does `SRTWT1900-BL-DIY` exist as a product, or only `SRTWT1900-DIY` (section 12, Q8)?
4. How many of the file's cleaned codes appear more than once in one upload (the duplicate-code
   check, section 6).
5. Which roles today can reach `/procurement/product-suppliers` writes (for the AC-S2-14 sweep).

## 4. Data model

Designed backwards from the Journey (UAC). One table for the cost lists, two for the upload's
change set, one for the supplier link, one boolean on `system_settings`, and `product_suppliers`
gains `__audit_track__`. One migration, chained on the head at Phase 2 time via
`./scripts/alembic-reparent.sh`; revision id under 32 characters (`cpc1_supplier_cost_lists`).

### 4.1 `product_supplier_costs`, the cost lists (CompanyScopedMixin, `__audit_track__`)

| Column | Type | Why (Journey step) |
| --- | --- | --- |
| `id` | UUID PK | |
| `product_supplier_id` | FK `product_suppliers.id` ON DELETE CASCADE, NOT NULL | a cost list belongs to one product-supplier link (Q3 ruling) |
| `unit_cost` | numeric(12,2) NOT NULL, >= 0 | the raw unit price, nothing about shipping, tax or terms (Q4 ruling) |
| `currency` | char(3) NOT NULL | the supplier's currency, no conversion (Q2 ruling) |
| `start_date` | date, nullable | null = from the beginning (Q3 ruling) |
| `end_date` | date, nullable | null = no end; check `end_date >= start_date` when both are set |
| `source_change_line_id` | FK `cost_price_change_lines.id` ON DELETE SET NULL, nullable | which upload line made it (J8, J14) |
| `created_by_user_id` | FK users, nullable | null when it came from a supplier set |
| `created_at`, `updated_at` | naive UTC | |

Index on `(product_supplier_id, start_date)`.

**The price in force on a day D** is, among the link's rows with (`start_date` null or <= D) and
(`end_date` null or >= D), the one with the latest `start_date` (null counts as earliest); a tie
goes to the latest `created_at`. So an "always" row is the base price and a dated row overrides
it for its range, as a dated rule does in an Odoo price list. One function,
`price_in_force(link, day)`, holds that rule; nothing else re-spells it.

### 4.2 `product_suppliers.unit_cost` stays the price in force

`unit_cost` and `currency` keep their meaning for every reader in section 3.2: "the price today".
For a link with at least one cost list row they are written only from `price_in_force(link,
today)`: in the same transaction as an apply or a cost list edit, and by a daily tick at 00:05
Malaysia time on the existing scheduler (a start date arriving, an end date passing). When no row
is in force (every row has ended or not started) `unit_cost` is set to null, which the reorder
engine already handles as "no typed price". A link with no cost list rows behaves exactly as
today. No reader changes.

Why not make readers compute the date rule: there are eight readers, several in raw SQL (section
3.2); one writer that keeps a column current is less code than eight joins that must agree.
Trigger to revisit: a reader needs a price for a day other than today (for example pricing a
future PO), twice.

### 4.3 `cost_price_change_sets` (CompanyScopedMixin, `__audit_track__`)

| Column | Type | Why (Journey step) |
| --- | --- | --- |
| `id` | UUID PK | |
| `code` | text, unique per company, `CPC-0001` from a sequence | J4, J12: the name people say and search by |
| `supplier_id` | FK `suppliers.id` ON DELETE RESTRICT, NOT NULL | J2 |
| `channel` | text: `staff_upload`, `supplier_page`, `supplier_upload` | J12; check constraint |
| `status` | text: `draft`, `pending_verification`, `applied` | J5, J8; check constraint. Return sends a pending set back to `draft` with `returned_reason`; Discard is a hard delete of a draft |
| `currency` | char(3) NOT NULL | J2 (AC-S1-07) |
| `start_date`, `end_date` | date, nullable | J2: the validity every cost list row made by this set gets (Q3 ruling); both empty means always |
| `source_attachment_id` | FK `attachments.id`, nullable | J14: the retained file (null for a table-only supplier set) |
| `source_meta` | JSONB | file name, sheet names, header row per sheet, merged-cell fills, letterhead text |
| `created_by_user_id` | FK users, nullable | J1 (null for a supplier set) |
| `submitted_by_user_id`, `submitted_at` | | J5, only when verification applies |
| `submitted_via_link_id` | FK `supplier_price_links.id`, nullable | J12 |
| `returned_reason`, `returned_by_user_id`, `returned_at` | | J9 |
| `applied_by_user_id`, `applied_at`, `verified` | FK, timestamp, bool | J8: `verified` records whether a second person decided it, so history never has to guess what the setting was that day |
| `created_at`, `updated_at` | naive UTC | |

Partial unique index: one row per (company_id, supplier_id) WHERE status IN ('draft',
'pending_verification') (AC-S1-14, Q10).

### 4.4 `cost_price_change_lines` (`__audit_track__`)

| Column | Type | Why |
| --- | --- | --- |
| `id`, `change_set_id` (FK, ON DELETE CASCADE) | | |
| `sheet`, `row_no`, `line_no` (序号) | text, int, text | J4: where in the file, searchable |
| `supplier_code_raw`, `supplier_code`, `code_note` | text | AC-S1-04: the cell as written, the cleaned code, the bracket text (shown, never matched) |
| `configuration` | text | J4 (产品配置), searchable |
| `flags` | text[]: `configuration_from_merge`, `price_from_merge`, `duplicate_code` | AC-S1-03, AC-S1-10 |
| `match_outcome` | text: `exact`, `ladder`, `alias`, `manual`, `unmatched` | AC-S1-08 |
| `match_rung` | text, nullable | the ladder rung that bound it, shown as a hint |
| `product_id` | FK products, nullable | bound or mapped product |
| `mapped_by_user_id` | FK users, nullable | AC-S1-12 |
| `current_unit_cost`, `current_currency` | numeric(12,2), char(3), nullable | AC-S1-09: price in force at parse, re-checked at apply (AC-S2-06) |
| `new_unit_cost` | numeric(12,2), nullable | |
| `line_state` | text: `changed`, `unchanged`, `new_link`, `needs_attention`, `skipped` | J4 tabs and filters |
| `skip_reason` | text | |
| `new_link_lead_time_days` | int, nullable | AC-S2-05 |
| `decision` | text: `accepted`, `rejected`, null | J7, only when verification applies |
| `decision_reason`, `decided_by_user_id`, `decided_at` | | J7 |

Change percent is computed on read, never stored. The round 2 columns `packaging_note`,
`candidate_product_id` and the `near`, `ambiguous` and `pick_one` values are gone (Q8 and Q9,
round 3).

### 4.5 `supplier_price_links` (CompanyScopedMixin, `__audit_track__`)

`id`, `supplier_id`, `token` (text, unique; `secrets.token_urlsafe(32)`), `recipient_name`,
`expires_at`, `revoked_at`, `issued_by_user_id`, `revoked_by_user_id`, `last_opened_at`,
`open_count`, `created_at`. One active link per supplier, enforced in the service (revoke the old
one in the same transaction as the new one, AC-S3-01). Created empty in Lane A's migration so Lane
B needs none.

### 4.6 `system_settings.cost_price_verification_enabled`

Boolean, NOT NULL, server default `false` (owner ruling 27 Sep 00:45: off for the first rollout).
Added to the model (`app/models/user.py:291`, beside `deferred_delete_seconds` at `:392`), to
**both** manual dict builders that serialise system settings (the lesson on new columns), and to
the System Settings screen as one switch. Changing it needs the existing system settings edit
permission and is audited like every other setting.

### 4.7 Nothing else

- No price basis column (Q4 ruling: the price is the raw unit price).
- No supplier currency column (Q2 ruling). Trigger: a supplier with no links yet uploads a list
  in a currency the header does not state, more than once.
- No supplier Chinese name column (section 5.4 names the trigger).
- No packaging variant column or pick step (Q9 withdrawn, section 12).

## 5. Parsing the supplier's Excel

One reader, `app/services/procurement/supplier_price_list_reader.py`, used by the staff upload and
the supplier upload alike. Synchronous in the request: 258 rows parse in well under a second.
Trigger to move it onto the `imports` queue: a real file over 2,000 rows or a parse over 5 s.

### 5.1 Steps

1. Open with openpyxl (not read-only, because `sheet_merges` needs `merged_cells`); `.xls` through
   the existing xlrd path. Reject over 25 MB, over 5,000 total rows, or a sheet over 20,000 cells
   before reading values (AC-S1-15).
2. For each sheet, scan rows 1 to 20 for the header: the first row where at least two of the four
   fields resolve through `import_field_alias` with a new doc_type `supplier_price_list`
   (seeded aliases: 型号 / 型號 / model / item / code to `item_code`; 价格 / 單價 / 单价 / price /
   unit price to `unit_price`; 产品配置 / 配置 / description / specification to `description`;
   序号 / no / s/n to `line_no`). A sheet with no header is recorded in `source_meta` and skipped
   (AC-S1-02).
3. Text above the header is kept as `letterhead` (for the supplier match, 5.4).
4. Body rows: stop at the first 5 consecutive empty rows. Merged cells fill down for
   `description` (always) and `unit_price` (flagged `price_from_merge`, AC-S1-03); `item_code` is
   never filled.
5. Code cleaning (AC-S1-04): NFKC-fold (turns `（彩盒）` into `(彩盒)`), trim, collapse inner
   whitespace, then split one trailing bracket group into `supplier_code` and `code_note`. The
   verbatim cell is `supplier_code_raw`. This is cleaning so the shared engine sees a code, not
   a variant concept: the note is shown under the code and never used to match (section 12, Q9).
6. Price cleaning (AC-S1-05): numbers as numbers; strings stripped of `¥ ￥ 元 RMB CNY ,` and
   spaces, then `Decimal`; anything else (面议, blank, negative) leaves the price null and the
   line `needs_attention`.
7. Currency (AC-S1-07): the price header's token via `price_column_currency` if present, else
   `supplier_price_list_currency(supplier)`, else required in the dialog. For TAIYANG this is CNY
   (Q2 ruling).
8. Validity (J2, Q3 ruling): the dialog's optional Valid from and Valid to. Nothing is read from
   the file name; the list date in `...20260917.xlsx` is shown beside the fields as the file's
   own date so the user can type it if they want it.

### 5.2 The parse probe

`POST /procurement/cost-price-changes/probe` (multipart) parses without storing and returns the
suggested supplier, currency, sheet list and counts, so the upload dialog can pre-fill (J2).
`POST /procurement/cost-price-changes` (same file plus supplier, currency and the optional
dates) parses again, matches, and stores the Draft set in one transaction.

### 5.3 Fixture

The owner's file, with prices and the supplier name replaced by synthetic values and every
structural quirk kept, is committed as `tests/fixtures/cost_price/taiyang_price_list.xlsx` and is
the golden input for AC-S1-01 to AC-S1-05. **Prerequisite:** the file is not in the repository
and was not attached to #1288 or #1291; the owner attaches it (or hands it to the lane) before
Phase 2. Phase 1 needs only the mockups.

### 5.4 Supplier from the letterhead

Match the letterhead text (NFKC, uppercased, punctuation stripped) against active suppliers'
`supplier_code` and `supplier_name`. Exactly one hit pre-selects; otherwise the supplier field is
required (AC-S1-06). Trigger for a Chinese-name alias per supplier: a supplier whose letterhead is
Chinese only has to be picked by hand on three uploads.

## 6. Matching codes

Owner ruling 27 Sep 00:45: "use the same matching engine as we use in loading plan upload and
packing list / supplier invoice upload". Owner question 27 Sep 00:10: near matches may be
over-design. Both are applied by dropping the near-match layer entirely.

- **Bind with the shared engine (section 3.7), unchanged:** `_products_by_code` then
  `_with_supplier_codes` on the cleaned `supplier_code`, with `remember=False` at upload (the
  loading plan preview's rule, `supplier_inventory_service.py:147`). Outcomes: `exact`, `alias`
  (a recorded alias for this supplier), `ladder` (rungs 2 to 4 bound it; the rung is shown as a
  hint, as the PI screen does). Product-set binds are refused on this screen (a set has no
  supplier price of its own) and become `unmatched`.
- **Everything else is `unmatched`**, including what the ladder found ambiguous. The row shows a
  product dropdown (the system single-select, searching by code and description) to map it, or
  Skip. There are no suggestions and no "did you mean". The round 1 one-edit rung and the round 2
  near-match suggestion are both withdrawn.
- **At apply**, the engine is asked again with `remember=True` for the ladder-bound codes (so it
  writes its own `auto` aliases exactly as the PI apply does), and each manual map writes an
  alias with `source=manual`, `matched_by='cost_price_set'`. Nothing is remembered from a set
  that is discarded or never applied (AC-S1-12).
- A bound product not yet linked to this supplier is `new_link` (AC-S1-09).
- **Duplicate code** (AC-S1-10): two lines in one set that bind to the same product are both
  flagged `duplicate_code` and the user skips one. This is the generic check any upload needs
  (one link gets one new price per upload), not a packaging feature; pre-flight query 4 says
  whether the owner's file triggers it at all.
- A skipped unmatched code writes nothing. Trigger for "remember this skip" (a dismissal alias,
  which the ladder already honours): the same code is skipped on three consecutive sets for one
  supplier.

## 7. Apply, and verification when it is switched on

### 7.1 Verification off (the first rollout)

With `cost_price_verification_enabled = false` (the default, owner ruling 27 Sep 00:45) a staff
upload is reviewed and applied by the uploader:

- The review page has no Submit step and no Decision column. The bar reads "Apply N changes",
  where N counts changed and new-link lines not skipped.
- Apply needs `procurement.cost_price_changes.upload`, refuses while any `unmatched`,
  `needs_attention` or `duplicate_code` line is unresolved (422), and writes the set `applied`
  with `verified = false`.

### 7.2 Verification on (when suppliers submit)

With the setting on, a staff upload goes Draft, Submit for verification, Pending; a different
Sorento person holding `verify` decides each line and applies (Q6 ruling: one person from
Sorento; the uploader or submitter cannot verify their own set, superadmin included). A supplier
set is always Pending on submit and always needs one verifier, **whatever the setting** (the
owner's rule in #1288). Turning the setting on or off never changes a set already Pending: a
Pending set is finished by a verifier.

- **Decide:** `PATCH .../lines/{id}` with `{decision, reason}`; `POST .../decide-all`.
- **Return** `POST .../return` with a required reason: back to `draft`, decisions cleared.

### 7.3 Apply (both paths)

`POST .../apply`:

1. `UPDATE cost_price_change_sets SET status='applied', ... WHERE id=:id AND status=:expected`
   (`draft` when verification is off for a staff set, `pending_verification` otherwise); zero
   rows means 409.
2. Refuse with 422 if any line is unresolved, or (verification path) any changed or new-link line
   is undecided.
3. For every line to write, lock the `product_suppliers` row (`SELECT ... FOR UPDATE`) and compare
   its price in force to the line's captured values; a mismatch rolls back with 409 listing the
   stale lines (AC-S2-06).
4. Insert one `product_supplier_costs` row per line (the set's currency, start and end dates;
   `source_change_line_id` set), create missing links with the lead time rule (AC-S2-05), write
   aliases (section 6), then recompute `unit_cost` and `currency` from `price_in_force(link,
   today)` through the ORM so the audit listener records old and new.
5. One `COST_SET_APPLY` audit row with the full change list (section 9).
6. Post-commit, best effort: the notification to the submitter (verification path only).

Apply adds rows and never deletes one, so it is a single click with no dialog and no countdown;
the button names the count.

### 7.4 Cost lists edited by hand

The supplier's Prices tab and the product's Suppliers tab list each link's cost lists (section
8.5). Staff holding `procurement.product_suppliers.edit` can add a row, change its price or dates,
or delete it (the 10 s deferred action, no dialog). Each write recomputes the price in force in
the same transaction and is audited. This is the ERP price list experience the Q3 ruling asks
for; it is not routed through a change set because only Sorento staff can reach it.

### 7.5 Other write paths (Q13)

The CRUD routes get their existing permission slugs enforced (AC-S2-14). The PO, alias, rules and
import writers that set `unit_cost` directly stay as they are for links with no cost lists; for
a link that has cost lists, the next daily tick puts the price in force back. That is a risk
(section 11) and an open question (Q16).

## 8. The supplier page and its link

### 8.1 Issuing (staff)

Supplier record gear menu, Share price page (permission `procurement.suppliers.price_link`):
`POST /procurement/suppliers/{id}/price-link` issues (and revokes the previous), `GET` returns the
current one with open stats, `DELETE` revokes through the 5 s deferred action. The dialog shows
the URL, a `QRCodeSVG`, Copy link, Save QR image and Copy message:

```
Sorento 价格维护 / Sorento price page
请在此更新贵司的产品价格:
<url>
(<expiry date> 前有效 / valid until <expiry date>)
```

Staff paste it into their own WeChat chat with the supplier (Q14). No server-side WeChat.

### 8.2 Public routes (`app/api/v1/public/supplier_prices.py`)

| Route | Does | AC |
| --- | --- | --- |
| `GET /supplier-prices/{token}` | supplier display name, currency, linked products with their cost lists (price, start, end), the open set if any | AC-S3-03 |
| `PUT /supplier-prices/{token}/lines` | upsert proposed prices and the proposal's validity into the open Draft set | AC-S3-04 |
| `POST /supplier-prices/{token}/upload` | parse with the S1 reader into the Draft set | AC-S3-05 |
| `POST /supplier-prices/{token}/submit` | Draft to Pending, always (section 7.2) | AC-S3-06, AC-S3-07 |
| `GET /supplier-prices/{token}/history` | own sets and per-line outcomes, no reasons | AC-S3-08 |

Every route calls `rate_limit.hit` on the token and the client IP (AC-S3-09), resolves the link
with company scope pinned to the link's company, and returns one 404 body on any failure. An
explicit response model is asserted as a whole key set in a test.

### 8.3 Page (`app/(public)/c/[company]/supplier-prices/[token]/page.tsx`)

Mobile first (375px design width, 1280px must not clip). Chinese first with English beneath,
hard-coded in a `labels.ts` beside the page; a 中文 / EN toggle (Q12). Tabs 价格表 Prices,
上传Excel Upload, 记录 History. **Search box at the top of the Prices and History tabs** (model code
and configuration; set code) (owner ruling 27 Sep 00:45). Each product row shows its cost lists
with their date ranges and which one is in force; a new price is proposed with an optional
生效日期 Valid from and 截止日期 Valid to for the whole submission. A pending set makes the table
read-only; an expired link shows only the invalid-link state.

### 8.4 Later: the supplier login (#1280)

When #1280 lands a user for an outside party, a supplier user replaces the token: the same routes
move behind the session and the audit rows become `actor_type = user`.

### 8.5 Staff screens and their search (owner ruling 27 Sep 00:45: every page has search)

| Screen | Search covers | Other filters (all system dropdowns) |
| --- | --- | --- |
| Purchasing > Cost price uploads (list) | set code, supplier, file name | Status (multi-select), Supplier (single-select, clearable) |
| Upload review page | supplier code, configuration, matched product code, sheet | stat cards as filters; Sheet tabs |
| Supplier record > Prices tab (cost lists) | product code, description, supplier code | Status (multi-select: In force, Scheduled, Ended, Always) |
| Product record > Suppliers tab | supplier name, price list set code | none (a product has few suppliers) |
| Supplier's own page (public) | model code, configuration; set code on History | none |
| Share price page dialog | not a list; no search | none |

Every single-select on these screens is `SearchableSelect` and every multi-select is
`SearchableMultiSelect` (`components/common/SearchableSelect.tsx:142`,
`components/common/SearchableMultiSelect.tsx:86`), clearable where optional. The public page uses
the same two components. List search uses the existing `ListSearchInput`
(`components/common/ListSearchInput.tsx`) and `buildDataGridParams`.

## 9. Audit trail

Written to #1281's standard and #1280's actor contract (PR #1285, section 8):

- **Row changes:** `product_supplier_costs`, `cost_price_change_sets`, `cost_price_change_lines`,
  `supplier_price_links` and `product_suppliers` are `__audit_track__` (AC-AU-01).
  `product_suppliers` gaining it matters most: today a price can change with no trace at all.
- **Named events** (AC-AU-02): `COST_SET_UPLOAD`, `COST_SET_SUBMIT`, `COST_SET_RETURN`,
  `COST_SET_APPLY` (verified yes or no, counts, validity dates, and the list of product code, old
  price in force, new price, currency), `SUPPLIER_COST_LIST_EDIT` (hand edits, section 7.4),
  `SUPPLIER_COST_TICK` (one row per daily tick that changed any price in force, listing them),
  `SUPPLIER_PRICE_LINK_ISSUE`, `SUPPLIER_PRICE_LINK_REVOKE`, `COST_VERIFICATION_SETTING` (on or
  off, by whom). One `trace_id` ties an apply to the row updates it caused (AC-AU-03).
- **The supplier as actor** (AC-S3-10): a public write sets `session.info["actor_link_id"]`; the
  listener writes `user_id = NULL`, the link id and the recipient name. When #1280 S0 ships, the
  same hook fills `actor_type = public_link`.
- **Opens are counters, not audit rows** (AC-S3-11).

## 10. Permissions and security

New slugs in `app/rbac/permission_registry.py`, seeded with a grant sweep in the migration
(pattern `alembic/versions/522_autocount_pull_perms.py`).

**Purchasing roles**: every role that holds `scm.proforma_invoice.upload` today, excluding
`integration\_%` roles; `admin` and `superadmin` by name.

| Slug | Grants | Seeded to |
| --- | --- | --- |
| `procurement.cost_price_changes.upload` | probe, upload, map, skip, discard a draft; **apply own set while verification is off**; submit while it is on | purchasing roles + admin, superadmin (Q5 ruling) |
| `procurement.cost_price_changes.view` | list, detail, history, source file | the same roles |
| `procurement.cost_price_changes.verify` | decide, return, apply a Pending set | purchasing roles + admin, superadmin (Q6 ruling); unused until the setting is on or a supplier submits |
| `procurement.suppliers.price_link` | issue, view, revoke the supplier link | purchasing roles + admin, superadmin (Lane B; Q11 not ruled) |

Verify is a Sorento staff permission: never an `integration\_%` role, never reachable from a
public route. The same person may not verify a set they uploaded or submitted (AC-S2-03). Plus
the existing `procurement.product_suppliers.add|edit|delete` enforced on the CRUD routes and the
cost list edits (AC-S2-14), with a sweep so no role that writes links today loses it.

Security surface (security-reviewer runs on both lanes: Lane A has uploads and an RBAC change,
Lane B a public ingest surface):

- The verification switch is the control that lets staff skip a second person, so it is a
  system setting behind the existing settings permission, audited, and it **never** applies to a
  supplier set (a test asserts a supplier submit is Pending with the setting off).
- Public, unauthenticated writes by token: 256-bit token, 30-day expiry, revocable, one active
  per supplier, rate limited, one 404 body, `no-referrer` and `noindex`, token masked in logs.
- A supplier can never change a live price or a cost list: a test asserts no public route writes
  `product_suppliers` or `product_supplier_costs`.
- Uploads: size, row and cell caps before values are read; openpyxl only; `.xlsm` refused; the
  retained file goes through the storage router.
- Company scope: every table is company scoped; the public route pins scope to the link's
  company; the staff upload refuses a multi-company session.

## 11. Slices, definitions of done, out of scope, risks

Two lanes, one PR each (`CLAUDE.md` "Lane merge discipline"). Each lane runs `/feature` Phases 1
to 3 in order: the FE against mocks first (the round 3 mockups are the target), then the `tester`
writes the red tests from the ACs, then one `coder` makes them green, then `reviewer`,
`security-reviewer` and the browser pass in parallel.

### Lane A: S1 + S2, "upload, cost lists, apply; verification built but off" (branch `feat/cost-price-change-sets`)

**S1: staff upload, review, apply into dated cost lists (verification off).** UAC AC-S1-01 to
AC-S1-27, AC-CL-01 to AC-CL-08, AC-SR-01 to AC-SR-03, AC-SR-05, AC-AU-01, AC-AU-02,
AC-AU-04. **Owner hand test: yes** (upload the
TAIYANG file, apply, see the cost lists on the supplier's Prices tab).

- BE: migration (cost lists, change sets and lines, `supplier_price_links` empty, the setting,
  permissions and sweep, the `supplier_price_list` alias seed); models; the reader; the shared
  engine call; `price_in_force` and the daily tick; routes under `/procurement/cost-price-changes`
  (probe, upload, list, detail, map, skip, discard, apply, source file) and the cost list routes;
  `product_suppliers.__audit_track__`.
- FE: sidebar entry Purchasing > Cost price uploads (permission gated), list page with search,
  upload dialog, review page (stat filters, search, sheet tabs, grid, map dropdown, apply bar,
  History tab), supplier Prices tab and product Suppliers tab cost lists, all with search.
- Done when: the anonymised fixture parses to the stated row counts; a real upload of the owner's
  file on the lane stack lands a Draft set, unmatched rows are mapped from the dropdown, Apply
  writes one cost list row per line with the chosen dates and the reorder screen shows the price
  in force; a dated row whose start is tomorrow shows as Scheduled and becomes in force after the
  tick (tested by running the tick with a fixed day); 375px and 1280px screenshots; pre-flight
  queries 1 to 5 answered in the PR body.

**S2: verification, built and switched off.** UAC AC-S2-01 to AC-S2-20, AC-AU-02, AC-AU-03.
**Owner hand test: yes, once**, by switching the setting on for a test set.

- BE: the setting; submit, decide, decide-all, return, the four-eyes rule, apply from Pending,
  notifications, the CRUD permission enforcement and its sweep.
- FE: the System Settings switch; with it on, the same review page gains Submit, the Decision
  column and Return (View and Edit are one layout); the product Suppliers tab cost lists.
- Done when: with the setting off, the uploader applies directly; with it on, the same user
  cannot apply (API and disabled button), a second user applies; a supplier-channel set is
  Pending with the setting off (test); a stale line blocks apply; the audit screen shows the
  `product_suppliers` before and after with the apply's trace id.

### Lane B: S3, "the supplier page" (branch `feat/supplier-price-page`, after Lane A merges)

UAC AC-S3-01 to AC-S3-18, AC-SR-04, AC-AU-02 (link events), AC-S3-10. **Owner hand test: yes** (open the
link on a phone at 375).

- BE: link issue, current, revoke; the five public routes; rate limits; the actor stamp; headers
  and log masking.
- FE: the Share price page dialog with QR and message; the public page (search, cost lists with
  dates, table edit with validity, upload, submitted state, history, expired state, language
  toggle).
- Done when: a second browser context at 375px edits and submits through a real link; the set is
  Pending with channel Supplier page even with the setting off; a verifier applies it; the
  supplier page shows Applied and the new cost list row with its dates; an expired and a revoked
  link both show only the invalid-link state; security-reviewer clean.

### Later (not in either lane)

- **S4, supplier login:** when #1280 ships users for outside parties (section 8.4).

### Out of scope, each with the trigger that would bring it in

| Not built | Trigger |
| --- | --- |
| Readers that price a day other than today | A reader needs a future or past price, twice (section 4.2) |
| Near-match suggestions or a new matching rung | Unmatched rows that the shared engine could have bound are mapped by hand on three sets (Q8) |
| Packaging variants as a concept | The owner names a supplier that prices one code in two packings that Sorento buys as one product (Q9) |
| FX conversion, or writing `products.cost_price` | The owner rules that the MYR cost should follow supplier prices (Q1, Q2) |
| OTP on the supplier page | A link is found forwarded outside the supplier, or the owner asks |
| Server-sent WeChat messages | Sorento connects a WeChat channel with an API |
| Creating a product from an unmatched code | Unmatched rows are routinely new products the owner wants in the master |
| More than one open set per supplier | A 409 seen more than once a month |
| Remembered skips | Section 6 trigger |
| Parsing on the `imports` queue | Section 5 trigger |

### Risks

- **Direct writers overwrite a price that has cost lists** (section 7.5): a PO flow or the
  product import writes `unit_cost`, and the next tick puts the price in force back. Visible in
  the audit trail both times; Q16 asks the owner whether those writers should add a cost list row
  instead.
- **Verification off means one person can change a price.** That is the owner's ruling for staff
  uploads; the audit row records `verified = false` and the setting change is itself audited.
- **The reorder engine starts using applied prices immediately.** The apply bar shows the
  largest rise so the user sees it before clicking.
- **The daily tick does not run** (worker down): scheduled prices start late. The Prices tab shows
  "In force" computed on read, so a mismatch with `unit_cost` is visible; the tick is idempotent
  and catches up on its next run.
- **CI has no data** (lesson): every test seeds its own supplier, products and links; the fixture
  file is committed, not read from a local path.

## 12. Owner rulings and open questions

Round 1 asked fifteen questions (26 Sep 2026). Rulings are recorded here as dated lines; the UAC
is written to them.

1. **Which price is "the cost price" this updates?** The supplier's price per product, which the
   reorder engine reads. `products.cost_price` (MYR, stock valuation) is not touched.
   **Owner ruling (26 Sep 2026): "yeah correct". Applied: AC-S2-13 and section 2.**
2. **Currency and exchange rate.** Keep the supplier's currency, no conversion.
   **Owner ruling (26 Sep 2026): "yeah correct, most is cny i believe in the file provided".
   Applied: section 5.1 step 7 and AC-S1-07; the TAIYANG fixture's currency is CNY.**
3. **Effective dates.** **Owner ruling (27 Sep 2026, 00:10 MYT): "oh okay yeah we need that, like
   a date range, there will be end also if there needs to be, so it is like price list function
   in ERP system including Odoo, where 1 product can have different price list, so this is like 1
   product supplier can have different cost list and the cost list can have start and end
   (optional), if both null then means always, if got start only then means no end, concept like
   that". Applied: `product_supplier_costs` (section 4.1) with optional start and end; the price
   in force rule (latest start wins); `unit_cost` kept as the price in force with a daily tick
   (4.2); the upload dialog and the supplier page take an optional Valid from and Valid to;
   AC-CL-01 to AC-CL-08.**
4. **Price basis.** **Owner ruling (27 Sep 2026, 00:10 MYT): "oh this is raw price only, no
   include shipping tax terms". Applied: the price is the raw unit price; no basis, shipping, tax
   or terms field anywhere (section 4.7, AC-CL-02).**
5. **Who may upload.** **Owner ruling (26 Sep 2026): "just give it a new permission and seed it
   for purchasing roles". Applied: `procurement.cost_price_changes.upload` (section 10, AC-S1-16,
   AC-S1-25).**
6. **Who may verify, and must it be a second person?** **Owner ruling (26 Sep 2026): "1 person
   from sorento". Applied: `verify` is a Sorento staff permission; one verifier's decision is
   final; the uploader or submitter may not verify their own set (section 7.2, AC-S2-03,
   AC-S2-19).**
7. **Partial acceptance and returns.** **Owner ruling (26 Sep 2026): "yeap". Applied: AC-S2-01,
   AC-S2-02, AC-S2-09 (verification path).**
8. **Codes we do not know.** **Owner question (27 Sep 2026, 00:10 MYT): "hmm i don't think this
   will happen, is this overdesign?" Answered on PR #1291 (round 3) with the file's evidence.
   Applied: near-match suggestion is dropped. The shared engine binds what it can (exact, the
   supplier's recorded aliases, the separator, order and trap-size rungs it already runs for PIs,
   packing lists and loading plans); every other code is "Not found" with a product dropdown to
   map it or Skip (section 6, AC-S1-08). The one real difference visible from here is
   `SRTWT1900-BL-DIY` in the file against `SRTWT1900-DIY` in our catalogue; pre-flight query 3
   settles whether that is a manual map or an exact match.**
9. **Packaging variants.** Round 1 recommended "pick one of two packaging prices"; the owner said
   "yeah correct" (26 Sep), then asked **"why got packaging variants de" (Lavish, 27 Sep 2026,
   00:45 MYT)**. Answered on PR #1291 (round 3): the only bracketed code seen in the file is
   `CB2500SS-BL（彩盒）` (colour box); no row pairing it with a second packing has been seen.
   **Applied: the variant concept is dropped.** The bracket text is cleaned off the code so it
   matches, and shown as a note (section 5.1 step 5). A code that appears twice in one upload is
   flagged "Duplicate code" and one is skipped, the generic check any upload needs (AC-S1-10).
10. **One open set per supplier.** **Owner ruling (26 Sep 2026): "yeah correct". Applied: the
    partial unique index (4.3) and AC-S1-14.**
11. **Supplier identity, what they see, and link expiry.** Not yet answered. Recommend: one link
    per supplier, 30 days, revocable, no OTP; the supplier sees only its own linked products, its
    own cost lists and per-line outcomes.
12. **Language.** Not yet answered. Recommend Chinese first with English beneath and a 中文 / EN
    switch; staff screens stay English.
13. **Other ways a supplier price changes today.** Not yet answered. Recommend enforcing the
    existing product-supplier permissions and auditing every supplier price change.
14. **Delivering the link over WeChat.** Not yet answered. Recommend staff send it from their own
    WeChat; the dialog gives a link, a QR image and a ready bilingual message.
15. **Who hears about a submission.** Not yet answered. Recommend an in-app notification to
    verifiers on submit, and to the submitter on apply or return (verification path only).
16. **(new, round 3) Old writers of a supplier price.** PO flows and the product import write the
    supplier price directly. For a product-supplier that has cost lists, should they (a) be
    overwritten back to the cost list's price in force by the next daily tick, or (b) add an
    "always" cost list row of their own? **Recommend (a)** for the first rollout: no change to
    those flows, visible in the audit trail. Under (b) five writers change and each writes a cost
    list row.

Rulings of 27 Sep 2026 that are not numbered questions:

- **Verification (Lavish, 00:45 MYT): "initially i will roll out to them is sorento upload so
  don't really need verification, this verification we need to do now, but will enable when the
  supplier comes into the picture". Applied: verification is built in Lane A (S2) behind
  `cost_price_verification_enabled`, default off (sections 4.6, 7.1, 7.2); a supplier submission
  is always verified; AC-S2-20.**
- **Matching engine (Lavish, 00:45 MYT): "use the same matching engine as we use in loading plan
  upload and packing list / supplier invoice upload thanks". Applied: section 3.7 names it and
  section 6 calls it unchanged; AC-S1-08.**
- **Search (Lavish, 00:45 MYT): "ok this is good, need to have search everywhere, correct, this
  applies to the pages that we do, must have search capability". Applied: section 8.5 lists the
  search on every screen; AC-SR-01 to AC-SR-05.**
- **Mockups (Lavish 00:45 and chat 00:50 MYT): "i need UI mockups" / "cost price yeah need final
  mockup ya". Applied: four final mockup files (header of this plan), every screen at 1280 and
  375, embedded in the alignment page.**
