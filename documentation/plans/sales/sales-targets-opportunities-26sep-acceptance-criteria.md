# UAC: sales targets, opportunities and the WhatsApp achievement broadcast (issue #1170)

Plan: `documentation/plans/sales/PLAN-sales-targets-opportunities-26sep.md`. Mockup:
`documentation/plans/sales/mockups/sales-targets.html`. Slice 1 of #1170 (a sales agent on a
customer) shipped in PR #1177 and is not repeated here.

Status: building. Wave 2, S1, is on PR #1297 (S1-1, S1-3 to S1-10, S1-12 to S1-15, S1-18 to S1-29, S6-4 to S6-7, S6-10; plan section 16). Wave 1, S6, merged on PR #1260 (S6-1 to S6-3, S6-8, S6-9, S6-12 to S6-18, S1-17; plan section 15). S6 accepted on the owner's hand test (26 Sep ~13:25Z); fix lane round 2 adds S6-16 to S6-18 (team leader, a returning agent listed once).
Earlier status: grilled. Round 1 answered by the owner 26 Sep 2026 (PR #1260 comment, 05:25Z); every AC
is now written to the ruling, marked "(Owner ruling 26 Sep, G#)". Round 2 questions R1 to R5
(plan section 9) may still adjust the ACs marked "(R#)"; each is written to its recommendation.
Round 3 (26 Sep): the owner's Lavish review of the mockup (PR #1260 comment, 05:35Z) is folded in
as rulings L1 to L4, marked "(Owner ruling 26 Sep (Lavish), L#)". Round 3 questions T1 to T5 (plan
section 10) may still adjust the ACs marked "(T#)"; each is written to its recommendation. No
criterion was deleted: new ones are S1-17, S1-18, S3-5, S4-10, S5-14 and the new slice S6 (sales teams),
which is built second, right after S1 (plan section 6).
Round 4 (26 Sep): the owner's second Lavish review, of the round 2 mockup (PR #1260 comment,
06:01Z), is folded in as rulings N1 to N13, marked "(Owner ruling 26 Sep 06:01 (Lavish), N#)".
Round 4 questions Q1 to Q5 (plan section 11) may still adjust the ACs marked "(Q#)"; each is
written to its recommendation. No criterion was deleted: an AC that a ruling changes keeps its
id and text and gains a "Round 4" note saying what now applies; new ones are J14, S1-19 to
S1-25, S2-15, S2-16, S3-6, S4-11, S5-15, S5-16, S6-12, S6-13 and the new slice S7 (dealer
targets). **Build order after round 4: S6, S1, S7, S2, S3, S4, S5** (plan section 6).
Round 5 (26 Sep): the owner's answers to R1 to R5 and T1 to T5 (PR #1260 comment, 06:09Z) are
folded in as rulings marked "(Owner ruling 26 Sep 06:09, R# or T#)". No criterion was deleted: an
AC a ruling changes keeps its id and text and gains a "Round 5" note; new ones are S1-26 to
S1-29, S3-7, S4-12, S6-14 and S6-15. Round 5 questions V1 to V3 (plan section 14, PR comment 5844053739) may still
adjust the ACs marked "(V#)"; each is written to its recommendation. Tables live in schema
`sales` (plan 3.7 map; V3): where an AC names `sales_targets` and the like, the built name is
`sales.targets`. **Every slice is built now, nothing deferred (T5). Waves: S6; then S1 beside
S2; then S7, S4, S3 and S5 side by side, S5 merging last** (plan section 6, "Lanes after round
5").

Tags: `[BE]` pytest, `[FE]` vitest, `[E2E]` recorded agent-browser run (no new Playwright spec),
`[T]` text or copy check. Every AC traces to a journey step (J1 to J12).

## Owner rulings 26 Sep (one line each)

- **G1, Owner ruling 26 Sep:** achievement basis is set per target: ordered, or delivered (confirmed).
- **G2, Owner ruling 26 Sep:** an agent target counts the sales order's agent; a dealer target counts all that dealer's orders.
- **G3, Owner ruling 26 Sep:** a target has its own validity, a start month and a number of months, Odoo style.
- **G4, Owner ruling 26 Sep:** metric (amount or quantity), product scope (all, categories, products) and date range are all set per target.
- **G5, Owner ruling 26 Sep:** opportunity stages live on the existing configurable stage table; Proposal is optional.
- **G6, Owner ruling 26 Sep:** full commission suite (tiers, higher rate above target, quantity commission); commission shown or hidden per contact.
- **G7, Owner ruling 26 Sep:** the broadcast schedule is set per contact.
- **G8, Owner ruling 26 Sep:** what each recipient sees is set per contact.
- **G9, Owner ruling 26 Sep:** targets by admins and holders of "sales targets: edit"; salespeople log opportunities in the portal.
- **G10, Owner ruling 26 Sep:** project sales count when they are the agent's sales; opened to dealer salespeople first.

## Owner rulings 26 Sep (Lavish), one line each

From the owner's Lavish review of the round 2 mockup (PR #1260 comment, 26 Sep 05:35Z, verbatim
quotes).

- **L1, Owner ruling 26 Sep (Lavish):** "put sales agents under sales also": the Sales Agents nav item moves into the Sales menu group (S1-17).
- **L2, Owner ruling 26 Sep (Lavish):** "need to be able to set multiple sales teams and put the sales agents under the team and be able to set team target": sales teams, agents placed in a team, and team targets whose achievement is the sum of the team's agents' orders under the same basis rules (J13, S6).
- **L3, Owner ruling 26 Sep (Lavish):** "there should be a CTA Set Target at the top right": a Set target primary button in the Targets page header, top right, on every tab and at 375 (S1-18).
- **L4, Owner ruling 26 Sep (Lavish):** "not sure if we should reuse our teams table in our system": asked as round 3 question T1; the ACs are written to its recommendation, a new sales team table (S6).

## Owner rulings 26 Sep 06:01 (Lavish), one line each

From the owner's second Lavish review, written against the round 2 mockup (PR #1260 comment,
26 Sep 06:01Z, verbatim quotes).

- **N1, Owner ruling 26 Sep 06:01 (Lavish):** "need to move under Sales, not under Master Data anymore": Sales Agents sits under Sales only, shown in the mockup, built in S6 (S1-17).
- **N2, Owner ruling 26 Sep 06:01 (Lavish):** "we should have a team view to configure the team, cna refer to how we built our Teams page": a Sales Teams page on the Teams page concept, on `sales_teams` (S6-12).
- **N3, Owner ruling 26 Sep 06:01 (Lavish):** "too many information": the list names a target by its name only (S1-21).
- **N4, Owner ruling 26 Sep 06:01 (Lavish):** "i want to keep each row as 1 line, if got more need to use +x pill, the details can be viewed if we go inside": one line per row, "+N" pills, details on the target's page (S1-21).
- **N5, Owner ruling 26 Sep 06:01 (Lavish):** "i want to see a list of teams first and the targtes, then only click inside the team to see a list of sale agent, and their target, also need to provide mockup of form view of target, and also teams": teams-first landing, team page, target page; teams ship first (S1-22, S1-23, S6-13, S7).
- **N6, Owner ruling 26 Sep 06:01 (Lavish):** "can this just be date range?": a start date and an end date (S1-19, S1-25).
- **N7, Owner ruling 26 Sep 06:01 (Lavish):** "why suddetnly got quarter so hard set one? what if i want month, week, year, 2 months, 2.5 months??": no quarter; any range; an optional free split (S1-19, Q1).
- **N8, Owner ruling 26 Sep 06:01 (Lavish):** "use dropdown for these, use our standard dropdown component": `SearchableSelect` for every picker (S1-24).
- **N9, Owner ruling 26 Sep 06:01 (Lavish):** "use dropdown for this, our standard dropdwon component": How tiers pay is a `SearchableSelect` (S4-11).
- **N10, Owner ruling 26 Sep 06:01 (Lavish):** "why we need this togle? it is or not a customer we can know right?": one Customer or prospect search that infers it (S2-15, Q2).
- **N11, Owner ruling 26 Sep 06:01 (Lavish):** "what's this, products?": optional product lines with a quantity (S2-16, Q3).
- **N12, Owner ruling 26 Sep 06:01 (Lavish):** "can this be configured at Internal Contacts page? so we got 1 page to set all things": a Sales updates tab on the contact's record (S5-15).
- **N13, Owner ruling 26 Sep 06:01 (Lavish):** "what's this": Add suggested is explained in the plan (3.6) and dropped (S5-16).

