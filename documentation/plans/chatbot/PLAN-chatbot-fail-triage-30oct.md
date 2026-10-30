# PLAN: chatbot failure-reply triage (30 Oct 2026)

**Status:** Batch 1 building (feature track M, lead pattern: tester red -> coder -> reviewer).
Owner answered Q1-Q5 on 30 Oct ~21:15; Q1 escalation routing evidence filed as a second ask
(routing change waits on it). UAC: `chatbot-fail-triage-acceptance-criteria.md`.

## Owner answers (30 Oct ~21:15)

- Global: never "Sorry, I am busy" or "Sorry, I ran into a problem understanding that"; every failure
  path gets an honest, specific reply. "Couldn't find X" is fine.
- Q1: evidence first (filed): the customer_service team is the code default (`contracts.py:264`,
  `turn_runtime.py:2177`) paired with the default agent general_enquiries (`contracts.py:282`), which
  has no customer_service team.
- Q2: dealer cost = the dealer promotion's `dealer_cost` (UAC AC-5).
- Q3: keep the category flag; the reply is a plain "Couldn't find X".
- Q4: parser extracts code head + size as a spec; the size is the trap length (UAC AC-6).
- Q5: add the price tag request form. Not prompt-only (UAC AC-3).

## Batches

- Batch 1 (now): AC-1 (every generic / busy path, C2 C4 C6 C8 included), AC-2 (F3), AC-3 (F7), AC-4.
- Batch 1b (after the Q1 answer): escalation picks agent + team as one reachable pair, default
  general_enquiries -> marketing_product, assignee uuid only from an assignee option.
- Batch 2: AC-5 dealer promotion cost, AC-6 code + size (parser prompt via md5 pin, owner publishes,
  eval gate).
- Outside this repo: C7, the n8n `sub-error-logger` text "Sorry, I couldn't process that just now"
  lives in n8n (never touched from a lane); its fix is an n8n promote by crew / owner. CRM side: the
  turn answers before n8n's ~60 s give-up (UNVERIFIED number, n8n config not in the repo).

## Ask

Owner, 30 Oct 2026: "There are a lot of sorry I couldn't process, I couldn't understand. Can you
identify the root cause for all of them and solve it?"

## Data and method

- Prod backup `sorento_prod_1028` (taken 28 Oct 2026), read-only (`BEGIN READ ONLY ... ROLLBACK`).
- Window: 28 Sep - 28 Oct 2026. 24,819 bot messages (`chat_histories` type outgoing, not human
  agents) to 495 contacts.
- What the contact received: `chat_histories.message`. Why: the turn row `chatbot.turns`
  (`status`, `stage`, `branch_kind`, `error`, `trace[]`), joined on `chatbot_turn_id`, else on the
  same contact within 240 s before the reply. Model / tokens: `analytics_connector.llm_calls`.
  Photos: `media_extraction_job`.
- Audience: `respond_contacts.chatbot_profile.tier` is null on all 495 contacts in the backup, so
  `is_staff_profile` (`turn/state.py:259`) reads every contact as a customer. This report counts a
  contact as staff when it holds any `*_office` access type.

## Volume

| Template (EN; MS/ZH in `label_catalog.py`) | Source | 30 d | staff / customer |
|---|---|---|---|
| "Sorry, I ran into a problem understanding that..." | `chatbot_reply_copy.py:97` | 31 | 13 / 17 |
| "Sorry, I couldn't process that just now - something went wrong on our side..." | n8n `sub-error-logger` | 11 | 4 / 7 |
| "Sorry, I am busy right now..." | `llm_call.py:39` | 6 | 1 / 5 |
| "I could not read anything from that photo..." | `media_extract/wording.py:291` | 37 | 8 / 27 |
| "I could not fetch {label} just now..." | `turn/compose.py:662,689,715` | 43 | 19 / 23 |
| "Sorry, you are not allowed to access purchase cost" | `chatbot_reply_copy.py:104` | 40 | 1 / 39 |
| "Could not find portal link for attachment price tag template" | `lanes/business/answer.py:4499` | 9 | 8 / 1 |
| "Couldn't find X. Did you mean..." | `dealer_stock.py:112-115`, `answer_bridge.py:2230` | 1,616 | 391 / 1,207 |

Explicit failure texts: 177 (0.7% of bot messages), flat by day (0-14 a day; spike 24 Oct = photos).
"Couldn't find": 1,616 (6.5%), 185 contacts.

## Causes

