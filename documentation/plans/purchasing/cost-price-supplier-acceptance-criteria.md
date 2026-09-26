# UAC: Cost price from the supplier's price list, as dated cost lists, verified when suppliers submit (#1288)

Status: draft, round 3 (27 Sep 2026). Written to the owner rulings of 26 Sep 23:45 MYT (Q1, Q2,
Q5, Q6, Q7, Q10), 27 Sep 00:10 MYT (Q3, Q4), 27 Sep 00:45 MYT (verification off for the first
rollout, the shared matching engine, search on every page) and 27 Sep 00:50 MYT (final mockups);
Q8 and Q9 are withdrawn features (plan section 12); Q11 to Q16 stay written to their
recommendations. An owner answer that differs rewrites the ACs it names before Phase 1 starts.
Track: full.
Plan: `PLAN-cost-price-supplier-26sep.md` (same folder).
Mockups: `mockups/cost-price-uploads.html` (J1, J2), `mockups/cost-price-review.html` (J3 to J9,
verification off and on), `mockups/supplier-cost-lists.html` (J8, J15, J16, the setting),
`mockups/supplier-price-page.html` (J10 to J13).

Tags: `[BE]` pytest, `[FE]` vitest, `[E2E]` agent-browser evidence run (no new Playwright spec),
`[T]` a test that guards a rule rather than a screen. Every AC names the Journey step it serves.

Terms used below:

- **Cost list** is one row of a product-supplier link's prices: a raw unit price (Q4) in the
  supplier's currency, with an optional start date and an optional end date (Q3). Both empty
  means always; a start with no end means from that day on.
- **Price in force** on a day is, among the link's cost lists that cover that day, the one with
  the latest start (an empty start counts as earliest; a tie goes to the newest). It is kept in
  `product_suppliers.unit_cost` + `currency`, which every existing reader uses.
- **Change set** (CPC-nnnn) is one upload or one supplier submission for one supplier.
- **Line** is one row of a change set: a supplier code, what it matched, the price in force and
  the proposed price.
- **Verification** is the setting `cost_price_verification_enabled` (default off). **Verifier** is
  a Sorento staff user holding `procurement.cost_price_changes.verify`.
- **Purchasing roles** are the roles holding `scm.proforma_invoice.upload` today, integration
  roles excluded.

## Journey

Actors: Mei Ling (purchasing, holds `upload` and `verify`), Kelvin (purchasing, a different
Sorento person, same permissions), Mr Chen (sales at XIAMEN TAIYANG, no Sorento account).

**Staff upload, verification off (S1, the first rollout)**

- **J1.** Mei Ling gets the supplier's Excel over WeChat. She opens Purchasing > Cost price
  uploads, can search past uploads by code, supplier or file name, and clicks Upload price list.
- **J2.** She drops the file. The system pre-selects the supplier from the letterhead and the
  currency from that supplier's prices. She may set Valid from and Valid to (both optional; empty
  means always). She clicks Upload.
- **J3.** The system reads every sheet, finds the header row on each (序号 型号 产品配置 价格), fills
  merged configuration cells down, cleans a bracketed note off a code, and matches every code with
  the same engine the PI, packing list and loading plan uploads use. She lands on the review page.
- **J4.** The review page opens filtered to "Price changed". She can search by code,
  configuration or product, and switch sheets. Each line shows sheet and row, supplier code,
  configuration, matched product, price in force, new price, change percent and currency. Codes
  the engine could not match are listed under "Not found"; a code that appears twice under
  "Duplicate code".
- **J5.** She maps each Not found row from a product dropdown or skips it, and skips one of each
  duplicate.
- **J8.** She clicks Apply N changes. Each line becomes a new cost list on its product-supplier
  link with the chosen dates; the price in force updates at once (or on the start date, for a
  future start). The set is Applied, marked "not verified".

**Staff upload, verification on (S2, built now, switched on later)**

- **J5b.** With the setting on, Apply is replaced by Submit for verification. The set is Pending
  and nothing live has changed.
- **J6.** Kelvin gets an in-app notification and opens the set.
- **J7.** He accepts or rejects each line (Accept all is one click), optionally with a reason.
- **J8b.** He clicks Apply N changes, which does what J8 does, marked "verified by Kelvin".
- **J9.** Or he clicks Return to submitter with a reason; the set goes back to Draft.

**Supplier page (S3)**

- **J10.** Mei Ling opens the supplier record and clicks Share price page. The dialog shows a link,
  a QR code and a ready bilingual message; she copies it into WeChat to Mr Chen.
