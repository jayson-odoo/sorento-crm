# CARD: Agentic P2 auto-route + P3 write actions (behaviour card)

Status: behaviour card filed (crew-ask on PR #1999), waiting on the owner's answers. No product code until then. Track: full pipeline
(Size L: new routing path on live WhatsApp turns, new write surface, identity change for writes).
Base: AGENTIC-P1 (PR #1982, owner hand test PASS 30 Oct). Lane AGENTIC-P2-CARD.

Owner, 30 Oct ~10:40 (verbatim): "I am okay for 1982, is a good start, now it is read only right, and it is
binary, either chat / agent mode, we should be smart enough to know which one should go to chat / agent mode,
maybe can use JEV for token saving, and in agent mode now we can read only right, should be able to write cause
that's what agent is strong at, maybe taht's in later phase isit but we should continue building towards that la".

Standing rulings this card keeps: foundation first; budgets configurable; continuous context with compaction;
no silent fallback between agent and bot; semantic routing only (no regex or word-list guards); staff contacts
on Gemini, customers on OpenAI; dev AI on Gemini (dev OpenAI key is dead); the owner publishes prompts; one
confirmation per write (P1 ruling R5).

Data: every place marked **[dev]** is filled from crew's read-only queries on the dev DB and the Jev research
report. Those figures and message examples are delivered in the crew report only and are NOT committed (public
repo). This file carries the rules, the reasoning and the recommendations they led to.

## What exists today (code facts)

- Every live turn runs `engine.run_turn` (`sorento_crm_backend/app/services/chatbot/engine.py:2933`); the
  parser call is at `engine.py:5313` (`head/parser.py:1396 parse`). The parser already emits, per message,
  `message_type` (5 values, `chatbot/contracts.py:178`), `intent_hint` (16 intents over 16 domains,
  `turn/policy_rows.py:55`), `domain_hint` and a free-text `user_goal` (`head/parser.py:190-196`). It has no
  message-level confidence; only entity-level `confident` / `hint_confident` (`parser.py:226-237`).
- Parser usage is logged per call as `feature = "chatbot_parser"` (`chatbot/usage.py:37`) in
  `ai_assistant_usage_logs` (prompt/completion/cached tokens, model, ms; `models/ai_assistant.py:146-177`).
  Agent turns log `feature = "chatbot_agent"` (P1).
- P1 agent: console only, `POST /system/chatbot/agent/turn`, `is_test = true`, nothing sent to WhatsApp.
  Entry requires `chatbot_allowed`, `chatbot_agent_enabled` and a linked active user
  (`agent/access.py:47-83`). 11 read tools in `agent/tools.py:61` (`ToolDef` at `:28`: `name`,
  `user_permission`, `contact_grant`, `render`). Dispatch re-checks the slug at call time.
- P1 known limit that matters for writes: MCP calls authenticate as the integration's act-as user; the linked
  user's company scope is applied only through the contact scope (`agent/access.py:48-50`). A write must not run
  that way.
- Writes that already exist somewhere: the in-app assistant halts any write tool for a Confirm / Cancel
  (`ai_assistant_service.py:139-146` `_is_write_tool`, `:1845` `_serve_pending_confirmation`, `:1945`
  resolve). MCP has `crm_purchase_request_approve/reject`, `crm_complaint_close`, `crm_order_cancel`,
  `crm_it_support_ticket_create`, `crm_sales_opportunity_log`, `crm_ideation_turn`
  (`sorento_crm_mcp/sorento_crm_mcp/catalog.py:887-1785`). Today's WhatsApp bot writes only through
  `submit_idea` (ideate domain) and the opportunity log.
- Grace window + undo already exist for form actions: `form_action_dispatch.dispatch_or_defer`
  (`app/services/form_action_dispatch.py`) parks a browser action for the configured grace and returns
  `pending_action_id`; an X-API-Key or no-request call runs immediately. Cancel / undo routes:
  `api/v1/sla/form_actions.py:150,170` (EVIDENCE-agentic-actions-29oct.md).

---

## Part 1, P2 AUTO-ROUTE: chat bot or agent, decided per message

### Rules

1. **Who is routed.** Only contacts with AI replies on, the Agent switch on and a linked active user (the P1
   entry rule, unchanged). Every other contact, every customer, never meets the router: zero extra cost, today's
   bot exactly as now.
2. **What decides.** One semantic classification per message: `chat` (a lookup the bot's 16 intents answer:
   stock of X, ETA of Y, order status, a link, a flyer) or `agent` (needs several reads combined, a comparison, a
   "why", an analysis over periods / agents / products, or a change to a record). The classifier sees the
   message plus the last 3 exchanges and which side answered each. No word lists, no regex.
3. **State goes first, then the classifier.** Two cases are decided by stored state, not by the model:
   (a) the agent has a pending write proposal for this contact (Part 2) -> agent; (b) today's bot has an open
   question waiting on this contact (`open_question`, `parser.py:1310`) -> bot. Everything else -> classifier.
4. **Stickiness.** A follow-up stays with the side that answered the last turn unless the classifier says the
   new message is a different ask (the classifier gets "last answered by: agent|bot" as input, so it decides
   semantically).
5. **Low confidence** (below a setting, default 0.7): today's bot answers. It is the cheap path and the
   behaviour staff already know. The turn records `route = chat, reason = low_confidence, score` so the eval can
   count these. No "which mode?" question to the user (owner: no manual switch).
6. **No silent fallback.** If the agent was chosen and fails (provider error, no key, budget before any
   result), the reply says the agent could not answer, as in P1. It does not re-run on today's bot. If the
   router itself fails (timeout, provider error), today's bot answers and the trace says `router_failed`.
7. **Media and flyers** go to today's bot (the agent has no media tools). Decided by the message carrying media,
   which is ingress state, not wording.
8. **Where it runs.** Console first (the console turn picks the side the same way, so the owner can watch it);
   WhatsApp live only after the gold-set eval passes (question P2-Q1). On WhatsApp, the agent's reply goes out
   through the same outbound path as today's bot reply; the turn row stops being `is_test` for routed turns.
9. **Visible.** Each turn's trace and the console show `route`, `score`, `reason`, router model and tokens.

### Router options (cost per 1,000 routed staff messages)

Formula: `1000 x (avg_in x price_in + avg_out x price_out)`. Prices to be read from the providers' current
price lists at build time, not from memory.

| Option | How | Extra calls | Input / output per message | Cost / 1k | Notes |
| --- | --- | --- | --- | --- | --- |
| A. Existing parser | Add one output pair to the parser schema: `route: chat|agent`, `route_score: 0..1` | 0 (parser already runs every turn) | +~40 output tokens on today's parser call **[dev: avg_in / avg_out per parser call, in crew report]** | parser cost + ~40 tokens | Cheapest. But the parser runs BEFORE the decision, so every agent turn also pays a full parser call it does not use **[dev: share of staff turns that would go to agent, in crew report]**. Changes the owner-published parser prompt and strict schema (`parser.py:164`). LLM self-reported scores are poorly calibrated. |
| B. Jev (TypeSafe AI) | Typed `choice(chat, agent)` + confidence | 1 per message, before the parser | message + 3 exchanges, under its 32k limit | **[from RESEARCH-JEV-parser-cost.md, in crew report]** | Returns a real confidence. English-first: staff write Malay, Chinese and mixed **[dev: language mix, in crew report]**. A new vendor receives staff messages (data agreement). |
| C. Gemini Flash-Lite | Its own prompt label `chatbot-router` (owner publishes), JSON `{route, score}` | 1 per message, before the parser | ~600-1,200 in (prompt + 3 exchanges), ~15 out | **[dev + price list, in crew report]** | Same provider and key as staff agent turns (Gemini). Lets agent turns skip the parser entirely. Score is self-reported, like A. |

Recommendation, on the dev numbers: **C**. It beats A as soon as a small share of staff messages goes to the
agent (it lets those skip the parser call, which is where the tokens are), and its absolute cost at staff volume
is a few dollars a month. **B (Jev)** saves almost nothing over C at that volume while adding a new vendor that
is English-first, waitlisted and would receive staff WhatsApp text. The owner's "use JEV for token saving" is a
real lever for the **parser** (most tokens per message are there; parser caching already works), not for the
router, and Jev cannot replace the parser's entity extraction. Keep it as a separate parser-cost experiment.

### How the switch and budgets change

- `respond_contacts.chatbot_agent_enabled` keeps its name and default (off). Meaning changes from "console Agent
  tab allowed" to "this contact's messages may be routed to the agent". Contact Details label: "Agent mode
  (auto)". No new per-contact column.
- New System Settings (one migration, the P1 budget screen): `chatbot_router_min_score` (0.7, 0.5..0.95),
  `chatbot_router_enabled` (off; on = routing live for switched contacts). The router model is its prompt
  label's model, like every other label.
- The four P1 budgets stay per agent turn. One new guard: `chatbot_agent_daily_turns` per contact (default 50,
  0 = no cap), because routing makes agent cost depend on how many messages a staff member sends. At the cap,
  messages go to today's bot and the trace says `route = chat, reason = daily_cap`.

### Examples (masked, dev data)

**[dev Q4: in crew report]** Six real staff messages (masked) with the route the card expects: two single
lookups (chat), a bare menu answer such as "2" (chat by state, rule 3b), a two-domain ask over several products
(agent), a category ranking the bot did not finish (agent), and the owner's W0 message (agent, write).

### Edge cases

- "and last month?" after an agent answer: sticky, agent. After a bot answer: bot.
- "yes" / "ok proceed" with a pending agent write: agent by state (rule 3a); the classifier never sees it.
- A message that is a lookup plus a change ("stock of <code> and mark the ask done"): agent (the change wins).
- Greeting / thanks / casual: bot (it already handles casual).
- Agent busy for this contact (P1 `single_flight`, `agent/loop.py:500`): on WhatsApp the message waits behind it
  (the inbox queue serialises one contact's turns, `chatbot/inbox_queue.py`); it is not sent to the bot instead.
- Switch turned off mid-conversation: next message goes to the bot; the agent conversation is kept, not
  deleted.
- A customer contact that is wrongly linked to a user: the router runs only for linked active users, so the
  link is the gate. The card flags it; fixing links is not this lane.

### Eval plan

1. Gold set: 200 real staff messages from the last 60 days (crew Q4), masked by crew, each with its previous 3
   exchanges. Today's staff traffic is almost all single lookups, so a random sample holds too few agent-shaped
   asks to measure missed-agent. The set is enriched with every staff turn that ended `clarify_menu` or
   `out_of_scope`, plus the P1 eval cases, until it holds at least 40 agent-labelled items. The owner (or crew,
   owner spot-checks 20) labels each `chat` or `agent`. A third for tuning the router prompt, the rest held out.
2. Each option runs on the same held-out set, through cassettes after the first paid run.
3. Measured: agreement with the label; **missed-agent** rate (labelled agent, routed chat); **wasted-agent**
   rate (labelled chat, routed agent); per language; p95 router latency; cost per 1k from the usage log.
4. Proposed pass bar: missed-agent <= 10%, wasted-agent <= 10%, router p95 <= 1.5 s, zero customer contacts
   routed. Paid runs capped at USD 5 (P1 eval rule).
5. CI: cassette tests for the state rules (pending write, open question, media, cap, router failure) with no
   paid calls.

### P2 questions (max 5)

- **P2-Q1** Where does routing go live first? (a) console only, WhatsApp after the eval passes; (b) WhatsApp
  straight away for switched staff. Recommend **(a)**: the router decides who gets a slower, costlier answer on
  a live channel, and the console lets you watch it first.
- **P2-Q2** Which router? (a) parser field, (b) Jev, (c) Gemini Flash-Lite label. Recommend **(c)**: on the dev numbers
  it costs a few dollars a month at staff volume, keeps the parser prompt untouched (P1 ruling R1) and lets
  agent turns skip the parser; Jev saves almost nothing on top and adds a vendor (see the cost table).
- **P2-Q3** On low confidence: (a) today's bot answers; (b) the agent answers. Recommend **(a)**: cheaper,
  familiar, and the eval counts how often it was wrong.
- **P2-Q4** Who labels the gold set? (a) the owner labels all 200; (b) crew labels, owner spot-checks 20.
  Recommend **(b)**, to save your time; the spot-check catches a crew bias.
- **P2-Q5** Daily agent-turn cap per contact: (a) 50 per day; (b) no cap. Recommend **(a)**: routing makes agent
  spend follow message volume, and a cap keeps one busy staff member from running the bill.

---

## Part 2, P3 WRITE ACTIONS

### Rules

1. **One request, one confirmation.** The agent turns one user request into one proposal and nothing is
   written until the user confirms it (P1 ruling R5). A proposal may cover several records when the user asked
   for several (the lead example below: 5 contacts); the summary lists every record, and the apply is one
   transaction, all or nothing, capped at 20 records.
2. **The proposal is server state, not chat text.** A write tool call does not write. It creates a pending
   action row with canonical arguments, the record's current state as read now (the precondition), a
   plain-language summary built by code from the arguments (not by the model), and an expiry (10 minutes). The
   reply shows that summary.
3. **Confirming.** Console: Confirm / Cancel buttons on the proposal. WhatsApp (later): the next message is
   routed to the agent by state (P2 rule 3a); the model reads it semantically and calls `confirm(action_id)` or
   `cancel(action_id)`. The server accepts `confirm` only in a user turn that came after the proposal, only for
   the newest pending action of that contact, and only before expiry.
4. **At execution the server re-checks everything**: switch on, linked user active, the user still holds the
   tool's permission slug, the contact still holds its grant, the record is unchanged since the proposal (same
   status / revision), and the domain service's own checks (scope, state transitions, handling lock). Any
   change -> nothing is written; the agent says what changed.
5. **Runs as the linked user, in process.** A write calls the same service function the screen's route calls,
   with the linked user as `current_user` (actor id, company scope, own-agent scope). It never goes through MCP
   and never as the integration's act-as user (fixes the P1 limit for writes). Form actions go through
   `dispatch_or_defer` with the UI channel, so the configured grace window and countdown apply exactly as on
   the screen.
6. **Registry, not a new framework.** P1's `ToolDef` gains `effect: "read" | "write"` and, for writes, `undo`
   (the inverse tool name or none). A write tool is exposed only when the user holds its slug AND the contact
   holds the new reveal-style grant `agent.write` (default off; set on the contact screen). Reads are unchanged.
7. **Audit.** The domain's own audit rows name the linked user, as if they clicked it, plus `via = agent` in the
   audit context. One ledger table `chatbot.agent_actions`: id, conversation id, turn id, contact, user, tool,
   canonical args, summary, before-state, status (`proposed | confirmed | executed | rejected | failed |
   cancelled | expired | undone`), result record id, error, timestamps. The console shows it under the turn.
8. **Undo.** Each write declares its inverse when the domain has one; "undo that" proposes the inverse as a new
   action (also confirmed). A form action inside its grace window is cancelled through the existing cancel
   route; after commit, the existing undo route and its eligibility apply. A write with no inverse says so in the
   proposal ("this cannot be undone here").
9. **Idempotent.** An action row executes at most once (status claim in one UPDATE). A lost response is checked
   by reading the record, never by running the write again.

### First write candidates (pick 3)

Grounded in what staff do today. The dev sample shows staff do not ask the bot for writes (it cannot do
them), so demand comes from outside the bot: the owner's W0 example came by person-to-person chat **[dev Q4: in
crew report]**:

| # | Write | Existing path (reused as-is) | Permission | Undo | Side effects |
| --- | --- | --- | --- | --- | --- |
| W0 | Dealer contact access: set role (Business owner / Employee), resign | `contact_setup_engine._apply_contact` (`contact_setup_engine.py:258`) + `unlink_customer` (`contact_customer_service.py:132`); see the lead example | today `user_management.contacts.edit` (whole contact book); proposed `user_management.contacts.edit_own` limited to contacts under the user's own sales agents (P3-Q2) | inverse from the ledger's before-state | the contact's bot answers change at its next message |
| W1 | Customer ask: add a note, mark Done, reopen | `PATCH /sales/customer-asks/{id}` -> `stock_ask_service.update_for_sales` with `_patch_scope` (`api/v1/sales/customer_asks.py:196-210`) | `sales.customer_asks.edit` (`customer_asks.py:40`) | Done <-> Reopen; a note cannot be removed | none outward |
| W2 | Sales opportunity: create, move stage, mark Lost with reason | `POST/PATCH /sales/opportunities` (`api/v1/sales/opportunities.py:219,259`), state graph + lost reason in `services/sales/opportunity_service.py:423` | `sales.opportunities.add` / `.edit` (`opportunities.py:37-38`) | previous stage from the before-state; create -> archive | none outward |
| W3 | Purchase request: approve / reject (reason required) | `approval-decision` route (`api/v1/procurement/purchase_requests.py:501`) through `dispatch_or_defer` | `procurement.purchase_requests.approve` + revision + handling lock | grace-window cancel; then form-action undo where eligible | notifies requester and contact, SLA event, approval automation |
| W4 | Complaint close | `POST /complaints/{id}/close` (`api/v1/complaints/complaints.py:1418`, `crm_complaint_close` wraps it), current-revision guard | `complaint_management.complaints.close` | form-action undo where eligible | notifications |
| W5 | IT ticket: create and submit | `api/v1/tickets/tickets.py:108,182` | `.add` | cancel draft before submit only | round-robin assignment, SLA |

Recommendation: **W0, W1, W2** first, W3 after. W0 is the owner's own example and a real salesperson request
today; W1 and W2 are internal and reversible with no outward notification. W3 is the first with real side
effects and uses the existing grace window.

### Lead example (owner, 30 Oct ~10:50): a salesperson changes dealer contacts' access

The message a salesperson sent (masked by crew; real names and phones never go in the repo):

```
Dealer-Person-A
Chg ALL to Business owner
+60-xxx-0001
+60-xxx-0002
+60-xxx-0003
+60-xxx-0004

Person-B resign. +60-xxx-0005
```

Meaning: set the access role of 4 dealer contacts to Business owner, and end access for one contact who
resigned. Owner: "a very good example of agentic movement ... so agents can help".

**The real model (code facts).**
- "Business owner" / "Employee" are the access sheet's role words (`app/services/contact_access_sheet_service.py:62`
  `OWNER_WORDS`). A role is a set of contact access types per company: every contact gets `end_user`; Business
  owner adds `dealer` + `cabana_dealer` for Sorento (SRT) and `mocha_dealer` for Mocha (MCH)
  (`contact_access_sheet_service.py:43-45` `TEMPLATE`, `:230-240` `_template_sets`). Access types live in
  `respond_contact_access_types` (`app/models/access.py:92`), codes in `contact_access_types` (`:67`).
