# PLAN: AGENTIC-UNIFY panel, the staff principal on the chatbot brain

Status: owner answered Q1-Q3 on 31 Oct 2026, all (a) ("q1 a q2a, q3a"). UAC written. Slices 1 (staff principal, live chat turn) and 2 (agent side, write routes, report path, opportunity, escalation) and 3 (page context) built; slice 4 (panel screen) in Phase 2. PR 3 of 4, builds on #2048 (identity) and the console PR (shared parts). Full pipeline, size L.

Behaviour: `CARD-agentic-unify-v2-31oct.md` and its owner table (on branch `crew/agentic-unify`, #2048). Its section 2 (test path) was overruled by the owner: a panel turn is live, with no WhatsApp send. This plan replaces that section.

`A` = `sorento_crm_backend/app`, `S` = `A/services`, `CHAT` = `S/chatbot`.

## Corrections to card v2, from the audit

- **Session:** the card's "console's existing per-run route" is dry-run only (`CHAT/engine.py:4211, 4237, 5005-5006, 8633`). A live panel turn needs a per-thread session store.
- **Daily cap:** a per-thread key caps per thread. Count the user's threads instead (`CHAT/router.py:160-170`).
- **No lane switch override needed:** `chatbot_business_lane_enabled` has no reader in the turn, `chatbot_completed_lanes` reaches only a trace fact (`CHAT/engine.py:5958, 7146`), and `completes_here` is a constant (`:7222`). `_lanes_on()` changes no routing. `offload=False` covers what the panel needs.
- **Escalation has no phantom row today:** with no phone, the assignee read is a 400 before the cursor moves, and the turn fails (`api/v1/external/next_assignee.py:420-425`, `CHAT/engine.py:10604-10629`). The risk appears when someone adds a staff phone to get past it.

## A live panel turn, every switch

Audited 31 rows: keep 8, skip 13, redirect to the user 6, owner decision 4.

| Decision | Behaviour |
| --- | --- |
| **Skip, panel exits first** | Phone gate and staff comment (`CHAT/engine.py:3175-3190`), the top accidental side effect: it would call Respond on the first panel message, before any other gate |
| **Skip** | Inbox queue (guard at `CHAT/inbox_queue.py:226`); worker offload (`offload=False`); session write log (`CHAT/engine.py:12615-12637`); profile facts; salesman job; assign and comment actions; takeover; media quota; trace Retry into live n8n (`api/v1/system/chatbot.py:493`, refuse for panel); ideate state, keeping the /ideas link until AGENTIC-IDEATE lands |
| **Skip, close honestly** | Delegate close: add panel at `CHAT/engine.py:8676`, or a `delegated` row is left with no reply. A non-null `delegate` is a failure |
| **Reserve** | The ingress literal at `CHAT/contracts.py:441-442`, and at `api/v1/external/chat.py:196`, or an API-key caller could claim "panel" |
| **Redirect to the user** | AI gate and scope (`CHAT/engine.py:1072-1117, 3519`); session store; usage logs carry `user_id`; low-stock and sales-analysis files go to My Downloads, never a claim for WhatsApp (`api/v1/scm/low_stock_report.py:672-679`, `api/v1/sales/analysis.py:465-468`); opportunity gate and audit actor (`S/sales/opportunity_chat.py:60-79`); agent eligibility and cap |
| **Keep** | `dry_run` false, pinned; dedup with a unique message id, rendering `duplicate=True` from its row; earlier-message answering, rendering in order; previous reply and Jev state, by thread key; frames; resolver usage; quick replies and `send_attachments` rendered; live trace views, filtered by ingress |
| **Owner, Q1-Q3** | Escalation draw and SLA row; stock ask rows; analytics facts |

`run_turn` executes no action itself; callers do (`CHAT/inbox_queue.py:716-745`). The panel renders `send_message` and `send_attachments`, and drops `assign_conversation`, `add_comment`, `update_contact_fields`.

## Owner questions, all answered (a)

**Q1. A staff member's panel question escalates. Who gets it, and how?** It must reach a real person (owner ruling). The draw is a round-robin member of the topic's team, or a named person.
(a) SLA task with no contact: the assignee gets it in My Pending with the SLA clock and an in-app notification (`S/sla_service.py:4406, 4507-4556`), WhatsApp off for this kind. Needs a new branch: `create_tracking` refuses with no contact, though the column is nullable and form rows already have none (`A/models/sla.py:107, 127`).
(b) In-app notification only (`S/notification_service.py:174`): no clock, no task.
(c) IT ticket (`S/ticket_intake_service.py:97-125`): wrong audience for stock or sales.
(d) Email: `S/email_event_registry.py` has no chatbot event.
**Recommend (a):** same clock and task list as customers' escalations, no WhatsApp. The panel's draws share the customers' rotation. The wording "they will reply shortly" (`CHAT/lanes/escalation.py:82`) has no return path to a panel thread, so the reply names the person and says they will follow up directly.

**Q2. Should a panel reply that refers someone create a row on the Customer asks tab?** (`S/stock_ask_service.py:163-165`.) (a) No. (b) Yes, with no contact and no customer.
**Recommend (a):** that tab is customers' asks, and these rows would have neither.

**Q3. Do panel turns count in chatbot analytics?** (`CHAT/analytics/facts.py:84, 116, 363`.) (a) No, they stay in the panel's own usage views. (b) Yes, as an "unknown" audience.
**Recommend (a):** keeps customer figures clean; adding them later is easy.

## In-process reads

AC-6: every read a lane makes inside the process rather than through MCP, for a staff principal. A gate is one line at the read, `staff_principal.lacks(db, slug)`; a staff member lacking the slug gets no rows, and a contact's turn never reaches the check. MCP reads carry the staff identity and the route's own gate (#2048), so they are not listed. `CHAT/lanes/business/services.py` is `S.py` below.

| Read | Where | Slug or open | Why |
| --- | --- | --- | --- |
| Promotion kinds (parser list, kind check) | `CHAT/turn_runtime.py:829`, reached by `CHAT/head/lookup_lists.py:564` | `marketing.promotions.view` or `dealer_kit.page.view` | The promotions list's own readers (`api/v1/marketing/promotions.py:45`) |
| Promotion hold check (menu choices) | `CHAT/turn_runtime.py:800` | Same | Runs the promotions read in process |
| Promotion name check | `CHAT/turn_runtime.py:617` | Same | Denied means no word names a promotion |
| No-such-kind reply | `CHAT/answer_bridge.py:664` | Same, by reach | Needs a kind `promotion_kind_rows` let through |
| Customer list for the parser | `CHAT/head/lookup_lists.py:613`, gated at `CHAT/engine.py:1252` | `order_management.customers.view` | The customer screen's slug. Never narrowed to links: a staff principal has none |
| Customer account levels | `S.py:613` | `order_management.customers.view` | Customer data |
| Customer names for the gate | `S.py:629`, `CHAT/turn_runtime.py:3240` | `order_management.customers.view` | Customer data |
| Carried customers at turn start | `S.py:647` | `order_management.customers.view` | Denied means nothing is carried |
| Customers a word could name | `S.py:866` | `order_management.customers.view` | Customer data |
| Customer line under a report | `S.py:512` | `order_management.customers.view` | Customer data |
| Sales agent list for the parser | `CHAT/head/lookup_lists.py:589`, gated at `CHAT/engine.py:1252` | `master_data.sales_agents.view` | The sales agents screen's slug (`api/v1/master_data/sales_agents.py:51`) |
| Sales agents a word names | `S.py:822`, `CHAT/lanes/business/report_ask.py:1194` | `master_data.sales_agents.view` | Same |
| Supplier names in the low stock ask | `CHAT/lanes/business/low_stock_ask.py:162` | `procurement.suppliers.view` | The suppliers screen's slug |
| A salesperson's own customers, to log an opportunity | `S/sales/opportunity_chat.py` `staff_customer_options` | Their own agents' customers, else `sales.opportunities.add` | The save asks for the slug again; a user with neither gets nothing |
| Resolver | `S.py:155` (`resolve_reference_post`), `CHAT/turn_runtime.py:2501` | Each kind by its slug, `KIND_SLUGS` of `CHAT/agent/tools.py` | Corrected by review: #2048 AC-14 keeps `lookup/resolve` open as a picker, but this in-process call returned customer names to a user with no customer slug. The agent's `crm_resolve` already refuses that kind |
| Purchase request and sponsorship cards, later pages too | `CHAT/lanes/business/__init__.py:1672-1696` (`ref_status`) | The kind's `.view`, else `.view_own` with `own_scope.request_in_scope` | Added by review: they were gated on `purchase_orders.placed` alone |
| Sales order cards | `CHAT/lanes/business/__init__.py:1587` (`so_status`) | `order_management.orders.view`, already held by `contracts.py:326` `visible_reference_kinds` | Added by review, no leak: pinned by `test_a_sales_order_card_needs_the_orders_view`. PO ref cards never reach a staff turn, which clears `po_refs` |
| Products, sets, families, spec values | `S.py:406, 588`, `CHAT/head/candidates.py`, `grounding.py`, `held_family.py`, `closed_lists_index.py`, `bare_size.py`, `lookup_lists.py:488, 754` | Open | #2048 AC-14 |
| Categories and classes | `S.py:766, 981`, `CHAT/head/lookup_lists.py:628` | Open | #2048 AC-14 |
| Brands | `CHAT/turn_runtime.py:554`, `S.py:535, 885`, `CHAT/head/lookup_lists.py:546` | Open | #2048 AC-14 |
| Warehouses | `S.py:548`, `CHAT/head/lookup_lists.py:575` | Open | #2048 AC-14, pinned by `test_warehouse_names_stay_open_to_any_staff_member` |
| File type and certificate names | `CHAT/turn_runtime.py:3427`, `CHAT/head/lookup_lists.py:526`, `scheme_index.py`, `closed_lists_index.py`, `grounding.py` | Open | Words to read a message by, no file. The files come through MCP on `master_data.product_attachments.view` |
| Sales order PO ref behind a resolver hit | `CHAT/turn_runtime.py:5675` | Open | The value only filters the MCP read that follows, which asks the user's own slug |
| Access level names | `S.py:126` | Open | Level names, no customer or price. The office level of every active brand |
| Teams and agents for an escalation | `CHAT/lanes/escalation_services.py` | Not reached in this slice | Escalation is slice 3 |

Trigger to centralise: none needed while one line at the read does it; a second principal type would pay for a table.

## Slice 3: the page reaches the brain (AC-19, AC-20)

**Architecture.** Layer: `panel_service` is the only reader of the client's snapshot; it decides what may go on, once, before the turn. Shared mechanism: the principal already carries a turn's staff facts to every seam, so the small page summary rides it. Classes this fixes: any question about the open page, for all four record kinds and for pages with no record, not one shape of question. No registry, no new table.

| Consumer | Receives | Where | Why this shape |
| --- | --- | --- | --- |
| Parser | One line, `Current page: {json}`, directly above `Current user message:`, at every context level | `ContextLayers.page_line`, `turn/context.py` `_render_l1` and `_assemble_off`, filled at `engine.py:5378` from the principal | JSON-quoted and bounded (400 bytes) as the L5 rule requires: a title holding a newline or `Current user message:` cannot make a line of its own. No visible text: it would pollute a mini parser's reading |
| Jev | `state["current_page"]`, the same dict; key absent with no page | `router.py` `_state`, panel branch | Published criteria already send "a why or an explanation drawn from the records" to the agent, so no prompt changes. A live probe checks this; if Jev picks chat, the owner publishes a criterion |
| Agent | One data message: title, path, visible text (cut at 6000, the frontend's own cap, `raw.slice(0, 6000)`), record facts JSON | Joined onto `context_after`, so it sits right before the question | Never the system role: outside text stays out of it (`agent/loop.py:711`). Dropped while a proposal waits, as all bot context is. Says to quote `display_ref`, never a UUID, as `respond()` does today |

The summary on the principal: `page: dict | None`, keys `title`, `path`, `record_kind`, `record_ref`, the last two only when the record may be read. It reaches the turn's envelope, so it carries no visible text and no facts. All blank snapshot means `page` is None.

**Permission.** Facts come from `RecordContextService.assemble`, behind `can_read_record_context`, the same two calls as `ai_assistant_service.py:1143-1154`. Refused, unknown kind, missing row or any failure: no facts and no record keys, the turn still answers, title and path stay (they are the user's own screen). A failed read rolls back so the turn's next query runs (an id that is not a UUID is a DataError on Postgres).

**Parity.** No page: not one byte changes for the parser, Jev or the agent, on any ingress. No prompt is touched, so no gate. The chat lanes get no record tool: a page question Jev sends to chat is measured in the labelled set before default.

Caps on the client's text: title 255, path 500, search 500, visible text 6000 characters, before any of it reaches a consumer.

## Slice 4: the panel screen (AC-18, AC-21 to AC-24)

**Architecture.** Layer: the server decides what a reader may see and what state a card is in; the panel only draws what it reads back. Shared mechanism: the console's own parts (`AgentTurnParts.tsx`, `RoutePill.tsx`, `TurnAttachments.tsx`), imported where they stand, no move. Classes this fixes: every brain reply on the panel, chat or agent, and every card state, live or after a reload. Which renderer a message gets is decided by `metadata_json.route`: present means it came from the brain, absent means today's markdown, so old threads and users without the permission see no change (AC-26).

**Server, gaps the audit found:**

| Gap | Today | Fix |
| --- | --- | --- |
| Files | `panel_service._rendered` keeps only `filename` and `url`, and `TurnAttachments` also needs `mimeType` and `attachmentType` | Keep the stored file as it is |
| A card after a reload | The turn's `pending_action` and `actions` are frozen in `metadata_json`, so a decided proposal still shows Confirm | Both are read live when a thread is read, one query per thread (`agent_actions.actions_by_turn`, `pending_action`), for both routes that return messages (`api/v1/system/ai_assistant.py:305, 336`) |
| The outcome | A decision writes nothing to the thread, so it is gone after a reload | Confirm, cancel and withdraw append the outcome as an assistant message with `route` agent and the outcome's status. A refused decision appends nothing. A deleted thread still decides, and appends nothing |
| AC-23 is a screen rule only | `_message_to_response` returns all of `metadata_json`, so steps, tool calls, usage and the route's score reach anyone's network tab | Stripped on read for a user without `system.ai_assistant_settings.view`: of `agent`, only `pending_action` and `actions` stay; `chatbot_turn_id` and the route decision go. `route` stays, it picks the renderer |
| The pill's data | `message_metadata` keeps only the side | Store `decision.as_response()` as `route_decision`, the shape `RoutePill` reads |

**Screen:**

- `lib/whatsappText.ts` gains `parseWhatsAppBlocks`: text and list blocks. A list item starts with `- `, `* `, `• `, `1. ` or `1) `; a `*bold*` line is not an item, because the marker needs its space; numbering is kept; fenced code stays whole. New `components/chatbot/WhatsAppBlocks.tsx` draws real lists with a hanging indent and each line through `WhatsAppText`. `WhatsAppText` itself stays untouched, so the console and the inbox do not change (AC-25).
- `AIAssistantBubble.tsx`: `WhatsAppBlocks` and `TurnAttachments` on a brain reply; `ProposalActions` and `ActionsBlock` for everyone on a reply that has them; `RoutePill`, `StepsDisclosure`, `ReplyMeta` only with `canViewTrace`. The trace link on a brain reply goes to `/system-management/chat-history?turn=<chatbot_turn_id>`, today's link stays on an old reply. Chips already read `suggestions`.
- Confirm, Cancel, Undo and a countdown's end all reload the thread and draw what comes back, no local outcome state. So a reload and a live view cannot differ. A refused decision shows its plain reason as a toast and reloads too.
- `lib/aiAssistantChatApi.ts` gains the three action calls, using `extractApiError`.

## Review round 1 rulings

Reviewer and security-reviewer at c50bd32793, both failed. All fixed red first, except where stated.

- **Rollout gate (AC-1):** `check_user_has_permission` passes every admin and superadmin, so they would move at deploy and lose answers until PR 4. This one slug reads the role's own grant. Superadmin needs the grant too.
- **A panel escalation is marked:** `source_entity_type = "panel_escalation"`, not "no contact". A customer's row whose contact was deleted also has no contact, and its people keep their WhatsApp (AC-25). The marker switches WhatsApp off everywhere, takeover paths included (`S/sla_takeover_service.py:447, 453, 494, 554`), and takes the row out of the tier runner.
- **Limits:** 20 panel messages a minute per user, the old path's figure, and 5 panel escalations an hour per user. Both one line on `rate_limit.hit`, both a plain reply. **Refused:** a row cap that does not need Redis. Every limiter here fails open, and nothing shows this one needs to be the exception. Trigger: a staff member actually flooding a colleague.
- **Company of an escalation:** only the principal's `active_company_id`. None means no draw, no row, an honest reply. A stored body's `company_id` stays as it is: security re-ran it and found no production writer, `engine.py:6371` drops a foreign company, and a thread drops `variables` after the turn. Trigger: anything that stores a routing company on a panel thread.
- **Reveal keys on the staff read path (AC-7):** asked of both users through `gate_user_ids`, as the invoiced gates are. Exposure stops at act-as.
- **Impersonation:** the principal carries the real user, so both audit stamps (`CHAT/agent/writes.py:152`, `S/sales/opportunity_chat.py:145`) name them.
- **The page:** the note is one JSON object after its header, so screen text cannot fake a section. "Authoritative" belongs to the record facts alone. The parser's page line is left out while a question is open, as the agent drops its context while a proposal waits.
- **Screen:** a reload for a thread no longer open is thrown away, and an older reload never overwrites a newer draw. Ordered items keep their printed number (`li value`), because a reply of 3 must mean the row marked 3. A line under an item stays in that item until a blank line or the next marker: the stock cards' shape. An ordered marker is 1 to 3 digits, so `2026. x` is text. A proposal past its time reads Expired, for the console too: it is the same read, and "Waiting" with no button helps nobody.
- **Smaller:** the turn id leaves `pending_action` for a reader without the slug. `POST /agent/conversation/new` refuses a panel key. A failed agent turn rolls back (AC-24). A sales agentless holder of `sales.opportunities.add` can log a prospect (AC-12).
- **Not fixed:** `TurnAttachments` has no URL scheme allowlist. React blocks `javascript:` and the linkifier allows only http(s), so it is not exploitable.

## Review round 2 rulings

Reviewers at fdef525938. Fixed red first:

- **Customer names, two more reaches:** a DO number prints the debtor's name (`S/entity_resolver.py:1046, 2172`), so `customer_order` needs `order_management.orders.view`. The casual lane resolves on its own (`CHAT/lanes/casual.py:132`), so it takes the same filter.
- **Import boundary:** the round 1 fix made core import the chatbot package (`S/entity_resolver.py:1167`, `S/sales/opportunity_chat.py:144`). The lane hands the read check and the real user in.
- **Screen:** Undo no longer waits on a send, or the window could lapse with the button disabled and the change commit. A failed send counts as a draw. A send's answer for a thread no longer open is dropped: this predates the lane, but agent turns take long enough to hit it, and the open thread ref exists now.
- **Label:** a marked row reads `Task`, as before, never `panel_escalation` (`team-pending/components/TeamPendingList.tsx:85`).

Not changed, shown at hand test: the closing line of a proposal ("Reply yes to go ahead", `CHAT/agent/loop.py:510`) and of `composers/status.py:38-40` sits inside the last list item, one indent. A blank line before it would change WhatsApp and console text, and the words are unchanged either way.

Accepted for hand test: `*Co B:*` under `3. Carol` sits inside that item, since it has no blank line before it (`tail/member_offer.py:255-262`). It needs more than one routing company, and the principal has one.

## Still to count or prove

- A live overridden turn has no test (`tests/chatbot/test_console_switch_override.py:150, 175`); runtime UNVERIFIED.
- A panel reset writes its frame through `CHAT/turn/memory.py`, keyed on the thread and with no embedding enqueued; `S/frame_service.py` is n8n's path and is not reached. Read from the code, no test pins it.
- Slices follow the answers; the page context layer and panel rendering are as in card v2 section 4 and mock v1.
