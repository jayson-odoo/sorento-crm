# UAC: sales target progress over the chat, slice 1 read-only (lane SALES-TARGET-CHAT)

Plan: `PLAN-sales-target-chat-25oct.md` (card v1 + owner answers 25 Oct: Q1 c, Q2 b, Q3 a; Q4 a and
Q5 a are crew defaults the owner may overrule). Slice 2 (log an opportunity) has its own UAC section,
written after the slice 1 hand test.

Each criterion names the test that proves it (BE = pytest on Postgres, MCP = pytest in
`sorento_crm_mcp/tests`, CB = pytest in `sorento_crm_backend/tests/chatbot`). Figures in the examples
are the card's real dev-copy figures; tests seed their own chain (CI has no data).

## Journey

**Dealer.** A dealer's contact (linked by staff to the dealer's customer accounts, and granted
"Sales target" in its contact access) writes on WhatsApp "how is my target this quarter?" (or in
Malay / Chinese). The system already knows who they are, which accounts are theirs, today's date and
their language. The bot answers, one fact per line, for every live dealer target that counts only
their own accounts: the period, which accounts count, what has been achieved (provisional, incl. tax,
up to the latest order date), the tier reached with its rate, and the next tier with its rate and the
amount still to go. No rebate amount in RM. If they name a period ("Q3", "last quarter", a month),
that period is answered instead. If they name another dealer, the bot refuses as it does today for
any figure that is not theirs. The dealer makes no decision; they end holding the gap to the next
tier. Nobody else is told anything.

**Salesperson.** A salesperson's contact (linked to their sales agent(s), granted "Sales target")
writes "my target?". The bot answers with three blocks: their own target(s), their team's target(s)
for teams they are in, and the targets of the dealers they own, the dealer with the smallest gap to
its next tier first. Their own target also shows the open opportunities closing within it. If they
name one of their dealers, only that dealer's targets come back; a dealer they do not own is
refused. They end knowing which dealer to push. Nobody else is told anything.

**Anyone else**, or a contact without the "Sales target" grant, gets the fixed "not enabled" line
and no figures.

## T1. Who sees which target (contact scoping)

- T1-1 [BE] A dealer contact gets only dealer targets whose EVERY counted account
  (`sales.target_accounts`) is one of the contact's linked customers. A target with one unlinked
  counted account is not returned at all. `test_dealer_sees_only_fully_linked_targets`.
- T1-2 [BE] A dealer contact never gets an agent or team target, even one whose agent owns their
  account. `test_dealer_never_gets_agent_or_team_targets`.
- T1-3 [BE] A salesperson contact gets the agent targets of every agent linked to the contact
  (`agents_for_contact`). `test_salesperson_gets_own_agent_targets`.
- T1-4 [BE] A salesperson contact gets the team targets of teams where one of their agents is a
  member on the as-of date (dated `sales.team_members`); a stay that ended before it does not count.
  `test_salesperson_gets_team_target_by_dated_membership`.
- T1-5 [BE] A salesperson contact gets the dealer targets whose EVERY counted account is owned by
  one of their agents (`customers.sales_agent_id`); a dealer target with an account owned by another
  agent is not returned. `test_salesperson_gets_owned_dealer_targets_only`.
- T1-6 [BE] Naming a customer narrows the answer to targets counting that customer, inside the
  rules above; a customer outside them answers 403 `customer_not_permitted` (same code as the sales
  report). `test_named_customer_narrows_and_foreign_customer_403`.
- T1-7 [BE] A contact that is staff (not salesperson, not dealer) or unclassified gets no targets
  and the not-allowed outcome. `test_staff_and_unclassified_get_no_targets`.
- T1-8 [BE] Without the per-contact "Sales target" grant the route answers 403 and returns no
  figure; the grant is off by default for every contact. `test_route_requires_sales_target_grant`.
- T1-9 [BE] Targets of another company are never returned, whatever the links.
  `test_other_company_targets_never_returned`.
- T1-10 [BE] The route takes `contact_id` and `space_id` together (one without the other is a 422,
  as the sales report does) and is callable with the integration API key.
  `test_route_contact_and_space_required`.

## T2. What each target line holds

- T2-1 [BE] Default period = the period of each live target that contains the as-of date (today);
  with `date_from`/`date_to`, the periods overlapping that span. Quarterly and yearly targets are both
  listed. `test_default_current_period_and_named_span`.
- T2-2 [BE] A target replaced by another (`replaced_by_target_id`) is listed like any other, as the CRM
  target list does; no special handling in slice 1. `test_replaced_target_listed`.
- T2-3 [BE] Achieved value equals the engine's own figure for that period (the same number the CRM
  target page shows; no second achievement query). `test_achieved_matches_target_detail`.
