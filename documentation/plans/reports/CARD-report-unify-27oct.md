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

The owner's hand-test messages from #1917 (27 Oct ~18:35-18:45) are verbatim, from the crew trace. Customer names are
left out.

| # | Ask (verbatim) | Today (v132) | Loss point | After |
|---|---|---|---|---|
| H1 | "p trap only" (after a SORENTO WC top-100), then "top 100 hot selling sorento p trap wc in 2026, by delivered qty" | The first gets the same WC list, with "p trap" not applied. The second gets "That would search every sales order we have - I need at least one filter...", although brand + category + year were all given. | The parser emitted `trap_type=p_trap`. The engine has no spec filter, so the spec fell to the generic gate (`chatbot/lanes/business/gate.py:540-545`). That reply replaced the fetched ranking (`answer.py:3364-3473`). | The spec resolves to the P-trap WC set (`resolve_product_set`) and the ranking runs over it: "Top 100 of N products by delivered sales / Brand: SORENTO / Category: WC, Water Closet / Spec: P-trap / Period: 2026". |
| H2 | "top 100 hot selling mch watr tap in 2026, by delivered qty" | "I don't know 'mch' as a brand." | The span pass matched MOCHA (0.80). The parser sent `{raw:"mch", hint:"brand", canonical_code:"MOCHA"}`. `take_words` keeps the canonical only for category (`report_ask.py:475-477`), and `resolve_brand_token` fails on "mch". | Brand bound to the MOCHA row by id, category Tap. Header "Brand: MOCHA / Category: Tap ...". |
| H3 | "sales agent yu sales for SRTSP231 in 2026" | "Which one do you mean?" with two **customers** | The span pass typed "yu" as a salesperson. The parser sent `hint:"sales_agent"`, order_status `sales_report`. Only `sales_ranking` moves agent words off the entity list (`report_ask.py:466`), so the generic resolver matched a customer. | Agent candidates come from the span pass, bound by id. If several agents match, the bot asks "Which sales agent?" (agents only, never customers). Then one total, headed "Sales agent: ... / Product: SRTSP231 / Period: 2026". |
| H4 | "sales agent yu total sale for SRTSP231 in 2026" | "Customer: all / Product: SRTSP231 / Delivery date: 2026 / Total: Qty 97, RM 14,797.53": the agent is **silently dropped**, so the figure covers all agents | "yu" landed in `person_mention`. `crm_sales_report` has no agent filter (`lanes/business/fetch.py:1086-1155`). | The same engine call as H3, so H3 and H4 give the same number. |

Side finds from the trace, folded into slice 3:
- The salesperson candidate list is capped at 5 (`chatbot/head/lookup_lists.py:55`). "YU - III" was matched but never handed over.
- "YMH I/III/IV" scored "exact 1.00" for "yu".
### Real prod turns, 27 Sep-27 Oct

These come from the crew chat connector. Askers are staff. Customer and agent names are placeholders, and turn ids
are kept so the eval can replay them. Some turns ran on older parser versions (v42-v63), so each one is replayed
on this lane's head; the "After" column is the required answer, not a claim about today.

| # | Ask | Bot then | After (one `run_ask` call) |
|---|---|---|---|
| P1 OK | "Sales agent \<agent S\> Sorento top 10 hot sale water closet" (73b2380f) | Correct ranking, agent + brand + category | unchanged |
| P2 | "Sale agent wt sorento top 10 ceramic product sale on September" (37dc441a) | Agent and category silently "all" | agent WT (bound by id) + brand SORENTO + category Ceramic, Sept; or a "Not applied: Category ceramic (no such category)" line if none binds |
| P3 | "我们哪一位业务员卖得最多srtwc286-SH" (2f6fafdc) | The product was lost, Dealer channel added, top items listed | `group_by=sales_agent, product=SRTWC286-SH`, after the one question (period + measure + basis) |
| P4 | "让我知道每个业务员卖了多少个Srtwc286-sh-New 在9 月按业务员" (fa1cf2c8) | The earlier turn's products were used and no agent grouping offered | `group_by=sales_agent, product=SRTWC286-SH-NEW`, Sept. A named product replaces the carried one. |
| P5 | "Dealer \<Customer B\> oct total sales" (a818d893) | After the account pick: "I can't break sales down by customer yet" | customer filter (the picked account), Oct, total |
| P6 | "Total quantity sale for Sorento brand kitchen sink on September 2026" (fd59e30c; same shape 96e4cded "water closet") | 32-customer pick: the category word was matched against customer names | brand SORENTO + category Kitchen Sink (bound from the span pass as a category, never as a customer), qty total |
| P7 | "\<Customer C\> any outstanding mocha item in sales order" (6c72d194) | The brand was dropped and every DO product dumped ("I could not find mocha") | `basis=outstanding, customer, brand=MOCHA`, by product |
| P8 | "SRTWC 8518-SH-250mm got outstanding?" (45622f08) | Ran for a customer the message never named; spec unresolved | product family SRTWC8518-SH + spec length 250 mm, resolved to a product set; `basis=outstanding`; no customer. With no 250 mm member, it says so and lists the family's lengths. |
| P9 | "Total sale for all sale agents on September 2026" (4a8adfc7) | "I can't break sales down by sales_agent yet" | `group_by=sales_agent`, Sept, all agents |
| P10 | "Who is the top sale dealer selling Srtwc286-SH-new" (67aa1cc5) | Top items instead of top dealers; product dropped | `group_by=customer, channel=Dealer, product=SRTWC286-SH-NEW` |
| P11 | "Sale Agent \<agent W\> top 5 dealer a/c 3 1/1/26-30/9/26" (21b1f1b2) | The account-number qualifier "a/c 3" was dropped with no note | Answered with a "Not applied: a/c 3 (no account filter)" line, unless Q4 says ask |
| P12 OK | "Can let me know dealers outstanding for srtub206" (91ab328a) | Correct, by customer | `basis=outstanding, product, group_by=customer`, now with RM |

The pattern across the owner's and the prod turns has four parts:
- filters (agent, category, account no., brand, spec) are dropped or re-typed with no note;
- customer and agent group-bys are refused, because they hit `crm_sales_analysis` / `crm_sales_report`;
- category words leak into customer matching;
- an earlier subject's products carry over a newly named one.

All four come from the same two causes. Each sales tool takes only some filter kinds, and the span pass's typed,
row-bound matches are only advice.

**Eval set for the lane:** the 4 owner messages, P1-P12, and the parser gold set. On the lane's head, each is
replayed against a seeded fixture (no prod data). It passes when the header carries every named filter, or a
"Not applied" line for it, and the grouping is the one asked.

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
