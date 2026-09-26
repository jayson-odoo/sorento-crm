# UAC: sales targets, opportunities and the WhatsApp achievement broadcast (issue #1170)

Plan: `documentation/plans/sales/PLAN-sales-targets-opportunities-26sep.md`. Mockup:
`documentation/plans/sales/mockups/sales-targets.html`. Slice 1 of #1170 (a sales agent on a
customer) shipped in PR #1177 and is not repeated here.

Tags: `[BE]` pytest, `[FE]` vitest, `[E2E]` recorded agent-browser run (no new Playwright spec),
`[T]` text or copy check. Every AC traces to a journey step (J1 to J9). Every AC marked
"(G#)" depends on the answer to that grill question in the plan; the AC is written to the
recommended answer and is rewritten if the owner rules otherwise.

## Journey

Actors: the **sales manager** (a CRM user, today the owner or a sales admin) who sets targets and
logs opportunities; the **sales agent** and the **dealer**, who have no CRM login (sales agents
are not users, ruling 14 Aug 2026, `app/models/sales_agent.py:1-17`) and meet this feature only as
a WhatsApp message.

- **J1. First screen.** From `/`, the manager expands **Sales** and clicks **Targets**. The page
  opens on the current month, **Agents** tab, one row per active sales agent: Target, Achieved,
  % achieved, Pipeline, Commission. The system already knows every agent, every sales order and
  the month; the manager is asked for nothing to see where the team stands. An agent with no
  target this month shows "No target" and a **Set target** action on the row.
- **J2. Set a target.** **Set target** opens a modal with the agent and month already filled. The
  one decision is the number. Measure defaults to Amount (RM); Quantity is one switch away and,
  when chosen, asks for a product category (G4). Commission % and Incentive (RM) are optional and
  pre-fill from the agent's previous month. Save closes the modal and the row shows the target.
- **J3. Copy last month.** At the start of a month with no targets yet, **Copy last month** creates
  this month's targets from last month's in one click (same measure, value, commission and
  incentive); the manager then edits the few that change.
- **J4. Dealers.** The **Dealers** tab lists every dealer (customer) that has a target this month,
  with the same columns and an **Add dealer target** button whose modal asks for the dealer first
  (searchable, by code and name), then the same fields as J2.
- **J5. Log an opportunity.** On a customer's detail page an **Opportunities** section lists that
  customer's open and closed opportunities (empty state: "No opportunities yet" plus **Log
  opportunity**). The modal asks for a title, expected amount, expected close month and product
  interest (optional category and a short note). Stage starts at New. The agent is taken from the
  customer (`customers.sales_agent_id`), never asked.
- **J6. Move it along.** From **Sales > Opportunities** (DataGrid, filter by stage, agent,
  customer, close month) or the customer section, the manager changes the stage: New, Qualified,
  Proposal, Negotiation, Won, Lost. Lost asks for a reason. Won optionally links the sales order
  that came of it.
- **J7. See the roll-up.** Back on Targets, each agent's **Pipeline** column is the weighted value
  of that agent's open opportunities expected to close this month (expected amount x stage
  probability). Achievement never includes opportunities; it comes from sales orders only.
- **J8. The broadcast.** Every Monday at 09:00 Malaysia time (G7) each agent with a target and a
  WhatsApp contact, and each dealer with a target and a primary contact, receives one WhatsApp
  message: this month's target, achieved so far, % and the gap, plus the days left. The manager
  can see every send in the Respond Outbox and can press **Send now** on a row to send that one
  message immediately.
- **J9. Month end.** On a closed month, the Commission column shows commission earned (commission
  % x achieved amount) plus the incentive when achievement reached 100%.

## Definitions the ACs rely on

- **Achieved amount** (G1): the sum of `sales_order_lines.line_total` over lines whose order is
  not `cancelled` and whose `line_status` is not `cancelled`, where `sales_orders.order_date`
  falls inside the target's month. `line_total` is the AutoCount "Total (Inc)" figure, so the
  amount is tax inclusive. This is the sales report's "ordered" figure
  (`app/services/sales_report_service.py:202-247`) bucketed by `order_date` instead of
  `coalesce(required_date, order_date)`.