- The writer is `contact_setup_engine._apply_contact` (`app/services/contact_setup_engine.py:258`), today
  called by the access-sheet upload `POST /user-management/contacts/access-sheet`
  (`api/v1/user_management/contacts.py:282`), which requires `user_management.contacts.edit` and has a dry run.
  The engine is **add-only**: it inserts types and links, never removes them (`contact_access_sheet_service.py:546`
  "apply is add-only").
- Phones resolve with `contact_setup_engine.normalise_phone` (`:54`, `+601` + 8-9 digits) and `_find_contacts`
  (`:72`): exact digits on `respond_contacts.phone_number`; two contacts with the same digits = neither (ambiguous).
- "Under this salesperson" is an explicit chain, no names: salesperson user -> `users.respond_contact_id` ->
  active `sales_agents.contact_id` (`app/services/sales/portal_agent.py:23` `agents_for_contact`) ->
  `customers.sales_agent_id` -> `respond_contact_customers` (`app/models/access.py:11`) -> the dealer contact.
  The same agent rule the portal and own-scope use (`app/services/own_scope.py:1-15`).
- There is no contact "active" flag. What a contact can do is: `chatbot_allowed` (AI replies,
  `models/access.py` RespondContact), its access types, its customer links (`contact_customer_service.py:132`
  `unlink_customer`, "the customer and the contact both survive it"), and its chatbot-agent windows (general /
  order / incoming-stock enquiries, `contact_agent_access.valid_to`, `models/access.py:477`; the sheet grants them
  in `TEMPLATE["agents"]`).

