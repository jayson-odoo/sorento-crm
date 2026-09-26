# PLAN - Chatbot memory: contact profile, episodes and turn context under a token budget

Status: DRAFT 26 Sep 2026, awaiting the owner's answers to the grill questions at the end.
Track: full (migration, parser prompt change, staff screen, expected diff well over 300 lines).
Issue #1282. UAC: `chatbot-memory-acceptance-criteria.md` (AC-MEM001 to AC-MEM099), written
to the recommendations in "Grill questions for the owner"; an answer that differs rewrites the
matching ACs before any code.

Core or module: CORE. This is the existing chatbot's memory shelf, not a new installable
capability. No new module key, no new Postgres schema; the rows stay where they are today
(`public.conversation_frames`, `public.respond_contacts.chatbot_profile`, `chatbot.turns`).

## Contents

1. The owner's words (binding)
2. What exists today (measured 26 Sep 2026 at origin/main 51d30ccc5)
3. What this plan changes, in one paragraph
4. Layer 1: contact profile
5. Layer 2: episodes
6. Layer 3: turn context assembly and the token budget
7. Out-of-boundary replies (with ten example exchanges)
8. How each layer is evaluated
9. Slices S0 to S4
10. Simplest thing, not built (and the trigger that would build it)
11. Risks
12. Relation to "an enterprise version of Claude Code"
13. Grill questions for the owner

## 1. The owner's words (binding)

Issue #1282, 26 Sep 2026 about 13:50Z, verbatim:

> "I believe our chatbot plan includes things like episodes and even user profile. Because I
> think now we are using focus only to survive multiple turns. But I think we have episode as
> well and profile so that, like Claude, you got a user profile that is a memory that stores
> everything about that user, and also episode, for some context management so that it feels
> more human and conversational when you are talking with the chatbot. Because now our chatbot
> fails constantly in a human conversation: when things are asked out of the boundary the
> chatbot struggles to understand because it's a one-dimensional reply chatbot. So I think we
> need to look into that and I'm also interested to discuss how to implement this so that we
> can be an enterprise version of Claude Code."

And the issue's constraint: "Token budget matters: the parser prompt is already ~22.8k tokens
against a 200k tokens/min org limit (#1275)."

Read as requirements:

- R1. A per-contact profile that remembers the person and their business.
- R2. Episodes: context management so the conversation survives beyond the one focus.
- R3. Out-of-boundary messages get a human reply, not a one-dimensional one.
- R4. No token growth that eats the #1275 headroom.
- R5. The "enterprise Claude Code" direction is a discussion, not a deliverable of this plan
  (section 12 maps it; grill question 14 asks where it goes).

## 2. What exists today (measured 26 Sep 2026 at origin/main 51d30ccc5)

The owner is right that the plans promised profile and episodes. `PLAN-chatbot-turn-rearch.md`
(approved 15 Sep) names three memory shelves (focus, profile, episodes; plan lines 74 to 79),
and its UAC carries them as D3, AC-1505, AC-1513 to AC-1515 and AC-1546 to AC-1549.
`PLAN-chatbot-growth-r1.md` D6 says the same: "Memory is the long-term shape (focus, episodes,
profile)". **They were built, and they do almost nothing.** So most of this is a repair plan
(PRINCIPLES: "a feature that ships already and is merely broken needs a repair plan"), plus
two additions the old plan never had: a token budget, and out-of-boundary replies.

### 2.1 What the parser sees each turn

The parser gets one system prompt (registry key `chatbot_semantic_parser`) and one user block
from `build_user_block` (`app/services/chatbot/head/parser.py:468-527`):

```
Previous response: <the bot's last reply, one only>
Current user message: <text, plus "reply to: <quoted>" when the dealer quoted a message>
Current subject: domain X; customer Y; ...        (focus, rendered as one line)
Pending: the assistant is waiting for a <kind> reply.
Open question options: 1 ...; 2 ...
Profile:                                          (tier / language / default ledgers)
Episodes:                                         (only after a recall re-parse)
```

- No earlier user message is ever sent. The only "history" is the bot's single last reply
  (`turn_runtime.py:211-253`).
- The system prompt still describes a `previous_conversation_state` input
  (`chatbot_parser_prompt.py:133`, first lines), which is never sent. That is dead text.
