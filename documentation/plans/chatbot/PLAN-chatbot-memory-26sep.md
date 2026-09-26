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

## 6. Layer 3: turn context assembly and the token budget

### 6.1 One assembler

`turn/context.py::assemble(layers: ContextLayers, budget: Budget) -> (text, ContextReport)`,
pure, no I/O. It replaces the string joining inside `build_user_block` and is the only place
the parser's user block is built. The same function, with a smaller budget, builds the memory
slice for the S4 clarifier call. Input is data already loaded at intake (profile row, frames,
live turns, focus, open question, message); nothing is fetched inside it.

Order in the block (most stable first, the live message last, so the model reads the current
message after its context):

```
About this contact:            L5 profile slice
Recent conversations:          L4 closed episode summaries
Earlier in this conversation:  L3 live episode (earlier user messages)
Previous response:             L3 (the bot's last reply, capped)
Current subject:               L2 focus
Pending / Open question options: L2
Current user message:          L1 (text, reply-to, media read line)
```

### 6.2 The budget, per layer

Tokens are estimated as `ceil(utf8_bytes / 3)`, which over-counts English (about 4 bytes per
token) and is close to exact for Malay and safe for Chinese (3 bytes per character, at most
one token each). Over-estimating is the safe direction: the cap can only be undershot.

