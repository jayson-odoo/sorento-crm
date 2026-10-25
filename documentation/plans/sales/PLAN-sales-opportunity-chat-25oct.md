# PLAN: log a sales opportunity over the chat (SALES-TARGET-CHAT slice 2)

Status: **planning, 25 Oct 2026.** Slice 1 (#1861, read-only target progress) owner PASS. Size L, full track (lead
pattern: tester red tests, coder, reviewer + security-reviewer). Ships DARK like slice 1: the routing value and the
parser key exist only in the test-copy prompt B4; prod v63 never routes here. UAC:
`sales-opportunity-chat-25oct-acceptance-criteria.md`. Slice 1 plan:
`documentation/plans/_archive/sales/PLAN-sales-target-chat-25oct.md` (card v1 answer H, rulings). Branch
`crew/sales-target-chat-s2` from main 3d59b5e716.

## Rulings

- Owner Q3 (a): only salespeople log opportunities in chat (dealers later, own slice).
- Owner Q5 (a, crew default): read the fields back, "Reply YES to save".
- Crew a37977616: build dark; test-copy-only prompt B4 = B3 + one opportunity section for the hand-test window;
  ~USD 0.3 gold probe x1 on ..bG4A (no ship gate); both inserts handed to CHAT-SLIM-INDEX-PLAN.
- Crew a38183607: flag-gated parser key `opportunity` {title, amount_rm, close_date}, present only when the prompt
  carries the B4 section; missing fields asked one at a time through a required_fields slot read by the parser;
  read-back + "Reply YES to save" as a yes_no pending; code only validates and saves (RS-9, no raw-text parsing).

## Journey

A salesperson (contact linked to their sales agent(s)) writes "log an opportunity: Bath Idea, condo job Taman X,
RM 40k, closing mid Dec". The system knows who they are, their agents and their own customers. The bot reads back
customer, title, amount and close date, then "Reply YES to save". Anything missing is asked one question at a time
(the customer as a numbered pick when several of their accounts match). YES saves the opportunity in stage New
under the agent who owns that customer (portal rule) and replies with its number and the open pipeline closing
within their current target. NO, "cancel" or a new unrelated ask drops it; nothing is saved. A dealer, staff or
unlinked contact is refused in one line. Nobody else is told (no approval step exists today).

## Architecture