**How the agent handles it.**
1. Reads the message as one request with two parts (role change for 4 phones, resign for 1). The dealer name
   line is context only; phones decide.
2. Resolves each phone with `normalise_phone` + `_find_contacts`. For each found contact, checks the explicit
   chain: is it linked to a customer whose sales agent is one of THIS salesperson's agents?
3. Reads each contact's current role from its access types (holds an owner type of one of its companies ->
   Business owner; only `end_user` -> Employee; none -> no access) and its companies
   (`respond_contact_companies`, `app/models/company.py:74`).
4. Builds one proposal (code writes the summary, not the model):

```
Change access for 5 contacts of <dealer> (your customer <cust-code>):
  +60-xxx-0001 <person>   Employee -> Business owner (Sorento)
  +60-xxx-0002 <person>   Employee -> Business owner (Sorento)
  +60-xxx-0003 <person>   already Business owner - no change
  +60-xxx-0004            not found in the CRM - skipped
  +60-xxx-0005 <person>   resigned: AI replies off, unlinked from <cust-code>, enquiry access ends today.
                          Contact and chat history are kept.
Reply yes to apply the 3 changes, or tell me what to change.
```

5. On confirm: re-checks everything (rule 4, including that each contact is still under this salesperson and
   its role has not changed), applies in one transaction through the engine's writer as the salesperson, writes
   the domain audit rows (`audit_service`, as the sheet does with `EVENT = "contact.access_sheet"`, here
   `contact.access_agent` with `via = agent`) and one ledger row listing every contact before / after.
