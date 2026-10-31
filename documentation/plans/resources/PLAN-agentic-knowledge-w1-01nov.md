# PLAN: AGENTIC-KNOWLEDGE P2 W1 - the agent answers WhatsApp contacts (read only, knowledge included)

Status: PLAN (owner answered card v2.1 on 31 Oct; build red-first next). Track: L (new principal, external ingest
surface; security review required). UAC: `agentic-knowledge-w1-acceptance-criteria.md`.
Card: `PLAN-agentic-knowledge-p2-31oct.md` (v2.1). Lane PR #2053, `crew-lane: AGENTIC-KNOWLEDGE-P2`.

## Owner answers (31 Oct, verbatim: "Wq1 a, wq2 b, shoundlt always go to marketing la, wq3 a, wq4 i just open
whatever we can do, wq5 a but i feel like we need to work on the control to be easier and straight forward and more
flexible, keep route cutoff")

- W-Q1 (a): a contact linked to an active CRM user runs as that user (today's agent, unchanged).
- W-Q2 (b): a knowledge miss offers the marketing product team whatever the contact's escalation switch. Crew is
  confirming the "shoundlt" wording; slice S4 is built last so the wording can still flip it (one condition).
- W-Q3 (a): the bot's read tools plus knowledge, each under the bot's own reveal key.
- W-Q4: W2 = every dealer write the agent can do safely, confirm-before-write, least risk first (section W2).
- W-Q5 (a) + a simpler access control model as a follow-up lane with its own mock (section "Access control lane").
- Router cut-off stays 0.70 (`router.DEFAULT_MIN_SCORE`); no change.

## No screen changes in W1

The per-contact Agent switch (`respond_contacts.chatbot_agent_enabled`) and the type audience already have their
controls. The contact gets no new mode or word: the agent's reply is the reply. So no mock in W1.

## Slices (one lane, one PR; tests first per slice)

`A` = `sorento_crm_backend/app`, `CHAT` = `A/services/chatbot`, `AG` = `CHAT/agent`.

### S1 - the contact principal (AG/access.py, AG/tools.py, AG/writes.py, AG/loop.py, CHAT/router.py one line)

- `AgentContext` gains `principal: str = "user"` (`"user" | "contact"`) and `access_codes: frozenset[str]`
  (the contact's ACTIVE access codes, `ContactAccessTypeService.get_contact_access_codes` filtered by
  `ContactAccessType.is_active`). `user_id` is `""` for a contact principal.
- `eligible_contact` (`AG/access.py:47`): an active linked user -> `(contact, user, None)` as today; no linked user ->
  `(contact, None, None)` (was refusal `no_linked_user`). `contact_not_found`, `ai_replies_off`, `switch_off` stay.
  `no_linked_user` stays in `AgentRefused`'s vocabulary for old callers but is no longer produced.
- `build_context`: no user -> `principal="contact"`, `user_name` = "" ; brand, company, grants, stock switch are read
  exactly as today (they are already the contact's).
- Tool gate for `principal == "contact"`: `CONTACT_TOOLS: dict[tool -> reveal key | None]` in `AG/tools.py`, used by
  `user_may_use` (exposure) and by `dispatch` (call time) instead of the user slug. A tool not in the dict is refused.

  | Tool | Reveal key (None = open to every contact) | Bot domain it mirrors |
  | --- | --- | --- |
  | `crm_knowledge_search` | None (audience rules in S2) | new |
  | `crm_products_find` | None | `master_products` |
  | `crm_resolve` | None; kinds `product`, `brand`, `category` only | resolver |
  | `crm_inventory_stock_balance_list` | `inventory.sellable` (+ `chatbot_stock_allowed`, existing `STOCK_TOOLS`) | `inventory` |
  | `crm_incoming_stock_by_product`, `crm_incoming_stock_shipments` | None | `incoming` |
  | `crm_procurement_po_placed_list`, `crm_procurement_grn_summary`, `crm_procurement_spo_allocations_last_receipt_list` | `purchase_orders.placed` | `purchase_order` |
  | `crm_procurement_po_last_cost_list` | `purchase_orders.cost` | `purchase_cost` |
  | `crm_report_ask` | `sales_orders.sales_report`; `dataset=chat` also `chatbot.analytics` (existing `ARG_CONTACT_GRANTS`); `basis=unpaid` refused (its gate is a user slug) | `sales`, `chat_analytics` |
  | `crm_order_management_orders_by_product_list` | `sales_orders.sales_report` | stricter than `order` |
  | `user_guides_read` | refused (staff only) | - |

- `searchable_kinds` for a contact: kinds in `CONTACT_KINDS = {product, brand, category}`; no slug read.
- `writes.permitted_writes` / `permitted_user_reads` return `[]` for a contact principal (W1 is read only; no
  `holds(None, ...)` call).
- `loop._system_prompt`: a contact principal is addressed as a customer ("You are answering a Sorento customer on
  WhatsApp."), never "working for <user>". `memory.current_conversation` keys on `user_id=None` + `grants_hash`.
- `CHAT/router.py:68`: `pending_action(..., user_id=str(user.id) if user else None)`. The only router edit; crew
  note to #2038 / #2051.

### S2 - knowledge for a contact (`A/services/knowledge_service.py`)

`search_for_contact(db, *, access_codes, query, top_k, embed)`; the same query as `search` with:
- type audience `dealer` -> the file's `access_levels` overlaps `access_codes - {"end_user"}`;
- type audience `public` -> the file's `access_levels` overlaps `access_codes`;
- type audience `staff` / `off` -> never;
- empty `access_codes` -> `{"status": "ok", "passages": []}` with no query run;
- company scope from the session (the contact's, stamped by `build_context`); `is_shared` as `_embedding_company_filter`;
- no `handoff_teams` in the result (team names are staff data).
`AG/tools._knowledge_search` calls it for a contact principal; the console operator check (`_operator_may_read`)
stays when an operator drives the turn.

### S3 - WhatsApp routing (`CHAT/inbox_queue.py` `_run_row`, `AG/loop.py`)

Before `engine.run_turn` (`inbox_queue.py:857`):
1. Read the row's text (`turn_runtime._envelope_text`) and whether the message carries an attachment.
2. `router.decide_route(db, contact_respond_id=contact, text=..., session_vars=None, has_media=...)`. The router's
   own gates (eligibility incl. the Agent switch, media, pending bot question, daily cap, length, Jev, min score
   0.70) decide; anything but `agent` -> today's bot, unchanged. A router exception -> the bot.
3. `agent` -> `run_agent_turn(..., is_test=False, rate_key=contact)`; its reply becomes one `send_message` action
   posted through the existing `_post` (split by `engine.split_send_actions`, the bot's own long-reply split). The
   inbox row is closed `done` with a trace record naming the agent turn id.
4. Agent busy / failed -> the fixed honest line (`AGENT_FAILED_REPLY` family, no "sorry", no "busy") posted the same
   way; never a bot re-run (router card rule 6).
- `run_agent_turn` gains `is_test: bool = True` (console default unchanged; WhatsApp `False`) and the rate limit
  keys on the contact when there is no operator.

### S4 - hand-off on a knowledge miss (W-Q2 b, one switch) - built last

Crew ruling 1 Nov: build (b) for now, keep it a single switch (owner wording "should" vs "shouldn't" pending).
- The agent arms the bot's existing single-team offer as the contact's open question
  (`session_vars.open_question`, shape of `turn/chat_state.py:631-640`): `team_pick`, `expects="yes_no"`, team
  `marketing_product`, agent `general_enquiries`, `payload.source = "knowledge_miss"`. Reply ends with
  "I couldn't find that in our product documents." plus the offer line. No ticket in the agent turn.
- The router sends the contact's answer to the bot (open question, `router.py:71-73`), so today's escalation lane
  makes the ticket on the contact's own "yes".
- Barred contacts: ONE switch `knowledge_service.KNOWLEDGE_MISS_IGNORES_ESCALATION_BAR = True`, read at ONE place,
  the turn's profile load (`turn_runtime.py:534`, not `engine.py`): when the contact's open question is a
  `knowledge_miss` offer and the switch is on, that turn's profile has `escalation_allowed = True`, so every
  backstop (`engine.py`, `compose.py`, `answer_bridge.py`) lets the one answer through without being edited.
  Switch off -> barred contacts get "Please refer to your salesman." and no offer is armed.
- Staff-tier profiles (`is_staff_profile`) are never offered (unchanged rule).
- Contract (names the tests use):
  - `knowledge_service.KNOWLEDGE_MISS_IGNORES_ESCALATION_BAR = True` (the one switch),
    `KNOWLEDGE_MISS_SOURCE = "knowledge_miss"`, `KNOWLEDGE_MISS_LINE = "I couldn't find that in our product documents."`.
  - `knowledge_service.arm_knowledge_miss_offer(db, contact_pk) -> bool`: writes `respond_contacts.session_vars
    ["open_question"]` = `pending.to_wire(team_pick ...)` (team `marketing_product`, option payload
    `{"team": "marketing_product", "agent": "general_enquiries", "brand_code": None}`, `expects="yes_no"`,
    `payload={"source": "knowledge_miss", "agent": "general_enquiries"}`), keeping every other session key.
    Returns False and writes nothing when the contact is barred and the switch is off.
  - Local agent tool `crm_knowledge_handoff` (no arguments), contact principal only, model-chosen (no word list):
    the protocol tells the model to call it when the documents do not answer. It arms the offer; the loop then makes
    sure the final reply carries `KNOWLEDGE_MISS_LINE` and the offer sentence (code-added, like IDEATE's note).
  - `turn_runtime.load_profile`: barred row + switch on + the row's `session_vars.open_question.payload.source ==
    "knowledge_miss"` -> `escalation_allowed=True`; anything else unchanged.

### S6 - ideas leave test mode (crew ruling 1 Nov, from AGENTIC-IDEATE #2038)

The owner ruled agent ideas stay TEST only until the agent reaches WhatsApp; this lane is that trigger. Depends on
#2038 merging first (the flag and the list live on its branch): merge main, then
- flip `agent/writes.py` `IDEA_IS_TEST` to False;
- do the to-do list in `documentation/plans/chatbot/PLAN-agentic-ideate-31oct.md` "To do when `IDEA_IS_TEST`
  flips": drop the second source in `crm_ideas_list` and the test-only edit rule; decide the view-only operator
  create; bound the values handed back to the model while waiting; strip the remaining invisible characters (Mn
  from U+E0100, CGJ, Hangul filler, braille blank); use-case edit merge rule; escape look-alike quotes; carry the
  turn's own text to `raw_transcript`; give the ss non-`captured` replay and 4xx their own lines.
- Note: idea writes stay user-principal only (a contact principal has no writes in W1), so on WhatsApp only linked
  staff contacts create ideas.

### S5 - eval and evidence

- Kill tests per slice (reviewer runs them). Zero-leak run: a contact principal over staff-audience chunks -> 0.
- Gold set seeds (the real question shapes from the crew data) stay in the crew folder; the scorer is the P1 scorer
  pattern. The gold eval needs real documents + Gemini embeddings, so it runs on the crew machine, not in this
  cloud sandbox (stated in the PR).
- Console pass: the console already routes through the same router and agent, so an unlinked pilot contact is
  testable there with no WhatsApp send.

## W2 - dealer writes (next lane, after AGENT-CONFIRM-GATE #2055), least risk first

| # | Write | Existing service | Permission / gate for a contact | Risk |
| --- | --- | --- | --- | --- |
| 1 | Drawing / quotation / photo request (hand to marketing product team) | escalation lane + SLA row | escalation route (W-Q2) | low: creates a task, no money, no stock |
| 2 | Warranty / complaint claim | `crm_complaints_*` (`contracts.py:115-117`) | contact must own the order / product; reveal TBD | low-medium: customer-facing case, no stock |
| 3 | Order request (send order) | `send_order.py` | reveal `sales_orders.outstanding` + customer link | medium: stock and price |
| 4 | Order cancel | `crm_order_cancel` | own order only | medium-high: reverses a commitment |
| 5 | Reserve request | reserve flow (#2046) | own customer | medium |
Today's agent writes (opportunities, contact update, purchase-request decide / undo) stay user-principal only.

## Access control lane (follow-up, own card + mock, does not block W1)

Owner: "we need to work on the control to be easier and straight forward and more flexible". Today the answer to
"who can read this document" is spread over four places: the type's `ai_audience`, the file's `access_levels`
(per-brand codes), the per-contact type grants, and company scope. Proposal for that lane: ONE "Document access"
view per attachment type listing, as a matrix, audience x brand code (who can read in AI / who can download), with
the contacts holding a grant underneath, editable in place; and per contact, a "what this contact can read" preview.
Named, not built here.

## Who owns which file

`inbox_queue.py` hook, `agent/access.py`, `agent/tools.py` contact gate, `agent/writes.py` (two empty-list guards),
`agent/loop.py` (prompt line, is_test, rate key), `knowledge_service.py`: this lane. `router.py`: one line only.
`engine.py`, `console_service.py`, panel: untouched (UNIFY #2051). #2038 adds labels to `agent/writes.py` / router
criteria: rebase only.