Layer: chat write path = parser value + flag-gated key -> business lane collects and confirms -> one write MCP tool
called at the lane's own seam (never through the read-only allow-list, LESSONS-LEARNT 155) -> API-key route ->
`opportunity_service.create_opportunity` (the portal's sequence, source "chat").
Reused, not copied: `create_opportunity` (opportunity_service.py:285-296) with `restrict_customer_to_agent_id`
(CUSTOMER_NOT_YOURS backstop); owner rule `agent_owning_customer` / `default_portal_agent` (:157-180) and the
company resolution of portal_sales_opportunity.py:119-148 (moved into the service if the route needs it);
`portal_agent.agents_for_contact` (:24); `customer_options(db, q=, sales_agent_id=[...])` (:69-121) for the
salesperson's own customers; required_fields slots (`answered_by_parser=True`, one field per turn); the yes_no
pending (turn/pending.py, apply.py:2596-2606 `is_affirmative`); the ideation write-seam shape (lanes/ideate.py:114-140);
ParserConfig flags read from the template (parser.py:978, :993); `agent_progress` pipeline for the saved reply.
New: routing value, flag + schema key, lane, write route, MCP write tool, source 'chat' migration.
Gate (who may log): salesperson asker (contact_asker.classify), not revoked (slice 1 `_user_revoked`), at least one
active agent, and the contact may see the portal "sales_opportunity" form (`require_form_visible`, the same
per-contact control as the portal). Crew default; flag if the owner wants a separate switch.

## Design (fixed for the tests)

### Backend: two API-key routes (`app/api/v1/external/sales_opportunities.py`, ideation precedent)

Auth `get_external_api_user` (dependencies.py:622, as `external/ideation.py:33-36`): no integration role holds
`sales.opportunities.add` (measured on the dev copy), and the portal route has no slug either; the per-contact gate
below is the authorization, as in the portal.

Gate, both routes, in this order (one helper):
1. `contact_id` and `space_id` stripped and both required: 422 `contact_identity_required`.
2. Contact resolved (`resolve_contact_with_null_workspace_fallback`); unknown: 403 `not_a_salesperson`.
3. Asker: `contact_asker.classify` must be salesperson and the contact not revoked (slice 1 `_user_revoked`):
   else 403 `not_a_salesperson`.
4. `portal_agent.agents_for_contact` non-empty: else 403 `not_a_salesperson`.
5. `require_form_visible(db, contact_id, "sales_opportunity")` (the portal's own per-contact control): else 403
   `opportunity_not_enabled`.
6. Contact audit actor stamped (portal `_require_agents` pattern, portal_sales_opportunity.py:83-91).

`GET /api/v1/external/sales-opportunities/customer-options?contact_id&space_id&q`
-> `{"items": [{"customer_id", "code", "name", "label"}], "prospect": bool, "blocked": bool}` from
`opportunity_service.customer_options(db, q=q, sales_agent_id=[agent ids])` (:69-121): own customers only;
`label` = `account_label` (A/C I ...); `blocked` = the exact name belongs only to another agent's customer.
`customer_id` is internal (never shown in a reply).

`POST /api/v1/external/sales-opportunities` body `{contact_id, space_id, customer_id | null, prospect_name | null,
title, expected_amount, expected_close_date, dry_run = false}` -> 201
`{"opportunity_no", "stage", "customer": {"code", "name", "label"} | null, "prospect_name", "title",
"expected_amount", "expected_close_date", "pipeline": {"target_end_date", "pipeline_value"} | null,
"dry_run": bool}`. Same sequence as the portal create (portal_sales_opportunity.py:223-244): owner agent =
`agent_owning_customer(...) or default_portal_agent(...)`, company per its `_resolve_company`,
`create_opportunity(..., source="chat", created_by_contact_id=contact, restrict_customer_to_agent_id=[agents])`.
Chat-only rule: `expected_amount` required and > 0 (422 `amount_required`); every service 422 passes through
(CUSTOMER_NOT_YOURS, CUSTOMER_OR_PROSPECT_REQUIRED, PROSPECT_IS_A_CUSTOMER, ...). `pipeline`: the owning agent's
current agent target from `target_service.agent_progress` (target end date + open pipeline incl. this one), null
when the agent has no current target. `dry_run`: every check runs, nothing is inserted or numbered,
`opportunity_no` null.

Migration `stc_0002_opp_source_chat` (down_revision oihr_0010_so_remark_column): swap
`ck_sales_opportunities_source` to `source IN ('portal','crm','chat')` (created in sales_0003_opportunities.py:99);
model `sales.py:269`. FE: `salesOpportunity.types.ts:46` gains 'chat'; `SOURCE_LABEL` in
`SalesOpportunitiesView.tsx:207` gains `chat: 'Chat'` (label value only, no mockup; browser check 1280/375).

### MCP

`crm_sales_opportunity_customer_options` (GET, read-only) and `crm_sales_opportunity_log` (POST, write; not in any
read-only allow-list; in the in-app assistant's write gate list `_WRITE_TOOL_NAMES` if that list is exhaustive).
The chat lane calls both at its own seam through `MCPRuntimeClient`, as `lanes/ideate.py:114-140` does, never via
`fetch.call_tool` (LESSONS-LEARNT 155).

### Parser (flag-gated, prod untouched)

- `order_status = "log_opportunity"` (free string, parser.py:261) and a new key `opportunity`:
  `{"title": string|null, "amount_rm": number|null, "close_date": "YYYY-MM-DD"|null}`.
- `ParserConfig.opportunity` is true only when the raw template carries the line
  `== LOG OPPORTUNITY: order_status "log_opportunity", domain_hint "order" ==` (the sales_channels pattern,
  parser.py:978); only then does the strict schema (:132) carry the key. v63 has no such line: its schema and parse
  are unchanged.
- The B4 test-copy text = v63 + the slice 1 SALES TARGET section + the LOG OPPORTUNITY section, both before the
  SALES REPORT anchor. Section text: below.

### Chat lane (`lanes/opportunity.py`, the ideate lane's shape)

- turn_runtime maps `log_opportunity` to the `sales` domain (slice 1 seam); a new branch kind `log_opportunity`
  routes to the lane (route.py, contracts BRANCH_KINDS, engine arm like ideate's at engine.py:~11274). Keyed on that
  status only.
- Not a salesperson (contact_asker): fixed line "Logging an opportunity is for salespeople only." and no call.
- Collect: values carried in a required_fields slot (`OPPORTUNITY_ASK`, `answered_by_parser=True`, one field per
  turn) merged with this turn's `opportunity` key and customer entity. Order asked: customer, title, amount, close
  date. Questions: "Which customer is it for?", "What is the opportunity? A short title, please.", "What is the
  expected amount in RM?", "When do you expect it to close?".
- Customer: the customer entity's raw words go to `crm_sales_opportunity_customer_options`: one item -> that
  customer; several -> numbered pick ("Which account?" 1. BKIN ELECTRICAL SDN BHD [A/C I] ...); `blocked` ->
  "That customer is not one of yours." and the flow ends; no item and not blocked -> a prospect (prospect_name = the
  raw words), shown as "Prospect: <name>" in the read-back.
- Read-back when all four are known, then a yes_no pending carrying the payload:
  "Save this opportunity?" / "Customer: <name> [<label>]" (or "Prospect: <name>") / "Title: <title>" /
  "Amount: RM 40,000.00" / "Close by: 15 Dec 2026" / "Reply YES to save."
- Answer: yes (parser `open_question_answer` yes, apply.py:2596-2606) -> `crm_sales_opportunity_log` ->
  "Saved OPP-000123, stage New." plus "Open opportunities closing by 31 Dec: RM 40,000.00." when `pipeline` is set;
  no / cancel -> "Not saved."; a field given while the read-back is open (same status, `opportunity` key) updates
  the payload and reads it back again; any other ask drops the pending and routes as usual.
- Route errors: 403 not_a_salesperson / opportunity_not_enabled -> "Logging an opportunity is not enabled for your
  account."; 422 CUSTOMER_NOT_YOURS -> "That customer is not one of yours."; other 4xx/5xx -> "I couldn't save
  that. Nothing was recorded." (never a raw error).
- Dry run (console test turn): the same reads and the same read-back; the write is sent with `dry_run` true and the
  reply says "Test run: nothing was saved." (LESSONS-LEARNT 101).

### LOG OPPORTUNITY section (B4, test copy only; handed to CHAT-SLIM-INDEX-PLAN with the slice 1 section)

Inserted immediately before `== SALES REPORT: order_status "sales_report", domain_hint "order" ==`, after the
slice 1 SALES TARGET section. Probe: ~USD 0.3 x1 on ..bG4A (crew a37977616), no ship gate.

```text
== LOG OPPORTUNITY: order_status "log_opportunity", domain_hint "order" ==
A salesperson LOGGING a new sales opportunity - a deal, project or job they expect to win and want recorded -
is order_status "log_opportunity", domain_hint "order", intent_hint "check_order": "log an opportunity", "new
opportunity", "add a deal", "record a project", "peluang baru", "rekod projek", "新商机", "记录一个机会". It is
never a sales target, sales report or sales analysis ask. Fill the `opportunity` object from THIS message only:
title = the job or deal in the user's own words (never the customer's name alone), amount_rm = the expected value
in ringgit as a plain number ("RM 40k" -> 40000, "1.2 juta" -> 1200000), close_date = the expected closing date as
YYYY-MM-DD (a month alone -> its last day, "mid Dec" -> the 15th); anything not said is null. The customer stays an
ordinary customer entity with the user's raw words. While "Open question" asks for one opportunity field, the
reply fills only that field, with order_status "log_opportunity"; a yes / ya / ok / 是 to "Reply YES to save" is
the open question's yes answer, never a new ask.
  - "log opportunity Bath Idea, condo job Taman X, RM 40k, close mid Dec" -> order_status "log_opportunity",
    entities [Bath Idea as customer], opportunity {title "condo job Taman X", amount_rm 40000, close_date
    the 15th of December of the current year}
  - "new opportunity for BKIN" -> order_status "log_opportunity", entities [BKIN as customer], opportunity
    {title null, amount_rm null, close_date null}
  - "peluang baru: hotel 200 bilik, RM 1.2 juta, tutup Mac" -> order_status "log_opportunity", opportunity
    {title "hotel 200 bilik", amount_rm 1200000, close_date the last day of the coming March}
  - "新商机：学校厕所翻新，八万，十二月底" -> order_status "log_opportunity", opportunity {title "学校厕所翻新",
    amount_rm 80000, close_date the last day of December of the current year}

```

### Lead decisions from the red tests (25 Oct)

- Seam: `lanes.opportunity.call_opportunity_tool(tool_name, arguments) -> dict` (module global, calls
  `MCPRuntimeClient.call_tool` directly, returns decoded JSON), the ideate shape.
- The two tools are NOT presenter tools: a refused route reaches the lane as the raw HTTP error body (top-level
  `code`, `status_code`); amounts arrive as decimal strings ("40000.00") and the lane formats them.
- A bare YES / NO / cancel turn reaches the lane through the yes_no pending (`message_type` casual, `order_status`
  null), not through the status. Cancel (`open_question_answer` mode cancel) is a reset upstream (`apply.is_reset`),
  so the lane handles it explicitly and replies "Not saved." before the reset clears the question.
- `crm_sales_opportunity_log` joins the in-app assistant's `_WRITE_TOOL_NAMES` (`_is_write_tool` true);
  `crm_sales_opportunity_customer_options` joins `UNDOMAINED_CHATBOT_TOOLS` and `BRAND_SCOPE_TREATMENT`.
- The numbered pick reads "Which account?" then "N. <name> [<label>]".
- O3-7 asserts the model constraint; the migration is checked by `alembic upgrade head` on the throwaway DB and the
  single-head gate.

### Test DB

`sorento_stc_throwaway` (at head oihr_0010), `.env.ci-tests`; serial pytest runs (a `-n 2` run hung in slice 1).
