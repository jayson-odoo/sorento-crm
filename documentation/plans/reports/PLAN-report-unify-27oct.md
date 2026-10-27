# PLAN: REPORT-UNIFY (finish `crm_report_ask` for every sales and outstanding ask)

Status: Build (slice 1 engine, red-first). The owner answered the card on 27 Oct ~19:15 (section 0).
Track: full (size L). Three stacked slices on one lane branch, one PR (#1922).
UAC: `report-unify-27oct-acceptance-criteria.md`.

Depends on SALES-UNIFIED (#1916). Its `invoiced` basis in `services/reports/ask.py` CATALOGUE and
`billing_document_lines.ASK_DEFINITION` are the sales calculation. This lane rebases onto #1916 once it merges and
adds no second calculation. Slice 1 touches only `ask.py` / the route / one new helper, so it can start on main and
pick up `invoiced` on rebase.

## 0. Rulings (owner, 27 Oct ~19:15)

| Q | Answer | Effect |
|---|---|---|
| Q1 retire tools | (a) | Slice 2 routes every `crm_sales_report`, `crm_outstanding_report` and `crm_sales_analysis` ask to `crm_report_ask`. The MCP `crm_top_selling_report` is removed. The Yearly comparison stays a screen. |
| Q2 outstanding | **"we need to ask and clarify"** | "Outstanding" is never defaulted. Like the sales basis question, the bot asks which one is meant: **undelivered order qty** (basis `outstanding`, the open SO remainder), **pending delivery** (new basis `pending_delivery`, lines of DOs not yet delivered) or **unpaid invoices** (new basis `unpaid`, AutoCount's per-document `billing_documents.outstanding`). Folded into the one question for everything missing. |
| Q3 spec | (a) | spec filter AND `group_by=spec:<key>` |
| Q4 not applied | (a) | A "Not applied: \<filter\> (\<reason\>)" line. The bot asks instead only when that filter was the only subject. |
| Q5 screen | (a) | One "Sales & outstanding" report screen over the same ask definitions |

### The two new outstanding bases (Q2)

**`pending_delivery`.**
- **Rows:** the existing `services/reports/datasets/delivery_order_lines.py` (DO lines, DO date), plus the
  outstanding-DO predicate `outstanding_report_service._outstanding_clause(_delivered_status_ids(db))`, the one
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
  \<filter\> (unpaid invoices are per document)". A grouping by them is answered with the same line and the total.

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
1. **Route param `spec`**, repeatable, `key:value` (e.g. `trap_type:p_trap`, `length:250mm`). It is resolved
   server-side to product ids by a new `services/reports/spec_set.py::product_ids_for_specs(db, specs,
   hidden_keys)`:
   - **String / bool values:** the membership clause `product_spec_search.filter_specs(specs=...)` builds. This is
     the same membership "any P-trap WC?" uses (`product_predicate_service.resolve_product_set`).
   - **Numeric values:** exact equality on `product_specifications.values[key].value`, after unit normalisation
     from `product_spec_registry`. `filter_specs` drops a numeric value from membership (:989-993). A report must
     not, so this is the one rule added.
   - **Hidden keys:** a key the contact may not see is not applied and is echoed under `not_applied`.
   - The resolved ids go to `run_ask` `filters["product"]`, ANDed with any named product / code.
   - **No match:** an empty set returns zero rows, never "no filter" (`ask.py` module docstring rule), with
     `status=no_products`.
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