6. Undo: "undo that" proposes the exact inverse from the ledger's before-state (re-link, AI replies back on,
   enquiry windows restored, and the exact access-type rows this action added deleted) as a new confirmed action.
   Deleting only rows the ledger says this action added is a narrow remove path; it is not a general downgrade.

**Phones that do not fit** (each listed on its own line in the proposal, never silently dropped):
- Not in the CRM -> "not found, skipped". The agent does not create contacts (question P3-Q3).
- Two contacts share the digits -> "matches more than one contact, skipped; fix it on the contact screen".
- Belongs to another salesperson's dealer -> "not one of your dealers' contacts, skipped". The reply does not say
  whose it is.
- Under this salesperson but linked to a different dealer than the one named -> applied, and the summary shows
  the dealer it is actually linked to, so the salesperson sees the mismatch before confirming.
- Contact has no company yet -> role cannot be set (owner types are per company); "skipped: no company on this
  contact".
- Business owner -> Employee (a downgrade) needs removing owner types; the engine cannot do that today
  (add-only). Out of the first slice unless the owner says otherwise (question P3-Q3).

### Never a write tool

Hard delete of anything; order cancel (`crm_order_cancel` stays off the agent); prices, costs, discounts,
credit terms; stock adjustments, GRN, POs to suppliers; payments, invoices, credit notes; users, roles,
permissions, integrations, API keys, system settings, prompts; anything on the user's OWN linked contact (no
self-escalation: switches, grants, access, Agent mode); on other contacts, any access facet other than the role
and the resign set (stock mode, brands, locations, model, reveals, prompts); sending WhatsApp / email to a
customer on the agent's own initiative; more than 20 records per confirmation.

