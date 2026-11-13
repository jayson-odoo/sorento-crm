# PLAN: After-sales P2, warranty (is this covered?)

Status: build, owner answers in (Q0 a, Q1 a, Q2 a, Q3 b, Q4 a). Backend green-up in progress; frontend next.
Track: L (new tables, migration, new screens, new permissions). Lane AFTER-SALES-REVIVE, slice P2, branch
`claude/after-sales-p2-warranty-engine` from main fc9c5a2977 (P1 merged as #2365), new PR titled
"AFTER-SALES-P2: warranty". Supersedes the earlier P2 draft PR #2374, which was based on pre-P1 main.

Owner inputs:
- 12 Nov: slices P1 to P4 as reviewed. Decision 3: CS enters the purchase date and the product kind (and here
  the defect) by hand.
- 12 Nov ~20:49, binding: "The after sales shouldn't affect how our current complaints work ... I want to not
  affect what's live now for the complaint." So the v1 design (warranty fields on complaint product lines and
  a Warranty card on the complaint page) is withdrawn.
- Open question 0 (crew-ask on #2374, 12 Nov): where the check lives, (a) on the service job or (b) a
  separate warranty-check record. Mock v2 is built on the recommendation, (a).

Ported from PR #163 slices S2 (the entitlement engine and the Policy v15 seed) and S7b (the configuration
screens).

## Journey

A customer reports a fault and CS opens a service job for it (P1). On the job, CS adds the product(s) with the
problem, and for each enters what it is, when it was bought and what is wrong:
- product code (catalogue, searchable);
- kind (suggested from the code by the rules);
- purchase date;
- defect.

The job's Warranty card then shows one answer per covered part, with the reason. For example:
- Ceramic body: Covered (lifetime)
- Flushing fittings: Expired 14/03/2025

CS sends the technician knowing whether the visit is under warranty.

An admin keeps the policy up to date under After-Sales Service > Warranty Configuration:
- **Policies:** versions and their dates in force.
- **Kinds:** the product types the policy names.
- **Rules:** which products are which kind, with a rule tester.

Nothing on the Complaints module changes. No complaint table gets a column, and no complaint screen shows
warranty.

## Simplest-thing decisions

| #163 | P2 | Trigger to add it back |
|---|---|---|
| `warranty_assessments` table (stored verdicts, CS confirmation) | Verdicts are computed when read: the engine is deterministic and its inputs live on the job line | CS must sign off a verdict, or a report needs verdicts frozen in time (S9) |
| Purchase date from the consumer ledger | `service_job_products.purchase_date`, entered by CS | P3 links a job line to a consumer purchase; the line's own date stays as the fallback |
| Registration bonus months (clause 26) | Not applied | P3 (registration records) |
| Warranty on complaint product lines | On the service job's own product lines (owner ruling) | - |
| Separate `warranty` module | Part of the `after_sales` module (P1) with its own permissions | A tenant needs warranty without service jobs |

## Rules (from #163's engine, unchanged)

1. One verdict per policy term for the line's kind. A water closet has three terms, so it gets three answers.
2. The policy used is the one in force on the **purchase date**, never today's. If no policy covers that date,
   the answer is Unknown ("no policy in force on dd/mm/yyyy").
3. The verdicts are:
   - **Covered:** up to and including the expiry date.
   - **Expired.**
   - **Defect not covered:** the term lists defects and this one is not among them.
   - **No term:** the policy says nothing about this kind.
   - **Unknown:** the purchase date, kind or defect is missing, and the answer names which one. An Unknown
     is never shown as "not covered".
4. Dates:
   - The purchase date and the expiry date are both covered.
   - Months add with clamping: 31/01 + 1 month = 29/02.
   - Lifetime has no expiry.
5. Defects:
   - A term with no defect list covers all defects.
   - A restricted term with no defect stated gives Unknown ("defect not stated").
6. Kind:
   - The product code, category and name are matched against the kind rules (series, model list, category,
     code prefix).
   - When several rules match, the winner is decided by priority, then match specificity, then the longest
     match, then the kind code.
   - CS can override the suggested kind on the line, and the override is kept.
7. Policies and kinds:
   - Policy windows may not overlap within a company.
   - Supersede closes the old version the day before the new one starts, in one save, and shows both date
     ranges before saving.
   - A term is either lifetime or a number of months, never both.
   - A kind used by a term, a rule or a job line cannot be deleted; it can be archived.
8. Clause 17 (residential only) is not enforced.
9. Policy v15 (31 kinds, 41 terms, 2 kind rules) is seeded from #163's `scripts/seed_warranty_policy_v15.py`
   and its source text. It is backdated to 01/01/2000 and open-ended (2 Aug ruling in that seed).

## Screens

