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
  is assembled for that contact (L3 earlier messages and the previous response stay, as
  today), no fact is learned, episodes are still written for staff. Evidence: pytest.
