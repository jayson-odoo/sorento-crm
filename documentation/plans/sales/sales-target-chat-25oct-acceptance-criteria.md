# UAC: sales target progress over the chat, slice 1 read-only (lane SALES-TARGET-CHAT)

Plan: `PLAN-sales-target-chat-25oct.md` (card v1 + owner answers 25 Oct: Q1 c, Q2 b, Q3 a; Q4 a and
Q5 a are crew defaults the owner may overrule). Slice 2 (log an opportunity) has its own UAC section,
written after the slice 1 hand test.

Each criterion names the test that proves it (BE = pytest on Postgres, MCP = pytest in
`sorento_crm_mcp/tests`, CB = pytest in `sorento_crm_backend/tests/chatbot`). Figures in the examples
are the card's real dev-copy figures; tests seed their own chain (CI has no data).

## Journey

**Dealer.** A dealer's contact (linked by staff to the dealer's customer accounts, and granted
"Sales target" in its contact access) writes on WhatsApp "how is my target this quarter?" (or asks in
Malay / Chinese; the reply text is English, as the sales report reply is today). The system already knows who they are, which accounts are theirs, today's date and
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
- T1-7 [BE] A contact that is staff (not salesperson, not dealer) or unclassified gets 403
  `sales_target_not_available` and no figure. `test_staff_and_unclassified_get_no_targets`.
- T1-8 [BE] Without the per-contact "Sales target" grant (`sales.sales_target`) the route answers 403
  `sales_target_not_enabled` and returns no figure; the grant is off by default for every contact
  (`FIELD_REVEAL_KEYS` carries `("sales.sales_target", "Sales target")`).
  `test_route_requires_sales_target_grant`.
- T1-9 [BE] Targets of another company are never returned, whatever the links.
  `test_other_company_targets_never_returned`.
- T1-10 [BE] `GET /api/v1/sales/target-progress` requires both `contact_id` and `space_id` (either
  missing is a 422 `contact_identity_required`) and is callable with the integration API key whose
  act-as user holds `sales.reports.view`; without that permission it is a 403.
  `test_route_contact_and_space_required`, `test_route_needs_sales_reports_view`.

- T1-11 [BE] (security S1) A contact whose linked CRM user is no longer ACTIVE, or is trashed, is
  refused with 403 `sales_target_not_available`, the revoke rule the chat report already follows
  (`chat_report.asker_of`, V1-CHATREPORT-REVOKE); a salesperson linked only through
  `sales_agents.contact_id` (no user) still gets through. `test_revoked_user_contact_refused`.
- T1-12 [BE] (security S2) `contact_id` / `space_id` are stripped before the both-required check: a
  blank or whitespace-only id is a 422 `contact_identity_required`. `test_blank_contact_ids_422`.

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

- T2-12 [BE] (review 3) A pct tier on a period whose target is 0 is reached only when its `from_pct` is
  100 or less, the engine's own rule (commission_service.py:124-128): tiers 100% / 120% on a 0 target
  give tier reached 1, not 2. `test_pct_tiers_on_zero_target_follow_engine`.
- T2-13 [BE] (review 5) Figures round half-up to 2 decimals like the engine (`ROUND_HALF_UP`).
  `test_rounding_half_up`.
- T2-14 [BE] (review 2) Agent lines carry `target_end_date` (the whole target's end, which the open
  pipeline is counted up to); null on team and dealer lines. `test_agent_line_target_end_date`.

## T3. MCP tool and reply text

- T3-1 [MCP] A read-only tool `crm_sales_target_progress` wraps the route, passes contact and
  space, restricted by the "Sales target" reveal key. `test_sales_target_tool_spec`.
- T3-1b [MCP] Period label: a calendar quarter reads "Q4 2026", a calendar month "Oct 2026", a
  calendar year "2026", any other span "1 Oct to 15 Nov 2026"; the header adds the dates
  "(1 Oct to 31 Dec)". When a reply holds more than one dealer target, each block's header ends with
  the dealer's name. A quantity target shows plain numbers, no "RM". `test_present_period_labels`.
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
- T3-6 [MCP] Additional rates read "6% + additional 1%"; per-account rates read "3% on A/C I";
  top tier reached reads "Top tier reached: Tier 3, 5%". `test_present_rates_and_top_tier`.
- T3-7 [MCP] A non-2xx route answer goes through the existing error envelope (no text,
  `has_result` false). `test_sales_target_error_envelope`.

- T3-8 [MCP] (review 1, blocker) A dealer line's "of RM t (Tier n)" is the NEXT tier's threshold, not
  the period target: reached Tier 1 at 50,000 with next Tier 2 at 70,000 and RM 55,000.00 achieved reads
  "...: RM 55,000.00 of RM 70,000.00 (Tier 2), RM 15,000.00 to go". `test_present_dealer_row_next_threshold`.
- T3-9 [MCP] (review 2) "Open opportunities closing by <d Mon>" prints the agent line's
  `target_end_date`. `test_present_pipeline_date_is_target_end`.

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
- T4-6 [CB] The tool's 403 `customer_not_permitted` (a salesperson naming a dealer they do not own)
  replies "I can only share targets for your own accounts."; 403 `sales_target_not_enabled` or
  `sales_target_not_available` replies "Sales target is not enabled for your account."
  `test_target_route_refusals_worded`.
- T4-7 [CB] The status is NOT one of `SALES_FIGURE_STATUSES`: a contact holding only "Sales target"
  (not "Sales report") gets the target answer, and one holding only "Sales report" gets the
  not-enabled line for a target ask. `test_target_grant_independent_of_sales_report`.

- T4-8 [CB] (review 4) A salesperson contact (no customer links, no staff user) holding the
  "Sales target" grant who names a dealer reaches `crm_sales_target_progress` with that customer, instead
  of today's "isn't under your account" refusal; ownership is decided by the route (T1-6, T4-6).
  Without the grant the existing refusal stays. `test_salesperson_named_dealer_reaches_target_tool`.

## T5. Parser gate (MOVED OUT of this PR, crew decision a30290657)

The v63-based candidate did not pass the re-measure rule (PLAN "Parser gate record"); slice 1 ships dark and the
candidate, the gold rows and the gate tooling go to the next prompt lane. T5-1 to T5-3 below are kept for that
lane; their tests and the insert / migration code are removed from this PR.

- T5-1 The parser recognises target questions (en / ms / zh, "target", "sasaran", "目标",
  "tier", "rebate") as the new status in the `sales` domain on the per-PR parser gate, and the gate's
  existing rows do not regress. Evidence: gate output in the PR, OpenAI eval key only, per-PR gate
  only (no full hidden run without the owner's OK), never the Gemini org key.

- T5-2 [BE] `prompt_inserts.insert_sales_target(text)`: the anchor line
  `== SALES TARGET...` section lands immediately before
  `== SALES REPORT: order_status "sales_report", domain_hint "order" ==`, everything else unchanged
  byte for byte; returns None when the anchor is missing or occurs twice, or the section is already
  there. `test_insert_sales_target_anchor`.
- T5-3 [BE] Migration `stc_0001_parser_sales_target` (its pinned base md5 is a module constant):
  publishes the inserted text as the next `chatbot_semantic_parser` version with NO label; a second
  run inserts nothing; no base row with the pinned md5, or no anchor, inserts nothing and moves no
  label. `test_stc_migration_publishes_unlabelled`.

## Out of slice 1

Creating an opportunity in chat (slice 2, salespeople only, read-back + "Reply YES to save"); the
WhatsApp achievement broadcast; any RM incentive amount; dealer-created opportunities.
