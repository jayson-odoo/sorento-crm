# PLAN: After-sales P2, warranty (is this covered?)

Status: plan + mock, waiting for owner approval of the mock. No code. Track: L (new tables, migration, new
screens, new permissions). Lane AFTER-SALES-REVIVE, slice P2, own branch `claude/after-sales-p2-warranty`
and own PR, titled "AFTER-SALES-P2: warranty".

Owner go: 12 Nov 2026 (slices P1 to P4 as reviewed; decision 3: CS enters the purchase date and product kind
on a complaint line). Review page: `documentation/plans/after-sales/review/index.html` on PR #2365.
Ported from PR #163 slices S2 (the entitlement engine and the Policy v15 seed) and S7b (the configuration
screens).

## Journey

A customer reports a fault. On the complaint, CS opens a product line and enters (or confirms) two things:
when it was bought, and what kind of product it is. The kind is suggested from the product code by the
rules. The complaint then shows a Warranty panel with one answer per covered part, e.g.:

- Ceramic body: Covered (lifetime)
- Flushing fittings: Expired 14/03/2025

Each answer comes with the reason. An admin keeps the policy up to date under Warranty Configuration:
- Policies: versions and their dates in force.
- Kinds: the product types the policy names.
- Rules: which products are which kind, with a rule tester.

## Simplest-thing decisions (what #163 had and P2 leaves out)

| #163 | P2 | Trigger to add it back |
|---|---|---|
| `warranty_assessments` table (stored verdicts, CS confirmation) | Verdicts are computed when read: the engine is deterministic, and the inputs live on the line | CS must sign off a verdict, or a report needs verdicts frozen in time (S9) |
| Purchase date from the consumer ledger (`consumer_purchase_lines`) | `complaint_product_lines.purchase_date` + `kind_id` + `defect_type`, entered by CS | P3 (the consumer ledger) links a line to a purchase; the line's own fields stay as the fallback |
| Registration bonus months (clause 26) | Not applied (no registration record exists without P3) | P3 |
| Separate `warranty` and `consumers` modules | One `warranty` module key for the screens and permissions | P3 adds `consumers` |

## Rules (from #163's engine, unchanged)

1. One verdict per policy term for the line's kind. A water closet has three terms, so it gets three answers.
2. The policy used is the one in force on the **purchase date**, never today's. If no policy covers that date,
   the answer is Unknown ("no policy in force on dd/mm/yyyy").
3. Verdicts:
   - Covered: up to and including the expiry date.
   - Expired.
   - Defect not covered: the term lists defects, and this one is not among them.
   - No term: the policy says nothing about this kind.
   - Unknown: the purchase date or the kind is missing. Each Unknown names what is missing. An Unknown is
     never shown as "not covered".
4. Dates:
   - The purchase date and the expiry date are both covered.
   - Months add with clamping: 31/01 + 1 month = 29/02.
   - Lifetime has no expiry.
5. Defect scope:
   - A term with no defect list covers all defects.
   - A restricted term with no defect stated on the line gives Unknown ("defect not stated").
6. Kind from rules. The product code, category and name are matched against the kind rules (series, model
   list, category, code prefix). The winner is decided in this order: priority, then match specificity, then
   longest match, then kind code. CS can override the suggested kind on the line, and the override is kept.
7. Policy windows:
   - Windows may not overlap within a company.
   - Supersede closes the old version the day before the new one starts, in one save, and the dialog shows
     both date ranges before saving.
   - A term is lifetime XOR a number of months.
   - A kind that is used by a term, a rule or a complaint line cannot be deleted; it can be archived.
8. Clause 17 (residential only) is not enforced.
9. Policy v15 (31 kinds, 41 terms, 2 kind rules) is seeded from #163's
   `scripts/seed_warranty_policy_v15.py` and its source text. v15 is backdated to 01/01/2000 and open-ended,
   per the 2 Aug ruling recorded in that seed.

## Screens