## Owner rulings 26 Sep 06:09, one line each

From the owner's answers to rounds 2 and 3 (PR #1260 comment, 26 Sep 06:09Z, verbatim quotes).

- **R1, Owner ruling 26 Sep 06:09:** "yeah correct": the portal form goes to Sorento's own dealer-channel sales agents first (S2-3, S2-4).
- **R2, Owner ruling 26 Sep 06:09:** "yeah": an agent target, and each team member, counts every code with the same person label (S1-29).
- **R3, Owner ruling 26 Sep 06:09:** "we will have DO integreation as soon as next Monday so by that time we will be able to know": delivered counts by DO date once DO lines are linked; by order date until then and for any quantity no linked DO explains (S1-26, V2).
- **R4, Owner ruling 26 Sep 06:09:** "yeah": amounts stay tax inclusive (no change).
- **R5, Owner ruling 26 Sep 06:09:** "yeah": higher rates pay above their threshold by default; "Highest rate on everything" is selectable on any target and built in S4 (S4-3, S4-4, S4-11).
- **T1, Owner ruling 26 Sep 06:09:** "okay can": new sales team tables, not the core `teams` (S6).
- **T2, Owner ruling 26 Sep 06:09:** "when we move agent to new team, only new order received in the new team is considred the ales of the new team right?": yes; membership is dated and a team counts each order by the membership in force on its date (S6-14, S6-15, V1).
- **T3, Owner ruling 26 Sep 06:09:** "I can set individual on each agent and add up to team ah": a team target's figure is the sum of its agents' targets; no team-level override (S1-27, S1-28).
- **T4, Owner ruling 26 Sep 06:09:** "yeap ok": team pool per period, never split (S4-10, S4-12).
- **T5, Owner ruling 26 Sep 06:09:** "the point is we need to do it now and not backlog or defer": every slice now, thin lanes in parallel waves, nothing to the backlog.
- **Owner question 26 Sep 06:09:** "are we doing this in a new schema and module called sales?": recommended yes to both, module `sales` and schema `sales` (plan 3.7, V3).
- **Owner ruling 26 Sep ~09:05 (chat):** "yeah I am okay with sales target": V1, V2 and V3 accepted as recommended; build S6 first.

## Owner rulings 26 Sep, S6 hand test (fix lane round 2), one line each

- **W2, Owner ruling 26 Sep ~13:05Z (chat), on reviewer nit N1:** "hmm shouldn't list twice la in my opinion": an agent who left a team and came back is listed once on the team page, as active; the earlier stay stays in the data (S6-18).
- **W1, Owner ruling 26 Sep ~13:25Z (chat, S6 hand test):** "hand test for sales team S6 is okay, but I need it to be able to set a sales leader, which is also a sales agent": S6 accepted as tested; one leader per team, chosen from its agents, a current attribute and not dated history (S6-16, S6-17).

## Journey

Actors: the **sales manager** (a CRM user: the owner or a sales admin) who sets targets and
chooses who receives what; the **salesperson** (a sales agent with no CRM login, ruling 14 Aug
2026, `app/models/sales_agent.py:1-17`) who logs opportunities in the portal and receives a
WhatsApp message; the **dealer**, who may receive a WhatsApp message.

- **J1. First screen.** From `/`, the manager expands **Sales** and clicks **Targets**. The page
  opens on the current month, **Agents** tab: one row per target period that covers this month,
  grouped by agent, with Target, Achieved, %, Pipeline and Commission. An active agent with no
  target covering this month shows one "No target" row with **Set target**. The manager is asked
  for nothing to see where the team stands.
  (Owner ruling 26 Sep (Lavish), L1: the Sales group also holds **Sales Agents**, and from S6
  **Sales Teams**. L3: a **Set target** button sits alone at the top right of the page header, on
  every tab.)
  (Round 4, Owner ruling 26 Sep 06:01 (Lavish), N3, N4, N5: the page opens on the **Teams** tab,
  one line per team with its target for today, then a "No team" line and the Unassigned line.
  Every row is one line; extra targets or measures fold into a "+N" pill. The toolbar's **Active
  on** date (default today) replaces the month picker. Clicking a team opens the team's page:
  its own targets, then its agents and their targets, one line each. The Agents tab is a flat
  list, one line per agent, with a Team filter.)
- **J2. Set a target.** **Set target** opens a modal with the agent (or dealer) and the start
  month filled in. It asks for a name, the metric (Amount or Quantity), the basis (Ordered or
  Delivered), the products it applies to (All, Categories, Products), how many months it runs and
  how the figure is split (per month, per quarter, or one figure for the whole period), and the
  target figure per period. Defaults: Amount, Ordered, All products, 1 month, per month. Save shows
  the new row.
  (Owner ruling 26 Sep (Lavish), L3: from the header **Set target** the modal opens with nothing
  chosen but "Target for" preset to the open tab's kind (Agent, Team from S6, or Dealer) and a
  searchable select for who; from a "No target" row it opens with that agent or team filled in and
  read-only, as before.)
  (Round 4, N6, N7, N8: every choice is a dropdown; "Starts / Runs for / Target figure is" become
  **Start date** and **End date** and an optional **Split** (off, or every N days, weeks or
  months); the figure is for the whole range, or for each period when split. Defaults: Amount,
  Ordered, All products, today to the last day of this month, split off.)
- **J3. Tune the periods.** The target's detail page lists its periods; the manager changes one
  period's figure (a lower December) in place.
  (Round 4, N5: this page is the target form view, J14.)
- **J4. Duplicate.** **Duplicate** on a target creates a copy starting the month after it ends,
  with the same settings, figures, scope and tiers, for the manager to adjust.
- **J5. Dealers.** The **Dealers** tab lists dealer targets covering this month; **Add dealer
  target** opens the same modal with a searchable dealer select first.
  (Round 4: built in S7, after S1; one line per dealer; the header Set target presets Dealer.)
- **J6. Salesperson logs an opportunity.** In the portal, a salesperson who has been granted it
  opens **Sales Opportunities**, taps **New**, picks one of their own customers (or types a
  prospect name when the buyer is not a customer yet), and enters a title, expected amount,
  expected close month and a short product note. Stage starts at the first stage. The agent is
  the salesperson, never asked.
  (Round 4, N10, N11: there is no "not a customer yet" switch. One **Customer or prospect**
  search lists their own matching customers and, when none matches the typed name, offers **Add
  "..." as a new prospect**. "What they want" becomes an optional **Products** table, a product
  and a quantity per row. The close month becomes an **expected close date**.)
- **J7. Salesperson moves it along.** The salesperson opens their opportunity and moves it to the
  next stage; Lost asks for a reason from a list. They see only their own opportunities.
- **J8. Manager sees opportunities.** **Sales > Opportunities** (DataGrid, filter by stage, agent,
  customer, close month) and an **Opportunities** section on the customer page show the same
  rows; the manager can log or edit on an agent's behalf and link a won one to its sales order.
- **J9. Pipeline beside the target.** On Targets, each agent's **Pipeline** is the weighted value
  of their open opportunities expected to close this month (expected amount x the stage's
  probability). Achievement never includes opportunities.
  (Round 4: expected to close inside the target period shown, by date.)
- **J10. Commission.** In the Set target modal, the manager adds commission tiers (from what %
  achieved, at what rate, with an optional one-off bonus) and picks whether a higher rate applies
  only above its threshold or to everything. The Commission column shows what each period has
  earned so far.
