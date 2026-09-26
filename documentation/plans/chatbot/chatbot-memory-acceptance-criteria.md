# UAC - Chatbot memory: contact profile, episodes, turn context under a token budget

Plan: `PLAN-chatbot-memory-26sep.md`. Issue #1282. Numbering: AC-MEM001 to AC-MEM099, grouped
by slice. Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` recorded agent-browser run, `[T]`
test evidence named in the line. Every criterion names its evidence.

Status: DRAFT 26 Sep 2026. **Written to the recommendations** of the plan's "Grill questions
for the owner" (Q1 to Q14). Where the owner answers differently, the ACs tagged with that
question (`(Qn)`) are rewritten before any code.

Terms: "contact" = a Respond.io contact through `/api/v1/external/chat/turn`; "dealer" = the
person behind it; "staff" = a CRM user with `user_management.contacts.view` (read) or
`.edit` (write); "operator" = a CRM user with `system.chat_history.view`; "episode" = one
`conversation_frames` row; "live episode" = the contact's turns since the last episode's
`closed_at`; "est. tokens" = `ceil(utf8_bytes / 3)`.

## Journey

### A. Mr Tan, a dealer on WhatsApp (the owner's "human conversation")

The system already knows, before he types: who he is (contact, linked customer Chin Chun
Trading, segment dealer, salesperson Aina), what he usually asks about (products SRTWB1455 and
M486-75-BL, site Kuching, tallied from his closed episodes), what he told the bot about
himself (role purchaser), what he asked in his last three conversations (one line each), and
what he said a minute ago in this one. He is never asked for any of it again.

1. Thursday 10:02. "stock SRTWB1455". Normal stock answer.
2. 10:03. "and in kuching?". The parser sees his earlier message in this conversation and
   carries the product; Kuching stock.
3. 10:05. "outstanding DO for chin chun". Topic switch: the stock conversation is closed as an
   episode with the summary "Thu 25 Sep, 2 turns: stock SRTWB1455 (answered)." The DO report
   renders.
4. Friday 09:10 (a gap of more than 30 minutes). "morning boss". The Thursday DO conversation
   is closed at intake; the bot greets him by name, names what he looked at last time and
   offers to re-run it.
5. "any update on that DO?". Resolved from yesterday's episode; the report re-runs with
   today's data, opening with one line naming what was carried.
6. "what did I ask you last week?". A numbered list of his recent conversations, no old
   figures, "reply with a number and I'll run it again".
7. "can give 10% discount for SO-2409-0112?". The bot cannot approve it; it says so in one
   human sentence and offers to pass it to Aina with the SO attached (yes / no).
8. "I'm the new purchaser, taking over from Mr Lim". Noted as a fact; nothing about his
   access changes.
9. "stock for the usual". His two usual products, Kuching first.
10. "I want to talk to a real person". Handover to Aina carrying what they were just
    discussing.

At no step does he get a bare refusal, silence, or an error text.

### B. Staff looking at what the bot knows

Sidebar > User Management > Contacts > Mr Tan > Chatbot card. Under the existing toggles:
"What the bot knows" (each fact with a CRM / Learned / Said / Staff badge, last seen,
expires), "Recent conversations" (one line per episode, opens Chat History), "Open orders"
(live). Staff add a note, correct a learned fact (it becomes Staff), or delete one (a
countdown on the button, no dialog). Two decisions at most: what to change, and Save.

### C. Operator troubleshooting a turn

Chat History > a turn. The Memory panel shows focus, profile and episodes before and after,
the episode written by this turn (if any), and the context report: est. tokens per layer and
what was dropped. The `understood` stage shows prompt and completion tokens.

### D. Owner watching the cost

After S3 ships, the token query (plan 8.4) over the first three weekdays shows p95 prompt
tokens per turn not higher than before, and zero recall re-parses.

## Owner decisions this UAC assumes (the plan's recommendations)

| Q | Recommendation assumed |
|---|---|
| Q1 | Memory ON by default for every contact; the per-contact toggle becomes an opt-out (supersedes D3 "global default off"). |
| Q2 | An episode closes on a topic switch or after a 30-minute gap. |
| Q3 | Episode summaries are deterministic (from the turns' trace), no LLM call, no figures. |
| Q4 | Each parse gets the last 3 episode summaries of the last 30 days and the live episode's last 3 earlier messages. |
| Q5 | The vector recall re-parse is deleted; embeddings keep being written for the n8n search route. |
| Q6 | Facts the dealer states (closed key list) are saved at once as `Said`, hints only, staff can delete. |
| Q7 | Retention: episodes and learned facts 90 days after last seen; stated facts 180 days; staff facts never. |
| Q8 | Token rule: the static prompt may not grow (addendum paid by cuts); user block hard cap 1,800 est. tokens; production p95 not higher than before. |
| Q9 | Out-of-boundary replies: the LLM writes only the acknowledgement; facts and offers come from data. |
| Q10 | Every bot turn not under human takeover sends a visible line. |
| Q11 | Memory card: `memory_default`, `episode_retention_days`, `episode_gap_minutes`; `profile_fields` and `focus_reset_events` removed. |
| Q12 | The staff screen lives inside the existing Chatbot card on the contact page. |
| Q13 | A commercial ask (discount, credit, price exception) is handed to the linked salesperson; everything else to the domain's team. |
| Q14 | "Enterprise Claude Code" (write actions) becomes its own ideation issue; not in this lane. |

## S0 - Schema and write path (AC-MEM001 to AC-MEM012)

- AC-MEM001 [BE][T] Migration adds `conversation_frames.is_test boolean not null default
  false` and the index `(contact_respond_id, is_test, closed_at desc)`; upgrade and downgrade
  both run on a prod copy; revision id <= 32 chars; single alembic head. Evidence: alembic
  run log in the PR; `check-migration-heads` green.
- AC-MEM002 [BE][T] Given a live episode of turns T1 to T3 and T4 whose verdict has
  `topic_reset: true`, when T4 runs, then exactly one frame is written with
  `turn_ids = [T1, T2, T3]`, `close_reason = topic_switch`. Evidence: pytest
  `tests/chatbot/test_memory_episode_boundaries.py`.
- AC-MEM003 [BE][T] (Q2) Given the contact's previous turn finished 31 minutes ago with an
  unclosed live episode, when a new turn arrives, then that episode is closed at intake with
  `close_reason = idle` BEFORE the parser runs, and the new turn starts a new live episode.
  At 29 minutes nothing is closed. Evidence: pytest with a frozen clock, both sides of the
  boundary.
- AC-MEM004 [BE][T] Given a human takeover happened after the last bot turn, when the next bot
  turn runs, the live episode is closed with `close_reason = handover`. Evidence: pytest.
- AC-MEM005 [BE][T] An empty live episode writes nothing; a dry run writes nothing (LESSONS
  #101); an `is_test` turn writes `is_test = true` frames and reads only `is_test` frames, and
  a live turn never reads an `is_test` frame. Evidence: pytest, one test per clause.
- AC-MEM006 [BE][T] The gap close runs inside the per-contact ticket: two turns of one contact
  arriving in the same second produce one close, not two. Evidence: pytest with two threads on
  Postgres.
- AC-MEM007 [BE][T] The trace `memory` event records `episode_written` (frame id, turn count,
  close reason) when this turn wrote one, and the profile before and after as they really
  were. Evidence: pytest on the trace shape.
- AC-MEM008 [FE][T] The turn drawer's Memory panel renders the backend's `memory` shape (one
  shape, the backend's); a vitest feeds it a trace recorded from a real turn (not a hand-made
  fixture) and asserts Focus, Profile, Episodes and "Episode written" render without throwing.
  Evidence: vitest `TurnDetailDrawer.memory.test.tsx`.
- AC-MEM009 [E2E] Sidebar > System Management > Chat History > a turn: the Memory panel shows,
  at 375 px and 1280 px. Evidence: agent-browser run recorded in `evidence/memory/`.
- AC-MEM010 [BE][T] The `understood` stage `facts` carry `prompt_tokens` and
  `completion_tokens` from the provider as well as `tokens`. Evidence: pytest with a stubbed
  provider usage.
- AC-MEM011 [BE][T] Every `ai_assistant_usage_logs` row written for a chatbot parser call
  carries the turn id. Evidence: pytest.
- AC-MEM012 [BE][T] S0 changes no reply text: the whole existing replay corpus
  (`tests/chatbot/replay_turns/**`) stays green with no new divergence entry. Evidence: CI.

## S1 - Episode summaries (AC-MEM020 to AC-MEM029)

- AC-MEM020 [BE][T] (Q3) `episode_digest.digest(turns)` is pure and returns domains,
  entities, asks with outcome, offers, small-talk count, turn count, first and last time,
  close reason. Evidence: pytest golden over 10 recorded, anonymised episodes from the 25 Sep
  dump.
- AC-MEM021 [BE][T] (Q3) The summary line is at most 240 chars, names each ask's domain,
  entities and outcome, and contains **no figure** (no quantity, price, ETA date or amount
  from any answer). Evidence: pytest over the 10 goldens plus a property test that no digit
  run from a turn's figures appears in the summary.
- AC-MEM022 [BE][T] Outcome is one of `answered | not_found | asked_back | escalated |
  declined | denied | small_talk`, read from branch and offer data, never from reply text.
  Evidence: pytest, one case per outcome.
- AC-MEM023 [BE][T] The frame row carries `summary`, `entities`, `result_refs` (document
  numbers returned), all `turn_ids`, `tools_used`, `domain`, `intent`,
  `last_user_message` (<= 200 chars). No placeholder "Closed the ... topic." is written again.
  Evidence: pytest; grep guard test for the old string in `app/`.
- AC-MEM024 [BE][T] `scripts/backfill_chatbot_episodes.py` over the retention window writes
  one frame per episode cut by the same rules, deletes the placeholder frames, and a second
  run changes nothing (same count, same ids). Evidence: pytest on a seeded history; run log on
  a prod copy in the PR.
- AC-MEM025 [BE][T] (Q7) The nightly sweep deletes a frame closed 91 days ago and keeps one
  closed 89 days ago (with `episode_retention_days = 90`), and closes a live episode idle past
  the gap. Evidence: pytest with a frozen clock.
- AC-MEM026 [BE][T] (Q11) `system_settings.chatbot_memory` holds `memory_default` (default
  true), `episode_retention_days` (default 90, 7 to 365), `episode_gap_minutes` (default 30,
  5 to 720); `profile_fields` and `focus_reset_events` are gone from model, schema, both dict
  builders and the card. Evidence: pytest on GET and PUT; 422 out of range.
- AC-MEM027 [BE][T] The engine reads `episode_gap_minutes` and `episode_retention_days` from
  settings (changing the value changes behaviour on the next turn). Evidence: pytest.
- AC-MEM028 [FE][T] The Memory card shows the three controls, saves and reloads each.
  Evidence: vitest on the hook; agent-browser Sidebar > User Management > Settings > Chatbot at
  375 and 1280 px.
- AC-MEM029 [BE][T] A new contact's memory toggle starts at `memory_default`. Evidence: pytest.

## S2 - Profile facts and staff screen (AC-MEM030 to AC-MEM049)

- AC-MEM030 [BE][T] The fact vocabulary is exactly the plan's table 4.1; a write with an
  unknown key or a disallowed source for that key is rejected (422 on the route, ignored with
  a trace line in the engine). Evidence: pytest parametrised over key x source.
- AC-MEM031 [BE][T] `derive_crm` at each episode close writes `customer` (primary linked
  customer first), `segment` (from `market_segment_code`) and `salesperson` (from the
  customer's sales agent), replacing all previous `crm` facts. Evidence: pytest with a seeded
  customer chain (CI DB has no data: seed it).
- AC-MEM032 [BE][T] `tally` writes `usual_products`, `usual_brands`, `usual_sites` from
  entities present in 2 or more closed episodes in the last 90 days, top 3 by count then
  recency, with `seen_count`, `first_seen`, `last_seen`, `expires_at = last_seen + 90 days`.
  An entity seen in one episode only is not a fact. Evidence: pytest.
- AC-MEM033 [BE][T] (Q6) A verdict with `profile_statement {key, value}` writes a `stated`
  fact on that turn, validated: brands against the brand master, sites against warehouse
  names, role against `purchaser | owner | sales | site_supervisor | other`, `project` cut to
  60 chars with newlines stripped, language in `en | ms | zh`. An invalid value writes nothing
  and records a trace line. Evidence: pytest per key, valid and invalid.
- AC-MEM034 [BE][T] Precedence staff > stated > crm > tallied for the same key; a staff
  delete leaves a tombstone and the next tally does not re-learn the value. Evidence: pytest.
- AC-MEM035 [BE][T] (Q7) Expired `tallied` and `stated` facts are dropped by the nightly sweep
  and are never rendered even before the sweep runs. Evidence: pytest with a frozen clock.
- AC-MEM036 [BE][T] **Facts never grant.** Given "I'm the owner of Iborn" (a `stated`
  `role: owner`), the contact's `access_levels`, company scope, linked customers and reveal
  results are byte-identical before and after, and a following "AR for Iborn" is answered
  exactly as it was before the statement. Evidence: pytest comparing the snapshots.
- AC-MEM037 [BE][T] A tier pick in chat writes `tier` to the profile (source stated), and the
  next turn does not ask the tier. Evidence: pytest across two turns.
- AC-MEM038 [BE][T] `GET /api/v1/user-management/contacts/{id}/chatbot/memory` returns facts
  (with source, last seen, expires), the last 10 episodes (date, domains, summary, turn count,
  close reason, first turn id) and the top 5 open orders of the linked customer; 403 without
  `user_management.contacts.view`. Evidence: pytest happy + 403.
- AC-MEM039 [BE][T] `PUT .../chatbot/facts/{key}` sets a staff fact (confirming a learned
  one turns it into staff, no expiry); `DELETE` of the same is a hard delete through the
  deferred-action path; both 403 without `user_management.contacts.edit`; 422 on an unknown
  key or a value over its limit. Evidence: pytest per route: happy, 403, 422.
- AC-MEM040 [BE][T] The existing whole-profile `PUT .../contacts/{id}/chatbot` no longer
  writes or clears `facts`; a staff fact save and a concurrent turn's tally both survive.
  Evidence: pytest with two sessions on Postgres.
- AC-MEM041 [BE][T] `facts` reaches the FE through both dict builders
  (`contact_to_response_dict` and the chatbot GET). Evidence: pytest asserting the field in
  both responses (a `response_model` would drop it silently).
- AC-MEM042 [BE][T] `always_full_report` is removed from the FE; an empty profile renders no
  `Profile` line at all. Evidence: vitest grep guard; pytest on the assembled block.
- AC-MEM043 [FE][T] (Q12) The Chatbot card shows "What the bot knows" as a DataGrid (fixed
  layout, resizable, explicit sizes, long values truncated with a title) with a source badge
  (`Badge`), last seen and expires; CRM rows are read-only and link to the customer; empty
  state "Nothing learned yet" with the Add action. Evidence: vitest on the hook and the grid.
- AC-MEM044 [FE][T] Add opens a modal with the key as `SearchableSelect` (clearable where
  optional) and the value; edit swaps the value in place (view and edit, same layout);
  errors via `extractApiError` and a toast. Evidence: vitest.
- AC-MEM045 [FE] Delete turns the button into a 10 s countdown with Cancel, no dialog, and the
  server commits when it lapses with the tab closed. Evidence: agent-browser run.
- AC-MEM046 [FE] "Recent conversations" lists the episodes (date, topic, summary, turns,
  close reason); a row opens Chat History at that episode's first turn (`rowHref`); empty
  state links to Chat History. Evidence: agent-browser run.
- AC-MEM047 [FE] "Open orders" lists the live top 5 with document numbers (no UUIDs), empty
  state when none. Evidence: agent-browser run.
- AC-MEM048 [E2E] Sidebar > User Management > Contacts > a contact > Chatbot card: view the
  three sections, add a note, confirm a learned fact, delete a fact, at 375 px and 1280 px.
  Evidence: agent-browser run recorded in `evidence/memory/`.
- AC-MEM049 [BE][T] The toggle "Use conversation memory" off for a contact: no memory layer
  is assembled for that contact (the user block is today's: previous response, current
  subject, open question, message; no earlier messages, summaries or facts), no fact is
  learned, episodes are still written for staff. Evidence: pytest.

## S3 - Prompt assembly under budget (AC-MEM060 to AC-MEM072)

- AC-MEM060 [BE][T] (Q8) `turn/context.assemble` is pure, renders the layers in the plan's
  order (profile, recent conversations, earlier in this conversation, previous response,
  current subject, open question, current message), and never returns more than 1,800 est.
  tokens; on a worst-case fixture (every layer at 3x its cap) it drops in the plan's order and
  keeps the current message and the open question whole. Evidence: pytest
  `test_context_assemble.py`, one test per layer cap plus the total.
- AC-MEM061 [BE][T] (Q8) `tests/chatbot/test_parser_prompt_budget.py` renders the production
  parser prompt (registry fallback plus the policy blocks seed) and fails above 22,100 est.
  tokens. Evidence: the test, and a kill test that appends 1,000 tokens and sees it red.
- AC-MEM062 [BE][T] Every parse records a `context` trace event with est. tokens per layer,
  the total, and what was dropped (layer, count). Evidence: pytest on the trace.
- AC-MEM063 [BE][T] (Q5) The recall re-parse is gone: no turn makes two parser calls; the
  `recall` trace kind is no longer written; `memory.recall` is deleted; the
  `/external/memory/frames/search` route still answers. Evidence: pytest; grep guard.
- AC-MEM064 [BE] (Q8) Production gate: over the first 3 weekdays after deploy, p95 of
  `prompt_tokens` per live turn is not higher than over the 3 weekdays before, and recall
  turns = 0 (plan 8.4 query). Evidence: the query output pasted in the PR or its follow-up.
- AC-MEM065 [BE][T] (Q4) A parse carries at most the last 3 closed episodes of the last 30
  days (printed oldest first) and at most the live episode's last 3 earlier user messages,
  each cut to 200 chars; `Previous response` is cut to 600 chars. Evidence: pytest.
- AC-MEM066 [BE][T] The memory addendum is at most 400 est. tokens and the prompt carries the
  cuts of plan 6.4 (the `previous_conversation_state` description, the n8n JS literal, the
  #1275 section when 8.2 stays green); `parser_memory_phrases.json` cues all appear in the
  addendum. Evidence: reachability pytest in the style of `test_parser_growth_r1_reachability`.
- AC-MEM067 [BE][T] Every case under `tests/chatbot/replay_turns/memory/` marked
  `needs_memory: true` passes, and FAILS when replayed with memory ablated (L3 earlier
  messages, L4, L5 and the frame and fact reads emptied). A case that passes under ablation
  fails the meta-test. Evidence: CI.
- AC-MEM068 [BE][T] Live parser evaluation (plan 8.2): at least 27 of 30 memory cases right
  with memory, at least 24 of 30 wrong with memory stripped; the existing corpus agrees at
  least 97% with the pre-S3 prompt and every disagreement is listed and ruled on in the PR.
  Evidence: `scripts/chatbot_parser_parity.py` output in the PR.
- AC-MEM069 [BE][T] The parser schema accepts `message_type = history_question` and a
  nullable `profile_statement {key, value}` with the five allowed keys; any other key is
  dropped by APPLY with a trace line. Evidence: pytest on the schema and APPLY.
- AC-MEM070 [BE][T] Memory never overrides the current message: with `usual_products` =
  [SRTWB1455] and the message "stock M483-BL", the verdict's product is M483-BL and APPLY
  keeps only M483-BL in focus. Evidence: replay case plus a live 8.2 case.
- AC-MEM071 [BE][T] `CURRENT DATE: {{current_date}}` is the last section of the system
  prompt, so the prompt's first 20,000 chars are byte-identical on two different dates.
  Evidence: pytest rendering two dates.
- AC-MEM072 [BE] Latency (plan 6.6): CRM turn p50 +0.1 s at most and p95 not higher over the
  same 3-weekday windows; `received` p95 +40 ms at most; `remembered` p95 <= 150 ms.
  Evidence: the #1275 A3 stage query output in the PR or its follow-up.

## S4 - Out-of-boundary replies (AC-MEM080 to AC-MEM095)

- AC-MEM080 [BE][T] (Q9) The reply to a `low_signal`, `history`, `out_of_scope` or
  `not_supported` turn is `ack + optional memory_line + offer`; only `ack` comes from the
  clarifier LLM, which returns `{"ack": "..."}` of at most 25 words and is given the profile
  slice and the episode summaries under 400 est. tokens. Evidence: pytest on the lane with a
  stubbed clarifier.
- AC-MEM081 [BE][T] (Q9) Guard: an `ack` holding a digit, a product-code-shaped token, a price
  or a date not present in its own input is replaced by the canned acknowledgement for the
  language. Evidence: pytest, one case per class.
- AC-MEM082 [BE][T] `history_question` routes to the history composer, which lists up to 5
  recent episodes (date, asks) from `conversation_frames` only, with no figure, and ends
  with a numbered re-run offer; "2" on the next turn re-runs episode 2's ask with fresh data.
  Evidence: replay cases (plan 7.3 example 3) plus a two-turn pytest.
- AC-MEM083 [BE][T] A follow-up resolved from `Recent conversations` opens its answer with one
  line naming what was carried ("For the outstanding DOs of Chin Chun Trading from Tuesday:").
  Evidence: replay case (example 2).
- AC-MEM084 [BE][T] (Q10) An `out_of_scope` turn always sends the dealer a visible line with
  the handover offer or the handover confirmation; an `escalation_declined` turn sends the
  existing `offer_declined` copy. Evidence: pytest asserting a `send_message` action on each.
- AC-MEM085 [BE][T] (Q10) Every bot turn not under human takeover ends with exactly one
  `send_message` action. Evidence: pytest over every branch kind; the #1275 no-reply query
  after deploy shows 0 turns without a send outside takeover.
- AC-MEM086 [BE][T] The clarifier error path sends the existing "Sorry, I ran into a
  problem..." copy, never exception text; `CLARIFIER_ERROR_PREFIX` is deleted. Evidence:
  pytest raising inside the clarifier; grep guard.
- AC-MEM087 [BE][T] (Q13) A commercial ask (discount, credit, price exception) offers the
  linked salesperson by name through the existing member offer; any other unfulfillable ask
  offers the domain's team; with no salesperson fact, the team. Evidence: pytest, three cases.
- AC-MEM088 [BE][T] A handover's routed message carries the live episode's summary line so
  the human sees what was being discussed. Evidence: pytest on the escalation comment.
- AC-MEM089 [BE][T] `memory_line` and `offer` come from `chatbot_reply_copy` templates in en,
  ms and zh, picked by profile `language`, else the language the clarifier reports for the
  message, else en. Evidence: pytest per language.
- AC-MEM090 [BE][T] The ten exchanges of plan 7.3 exist as replay cases under
  `replay_turns/memory/`; examples 1, 2, 3, 4, 5, 8 and 10 are `needs_memory: true` (red under
  ablation); 7 and 9 assert the fact on the profile after the turn; 6 asserts the live open
  orders read and the two-option offer. Evidence: CI (AC-MEM067 meta-test).
- AC-MEM091 [BE][T] Small talk with memory ON and no episodes yet (a first-time contact)
  still gets a human greeting and a concrete offer (the domain menu), never an empty
  `memory_line` placeholder. Evidence: replay case.
- AC-MEM092 [BE][T] A dealer's open orders in a reply (example 6) are fetched live through the
  existing order tool at reply time, never from a stored fact or summary. Evidence: pytest
  asserting the tool call.
- AC-MEM093 [BE][T] The out-of-boundary lanes persist session state and write the memory trace
  like every other lane (today `low_signal` persists nothing). Evidence: pytest.
- AC-MEM094 [BE] Console check `tests/chatbot/console_cases/2026-09-memory.yaml` green against
  the deployed stack (topic-switch carry case plus examples 1, 3, 4, 10). Evidence:
  `scripts/chatbot_console_check.py` output in the PR.
- AC-MEM095 [E2E] Owner hand pass: the ten exchanges on the WhatsApp test number; the owner's
  verdict recorded verbatim in the PR. Evidence: the PR comment.