- **J11.** Mr Chen opens the link. The page is Chinese first with English beneath. He searches
  his models, sees each one's cost lists with their date ranges and which is in force, types new
  prices (with an optional Valid from and Valid to for the submission) or uploads the same Excel,
  and clicks 提交审核 Submit for review.
- **J12.** The set is Pending whatever the setting, and goes through J6 to J9. His page shows
  审核中 Pending review, and later the outcome per line.
- **J13.** When the link expires or is revoked, the page says so in both languages and nothing
  else is readable.

**Cost lists (S1)**

- **J15.** Anyone with product-supplier view opens a supplier's Prices tab, searches a product,
  and sees every cost list with its dates and a status: In force, Scheduled, Ended, or Always.
- **J16.** Staff with product-supplier edit add, change or delete a cost list row there by hand;
  the price in force updates at once.
- **J17.** Overnight, a scheduled cost list whose start date has arrived becomes the price in
  force, and one whose end date has passed stops being it.

**Throughout**

- **J14.** Anyone with `view` opens a set's History tab and sees who uploaded, mapped, skipped,
  submitted, decided, returned and applied, with before and after values, and downloads the file.

## S1: Staff upload, review and apply (verification off)

- **AC-S1-01** `[BE]` (J2, J3) Given the TAIYANG fixture workbook (5 sheets, letterhead rows 1 to 5,
  header at row 6), when it is parsed, then every sheet yields its rows with `sheet`, `row_no`,
  `supplier_code`, `configuration`, `price`, and the 序号 value; row counts are 40, 24, 18, 58 and
  118 (the owner's file), minus rows with neither a code nor a price.
- **AC-S1-02** `[BE]` (J3) Given a sheet whose header sits at row 4 or row 9 instead of 6, then
  the header is still found; a sheet with no recognisable header is reported by name and skipped,
  not a 500.
- **AC-S1-03** `[BE]` (J3) Given 产品配置 merged across rows 7 to 9, then rows 8 and 9 carry row 7's
  configuration flagged `configuration_from_merge`. Given 价格 merged across two rows, then both
  carry the price flagged `price_from_merge`, and the flag shows on the line.
- **AC-S1-04** `[BE]` (J3) Given codes `CB2500SS-BL（彩盒）` and ` SRTWT1900-BL-DIY `, then the codes
  are NFKC-folded and trimmed to `CB2500SS-BL` and `SRTWT1900-BL-DIY`, the bracket text is kept as
  `code_note` (`彩盒`) and shown under the code, the verbatim cell is kept as `supplier_code_raw`,
  and the note is never used to match.
- **AC-S1-05** `[BE]` (J3) Given a price cell holding `¥512`, `512.00元`, `"512"` or `512`, then the
  price is 512.00; given `面议`, blank or a negative number, then the line has no price, is listed
  under "Needs attention" and blocks Apply until skipped.
- **AC-S1-06** `[BE]` (J2) Given the letterhead names exactly one active supplier, then the upload
  pre-selects it; given zero or several, the supplier field is empty and required.
- **AC-S1-07** `[BE]` (J2) Given the supplier's existing links all carry `CNY`, then the set's
  currency is CNY; given the 价格 header carries a currency token, that wins; given neither, the
  currency is required. No house default (Q2 ruling).
- **AC-S1-08** `[BE]` `[T]` (J3, J4) Given the parsed lines, then codes are bound by the shared
  engine unchanged (the exact, company-scoped lookup, then the supplier code ladder, with
  `remember=False`), and each line records one outcome: `exact`, `alias` or `ladder` (with the
  rung) when bound, else `unmatched`. A code the ladder finds ambiguous, or that names a product
  set, is `unmatched`. There is no near-match or suggestion outcome, and no new rung (Q8, round
  3). A test asserts the upload calls the same engine functions the PI apply calls.
- **AC-S1-09** `[BE]` (J4) Given a bound product, then the line records the price in force of the
  (product, supplier) link at parse time, the new price, and the change percent (null when there
  is none); given no link exists, the line is `new_link`.
- **AC-S1-10** `[BE]` (J4, J5) Given two lines that bind to one product, then both are flagged
  `duplicate_code` and listed under "Duplicate code"; Apply is refused until one is skipped.
  There is no packaging variant concept (Q9, round 3).
- **AC-S1-11** `[BE]` (J5, J8) Given any `unmatched`, `needs_attention` or `duplicate_code` line not
  mapped or skipped, when Apply (or, with verification on, Submit) is called, then 422 names the
  count.
- **AC-S1-12** `[BE]` (J5, J8) Given an unmatched line mapped to a product from the dropdown, then
  the map is stored on the line (`match_outcome = manual`); the alias (`source=manual`) and the
  engine's own `auto` aliases for ladder binds are written only when the set is applied, so a
  discarded set teaches nothing.
- **AC-S1-13** `[BE]` (J4) Given a line whose new price equals the price in force in the same
  currency and the set has no dates, then it is `unchanged`, listed on its own filter and never
  applied. Given the set has dates, the line is `changed` (a dated cost list is new information).
- **AC-S1-14** `[BE]` (J1) Given a supplier that already has a Draft or Pending set, when a second
  upload arrives, then 409 names the open set's code and the FE offers to open it.
- **AC-S1-15** `[BE]` (J2) Given a file over 25 MB, not `.xlsx`/`.xls`, or over 5,000 parsed rows,
  then 422 with a plain message and nothing is stored.
- **AC-S1-16** `[BE]` (J1 to J8) Given a caller without `procurement.cost_price_changes.upload`,
  then upload, map, skip, discard and apply (verification off) return 403; without `.view`, list
  and detail return 403.
- **AC-S1-17** `[BE]` (J3) Given the caller's session spans two companies, then upload returns 422
  "pick one company".
- **AC-S1-18** `[BE]` (J14) Given an upload, then the source file is retained and downloadable, and
  the set records file name, sheet names and parser notes.
- **AC-S1-19** `[FE]` (J2) The upload dialog pre-fills supplier and currency from the parse probe;
  Supplier and Currency are the system single-select (`SearchableSelect`; supplier not clearable,
  currency required only when unresolved); Valid from and Valid to are optional date inputs,
  clearable, with Valid to refused before Valid from; the file's own date from its name is shown
  beside them as text; the file input is `FileDropzone`.
- **AC-S1-20** `[FE]` (J4) The review page renders the stat cards as filters, a search box, sheet
  tabs (`variant="line"`, scrolling at 375px), and a `DataGrid` with explicit column sizes; change
  percent is a `Badge` (rise and fall tinted apart); a `code_note` shows under the code; a
  Not found row carries the product single-select (`SearchableSelect`, searching code and
  description, clearable) and Skip.
- **AC-S1-21** `[FE]` (J4) Every filter renders an explicit empty state (e.g. "No codes need
  mapping"), including a set with zero changed lines ("Nothing changed against current prices",
  with Discard as the next step).
- **AC-S1-22** `[FE]` (J1) Purchasing > Cost price uploads is a `DataGrid` list (code, supplier,
  source, validity, status pill, lines changed, uploaded by, applied at, verified) with search
  (code, supplier, file name), a Status filter (`SearchableMultiSelect`), a Supplier filter
  (`SearchableSelect`, clearable) and Upload price list; rows use `rowHref`, and the detail page
  carries `RecordNavigation`.
- **AC-S1-23** `[BE]` (J5) Discard on a Draft set is a hard delete through the deferred-action
  window (10 s, no dialog); a Pending or Applied set cannot be deleted (409).
- **AC-S1-24** `[E2E]` (J1 to J8) From `/`, sidebar to Cost price uploads, search the list, upload
  the fixture with Valid from set, search the review page, map a Not found row, skip one
  duplicate, apply; the supplier's Prices tab shows the new cost lists with that start date.
  Screenshots at 375px and 1280px.
- **AC-S1-25** `[BE]` `[T]` (J1) Given the migration has run, then
  `procurement.cost_price_changes.upload` and `.view` are granted to every role holding
  `scm.proforma_invoice.upload`, and to `admin` and `superadmin`; no `integration_%` role gets
  either; running it twice grants nothing twice (Q5 ruling).
- **AC-S1-26** `[BE]` `[T]` (J8) Given verification is off and a Draft staff set with everything
  resolved, when its uploader calls Apply, then the set becomes `applied` with `verified = false`,
  and no Submit or decision is required.
- **AC-S1-27** `[BE]` (J8) Given Apply, then in one transaction: one `product_supplier_costs` row
  per changed or new-link line not skipped, carrying the set's currency, start and end dates and
  `source_change_line_id`; a `new_link` line creates the link first (AC-S2-05); the price in force
  is recomputed; the aliases of AC-S1-12 are written.

## Cost lists (S1)

- **AC-CL-01** `[BE]` `[T]` (J15, Q3) `price_in_force(link, day)` returns: the always row when it is
  the only row; a dated row over the always row inside its range; the always row again after the
  dated row's end; for two rows covering the day, the one with the later start; for equal starts,
  the newest; none when every row has ended or not started.
- **AC-CL-02** `[BE]` (Q4) A cost list row stores only price, currency, start and end; there is no
  basis, shipping, tax or terms field on any screen or route.
- **AC-CL-03** `[BE]` Given end before start, then 422; given a negative price, 422.
- **AC-CL-04** `[BE]` `[T]` (J8, J16) Given an apply or a hand edit, then `product_suppliers.unit_cost`
  and `currency` equal `price_in_force(link, today)` in the same transaction; null when none is
  in force. A link with no cost list rows is never written by this code.
- **AC-CL-05** `[BE]` `[T]` (J17) Given the daily tick runs for a fixed day, then every link with cost
  lists whose price in force differs from `unit_cost` is updated through the ORM, and one
  `SUPPLIER_COST_TICK` audit row lists them; a second run the same day changes nothing.
- **AC-CL-06** `[BE]` (J16) Given `procurement.product_suppliers.edit`, then add, change and delete
  of a cost list row succeed and are audited; without it, 403. Delete is the 10 s deferred action.
- **AC-CL-07** `[FE]` (J15) The supplier record's Prices tab lists each linked product with its cost
  list rows (price, currency, Valid from, Valid to, status pill: In force, Scheduled, Ended,
  Always; source: set code or "Edited by hand"), with search (product code, description, supplier
  code) and a Status filter (`SearchableMultiSelect`); empty state "No prices recorded for this
  supplier yet" with Upload price list as the next step.
- **AC-CL-08** `[FE]` (J15) The product record's Suppliers tab shows, per supplier, the price in
  force and its cost lists (same columns as AC-CL-07), with search by supplier name or set code;
  the price renders in the link's own currency (fixes `ProductDetail.tsx` formatting every cost
  as MYR, for the supplier price only).