| # | Root cause | Replies | Evidence |
|---|---|---|---|
| C1a | Exact code hidden because its CATEGORY is `is_searchable=false` | 11 seen (PROJECT, CB-ACC; flipped true 9 + 28 Oct); VD (73 active) + RET-006 (1) still hidden | `models/product.py:521-526` applied on the exact tier `entity_resolver.py:866` and `:3876`; audit_logs flip times match the first success |
| C1b | Code typed without its dash/slash, or brand/company scope hides it, or product created later | ~100 | `contact_brand_scope.py:150-176` (contact brands lack MOCHA for M6333 / MSC02) |
| C1c | Real code + size glued ("SRTWC286200MM" = SRTWC286-SH + 200 mm) | 264 (94 contacts) | `resolve_gate.py:548-563`, `product_code_family.py:44,59-68`, `entity_resolver.py:846,5624,5635` |
| C1d | No such code (typo / unknown variant), did-you-mean shown | 805 (720 with suggestions) | designed path |
| C2 | Escalation after the contact says "Yes" fails, contact gets "problem understanding" | 17 of the 31 | agent `general_enquiries` has no `customer_service` team link, `incoming_stock_enquiries` no `warehouse` link (`agent_teams`), `marketing_form` no SLA policy; raised `next_assignee.py:180-187`, `sla_service.py:4127`, caught `engine.py:10407-10475` -> `_failed_result`; 1 case passes the Mocha company id as `preferred_assignee_id` |
| C3 | Dealer asks "my cost / dealer cost / cost price" and the parser reads supplier purchase cost | 40 (25 contacts) | `head/parser_template.py:238` (R-P3-02), denial `lanes/canned.py:56-95` |
| C4 | Fetch outcome worded "could not fetch": empty set (10), report 422 subject_required (5), attachments on a held 201-product set (9), MCP 10 s timeout on stock / orders (10), other (9) | 43 | `turn/compose.py:662,689,715`, `config.py:203` |
| C5 | Photo: Gemini 402 prepaid credits depleted 24 Oct (11), non-object JSON (2), 503 (1); nothing readable on a plain product photo (~23) | 37 | `media_intake.py:431,470` |
| C6 | Parser provider: OpenAI 20 s timeout (6, cluster 14 Oct 02:38-04:04 UTC), 403 (2, 12 Oct) | 8 | `llm_call.py:49-52`, `engine.py:5348-5402` |
| C7 | n8n gives up at ~60 s after turn start (CRM assumes 90 s): slow parser/route step (2), stuck `processing` (2), queue wait (1), CRM done in <10 s (3, UNVERIFIED why) | 11 | `send_order.py:74`; n8n config not in repo |
| C8 | First message races contact creation: "Respond contact not found" | 15 turns, 6 generic reply, 9 silent, all 30 Sep - 5 Oct | `engine.py:3262,3272` |
| C9 | Staff ask for a portal link to request a price tag; portal-link tool does not offer that form | 9 | `mcp_tool_capability_service.py:1442` |
| C10 | Code bugs: `TypeError: unhashable type: 'dict'` in the business lane (2), ideation MCP arg validation (1) | 3 | turns 15 + 26 Oct |

## Drift (releases #8 b07e71d5bf, #9 257b6967eb; backup predates them)

No change to the parser prompt, provider timeouts, rate-limit copy, media_extract, escalation
routing, respond-contact lookup or `turn/compose.py`. Plausible movers: #1967 LOOKUP-EMBED-CENTRAL
(new lookup word store) and #1982 AGENTIC-P1 (`lanes/business/fetch.py`). Nothing on main after
#9 fixes any cause above.

## Fix slices (Phase 2, after the owner answers)

| Slice | Cause | Track | Change |
|---|---|---|---|
| F1 | C2 | S + config | escalation offers / routes only a team the agent can reach; a routing gap never answers "problem understanding"; fix the assignee/company swap |
| F2 | C1a | S | exact-code tier ignores the category flag (product flag still applies), or says "not offered" |
| F3 | C4 | S | honest outcome per reason: none found / ask whose sales / ask which product / one MCP retry |
| F4 | C3 | M (prompt, md5 pin, owner publishes) | dealer's "my cost" is the dealer's own price, never supplier purchase cost |
| F5 | C1c | M | code + size resolves to the family variant |
| F6 | C1b | S | hidden-by-scope says "not in your range", not "Couldn't find" |
| F7 | C9 | S | portal link offers the price tag request form |
| F8 | C8 | S | first-message contact race retried |
| F9 | C6, C7, C10 | S | provider fallback, n8n budget alignment, the 3 code bugs (red tests from the real turns) |
| ops | C5 | - | Gemini prepaid credit alert (billing, not code) |

Each slice: red test first from the real failing turns (gold cases), then the fix, kill test,
reviewer, chatbot eval gate. Standing rules: semantic fixes only (no regex/word-list guards),
prompt changes via md5 pin + owner publishes, staff Gemini / customers OpenAI.