- T2-4 [BE] Next tier: the lowest tier threshold above the achieved value, as RM (pct tiers resolve
  to % x period target; amount tiers as is), with its rate and any additional rate at the same
  threshold, and the gap = threshold - achieved. Example: achieved 47,407.44, tiers 50,000 3% /
  70,000 4% / 90,000 5% gives next tier 1, 3%, gap 2,592.56. `test_next_tier_gap_amount_tiers`,
  `test_next_tier_gap_pct_tiers`.
- T2-5 [BE] Tier reached: the highest tier at or below the achieved value, with its rate (and
  additional rate); none when below the first tier. Above the top tier: tier reached = top, no next
  tier. `test_tier_reached_and_top_tier`.
- T2-6 [BE] No RM incentive / rebate / commission amount appears anywhere in the response (owner
  Q2 b). `test_no_incentive_amount_in_response`.
- T2-7 [BE] Points targets: with a point ratio in force on the period's last day (the engine's
  `ratio_on`), thresholds, achievement and gap are in RM at that ratio, and each threshold also carries
  its points figure; with no ratio, the line carries `ratio_missing`, the target in points, achieved in
  RM, and no tier, next tier or gap. `test_points_target_with_and_without_ratio`.
- T2-7b [BE] A tier paid per account ("A/C I- 3%", stored as per-account rates) shows its rate per
  account label ("3% on A/C I"); a tier with one rate for all accounts shows that rate.
  `test_rate_per_account_label`.
- T2-8 [BE] Dealer lines carry `provisional = true` and the counted account labels (A/C I, A/C III,
  ...); every line carries the as-of date = the latest order date of the company's sales orders.
  `test_dealer_line_provisional_and_accounts`.
- T2-9 [BE] Agent target lines carry the open opportunities closing within the target (the portal
  "My target" figure, `agent_progress`). `test_agent_line_carries_open_pipeline`.
- T2-10 [BE] The dealer block for a salesperson is ordered by gap to next tier, smallest first;
  lines with no next tier last. `test_dealer_block_smallest_gap_first`.
- T2-11 [BE] The response carries no UUID: subjects by name / code, accounts by code and label.
  `test_response_has_no_ids`.

## T3. MCP tool and reply text

- T3-1 [MCP] A read-only tool `crm_sales_target_progress` wraps the route, passes contact and
  space, restricted by the "Sales target" reveal key. `test_sales_target_tool_spec`.
- T3-2 [MCP] Dealer reply shape (card A):
  `Sales target Q4 2026 (1 Oct to 31 Dec)` / `Counts: A/C I` /
  `Achieved: RM 17,414.05 (provisional, incl. tax, to 23 Oct)` /
  `Next tier: Tier 1, 3% at RM 85,000.00, RM 67,585.95 to go`. `test_present_dealer_target`.
- T3-3 [MCP] Missed period (card B): `Tier 1 (3%) at RM 50,000.00: not reached, short RM 2,592.56`.
  `test_present_closed_period_not_reached`.
- T3-4 [MCP] Points with no ratio (card E): target in points, achieved in RM, and the fixed line
  "Points are not converted yet, so I can't compare.". `test_present_points_without_ratio`.
- T3-5 [MCP] Salesperson (card F, G): own block (or "No sales target is set for you for <period>."),
  team block when present, dealer block one line per dealer smallest gap first:
  `BKIN ELECTRICAL SDN BHD [A/C I]: RM 5,275.80 of RM 50,000.00 (Tier 1), RM 44,724.20 to go`.
  `test_present_salesperson_blocks`.
- T3-6 [MCP] Additional rates read "6% + additional 1%". `test_present_additional_rate`.

## T4. Chat routing

- T4-1 [CB] A target question from a granted dealer or salesperson routes to
  `crm_sales_target_progress` (sales domain, new status value), never to the sales report.
  `test_target_question_routes_to_target_tool`.
- T4-2 [CB] Without the grant the bot answers the fixed not-enabled line and calls no tool.
  `test_target_without_grant_refused`.
- T4-3 [CB] A named period reaches the tool as `date_from`/`date_to`.
  `test_target_named_period_passed`.
- T4-4 [CB] Allow-list, tool-domain map and brand-scope contract include the new tool (the existing
  contract tests stay green). `test_brand_scope_contract` (existing), `test_target_tool_allowed`.
- T4-5 [CB] A dealer naming another dealer gets today's "only your own accounts" refusal.
  `test_dealer_other_dealer_refused`.

## T5. Parser gate

- T5-1 The parser recognises target questions (en / ms / zh, "target", "sasaran", "目标",
  "tier", "rebate") as the new status in the `sales` domain on the per-PR parser gate, and the gate's
  existing rows do not regress. Evidence: gate output in the PR, OpenAI eval key only, per-PR gate
  only (no full hidden run without the owner's OK), never the Gemini org key.

## Out of slice 1

Creating an opportunity in chat (slice 2, salespeople only, read-back + "Reply YES to save"); the
WhatsApp achievement broadcast; any RM incentive amount; dealer-created opportunities.