- **Achieved quantity**: the sum of `qty_ordered` under the same filter, restricted to products in
  the target's category.
- **Attribution** (G2): an agent target counts orders whose `sales_orders.sales_agent_id` is that
  agent; a dealer target counts orders whose `sales_orders.customer_id` is that dealer.
- **Stage probability** (fixed, G5): New 10%, Qualified 25%, Proposal 50%, Negotiation 75%,
  Won 100%, Lost 0%.

## S1. Agent amount targets with live achievement

- **S1-1 [BE] (J2)** `POST /api/v1/sales/targets` with `{sales_agent_id, period_month, measure:
  "amount", target_value}` creates a row and returns it with `achieved_value`, `achieved_pct`,
  agent code and name. `period_month` not on the 1st of a month is 422.
- **S1-2 [BE] (J2)** A second target for the same agent, month, measure and category is 409 with a
  message naming the agent and month.
- **S1-3 [BE] (J1)** `GET /api/v1/sales/targets?period_month=2026-09-01&subject=agent` returns one
  row per active sales agent in scope, including agents with no target (`target_id: null`,
  `target_value: null`), each with its achieved amount.
- **S1-4 [BE] (J1, G1, G2)** Achievement golden set: seeded orders for agent A in September (one
  open, one fulfilled, one cancelled order, one open order with a cancelled line, one order dated
  31 Aug, one order with `order_date` null) produce exactly the sum of the non-cancelled lines of
  the September orders. Agent B's orders never count for A.
- **S1-5 [BE] (J1)** A user without `sales.targets.view` gets 403; without `sales.targets.add` the
  POST is 403. An agent or order from another company is invisible under company scope.
- **S1-6 [BE] (J2)** `PATCH` changes value, commission and incentive; `DELETE` hard deletes
  (deferred-action countdown on the FE, no dialog).
- **S1-7 [FE] (J1)** Targets page renders the agents grid for the current month with a month
  picker; an agent without a target shows "No target" and a Set target action; loading, empty
  (no active agents) and error states render.
- **S1-8 [FE] (J2)** The Set target modal pre-fills agent and month, defaults measure to Amount,
  and the payload carries the typed value; commission and incentive pre-fill from the previous
  month when one exists.
- **S1-9 [FE] (J1)** Achieved over target renders as a percentage with a bar; over 100% is shown
  in the success tone and the number is not capped.
- **S1-11 [BE][FE] (J1, G2)** Orders in the month with a null `sales_agent_id` are totalled in one
  "Unassigned" row at the foot of the Agents grid (no target, no actions), so unattributed sales
  are visible rather than silently dropped.
- **S1-10 [E2E] (J1, J2)** Sidebar Sales > Targets from `/`, set a target on one agent, reload,
  value persists; usable and unclipped at 1280 and 375.

## S2. Copy last month, dealer targets, quantity targets

- **S2-1 [BE] (J3)** `POST /api/v1/sales/targets/copy {from_month, to_month}` copies every target
  of `from_month` that has no counterpart in `to_month`, returns the count created, and is a
  no-op (count 0) when run twice.
- **S2-2 [BE] (J4)** A target with `customer_id` instead of `sales_agent_id` is accepted; one with
  both or neither is 422.
- **S2-3 [BE] (J4, G2)** A dealer target's achievement counts that customer's orders regardless of
  which agent is on the order.
- **S2-4 [BE] (J2, G4)** `measure: "quantity"` without `product_category_id` is 422; with it,
  achievement is the `qty_ordered` sum over products in that category only.
- **S2-5 [FE] (J3)** Copy last month is shown only when the month has no targets and the previous
  month has some; after it, the grid shows the copied rows.
- **S2-6 [FE] (J4)** Dealers tab lists dealer targets; Add dealer target asks for the dealer via a
  searchable, clearable select showing `code - name`, never a UUID.
- **S2-7 [FE] (J2)** Switching Measure to Quantity reveals a required category select and changes
  the unit label from RM to units.

## S3. Commission and incentive

- **S3-1 [BE] (J9)** Each target row returns `commission_earned = round(achieved_value x
  commission_pct / 100, 2)` for amount targets, and `incentive_earned = incentive_amount` when
  `achieved_pct >= 100` else 0. A quantity target returns `commission_earned: null` (G6).