## S2: Verification, built now and switched off

- **AC-S2-20** `[BE]` `[T]` (J5b) Given the migration has run, then
  `system_settings.cost_price_verification_enabled` exists, defaults to false, appears in both
  system settings serialisers, is editable only with the system settings edit permission, and a
  change writes `COST_VERIFICATION_SETTING`.
- **AC-S2-01** `[BE]` (J7) Given a Pending set, when a verifier sets a line accepted or rejected
  (optional reason up to 500 characters), then the decision, verifier and time are stored; Accept
  all and Reject all apply to every undecided changed line.
- **AC-S2-02** `[BE]` (J8b) Given any undecided changed line, when Apply is called on a Pending set,
  then 422 names the count.
- **AC-S2-03** `[BE]` `[T]` (J8b) Given verification applies and the verifier is the set's uploader
  or submitter, then accept, reject, return and apply return 403 `SAME_PERSON_CANNOT_VERIFY`,
  superadmin included. A different Sorento user holding `verify` is enough (Q6 ruling). A
  supplier set has no staff submitter, so any one verifier may verify it.
- **AC-S2-04** `[BE]` `[T]` (J5b) Given verification is on, then Apply on a Draft staff set returns
  409 "submit for verification first", and Submit moves it to `pending_verification` with
  `submitted_by_user_id`, `submitted_at`; given it is off, Submit returns 409 and Apply works
  (AC-S1-26).