- **J11. Choose recipients.** On the **Recipients** tab, the manager adds a WhatsApp contact,
  chooses what they follow (an agent, a dealer, or the team), when they receive it (daily, weekly
  on a weekday, or monthly on a day, at a time) and what they see (commission, pipeline, one line
  per target). **Preview** shows the message; **Send now** sends it; **Enabled** turns the
  schedule on.
  (Round 4, N12, N13: the manager does this on the contact's own record, **Internal Users > the
  contact > Sales updates**, one page for all of a contact's settings. There is no Recipients
  tab and no Add suggested; **Add** on a contact linked to an agent presets Follows to that
  agent.)
- **J12. The message arrives.** At each recipient's own time, they receive one WhatsApp message
  with the figures they are set to see and nothing else.
- **J13. Teams and team targets** (Owner ruling 26 Sep (Lavish), L2). The manager opens **Sales >
  Sales Teams**, clicks **Add team**, types a name and picks the agents who belong to it (an agent
  already in another team is labelled with that team and moves on save). On **Targets**, the
  **Teams** tab lists each team's target periods for the month with the same columns as Agents;
  a team with no covering target shows "No target" with **Set target**. A team target is set in the
  same modal with "Target for: Team". Its achieved figure is the sum of its agents' orders counted
  by that target's own metric, basis and product scope. The Agents tab can be filtered by team.
  (Round 4, N2, N5: Sales Teams follows the Users & Access > Teams concept: a list with search
  and **Add team**, one modal, and the team's own page. Teams ship first, before any target
  (S6); the Teams tab is the Targets landing (S1).)
  (Round 5, Owner ruling 26 Sep 06:09, T2, T3: picking an agent who is in another team shows
  **Moves on** (default today); orders dated from that day count for the new team and earlier
  ones stay with the old team. A team target is set by typing each agent's figure in one form;
  the team figure is their sum, shown read-only.)
- **J14. Open a target** (round 4, Owner ruling 26 Sep 06:01 (Lavish), N3, N4, N5). From any
  target pill or row, the manager opens the target's own page: who it is for, what counts, the
  dates and split, one line per period with its figure and achievement, and the commission
  tiers. **Edit** turns the same fields into inputs in place; **Duplicate** and a deferred
  **Delete** sit in the header, with previous and next target navigation.

## Definitions the ACs rely on

- **Period.** A row of `sales_target_periods`: `[period_start, period_end)`, month aligned. A
  target covers month M when one of its periods contains M.
  Round 4 (N6, N7): `[period_start, period_end]`, both days counted, any dates; one period for
  the whole range unless the target is split. A target is **active on** date D when one of its
  periods contains D, and that period is the one shown.
- **Achieved value** of a period (Owner ruling 26 Sep, G1, G2, G4, G10): over
  `sales_order_lines` whose order is not `cancelled`, whose `line_status` is not `cancelled`, and
  whose `sales_orders.order_date` is inside the period; attributed by `sales_orders.sales_agent_id`
  for an agent target (R2 may widen this to the person's other codes) or `sales_orders.customer_id`
  for a dealer target; `demand_class` not filtered; restricted to the scope (all; categories
  including sub-categories; or products). Value:
  - amount, ordered: `line_total` (tax inclusive, R4);
  - amount, delivered: `round(line_total x least(qty_delivered, qty_ordered) / qty_ordered, 2)`,
    0 when `qty_ordered = 0` (the sales report's confirmed value; bucketed by order date, R3);
  - quantity, ordered: `qty_ordered`;
  - quantity, delivered: `least(qty_delivered, qty_ordered)`.
- **Team achieved value** (Owner ruling 26 Sep (Lavish), L2): the achieved value above, with the
  agent test widened to "`sales_orders.sales_agent_id` is an agent who is a member of the team
  now" (T2: current membership, not dated), each agent widened by R2 exactly as for an agent
  target. The team target's own metric, basis and scope apply. It equals the sum of what the same
  target would give on each member agent separately, and never counts an order twice.
  Round 5 (Owner ruling 26 Sep 06:09, T2): "a member of the team **on the order's date**": a
  `team_members` row for that agent and team with `valid_from` empty or on or before the order
  date, and `valid_to` empty or on or after it. With no move in the period it still equals the
  per-member sum.
- **Delivered, by DO date** (round 5, Owner ruling 26 Sep 06:09, R3): for a sales order line in
  scope, the delivered quantity in a period is (a) the sum of `order_lines.quantity` of
  non-cancelled DOs (`orders.is_cancelled` false) linked to the line through
  `order_lines.sales_order_line_id` whose `orders.order_date` (the DO date) is inside the period,
  plus (b), only when the sales order's `order_date` is inside the period, the residual
  `greatest(least(qty_delivered, qty_ordered) - all linked non-cancelled DO quantity, 0)`; the
  line's total over all periods never exceeds `qty_ordered` (linked DO quantities count in DO
  date order until `qty_ordered` is reached, the rest counts nowhere). Amount = `round(line_total x quantity /
  qty_ordered, 2)`. With no linked DO line this is exactly the round 2 figure above.
- **Team target figure** (round 5, Owner ruling 26 Sep 06:09, T3): each team period's target is
  the sum of the same-dated periods of the agent targets whose `parent_target_id` is that team
  target.
- **Stage probability** (Owner ruling 26 Sep, G5): the `win_probability` of the opportunity's
  status row; defaults New 10, Qualified 25, Proposal 50 (inactive), Negotiation 75, Won 100,
  Lost 0.
- **Commission** (Owner ruling 26 Sep, G6): per period from the target's tiers; `marginal` applies
  each tier's rate to the slice between its threshold and the next; `retroactive` applies the
  highest reached tier's rate to the whole; each reached tier's bonus is paid once per period;
  rate is % of amount for amount targets and RM per unit for quantity targets; rounded half up to
  2 dp per period.

## S1. Flexible targets with live achievement in the CRM

- **S1-1 [BE] (J2, Owner ruling 26 Sep, G3, G4)** `POST /api/v1/sales/targets` with `{subject_kind:
  "agent", sales_agent_id, name, metric: "amount", basis: "ordered", product_scope: "all",
  start_month: "2026-10-01", months: 6, periodicity: "month", target_value: 120000}` creates the
  header, six period rows of 120,000 (Oct to Mar) and returns `target_no` (`TGT-...`), the agent
  code and name, and the periods.
  Round 4 (N6, N7): the payload is S1-19's (`start_date`, `end_date`, optional split);
  `start_month`, `months` and `periodicity` are not accepted. The rest of this AC stands.
- **S1-2 [BE] (J2, G3)** `periodicity: "quarter"` with `months: 6` creates two periods; with
  `months: 4` it is 422. `periodicity: "whole"` creates one period spanning all months.
  `start_month` not on the 1st is 422; `months` outside 1 to 36 is 422.
  Round 4 (N7): no quarter or whole option; S1-19 holds the split and the validation.
- **S1-3 [BE] (J2, G4)** `product_scope: "categories"` without category ids is 422; with product
  ids is 422; `"products"` without product ids is 422; `"all"` with any scope ids is 422.
- **S1-4 [BE] (J3)** `PATCH /sales/targets/{id}/periods/{period_id}` changes one period's
  `target_value`; the other periods are unchanged.
- **S1-5 [BE] (J2, G3)** Changing `months` from 6 to 8 on the header adds two periods and keeps
  the six existing figures; changing `periodicity` regenerates periods and keeps any figure whose
  `period_start` is unchanged.
  Round 4: changing the dates or the split regenerates periods under the same keep rule.
- **S1-6 [BE] (J1)** `GET /api/v1/sales/targets?month=2026-10-01&subject=agent` returns one row per
  target period covering October (for a quarterly target, the quarter containing October), with
  `achieved_value`, `achieved_pct`, the period bounds, and one `target_id: null` row per active
  agent with no covering target.
  Round 4: `?on=2026-10-15` replaces `month` (S1-20); `subject=team` is the landing's call.
- **S1-7 [BE] (J1, Owner ruling 26 Sep, G1, G2)** Achievement golden set, amount: seeded orders for
  agent A in October (open, fulfilled, cancelled order, open order with a cancelled line, one
  dated 30 Sep, one with `order_date` null, one with agent B) give exactly the sum of the
  non-cancelled October lines of agent A, for `ordered`; for `delivered` the same lines give the
  sum of their confirmed values, and a line with `qty_ordered = 0` adds 0.
  Round 5 (R3): this holds when no DO line is linked; with linked DO lines, S1-26 applies.
- **S1-8 [BE] (J1, G4)** Achievement golden set, quantity: `ordered` sums `qty_ordered`,
  `delivered` sums `least(qty_delivered, qty_ordered)` (a line over-delivered by AutoCount never
  counts more than ordered).
- **S1-9 [BE] (J1, G4)** Scope: a `categories` target on "Basins" counts a product in
  "Basins > Countertop" and not one in "Taps"; a `products` target counts only the listed
  products; `all` counts everything.
- **S1-10 [BE] (J1, Owner ruling 26 Sep, G10)** An agent's `demand_class = "project"` order counts
  toward that agent's target exactly as a retail one does.
- **S1-11 [BE] (J5, G2)** A dealer target counts that customer's orders whichever agent is on
  them; a target with both or neither of agent and customer is 422.
- **S1-12 [BE] (J4)** `POST /sales/targets/{id}/duplicate` creates a new header starting the month
  after the source ends, with the same settings, period figures in order and scope rows, and a new
  `target_no`.
- **S1-13 [BE] (J1, Owner ruling 26 Sep, G9)** Without `sales.targets.view` the list is 403;
  without `sales.targets.add` create is 403; without `sales.targets.edit` PATCH, period edit and
  duplicate are 403; without `sales.targets.delete` DELETE is 403. Another company's target,
  agent or order is invisible under company scope. `DELETE` hard deletes header, periods and scope.
  Round 4: the same slugs gate team targets (built in S1) and dealer targets (S7).
- **S1-14 [BE][FE] (J1)** Orders in the month with a null `sales_agent_id` are totalled in one
  "Unassigned" row at the foot of the Agents grid (no target, no actions).
- **S1-15 [FE] (J1, J2, J3)** Targets page renders the month picker, Agents and Dealers tabs, rows
  showing name, metric and basis chip, scope summary ("All products", "3 categories"), period,
  target, achieved, a % bar (over 100% in the success tone and not capped); "No target" rows with
  Set target; loading, empty and error states. The Set target modal defaults as in J2, reveals the
  category or product multi-select for the chosen scope, changes the unit label between RM and
  units, and sends the payload of S1-1. The detail page edits a period figure in place; view and
  edit are the same layout; delete is a deferred-action countdown with no dialog.
  Round 4 (N3, N4, N5, N6, N8): the landing tab is Teams, then Agents, then Dealers (S7); the
  month picker is an Active on date; name, metric and basis chips and the scope summary are one
  "+N" pill cell on one line (S1-21); the modal's pickers are dropdowns (S1-24) and its validity
  is a date range (S1-25); the detail page is the target form view (S1-23).
- **S1-16 [E2E] (J1 to J5)** From `/`, Sales > Targets; set a 3-month, per-month target on one
  agent with a category scope, reload, it persists; change one period; duplicate it; add a dealer
  target; usable and unclipped at 1280 and 375.
  Round 4: the run starts on the Teams tab, opens a team, then an agent's target; the dealer
  step moves to S7-3.
- **S1-17 [FE][E2E] (J1, Owner ruling 26 Sep (Lavish), L1)** In the sidebar, the **Sales** group
  lists Targets, Opportunities (from S2) and **Sales Agents**; Sales Agents no longer appears under
  Users & Access > People. Its path (`/master-data-management/sales-agents`) and permission
  (`master_data.sales_agents.view`) are unchanged, and it stays visible when the `sales` module is
  switched off but the module owning the Sales Agents page is on (each child carries its own
  `moduleKey`). Reached by sidebar clicks from `/` in the E2E run.
  Round 4 (N1): built in S6, which ships first; the mockup shows Sales Agents under Sales and no
  "Master Data" group anywhere.
- **S1-18 [FE][E2E] (J1, J2, Owner ruling 26 Sep (Lavish), L3)** The Targets page header shows a
  **Set target** primary button alone at the top right, on the Agents, Dealers and Recipients tabs
  (and Teams from S6), at 1280 and at 375, and only for holders of `sales.targets.add`. It opens
  the Set target modal with "Target for" preset to the open tab's kind (Agent on the Recipients
  tab) and an empty searchable subject select; Save is disabled until a subject is picked. The
  month picker sits in the toolbar under the tabs, not beside the CTA.
  Round 4 (N5, N8, N12): the tabs are Teams, Agents and Dealers (no Recipients); "Target for" is
  a `SearchableSelect` preset to the open tab's kind (Team on the landing); the toolbar holds the
  Active on date. The team page's Set target presets that team.

