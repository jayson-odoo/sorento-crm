# CARD: REPORT-UNIFY (finish the report engine for every sales and outstanding ask)

Status: Plan. Behaviour card posted as one crew-ask on PR #1922. No code until the owner answers. Track: full (size L).

## The owner's question in one line

"I thought we already have a unified reporting engine?" **Yes, for rankings only.** Since 23 Oct every *ranking*
("top selling", "top customer", "top agent") goes through `crm_report_ask`. Three other kinds of ask still go to
older tools with their own SQL:
- a **total** for one customer or one product goes to `crm_sales_report`;
- any **outstanding** ask goes to `crm_outstanding_report`;
- a **channel or month breakdown** goes to `crm_sales_analysis`.

None of these tools, nor the engine, can filter by **spec**. This lane moves those three kinds of ask into the same
engine and adds the missing filters. It builds no new engine.

## 1. Inventory: who answers what today (main at e191202c, plus #1916 where noted)

Paths in `sorento_crm_backend/app/` unless marked otherwise.

| Ask (example) | Chatbot picks | Picked at | SQL | Basis / date | Filters | Groupings |
|---|---|---|---|---|---|---|
| "top 10 selling sorento wc 2026" | `crm_report_ask` | `services/chatbot/lanes/business/__init__.py` `sales_ranking` override; `report_ask.ASK_NAME` `lanes/business/report_ask.py:31` | `services/reports/ask.py:231` `run_ask` over `services/reports/datasets/sales_order_lines_ask.py` (+ `billing_document_lines` for **invoiced**, #1916) | ordered / delivered / outstanding by line required date, else SO date (`services/sales_report_service.py:193-197`); invoiced by DocDate (#1916) | customer, product (code prefix / ids), brand, category, sales agent, customers-assigned-to, location, channel, period (`ask.py:28`) | customer, product, brand, category, sales agent, location, channel, month; top N; compare (`ask.py:27`) |
| "sales for customer X this year", "sales of code Y" | `crm_sales_report` | `lanes/business/__init__.py:2271-2289` (a product or customer is named and `order_status` = `sales_report`) | `services/sales_report_delivered.py:225` over `services/reports/datasets/delivery_order_lines.py` | **delivered only**, by DO date | product, customer, brand, channel, location. **No agent, no category** (`lanes/business/fetch.py:1086-1155`; the route never sends them) | period buckets + one of customer / product / DO / agent |
| "outstanding for customer X / code Y / brand Z" | `crm_outstanding_report` | `lanes/business/__init__.py:2160-2168` | `services/outstanding_report_service.py:175` (`_fill_so` :255, `_fill_do` :448) | **qty only, no RM**; SO side open header + line with ordered − delivered > 0; DO side = undelivered DOs | product code(s), customer, brand, location, order date. **No agent, category or spec**; needs a subject | so / do / both; by location, customer or product; no top N |
| "sales by month / by channel 2026" | `crm_sales_analysis` | override ending `lanes/business/__init__.py:2270`; args `fetch.py:1212-1245` | `services/reports/definitions/sales_yearly.py:66` (also the **Yearly comparison** screen) | delivered / ordered by **SO date**; invoiced (#1916) | company, channel, basis, period only | year x month / channel |
| sales total naming only a brand | rerouted to `crm_report_ask` | `lanes/business/__init__.py:2138-2151` (the only total that reaches the engine today) | as row 1 | | | |
| "sales agent X's total" / "my customers' sales" | **no tool takes an agent filter for a total.** `crm_sales_report` drops the agent; only a `sales_ranking` ask moves agent words off the entity list (`report_ask.py:466`, `WORD_HINTS` :69) | | | | | |

Other paths, not chatbot routes but in scope for "same number everywhere":
- `crm_top_selling_report` (MCP `sorento_crm_mcp/sorento_crm_mcp/catalog.py:996`, `services/sales_report_service.py:642`)
  is off the chatbot (`lanes/business/__init__.py:1869-1873` rewrites it into report ask). It is still in the MCP
  catalog and the analytics connector (`services/analytics_connector/reused_tools.py:910`).
- `orders_list` with `order_status=so_outstanding` (`services/order_service.py:332,389`) checks only that the line is
  open, never the SO header. It is reached only when no subject is named (`lanes/business/__init__.py:2397`).
- `crm_order_analytics` (`services/order_service.py:1523`) reads the DO header and includes tax. Kept off the chatbot's
  order domain.
- Targets / achievement (`services/sales/achievement_service.py:238`) and commission sit on their own crediting rules
  (agent sharing, team windows). **Out of scope:** a target is not a report ask.
- AR (unpaid invoices) is pushed from AutoCount as `customers.ar_outstanding`. It is read by the finance billing
  documents routes (`api/v1/finance/billing_documents.py:40,114`) and on no MCP tool.
- No email or digest sends sales or outstanding figures.

Where the engine itself falls short, the gaps all sit at the chatbot's edge:
- **No spec filter.** The route allow-list is `api/v1/order_management/report_ask.py:58-64,233-244`; anything else
  gets a 422. `ask.FILTERS` has no spec either.
- **Only brand, agent and category words are resolved** (`report_ask.py:854` `_WORD_PARAMS`).
- **Only category keeps the parser's canonical code** (`report_ask.py:475-477`). Brand and agent are re-matched from
  raw words, so "mch" (MOCHA) comes back unknown.
- **Span-pass matches never reach the report.** They are found at `services/chatbot/engine.py:1431-1514`, reach only
  the prompt (`engine.py:5246`), and the lane re-resolves raw words with type-locked matchers. So "sales agent ..." can
  resolve as a customer.

## 2. The unified rule

1. **One service.** `services/reports/ask.run_ask`, behind `crm_report_ask`, answers every sales and outstanding
   figure the chatbot gives: a ranking, a total (no grouping), or a breakdown (group by month / channel / ...).
   Sales on the invoiced basis come from #1916's `invoiced_sales` (billing lines). The order bases stay on
   `sales_order_lines_ask`. No second calculation anywhere.
2. **Every filter on every basis:** customer, sales agent (order's own), customers assigned to (an agent's book),
   product / product set, **spec** (new), brand, category, channel, location, period.
3. **Every grouping:** product, customer, agent, brand, category, channel, location, month, **spec key** (new). Top N,
   or the total.
4. **Measures:** RM and qty on every basis. Outstanding gains RM, which the old outstanding tool never had.
5. **The spec filter adds no new spec logic.** Spec words resolve through the described-set resolver
   `services/product_predicate_service.resolve_product_set`, the one "any P-trap WC?" already uses. Its product ids
   travel as the engine's `product` filter, and the header names the spec ("Spec: P-trap").
6. **Bound by row id.** A span-pass match (customer, agent, brand, category, spec key/value) travels to the report as
   a structured candidate carrying its row id. The lane never re-reads the raw word.
7. **Nothing dropped silently.** A filter the service cannot apply prints as a `Not applied: <filter> (<reason>)` line
   under the header. When that filter was the ask's only subject, the bot asks instead of answering.
8. **Standing rulings kept.**
   - One question for everything missing (period + measure + basis); Invoiced is offered first and never defaulted.
   - A "by X" follow-up changes the grouping and keeps every filter on screen.
   - The contact's Sales report switch is respected.
   - "My ..." from an ungranted live salesperson means their own customers, headed "Limited to: your customers".
9. **Screens.** The same `run_ask` / definitions back the report screens. Yearly comparison, Top selling items and
   Sales by debtor type are already engine definitions (#1916). The three ask definitions get one screen (Q5).

## 3. Messages and what they answer after the change

The owner's hand-test messages from #1917 are paraphrased from the crew trace. Verbatim text was requested from crew
(crew-note on #1922) and replaces these on arrival.

| # | Ask | Today | After |
|---|---|---|---|
| H1 | sales of "mch" (MOCHA) items, period given | "mch" unknown: brand words are re-matched raw, only category keeps its canonical (`report_ask.py:475-477`) | span pass binds brand MOCHA by row id; `run_ask` brand = MOCHA; header "Brand: MOCHA" |
| H2 | "sales agent \<name\> sales this year" | name resolves as a **customer pick** (type-locked re-resolution) | agent bound by row id; `run_ask(filters={sales_agent})`, no grouping = one total; header "Sales agent: \<name\>" |
| H3 | total for an agent + another filter | agent **silently dropped** (`crm_sales_report` has no agent param) | same engine call with both filters; a filter it truly cannot apply prints a "Not applied:" line |
| H4 | top selling "p trap" WC | spec ignored / "need a filter" | spec -> product set via `resolve_product_set`; ranking over that set; header "Spec: P-trap" |
| R1 | "outstanding for customer X" | `crm_outstanding_report`, qty only, SO/DO blocks | `run_ask(basis=outstanding, customer)`, qty + RM, by product (Q2 decides the DO half) |
| R2 | "outstanding for agent X by customer" | not answerable (no agent filter on the outstanding tool) | `run_ask(basis=outstanding, sales_agent, group_by=customer)` |
| R3 | "who bought the most of code Y" | ranking OK today | unchanged path; the same number as "sales of Y by customer" because both are one call |
| R4 | "sales by month for brand Z" | `crm_sales_analysis` cannot filter brand | `run_ask(group_by=month, brand)` |
| R5 | "sales by trap type for WC" | not answerable | `run_ask(group_by=spec:trap, category=WC)` |

R1-R5 stand in for real prod turns until crew returns them (requested on #1922).

## 4. Edge cases

- **One rule for the date of an order-basis line.** Totals today use the DO date (`crm_sales_report`) or the SO date
  (`crm_sales_analysis`); the engine uses required date, else SO date. After the change, every order-basis figure in
  the chatbot uses the engine's rule. Invoiced uses DocDate, so it tallies with AutoCount (#1916). The DO-date
  delivered total disappears from chat. That is the point: one number.
- **A spec matching no products** says so and names the spec ("No products with Spec: P-trap"). It never ranks the
  unfiltered set.
- **A spec key the contact may not see** (`hidden_keys`) neither filters nor groups. It prints as "Not applied".
- **A spec group-by on products with no value for that key** goes to a "Not stated" row, so the rows still add up to
  the total.
- **Dealer contacts** keep `DEALER_KEYS` (`ask.py:68`): product, brand, category, month, plus spec (product facts, not
  other customers' data).
- **Mixed-code product words** keep `MIXED_PRODUCTS_LINE` (asked, never frozen on the first code).
- **Outstanding RM** = `line_total` x open qty / ordered qty, as the engine's outstanding basis already prices it.

## 5. Delivery (after answers)

Small stacked PRs, red-first:
1. **Engine:** spec filter + spec grouping + outstanding RM, plus a tally test of the MCP route against the report
   definition.
2. **Chatbot routing:** totals, outstanding and breakdowns go to `crm_report_ask`; old tools retire per Q1.
3. **Span binding:** row-id candidates and "Not applied" lines.

Gates: eval on the parser gold set + the owner's messages; reviewer; browser pass; hand test.

## 6. Questions (also in the crew-ask)

1. **Retire which tools from the chatbot?**
   - (a) `crm_sales_report`, `crm_outstanding_report` and `crm_sales_analysis` all route to `crm_report_ask`. The MCP
     `crm_top_selling_report` is removed. The Yearly comparison stays a screen + Excel file.
   - (b) Keep `crm_sales_report` for its DO-date period buckets.
   - **Rec (a):** two delivered numbers for one question is the bug the owner reported.
2. **What does "outstanding" mean?**
   - (a) Undelivered order quantity (what the bot means today), one definition: the engine's open SO remainder, qty
     + RM, with the DO "pending delivery" half dropped from chat.
   - (b) As (a), but keep the SO / DO / both choice by adding a "pending delivery" basis to the same engine.
   - (c) Unpaid invoices (AR).
   - **Rec (a):** one figure. (b) is cheap to add later if staff miss the DO half. AR stays on the billing documents
     screen.
3. **Spec scope?**
   - (a) Filter **and** group by a spec key ("by trap type").
   - (b) Filter only for now.
   - **Rec (a):** the owner listed "by spec" as a grouping.
4. **A filter the service cannot apply:**
   - (a) Answer with a "Not applied: \<filter\> (\<reason\>)" line, and ask instead only when it was the sole subject.
   - (b) Always ask before answering.
   - **Rec (a):** it keeps the answer and never hides the gap.
5. **Report screen for the same engine?**
   - (a) One "Sales & outstanding" screen over the ask definitions (basis picker, the same filters and groupings,
     Excel), so staff can check the bot's number.
   - (b) Chatbot only in this lane.
   - **Rec (a):** it is the screen half of "shared across", and it only registers definitions that already exist.