| layer | content | budget (est. tokens) | when over | never dropped |
|---|---|---|---|---|
| L0 system prompt | registry body + policy blocks + memory addendum | **22,100** hard ceiling (today's measured 21.2k + 0.9k); memory addendum at most 400, paid by cuts in the same slice (6.4) | CI fails (6.3) | |
| L1 current message | text, `reply to:` quote (cut to 300 chars), media read line | 600 | quote cut first, then message cut at 1,500 chars with "(cut)" | the message itself |
| L2 focus + open question | `Current subject:`, `Pending:`, options (frozen) | 350 | options beyond 10 dropped with "(+N more)"; today's roster cap is 10 | the open question kind |
| L3 live episode | earlier user messages (max 3 x 200 chars) + `Previous response:` (600 chars) | 450 | oldest earlier message first, then the previous response is cut to 300 chars | the previous response's first 300 chars |
| L4 episode summaries | last 3 closed, 30 days, 240 chars each | 250 | oldest summary first | |
| L5 profile slice | parser-fed facts, fixed key order, values cut to 60 chars, list values max 3 | 150 | `note` first, then `project`, then `usual_sites` | `customer`, `segment`, `language` |
| **user block total** | L1 to L5 | **1,800 hard cap** | L5, then L4, then L3 trimmed to their "never dropped" floor | L1 message, L2 open question |
| output | `max_tokens` | 2,048 today, unchanged here (#1275 item 4 owns lowering it) | | |
| recall re-parse | second full parser call | **0** (deleted; today up to +22.8k per recall turn) | | |

What this adds, worst case: L3 +about 200 over today's uncapped previous reply, L4 +250, L5
+150 (today's `Profile:` line is about 10), plus the 400 addendum = **about +1,000 est.
tokens on a turn with full memory**, about +4% of 24.8k. A first-time contact adds 0.

### 6.3 How the budget is enforced (not just stated)

1. **In code:** `assemble` never returns a block over 1,800 est. tokens; the truncation order is
   the table above. Pure function, unit-tested on a worst-case fixture (every layer at 3x its
   cap). AC-MEM060.
2. **In CI, the system prompt:** `tests/chatbot/test_parser_prompt_budget.py` renders the
   production parser prompt (registry fallback + the policy blocks seed) and fails over 22,100
   est. tokens. This is the guard that would have caught the unexplained 13.4k to 22.8k jump
   of 22 Sep (#1275). AC-MEM061.
3. **In every trace:** the `understood` stage `facts` gain `prompt_tokens` and
   `completion_tokens` from the provider (not only `total_tokens`), and a `context` event
   records est. tokens per layer and what was dropped. `usage.py` logs the turn id. The
   recall-overwrite bug (`engine.py:1508`) disappears with the re-parse. AC-MEM062, AC-MEM063.
4. **In production, the gate:** S3 ships only if, over the first 3 weekdays after deploy,
   p95 of `prompt_tokens + 2048` per turn is **not higher than** the 3 weekdays before (the
   24.8k line), measured with the query in 8.2. If it is higher, the memory addendum is
   cut or the L4 / L5 caps are lowered before anything else ships. AC-MEM064.

### 6.4 Paying for the addendum (net zero on the static prompt)

The memory addendum (about 400 tokens: what the three blocks mean, how to use them for
references, that memory never overrides the current message) is paid for in the same slice by
deleting text measured as dead or ruled out:

| cut | est. tokens | evidence |
|---|---|---|
| the `previous_conversation_state` input description (never sent) | about 40 | section 2.1 |
| the n8n JS expression literal | about 197 | #1275 item 4 ("owner already ruled cut"); `parser-prompt-inventory.md` "dead" class |
| the 536-token section #1275 names, if the parser corpus stays green | about 536 | #1275 item 4 |
| **total** | **about 770** | covers the 400 addendum with margin |

The larger cut (finding the 9.4k added on 22 Sep) stays with #1275 item 4; this plan does not
depend on it and does not duplicate it.

Also in S3: move `CURRENT DATE: {{current_date}}` from character 595 to the end of the system
prompt, so the 21k static prefix is byte-stable across days for OpenAI's automatic prefix
cache (lower latency and cost on the cached part; whether cached tokens still count toward TPM
is unverified for this tier, so no capacity claim is made for it).

### 6.5 What the parser is asked to do with memory (the addendum, in substance)

- Resolve a reference ("that one", "same as yesterday", "the usual", "the one in Kuching")
  against, in order: the open question, `Current subject`, `Earlier in this conversation`,
  `Recent conversations`, `About this contact`. Copy the resolved entity into `entities[]`
  with `current_message: false`, exactly as focus carry works today.
- Memory never overrides a code, customer or domain named in the current message.
- `message_type` gains one value, `history_question`, for questions about the dealer's own
  past with the bot ("what did I ask you last week", "which products did I check"). Routed to
  the S4 history composer.
- New optional output `profile_statement: {key, value} | null`, keys limited to `language`,
  `role`, `usual_brands`, `usual_sites`, `project`, set only when the dealer states it about
  themselves ("I'm the purchaser", "always show Kuching first", "reply in Malay"). Applied by
  APPLY as a `stated` fact. Grill question 6.

The parser's strict JSON schema grows by one enum value and one nullable key. Parser pins:
`fixtures/parser_memory_phrases.json` in the style of `parser_growth_r1_phrases.json`, graded
by a reachability test that each cue appears in the addendum (AC-MEM066).

### 6.6 Latency budget

| step | today | budget after | how measured |
|---|---|---|---|
| intake memory reads (profile row already read; last 3 frames by the new index; live turns, limit 4) | n/a | p95 <= 40 ms | `received` stage `ms`, new `memory_ms` fact |
| gap close at intake (digest + one insert + embedding enqueue) | n/a | p95 <= 60 ms, only on the first turn after a gap | `received` facts `episode_closed_ms` |
| parser call with +1,000 tokens | p50 2.6 s | p50 +0.05 s at most (measured slope: +0.25 s per 9.4k tokens) | `understood` `ms` |
| recall re-parse | +2.6 s on each recall turn | 0 (deleted) | no `recall` event |
| tail (`remembered`), topic-switch close + tally | p95 105 ms | p95 <= 150 ms | `remembered` `ms` |
| S4 clarifier with memory slice | existing call | no added call; p50 +0.1 s at most | `routed`/`replied` `ms` on `low_signal` |
| **CRM turn total** | p50 3.8 s | **p50 +0.1 s at most, p95 unchanged** | turn `finished_at - started_at` |

The 10 s end-to-end target of #1275 is not moved by this plan either way; its limiters are
the n8n pre-turn gap and the resolver miss path, owned there.

## 7. Out-of-boundary replies

### 7.1 The four kinds and where each goes

| kind | example | parser signal | route | reply built by |
|---|---|---|---|---|
| small talk, thanks, off-topic | "morning boss", "what's the weather in Penang" | `message_type` casual / unknown, no domain | `low_signal` (existing) | clarifier writes the acknowledgement only; the engine adds the memory line and the offer |
| follow-up that needs the previous episode | "any update on that?" the next morning | a domain plus entities resolved from `Recent conversations` | business (existing) | the normal composer; the reply opens with one line naming what was carried ("For the outstanding DOs of Chin Chun Trading from yesterday:") |
| a question about their own history | "what did I ask you last week?" | `message_type = history_question` (new) | `history` (new, deterministic) | the history composer, from `conversation_frames` only |
| a request the CRM cannot fulfil | "give me 10% off", "cancel my order", an unsupported domain | escalation / request_for_help / not supported | `out_of_scope` / `not_supported` (existing) | acknowledgement + what the CRM can do instead + the handover offer (existing team or member offer) |

### 7.2 The reply shape (one contract for all four)

```
reply = ack            one sentence, human, may use the dealer's first name
      + memory_line    optional, deterministic, from profile / episodes / live CRM data
      + offer          the concrete next thing: a numbered choice, a re-run, or a handover
```

- Only `ack` is written by an LLM (the existing clarifier call, gpt-4.1-mini, now given the
  L5 profile slice and L4 summaries under a 400-token memory budget). It returns
  `{"ack": "..."}`, 25 words at most.
- **Guard:** an `ack` that contains a digit, a product-code-shaped token, a price or a date
  not present in its own input is replaced by the canned acknowledgement for the language
  (`chatbot_reply_copy`, editable). Facts reach the dealer only through `memory_line` and the
  composers, which read data. AC-MEM081.
- `memory_line` and `offer` are templates in `chatbot_reply_copy` (en, ms, zh), picked by
  profile `language`, else the language of the dealer's message as the clarifier reports it.
- **Never a bare refusal, never silence, never an exception.** Every bot turn that is not
  under human takeover sends one visible line. This fixes the 28 `out_of_scope` and 16
  `escalation_declined` turns that sent nothing (#1275), and replaces
  `"There is some error encountered by the AI: " + str(exc)` with the existing "Sorry, I ran
  into a problem..." copy. AC-MEM084 to AC-MEM086.
- A handover always names who: the linked salesperson (`salesperson` fact) when the ask is
  commercial (discount, credit, price exception), else the domain's team from
  `chatbot_domains`. It uses the existing offer and escalation path (`member_offer` /
  `team_pick`), so routing, assignment, comment and SLA row are unchanged.

### 7.3 Ten example exchanges

The contact in all ten: Mr Tan, purchaser at Chin Chun Trading (CC001), dealer, language en
unless stated, salesperson Aina. Memory holds: usual products SRTWB1455 and M486-75-BL, usual
site Kuching; episodes "Thu 25 Sep: stock SRTWB1455 (answered); incoming M486-75-BL (not
found); offered Stock team, declined." and "Tue 23 Sep: outstanding DO for CC001 Chin Chun
Trading (answered)."

**1. Greeting at the start of a day (small talk, memory used).**
> Dealer: morning boss
> Bot: Morning Mr Tan! Last time we looked at stock for SRTWB1455 and the incoming for
> M486-75-BL. Want me to check either again, or something new?

`low_signal`; ack from the clarifier ("Morning Mr Tan!"); memory_line from the newest summary;
offer = re-run. Without memory today: "Hello! How can I help you?" or the clarify menu.

**2. A follow-up that needs yesterday's episode.**
> Dealer: any update on that DO?
> Bot: For the outstanding DOs of Chin Chun Trading from Tuesday: (report, fetched now)

The parser resolves "that DO" from `Recent conversations` to document DO, customer CC001,
status outstanding; the business lane runs as normal; the carried-context line opens the
reply. Without memory: "Which customer?" (the focus from Tuesday may have been reset).

**3. A question about their own history.**
> Dealer: what did I ask you last week?
> Bot: Here's what you checked with me recently:
> 1. Thu 25 Sep: stock SRTWB1455, incoming M486-75-BL (not found then)
> 2. Tue 23 Sep: outstanding DOs for Chin Chun Trading
> Reply with a number and I'll run it again with today's figures.

`history_question`; deterministic from frames; no figures from the past. Without memory: the
clarify menu, or a stock search for the word "ask".

**4. A request the bot cannot fulfil (commercial).**
> Dealer: can give 10% discount for SO-2409-0112?
> Bot: I can't approve discounts myself, Mr Tan, but Aina can. Shall I send her SO-2409-0112
> with your request? 1. Yes 2. No, it's okay

`out_of_scope`, commercial, so the handover names the salesperson; existing member offer.
Without memory: an internal note to a team and nothing sent to the dealer.

**5. Off-topic.**
> Dealer: hot today in Kuching ah
> Bot: Very! Stay cool, Mr Tan. While you're here, want me to check Kuching stock for
> SRTWB1455 or M486-75-BL?

`low_signal`; offer uses `usual_sites` and `usual_products`. Without memory: a generic
greeting or the clarify menu.

**6. Frustration about a delivery.**
> Dealer: my delivery late again, very frustrating
> Bot: Sorry about that, Mr Tan, I understand. Chin Chun Trading has 2 open DOs: DO-2409-0331
> and DO-2409-0350. Want me to check their status, or pass this to the Logistics team?
> 1. Check status 2. Logistics team

`low_signal` with a complaint tone; memory_line fetches open DOs live through the existing
order tool (not a stored fact); offer is a two-option pick. Without memory: a clarify menu.

**7. A stated fact (profile write).**
> Dealer: I'm the new purchaser here, taking over from Mr Lim
> Bot: Welcome aboard! I've noted you're the purchaser at Chin Chun Trading. What can I check
> for you?

`profile_statement {role: purchaser}`, source `stated`, visible to staff with a `Said` badge.
No grant, scope or customer link changes (AC-MEM036). Without memory: the clarify menu.

**8. "The usual".**
> Dealer: stock for the usual
> Bot: Your usual two: (stock for SRTWB1455 and M486-75-BL, Kuching first)

The parser resolves "the usual" from `usual_products`; `usual_sites` orders the warehouses.
Without memory: "Which product?"

**9. Language preference (Malay).**
> Dealer: boleh reply dalam Bahasa Melayu lepas ni?
> Bot: Boleh, Encik Tan. Lepas ni saya balas dalam Bahasa Melayu. Ada apa-apa yang saya boleh
> semak?

`profile_statement {language: ms}`; later canned lines and templates use ms. Without memory:
English replies continue.

**10. Wants a person, mid-conversation.**
> Dealer: I want to talk to a real person
> Bot: Sure, Mr Tan. Aina looks after Chin Chun Trading; I'll ask her to message you here
> about the incoming for M486-75-BL we were just checking. OK? 1. Yes 2. No, it's okay

`request_for_help`; the handover carries the live episode's subject into the routed message
(the existing escalation comment gets the summary line). Without memory: a team question with
no context carried.

Every example is a replay case in S4 (section 8.1). Examples 1, 2, 3, 4, 5, 8 and 10 go red
with memory ablated (they read memory); 7 and 9 test the write path (the fact must be on the
profile afterwards); 6 tests the live CRM read and the two-option offer.

## 8. How each layer is evaluated

Three questions per layer: does it go red without memory (proof the test tests memory), what
does it cost in prompt tokens, and what does it cost in latency.

### 8.1 Key-free turn replay (CI, every PR)

New directory `tests/chatbot/replay_turns/memory/`, run by the existing
`tests/chatbot/test_turn_replay.py`. The case shape gains three optional inputs and two
expectations:

```
given:    frames: [...]            closed episodes seeded for the contact (is_test)
          profile_facts: [...]     facts seeded into chatbot_profile.facts
          live_turns: [...]        earlier turns of the live episode (message, branch, focus)
expected: prompt_contains: [...]   lines the assembled user block must contain
          context_caps: true       the ContextReport shows every layer within budget
          (plus the existing branch_kind, tools, focus_after, text, canned, action_kinds)
```

Replay stubs the parser with the recorded verdict, so it proves the ENGINE side: assembly,
routing, the history composer, the reply shape, the writes. Each case carries
`needs_memory: true`, and a meta-test re-runs every such case with memory ablated (a fixture
that empties L3 to L5 and the frames and facts reads) and **asserts it now fails**. A memory
case that stays green without memory is a defect in the case (the PRINCIPLES kill test,
applied to the corpus). AC-MEM067.

Cases per layer (minimum; each lands in its slice):

| layer | cases | red without memory because |
|---|---|---|
| episodes (S1, S3) | gap close + summary text; topic-switch close with all turn ids; "same report as yesterday" re-runs without asking; "and in kuching?" carries the live product; "that one" resolves to the previous episode's product after a topic switch | prompt lacks the summary or earlier message; the recorded verdict's carried entity has no source line |
| profile (S2, S3) | "the usual" (example 8); usual site ordering; stated role written (example 7); stated language used on the next canned line (example 9); a staff tombstone is not re-learned; "I'm the owner" grants nothing | no `About this contact` line; fact missing after the turn |
| out-of-boundary (S4) | the ten examples of 7.3; the ack guard replaces a hallucinated number; no silent turn on `out_of_scope` / `escalation_declined`; no exception text | no memory_line / offer; silence |

### 8.2 Live parser evaluation (needs the OpenAI key; run on every PR that touches the prompt)

`tests/chatbot/fixtures/parser_memory_cases.json`, about 30 cases: an assembled user block
with memory, plus the expected verdict keys (resolved entities with `current_message: false`,
`message_type`, `profile_statement`). Run through the existing parity path
(`scripts/chatbot_parser_parity.py`) twice:

| run | pass bar |
|---|---|
| with memory blocks | at least 27 of 30 correct |
| memory blocks stripped (ablation) | at least 24 of 30 WRONG (else the case does not test memory and is rewritten) |
| the existing parser corpus (about 1,871 params) new prompt vs pre-S3 prompt | agreement at least 97% (the S1b slim work measured 95.8% as a regression and 99.0% as self-agreement), every disagreement listed in the PR and ruled on |

### 8.3 Console check (live, after deploy; `documentation/agents/chatbot-verification.md`)

`tests/chatbot/console_cases/2026-09-memory.yaml`: multi-turn sequences that close an episode
by a natural topic switch (no clock tricks): "stock SRTWB1455" / "outstanding DO for chin
chun" / "back to that sink, stock in kuching?" must answer SRTWB1455 in Kuching. Plus examples
1, 3, 4 and 10 on the console contact. These run on `is_test` turns and so write and read
`is_test` frames only.

### 8.4 Token measurement (the S3 production gate)

Recorded per turn from S3 on: `understood.facts.prompt_tokens`, `completion_tokens`, and the
`context` event's per-layer estimates. The gate query (3 weekdays before vs 3 after):

```sql
select t.created_at::date d, count(*) turns,
  percentile_cont(0.5)  within group (order by (e->'facts'->>'prompt_tokens')::int) p50,
  percentile_cont(0.95) within group (order by (e->'facts'->>'prompt_tokens')::int) p95,
  max((e->'facts'->>'prompt_tokens')::int) mx,
  count(*) filter (where t.trace::text like '%"kind": "recall"%') recall_turns
from chatbot.turns t, jsonb_array_elements(t.trace) e
where e->>'stage' = 'understood' and not t.is_test and t.ingress = 'webhook'
group by 1 order by 1;
```

Before S3 the same query uses `facts.tokens` (total) minus the completion estimate; S0 adds
`prompt_tokens` to the facts early so the "before" window is measured the same way.

Pass: p95 prompt tokens after <= p95 before; `recall_turns` = 0; the estimator is never below
the provider's `prompt_tokens` for the user block's share (checked on the same window).

### 8.5 Latency

The stage query of #1275 (appendix A3) over the same two windows, with the budgets of 6.6.
Pass: CRM turn p50 +0.1 s at most, p95 not higher; `received` p95 +40 ms at most;
`remembered` p95 <= 150 ms.

### 8.6 Owner hand pass

The ten examples of 7.3 on the WhatsApp test number, after S4, before merge. The owner's
verdict is recorded verbatim in the PR.

## 9. Slices

One lane, one branch (`feat/chatbot-memory`), one PR; slices land as commits (lane merge
discipline). Phase 1 first: the FE for S2 (facts grid, episodes grid, open orders) and the
S0 drawer fix and S1 settings card, against mocks, verified in the browser. Then Phase 2 per
slice, tester first. Phase 3 once for the lane; `security-reviewer` joins because S2 adds
write routes on contacts and S3 changes what reaches an LLM from stored data.

| slice | what | depends on | UAC |
|---|---|---|---|
| S0 | schema and write path: frame index + `is_test`; episode boundaries (topic switch, gap at intake, handover); every turn id recorded; trace `memory` event fixed; drawer contract fixed; `prompt_tokens` on the trace; usage logs carry turn id | none | AC-MEM001 to AC-MEM012 |
| S1 | episode summaries: `episode_digest`; summary rules (no figures); backfill script; retention sweep; settings card wired / trimmed | S0 | AC-MEM020 to AC-MEM029 |
| S2 | profile facts and staff screen: vocabulary, four writers, precedence, tombstones, "facts never grant", tier pick writes, Contact card sections, facts routes | S1 (tally reads digests) | AC-MEM030 to AC-MEM049 |
| S3 | prompt assembly under budget: `turn/context.py`, per-layer caps, memory addendum and its paid cuts, `history_question` and `profile_statement` in the schema, recall re-parse deleted, date moved to the end, budget CI test, production token gate | S1, S2 | AC-MEM060 to AC-MEM072 |
| S4 | out-of-boundary replies: reply shape, clarifier gets the memory slice, ack guard, history composer, handover names who, no silence, no exception text, language templates | S3 | AC-MEM080 to AC-MEM095 |

### S0 - Schema and write path

- Migration: `conversation_frames.is_test boolean not null default false`; index
  `(contact_respond_id, is_test, closed_at desc)`. Revision id <= 32 chars, reparented at
  PR time (`scripts/alembic-reparent.sh`).
- `_write_episode` takes the full turn range (turns since the previous frame's `closed_at`),
  writes on `topic_reset` and on a gap detected at intake inside the per-contact ticket; no
  write when the range is empty; still none on a dry run.
- Handover close: the first bot turn after a human takeover closes the range.
- The trace `memory` event records the frame WRITTEN this turn and the real profile before and
  after; `trace_detail._memory` and `TurnDetailDrawer` agree on one shape (backend shape wins;
  FE types follow it); a vitest crosses the seam with a recorded production trace
  (LESSONS-LEARNT #102).
- `understood.facts` carries `prompt_tokens` and `completion_tokens`; `usage.py` logs the turn
  id.
- Summary text stays the old placeholder in S0 (S1 replaces it); behaviour for the dealer is
  unchanged in S0.

DoD: migration up and down on a prod copy; `pytest tests/chatbot -k "memory or episode"` green
on Postgres; a three-topic conversation plus one 31-minute gap produces three frames with the
right turn ids; drawer shows the Memory panel on a real turn at 375 and 1280 px
(agent-browser, sidebar navigation); single alembic head.

### S1 - Episode summaries

- `turn/episode_digest.py` (pure) and the summary line of 5.2, written by S0's writer.
- `scripts/backfill_chatbot_episodes.py` over the retention window; deletes placeholder
  frames; idempotent.
- Nightly sweep: retention, idle close.
- Settings card: `memory_default`, `episode_retention_days`, `episode_gap_minutes`; the two
  dead keys removed from model, schema, both dict builders and the card.

DoD: digest golden tests over 10 recorded episodes from the 25 Sep dump (anonymised), each
summary <= 240 chars with no figure; backfill run twice on a prod copy gives the same frame
count; sweep deletes a 91-day frame and keeps an 89-day one; card saves and reloads each key;
browser pass on the card.

### S2 - Profile facts and staff screen

- `turn/profile_facts.py`: vocabulary, `derive_crm`, `tally`, `apply_statement`, precedence,
  tombstones, expiry; called from the S0 writer's transaction and from APPLY's tail write.
- Routes: `GET /user-management/contacts/{id}/chatbot/memory` (facts, last 10 episodes, top 5
  open orders); `PUT` and `DELETE .../chatbot/facts/{key}` (deferred-action delete). The
  whole-profile PUT stops writing `facts`.
- Tier pick in chat writes `tier`. `always_full_report` removed.
- FE: the two grids and the open orders list in `ContactChatbotSection.tsx`, via hook and
  service (`useContactChatbotMemory`, `contactChatbotService`), `extractApiError`,
  `SearchableSelect clearable` for the key, DataGrid fixed layout.

DoD: pytest per route (happy, 403 without the permission, 422 on an unknown key, tombstone
survives a tally); the "I'm the owner" case leaves `access_levels` and linked customers
byte-identical; agent-browser: sidebar to User Management > Contacts > a contact, add, edit,
delete (countdown, no dialog) a fact, at 375 and 1280 px; both dict builders carry `facts`.

### S3 - Prompt assembly under budget

- `turn/context.py` and its budget table (6.2); `build_user_block` becomes a caller.
- Parser prompt: the memory addendum, the cuts of 6.4, the date moved to the end, the schema
  additions; published as a new registry version (Prompts page, one commit message).
- Recall re-parse and its trace kind deleted; the per-contact toggle relabelled.
- CI: `test_parser_prompt_budget.py`, the `assemble` worst-case test, the ablation meta-test.

DoD: 8.1 memory cases green and red under ablation; 8.2 bars met and the parity list ruled on
in the PR; the budget test green; after deploy, the 8.4 gate and 8.5 latency pass (the lane
stays open, or a follow-up is filed, until the 3-weekday window is in).

### S4 - Out-of-boundary replies

- Reply shape (7.2); clarifier input gains the L5 + L4 slice under 400 tokens and returns
  `{"ack": ...}`; the guard; templates in `chatbot_reply_copy` (en, ms, zh).
- `history` route and composer (frames only, numbered re-run options that the parser can
  resolve next turn against `Recent conversations`).
- `out_of_scope` and `escalation_declined` always send a visible line; the error path sends
  the existing apology copy, never exception text.
- Handover names the salesperson for commercial asks, the domain team otherwise; the routed
  message carries the live episode's summary line.

DoD: the ten examples as replay cases (8.1) green, and red under ablation where 7.3 says so;
console YAML green after deploy; the owner's hand pass (8.6) recorded; the #1275 no-reply
query shows 0 `out_of_scope` / `escalation_declined` turns without a send over 3 weekdays.

## 10. Simplest thing, not built (and the trigger that would build it)

| not built | why not now | trigger that builds it |
|---|---|---|
| a `contact_profile_facts` table | about 12 facts per contact, never queried across contacts, row already locked by the tail | the first feature that queries facts across contacts |
| an LLM episode summary | second model call per episode on the shared 200k TPM; not replayable; can invent facts | a history-question replay case or the owner's hand pass needs something the digest does not hold |
| vector recall (kept only as the n8n search route) | the last 3 summaries ride every parse; older history is answered by the history composer from the table | a hand-pass reference to an episode older than the last 3 that the history composer cannot find by entity |
| a tokenizer library (tiktoken) | the byte estimator over-counts and is checked against the provider's own `prompt_tokens` on every turn | the 8.4 check finds the estimator below the provider count |
| per-layer budgets as settings | one set of numbers, no second tenant, no evidence anyone would tune them | a second tenant or a measured need to tune without a deploy |
| company-level shared memory (two contacts at one dealer) | same-contact only was the owner's D3; no evidence yet | the owner asks for it, or a hand pass shows two contacts of one customer repeating each other's asks |
| proactive follow-ups ("I'll tell you when the ETA changes") | a new outbound trigger surface; not asked for | an owner ruling (it touches Respond.io outbound and consent) |

## 11. Risks

- **Parser regression from the addendum.** Mitigated by the 8.2 parity run with every
  disagreement ruled on in the PR, and by keeping the addendum at or below 400 tokens.
- **Stale memory misleads.** Summaries carry no figures; facts expire; the current message
  always wins (addendum rule); a follow-up always re-fetches.
- **Prompt injection through stored text.** Only staff write free text (`note`, 200 chars).
  Stated values are validated against masters: brands against the brand list, sites against
  warehouse names, role against a closed list (`purchaser`, `owner`, `sales`,
  `site_supervisor`, `other`), `project` cut to 60 chars with newlines stripped and printed
  quoted. `security-reviewer` checks this seam.
- **Privacy (Malaysia PDPA).** Nothing new is collected: turns are stored today; episodes are
  derived from them with a 90-day retention, and staff can see and delete every fact. The
  opt-out toggle stays per contact.
- **Concurrency.** Episode close and fact writes happen inside the per-contact ticket and the
  tail's `FOR UPDATE`; the staff fact routes update one key with `jsonb_set` under the same
  row lock, so a staff save never overwrites a learned fact (and the whole-profile PUT no longer
  touches `facts`).
- **Overlap with #1275.** Both touch the parser prompt. This plan cuts only the three items of
  6.4 and moves the date line; any larger cut is #1275's. Whichever lane merges second rebases
  the prompt text and re-runs 8.2.
- **Backfill on production.** Read-heavy over 90 days of turns; runs per contact in batches,
  idempotent, re-runnable; about 4.4k turns today.

## 12. Relation to "an enterprise version of Claude Code"

The owner's comparison maps cleanly, and it is useful because it names what this plan builds
and what it does not:

| Claude Code | Sorento chatbot after this plan |
|---|---|
| CLAUDE.md, the system prompt | the parser prompt plus the policy blocks rendered from `chatbot_domains` |
| user memory (facts about the person) | profile facts (layer 1), with source and expiry, editable by staff |
| context compaction (older turns become a summary) | episodes (layer 2): closed segments become one digest line |
| the context window budget | the per-layer token budget (layer 3), enforced in code and measured per turn |
| tools | the MCP tools behind the fetch lanes |
| permissions | grants, reveal gates, company scope (memory never changes them) |
| asking before acting | the open question and the numbered offer |

What Claude Code has and this plan does not build: acting on the user's behalf through tools
that WRITE (create a quote, raise a complaint, place an order after a confirmation). That is
the next step of the comparison and a different risk class (writes, approvals, audit). Grill
question 14 asks whether to open it as its own ideation issue.