- The prompt has **no** instructions for the `Profile:` or `Episodes:` blocks (0 mentions in
  `chatbot_parser_prompt.py`). The model gets the blocks but was never told what they mean.

### 2.2 Focus (the one shelf that works)

`Focus` (`turn/state.py:86-111`): products, customers, warehouse, brands, tier, domains,
document, status, sales_channel, date_window, set_page, extra. Stored in
`respond_contacts.session_vars.focus`. Written by APPLY only.

- No age, no decay: a focus from last Tuesday is still "Current subject" today.
- `topic_reset` clears everything except `RESET_KEEPS = {"tier", "brands"}` (`apply.py:55`).
- Only the open question has a clock: an escalation offer lives 3 turns (`OFFER_TTL = 3`,
  `pending.py:154`).

### 2.3 Profile (built, read by one rule, written by one screen)

| piece | where | state |
|---|---|---|
| `chatbot_profile` JSONB, `chatbot_recall_enabled` (default false) | `models/access.py:265-266`, migration `chatbot_rearch_s0.py` | shipped |
| `Profile` dataclass: tier, language, grants (always None), default_ledgers, stock_allowed, notify_salesman, packing_list_allowed | `turn/state.py:114-133`, `load_profile` `turn_runtime.py:256-315` | shipped |
| `Profile:` block on every parse | `turn/memory.py:206-215` | shipped; sends a bare `Profile:` line when empty |
| reader | `narrow.py:452,467` (a known tier skips the tier question) | the only reader |
| writer | `PUT /user-management/contacts/{id}/chatbot` (`contacts.py:240-275`), replaces the whole JSONB | the only writer; a tier pick in chat never saves (plan line 78 promised it would) |
| `always_full_report` | FE only | dead field |
| Contact card | `ContactChatbotSection.tsx`: stock, recall, notify salesman, packing list, language, tier | shipped |

The profile holds settings, not knowledge. Nothing learned from a conversation ever lands in it.

### 2.4 Episodes (built, content is a placeholder)

- Store: `conversation_frames` (migration 201 plus rearch columns `contact_respond_id`,
  `entities`, `turn_ids`, `opened_at`). It also has unused `result_refs`, `last_user_message`,
  `last_assistant_summary`, `pending_request`. Only a single-column index on
  `contact_respond_id`.
- Writer: `_write_episode` (`engine.py:3326-3379`), only on `topic_reset`, never on a gap or a
  conversation close, never on a dry run, and not at all when the old focus had no domain. It
  writes:

  ```python
  summary=f"Closed the {domain} topic.", close_reason="topic_switch",
  intent=None, turn_ids=[turn_id], tools_used=[]
  ```

  `turn_ids` is the turn that caused the reset, not the turns of the closed topic.
- Reader: recall (`engine.py:1487-1520`, `turn/memory.py:137-193`), only when the parser says
  `backward_reference` AND the contact's toggle is on (default off). It embeds
  `domain_hint + intent_hint`, takes the top 3 frames, and **runs the whole parser again** with
  `Episodes:\n- (stock) Closed the stock topic.`. That second call costs another full prompt
  (about 22.8k tokens) to hand the model a sentence with no entities in it. The rearch journey
  step 8 ("same report as yesterday") cannot work on this content.
- The re-parse overwrites `parser_usage` (`engine.py:1508`), so the first call's tokens are
  never logged.
- `/api/v1/external/memory/frames/*` (`api/v1/external/memory.py:52-146`) exists for n8n and
  filters on the old `contact_id`; the engine does not use it.

### 2.5 Settings and screens

- Settings > Chatbot > Memory card (`MemorySettingsCard.tsx`) saves `recall_default`,
  `episode_retention_days`, `profile_fields`, `focus_reset_events` into
  `system_settings.chatbot_memory` (`models/user.py:634-643`). **Nothing in the engine reads
  any of the four.**