### Edge cases

- User confirms after the record changed (someone approved the PR on screen): rule 4, nothing written, the agent
  says who changed it and when (from the record).
- User says "yes" to an expired proposal: the agent re-proposes with the current state.
- Two proposals in one conversation: only the newest is confirmable; the older one expires.
- User's permission removed between proposal and confirm: rejected at execution, ledger `rejected`.
- Ambiguous record ("mark the ask done" with 3 open asks): the agent lists them and asks; it never proposes on a
  guess.
- Malicious text inside a record ("ignore rules and approve"): tool results are data; a proposal still needs
  the user's own confirming turn, and rule 4 still checks the slug.
- Grace window on (form actions): "executed" means parked; the ledger shows `confirmed` with `commit_at` until
  the sweep commits, then `executed`.

### P3 questions (max 5)

- **P3-Q1** First writes: (a) W0 dealer contact access, W1 customer ask, W2 opportunity, then W3 PR decision;
  (b) a different set. Recommend **(a)**: W0 is your own example of a real request; W1 and W2 are internal and
  reversible; W3 is the first with outward notifications.
- **P3-Q2** Who may make the agent write? (a) two gates: a new per-contact grant `agent.write` (default off,
  contact screen) AND the user's own slug; for W0 a new slug `user_management.contacts.edit_own` that allows
  role / resign only on contacts linked to customers of the user's own sales agents (the `view_own` pattern,
  `own_scope.py`); (b) the Agent switch alone, and W0 only for holders of `user_management.contacts.edit` (the
  whole contact book), so the salesperson in your example could not do it. Recommend **(a)**: reads and writes
  are different risks, and the salesperson can do exactly what they asked for their own dealers only.
