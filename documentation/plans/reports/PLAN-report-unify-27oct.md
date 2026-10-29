# PLAN: REPORT-UNIFY (finish `crm_report_ask` for every sales and outstanding ask)

Status: Review, round 6 done by the LOCAL worker (lane REPORT-UNIFY-LOCAL) on 29 Oct: reviewer READY and security CLEAN on 2839b6581c, the hand-test script re-run on the crew copy on the final code (section 7). Waiting on CI and the owner's hand test.
Track: full (size L). Three stacked slices on one lane branch, one PR (#1922).
UAC: `report-unify-27oct-acceptance-criteria.md`.

Depends on SALES-UNIFIED (#1916). Its `invoiced` basis in `services/reports/ask.py` CATALOGUE and
`billing_document_lines.ASK_DEFINITION` are the sales calculation. This lane rebases onto #1916 once it merges and
adds no second calculation. Slice 1 touches only `ask.py` / the route / one new helper, so it can start on main and
pick up `invoiced` on rebase.

## 0. Rulings (owner, 27 Oct ~19:15)

| Q | Answer | Effect |
|---|---|---|
| Q1 retire tools | (a) | Slice 2 routes every `crm_sales_report`, `crm_outstanding_report` and `crm_sales_analysis` ask to `crm_report_ask`. The MCP `crm_top_selling_report` is removed. The Yearly comparison SCREEN stays. In chat (28 Oct, after #1931 merged) the Yearly comparison is the report ask grouped by a new `year` dimension, so no chat path calls `crm_sales_analysis`; its MCP tool and route stay. |
| Q2 outstanding | **"we need to ask and clarify"** | "Outstanding" is never defaulted. Like the sales basis question, the bot asks which one is meant: **undelivered order qty** (basis `outstanding`, the open SO remainder), **pending delivery** (new basis `pending_delivery`, lines of DOs not yet delivered) or **unpaid invoices** (new basis `unpaid`, AutoCount's per-document `billing_documents.outstanding`). Folded into the one question for everything missing. |
| Q3 spec | (a) | spec filter AND `group_by=spec:<key>` |
| Q4 not applied | (a) | A "Not applied: \<filter\> (\<reason\>)" line. The bot asks instead only when that filter was the only subject. |
| Q6 access (22:52) | (a) | The route checks the **Outstanding** reveal (`sales_orders.outstanding`) for bases `outstanding` / `pending_delivery` / `unpaid` and the **Sales report** reveal (`sales_orders.sales_report`) for the sales bases. A linked contact stays limited to its own customers. No new permission. |
| Q7 salesperson scope (28 Oct 08:40) | linked customer | One rule for totals and rankings, set by the contact's linked customer (`_contact_scope.enforce_customer_scope`, called at `report_ask.py:472`). With no linked customer: ALL figures. With one: only that customer's. An ungranted live salesperson is no longer always narrowed to its own book. Assumed, flagged to the owner: "my ..." still means the own book. Outstanding kinds keep Q6: a salesperson without the Outstanding reveal stays on its own book there (security re-check, 28 Oct). |
| Q9 item and category rankings (28 Oct 10:15) | no linked customer sees everything | REPORT-SMART R1 (item / category rankings staff-only, the 403 `customer_not_permitted`) retires for a contact with no linked customer that may ask at all (a reveal, or a live salesperson), staff or not. A linked contact stays on its customers (`enforce_customer_scope`); a contact with neither reveal nor salesperson status stays refused. S1 (outstanding kinds keep Q6) stands. |
| Q10 parser only (28 Oct, owner rule restated) | semantic parser reads | The Yearly basis, company and sales agent questions are answered ONLY by the parser's declared pick of an offered option (`required_fields.picked_option`); no typed label, digit or reply length is read in code. Pre-existing rule-based reads that remain: the report ask's period, count, measure and basis fields keep the `shape_fallback` capture, and the ideation and chat report asks keep their shape capture. |
| Q11 hand test (28 Oct, crew copy on prod parser text) | trace-proven fixes | The MCP no longer requires a period for `crm_report_ask`; the route decides per basis. The outstanding kind question carries its 3 options, the kind comes only from the parser's pick, and the parser `basis` enum gains `pending_delivery` / `unpaid`. A group_by without a parser ranking marker (`rank_direction` / `top_n` / `rank_by`) is a breakdown: all rows, never "How many?". Spec values echo through `product_spec_registry.display_spec_value`. One basis question: #1931's `sales_basis_ask` 4-option question for totals and the Yearly comparison, then `crm_report_ask`. A `year` dimension on every ask definition, on each definition's own date (billing doc date, SO line bucket date, DO date, document date). `year` is also offered on unpaid and to dealers (a dealer already sees its own months, so nothing new is exposed). Totals have one layout on every basis: the report ask total. Known parser-side gaps (not lane code): a named agent sent as `group_by` ("sales agent yu total sale ..."), which needs a prompt line plus eval; "mch" needs a parser version with the span pass on. |
| Q13 owner answers (28 Oct) | owner | Supersedes Q12 on unpaid. 1(a): the chat route needs BOTH the contact's Outstanding reveal AND `finance.billing_documents.view` on the act-as user, granted by the additive migration `unpaid_0001_chatbot_ar_role` (a dedicated role, only the act-as users of `n8n` / `sorento-mcp`, only when that user is a live integration user). 2(b): unpaid is refused to anyone without the Outstanding reveal, salespeople included; undelivered orders and pending delivery keep the salesperson's own book. 3(a): the reveal is labelled "Outstanding (orders, deliveries, unpaid invoices)"; the field key `sales_orders.outstanding` is unchanged. Captain rulings in round 5: a parser `basis` among the offered kinds answers the kind question; "by X" over an outstanding frame keeps the period, a switch from a sales basis to outstanding drops it. |
| Q12 hand test 2 (28 Oct, crew copy :3107) | captain decisions, flagged to crew | The unpaid basis on the chatbot route is gated by the asking contact's Outstanding reveal, per Q6 (a) ("Unpaid invoices need the Outstanding reveal too"). The act-as finance check (security S1) is removed from the chat route. No grant for the integration user. The staff screen keeps `finance.billing_documents.view` on unpaid (B1). Question order everywhere: the required fields (basis, and the measure for a ranking) first, the company question last. A breakdown asks no measure, because every row shows qty and RM. An outstanding kind is never inferred from a held frame and uses only a period named in its own message. The six screen definitions truncate the detail at 5,000 rows (`cap="truncate"`) so the SQL summary always renders. |
| Q8 retired behaviours (28 Oct 09:30) | keep 1, retire 2 and 3 | Item 1: under an undelivered-orders answer (basis `outstanding`), the offer "Reply 1 for the sales order list" lists the open SOs behind the figure. It re-runs the SAME ask grouped by a new `sales_order` dimension on the outstanding definition, so the list is the figure's population by construction. Items 2 (sales-report drill offers) and 3 (SF-2 carried offer) retire. |
| Q5 screen | (a) | One "Sales & outstanding" report screen over the same ask definitions |

### The two new outstanding bases (Q2)

**`pending_delivery`.**
- **Rows:** the existing `services/reports/datasets/delivery_order_lines.py` (DO lines, DO date), plus the
  outstanding-DO predicate `order_service._outstanding_clause(_delivered_status_ids(db))` (`services/order_service.py:75,102`), the one
  population the old report's DO block used (`outstanding_report_service.py:448-480`, owner R11).
- **Measures:** qty = line quantity; RM = the dataset's own line amount.
- **Filters and groupings:** every filter and grouping the dataset already declares (customer, product, brand,
  category, sales agent, location, channel), plus spec.
- **No new SQL population.** It is a predicate on an existing dataset.

**`unpaid`.**
- **Rows:** `billing_documents` (`models/finance.py:62`) with `outstanding > 0`, `status` posted, not cancelled.
- **Measure:** RM = `outstanding` (as pushed, `outstanding_as_of`). Qty does not apply.
- **Filters:** customer, sales agent (document agent), customers-assigned-to, month (doc date).
- **Not applicable:** product, brand, category, spec, location and channel. Those filters print "Not applied:
  \<filter\> (unpaid invoices are per document)". A grouping by them is a 422 `unknown_group_by` at the route (the dimensions tuple). The lane answers it with the
  same Not-applied line plus the ungrouped total.

**Period on every outstanding basis.** Outstanding is "as of now", so a missing period is not asked. It means all
dates, as the old outstanding report did ("Order date: all"). A named period filters the SO / DO / document date. So
the one question asks only the outstanding kind (and the measure for a ranking).

## 1. Slice 1: engine (route + `run_ask`), red-first

Measured facts:
- The route allow-list is `api/v1/order_management/report_ask.py:58-64`. `product_ids` is capped at
  `_MAX_VALUES = 50` (:52).
- A spec set is routinely larger than 50 (P-trap WC is in the hundreds), so spec cannot travel as `product_ids`
  from the lane. It travels as spec terms and resolves **server-side**.
- `run_ask` (`services/reports/ask.py:231`) already returns qty + RM on every basis, outstanding included. The
  outstanding RM exists today; only the old outstanding tool lacks it.

Changes:
1. **Route param `spec`**, repeatable, `key:value` (e.g. `trap_type:p_trap`, `length:250`, `length:250mm`). It is
   resolved server-side by a new `services/reports/spec_set.py`:
   - **Membership** is `product_spec_search.membership_clause({key: [values]})` (`product_spec_search.py:895`), the
     exact clause the described-set path uses. It already handles string / list / yes-no values and exact JSON
     numbers. No new matching rule is added.
   - **Units:** a value with a unit is accepted only in the registry's unit (`product_spec_registry.unit`). "250mm"
     on an `mm` key is 250; another unit goes under `not_applied` with reason `unit`.
   - **Unknown key:** a key not in `product_spec_registry` goes under `not_applied` with reason `unknown_spec`.
   - **Hidden keys:** a key the contact may not see is resolved as in
     `api/v1/system/references.py:1644` `_contact_hidden_spec_keys`, through
     `spec_visibility.resolve_policy` / `hidden_keys` (moved into one shared helper in `spec_visibility`, which both
     callers use). It goes under `not_applied` with reason `hidden`.
   - The matching product ids go to `run_ask` `filters["product"]`, ANDed with any named product / code.
   - **No match:** an empty set returns zero rows with `status=no_products`, never "no filter" (`ask.py` module
     docstring rule).
2. **The two new bases** (section 0) go in `ask.CATALOGUE["sales"]` (`pending_delivery`, `unpaid`) with their own
   dimensions / filters tuples. The route's `basis` doc and allow-list follow the catalogue.
3. **`group_by=spec:<key>`.** `run_ask` runs `group_by=product` with no top-N cut, then folds the rows by each
   product's value for `<key>` (one read of `product_specifications` for the ids). Products with no value go to
   "Not stated". Ranking and the top-N cut happen after the fold. The engine kernel is unchanged.
4. **Echo.** The body echoes `filters.spec` with labels from the registry ("Trap type: P-trap") and `not_applied: [{filter,
   reason}]`.
5. **Tally tests:**
   - On every basis, for a seeded chain, the total with no grouping = the sum of rows grouped by product = the sum
     grouped by `spec:<key>` (including "Not stated").
   - Invoiced (after rebase): the `crm_report_ask` total = `invoiced_sales` = the Top selling items report total for
     the same filters.

Confirmed by SALES-UNIFIED (crew-note 6440275524 on #1922):
- The `billing_document_lines.ASK_DEFINITION` param keys are stable. `product` = `product_id IN (...)`.
- Billing lines with no CRM product drop out of a spec filter. That is the right reading.
- `location` on invoiced is 422 `location_needs_order_basis`. The lane maps it to a "Not applied: Location (invoices
  carry no warehouse)" line, never an error reply.
- The spec fold runs over product rows in Python, so it needs no new column on that dataset.

### Slice 1 contract details (pinned with the tester, 27 Oct)

- **Echo:** `filters` stays the existing list of `{key, label, values}`. A spec is one entry `key=spec` with values
  like "Trap type: P-trap".
- **`not_applied`** is a top-level list of `{filter, value, reason}`.
- **Spec group rows** are named by the value (the registry label where one exists), plus "Not stated".
  `group_by=spec:<key>` needs `top_n` like every group.
- **Malformed input:** a `spec` with no colon is 422 `invalid_spec`. `spec` on the chat dataset is 422
  `unknown_param`.
- **Period on an outstanding basis:** both dates or neither. Only one is 422 `period_required`.
- **Brand-scoped contacts on `unpaid`:** a contact limited to some brands is refused `unpaid`, with 403
  `report_dimension_not_allowed`. A billing document carries no brand, so the brand scope cannot narrow it, and the
  refusal fails closed instead of showing the unscoped total.
- **`group_by=spec:<key>` with a count measure** (customers / orders / products) is 422 `unknown_measure`, because
  distinct counts do not add across a group's products.
- **Echo with no period:** on an outstanding kind asked with no period, the body's `date_from` / `date_to` are
  `null`. The slice 2 lane prints "all dates".
- A spec set that is non-empty but has an empty intersection with `product_ids` answers `status=ok` with zero rows,
  as the existing AND does. Only a spec matching no product at all is `no_products`.

## 2. Slice 2: chatbot routing

0. **Access is kept.** An invoiced total moved onto `crm_report_ask` still needs `sales.reports.view` on the act-as
   principal (#1916 security M1, 403 `invoiced_needs_sales_reports`). The lane's existing handling of that refusal
   applies to totals and outstanding the same way.

1. `report_ask.take_words` / `hold_words` (`lanes/business/report_ask.py:445,466`) apply to every sales or
   outstanding status, not only `sales_ranking`. The gate on `ASK_NAME` becomes "any sales / outstanding status".
2. `lanes/business/__init__.py`:
   - the `crm_outstanding_report` override (:2160-2168) and the `crm_sales_report` branch (:2271-2289) send the ask
     to `crm_report_ask`: `basis=outstanding` for outstanding, no grouping for a total, the asked grouping for "by X";
   - the brand-only reroute (:2138-2151) is subsumed;
   - the `crm_sales_analysis` override goes too, except the Excel yearly-comparison file (per Q1).
3. Spec entities the parser emits (`trap_type=p_trap`) become `spec` route params, instead of falling to the
   generic gate (`gate.py:540-545`).
4. **"Not applied:" line.** Any parsed filter the route echoes under `not_applied`, or that has no route param
   (e.g. "a/c 3"), prints one line under the header. If it was the sole subject, the bot asks (Q4).
5. **A named product replaces a carried one** (P4). Carry applies only when this turn names no product.
6. **Removals:**
   - Policy rows `turn/policy_rows.py:161-170,337,382-385` drop the retired tools.
   - A migration re-seeds the `order` / `sales` rows the same way `or_r4b_top_selling_off` did.
   - The MCP catalog entry for `crm_top_selling_report` goes (`sorento_crm_mcp/sorento_crm_mcp/catalog.py:996`).
   - The analytics connector reuse goes (`services/analytics_connector/reused_tools.py:910`).

## 3. Slice 3: span binding

1. `_span_lookup` (`chatbot/engine.py:1431-1514`) keeps each match's row id and list. The candidates go to the
   parser with a stable id, and the parser's entity carries `canonical_code` = that id or label.
2. `take_words` binds the brand, sales agent, category and spec key/value straight from the candidate's row id (for
   category, today's canonical rule `report_ask.py:475-477`, generalised to every kind). The lane never re-reads the
   raw word.
3. **A sales-agent word never reaches the customer resolver.** Several agent candidates mean "Which sales agent?"
   with only the agents listed (H3).
4. **A category word never reaches the customer resolver** (P6).
5. **The salesperson candidate cap.** `head/lookup_lists.py:55` (5) is raised to the list's other caps, or the cap
   is applied after exact matches. This is decided in the slice with a test on the "yu" set.

## 3b. Slice 4: the "Sales & outstanding" screen (owner Q5 (a))

The same ask definitions, shown on screen, so staff can check the bot's number. The page is
`/sales/sales-and-outstanding`, with a sidebar entry under Sales next to Top selling items
(`sorento_crm_frontend/config/menu.config.tsx:147`).

- **No new page machinery.** The page is the existing `components/reports/ReportPage` (as `top-selling-items/page.tsx`
  and `yearly-comparison/page.tsx` use it), with line tabs, one per basis: Invoiced, Delivered, Ordered,
  Undelivered orders, Pending delivery, Unpaid invoices. A tab switches `reportKey`.
- **Backend:** the six ask definitions (`sales_order_lines_ask.DEFINITIONS`, `billing_document_lines.ASK_DEFINITION`,
  `delivery_order_lines.PENDING_DEFINITION`, `unpaid_documents.DEFINITION`) are registered with `reg.register`.
  - Their `_no_options` selects get real option lists (customers, agents, brands, categories), reusing the
    option helpers `top_selling_items.py` / `sales_by_debtor_type.py` already have.
  - Permission per definition follows Q6:
    - the order bases use `order_management.orders.view` with the Outstanding / Sales report split;
    - invoiced uses `sales.reports.view`.
- **Spec on screen:** a `spec` select param on each definition. Its condition is
  `product_id IN (spec_set ids)`, through the same `spec_set` resolution the route uses, so the figure is the same
  as the chat answer.
- **Tally test:** for one seeded world, the screen run (`POST /reports/<key>/run`) total equals the
  `crm_report_ask` total for the same basis, filters and period, on every basis.
- **Phase order:** FE mock first (the page with tabs on mocked meta), then wiring. Browser pass at 375 and 1280.

## 4. Gates

- Red-first for each slice; the touched suites stay green.
- The eval set: the owner's 4 messages, prod turns P1-P12 (card section 3) and the parser gold set, replayed against
  a seeded fixture on the lane head. A message passes when every named filter is in the header or in a "Not
  applied" line, and the grouping is the one asked.
- The AutoCount tally is #1916's `scripts/sales_unified_tally.py`, run by crew on the owner's copy for the invoiced
  basis.
- Reviewer; security-reviewer (the route gains a param on an external ingest surface, the X-API-Key route); browser
  pass; hand test.

## 5. Not in this lane

- Targets / achievement / commission, which have their own crediting rules.
- AR (unpaid invoices).
- `crm_order_analytics` (off the chatbot).
- SCM analytics.

## 6. Handoff to the local worker (28 Oct)

Owner decision: the lane moves to a local worker that can run its own chat and screen checks on the copy. The last
pushed head before the handoff checkpoint is `cb882117` (round 5 plus a clean merge of main 8e569661). The handoff
commit on top is a round 6 WIP with `[skip ci]`.

### State of each item

- **Owner answers 1(a), 2(b), 3(a): done on `cb882117`** (section 0, Q13). Route gate:
  `app/api/v1/order_management/report_ask.py` (~412-426) plus `require_unpaid_access` in
  `app/services/sales/invoiced_sales.py`. Migration: `alembic/versions/unpaid_0001_chatbot_ar_role.py`. Tests:
  `tests/test_report_unify_outstanding_bases.py`, `tests/test_report_ask_my_sales_route.py`,
  `tests/test_migration_unpaid_0001_chatbot_ar_role.py`, the label pin in `tests/chatbot/test_outstanding_lane.py`.
- **Reviewer on `cb882117`: NOT READY, one blocker (B1).** K3 (i) in `tests/chatbot/test_report_unify_parser_only.py`
  (`test_the_kind_question_is_not_answered_by_a_basis_outside_the_offered_kinds`) only asserted that no call ran with
  that basis. Mutant M6 survived: any parser basis answered the kind question, and one not offered mapped to
  option 1, so invoiced / delivered / ordered silently ran `basis=outstanding`.
- **Security on `cb882117`: no blockers; S1 should-fix.** The migration gave the role to whatever user an
  integration acts as, so a human staff user pointed at by `n8n` would gain finance view. Note for the PR body: the
  grant also opens, for the n8n / sorento-mcp keys, the external `billing_documents` / `ar_outstanding` reads, the
  billing-document list-query and document relations. That follows from owner answer 1(a). Security N5: on a DB where
  `integration_seed` and `fin_0001` ran, those users very likely hold the slug already, so the contact's reveal is
  the gate that really separates users.
- **Round 6 WIP (the handoff commit). Only the two touched files were run (62 passed). The full selection, the kill
  tests and a reviewer pass are NOT done.**
  1. B1: K3 (i) now asserts `calls == []` and that the kind is asked again. Still to do: kill-test it against M6 in
     a scratch worktree.
  2. Security S1: the assignment insert requires `u.is_integration = true AND u.is_trashed = false`. Two new
     migration tests: a human act-as user and a trashed one gain nothing.
  3. Security N7: under the kind question, a parse with a kind basis AND a subject bound this turn
     (`entities[].hint` in `_FILTER_HINTS`, `current_message` not false) becomes a fresh outstanding ask that keeps
     the subject, not a bare pick that drops it (`as_basis_answer` in
     `app/services/chatbot/lanes/business/report_ask.py`). Test:
     `test_a_kind_answer_that_also_binds_a_customer_runs_for_that_customer_never_the_whole_scope`. Check that
     `current_message` / `hint` are the right entity fields against the parser schema (`head/parser.py`).
  4. Reviewer N1: a sales basis (invoiced / delivered / ordered) under the kind question now picks nothing, so the
     kind is asked again instead of the generic "I can rank sales by ..." reply.

### Migration SQL for the dev DB (plain psql, no binds; idempotent; never touches `alembic_version`)

The crew-migration comment `6473935190` on #1922 is out of date: its assignment insert lacks the round 6 live
integration user filter. Post this version:

```sql
INSERT INTO user_permissions (id, slug, name, created_at)
SELECT gen_random_uuid()::text, 'finance.billing_documents.view', 'finance.billing_documents.view', now()
WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = 'finance.billing_documents.view');

INSERT INTO user_roles (id, slug, name, description, is_trashed, is_protected, is_default, created_at)
SELECT gen_random_uuid()::text, 'chatbot_integration_unpaid_read', 'Chatbot integration: unpaid invoices read',
       'Lets the chatbot integration read unpaid invoices (finance.billing_documents.view) and nothing else.',
       false, false, false, now()
WHERE NOT EXISTS (SELECT 1 FROM user_roles WHERE slug = 'chatbot_integration_unpaid_read');

INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
SELECT gen_random_uuid()::text, r.id, p.id, now()
FROM user_roles r, user_permissions p
WHERE r.slug = 'chatbot_integration_unpaid_read' AND p.slug = 'finance.billing_documents.view'
  AND NOT EXISTS (SELECT 1 FROM user_role_permissions x WHERE x.role_id = r.id AND x.permission_id = p.id);

INSERT INTO user_role_assignments (id, user_id, role_id, assigned_at)
SELECT gen_random_uuid()::text, u.id, r.id, now()
FROM user_roles r
JOIN users u ON u.id IN (SELECT i.act_as_user_id FROM integrations i WHERE i.name IN ('n8n', 'sorento-mcp'))
WHERE r.slug = 'chatbot_integration_unpaid_read'
  AND u.is_integration = true AND u.is_trashed = false
  AND NOT EXISTS (SELECT 1 FROM user_role_assignments a WHERE a.user_id = u.id AND a.role_id = r.id);
```

Without the `is_integration` / `is_trashed` line, this SQL ran twice cleanly under `psql -v ON_ERROR_STOP=1` in a
throwaway DB with stand-in tables. Re-check it with that line added.

### The 9 failing steps of crew hand test 2 (on `c858f429`)

Crew's hand-test report on #1922 has the step-by-step list. The fixes landed in rounds 4 and 5 by root cause, and
none has been re-run on a copy yet:

- (a) Question order: the required fields first, the company last; a breakdown asks no measure.
- (b) Reply "1" under "Reply 1 for the sales order list" opens the list (`without_pick_axis`, SO_LIST). This was
  inferred, because crew's exact parse of that turn was requested but never received.
- (c) The unpaid gate: superseded by owner answers 1(a) and 2(b).
- (d) The screen summaries stop at the 5,000-row cap: the six definitions now use `cap="truncate"`.
- (e) A fresh outstanding ask asks the kind and uses only its own period. A parser-flagged refine keeps the period on
  screen and never infers the kind. Round 5 narrowed this: "by X" over an outstanding frame keeps the period, and a
  switch from a sales basis drops it.

### Next steps, in order

1. Run the full selection on the WIP tree, every group: route / screen / kernel / yearly / migration,
   `tests/chatbot/test_picker_*.py`, chatbot report / sales / ranking / ledger / so_list / doc_scope /
   required_fields / outstanding / reveals, replay / ideation / low-stock, and MCP with `PYTHONPATH`. Kill-test items
   1-3 above, with mutations only in a scratch worktree.
2. Commit the result without `[skip ci]`, with the pre-push hook running normally (no `SKIP_PREPUSH`).
3. Post the corrected crew-migration block above. Crew re-applies it.
4. Reviewer plus security re-check on that head. Then merge main if it moved and run `./scripts/alembic-reparent.sh`
   (single head `unpaid_0001_chatbot_ar_role`). Then post `ci-ready head <sha>`.
5. On the local copy, with the migration SQL applied: re-run the 18-step crew hand-test script (the latest
   `crew-handtest` comment on #1922), plus the 9 steps that failed in hand test 2. Do the browser pass for the
   "Sales & outstanding" screen at 375px and 1280px.
6. Still open with crew / owner:
   - the parser prompt line for "sales agent yu total sale ..." (crew-ask 6461889733; needs a Gemini eval);
   - the exact parse of the sales-order-list "1" turn;
   - the reveal holder list for the owner (query in crew-note 6471441550; results go to the owner, not the PR).
7. Before ready: add to the PR body the extra reads the grant opens for the n8n / sorento-mcp keys (security note
   above), and that the chatbot path is parser-only.

## 7. Round 6 outcome (local worker, 29 Oct)

Every fix below went red-first (a `test(red):` commit touching only tests, then the fix) and was kill-tested in a
scratch worktree (each mutant red, restored green).

| Item | Red | Fix |
|---|---|---|
| Reviewer B1 (K3 (i) guard), security S1 (live integration user), N7 (subject on a kind answer), N1 | 9ba1e65a54 (cloud) | 9ba1e65a54 |
| Regression found by the full selection: a refine over a frame already on an outstanding kind re-asked the kind | existing samantha r3 test | c2c7ba490c |
| B2: a sales basis under the kind question swallowed a whole new sales ask; B4: a position pick dropped a subject | 10f6656e32 | ba5297c6df |
| B5: the declared pick / cancel must win over positions; P3: the parser's offered-kind basis beats a position | a9b7f7e9de | a057c424db |
| Declared fill naming a kind keeps a subject (P7) | a8948bf915 | 172749ce04 |
| Copy step 20: a declared fill with its own sales ask; copy step 14: an agent word beside a document; copy step 13 seam | 8cc3ccf21f | 1e054c169b |
| Copy step 13: the document/status projection replaced the seam's sales_ranking | 10f6ba507b | 14b2f8bc3d |
| B6: the step-14 exception dropped a brand from a plain SO list | 64312877cd | 8075f21128 |
| B7: the live parse sends by_words null beside group_by | 5587f5fc50 | 1724cd3cfd |
| Copy step 8 on the final code: a company answer's guessed group_by (no by_words) replaced the held axis | 408c88d00b | 2839b6581c |

Copy run (crew copy :3104 on sorento_prod_1020, parser v189 on Gemini flash-lite, console route with the session
carried turn to turn; steps 1-13 re-run on the final code): steps 1-8, 10-20 PASS; 11 and 17 partly ENV (the billing tables are empty, so unpaid and
invoiced read RM 0.00). Step 9 in sequence (bare "outstanding" right after a delivered total) runs Undelivered orders
for the held company and year: the parser itself emits `basis: outstanding`, `ranking_refine: true` and the year's
dates for that message, and no parser field says whether the basis or the dates were read off this message, so the
engine cannot tell it from a named kind without reading text (Q10). In a new conversation it asks the kind. This is
parser-side (a prompt line, with a Gemini eval), not lane code.

The 14 `test_replay.py` full-corpus failures are pre-existing: the same 14 fail on origin/main when
`CHATBOT_FIXTURES_DIR` points at the n8n corpus (gate text drift, `gate.py:1051`); CI has no corpus and skips them.

Open after this round:
- reviewer note (not blocking): the company seam drops a `group_by` when the answer carries no `by_words`; a
  parser that omits `by_words` on "Mocha, by month" would lose the month split there.
- reviewer should-fix (not blocking): the step-14 exception reads the parser's raw `group_by`; a guessed
  `group_by: brand` on a plain "my sales orders for <brand>" would drop the brand again. No live parse shows it.
- the parser prompt line for step 9 (bare "outstanding" after a sales total) and for a named agent sent as `group_by`;
- the stray `projects.projects.view` on the dedicated role on the shared dev DB (not from this lane; DELETE held for
  the owner, PR comment 6476434849);
- the unpaid chat total still prints "0 pcs" and the screen's unpaid empty state reads "01/01/1900 to 31/12/2200":
  cosmetic, not changed in this round.