- The chat-history turn drawer has a Memory panel (`TurnDetailDrawer.tsx:375-380`) that types
  `memory.focus` as an array of slots and calls `.map`. The backend sends
  `{before, after, writer}` objects (`trace_detail.py:273-283`) and none of the
  `recall_hit / reason / last_frame_summary / frame_count` keys the FE expects. Inferred from
  the code (LESSONS-LEARNT #102 shape: a port's test never crossed the seam); a browser pass in
  S0 confirms it before the fix.
- The trace `memory` event records profile before == after always, and records the recalled
  frame ids as "episodes", never the frame written this turn.

### 2.6 The per-contact ticket and the trace

- The per-contact ticket is a Redis ordering ticket, not a table (`dispatch.py:54-57`, keys
  `chatbot:seq|done|running:{contact}`, TTL 3600 s). Taken at `engine.py:859` in S7 mode and
  not on dry runs, released in a `finally`. It guarantees one turn per contact at a time, which
  is what lets an episode be closed at intake without a lock race. #1275 measured its queue
  wait at p99 0.05 s.
- `chatbot.turns.trace` holds per-stage `ms` (latency per stage exists), a `prompt_text` event
  (the user block only, not the system prompt), `apply`, `memory`, `recall`. The `understood`
  stage stores only `total_tokens`; `prompt_tokens` goes to `ai_assistant_usage_logs` with no
  turn id.

### 2.7 Out-of-boundary today

`_lane` (`turn/apply.py:1180-1258`) and `route.py:17-35`:

| parser says | lane | what the dealer gets |
|---|---|---|
| casual / unknown / confirmation, no domain | `low_signal` | the clarifier LLM (`lanes/casual.py`, gpt-4.1-mini) with `session_vars` HIDDEN (`casual.py:187`); on error it sends `"There is some error encountered by the AI: " + str(exc)` (`casual.py:57`), i.e. a raw exception to a customer |
| domain not supported | `not_supported` | canned "Sorry, we don't support direct goods receive & SPO at the moment..." |
| clarification | `clarify_menu` | canned menu "Are you asking about any of these?" |
| escalation / request_for_help | `out_of_scope` | an internal note; #1275 found 28 `out_of_scope` and 16 `escalation_declined` turns that sent the dealer **nothing** |

That is the "one-dimensional reply chatbot" the owner describes: the lane that handles
anything outside a domain is the one lane that is told nothing about who the person is or
what was said before.

### 2.8 Token and latency facts (from the #1275 scout report on the 25 Sep prod dump)

| fact | value |
|---|---|
| parser prompt per call | 22.8k tokens since 22 Sep (13.4k on 21 Sep, 9.6k on 9 Sep) |
| of which static system text | about 21.2k body + 0.9k policy blocks (chars / 4) |
| requested per call | about 24.8k (prompt + `max_tokens` 2048) |
| org limit | 200k tokens per minute on gpt-5.4-mini, shared with dev |
| calls per minute that fit | 8 |
| peak minute today / stacked +50 contacts | 6 turns (149k) / 9 turns (223k, over) |
| parser p50 | 2.6 s; doubling the prompt added about 0.25 s |
| turns per contact per day | mean 7.4, p50 4, p95 30 |
| prompt caching | none explicit; `{{current_date}}` sits at char 595, so any automatic prefix cache breaks daily |
| a recall turn today | two full parser calls, about 49.6k requested |

The consequence for this plan: **memory must not add net tokens to the parser call.** Every
token it adds is paid for by a cut in the same slice (section 6).

## 3. What this plan changes, in one paragraph

Keep the three shelves and their single writers; fill them with something worth reading, and
feed them to the parser in a fixed, capped shape. Episodes get real boundaries (topic change
**or** a 30 minute gap, closed lazily at the next turn's intake inside the per-contact ticket)
and a deterministic written summary built from the turns' own trace (domains, entities,
answers, offers, outcome): no extra LLM call, backfillable over the 4,414 live turns already
in `chatbot.turns`. The profile gains a `facts` list inside the existing `chatbot_profile`
JSONB (no new table): facts derived from CRM links, facts tallied from closed episodes, facts
the dealer states, facts staff enter; each with source, last seen and expiry; staff see and
edit them on the Contact page. Every parse gets a capped context (profile slice, last three
episode summaries, the live episode's earlier messages, focus, open question, current
message) assembled by one pure function under a per-layer token budget, and the recall
re-parse is deleted, which pays for the added lines several times over. The low-signal lane
(small talk, "what did I ask you", "can you give me a discount") gets the same memory slice
and a reply shape (acknowledge, use what memory knows, offer the concrete thing the CRM can
do, or hand over), and never sends a raw error or nothing at all.

## 4. Layer 1: contact profile

### 4.1 What it holds

One closed vocabulary. A key not in this table is rejected by the writer (one validation
function, `turn/profile_facts.py`). Staff can add a free-text note; nothing else is free-form.

| key | example value | sources allowed | fed to the parser | expiry |
|---|---|---|---|---|
| `customer` | "Chin Chun Trading (CC001)" | crm | yes | live (re-derived at each episode close) |
| `segment` | "dealer" / "project" / "end user" | crm, staff | yes | live |
| `salesperson` | "Aina" | crm | no (S4 composer only) | live |
| `language` | "ms" | staff, stated | yes | none (staff) / 180 days (stated) |
| `role` | "purchaser" | stated, staff | yes | 180 days / none |
| `usual_products` | ["SRTWB1455", "M486-75-BL"] | tallied, staff | yes | 90 days after last seen |
| `usual_brands` | ["Sorento"] | tallied, stated, staff | yes | 90 days after last seen |
| `usual_sites` | ["Kuching"] | tallied, stated, staff | yes | 90 days after last seen |
| `project` | "Aurora Residences block B" | stated, staff | yes | 180 days / none |
| `note` | free text, max 200 chars | staff | yes | none |

Plus the existing settings keys stay where they are (`tier`, `default_ledgers`, the toggles):
they are settings, not facts, and keep their current writer.

**Open orders are not a profile fact.** They change every hour, the business lane already
fetches them fresh, and putting a count in the prompt would be stale by the next turn. The
staff screen shows them live (from the linked customer), and the S4 composer fetches them
when a reply needs them (example 6 in section 7).

### 4.2 Shape (inside the existing JSONB, no migration for the shape)

```json
"chatbot_profile": {
  "tier": "dealer", "language": "ms", "default_ledgers": [],          // existing settings
  "facts": [
    {"key": "usual_products", "value": ["SRTWB1455", "M486-75-BL"],
     "source": "tallied", "source_ref": "<frame id>", "first_seen": "2026-09-02",
     "last_seen": "2026-09-25", "seen_count": 4, "expires_at": "2026-12-24",
     "set_by": null},
    {"key": "role", "value": "purchaser", "source": "stated",
     "source_ref": "<turn id>", "first_seen": "2026-09-26", "last_seen": "2026-09-26",
     "seen_count": 1, "expires_at": "2027-03-25", "set_by": null},
    {"key": "note", "value": "Prefers PDF quotes", "source": "staff",
     "source_ref": null, "set_by": "<users.id>", "expires_at": null}
  ]
}
```

Why no table: one contact holds at most about 12 facts, nothing queries facts across contacts,
and the row is already locked `FOR UPDATE` by the tail. Trigger for a table (written down per
PRINCIPLES): the first feature that must query facts across contacts (for example "every
contact whose usual brand is X" for a campaign).

### 4.3 Writers (each source has exactly one)

| source | writer | when |
|---|---|---|
| `crm` | `profile_facts.derive_crm(contact)` from `respond_contact_customers` (primary first), `customers.market_segment_code`, `customers.sales_agent_id` | at each episode close, in the same transaction; replaces all `crm` facts |
| `tallied` | `profile_facts.tally(contact)`: a product, brand or warehouse present in the entities of 2 or more closed episodes in the last 90 days; top 3 by count then recency | at each episode close |
| `stated` | the parser's new optional `profile_statement` output (section 6.5), applied by APPLY into the tail's write | on the turn the dealer says it |
| `staff` | `PUT /user-management/contacts/{id}/chatbot/facts/{key}` and `DELETE` of the same; the existing whole-profile PUT stops touching `facts` | on the Contact page |

Precedence when two sources hold the same key: `staff` > `stated` > `crm` > `tallied`. A staff
delete of a learned fact records a tombstone (`{"key": ..., "source": "staff", "value": null}`)
so the tally does not re-learn it the next day.

**Hard rule: facts are hints, never grants.** No fact changes `access_levels`, company scope,
the linked customers or any reveal gate. A dealer who says "I'm the owner of Iborn" gets
`role: owner` as a hint and exactly the same data access as before. Test AC-MEM036.

### 4.4 The fix list carried from section 2.3

- A tier pick in chat writes `tier` to the profile (plan line 78 promised this). Via the tail,
  source `stated`.
- `always_full_report` is removed from the FE (no reader).
- An empty profile renders no `Profile:` line at all.

### 4.5 Staff screen

Contact detail page, the existing Chatbot card (`ContactChatbotSection.tsx`) gains two
sections under the toggles, same layout on view and edit:

- **What the bot knows** (a DataGrid): key label, value, source badge (`CRM`, `Learned`,
  `Said`, `Staff`), last seen, expires. CRM rows are read-only and link to the customer. Staff
  can Add (modal: key from a `SearchableSelect` of the vocabulary, value), edit a row in place,
  and Delete (deferred action, 10 s hard delete, no confirm dialog; D7). Confirming a `Learned`
  or `Said` row turns it into `Staff` (no expiry). Empty state: "Nothing learned yet" plus the
  Add action.
- **Recent conversations** (read-only DataGrid): episode date, topic (domains), summary line,
  turn count, close reason; the row opens that turn range in Chat History (`rowHref`).
  Empty state with a link to Chat History.
- **Open orders** (read-only, live from the linked customer, top 5): shown here because staff
  asked "what does the bot know about this person" and orders are part of that answer; not a
  fact, not stored.

Permissions: view needs the existing `user_management.contacts.view`; add, edit and delete
need the existing `user_management.contacts.edit`. No new permission, so no grant sweep.
Both dict builders (`contact_to_response_dict` and the chatbot GET) list `facts` (DoD 4).

## 5. Layer 2: episodes

### 5.1 What an episode is

A contiguous run of one contact's turns about one thing. It is **closed** by the first of:

| trigger | close_reason | detected where |
|---|---|---|
| the parser says `topic_reset` (today's only trigger) | `topic_switch` | APPLY, written by the tail (unchanged seam) |
| a gap: this turn arrives more than `episode_gap_minutes` (default 30) after the contact's previous turn | `idle` | intake, before the parser runs, inside the per-contact ticket |
| the nightly memory sweep finds a live episode idle past the gap | `idle` | the existing scheduler (section 5.5) |
| staff take over the conversation (human intervention flag) | `handover` | intake of the next bot turn |

There is **no open row**. The live episode is simply "this contact's turns since the last
closed frame's `closed_at`" (one indexed read of `chatbot.turns`, at most 4 rows needed). An
episode is written once, already closed, as `write_episode` does today. This keeps the one
writer (the tail, or intake for a gap close) and needs no "open then patch" state.

Why 30 minutes: turns per contact per day are p50 4, p95 30 (#1275), and a WhatsApp dealer's
burst is minutes long. Grill question 2 lets the owner pick another number; it is one value
in the existing `system_settings.chatbot_memory` JSON (the Memory card already has the field
slot; section 5.6).

`is_test` turns (console) write frames flagged `is_test = true` and read only `is_test`
frames, so console conversations never leak into a real dealer's memory and vice versa. Dry
runs keep writing nothing (LESSONS-LEARNT #101: a dry run previews the decision, it does not
persist it).

### 5.2 The written summary (deterministic, no LLM call)

Built by one pure function, `turn/episode_digest.py::digest(turns) -> Digest`, from what the
turns already recorded: each turn's `branch_kind`, `focus` after, the composer's section data
(domain, entities, hit or miss), the offer and its answer, the escalation team. Output:

```
Digest = {
  domains: ["stock", "incoming"],
  entities: {"product": ["SRTWB1455"], "customer": ["CC001 Chin Chun Trading"], ...},
  asks: [{"domain": "stock", "entities": ["SRTWB1455"], "outcome": "answered"},
         {"domain": "incoming", "entities": ["M486-75-BL"], "outcome": "not_found"}],
  offers: [{"team": "Stock", "answer": "declined"}],
  small_talk_turns: 1,
  turn_count: 5, first_at, last_at, close_reason
}
summary (<= 240 chars) =
  "Thu 25 Sep, 5 turns: stock SRTWB1455 (answered); incoming M486-75-BL (not found);
   offered Stock team, declined."
```

Rules:

- **No figures in a summary.** A stock count, a price or an ETA is stale by the next day; the
  summary says what was asked and how it ended, never the number. A follow-up re-fetches.
- Outcome is one of `answered | not_found | asked_back | escalated | declined | denied |
  small_talk`, read from the turn's branch and offer, never from reply text.
- Written into the existing columns: `summary`, `entities` (the digest's entities),
  `result_refs` (document numbers the turns returned, e.g. SO numbers, for the history
  answer), `turn_ids` (every turn of the episode, fixing today's one-id bug), `tools_used`,
  `domain` (first domain), `intent`, `last_user_message` (200 chars).
- It is a function of recorded data, so it is replayable in CI and backfillable over history.

Why not an LLM summary: it would be a second model call per episode on the same shared 200k
TPM org, it cannot be replayed key-free, and it can invent a fact. The deterministic line
carries everything the parser and the history answer need (what, which entities, outcome).
What it loses is the colour of small talk ("my son is sick today"). Trigger to add an LLM
sentence (written down per PRINCIPLES): the S4 history-question replay cases or the owner's
hand pass show a question the digest cannot answer. Grill question 3.

### 5.3 Backfill (DoD 2)

`scripts/backfill_chatbot_episodes.py` (idempotent, run once at deploy, re-runnable): for each
contact, walk live `chatbot.turns` of the last `episode_retention_days` (default 90) in order,
cut episodes by the same two triggers (recorded `topic_reset` in the `apply` event, and the
gap), write one frame per episode with its digest, and delete the placeholder frames whose
summary matches `Closed the % topic.`. Key: `(contact_respond_id, first turn id)`, so a second
run changes nothing. About 4.4k turns from 74 contacts today: seconds, not minutes. After it
runs, every dealer already has memory on day one.

### 5.4 What the parser gets from episodes

Two blocks, both inside the budget (section 6):

```
Earlier in this conversation (oldest first):
- 10:02 you: stock SRTWB1455
- 10:03 you: and in kuching?
Recent conversations:
- Thu 25 Sep: stock SRTWB1455 (answered); incoming M486-75-BL (not found); offered Stock team, declined.
- Tue 23 Sep: outstanding DO for CC001 Chin Chun Trading (answered).
```

- "Earlier in this conversation": the live episode's user messages before the current one,
  newest 3, each cut to 200 chars. The existing `Previous response:` line stays and is capped
  at 600 chars. This is the "live episode instead of raw history" the owner asked for: the
  parser has never seen a single earlier user message until now.
- "Recent conversations": the last 3 closed episodes of the last 30 days, newest first in the
  query, printed oldest first.
- Recall is replaced by this. The vector recall and its second parse (`engine.py:1487-1520`)
  are deleted in S3: every parse already carries the last three summaries, and a reference
  beyond three episodes is a history question the S4 composer answers from the table. The
  embedding enqueue stays (it exists, costs nothing on the turn, and
  `/external/memory/frames/search` still serves n8n). Grill question 5.
- The per-contact `chatbot_recall_enabled` toggle becomes the memory opt-out for that
  contact (label "Use conversation memory"), default ON. Owner decision D3 of 15 Sep set
  "global default off" for recall; this plan asks to flip it (grill question 1) because the
  new blocks cost no extra call and carry no other contact's data.

### 5.5 Retention

A nightly sweep on the existing scheduler (`ENABLE_SCHEDULER` worker): deletes frames older
than `episode_retention_days` (default 90), drops expired `tallied` / `stated` facts, and
closes live episodes idle past the gap (so the staff screen and the tally are current even for
a dealer who never writes again). The sweep is the only new scheduled job; it also closes
BL-054's gap for frames (turns keep their own backlog item).

### 5.6 Settings card: wire or remove

The four dead `chatbot_memory` keys become:

| key today | becomes |
|---|---|
| `recall_default` | `memory_default` (bool, default true): the value a new contact's toggle starts at |
| `episode_retention_days` | wired: sweep and backfill window (default 90) |
| `profile_fields` | removed (the vocabulary is code; a field list that nothing reads is config for a hypothetical) |
| `focus_reset_events` | removed; replaced by `episode_gap_minutes` (default 30) |

Both dict builders of `system_settings` carry the two new keys (DoD 4); the card shows three
controls. Grill question 11.