- **S3-2 [BE] (J9)** Golden numbers: target 100,000, achieved 104,250.50, 2.5% and incentive 500
  give commission 2,606.26 and incentive 500; achieved 99,999.99 gives incentive 0.
- **S3-3 [FE] (J9)** Commission column shows earned commission plus incentive, with the incentive
  shown separately in the row's tooltip or detail; blank commission % shows a dash.

## S4. Opportunities on the customer

- **S4-1 [BE] (J5)** `POST /api/v1/sales/opportunities` with `{customer_id, title,
  expected_amount, expected_close_month}` creates stage `new`, stamps `sales_agent_id` from the
  customer, and returns agent code and name. A customer with no agent is accepted with a null
  agent.
- **S4-2 [BE] (J6)** `PATCH stage` accepts the six stages only; `lost` without `lost_reason` is
  422; `won` accepts an optional `sales_order_id` that must belong to the same customer (422
  otherwise).
- **S4-3 [BE] (J6)** `GET /api/v1/sales/opportunities` filters by stage, agent, customer and close
  month, paginated through the list-query contract.
- **S4-4 [BE] (J5)** Permissions `sales.opportunities.view|add|edit|delete` gate each route; company
  scope applies.
- **S4-5 [FE] (J5)** Customer detail renders an Opportunities section in both view and edit, with
  the empty state and Log opportunity CTA when there are none.
- **S4-6 [FE] (J6)** Opportunities DataGrid has fixed layout, resizable columns, stage shown as a
  `Badge`, `rowHref` to the opportunity detail, stage filter as a SearchableSelect.
- **S4-7 [FE] (J6)** Choosing Lost reveals a required reason field; choosing Won reveals an
  optional sales order select limited to that customer.
- **S4-8 [E2E] (J5, J6)** Log an opportunity on a customer, move it to Proposal, then Lost with a
  reason; the list reflects each step; 1280 and 375.

## S5. Pipeline roll-up on targets

- **S5-1 [BE] (J7)** Each agent row carries `pipeline_value` = sum over that agent's opportunities
  in stages new to negotiation with `expected_close_month` equal to the target month of
  `expected_amount x probability`, and `pipeline_count`.
- **S5-2 [BE] (J7)** Won and lost opportunities never add to `pipeline_value`, and no opportunity
  ever adds to `achieved_value`.
- **S5-3 [FE] (J7)** The Pipeline cell links to Sales > Opportunities filtered to that agent and
  month.

## S6. Scheduled WhatsApp broadcast

- **S6-1 [BE] (J8)** A `scheduled_tasks` row `sales_target_broadcast` (seeded by migration,
  weekly, Monday 09:00 Asia/Kuala_Lumpur, G7) runs a handler that sends one message per agent
  target of the current month to `sales_agents.contact_id`, and one per dealer target to the
  customer's primary `respond_contact_customers` contact.
- **S6-2 [BE] (J8)** The message text carries target, achieved, % and gap in RM (or units) and the
  days left in the month; the golden text is asserted for one agent and one dealer.
- **S6-3 [BE] (J8)** A recipient with no contact, or with `outbound_enabled = false`, is skipped
  and counted in the run summary; no send is attempted.
- **S6-4 [BE] (J8)** Every attempt writes an `integration_log` row on success AND failure with
  `business_table = "sales_targets"` and `business_id` = the target id.
- **S6-5 [BE] (J8)** Sends go through `send_text_or_template(..., use_case="sales_target_progress")`;
  the use case is in `TEMPLATE_DEFAULT_USE_CASES`, so outside the 24h window the approved template
  is used.
- **S6-6 [BE] (J8)** Running the handler twice on the same day sends nothing the second time
  (idempotent on target id + local date via `integration_log`).
- **S6-7 [BE] (J8)** `POST /api/v1/sales/targets/{id}/send-now` sends that one message and is gated
  by `sales.targets.edit`.
- **S6-8 [FE] (J8)** The row menu has Send now; the toast names the recipient; a target whose
  recipient has no contact shows the action disabled with the reason in its title.
- **S6-9 [E2E] (J8)** Send now on one agent target against the local Respond sandbox or a stubbed
  client; the Respond Outbox shows the row.
