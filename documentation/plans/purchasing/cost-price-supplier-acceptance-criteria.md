# UAC: Cost price from the supplier's price list, verified before it applies (#1288)

Status: draft, round 2 (26 Sep 2026). Written to the owner rulings of 26 Sep 23:45 MYT for Q1, Q2,
Q5, Q6, Q7, Q9, Q10, to the restated round 2 recommendations for Q3, Q4, Q8 (re-asked on PR
#1291), and to the round 1 recommendations for Q11 to Q15 (plan section 12). An owner answer that
differs from a recommendation rewrites the ACs it names before Phase 1 starts. Track: full.
Plan: `PLAN-cost-price-supplier-26sep.md` (same folder).
Mockups: `mockups/cost-price-upload-review.html` (S1), `mockups/cost-price-verification.html`
(S2), `mockups/supplier-price-page.html` (S3).

Tags: `[BE]` pytest, `[FE]` vitest, `[E2E]` agent-browser evidence run (no new Playwright spec),
`[T]` a test that guards a rule rather than a screen. Every AC names the Journey step it serves.

Terms used below:

- **Price** means the supplier's unit cost for one product, in the supplier's currency: the
  existing `product_suppliers.unit_cost` + `product_suppliers.currency` pair (Q1).
- **Change set** (CPC-nnnn) is one batch of proposed prices for one supplier, from one source: a
  staff upload, the supplier's page table, or the supplier's page upload.
- **Line** is one row of a change set: a supplier code, what it matched, the current price and
  the proposed price.
- **Verifier** is a Sorento staff user holding `procurement.cost_price_changes.verify` (Q6
  ruling). One verifier decides a set; the set's uploader or submitter cannot be its verifier.
- **Purchasing roles** are the roles holding `scm.proforma_invoice.upload` today, integration
  roles excluded (plan section 10).

## Journey

Actors: Mei Ling (purchasing, holds `upload` and `verify`), Kelvin (purchasing, a different
Sorento person, holds `upload` and `verify`), Mr Chen (sales at XIAMEN TAIYANG, no Sorento
account). Both staff hold the same permissions (Q5, Q6 rulings); Kelvin verifies Mei Ling's set
because she uploaded it.

**Staff upload (S1)**

- **J1.** Mei Ling gets the supplier's Excel over WeChat. She opens Purchasing > Cost price
  changes and clicks Upload price list.
- **J2.** She drops the file. The system reads the letterhead and pre-selects the supplier, and
  takes the currency from that supplier's current prices. On a clean file she clicks Upload with
  no other decision.
- **J3.** The system reads every sheet, finds the header row on each (序号 型号 产品配置 价格), fills
  merged configuration cells down, splits a bracketed packaging note off a code, and matches
  every code against the product master and this supplier's links. She lands on the change set
  in Draft.
- **J4.** The set opens filtered to "Price changed". Each line shows sheet and row, supplier code,
  configuration, the matched product, current price, new price, change percent and currency.
  Near matches, codes not in the master, and two packaging variants that land on one product are
  counted and listed apart; they stay out of the set until she maps, picks or skips them.
- **J5.** She resolves those rows (map a near match, pick one of two packaging prices, skip an
  unknown code) and clicks Submit for verification. The set is now Pending verification and
  nothing live has changed.

**Verification (S2)**

- **J6.** Kelvin gets an in-app notification and opens the set from it (or from the list, filtered
  to Pending verification).
- **J7.** He sees the changed lines with their percent change and when each price last changed.
  He accepts or rejects each line (Accept all is one click), optionally with a reason.
- **J8.** He clicks Apply N changes. Only now do the accepted prices land in
  `product_suppliers`. The set becomes Applied, and every product's Suppliers tab shows the new
  price with its history (applied date, change set, verifier, source).
- **J9.** Alternatively he clicks Return to submitter with a reason; the set goes back to Draft
  for Mei Ling (or to the supplier's page, for a supplier set).

**Supplier page (S3)**

- **J10.** Mei Ling opens the supplier record and clicks Share price page. The dialog shows a link,
  a QR code and a ready-to-paste bilingual message; she copies the message into WeChat to Mr Chen.
- **J11.** Mr Chen opens the link in WeChat. The page is in Chinese with English beneath. He sees
  only this supplier's linked products and their current prices. He either types new prices in
  the table or uploads the same Excel he used to send, reviews the changes, and clicks 提交审核
  Submit for review.
- **J12.** The set enters Pending verification exactly like a staff upload (J6 to J9). Mr Chen's
  page shows it as 审核中 Pending review, and later its outcome per set and per line.
- **J13.** When the link expires or is revoked, the page says so in both languages and nothing
  else is readable.

**Throughout**

- **J14.** Anyone with `view` can open any set's History tab and see who uploaded, mapped,
  skipped, submitted, accepted, rejected, returned and applied, with before and after values,
  and download the source file.

## S1: Staff upload into a pending change set

- **AC-S1-01** `[BE]` (J2, J3) Given the TAIYANG fixture workbook (5 sheets, letterhead rows 1 to 5,
  header at row 6), when it is parsed, then every sheet yields its rows with `sheet`, `row_no`,
  `supplier_code`, `configuration`, `price`, and the 序号 value; row counts are 40, 24, 18, 58 and
  118 (the owner's file), minus rows with neither a code nor a price.
- **AC-S1-02** `[BE]` (J3) Given a sheet whose header sits at row 4 or row 9 instead of 6, when
  parsed, then the header is still found (scan of the first 20 rows for the aliases), and a sheet
  with no recognisable header is reported as "no header found" by name and skipped, not a 500.
- **AC-S1-03** `[BE]` (J3) Given 产品配置 merged across rows 7 to 9, when parsed, then rows 8 and 9
  carry row 7's configuration and are flagged `configuration_from_merge`. Given 价格 merged
  across two rows, then both rows carry the price and are flagged `price_from_merge`, and the
  flag shows on the line.
- **AC-S1-04** `[BE]` (J3) Given codes `CB2500SS-BL（彩盒）`, `CB2500SS-BL(白盒)` and
  ` SRTWT1900-BL-DIY `, when parsed, then the codes are NFKC-folded and trimmed to
  `CB2500SS-BL`, `CB2500SS-BL`, `SRTWT1900-BL-DIY`, the bracket text is kept as
  `packaging_note` (`彩盒`, `白盒`), and the verbatim cell text is kept as `supplier_code_raw`.
- **AC-S1-05** `[BE]` (J3) Given a price cell holding `¥512`, `512.00元`, `"512"` or `512`, then the
  price is 512.00; given `面议`, blank or a negative number, then the line has no price, is listed
  under "Needs attention" and cannot be submitted until skipped.
- **AC-S1-06** `[BE]` (J2) Given the letterhead text contains the supplier's name or code and
  exactly one active supplier matches, then the upload pre-selects it; given zero or several, then
  the supplier field is empty and required.
- **AC-S1-07** `[BE]` (J2) Given the supplier's existing links all carry `CNY` (the owner
  expects CNY for TAIYANG's file, Q2 ruling), then the set's currency is CNY; given the 价格 header carries a currency token (`RMB`, `元`, `USD`), then that
  wins; given neither resolves, then the currency field is required in the upload dialog. There is
  no house default.
- **AC-S1-08** `[BE]` (J3, J4) Given the parsed lines, when matched, then each line records one
  outcome: `exact` / `normalised` / `alias` (bound to a product), `near` (one token-set
  candidate from the existing `supplier_code_matcher`, suggested and never bound), `unmatched`,
  or `ambiguous` (several candidates, not bound). No one-edit rung is added (Q8, round 2).
  Matching runs with `remember=False`; the upload writes no alias.
- **AC-S1-09** `[BE]` (J4) Given a bound product, then the line records the current
  `unit_cost` and `currency` of the (product, supplier) link at parse time, the new price, and the
  change percent (null when there is no current price); given no link exists, then the line is
  `new_link`.
- **AC-S1-10** `[BE]` (J4) Given two lines bound to one product (two packaging variants), then
  both are flagged `pick_one`, neither is submittable, and picking one marks the other `skipped`
  with reason `other packaging variant picked`.
- **AC-S1-11** `[BE]` (J5) Given a Draft set with any `near`, `unmatched`, `ambiguous`, `pick_one`
  or priceless line not yet mapped, picked or skipped, when submitted, then 422 names the count;
  given all resolved, then status becomes `pending_verification` and `submitted_by_user_id`,
  `submitted_at` are set.
- **AC-S1-12** `[BE]` (J5) Given a near or unmatched line mapped to a product, then the mapping is
  stored on the line and the alias is written (`source=manual`) only when the set is applied, so a
  rejected or discarded set leaves no alias behind.
- **AC-S1-13** `[BE]` (J4) Given a set, then unchanged lines (new price equals current price in the
  same currency) are stored with outcome `unchanged`, listed on their own tab and never applied.
- **AC-S1-14** `[BE]` (J1) Given a supplier that already has a non-terminal set (Draft or Pending
  verification, from any channel), when a second upload for it arrives, then 409 names the open
  set's code, and the FE offers to open it.
- **AC-S1-15** `[BE]` (J2) Given a file over 25 MB, not `.xlsx`/`.xls`, or over 5,000 parsed rows,
  then 422 with a plain message and nothing is stored.
- **AC-S1-16** `[BE]` (J1 to J5) Given a caller without `procurement.cost_price_changes.upload`,
  then upload, map, pick, skip and submit return 403; without `.view`, then list and detail
  return 403.
- **AC-S1-25** `[BE]` `[T]` (J1) Given the migration has run, then
  `procurement.cost_price_changes.upload` and `.view` exist and are granted to every role that
  holds `scm.proforma_invoice.upload`, and to `admin` and `superadmin`; no `integration_%` role
  receives either; running the migration twice grants nothing twice (Q5 ruling).
- **AC-S1-17** `[BE]` (J3) Given the caller's session spans two companies, then upload returns 422
  "pick one company" (the `_require_single_company` rule).
- **AC-S1-18** `[BE]` (J14) Given an upload, then the source file is retained and downloadable from
  the set, and the set records its file name, sheet names and parser notes (header row per sheet,
  merged cells filled).
- **AC-S1-19** `[FE]` (J2) The upload dialog pre-fills supplier and currency from the parse probe,
  keeps both editable (`SearchableSelect`, supplier not clearable, currency required only when
  unresolved), and uses `FileDropzone`.
- **AC-S1-20** `[FE]` (J4) The set detail renders the stat cards as filters, sheet tabs
  (`variant="line"`, scrolling at 375px), and a `DataGrid` with explicit column sizes; the change
  percent renders as a `Badge` (rise and fall tinted apart); a line with `packaging_note` shows it
  under the code.
- **AC-S1-21** `[FE]` (J4) Every section renders with an explicit empty state (e.g. "No near
  matches"), including a set with zero changed lines ("Nothing changed against current prices"
  with Discard as the next step).
- **AC-S1-22** `[FE]` (J1) Purchasing > Cost price changes is a `DataGrid` list (code, supplier,
  source, status pill, lines changed, submitted by, submitted at, applied at) with search, a status
  filter and Upload price list; rows use `rowHref`, and the detail page carries
  `RecordNavigation`.
- **AC-S1-23** `[BE]` (J5) Discard on a Draft set is a hard delete through the deferred-action
  window (10 s, no dialog); a Pending or Applied set cannot be deleted (409).
- **AC-S1-24** `[E2E]` (J1 to J5) From `/`, sidebar to Cost price changes, upload the fixture,
  resolve the near match and the packaging pick, submit; screenshots at 375px and 1280px; the
  product's live price is unchanged afterwards.

## S2: Verification and apply

- **AC-S2-01** `[BE]` (J7) Given a Pending set, when a verifier sets a line to accepted or rejected
  (with an optional reason up to 500 characters), then the decision, the verifier and the time are
  stored on the line; Accept all and Reject all apply to every undecided changed line.
- **AC-S2-02** `[BE]` (J8) Given any undecided changed line, when Apply is called, then 422 names
  the count.
- **AC-S2-03** `[BE]` `[T]` (J8) Given the verifier is the set's uploader or submitter, then accept,
  reject, return and apply return 403 `SAME_PERSON_CANNOT_VERIFY`; this holds for superadmin too.
  Given a different Sorento user holding `verify`, then that one user's decisions and Apply are
  enough (no second approval). A supplier-page set has no staff submitter, so any one verifier
  may verify it (Q6 ruling).
- **AC-S2-04** `[BE]` (J8) Given Apply, then in one transaction: each accepted line writes
  `product_suppliers.unit_cost` and `currency` for its (product, supplier) pair; a `new_link` line
  creates the link (lead time from AC-S2-05); every mapped line writes its alias
  (`source=manual`); the set becomes `applied` with `applied_by_user_id`, `applied_at` and
  Rejected lines write nothing.
- **AC-S2-05** `[BE]` (J8) Given a `new_link` line accepted, then the new link's
  `standard_lead_time_days` is the most common value across this supplier's existing links; given
  the supplier has no links, then the line shows a lead time input and cannot be accepted empty.
- **AC-S2-06** `[BE]` `[T]` (J8) Given a line's recorded current price no longer equals the live
  `unit_cost`/`currency` at Apply (someone changed it since parse), then Apply returns 409 listing
  those lines as `stale`, writes nothing, and the lines show both values for a fresh decision.
- **AC-S2-07** `[BE]` (J8) Given Apply is called twice concurrently, then exactly one succeeds
  (conditional update on `status='pending_verification'`), and the other returns 409.
- **AC-S2-08** `[BE]` (J8) Given Apply, then the new price takes effect at once and the set's
  `applied_at` is the date shown in history; Apply takes no date input (Q3, round 2 restated
  recommendation, re-asked). If the owner asks for the supplier's list date instead, this AC is
  rewritten to an `effective_date` defaulting to the apply date, never future.
- **AC-S2-09** `[BE]` (J9) Given Return to submitter with a reason (required, up to 500
  characters), then the set goes back to `draft`, decisions are cleared, the reason is stored and
  shown in the header, and the submitter (or the supplier page, for a supplier set) can edit and
  resubmit.
- **AC-S2-10** `[BE]` (J8) Given an Applied set, then no line, decision or date can change (409
  on every write route).
- **AC-S2-11** `[BE]` (J8) Given a product, then `GET .../products/{id}/supplier-cost-history`
  returns, per supplier, the accepted lines of applied sets newest first (price, currency,
  applied date, set code, verifier, channel), plus one "before tracking" row per pair carrying
  the oldest recorded current price when it is not null.
- **AC-S2-12** `[BE]` (J6) Given a set enters `pending_verification`, then every active user holding
  `verify` in the set's company gets one in-app notification linking to the set; given a set is
  applied or returned, then the submitter (staff set) gets one.
- **AC-S2-13** `[BE]` `[T]` (J8) Given Apply, then `products.cost_price`, `products.list_price` and
  `products.invoice_price` are unchanged (Q1): the supplier price never writes the product's MYR
  cost.
- **AC-S2-14** `[BE]` (J7) The product-supplier CRUD routes
  (`/procurement/product-suppliers`) require `procurement.product_suppliers.add|edit|delete` from
  this slice on, with a grant sweep to every role that could reach them before (Q13).
- **AC-S2-15** `[FE]` (J7) The verification view is the same set detail page (same tabs, same
  order) with the Decision column switched on; the apply bar shows accepted,
  rejected and undecided counts, and the largest rise; Apply names the accepted count and is
  disabled with a tooltip reason when AC-S2-02 or AC-S2-03 would refuse it.
- **AC-S2-16** `[FE]` (J8) The product detail's Suppliers tab shows the cost history sub-table per
  AC-S2-11 (no row action, no pointer cursor), with the empty state "No verified price changes
  yet".
- **AC-S2-17** `[FE]` (J8) The price on the product page renders in the link's own currency
  (fixes `ProductDetail.tsx` formatting every cost as MYR, for the supplier price only).
- **AC-S2-18** `[E2E]` (J6 to J8) A second user opens the notification, rejects one line with a
  reason, applies; the product's Suppliers tab shows the new price and history; the reorder
  screen's supplier price for that product shows the new value. 375px and 1280px.
- **AC-S2-19** `[BE]` `[T]` (J7, J8) Given the migration has run, then
  `procurement.cost_price_changes.verify` is granted to every role that holds
  `scm.proforma_invoice.upload`, and to `admin` and `superadmin`, and to no `integration_%` role;
  given an API-key principal (`X-API-Key`, including one acting as a user through
  `EXTERNAL_API_KEY_ACT_AS_USER_ID`) or any public supplier route, then decide, return and apply
  are unreachable (403 or no such route): verification is by a Sorento staff session only (Q6
  ruling).

## S3: The supplier page

- **AC-S3-01** `[BE]` (J10) Given a user with `procurement.suppliers.price_link`, when they issue a
  link for a supplier, then a `supplier_price_links` row is created with a 256-bit token
  (`secrets.token_urlsafe(32)`), `expires_at` 30 days out, `issued_by_user_id`, and the
  recipient name pre-filled from the supplier's `contact_name`; any older active link for that
  supplier is revoked in the same transaction (one active link per supplier).
- **AC-S3-02** `[BE]` (J13) Given revoke (5 s deferred action, no dialog), then `revoked_at` is set;
  given an unknown, expired or revoked token, then every public route returns the same 404 body.
- **AC-S3-03** `[BE]` `[T]` (J11) Given a valid token, then the public GET returns only: the
  supplier's display name, the set currency, and for each product linked to this supplier its
  code, description, the supplier's current price, and the last supplier code seen for it. It
  never returns another supplier's price, `products.cost_price`, `list_price`, margins, internal
  reasons or any user's name.
- **AC-S3-04** `[BE]` (J11) Given the supplier edits prices in the table, then each save writes the
  supplier's open Draft set for this link (created on first edit, channel `supplier_page`);
  unedited rows are not lines.
- **AC-S3-05** `[BE]` (J11) Given the supplier uploads the Excel, then the same parser and matcher
  as S1 build lines into the supplier's Draft set (channel `supplier_upload`); lines that did not
  bind to one of this supplier's linked products are shown to the supplier as "models we do not
  know" and kept on the set for Sorento, never bound by the supplier.
- **AC-S3-06** `[BE]` (J11, J12) Given Submit, then the set enters `pending_verification` with
  `submitted_via_link_id` set and no staff submitter; unmatched and packaging-pick lines go to the
  verifier to resolve (the verifier may map, pick or skip on a supplier set before deciding).
- **AC-S3-07** `[BE]` (J12) Given a supplier set is Pending, then the page's table is read-only and
  shows the submitted values; a second submit or a new upload returns 409 (one open set per
  supplier, AC-S1-14).
- **AC-S3-08** `[BE]` (J12) Given the History route, then the supplier sees each of its own sets
  (code, submitted date, status, accepted count of total) and per-line accepted or rejected, never
  the reason text.
- **AC-S3-09** `[BE]` `[T]` (J11) Given more than 60 public requests a minute, or more than 10
  uploads an hour, from one token or one IP, then 429 (`rate_limit.hit`); upload limits of
  AC-S1-15 apply.
- **AC-S3-10** `[BE]` `[T]` (J11) Given any public write, then the audit row carries actor type
  `public_link`, the link id and the recipient name (section 9 of the plan), never a Sorento
  user id.
- **AC-S3-11** `[BE]` (J10) Given a link is opened, then `last_opened_at` and `open_count` update
  (not an audit row per open).
- **AC-S3-12** `[FE]` (J10) The supplier record's gear menu has Share price page (permission gated)
  opening a modal with the URL, a `QRCodeSVG` (`qrcode.react`, already a dependency), Copy link,
  Save QR image, and Copy message (bilingual text with the URL and the expiry date); the modal
  shows the current link's expiry, last opened time and open count, and Revoke.
- **AC-S3-13** `[FE]` (J11) The public page lives at `/c/{company}/supplier-prices/{token}`, renders
  at 375px first, and every label is Chinese first with English beneath; a 中文 / EN toggle swaps
  which leads and is remembered in `localStorage` (guarded). Tabs: 价格表 Prices, 上传Excel Upload,
  记录 History.
- **AC-S3-14** `[FE]` (J11) Price inputs are `inputmode="decimal"` at 16 px (no iOS zoom), a changed
  value is highlighted with its change percent, the sticky footer shows changed and total counts
  and 提交审核 Submit for review, and search filters by model code.
- **AC-S3-15** `[FE]` (J13) An expired or revoked link shows 链接已失效 / This link is no longer valid
  and nothing else.
- **AC-S3-16** `[BE]` (J11) The public page response sets `Referrer-Policy: no-referrer` and
  `X-Robots-Tag: noindex`; the token is never written to application logs (path is masked the way
  the supplier-request route is).
- **AC-S3-17** `[E2E]` (J10 to J12) Staff issues a link; a second browser context opens it at 375px,
  edits two prices, submits; the staff list shows the set Pending with channel Supplier page; a
  verifier applies it; the supplier page's History shows Applied. Screenshots at 375px (supplier)
  and 1280px (staff).

## Audit trail (all slices, per #1281)

- **AC-AU-01** `[BE]` (J14) `cost_price_change_sets`, `cost_price_change_lines`,
  `supplier_price_links` and `product_suppliers` carry `__audit_track__`; every create, update and
  delete writes an `audit_logs` row with old and new values.
- **AC-AU-02** `[BE]` (J14) Upload, submit, return, apply, link issue and link revoke each write one
  named audit action (`COST_SET_UPLOAD`, `COST_SET_SUBMIT`, `COST_SET_RETURN`, `COST_SET_APPLY`,
  `SUPPLIER_PRICE_LINK_ISSUE`, `SUPPLIER_PRICE_LINK_REVOKE`) against the set or link, carrying the
  counts and, for apply, the list of (product code, old, new, currency).
- **AC-AU-03** `[BE]` `[T]` (J8) Given Apply, then every `product_suppliers` row it touched has an
  audit UPDATE (or CREATE) with the old and new `unit_cost`/`currency`, and the same `trace_id` as
  the `COST_SET_APPLY` row.
- **AC-AU-04** `[FE]` (J14) The set's History tab lists those events newest first with actor,
  time (`formatDateTimeInMalaysia`) and a one-line summary, and links the source file download.

## Out of scope (named triggers in the plan, section 11)

A separate effective date and future-dated prices (Q3), FX conversion into MYR, writing
`products.cost_price`, a supplier login (arrives with #1280), OTP on the supplier page, automatic WeChat sending, product creation
from an unmatched code, and multiple open sets per supplier.