- **S1-19 [BE] (J2, Owner ruling 26 Sep 06:01 (Lavish), N6, N7, Q1)** `POST /sales/targets`
  takes `start_date` and `end_date` (inclusive, any day) and optional `split_every` (1 to 99)
  with `split_unit` (`day`, `week`, `month`). No split: one period from start to end. 1 Oct to
  15 Dec 2026 split every 1 month: periods 1 to 31 Oct, 1 to 30 Nov, 1 to 15 Dec, each with the
  typed figure. 1 Oct to 15 Dec 2026 split every 2 weeks: five periods of 14 days (the fifth
  ending 9 Dec) and a last one from 10 to 15 Dec. A start on 31 Jan 2027 split every month gives
  31 Jan to 27 Feb, then 28 Feb to 30 Mar (each period starts N months after the start date,
  moved to the month's last day when the month is shorter). `end_date` before
  `start_date` is 422; one of `split_every` or `split_unit` without the other is 422; more than
  104 periods is 422. A one-day range is valid.
- **S1-20 [BE] (J1, N6)** `GET /sales/targets?on=2026-10-15&subject=agent` returns, for each target
  with a period containing 15 Oct, that period's row (bounds, target, achieved, %); an order dated
  on `period_end` counts and one dated the day after does not; a target whose range ended 14 Oct
  is not returned.
- **S1-21 [FE] (J1, J13, N3, N4)** Every row on the Teams, Agents and Dealers tabs, the team page
  and the Sales Teams list is one line at 1280: no second line, no wrapping. A subject with more
  than one target active on the date shows one row whose numeric cells are the first target's
  (amount before quantity, then soonest end date, then lowest target number) and whose Targets
  cell is a `PillOverflow` of the target names with "+N"; the pill popover lists every target on
  one line with its %, each linking to its page. Metric, counts and scope are one `PillOverflow`
  cell. The target number, dates and split are not in any list row.
- **S1-22 [FE][E2E] (J1, J13, N5)** Sales > Targets opens on the Teams tab: one line per active
  team (team, agents pills, targets pills, target, achieved, %, pipeline from S3, team pool from
  S4), then a "No team" line counting active agents in no team that opens the Agents tab filtered
  to "No team", then the Unassigned line. A team with no target on the date shows "No target"
  and Set target. Clicking a team row opens `/sales/teams/{id}` (S6-13) with its Team targets
  section and its Agents section listing each member agent's targets, one line each. No
  grouped or nested rows on any tab.
- **S1-23 [FE][E2E] (J14, N5)** `/sales/targets/{id}` renders, in order, Target (target for, who,
  name), What counts (metric, counts, applies to, the list when not all), Dates (start, end,
  split), Periods (one line each, today's period marked, figure edited in place), Commission
  (S4; empty state "No commission" with Add tier before S4). The target number, subject link,
  created and updated sit in the header, not in a section. Edit swaps values for inputs in
  place with no section moving; Duplicate and deferred Delete in the header; `RecordNavigation`
  across the list the user came from.
- **S1-24 [FE] (J2, N8)** Metric, Counts, Applies to, Target for and Split unit are
  `SearchableSelect` (`components/common/SearchableSelect.tsx`); the category and product lists
  are `SearchableMultiSelect`. No segmented button group remains in the modal or the target
  page. Required pickers are not clearable; Split unit is clearable and clearing it turns the
  split off.
- **S1-25 [FE] (J2, N6, N7)** The Set target modal has Start date and End date (the shared
  `DateRangePicker`), a Split switch that reveals "every [N] [unit]", and one Target figure
  field labelled "for the whole range" or "per period" to match; its hint names the number of
  periods and the last one's dates. There is no "Runs for" field and no "One per quarter" choice.

- **S1-26 [BE] (J1, Owner ruling 26 Sep 06:09, R3, V2)** Delivered by DO date, golden set, for
  an agent target on October with `basis: "delivered"`. Seed one sales order dated 20 Sep
  (outside October) with a line of 100 units, `line_total` 10,000, `qty_delivered` 100:
  (a) no linked DO line: October counts 0 and the September period counts 100 units / RM
  10,000 (the round 2 figure); (b) DO lines linked to it of 40 dated 5 Oct and 30 dated 3 Nov:
  October counts 40 units / RM 4,000, November 30, and September keeps the residual 30 / RM
  3,000; (c) the 3 Nov DO cancelled: November counts 0 and September's residual becomes 60;
  (d) linked DO lines of 70 on 5 Oct and 50 on 3 Nov on a line of 100: October 70, November 30,
  never more than 100 across all periods.
  An order line with a linked DO and a DO free-text salesman different from the order's agent
  still counts for the order's agent. Amount and quantity metrics, agent, team and dealer
  subjects all use this rule.
- **S1-27 [BE][FE] (J2, J13, Owner ruling 26 Sep 06:09, T3)** `POST /sales/targets` with
  `subject_kind: "team"` takes `agent_figures: [{sales_agent_id, target_value}]` for agents who
  are members of the team at any day in the range (422 for anyone else) and creates the team
  target plus one agent target per entry with `parent_target_id` set and the team's metric,
  counts, products, dates and split copied. Each team period's `target_value` equals the sum
  of its children's same-dated periods. In the Set target modal, "Target for: Team" shows an
  **Agents** table (agent, figure) prefilled with the team's members, and a read-only **Team
  target** total that updates as figures are typed; there is no editable team figure field.
- **S1-28 [BE] (J3, J13, T3)** `PATCH` of a team target's period is 422 `TEAM_TARGET_IS_SUM`.
  Changing a child's period figure, adding a child (Add figure for a member with none) or
  deleting a child re-sums the team's periods in the same transaction. Editing the team
  target's metric, counts, products, dates or split rewrites every child the same way; a
  child's own metric, counts, products, dates and split are 422 to change directly. Deleting
  the team target deletes its children as one deferred action whose countdown names the count.
  A child keeps its figures when its agent moves to another team.
- **S1-29 [BE] (J1, Owner ruling 26 Sep 06:09, R2)** An agent target on SEAN I counts orders
  under SEAN I and SEAN III when both carry the person label "Sean", and only SEAN I's when
  SEAN I has no label; a team with SEAN I as a member counts SEAN III's orders only inside
  Sean's membership window.

## S2. Opportunities, logged by salespeople in the portal

- **S2-1 [BE] (J6, Owner ruling 26 Sep, G5)** At startup the `sales_opportunity` status graph is
  seeded once with New (initial, 10), Qualified (25), Proposal (50, **inactive**), Negotiation
  (75), Won (terminal, 100), Lost (terminal, 0) and edges between live stages, back one step, and
  to Won and Lost; a second startup changes nothing, and an admin's later edits survive restarts.
- **S2-2 [BE] (J7, G5)** After an admin activates Proposal in System > Status Graphs, an
  opportunity can move Qualified to Proposal with no code change; renaming Won keeps won
  semantics (detected by key).
- **S2-3 [BE] (J6, Owner ruling 26 Sep, G9)** `POST /api/v1/public/portal/sales-opportunities`
  with a portal token whose contact is granted `sales_opportunity` and is linked to an active
  sales agent creates an opportunity at the initial stage, `source = "portal"`,
  `created_by_contact_id` set, and `sales_agent_id` = that agent, ignoring any agent id in the
  body.
- **S2-4 [BE] (J6, G9, G10)** A contact without the grant gets 403 `FORM_TYPE_NOT_VISIBLE`; a
  granted contact not linked to a sales agent gets 403 `NOT_A_SALES_AGENT`; the kind is not in the
  base kinds, so a contact with no segment and no override does not see it.
- **S2-5 [BE] (J6)** The portal customer lookup returns only customers whose `sales_agent_id` is
  the salesperson's agent; creating with another agent's customer is 422. With no customer,
  `prospect_name` is required (422 without it).
  Round 4 (N10): the prospect name comes from the search's "Add ... as a new prospect" option
  (S2-15); the 422 rules stand.
- **S2-6 [BE] (J7)** A salesperson lists and opens only opportunities whose `sales_agent_id` is
  theirs; another agent's id is 404. Stage changes follow the graph's edges only (422 otherwise);
  Lost without a `lost_reason` from `sales_opportunity_lost_reasons` is 422.
- **S2-7 [BE] (J8)** CRM `POST /api/v1/sales/opportunities` stamps `sales_agent_id` from the
  customer (null agent accepted), `source = "crm"`; `PATCH` to Won accepts an optional
  `sales_order_id` of the same customer (422 otherwise); `outcome` follows the terminal stage key.
- **S2-8 [BE] (J8)** `GET /api/v1/sales/opportunities` filters by stage, agent, customer and close
  month through the list-query contract; `sales.opportunities.view|add|edit|delete` gate each CRM
  route; company scope applies.
  Round 4: the close filter is a date range on `expected_close_date`.
- **S2-9 [BE] (J7)** Every stage change is in the audit timeline, attributed to the contact for
  portal changes and to the user for CRM changes.
- **S2-10 [FE] (J6, J7)** Portal: the landing shows a Sales Opportunities card only when the kind
  is visible; the list shows number, title, customer or prospect, stage `Badge`, amount and close
  month; the form uses searchable selects, a "Not a customer yet" switch revealing Prospect name,
  and at 375 has no horizontal scroll.
  Round 4 (N10, N11): no "Not a customer yet" switch (S2-15); the list shows the expected close
  date; the form adds the Products table (S2-16); the rest stands.
- **S2-11 [FE] (J7)** Portal detail: stage buttons offer only the allowed next stages; Lost reveals
  a required reason select.
- **S2-12 [FE] (J8)** CRM: Opportunities DataGrid with fixed layout, resizable columns, stage
  `Badge`, `rowHref` to the detail page with `RecordNavigation`; the customer page shows an
  Opportunities section in view and edit, with "No opportunities yet" and **Log opportunity**.
- **S2-13 [FE] (J8)** Choosing Won reveals an optional sales order select limited to that
  customer; the Source column shows Portal or CRM.
- **S2-14 [E2E] (J6 to J8)** As a granted salesperson in the portal at 375: log an opportunity on
  own customer, move it to Qualified, then Lost with a reason; as the manager in the CRM at 1280
  the list and the customer section show each step with the salesperson as the actor.

- **S2-15 [BE][FE] (J6, Owner ruling 26 Sep 06:01 (Lavish), N10, Q2)** The portal form has one
  **Customer or prospect** `SearchableSelect` and no switch. Typing "kedai" lists the
  salesperson's own customers matching by code or name. When no customer of the company has the
  typed name exactly (case and repeated spaces ignored), the list ends with **Add "Seri Indah
  Renovation" as a new prospect**; choosing it saves `prospect_name` with no `customer_id` and no
  customer row is created. When the typed name exactly matches another agent's customer, that
  option is replaced by a disabled "Seri Indah is another agent's customer" line, and a create
  with that name as a prospect is 422. The CRM opportunity modal uses the same field over all
  customers.
- **S2-16 [BE][FE] (J6, N11, Q3)** The portal form and the CRM modal have an optional **Products**
  table: a product search and a quantity per row, Add product, a remove control, and "No
  products yet" when empty (the complaint form's pattern). `POST` and `PATCH` take `lines:
  [{product_id, qty}]`, stored in `sales_opportunity_lines` in the entered order; qty 0 or less
  is 422; zero lines is valid; `expected_amount` is required and never computed from the lines.
  The opportunity page lists the lines as product code, name and quantity, one line each.

## S3. Pipeline beside the target

- **S3-1 [BE] (J9)** Each agent row carries `pipeline_value` = sum over that agent's
  opportunities on non-terminal stages with `expected_close_month` in the chosen month of
  `expected_amount x win_probability / 100`, and `pipeline_count`.
- **S3-2 [BE] (J9)** Won and Lost never add to `pipeline_value`; no opportunity ever adds to
  `achieved_value`.
- **S3-3 [BE] (J9)** An opportunity on a stage with null `win_probability` adds 0 and is counted in
  `pipeline_unweighted_count`, never guessed.
- **S3-4 [FE] (J9)** The Pipeline cell and KPI link to Sales > Opportunities filtered to that agent
  and month; a non-zero unweighted count shows a hint in the cell's title.
  Round 4: filtered to that agent and the period's dates.
- **S3-5 [BE][FE] (J9, J13, Owner ruling 26 Sep (Lavish), L2)** Each team row carries
  `pipeline_value` and `pipeline_count` equal to the sums over the team's current member agents
  (S3-1 rules unchanged); the Pipeline cell links to Opportunities filtered to those agents and
  the month.

- **S3-6 [BE] (J9, N6, N7)** `pipeline_value` for a period row counts open opportunities whose
  `expected_close_date` is between `period_start` and `period_end`, both included; a split
  target's other periods do not share it.
- **S3-7 [BE] (J9, J13, Owner ruling 26 Sep 06:09, T2)** A team row's `pipeline_value` counts an
  open opportunity of agent A only when A is a member of the team on the opportunity's
  `expected_close_date`.

## S4. Commission tiers

- **S4-1 [BE] (J10, Owner ruling 26 Sep, G6)** Create and update accept `commission_method` and
  `tiers: [{from_pct, rate, bonus_amount}]`; `from_pct` must be unique per target and at least 0;
  method `none` with tiers is 422, and `marginal` or `retroactive` without tiers is 422.
- **S4-2 [BE] (J10)** Flat: one tier `{0, 2.5}`; target 100,000, achieved 104,250.50 gives
  commission 2,606.26.
- **S4-3 [BE] (J10)** Marginal accelerator: tiers `{0, 2}`, `{100, 4}`; target 100,000, achieved
  120,000 gives 2,000 + 800 = 2,800.00.
- **S4-4 [BE] (J10)** Retroactive: the same tiers and figures give 4,800.00; achieved 99,999.99
  gives 2,000.00 (100% not reached).
- **S4-5 [BE] (J10)** Bonus: tier `{100, 2, bonus 500}` pays 500 at 100.00% and 0 at 99.99%, once
  per period.
- **S4-6 [BE] (J10, G6)** Quantity: tiers `{0, 1.50}` on a quantity target, achieved 1,200 units,
  gives RM 1,800.00.
- **S4-7 [BE] (J10)** Each period row returns `commission_earned`, `bonus_earned` and
  `commission_breakdown` (per tier: slice, rate, amount); a `none` target returns nulls.
  Duplicate copies tiers.
- **S4-8 [FE] (J10)** The modal's Commission section offers method (None, Higher rate above each
  threshold only, Highest rate on everything) and a tier editor (add, remove, reorder by from %);
  the unit label follows the metric (% of RM, or RM per unit).
  Round 4 (N9): the method is a dropdown (S4-11).
- **S4-9 [FE] (J10)** The Commission column shows commission plus bonus, with a popover of the
  breakdown; `none` shows a dash.
- **S4-10 [BE][FE] (J10, J13, Owner ruling 26 Sep (Lavish), L2, T4)** Tiers on a team target work
  exactly as on an agent target and give one team commission figure per period, shown on the team
  row as "Team pool"; it is never split to agents and never added to any agent's commission.

- **S4-11 [FE] (J10, Owner ruling 26 Sep 06:01 (Lavish), N9)** How tiers pay is a
  `SearchableSelect` with None, Higher rate above each threshold only, and Highest rate on
  everything, on the Set target modal and the target page; no segmented buttons.
- **S4-12 [BE][FE] (J10, J13, Owner ruling 26 Sep 06:09, R5, T3, T4)** "Highest rate on
  everything" (`retroactive`) is selectable on agent, team, child and dealer targets and ships
  in S4 (S4-4's golden numbers). The team form has two tier tables: **Team pool tiers** on the
  team target (computed on the summed team figure and the team's achieved) and **Agent tiers**,
  copied to every child on save; a child's tiers can then be changed on its own page without
  touching the others.

## S5. Per-contact WhatsApp broadcast

- **S5-1 [BE] (J11, Owner ruling 26 Sep, G7, G8)** `POST /api/v1/sales/recipients` creates a
  recipient with `contact_id`, `follows_kind` (`agent`, `dealer`, `team`) and its subject,
  schedule (`frequency`, `weekday` or `day_of_month`, `send_time`, `timezone`) and content flags;
  weekly without a weekday or monthly without a day is 422; the same contact following the same
  subject twice is 409.
- **S5-2 [BE] (J11, G6, G8)** Defaults when omitted: `show_commission` true for agent, false for
  dealer and team; `show_pipeline` true for agent and team, false for dealer; `show_breakdown`
  false; `enabled` false; weekly, Monday, 09:00, Asia/Kuala_Lumpur.
- **S5-3 [BE] (J12, G7)** `next_run_for` golden table: weekly Monday 09:00 computed on Monday 09:01
  gives next Monday; monthly last day from 31 Jan gives 28 Feb (29 in a leap year); monthly 15 at
  08:00 KL is stored as 00:00 UTC; enabling a recipient sets `next_run_at`, disabling clears it.
- **S5-4 [BE] (J12)** The seeded `sales_target_broadcast_runner` task sends for every enabled
  recipient whose `next_run_at` has passed, one message each, then advances `next_run_at`.
- **S5-5 [BE] (J12, G8)** Golden text for three recipients: an agent with commission shown, the
  same agent with commission hidden (no commission line at all), and a dealer (own figures only,
  no commission, no pipeline); a team recipient gets totals plus one line per agent.
- **S5-6 [BE] (J12, G8)** A dealer recipient's message never contains another customer's or any
  agent's figures; an agent recipient's never contains another agent's.
- **S5-7 [BE] (J12)** A recipient whose contact has `outbound_enabled = false` is skipped and
  counted in the run summary; no send is attempted.
- **S5-8 [BE] (J12)** Every attempt writes an `integration_log` row on success AND failure with
  `business_table = "sales_target_recipients"` and `business_id` = the recipient id.
- **S5-9 [BE] (J12)** Sends go through `send_text_or_template(..., use_case="sales_target_progress")`;
  the use case is in `TEMPLATE_DEFAULT_USE_CASES`.
- **S5-10 [BE] (J12)** Running the handler twice for the same due time sends once.
- **S5-11 [BE] (J11, G9)** `POST /sales/recipients/{id}/send-now` and `GET .../preview` are gated by
  `sales.targets.edit`; recipients CRUD by `sales.targets.view|edit`.
- **S5-12 [FE] (J11)** Recipients tab: DataGrid (contact, follows, schedule in words, shows,
  enabled, next send); modal with a searchable contact select, follows select, schedule fields
  that appear for the chosen frequency, content switches; Preview renders the golden text; Add
  suggested lists agents with a contact and dealers with a primary contact, disabled; Send now
  toasts the recipient's name.
  Round 4 (N12, N13): this grid lives on the contact's Sales updates tab (S5-15), without the
  Contact column; Add suggested is dropped (S5-16); follows and how often are dropdowns.
- **S5-13 [E2E] (J11, J12)** Add a recipient, preview, Send now against a stubbed Respond client;
  the Respond Outbox shows the row; 1280 and 375.
  Round 4: starting from Internal Users, open a contact, then its Sales updates tab.
- **S5-14 [BE][FE] (J11, J12, Owner ruling 26 Sep (Lavish), L2)** A `team` recipient takes an
  optional `sales_team_id`: set, it receives that team's target figures plus one line per member
  agent (round 5, T2: the agents who were members during the period shown); null, it receives every agent (the round 2 behaviour). A team recipient never receives
  another team's lines. The recipient modal shows a searchable team select, clearable, under
  "Follows: Team" (empty = "All agents").
- **S5-15 [BE][FE][E2E] (J11, Owner ruling 26 Sep 06:01 (Lavish), N12)** A contact's record
  (`/user-management/contacts/{id}`, opened from Internal Users or the contacts list) has a
  **Sales updates** tab after Chat when the `sales` module is on and the viewer holds
  `sales.targets.view`; it is absent otherwise. It lists that contact's recipient rows, one line
  each (Follows, When, Sees as pills with "+N", Enabled, Next send), with Add, and per row Edit,
  Preview, Send now and deferred delete; Add, Edit and Send now need `sales.targets.edit`. `GET
  /sales/recipients?contact_id=...` returns only that contact's rows. The Targets page has no
  Recipients tab.
- **S5-16 [BE][FE] (J11, N13)** There is no Add suggested button anywhere. The list response for a
  contact carries `suggested_follow`: the agent whose `contact_id` is this contact, else the
  dealer with a target for which it is the primary contact, else null; Add opens with Follows
  preset to it, changeable. Follows, How often, weekday and day pickers are `SearchableSelect`
  (N8).

## S6. Sales teams and team targets (built second, right after S1)

Owner ruling 26 Sep (Lavish), L2 and L4. Written to round 3 recommendations T1 (new `sales_teams`
table, not the existing `teams`), T2 (one team per agent, current membership), T3 (a team target
is set on its own, not split from or summed from agent targets) and T4 (team commission is a
figure only, S4).

Round 4 (Owner ruling 26 Sep 06:01 (Lavish), N2, N5): S6 is now built **first**, teams only;
S6-4 to S6-7 and S6-10 (team targets) build in S1's lane, and S6-12 and S6-13 are added.

- **S6-1 [BE] (J13)** `POST /api/v1/sales/teams` with `{name, sales_agent_ids}` creates a team and
  its members; a blank name is 422; a second team with the same name (case-insensitive) in the
  company is 409. `GET /sales/teams` lists teams with member count; `GET /sales/teams/{id}`
  returns members as agent code and name.
- **S6-2 [BE] (J13, T2)** `PUT /sales/teams/{id}/members` with `{sales_agent_ids}` sets the member
  list; an agent who was in another team of the same company is moved (the response names the
  team they left); an agent is never in two teams of one company.
  Round 5 (T2): "never in two teams" means never two memberships on the same day; the move is
  dated (S6-14).
- **S6-3 [BE] (J13)** `PATCH` renames or sets `is_active`; an inactive team gets no "No target" row
  and cannot be picked for a new target, and its existing targets still show. `DELETE` hard
  deletes the team, its memberships and its targets (with their periods, scope and tiers); the
  agents themselves are untouched.
- **S6-4 [BE] (J13, L2)** `POST /sales/targets` with `subject_kind: "team"` and `sales_team_id`
  creates a team target under every S1 rule (periods, scope, metric, basis); `team` without a
  team, or with an agent or customer id as well, is 422; an inactive team is 422.
  Round 5 (T3): the payload carries `agent_figures` and the team figure is their sum (S1-27);
  a `target_value` for the team itself is not accepted.
- **S6-5 [BE] (J13, L2)** Team achievement golden set: team N with agents A and B; orders of A,
  B and C (not in N) in October. An amount-ordered team target counts exactly A's and B's
  non-cancelled October lines; a quantity-delivered, category-scoped team target counts A's and B's
  confirmed units in that category only; the team figure equals the sum of the same target
  evaluated on A and on B alone.
- **S6-6 [BE] (J13, T2)** Moving B from team N to team S changes N's and S's achieved figures for
  every period, past ones included (current membership); an agent with no team counts for no team
  target.
  Round 5 (Owner ruling 26 Sep 06:09, T2): reversed by the ruling. A move changes only orders
  dated on or after the move date (S6-14); past periods keep their figures. The "no team counts
  for no team target" part stands.
- **S6-7 [BE] (J13)** `GET /sales/targets?month=2026-10-01&subject=team` returns one row per team
  target period covering October, with achieved and %, plus one `target_id: null` row per active
  team with no covering target. `GET /sales/targets?subject=agent&sales_team_id=...` returns only
  that team's agents.
- **S6-8 [BE] (J13, G9)** `sales.teams.view|add|edit|delete` gate each team route (403 without);
  team targets use the `sales.targets.*` slugs of S1-13. Another company's teams are invisible
  under company scope.
- **S6-9 [FE] (J13, L1, L2)** The Sales group gains **Sales Teams** (`moduleKey: 'sales'`). The
  Sales Teams page is a DataGrid (name, agents, active, targets this month) with **Add team**;
  create and edit are one modal (name, a searchable multi-select of active agents, each labelled
  with their current team); the team detail page shows Members and Targets sections, each with an
  empty state and a next-step CTA (Add agents, Set target), `RecordNavigation`, and deferred
  delete with no dialog.
  Round 4 (N2, N5): read with S6-12 and S6-13; the "targets this month" column arrives with S1.
- **S6-10 [FE] (J13, L2, L3)** The Targets page has a **Teams** tab (between Agents and Dealers)
  with the Agents columns plus an Agents count; "No target" rows with Set target; the header Set
  target on this tab presets "Target for: Team". The Agents tab gains a clearable searchable Team
  filter.
  Round 4 (N5): built in S1; the Teams tab is the landing and opens first (S1-22); the Team
  filter also offers "No team".
- **S6-11 [E2E] (J13)** From `/`, Sales > Sales Teams; create "North" with two agents; move one
  agent to a second team; on Targets, set a team target for North from the header CTA; its
  achieved equals the sum of its agents' rows for the same basis; 1280 and 375.
  Round 5 (T2, T3): the team target is set by typing each agent's figure (S1-27); the move shows
  Moves on (S6-15).

- **S6-12 [FE][E2E] (J13, Owner ruling 26 Sep 06:01 (Lavish), N2)** Sales > Sales Teams follows
  the Users & Access > Teams concept: `PageHeader` "Sales teams" with **Add team**, a search box,
  and a DataGrid with one line per team (name, agents as a `PillOverflow` with "+N", Active badge,
  targets now from S1); the whole row opens the team page. Add and Edit are one modal: Name,
  Agents (`SearchableMultiSelect` of active agents, each option labelled with the team they are
  in now), Active. Empty state "No sales teams yet" with Add team. No tree and no drag nesting.
- **S6-13 [FE][E2E] (J13, N5)** `/sales/teams/{id}` shows the team name in the header with the
  Active badge and agent count in the meta strip, Set target (from S1), Edit and deferred Delete,
  and `RecordNavigation`. Sections, in order, always rendered: **Team targets** (from S1; one line
  per target active on the date, empty state "No team target" with Set target) and **Agents**
  (one line per member agent with their targets from S1, "No target" with Set target presetting
  that agent; empty state "No agents in this team" with Add agents). Edit changes the name in
  place and adds Add agents and a remove control in the Agents section; nothing moves. In the
  S6 lane, before S1, the Team targets section is absent and the Agents rows show agent and code
  only.

- **S6-14 [BE] (J13, Owner ruling 26 Sep 06:09, T2, V1)** `team_members` has `valid_from` and
  `valid_to` (dates, both optional). `PUT /sales/teams/{id}/members` with `{sales_agent_ids,
  moves_on}`: an agent in no team gets a row with `valid_from` empty (V1); an agent in another
  team gets that row closed at `moves_on - 1` and a new row from `moves_on` (default today; a
  future date is 422). An agent left out of the list gets `valid_to = today`, and the row stays.
  One open membership per agent per company (unique), and no two memberships of one agent in
  one company overlap (422). Golden set: A in N, moved to S on 15 Oct; A's orders of 10 Oct count
  for N's October team target and not S's; 15 Oct and later count for S and not N; S6-5's equality
  holds for any period with no move in it.
- **S6-15 [FE][E2E] (J13, T2)** The team modal shows **Moves on** (a date, default today,
  not clearable) only when a picked agent is in another team, with that team named on the
  option. The team page's Agents section lists members on the Active on date; an agent who left
  during the period shown keeps a muted line with a "Left 14 Oct" pill, so the team's achieved
  figure is explained on screen. E2E: move an agent, see the pill, see the old team's past period
  unchanged.
- **S6-16 [BE] (J13, Owner ruling 26 Sep ~13:25Z, W1)** `sales.teams.leader_sales_agent_id`
  (nullable, foreign key to `sales_agents` ON DELETE SET NULL; migration `sales_0002_team_leader`
  on `sales_0001_teams`). `POST /sales/teams` and `PATCH /sales/teams/{id}` take
  `leader_sales_agent_id`: on PATCH, sent sets it and `null` clears it, left out keeps it. A
  leader who is not among the team's agents is placed in the team the way Add agents places
  anyone (from the beginning for a first team; a Moves on and a `moved` entry when they come
  from another team). Another company's agent is 422. When the leader is removed from the team
  or moves to another team, that team's leader clears. The database holds the rule for any
  writer: `trg_sales_teams_leader_is_member`, deferred constraint triggers on `sales.teams` and
  `sales.team_members`, refuses a leader without an open membership row in the team at commit.
  List rows and the team read return `leader_sales_agent_id`; the team read adds `leader_label`.
  Gated by `sales.teams.edit` (no new slug). Upgrade and downgrade both run.
- **S6-17 [FE][E2E] (J13, W1)** The list row draws the leader's pill first, reading
  "<agent> (Leader)". The team page names the leader on a line under the team name ("Leader:
  <agent>", or "No leader") and tags the leader's row "Leader". The Add team modal and the
  team page's in-place edit have a clearable **Leader** `SearchableSelect` offering only the
  picked agents (in edit: the agents kept plus those being added); unpicking or removing the
  leader clears it. 1280 and 375.
- **S6-18 [BE][FE] (J13, Owner ruling 26 Sep ~13:05Z, W2)** The team page lists each agent once:
  an agent who left and came back shows once, from the stay in force on the date shown (active);
  when every stay in the month has ended, from the last one ("Left <date>"). The earlier stays
  stay in `sales.team_members`.

## S7. Dealer targets (built third, round 4)

Split out of S1 by round 4 (plan section 4) so S1 stays thin. S1-11 and J5 build here.

- **S7-1 [BE] (J5)** The S7 migration adds `sales_targets.customer_id` and widens `subject_kind`
  to `agent`, `team` or `dealer`; `POST /sales/targets` with `subject_kind: "dealer"` and
  `customer_id` creates a dealer target under S1-19; S1-11's counting and 422 rules apply.
- **S7-2 [FE] (J5, N4, N8)** The Targets page gains the **Dealers** tab after Agents: one line per
  dealer with a target active on the date, the S1-21 cells; "Target for: Dealer" in the modal
  with a searchable dealer select (code - name).
- **S7-3 [E2E] (J5)** From `/`, Sales > Targets > Dealers; set a dealer target from the header;
  it shows one line; its page opens; 1280 and 375.

## Round 5 (answers to R1 to R5 and T1 to T5) additions (nothing deleted)

Every earlier AC stands with its id and text; round 5 appended "Round 5" notes to J13, the Team
achieved value definition, S1-7, S5-14, S6-2, S6-4, S6-6 and S6-11, added the definitions
"Delivered, by DO date" and "Team target figure", and added S1-26 to S1-29, S3-7, S4-12, S6-14
and S6-15. S6-6's "past ones included" is reversed by T2 (its note says so); nothing is
removed. Lanes after round 5 (T5, plan section 6): wave 1 **S6** builds S6-1 to S6-3, S6-8,
S6-9, S6-12 to S6-15 and S1-17; wave 2 **S1** (the rest of S1 except S1-11, plus S1-26 to S1-29,
S6-4 to S6-7 and S6-10) beside **S2**; wave 3 **S7**, **S4** (with S4-12), **S3** (with S3-7) and
**S5** side by side, S5 merging last. Nothing is deferred.

## Round 4 (second Lavish review) additions (nothing deleted)

Every earlier AC stands with its id and text; round 4 appended "Round 4" notes to J1, J2, J3,
J5, J6, J9, J11, J13, the Period definition, S1-1, S1-2, S1-5, S1-6, S1-13, S1-15 to S1-18,
S2-5, S2-8, S2-10, S3-4, S4-8, S5-12, S5-13, S6-9 and S6-10, and added J14, S1-19 to S1-25,
S2-15, S2-16, S3-6, S4-11, S5-15, S5-16, S6-12, S6-13 and S7-1 to S7-3. Lanes after round 4:
S6 builds S6-1 to S6-3, S6-8, S6-9, S6-12, S6-13 and S1-17; S1 builds the rest of S1 except
S1-11, plus S6-4 to S6-7 and S6-10; S7 builds S1-11 and S7. Build order S6, S1, S7, S2, S3, S4,
S5 (plan section 6).

## Round 3 (Lavish) additions (nothing deleted)

Every round 2 AC above stands with its id and text. Round 3 only appended the (Lavish) notes to
J1 and J2 and added J13, S1-17, S1-18, S3-5, S4-10, S5-14 and S6-1 to S6-11. Slice ids are stable;
the build order is S1, S6, S2, S3, S4, S5 (plan section 6).

## Round 1 criteria carried forward (nothing deleted)

Every round 1 AC is kept, as rewritten to the ruling or as noted.

| Round 1 | Now | Change |
| --- | --- | --- |
| S1-1 | S1-1, S1-2 | monthly `period_month` replaced by validity (G3) |
| S1-2 (409 duplicate) | S1-13 note | overlapping targets allowed (plan 3.1); 409 retired by G4's flexibility |
| S1-3 | S1-6 | |
| S1-4 | S1-7, S1-8 | basis added (G1) |
| S1-5 | S1-13 | |
| S1-6 | S1-4, S1-13 | |
| S1-7, S1-8, S1-9 | S1-15 | |
| S1-10 | S1-16 | |
| S1-11 | S1-14 | |
| S2-1 (copy last month) | S1-12 | Duplicate replaces copy month, since targets now span months (G3) |
| S2-2, S2-3 | S1-11 | |
| S2-4 (quantity needs a category) | S1-3, S1-9 | quantity on all products allowed (G4) |
| S2-5 | S1-15 | Duplicate button replaces Copy last month |
| S2-6, S2-7 | S1-15 | |
| S3-1, S3-2 | S4-2, S4-5, S4-7 | flat % and incentive are now tier cases (G6) |
| S3-3 | S4-9 | |
| S4-1 | S2-3, S2-7 | portal create added (G9) |
| S4-2 | S2-6, S2-7 | stages from the status engine (G5) |
| S4-3, S4-4 | S2-8 | |
| S4-5, S4-6, S4-7 | S2-12, S2-13, S2-11 | |
| S4-8 | S2-14 | |
| S5-1, S5-2, S5-3 | S3-1, S3-2, S3-4 | probability from the stage row (G5) |
| S6-1 | S5-1, S5-4 | global schedule replaced by per contact (G7) |
| S6-2 | S5-5 | |
| S6-3 | S5-7 | |
| S6-4 | S5-8 | business table is now the recipient |
| S6-5 | S5-9 | |
| S6-6 | S5-10 | |
| S6-7 | S5-11 | send now per recipient (G8) |
| S6-8 | S5-12 | |
| S6-9 | S5-13 | |