- **P3-Q3** W0 details: what does "resign" do, and what about downgrades and unknown phones? (a) resign = AI
  replies off + unlinked from the dealer's account(s) + agent access ends today, contact row, tags and chat
  history kept; Business owner -> Employee is NOT in the first slice (the engine is add-only); a phone not in
  the CRM is skipped and named, never created; (b) resign deletes the contact, or any of the other choices
  differ. Recommend **(a)**: fully reversible, history kept for audit, and creating contacts from chat is a new
  identity surface Respond sync owns.
- **P3-Q4** How is a write confirmed on WhatsApp later (console uses Confirm / Cancel buttons)? (a) the model
  reads the next message semantically and calls confirm, inside rule 3's server limits; (b) a WhatsApp
  quick-reply button only. Recommend **(a)**, consistent with the semantic-only ruling; add (b) if the eval
  shows a false confirm.
- **P3-Q5** Order: (a) P2 routing first, then P3 writes; (b) P3 writes first in the console (explicit Agent tab),
  routing after. Recommend **(b)**: writes build on the P1 console you just passed and need no router. The dev
  sample shows staff ask today's bot almost only single lookups, so routing has little to move until the agent
  can do something the bot cannot; writes are that thing. The gold set can be labelled in parallel.

Settled by default, not asked: agent form actions use the screen's configured grace window (rule 5), so one
action has one rule and keeps its cancel path.

## Not in this card

Multi-record batches, scheduled / background agent tasks, the analytics query builder, media tools in the
agent, customer-facing agent. Each needs its own card.