- **AC-S2-05** `[BE]` (J8) Given a `new_link` line applied, then the new link's
  `standard_lead_time_days` is the most common value across this supplier's links; given none,
  the line shows a lead time input and blocks Apply while empty.
- **AC-S2-06** `[BE]` `[T]` (J8) Given a line's recorded price in force no longer equals the live
  one at Apply, then 409 lists those lines as `stale`, nothing is written, and the lines show both
  values.
- **AC-S2-07** `[BE]` (J8) Given Apply twice concurrently, exactly one succeeds (conditional update
  on the expected status), the other 409.
- **AC-S2-08** `[BE]` (J8b) Given Apply on a Pending set, then it writes exactly as AC-S1-27 and the
  set records `verified = true` with the verifier as `applied_by_user_id`.
- **AC-S2-09** `[BE]` (J9) Given Return with a reason (required, up to 500 characters), then the set
  goes back to `draft`, decisions are cleared, the reason shows in the header, and the submitter
  (or the supplier page) can edit and resubmit.
- **AC-S2-10** `[BE]` (J8) Given an Applied set, then no line, decision or date can change (409).
- **AC-S2-11** `[BE]` `[T]` (J12) Given the setting is off, when a supplier-channel set is
  submitted, then it is `pending_verification` and cannot be applied without a verifier; toggling
  the setting never moves a Pending set.
