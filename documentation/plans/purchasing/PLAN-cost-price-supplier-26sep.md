# PLAN: Cost price from the supplier's price list, verified before it applies (#1288)

Status: draft plan + UAC, 26 Sep 2026, awaiting the owner's answers to section 12. Track: full
(two new tables and a migration, new permissions, a new public ingest surface with uploads).
Nothing built; this lane is docs only (draft PR #1291).
UAC: `cost-price-supplier-acceptance-criteria.md` (same folder; the Journey is there and every AC
traces to a step in it).
Mockups: `mockups/cost-price-upload-review.html`, `mockups/cost-price-verification.html`,
`mockups/supplier-price-page.html`.
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
  there is no pending state, no second person, no effective date, no history beyond generic
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
who applied, effective date) and one line per parsed row (the supplier's code verbatim, what it
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
