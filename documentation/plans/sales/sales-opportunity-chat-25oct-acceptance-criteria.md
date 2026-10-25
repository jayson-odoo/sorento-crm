# UAC: log a sales opportunity over the chat (SALES-TARGET-CHAT slice 2)

Plan: `PLAN-sales-opportunity-chat-25oct.md`. Rulings: owner Q3 (a), Q5 (a); crew a37977616, a38183607. Each line
names its test (BE = pytest on Postgres, MCP = sorento_crm_mcp pytest, CB = chatbot pytest with the parser and the
MCP calls faked, PR = parser pytest). Tests seed their own data (CI has none).

## Journey

See the plan. A salesperson logs a deal in chat; the bot asks for what is missing one question at a time, reads it
back, saves on YES under the agent who owns the customer, and says the open pipeline within their target. Nothing is
saved without YES. Dealers, staff and unlinked contacts are refused.

## O1. Gate (both routes)

- O1-1 [BE] `contact_id` / `space_id` stripped and both required: 422 `contact_identity_required`.
  `test_opp_routes_need_contact_and_space`.
- O1-2 [BE] A dealer, staff, unclassified or unknown contact: 403 `not_a_salesperson`; a salesperson whose linked
  CRM user is inactive or trashed: 403 `not_a_salesperson`. `test_opp_routes_refuse_non_salespeople`.
- O1-3 [BE] A salesperson whose contact may not see the portal "sales_opportunity" form: 403
  `opportunity_not_enabled`. `test_opp_routes_need_the_portal_form`.
- O1-4 [BE] Both routes accept the integration API key with no permission slug; a Bearer staff token is refused.
  `test_opp_routes_api_key_only`.

## O2. Customer options route

- O2-1 [BE] `q` matches only the salesperson's OWN customers (customers.sales_agent_id in their agents), with code,
  name and account label; another agent's customers never appear. `test_options_own_customers_only`.
- O2-2 [BE] Several own accounts of one dealer (A/C I, A/C III) are all returned, labelled.
  `test_options_returns_every_own_account`.
- O2-3 [BE] A name that exists only as another agent's customer: `items` [] and `blocked` true; an unknown name:
  `items` [] and `prospect` true. `test_options_blocked_and_prospect`.

## O3. Create route

- O3-1 [BE] A valid body creates one opportunity: source "chat", stage New (initial status), outcome open,
  owner agent = the agent owning the customer (portal rule), created_by_contact_id = the contact, number from the
  numbering rule; 201 with the contract fields. `test_create_saves_with_source_chat_and_owner_agent`.
- O3-2 [BE] A prospect (no customer): owner = the contact's first agent by code (`default_portal_agent`).
  `test_create_prospect_goes_to_first_agent`.
- O3-3 [BE] A customer of another agent: 422 `CUSTOMER_NOT_YOURS`, nothing saved.
  `test_create_refuses_other_agents_customer`.
- O3-4 [BE] `expected_amount` missing, 0 or negative: 422 `amount_required`, nothing saved.
  `test_create_requires_positive_amount`.
- O3-5 [BE] `dry_run` true: every check runs, nothing is inserted, no number is consumed, `opportunity_no` null.
  `test_create_dry_run_saves_nothing`.
- O3-6 [BE] `pipeline` = the owning agent's current target end date and open pipeline including this opportunity;
  null with no current agent target. `test_create_returns_pipeline`.
- O3-7 [BE] The migration allows source 'chat' and keeps 'portal' / 'crm'; one alembic head.
  `test_opportunity_source_accepts_chat`.
- O3-8 [BE] No UUID other than the internal `customer_id` of the options route appears in any response.
  `test_opp_responses_carry_no_other_ids`.

## O4. MCP

- O4-1 [MCP] `crm_sales_opportunity_customer_options` (GET, read-only) and `crm_sales_opportunity_log` (POST, not
  read-only) wrap the two routes with the contract params. `test_opportunity_tool_specs`.
- O4-2 [CB] Neither tool is reachable through the read-only allow-list path except the options read; the write
  tool is called only from the opportunity lane's seam. `test_tool_pool_is_read_only` (existing, stays green),
  `test_log_tool_not_in_read_only_pool`.

## O5. Parser flag

- O5-1 [PR] With a template carrying the LOG OPPORTUNITY line, `ParserConfig.opportunity` is true and the strict
  schema has the `opportunity` key {title, amount_rm, close_date}, required, nullable; without the line (v63) the
  schema is byte-for-byte unchanged. `test_opportunity_key_only_with_its_section`.

## O6. Chat lane (engine-level, parser and MCP faked)

- O6-1 [CB] A salesperson's "log_opportunity" turn with all four fields in one message replies with the read-back
  exactly: "Save this opportunity?" / "Customer: BATH IDEA BATHROOM & KITCHEN MARKETING SDN BHD [A/C I]" /
  "Title: condo job Taman X" / "Amount: RM 40,000.00" / "Close by: 15 Dec 2026" / "Reply YES to save." and calls no
  write. `test_all_fields_reads_back`.
- O6-2 [CB] Missing fields are asked one per turn in the order customer, title, amount, close date, with the plan's
  exact questions; an answer fills only its field; the collected values survive the turns.
  `test_missing_fields_asked_one_at_a_time`.
- O6-3 [CB] Several own accounts match: a numbered pick; the answer "2" picks the second.
  `test_customer_numbered_pick`.
- O6-4 [CB] `blocked`: "That customer is not one of yours." and the flow ends; no item and not blocked: the
  read-back shows "Prospect: <raw words>". `test_blocked_and_prospect_lines`.
- O6-5 [CB] YES to the read-back calls `crm_sales_opportunity_log` once with the payload and replies
  "Saved OPP-000123, stage New." and "Open opportunities closing by 31 Dec: RM 40,000.00."; without a pipeline only
  the first line. `test_yes_saves_once`.
- O6-6 [CB] NO or cancel: "Not saved." and no write; a different ask while the read-back is open drops it and is
  answered as usual, no write. `test_no_and_other_ask_save_nothing`.
- O6-7 [CB] A field given while the read-back is open ("make it 50k") updates the payload and reads back again with
  "Amount: RM 50,000.00". `test_correction_reads_back_again`.
- O6-8 [CB] A dealer or staff contact asking to log one: "Logging an opportunity is for salespeople only." and no
  MCP call. `test_non_salesperson_refused_in_lane`.
- O6-9 [CB] Route errors are worded per the plan (not enabled, not yours, could not save); no raw error text.
  `test_route_errors_worded`.
- O6-10 [CB] A console dry-run turn makes the same reads and read-back, sends the write with dry_run true and says
  "Test run: nothing was saved.". `test_dry_run_turn_saves_nothing`.
- O6-11 [CB] Any turn whose order_status is not "log_opportunity" (sales_target, sales_report, ...) behaves exactly
  as before (existing lane suites stay green). `test_other_statuses_untouched`.

## O7. UI

- O7-1 [UX] The CRM Sales > Opportunities list shows source "Chat" for a chat-logged opportunity; usable at 1280
  and 375. Agent-browser evidence. Vitest: `SalesOpportunitiesView` renders "Chat" for source chat.