- **Warranty Configuration** (sidebar: Complaints > Warranty Configuration; one page, three line tabs).
  - **Policies tab:** a DataGrid with columns Version, In force from, In force to, Status pill, Terms. Create
    opens a dialog (Edit uses the same dialog). Right-click offers Edit, Supersede, Delete (countdown).
  - **Policy page** (`/warranty/policies/{id}`):
    - Header: version + status pill, a pager, and one main button (Supersede).
    - Tabs: Details (period, policy text) | Terms (grouped by kind, one line per term: Part, Cover,
      Defects, Installation) | History.
    - Term create and edit use one dialog.
  - **Kinds tab:**
    - A DataGrid with columns Kind, Code, Rules, Terms, Active.
    - A count pill above it: "29 of 31 kinds have no rule". Clicking the pill filters the grid to those kinds.
    - Right-click offers Edit, Archive and Delete (countdown, only when unused).
  - **Rules tab:**
    - A DataGrid with columns Kind, Match, Value, Priority. Kind is a multi-select filter.
    - A "Test a product" button opens a centred dialog: type or pick a product, then see the kind it lands
      in and the deciding rule.
- **Complaint detail, product lines:**
  - Each line shows two values: Purchase date (dd/mm/yyyy or "-") and Kind (name or "-").
  - Both are edited in the complaint's edit form, in the same place, so View = Edit. The kind is a
    searchable select, prefilled with the rule's suggestion, and the hint "suggested from the product code"
    stays off the screen.
- **Complaint detail, Warranty card:**
  - One line per line-and-term: Product, Part, Answer pill, Until, Reason.
  - With no product lines, the card shows a heading + hint and no button.
- The free-text "Within warranty" field on the complaint stays as it is. Removing it is an owner call (Q2).

## Design lessons applied

The lessons are the same ones the P1 plan lists:
- one filled main button;
- dialogs for create, edit, supersede and test;
- one line per row with right-click menus;
- dd/mm/yyyy and the shared DatePicker;
- the shared AuditTrail as History;
- plain states;
- reuse of DataGrid, `DataGridListToolbar`, multi-select filters, `PageHeader`, `RecordNavigation`,
  `DeferredActionButton` and `SearchableSelect`.

#163's August screens broke the following, and P2 fixes each of them:
- row icon buttons
- AlertDialog deletes
- "01 Jan 2000" dates
- native date inputs
- hand-rolled headers
- no History tab

## Data (one additive migration on main's head)

- New tables, copied from #163 `317_warranty_engine.py` + `331_warranty_config.py`, ids uuid, company
  scoping as in #163:
  - `warranty_product_kinds`
  - `warranty_kind_rules`
  - `warranty_policies`
  - `warranty_terms`
- New columns on `complaint_product_lines`, all nullable:
  - `purchase_date` date
  - `kind_id` FK
  - `defect_type` (a lookup option value)
- Seeds: the warranty permissions `warranty.policies.view` / `.manage` and `warranty.kinds.view` / `.manage`,
  granted to admin. CS roles get view through the complaints view grant (Q3). The defect-type lookup set
  (crack, leak, rust, broken holder) is seeded too. The v15 policy goes through the seed script, run from the
  migration, idempotently.

## API

- Ported from #163 `app/api/v1/warranty/*.py`: `/api/v1/warranty-management/{policies,kinds,kind-rules,...}`.
- Adapted to main's list conventions: server sort, filter and search, and the `list_query` column config.
- Complaint GET carries `warranty` (the computed verdicts per line).
- The complaint line update accepts `purchase_date`, `kind_id` and `defect_type`.

## Questions (crew-ask with the mock)

1. Who edits the policy, kinds and rules?
   - (a) admins only;
   - (b) admins + a new "warranty manager" permission that can be granted to a CS lead.

   Recommendation: (b). It is the same permission pair, just grantable.
2. The old free-text "Within warranty" field:
   - (a) keep it as it is;
   - (b) hide it once a line has a computed verdict;
   - (c) remove it.

   Recommendation: (a) for P2, decided after the hand test.
3. Who sees the Warranty card on a complaint?
   - (a) everyone who can view the complaint;
   - (b) only holders of the warranty view permission.

   Recommendation: (a). CS needs it on every complaint.
4. The 29 kinds with no product rule (data work):
   - (a) the lane seeds rules from product categories where a category clearly maps to a kind, and lists
     the rest for ops;
   - (b) ops maps them all on the Rules tab after the PR.

   Recommendation: (b), with the rule tester. A guessed mapping gives wrong verdicts with confidence.

## Phases

1. This plan + UAC + mock. The owner approves the mock.
2. Tester: red tests (port #163's 79-test engine net and its config tests, adapted).
3. Coder: green.
4. Reviewer + security-reviewer + browser passes.
5. Hand test (`laneboard/scripts/<PR>.md`), then freeze.