- **AC-S2-12** `[BE]` (J6) Given a set enters `pending_verification`, then every active user holding
  `verify` in the set's company gets one in-app notification; given applied or returned, the
  staff submitter gets one.
- **AC-S2-13** `[BE]` `[T]` (J8) Given Apply, then `products.cost_price`, `list_price` and
  `invoice_price` are unchanged (Q1).
- **AC-S2-14** `[BE]` (J7, J16) The product-supplier CRUD routes and the cost list routes require
  `procurement.product_suppliers.add|edit|delete`, with a grant sweep to every role that could
  reach them before (Q13).
- **AC-S2-15** `[FE]` (J5b, J7) With the setting on, the review page is the same layout (same tabs,
  same order) with Submit for verification in place of Apply for the uploader, and for a verifier
  the Decision column, Accept all, Return to submitter and Apply N changes; Apply is disabled with
  a tooltip reason when AC-S2-02 or AC-S2-03 would refuse it. With the setting off, none of these
  render.
- **AC-S2-16** `[FE]` (J5b) System Settings has one switch, "Verify cost price uploads by a second
  person", off by default.
- **AC-S2-17** `[FE]` (J14) The list and the set header show Verified by name, or "Not verified"
  for a set applied with the setting off.
- **AC-S2-18** `[E2E]` (J5b to J8b) Switch the setting on; Mei Ling uploads and submits; she cannot
  apply; Kelvin opens the notification, rejects one line with a reason, applies; the supplier's
  Prices tab shows the new cost lists. 375px and 1280px.
- **AC-S2-19** `[BE]` `[T]` (J7, J8b) Given the migration has run, then `.verify` is granted to every
  role holding `scm.proforma_invoice.upload`, and to `admin` and `superadmin`, and to no
  `integration_%` role; an API-key principal or any public route cannot decide, return or apply
  (Q6 ruling).

## S3: The supplier page

- **AC-S3-01** `[BE]` (J10) Given `procurement.suppliers.price_link`, when a link is issued, then a
  `supplier_price_links` row with a 256-bit token, `expires_at` 30 days out and
  `issued_by_user_id` is created, and any older active link for that supplier is revoked in the
  same transaction.
- **AC-S3-02** `[BE]` (J13) Given revoke (5 s deferred action, no dialog), then `revoked_at` is set;
  given an unknown, expired or revoked token, every public route returns the same 404 body.
- **AC-S3-03** `[BE]` `[T]` (J11) Given a valid token, then the public GET returns only: the
  supplier's display name, currency, and for each product linked to this supplier its code,
  description, its cost lists (price, currency, start, end, in force or not) and the last
  supplier code seen for it; never another supplier's price, `products.cost_price`, `list_price`,
  reasons or any user's name.
- **AC-S3-04** `[BE]` (J11) Given the supplier edits prices, then each save writes the supplier's
  open Draft set (created on first edit, channel `supplier_page`) with the submission's optional
  start and end dates; unedited rows are not lines.
- **AC-S3-05** `[BE]` (J11) Given the supplier uploads the Excel, then the same reader and the same
  shared engine build lines into the Draft set (channel `supplier_upload`); lines that did not
  bind are shown to the supplier as "models we do not know" and kept for Sorento to map.
- **AC-S3-06** `[BE]` (J12) Given Submit, then the set enters `pending_verification` with
  `submitted_via_link_id`, whatever the setting (AC-S2-11); the verifier may map and skip before
  deciding.
- **AC-S3-07** `[BE]` (J12) Given a supplier set is Pending, then the table is read-only; a second
  submit or a new upload returns 409.
- **AC-S3-08** `[BE]` (J12) Given History, the supplier sees each of its own sets (code, submitted
  date, validity, status, accepted count of total) and per-line accepted or rejected, never the
  reason text.
- **AC-S3-09** `[BE]` `[T]` (J11) Given more than 60 public requests a minute, or more than 10
  uploads an hour, from one token or one IP, then 429.
- **AC-S3-10** `[BE]` `[T]` (J11) Given any public write, the audit row carries actor type
  `public_link`, the link id and the recipient name, never a Sorento user id.
