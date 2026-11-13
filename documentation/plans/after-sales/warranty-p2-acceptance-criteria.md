# UAC: After-sales P2, warranty (is this covered?)

Plan: `PLAN-warranty-p2-12nov.md`. Card: `CARD-warranty-p2-13nov.md`. Mock v2 (approved 13 Nov 16:29 MYT):
`documentation/mockups/after-sales-p2/index.html`.
Status: build. Owner answers 13 Nov ~17:05: Q1 (a) admins only, Q2 (a) every service-job viewer, Q3 (b) no guessed rules, nothing automatic.
Dates in examples are dd/mm/yyyy. "Today" is MYT (`warranty_today()`).

Decided (crew, 13 Nov 16:30, from rulings): Q0 = the warranty lines live on the service job; nothing on the
Complaints module changes. Q4 = `products.warranty_months` is left alone; the policy is the only source.

## E. Engine (pure; ported from #163 `app/services/warranty_service.py` and `tests/test_warranty_engine.py`)

- **E1.** A line gets one verdict per term of its kind in the policy in force. A kind with 3 terms gives 3
  verdicts, in the terms' order (sort order, then part name).
- **E2.** The policy is the company's one whose window holds the **purchase date** (`effective_from <=
  purchase_date <= effective_to`, open-ended `effective_to` = no end). Not today's. None holds it: one
  Unknown verdict, reason "No policy in force on dd/mm/yyyy".
- **E3.** Verdict values: `covered`, `expired`, `defect_not_covered`, `no_term`, `unknown`. A kind with no
  term in the policy gives one `no_term` verdict.
- **E4.** Expiry = purchase date + N months, clamped to the month's last day (31/01/2024 + 1 month =
  29/02/2024; 31/01/2023 + 1 month = 28/02/2023). Covered while today <= expiry (the expiry day is covered).
  Today > expiry: `expired`, with the expiry date. Lifetime: `covered`, no expiry.
- **E5.** A term whose defect list is NULL or empty covers every defect. A term with a list: line defect in
  the list -> judged by date; line defect not in the list -> `defect_not_covered`; no defect on the line ->
  `unknown`, reason "Defect not stated".
- **E6.** Missing inputs give `unknown` naming the missing one, never `expired` or `defect_not_covered`:
  no purchase date -> "Purchase date not entered"; no kind (none picked by CS and no configured rule matches) -> "No warranty rule for this product yet" (owner Q3: say it plainly, never guess).
- **E7.** Each verdict carries: part name, verdict, expiry (or null), reason text (e.g. "5 years from
  15/03/2020", "Lifetime cover"), is_lifetime, installation_included, policy version.
- **E8.** Clause 17 (residential only) and registration bonus months are not applied.

## K. Kind suggestion (ported from #163 `rank_kind_matches` / `resolve_kind`)

- **K1.** Rule match types: `series`, `model_list`, `category`, `code_prefix`, matched against the product's
  code, category code and name, case-insensitive.
- **K2.** Several matches: highest priority wins, then the more specific match type, then the longest matched
  value, then the kind code (stable).
- **K3.** Only active kinds are suggested. No match: no suggestion (null).
- **K4.** A rule tester call (`product_id`) returns the winning kind and the rule that decided it, or none.

## C. Configuration (ported from #163 `warranty_config_service.py`, tests `test_warranty_config_*`)

- **C1.** Policies: create / edit / delete; within a company two policy windows may not overlap (409 with a
  message naming the other version and its dates). `effective_to` before `effective_from` is 422.
- **C2.** Supersede: one call takes the new version + start date; it sets the old policy's `effective_to` to
  the day before and creates the new one in one transaction. A start date on or before the old one's
  `effective_from` is 422. A closed policy (has `effective_to`) cannot be superseded (409).
- **C3.** Terms: a term is lifetime OR has `duration_months` >= 1, never both and never neither (422).
  Defect ids must belong to the defect-type set (422 otherwise).
- **C4.** Kinds: code unique (409). A kind used by a term, a rule or a job product line cannot be deleted
  (409, message names the use); it can be archived (`is_active = false`) and restored.
- **C5.** Rules: create / edit / delete; `match_type` in K1's list (422 otherwise); `match_value` not blank.
- **C6.** Lists (policies, kinds, rules) are server-side paginated, searchable and sortable on every shown
  column, with multi-select filters (rules: kind; kinds: active, "has no rule"). Kinds list returns per row
  the rule count and term count. Responses never carry other companies' rows.
- **C7.** Every create, edit, delete, archive and supersede writes an audit row, so the record's History tab
  (shared AuditTrail) shows it.

## J. Job product lines (new table `service_job_products`)

- **J1.** `GET|POST /api/v1/after-sales/service-jobs/{id}/products`, `PATCH|DELETE .../products/{line_id}`.
  A line: product (required, an existing catalogue product of the job's company), kind (optional),
  purchase date (optional), defect (optional, an option of the defect-type set).
- **J2.** No free-text product: missing or unknown `product_id` is 422.
- **J3.** A purchase date after today is 422 ("Purchase date cannot be in the future").
- **J4.** Kind not sent on create: the K suggestion is stored. Kind sent (CS override): it is kept, and a later
  edit that does not send kind does not re-suggest over it.
- **J5.** The same product may be on two lines of one job (two units).
- **J6.** An archived kind cannot be set on a new line or changed to (422); a line that already has it keeps it
  and its verdicts.
- **J7.** Deleting a job deletes its lines (cascade). Line delete is a hard delete.
- **J8.** The job GET carries `warranty`: per line, the line's fields (product code + name, kind name,
  purchase date, defect label) and its E verdicts, computed at read time (nothing stored).
- **J9.** The jobs list carries one `warranty_summary` per job: `covered` (all verdicts covered),
  `partly_covered` (some), `not_covered` (none covered and at least one expired / defect_not_covered /
  no_term), `unknown` (none covered and only unknowns), null (no lines). Sortable and multi-select
  filterable on the server.
- **J10.** Line adds, edits and removes write audit rows that show on the job's History.

## S. Seed and data

- **S1.** One additive migration on main's head: `warranty_product_kinds`, `warranty_kind_rules`,
  `warranty_policies`, `warranty_terms`, `service_job_products` (uuid ids, company-scoped where #163 was).
  No complaint table is altered.
- **S2.** Idempotent seed: the `after_sales_defect_type` lookup set (Crack line, Leakage, Rust, Broken holder,
  plus #163's v15 list), and Policy v15 from #163 `seed_warranty_policy_v15.py`: 31 kinds, 41 terms, 2 kind
  rules, `effective_from` 01/01/2000, open-ended. Running it twice changes nothing.
- **S3.** No guessed kind rules: the seed carries only #163's 2 rules; nothing derives a kind from a category on its own. Ops maps the other 29 kinds on the Rules tab.

## G. Guards

- **G1.** `tests/test_after_sales_does_not_touch_complaints.py` stays green unchanged.
- **G2.** `tests/test_schema_uuid_id_principle.py` and `tests/test_list_pagination_limit.py` stay green with
  the new tables and lists.

## P. Permissions (owner Q1 = a, Q2 = a)

- **P1.** Only admins (role `admin` or `superadmin`) create, edit, delete, archive or supersede policies,
  terms, kinds and rules, and use nothing else: no warranty-manager permission exists. A non-admin gets 403
  on every configuration write. Configuration reads (lists, policy page, rule tester) need
  `after_sales.service_jobs.view` (or admin). The Warranty Configuration menu item shows for admins only.
- **P2.** Every `after_sales.service_jobs.view` holder sees the Warranty card, the job `warranty` field and
  the list column; no extra permission.
- **P3.** Writing job lines needs `after_sales.service_jobs.dispatch` (same as editing the job, P1 N5).

## F. Frontend (mock v2)

- **F1.** Job page Details tab: Products card (Product code, Description, Kind, Purchase date, Defect; one
  line per row; Add product dialog; right-click Edit / Remove with countdown) and Warranty card (Product,
  Part, Answer pill, Until, Reason); empty states heading + hint.
- **F2.** Jobs list: Warranty column (pill), sortable, multi-select filter, hideable.
- **F3.** After-Sales Service > Warranty Configuration: Policies / Kinds / Rules line tabs, policy page with
  Details / Terms / History, Supersede dialog showing both versions' dates, "N of M kinds have no rule" pill,
  "Test a product" dialog. Dates dd/mm/yyyy via the shared DatePicker.