- **Service job page (P1), Details tab:**
  - **A "Products" card,** one line per product: Product code, Description, Kind, Purchase date, Defect.
    - Lines are added, edited and removed in a centred dialog (Add product, Edit), with the dialog's main
      button always in view (P1 round 7b).
    - Remove is the right-click menu with the countdown.
    - Kind is prefilled from the rules and can be changed.
    - Product is a searchable catalogue picker; there are no free-text lines.
  - **A "Warranty" card,** one line per product and term: Product, Part, Answer pill, Until (dd/mm/yyyy or
    "-"), Reason.
    - Empty state: heading + hint, no button.
- **Service Jobs list (P1):** one new column, "Warranty", with one pill per job:
  - Covered: every answer is Covered.
  - Partly covered: some answers are.
  - Not covered.
  - Unknown.
  - "-" when the job has no products.

  It is sortable, filterable (multi-select) and hideable like every column.
- **Warranty Configuration:** sidebar After-Sales Service > Warranty Configuration; one page, three line tabs.
  - **Policies tab:**
    - A DataGrid with columns Version, In force from, In force to, Status pill, Terms.
    - "Create" opens the dialog; Edit uses the same dialog.
    - The right-click menu offers Edit, Supersede and Delete (countdown).
  - **Policy page:**
    - Header: version + status pill, the pager, one main button (Supersede).
    - Tabs:
      - Details: period, policy text.
      - Terms: grouped by kind, one line per term: Part, Cover, Defects, Installation.
      - History.
  - **Kinds tab:**
    - A DataGrid with columns Kind, Code, Rules, Terms, Active.
    - A count pill, "29 of 31 kinds have no rule", which filters the grid.
    - The right-click menu offers Edit, Archive and Delete (only when unused).
  - **Rules tab:**
    - A DataGrid with columns Kind, Match, Value, Priority, and a multi-select Kind filter.
    - "Test a product" opens a dialog showing the kind a product lands in and the rule that decided it.

## Design lessons applied

These are the same lessons the P1 plan lists:
- one filled main button;
- centred dialogs with the footer always in view;
- one line per row, one value per column, right-click menus;
- dd/mm/yyyy and the shared DatePicker;
- History through the shared AuditTrail;
- plain states;
- catalogue products only;
- reuse of DataGrid, `DataGridListToolbar`, multi-select filters, `PageHeader`, `RecordNavigation`,
  `DeferredActionButton` and `SearchableSelect`.

## Data (one additive migration on main's head after P1)

- New tables, copied from #163 `317_warranty_engine.py` + `331_warranty_config.py` (uuid ids, company-scoped):
  - `warranty_product_kinds`
  - `warranty_kind_rules`
  - `warranty_policies`
  - `warranty_terms`
- New table `service_job_products`:
  - `id`
  - `service_job_id` (FK, cascade)
  - `product_id` (FK products)
  - `kind_id` (nullable FK)
  - `purchase_date` (nullable date)
  - `defect_type` (nullable lookup value)
  - `sort_order`
  - timestamps
- No complaint table is touched. The P1 guard test `test_after_sales_does_not_touch_complaints.py` keeps
  pinning that.
- Seeds, all idempotent:
  - no new permission (owner Q1 = admins only, Q2 = service-job viewers); was: `after_sales.warranty.view` / `.manage`, granted to the roles that hold
    `after_sales.service_jobs.view` / admin;
  - the defect-type lookup set (crack, leak, rust, broken holder);
  - the v15 policy.

## API

- Ported from #163 `app/api/v1/warranty/*.py`, moved under `/api/v1/after-sales/warranty/{policies,kinds,kind-rules,...}`.
- Adapted to main's list conventions: server sort, filter and search, and column config.
- Job lines: `/api/v1/after-sales/service-jobs/{id}/products` (list, add, edit, remove).
- The job GET carries `warranty`, the computed verdicts per line.
- The jobs list carries the summary.

## Questions (answered 13 Nov ~17:05: Q0 a, Q1 a admins only, Q2 a, Q3 b no guessing, Q4 a)

0. Where the check lives:
   - (a) on the service job (this plan, mock v2);
   - (b) a separate warranty-check record.

   Recommendation: (a). One record per case.
1. Who edits the policy, kinds and rules?
   - (a) admins only;
   - (b) admins + an `after_sales.warranty.manage` permission that can be granted to a CS lead.

   Recommendation: (b).
2. Who sees the Warranty card?
   - (a) everyone who can view service jobs;
   - (b) only `after_sales.warranty.view` holders.

   Recommendation: (a).
3. The 29 kinds with no product rule:
   - (a) the lane guesses rules from categories;
   - (b) ops maps them on the Rules tab after the PR, with the tester.

   Recommendation: (b). A guessed mapping gives wrong answers with confidence.

## Phases

1. Plan + UAC + mock v2. The owner approves the mock.
2. Tester: red tests (port #163's 79-test engine net and its config tests, adapted).
3. Coder: green.
4. Reviewer + security-reviewer + browser passes.
5. Hand test (`laneboard/scripts/2374.md`), then freeze.