- **AC-S3-11** `[BE]` (J10) Opening a link updates `last_opened_at` and `open_count` (not an audit
  row per open).
- **AC-S3-12** `[FE]` (J10) The supplier record's gear menu has Share price page (permission gated)
  opening a dialog with the URL, a `QRCodeSVG`, Copy link, Save QR image and Copy message, plus the
  current link's expiry, last opened time, open count and Revoke.
- **AC-S3-13** `[FE]` (J11) The public page at `/c/{company}/supplier-prices/{token}` renders at
  375px first, Chinese first with English beneath, with a 中文 / EN toggle remembered in guarded
  `localStorage`. Tabs: 价格表 Prices, 上传Excel Upload, 记录 History.
- **AC-S3-14** `[FE]` (J11) Prices tab: a search box (model code, configuration) at the top; each
  product shows its cost lists with date ranges and an In force marker; the new price input is
  `inputmode="decimal"` at 16 px; a changed value shows its change percent; the sticky footer has
  生效日期 Valid from and 截止日期 Valid to (optional), changed and total counts, and 提交审核 Submit
  for review.
- **AC-S3-15** `[FE]` (J13) An expired or revoked link shows 链接已失效 / This link is no longer valid
  and nothing else.
- **AC-S3-16** `[BE]` (J11) Responses set `Referrer-Policy: no-referrer` and `X-Robots-Tag: noindex`;
  the token is never written to application logs.
- **AC-S3-17** `[E2E]` (J10 to J12) With the setting off, staff issue a link; a second browser
  context at 375px searches, edits two prices with a Valid from, submits; the staff list shows the
  set Pending with channel Supplier page; a verifier applies it; the supplier page's History
  shows Applied and the Prices tab shows the new cost list with its date.
- **AC-S3-18** `[FE]` (J12) History tab has a search box (set code) and an empty state
  "暂无记录 No submissions yet".

## Search on every page (owner ruling 27 Sep 00:45)

- **AC-SR-01** `[FE]` Cost price uploads list: search by set code, supplier name or file name,
  debounced, through `buildDataGridParams` (AC-S1-22).
- **AC-SR-02** `[FE]` Review page: search by supplier code, configuration, matched product code or
  sheet, combined with the active stat filter and sheet tab; the stat card counts follow the
  search (AC-S1-20).
- **AC-SR-03** `[FE]` Supplier Prices tab and product Suppliers tab: search as AC-CL-07, AC-CL-08.
- **AC-SR-04** `[FE]` Supplier's own page: search on Prices and History (AC-S3-14, AC-S3-18).
- **AC-SR-05** `[FE]` `[T]` Every single-select on these screens is `SearchableSelect` and every
  multi-select is `SearchableMultiSelect`; a test over the new files fails on a native `<select>`
  or another dropdown component.

## Audit trail (all slices, per #1281)

- **AC-AU-01** `[BE]` (J14) `product_supplier_costs`, `cost_price_change_sets`,
  `cost_price_change_lines`, `supplier_price_links` and `product_suppliers` carry
  `__audit_track__`; every create, update and delete writes old and new values.
- **AC-AU-02** `[BE]` (J14) Upload, submit, return, apply, hand edit, tick, link issue, link revoke
  and the setting change each write one named action (`COST_SET_UPLOAD`, `COST_SET_SUBMIT`,
  `COST_SET_RETURN`, `COST_SET_APPLY`, `SUPPLIER_COST_LIST_EDIT`, `SUPPLIER_COST_TICK`,
  `SUPPLIER_PRICE_LINK_ISSUE`, `SUPPLIER_PRICE_LINK_REVOKE`, `COST_VERIFICATION_SETTING`); apply
  carries verified yes or no, the dates and the list of (product code, old, new, currency).
- **AC-AU-03** `[BE]` `[T]` (J8) Given Apply, every `product_suppliers` and `product_supplier_costs`
  row it touched has an audit row with the same `trace_id` as `COST_SET_APPLY`.
- **AC-AU-04** `[FE]` (J14) The set's History tab lists those events newest first with actor, time
  (`formatDateTimeInMalaysia`) and a one-line summary, and links the source file download.

## Out of scope (named triggers in the plan, section 11)

Readers that price a day other than today, near-match suggestions or a new matching rung,
packaging variants, FX conversion into MYR, writing `products.cost_price`, a supplier login
(arrives with #1280), OTP on the supplier page, automatic WeChat sending, product creation from
an unmatched code, and multiple open sets per supplier.
