# PLAN - Chatbot memory: contact profile, episodes and turn context under a token budget

Status: DRAFT round 2, 26 Sep 2026. Owner rulings of 26 Sep 23:45 MYT applied (grill
questions 1, 2, 7, 10); questions 3, 4, 5, 6, 8, 9 answered in plain language and re-asked
on PR #1284 (comment 5847656721, "Answers to the owner's questions (round 2)"); 11 to 18 still open.
Track: full (migration, parser prompt change, staff screen, expected diff well over 300 lines).
Recommended as two lanes (grill question 17): A = S0 to S3 plus the owner test slice S3T,
B = S4.

Owner rulings applied in round 2 (26 Sep 2026 23:45 MYT, verbatim in the PR comment "Owner
rulings on the chatbot memory plan grill questions"):

- **Owner ruling 26 Sep 2026 (Q1):** memory stays OFF by default. "off first i need to test
  how it looks like to make sure no regression and carry forward of unnecessary memory". The
  per-contact toggle stays default false; no migration flips it. A new slice S3T (section 9)
  is the owner's test on a local stack, and any default-on decision is a separate later ruling
  made on S3T's evidence.
- **Owner ruling 26 Sep 2026 (Q2):** a conversation ends on a topic switch only. "i don't like
  time gap, it can be topic switch". No idle gap, no minutes setting, no handover close.
- **Owner ruling 26 Sep 2026 (Q7):** retention is not time based. "again i don't like time
  based, very uncertain". Replaced by counts (section 5.5): the newest 20 conversations per
  contact are kept, facts are kept until replaced, removed by staff, or the contact is deleted.
  The same rule removes every other day window from memory (the 30-day summary window, the
  90-day tally window, fact expiry dates, the nightly sweep).
- **Owner ruling 26 Sep 2026 (Q10):** accepted as recommended. "okay". The bot never stays
  silent.
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
  not on dry runs, released in a `finally`. It serialises one contact's turns only in S7
  mode and only while Redis is up, so this plan does not rely on it for correctness (5.1 makes
  the episode close idempotent in the database instead). #1275 measured its queue
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
feed them to the parser in a fixed, capped shape. Episodes get real boundaries (a topic
switch only, owner ruling 26 Sep 2026; no clock) and a deterministic written summary built from the turns' own trace (domains, entities,
answers, offers, outcome): no extra LLM call, backfillable over the 4,414 live turns already
in `chatbot.turns`. The profile gains a `facts` list inside the existing `chatbot_profile`
JSONB (no new table): facts tallied from closed episodes, facts the dealer states, facts staff
enter, each with source and last seen, none with an expiry date; CRM facts (customer, segment, salesperson) are
read live from the CRM links, never stored; staff see and edit it all on the Contact page. Every parse gets a capped context (profile slice, last three
episode summaries, the live episode's earlier messages, focus, open question, current
message) assembled by one pure function under a per-layer token budget, and the recall
re-parse is deleted. All of this runs only for a contact whose memory toggle is on, and the
toggle stays off by default until the owner has tested it (owner ruling 26 Sep 2026, S3T).
The low-signal lane
(small talk, "what did I ask you", "can you give me a discount") gets the same memory slice
and a reply shape (acknowledge, use what memory knows, offer the concrete thing the CRM can
do, or hand over), and never sends a raw error or nothing at all.

## 4. Layer 1: contact profile

### 4.1 What it holds

One closed vocabulary. A key not in this table is rejected by the writer (one validation
function, `turn/profile_facts.py`). Staff can add a free-text note; nothing else is free-form.

| key | example value | sources allowed | fed to the parser | kept until |
|---|---|---|---|---|
| `customer` | "Chin Chun Trading (CC001)" | crm (read live, not stored) | yes | n/a (live join) |
| `segment` | "dealer" / "project" / "end user" | crm (read live), staff | yes | n/a / staff removes it |
| `salesperson` | "Aina" | crm (read live) | no (S4 handover only) | n/a (live join) |
| `language` | "ms" | staff, stated | yes | replaced by a newer statement, or removed by staff |
| `role` | "purchaser" | stated, staff | yes | replaced, or removed by staff |
| `usual_products` | ["SRTWB1455", "M486-75-BL"] | tallied, staff | yes | tallied: drops out of the last 10 conversations; staff: removed by staff |
| `usual_brands` | ["Sorento"] | tallied, stated, staff | yes | as above |
| `usual_sites` | ["Kuching"] | tallied, stated, staff | yes | as above |
| `project` | "Aurora Residences block B" | stated, staff | yes | replaced, or removed by staff |
| `note` | free text, max 200 chars | staff | yes | removed by staff |

No fact carries an expiry date (owner ruling 26 Sep 2026, Q7: retention is not time based).
Every fact also goes when the contact is deleted.

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
     "last_seen": "2026-09-25", "seen_count": 4, "set_by": null},
    {"key": "role", "value": "purchaser", "source": "stated",
     "source_ref": "<turn id>", "first_seen": "2026-09-26", "last_seen": "2026-09-26",
     "seen_count": 1, "set_by": null},
    {"key": "note", "value": "Prefers PDF quotes", "source": "staff",
     "source_ref": null, "set_by": "<users.id>"}
  ]
}
```

`crm` facts never appear in the JSONB: they are one join at read time
(`respond_contact_customers` primary first, `customers.market_segment_code`,
`customers.sales_agent_id`), so they cannot go stale and need no writer.

Why no table: one contact holds at most about 12 facts and nothing queries facts across
contacts. Trigger for a table (written down per
PRINCIPLES): the first feature that must query facts across contacts (for example "every
contact whose usual brand is X" for a campaign).

### 4.3 Writers (each source has exactly one)

| source | writer | when |
|---|---|---|
| `crm` | none: `profile_facts.crm_view(contact)` reads them live at intake and on the staff screen | every read |
| `tallied` | `profile_facts.tally(contact)`: a product, brand or warehouse present in the entities of 2 or more of the contact's last 10 closed episodes (a count, not a day window; owner ruling 26 Sep 2026, Q7); top 3 by count then recency; recomputed whole, so a value that drops out of the last 10 stops being "usual" | right after each episode is written |
| `stated` | the parser's new optional `profile_statement` output (section 6.5), applied by APPLY into the tail's write | on the turn the dealer says it |
| `staff` | `PUT /user-management/contacts/{id}/chatbot/facts/{key}` and `DELETE` of the same; the existing whole-profile PUT stops touching `facts` | on the Contact page |

Every fact write is a single-key `jsonb_set` on `respond_contacts.chatbot_profile` under
`SELECT ... FOR UPDATE` of that row at write time, never a read-modify-write of the snapshot
loaded at intake (the parser call sits between the two for about 2.6 s, long enough for a
staff save to land and be overwritten). `write_episode` commits on its own session today
(`memory.py:62`, reasons in `engine.py:3330-3350`); the tally runs after that commit in its
own short transaction.

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
  `Said`, `Staff`), last seen. CRM rows are read-only and link to the customer. Staff
  can Add (modal: key from a `SearchableSelect` of the vocabulary, value), edit a row in place,
  and Delete (deferred action, 10 s hard delete, no confirm dialog; D7). Confirming a `Learned`
  or `Said` row turns it into `Staff` (the tally no longer replaces it). Empty state: "Nothing learned yet" plus the
  Add action.
- **Recent conversations** (read-only DataGrid): episode date, topic (domains), summary line,
  turn count, close reason; the row opens that turn range in Chat History (`rowHref`).
  Empty state with a link to Chat History.
- **Open orders** (read-only, live from the linked customer, top 5): the brief lists open
  orders as part of what the bot should know about a dealer, and this is the cheapest honest
  form of it: a live read, not a fact, not stored, not in the prompt.

Permissions: view needs the existing `user_management.contacts.view`; add, edit and delete
need the existing `user_management.contacts.edit`. No new permission, so no grant sweep.
Both dict builders (`contact_to_response_dict` and the chatbot GET) list `facts` (DoD 4).

Contact deletion: `conversation_frames` has no FK to `respond_contacts`, so the contact delete
service also deletes the contact's frames (by `contact_respond_id`), and the facts go with the
row. A PDPA erasure request is the same path. `chatbot.turns` keep their own retention
(BL-054 still open), so the episode count limit of 5.5 is not by itself a privacy guarantee.

## 5. Layer 2: episodes

### 5.1 What an episode is

A contiguous run of one contact's turns about one thing. It is **closed** by one trigger only:

| trigger | close_reason | detected where |
|---|---|---|
| the parser says `topic_reset` (today's only trigger, kept as the only one) | `topic_switch` | APPLY, written by the tail (unchanged seam) |

**Owner ruling 26 Sep 2026 (Q2): a conversation ends on a topic switch only.** The round 1
draft also closed on a 30-minute gap and on the human-takeover flag; both are dropped. Time
never closes a conversation: a dealer who asks about SRTWB1455 on Thursday and writes "and in
kuching?" on Monday is still in the same conversation, and the parser sees Thursday's message
as an earlier line (each earlier line is printed with its day, section 5.4, so the parser can
tell it is old). A human takeover does not close it either: when the bot resumes, the topic is
whatever it was. What bounds the context is the layer caps of section 6.2 (at most 3 earlier
messages), not a clock. If the owner's S3T test shows old messages carried where they should
not be, the fix is a sharper topic-switch signal from the parser (for example a greeting after
a finished answer), never a time rule.

There is **no open row**. The live episode is "this contact's turns created after the last
frame's `last_activity_at`", where `last_activity_at` is set to the `created_at` of the
episode's LAST turn (not the frame's write time: `closed_at` is a naive Python clock taken
after the resetting turn started, so bounding by it would put the resetting turn in the
closed episode). On a topic switch the resetting turn opens the new episode; the frame covers
the turns before it. An episode is written once, already closed, as `write_episode` does
today.

The live episode's earlier messages are one read of at most 4 rows (this contact's turns on the
same `is_test` side created after the last frame's `last_activity_at`, newest first).

Concurrency: the per-contact ticket serialises a contact's turns only in S7 mode, never on dry
runs, and a Redis outage runs the turn unordered (`engine.py:831-860`). So the close is made
idempotent in the database, not assumed: a unique index on
`(contact_respond_id, is_test, (turn_ids[1]))`, and the writer inserts with
`ON CONFLICT DO NOTHING`.

Console turns are dry runs (`console_service.py`: "D14: zero writes outside
`chatbot.turns`"), and two named exceptions already exist (media among them). Their live
episode works without any exception, because it is read from `chatbot.turns`, which dry runs
do write. Closing an episode is a write, so this plan asks for a **third named D14
exception**: an `is_test` turn may write an `is_test = true` frame (never a fact, never
anything else). Live turns never read `is_test` frames and `is_test` turns never read live
ones. Without the exception, cross-episode memory can only be tested key-free with injected
frames, never on the console. Grill question 15.

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
contact, walk all live `chatbot.turns` in order (no day window), cut episodes by the same one
trigger (recorded `topic_reset` in the `apply` event), write one frame per episode with its
digest, keep the newest 20 per contact (5.5), and delete the placeholder frames whose
summary matches `Closed the % topic.`. Key: the unique index of 5.1, so a second run changes
nothing. About 4.4k turns from 74 contacts today: seconds, not minutes. After it
runs, every dealer already has conversations on file, used the day their toggle is switched on.

### 5.4 What the parser gets from episodes

Two blocks, both inside the budget (section 6):

```
Earlier in this conversation (oldest first):
- Thu 10:02 you: stock SRTWB1455
- Thu 10:03 you: and in kuching?
Recent conversations:
- Thu 25 Sep: stock SRTWB1455 (answered); incoming M486-75-BL (not found); offered Stock team, declined.
- Tue 23 Sep: outstanding DO for CC001 Chin Chun Trading (answered).
```

- "Earlier in this conversation": the live episode's user messages before the current one,
  newest 3, each cut to 200 chars and prefixed with its day and time (the conversation has no
  time limit, so the day tells the parser a line is old). The existing `Previous response:`
  line stays and is capped at 600 chars. This is the "live episode instead of raw history" the
  owner asked for: the parser has never seen a single earlier user message until now.
- "Recent conversations": the last 3 closed episodes, however old (no day window; owner ruling
  26 Sep 2026, Q7 "no time-based rule"), newest first in the query, printed oldest first.
- Recall is replaced by this. The vector recall and its second parse (`engine.py:1487-1520`)
  are deleted in S3: every parse already carries the last three summaries, and a reference
  beyond three episodes is a history question the S4 history reply answers from the table.
  With no reader left, the frame embedding enqueue is also removed (it spends embedding calls
  for nothing; the n8n `/external/memory/frames/search` route filters on the old
  `contact_id` and there is no evidence n8n calls it). Grill question 5.
- The per-contact `chatbot_recall_enabled` toggle becomes the memory switch for that
  contact (label "Use conversation memory"), and it stays **default OFF**. **Owner ruling 26
  Sep 2026 (Q1): "off first i need to test how it looks like to make sure no regression and
  carry forward of unnecessary memory".** No migration touches the column default or existing
  rows. With the toggle off, the contact's parse is today's (AC-MEM049). The owner switches it
  on for a test contact in S3T; turning it on for everyone is a later, separate ruling made on
  S3T's evidence, and would be its own one-line migration then.

### 5.5 Retention (by count, never by time)

**Owner ruling 26 Sep 2026 (Q7): "again i don't like time based, very uncertain".** The round 1
draft kept conversations and learned facts 90 days and stated facts 180 days. Replaced by:

| what | kept until |
|---|---|
| closed conversations (frames) | the newest **20** per contact are kept. Writing the 21st deletes the oldest in the same transaction as the insert. |
| tallied facts | recomputed from the last 10 conversations on every episode write; a value no longer in 2 of them stops being a fact |
| stated facts | the dealer states a new value for the same key, or staff delete it |
| staff facts | staff delete it |
| everything above | the contact is deleted (4.5), which removes frames and facts |

Why 20: the bot reads at most 3 summaries per parse, the history answer lists 5, the staff
screen shows 10, and the tally reads 10; 20 leaves room above every reader. At 7.4 turns per
contact per day (#1275) that is weeks of conversations for a busy dealer and months for a quiet
one, and it is the same for both whatever the calendar says. It is a constant in code
(`turn/memory.py`, `KEEP_EPISODES = 20`, next to `write_episode`), not a setting. Trigger for a setting: the
owner asks to change it without a deploy.

No scheduled job: trimming happens on write, so the round 1 nightly sweep is dropped (one less
moving part). Turns keep their own retention item (BL-054). The staff screen shows the
unclosed tail as "current conversation", derived on read.

### 5.6 Settings card: remove the four dead keys

The four dead `chatbot_memory` keys all go, and with them the Memory settings card, since
nothing would be left on it:

| key today | becomes |
|---|---|
| `recall_default` | removed; the column default (false, Q1 ruling) is the default, no setting reads it |
| `episode_retention_days` | removed; retention is a count (5.5, Q7 ruling) |
| `profile_fields` | removed (the vocabulary is code; a field list that nothing reads is config for a hypothetical) |
| `focus_reset_events` | removed; a conversation ends on a topic switch only (5.1, Q2 ruling), so there is no gap setting to replace it with |

Both dict builders of `system_settings` drop the key (DoD 4). Grill question 11 (not yet
answered) is revised by rulings 2 and 7: the round 1 recommendation kept two controls, and
both were time rules.

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

Tokens are estimated as `ceil(utf8_bytes / 3)`. That over-counts English and Malay (about 4
bytes per token) and is about right for common Chinese (3 bytes per character); rare CJK
characters can take 2 to 3 tokens each, so the estimate is checked against the provider on
real turns (6.3 item 3), not trusted blindly. Every cap below is in est. tokens, and every
"cut at" is in bytes, so the two never mix.

| layer | content | cap (est. tokens) | when over | kept whole |
|---|---|---|---|---|
| L0 system prompt | registry body + policy blocks + memory addendum | **22,100** ceiling (today's measured 21.2k + 0.9k); addendum at most 400, paid by cuts (6.4) | CI fails (6.3) | |
| L1 current message | text (cut at 1,500 bytes with "(cut)"), `reply to:` quote (cut at 600 bytes), media read line | 600 | quote cut first, then the text | the first 1,500 bytes of the text |
| L2 focus + open question | `Current subject:`, `Pending:`, options (frozen) | 350 | options beyond 10 dropped with "(+N more)"; today's roster cap is 10 | the open question kind |
| L3 live episode | earlier user messages (max 3, 600 bytes each) + `Previous response:` (1,800 bytes) | 450 | oldest earlier message first, then the previous response is cut to 900 bytes | the previous response's first 900 bytes |
| L4 episode summaries | last 3 closed (no day window), 720 bytes each | 250 | oldest summary first | |
| L5 profile slice | parser-fed facts, fixed key order, values cut to 180 bytes, list values max 3 | 150 | `note` first, then `project`, then `usual_sites` | `customer`, `segment`, `language` |
| **user block** | L1 to L5 | **1,800** = the sum of the layer caps; no separate global rule | each layer enforces its own cap, so the sum cannot be exceeded | |
| output | `max_tokens` | 2,048 today, unchanged here (#1275 item 4 owns lowering it) | | |
| recall re-parse | second full parser call | **0** (deleted; today up to +22.8k per recall turn, rare because recall is off by default) | | |

What this adds, worst case, on a turn with full memory: L3 about +200 over today's uncapped
previous reply, L4 +250, L5 +150 (today's `Profile:` line is about 10): **about +600 est.
tokens on the user block**. The system prompt is net zero if 6.4's cuts cover the addendum.
At +600, requested per call goes from about 24.8k to about 25.4k: 7.87 calls per minute
instead of 8.06 (-2.4%) in the worst case; a first-time contact adds 0. Capacity itself is
#1275's lane; this plan only promises not to make it materially worse.

### 6.3 How the budget is enforced (not just stated)

1. **In code:** each layer renderer enforces its own cap in `assemble`; a test asserts the
   invariant "user block <= 1,800 est. tokens" on a worst-case fixture (every layer at 3x its
   cap). AC-MEM060.
2. **In CI, the system prompt:** `tests/chatbot/test_parser_prompt_budget.py` renders the
   production parser prompt (registry fallback + the policy blocks seed) and fails over 22,100
   est. tokens. This is the guard that would have caught the unexplained 13.4k to 22.8k jump
   of 22 Sep (#1275). AC-MEM061.
3. **In every trace:** the `understood` stage `facts` gain `prompt_tokens` and
   `completion_tokens` from the provider (not only `total_tokens`), and a `context` event
   records est. tokens per layer and what was cut. The provider reports only the total, so the
   system prompt's own token count is recorded once per published prompt version (one probe
   call with a one-word user block at publish), and the user block's real share is
   `prompt_tokens - system_prompt_tokens(version)`; the estimator is checked against that.
   `usage.py` logs the turn id. The recall-overwrite bug (`engine.py:1508`) disappears with the
   re-parse. AC-MEM062, AC-MEM063.
4. **In production, the gate:** memory is off by default (owner ruling 26 Sep 2026, Q1), so
   S3's deploy changes only the static prompt for almost every contact. Over the first 3
   weekdays after S3 deploys, p95 of `prompt_tokens` per live turn is **not higher** than the
   p95 of the 3 weekdays before (the static prompt is net zero). The **+600** worst case of the
   memory blocks is measured on the owner's S3T turns (every trace carries the `context`
   event) and re-measured with the query in 8.4 over the 3 weekdays after any later default-on
   ruling. Over either bar, the L4 / L5 caps are lowered before anything else ships.
   AC-MEM064. Grill question 8.

### 6.4 Paying for the addendum (net zero on the static prompt)

The memory addendum (about 400 tokens: what the three blocks mean, how to use them for
references, that memory never overrides the current message) is paid for in the same slice by
deleting text measured as dead or ruled out:

| cut | est. tokens | firm? | evidence |
|---|---|---|---|
| the `previous_conversation_state` input description (never sent) | about 40 | firm | section 2.1 |
| the n8n JS expression literal | about 197 | firm | #1275 item 4 ("owner already ruled cut"); `parser-prompt-inventory.md` "dead" class |
| the 536-token section #1275 names | about 536 | only if 8.2 stays green | #1275 item 4 |
| **firm total** | **about 237** | | short of the 400 addendum by about 163 |

So the firm cuts do not pay for a 400-token addendum on their own. The CI ceiling (22,100) is
the rule, not the list: S3 either lands the 536 cut (or another cut from the inventory's dead
or duplicated classes that 8.2 shows is safe), or the addendum is written to fit in what the
firm cuts pay for (about 237 tokens). Either way the ceiling holds.

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
| a question about their own history | "what did I ask you last week?" | `message_type = history_question` (new enum value) | `low_signal` (existing; no new route) | the ack plus a deterministic `memory_line` listing recent episodes from `conversation_frames` only |
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
- Language. `chatbot_reply_copy` has one registry key per string today, no language variants,
  and existing canned and composer text is English in code (`turn/compose.py:395-397`,
  `lanes/business/answer.py:1691`). This plan does not translate existing text. The ack is
  written by the LLM in the dealer's language; the clarifier's output gains a `language`
  field (`en | ms | zh`) next to `ack`. Only the NEW `memory_line` and `offer` templates get
  en, ms and zh keys (`chatbot_reply_copy` key suffix `.ms` / `.zh`, falling back to the bare
  key), picked by profile `language`, else the clarifier's `language`. The escalation offer
  wording is NOT translated: accepted-offer detection still matches it by regex until the
  rearch S8 (`chatbot_reply_copy.py:14-19`), so a handover offer keeps the existing English
  copy. Translating the rest is its own lane (grill question 16).
- Names. The ack may use the contact's stored `first_name`; code never adds an honorific
  ("Mr", "Encik"). Names in the examples below are illustrative.
- **Never a bare refusal, never silence, never an exception.** Every turn that reaches the
  reply stage sends exactly one visible line. This fixes the 28 `out_of_scope` and 16
  `escalation_declined` turns that sent nothing (#1275), and replaces
  `"There is some error encountered by the AI: " + str(exc)` with the existing "Sorry, I ran
  into a problem..." copy. AC-MEM084 to AC-MEM086.
- A handover always names who: the linked salesperson (`salesperson`, read live) when the ask
  is commercial (discount, credit, price exception) and the salesperson is reachable by the
  member-offer path; otherwise the domain's team from `chatbot_domains`. It uses the existing offer and escalation path (`member_offer` /
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

`history_question`, answered in the `low_signal` lane: the ack from the clarifier, the list
deterministic from frames, no figures from the past; "2" next turn is resolved by the parser
against `Recent conversations`. Without memory: the clarify menu, or a stock search for the
word "ask".

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
> Bot: Sorry about that, Mr Tan, I understand. Want me to check the outstanding DOs for Chin
> Chun Trading now, or pass this to the Logistics team?
> 1. Check outstanding DOs 2. Logistics team

`low_signal`; there is no complaint-tone signal and none is added: the clarifier's ack
carries the tone. The offer names the customer from the live CRM link; nothing is fetched in
this lane. "1" next turn runs the normal order lane (fresh data). Without memory: a clarify
menu that does not know who the customer is.

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

`profile_statement {language: ms}`; later acks and the new memory templates use ms. Existing
report and canned text stays English (grill question 16). Without memory: the next small-talk
reply may drift back to English.

**10. Wants a person, mid-conversation.**
> Dealer: I want to talk to a real person
> Bot: Sure, Mr Tan. Aina looks after Chin Chun Trading; I'll ask her to message you here
> about the incoming for M486-75-BL we were just checking. OK? 1. Yes 2. No, it's okay

`request_for_help`; the handover carries the live episode's subject into the routed message
(the existing escalation comment gets the summary line). Without memory: a team question with
no context carried.

Every example is a replay case in S4 (section 8.1). Examples 1, 2, 3, 4, 5, 8 and 10 go red
with memory ablated (they read memory); 7 and 9 test the write path (the fact must be on the
profile afterwards, asserted in pytest because replay is a dry run); 6 tests the live CRM
link and the two-option offer.

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
          live_turns: [...]        earlier turns of the live episode (message, branch, focus,
                                   created_at: injected, because now() is fixed for the whole
                                   replay transaction and every step would get the same time)
expected: prompt_contains: [...]   lines the assembled user block must contain
          context_caps: true       the ContextReport shows every layer within budget
          (plus the existing branch_kind, tools, focus_after, text, canned, action_kinds)
```

Replay stubs the parser with the recorded verdict, and every replay step is an `is_test` dry
run (`test_turn_replay.py:845`; D14: no writes outside `chatbot.turns`), all on one shared
Postgres connection (`tests/chatbot/conftest.py:24-48`), so seeded rows are visible. Replay
therefore proves the ENGINE's READ side: assembly, routing, the history reply, the reply
shape. The WRITE side (frames written with the right turn ids, facts on the profile after
examples 7 and 9, the topic-switch close, the trim to 20) is proved by ordinary pytest on live-mode turns in
`tests/chatbot/test_memory_*.py`, not by replay. Each case carries
`needs_memory: true`, and a meta-test re-runs every such case with memory ablated (a fixture
that empties L3 to L5 and the frames and facts reads) and **asserts it now fails**. A memory
case that stays green without memory is a defect in the case (the PRINCIPLES kill test,
applied to the corpus). AC-MEM067.

Cases per layer (minimum; each lands in its slice):

| layer | cases | red without memory because |
|---|---|---|
| episodes (S1, S3) | topic-switch close with all turn ids and the summary text; a message days later without a topic switch stays in the same conversation; "same report as yesterday" re-runs without asking; "and in kuching?" carries the live product; "that one" resolves to the previous episode's product after a topic switch | prompt lacks the summary or earlier message; the recorded verdict's carried entity has no source line |
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

`tests/chatbot/console_cases/2026-09-memory.yaml`:

- Within one live episode (works under D14 as it stands, the live episode is read from
  `chatbot.turns`): "stock SRTWB1455" / "and in kuching?" must answer SRTWB1455 in Kuching.
- Across episodes (needs the D14 exception of grill question 15): "stock SRTWB1455" /
  "outstanding DO for chin chun" (topic switch closes an `is_test` episode) / "back to that
  sink, stock in kuching?" must answer SRTWB1455 in Kuching. Plus examples 1, 3, 4 and 10.
  Without the exception these cases are dropped and the cross-episode proof is key-free
  replay plus the owner's hand pass only.

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

Pass after S3 (memory off by default): p95 prompt tokens after <= p95 before;
`recall_turns` = 0. Pass after a later default-on ruling: p95 after <= p95 before + 600. In
both, the estimator is never
below the user block's real share (`prompt_tokens - system_prompt_tokens(version)`, 6.3) on
the same window.

### 8.5 Latency

The stage query of #1275 (appendix A3) over the same two windows, with the budgets of 6.6.
Pass: CRM turn p50 +0.1 s at most, p95 not higher; `received` p95 +40 ms at most;
`remembered` p95 <= 150 ms.

### 8.6 Owner hand pass

The ten examples of 7.3 on the WhatsApp test number, after S4, before merge. The owner's
verdict is recorded verbatim in the PR.

## 9. Slices

Slices land as commits on their lane's branch (lane merge discipline); the recommended split
into two lanes is below the table. Phase 1 first: the FE for S2 (facts grid, episodes grid, open orders) and the
S0 drawer fix and S1 settings card, against mocks, verified in the browser. Then Phase 2 per
slice, tester first. Phase 3 once for the lane; `security-reviewer` joins because S2 adds
write routes on contacts and S3 changes what reaches an LLM from stored data.

| slice | what | depends on | UAC |
|---|---|---|---|
| S0 | schema and write path: frame `is_test`, index and unique key; episode boundary by topic switch only (owner ruling 26 Sep 2026, Q2); trim to the newest 20 per contact on write (Q7); every turn id recorded; trace `memory` event fixed; drawer contract fixed; `prompt_tokens` on the trace; usage logs carry turn id; contact delete removes frames | none | AC-MEM001 to AC-MEM013 |
| S1 | episode summaries: `episode_digest`; summary rules (no figures); backfill script; the four dead memory settings and the Memory card removed | S0 | AC-MEM020 to AC-MEM029 |
| S2 | profile facts and staff screen: vocabulary, CRM view read live, tally, stated, staff, precedence, tombstones, single-key writes under lock, "facts never grant", tier pick writes, Contact card sections, facts routes | S1 (tally reads digests) | AC-MEM030 to AC-MEM050 |
| S3 | prompt assembly under budget: `turn/context.py`, per-layer caps, memory addendum and its paid cuts, `history_question` and `profile_statement` in the schema, recall re-parse and frame embedding deleted, toggle relabelled and still default OFF (Q1 ruling), date moved to the end, budget CI test, production token gate | S1, S2 | AC-MEM060 to AC-MEM073 |
| S3T | owner memory test on a local stack (owner ruling 26 Sep 2026, Q1): memory switched on for one test contact; regression run; carry-over cases that must NOT carry; the owner's verdict recorded verbatim. No default-on change in this slice | S3 | AC-MEM074 to AC-MEM079 |
| S4 | out-of-boundary replies: reply shape, clarifier gets the memory slice and reports language, ack guard, history reply, handover names who, no silence, no exception text, new templates in en / ms / zh | S3 | AC-MEM080 to AC-MEM095 |

No slice flips the memory default (owner ruling 26 Sep 2026, Q1). Until S3 deploys, the
toggle still gates today's recall re-parse, so no contact's toggle is switched on for testing
before S3 (it would test the old double call, not the new memory).

Lane split (grill question 17): recommended as two lanes, A = S0 to S3 plus S3T (ships with
memory off, then the 3-weekday static-prompt token and latency check runs, and the owner runs
S3T), B = S4 (changes what dealers read; starts after the owner's S3T verdict). Each is its own
branch and PR, which the lane merge rule allows because B's start depends on the owner's test
of A, not on code alone. The S3T cases are re-run once B lands, before any default-on ruling.

### S0 - Schema and write path

- Migration: `conversation_frames.is_test boolean not null default false`; index
  `(contact_respond_id, is_test, last_activity_at desc)`; unique index
  `(contact_respond_id, is_test, (turn_ids[1]))`. Revision id <= 32 chars, reparented at PR
  time (`scripts/alembic-reparent.sh`).
- `_write_episode` takes the full turn range (turns created after the previous frame's
  `last_activity_at`), sets `last_activity_at` to the last turn's `created_at`, inserts with
  `ON CONFLICT DO NOTHING`, writes on `topic_reset` only (owner ruling 26 Sep 2026, Q2: no
  gap close, no handover close); no write when the range is empty; none on a dry run unless
  grill question 15 grants the `is_test` frame exception.
- In the same transaction as the insert, deletes the contact's frames beyond the newest
  `KEEP_EPISODES = 20` on that `is_test` side (owner ruling 26 Sep 2026, Q7).
- The contact delete service deletes the contact's frames.
- The trace `memory` event records the frame WRITTEN this turn and the real profile before and
  after; `trace_detail._memory` and `TurnDetailDrawer` agree on one shape (backend shape wins;
  FE types follow it); a vitest crosses the seam with a recorded production trace
  (LESSONS-LEARNT #102).
- `understood.facts` carries `prompt_tokens` and `completion_tokens`; `usage.py` logs the turn
  id.
- Summary text stays the old placeholder in S0 (S1 replaces it); behaviour for the dealer is
  unchanged in S0.

DoD: migration up and down on a prod copy; `pytest tests/chatbot -k "memory or episode"` green
on Postgres; a three-topic conversation with a three-day pause inside one topic produces two
frames with the right turn ids (the pause closes nothing); a 21st frame deletes the oldest; drawer shows the Memory panel on a real turn at 375 and 1280 px
(agent-browser, sidebar navigation); single alembic head.

### S1 - Episode summaries

- `turn/episode_digest.py` (pure) and the summary line of 5.2, written by S0's writer.
- `scripts/backfill_chatbot_episodes.py` over all live turns, keeping the newest 20 frames per
  contact; deletes placeholder frames; idempotent.
- No nightly sweep (retention is a count, trimmed on write; Q7 ruling).
- `recall_default`, `episode_retention_days`, `profile_fields` and `focus_reset_events`
  removed from model, schema, both dict builders; the Memory settings card removed.

DoD: digest golden tests over 10 recorded episodes from the 25 Sep dump (anonymised), each
summary <= 240 chars with no figure; backfill run twice on a prod copy gives the same frame
count and at most 20 frames per contact; browser pass that Settings > Chatbot renders
without the Memory card at 375 and 1280 px.

### S2 - Profile facts and staff screen

- `turn/profile_facts.py`: vocabulary, `crm_view` (live join), `tally`, `apply_statement`,
  precedence, tombstones (no expiry dates, Q7 ruling); every write a single-key `jsonb_set` under a row lock taken
  at write time; `tally` runs after `write_episode` commits, `apply_statement` in the tail.
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
- Recall re-parse, its trace kind and the frame embedding enqueue deleted; the per-contact
  toggle relabelled "Use conversation memory", still default OFF, no data change (owner ruling
  26 Sep 2026, Q1).
- CI: `test_parser_prompt_budget.py`, the `assemble` worst-case test, the ablation meta-test.

DoD: 8.1 memory cases green and red under ablation; 8.2 bars met and the parity list ruled on
in the PR; the budget test green; after deploy, the 8.4 static-prompt gate and 8.5 latency
pass (the lane stays open, or a follow-up is filed, until the 3-weekday window is in).

### S3T - Owner memory test on a local stack (owner ruling 26 Sep 2026, Q1)

The owner's words: "off first i need to test how it looks like to make sure no regression and
carry forward of unnecessary memory". This slice is that test, made repeatable, and it comes
before any default-on decision.

- Stack: the owner's local stack (the four Dev-session services of CLAUDE.md) on a prod copy,
  with an OpenAI key set (the local `.env` has none by default, and the console's live parser
  needs it). Memory is switched on for one named test contact on its Contact card; every other
  contact stays off.
- `tests/chatbot/console_cases/2026-09-memory-owner.yaml`, run with
  `scripts/chatbot_console_check.py` against that contact, in three groups:
  1. **No regression.** The existing console case files re-run with the test contact's memory
     ON give the same branch kind, tools and canned text as with it OFF; each difference is
     listed in the PR for the owner to rule on.
  2. **No unwanted carry-over** (each must NOT use memory): after "stock SRTWB1455" then
     "outstanding DO for chin chun" (topic switch), "stock M483-BL" answers M483-BL only; a
     message naming a new product never gets the old one added; "hi" after a finished answer
     does not re-run the old question; a question about another customer does not inherit the
     previous customer; a fact "said" by the dealer never changes what data he can see
     (AC-MEM036); the same case with memory OFF gives today's reply.
  3. **Memory helps** (each must use memory): "and in kuching?" carries the product; "same as
     last time" re-runs the previous conversation's ask; "stock for the usual".
- Every S3T turn's trace carries the `context` event, so the owner's run also records the
  memory blocks' real token cost (the +600 bar of 6.3).
- The owner's verdict is recorded verbatim in the PR, with the list of turns where memory
  carried something it should not have. Each such turn becomes a replay case in
  `replay_turns/memory/` that asserts the carry does NOT happen, and is fixed before any
  default-on ruling (by a sharper topic-switch signal or a tighter layer, never a time rule).
- Out: flipping the default. That is a separate owner ruling after this verdict; if it is yes,
  it is a one-line migration in its own commit, followed by the 8.4 +600 gate.

DoD: the YAML green on the owner's stack; the regression diff list ruled on; the owner's
verdict in the PR; every carry-over turn the owner flags has a replay case.

### S4 - Out-of-boundary replies

- Reply shape (7.2); clarifier input gains the L5 + L4 slice under 400 tokens and returns
  `{"ack": ..., "language": ...}`; the guard; the new templates in `chatbot_reply_copy` with
  `.ms` / `.zh` keys (existing copy untouched).
- `history_question` in the `low_signal` lane: the memory_line lists recent episodes from
  frames only, numbered, and the parser resolves the number next turn against
  `Recent conversations`.
- `out_of_scope` and `escalation_declined` always send a visible line; the error path sends
  the existing apology copy, never exception text.
- Handover names the salesperson for commercial asks, the domain team otherwise; the routed
  message carries the live episode's summary line.

With memory off for a contact (the default), the reply shape still holds with no
`memory_line`: ack plus offer.

DoD: the ten examples as replay cases (8.1) green, and red under ablation where 7.3 says so;
console YAML green after deploy; the S3T cases re-run green; the owner's hand pass (8.6) recorded; the #1275 no-reply
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
- **Stale memory misleads.** Summaries carry no figures; earlier messages carry their day;
  tallied facts follow the last 10 conversations; the current message always wins (addendum
  rule); a follow-up always re-fetches. The owner's S3T test looks for exactly this before
  memory is on for anyone.
- **A conversation that never ends.** With no time rule, a dealer who never switches topic
  stays in one conversation. Bounded by the 3-message cap of L3, and caught in S3T if it
  misleads.
- **Prompt injection through stored text.** Only staff write free text (`note`, 200 chars).
  Stated values are validated against masters: brands against the brand list, sites against
  warehouse names, role against a closed list (`purchaser`, `owner`, `sales`,
  `site_supervisor`, `other`), `project` cut to 60 chars with newlines stripped and printed
  quoted. `security-reviewer` checks this seam.
- **Privacy (Malaysia PDPA).** Nothing new is collected: turns are stored today; episodes are
  derived from them, at most 20 per contact, and staff can see and delete every fact. The
  toggle stays per contact and off by default.
- **Concurrency.** The episode close is idempotent by a unique key, not by the ticket. Every
  fact write (tally, stated, staff) is a single-key `jsonb_set` under a row lock taken at
  write time, never a write-back of the snapshot read at intake, so a staff save during a
  turn's 2.6 s parser call is not overwritten (and the whole-profile PUT no longer touches
  `facts`).
- **Overlap with #1275.** Both touch the parser prompt, and a #1275 prompt cut landing inside
  S3's before/after window would hide or fake S3's token effect. This lane waits for any
  #1275 prompt change to be deployed first, and its "before" window starts after that deploy.
  This plan cuts only the items of 6.4 and moves the date line; any larger cut is #1275's.
  Whichever lane merges second rebases the prompt text and re-runs 8.2.
- **Backfill on production.** Read-heavy over all live turns; runs per contact in batches,
  idempotent, re-runnable; about 4.4k turns today.

## 12. Relation to "an enterprise version of Claude Code"

The owner's comparison maps cleanly, and it is useful because it names what this plan builds
and what it does not:

| Claude Code | Sorento chatbot after this plan |
|---|---|
| CLAUDE.md, the system prompt | the parser prompt plus the policy blocks rendered from `chatbot_domains` |
| user memory (facts about the person) | profile facts (layer 1), with source, editable by staff |
| context compaction (older turns become a summary) | episodes (layer 2): closed segments become one digest line |
| the context window budget | the per-layer token budget (layer 3), enforced in code and measured per turn |
| tools | the MCP tools behind the fetch lanes |
| permissions | grants, reveal gates, company scope (memory never changes them) |
| asking before acting | the open question and the numbered offer |

What Claude Code has and this plan does not build: acting on the user's behalf through tools
that WRITE (create a quote, raise a complaint, place an order after a confirmation). That is
the next step of the comparison and a different risk class (writes, approvals, audit). Grill
question 14 asks whether to open it as its own ideation issue.

## 13. Grill questions for the owner

Each has a recommendation. The UAC is written to the recommendations; a different answer
rewrites the ACs tagged with that question before any code. The draft was grilled once by a
`planner` pass against the code (26 Sep); its corrections are already folded into sections 4
to 9 (episode boundary by turn time, replay and console are dry runs, the one-shot takeover
flag, no per-language copy today, firm prompt cuts short of the addendum, the recall default
flip must land with the recall deletion).

Round 2 status: 1, 2, 7 and 10 are ruled (below); 3, 4, 5, 6, 8 and 9 were asked back as
questions and are answered in plain language on PR #1284 ("Answers to the owner's questions
(round 2)"), then re-asked; 11 to 18 are not yet answered.

1. **RULED. Owner ruling 26 Sep 2026: memory OFF by default** until the owner has tested it on
   a local stack for regressions and unwanted carry-over (slice S3T). The round 1
   recommendation (ON for everyone) is withdrawn; default-on is a later ruling made on S3T's
   evidence.
2. **RULED. Owner ruling 26 Sep 2026: a conversation ends on a topic switch only.** No time
   gap, no gap setting (5.1).
3. **Who writes the episode summary?** **Recommendation: code, from what the turns recorded,
   no LLM call, and never a figure** (no stock count, price or ETA from the past; a follow-up
   always re-fetches). Zero tokens on the shared limit, replayable, backfillable, cannot invent
   a fact. It loses the colour of small talk; an LLM sentence is added only if a hand pass shows
   a question the code summary cannot answer.
4. **How much history rides on every parse?** **Recommendation: the last 3 conversation
   summaries (no day window, per the Q7 ruling), plus the current conversation's last 3
   messages from the dealer** (the parser has never seen a single earlier dealer message until now). Older
   history is answered on request ("what did I ask last week").
5. **Delete the vector recall (the second parser call)?** **Recommendation: yes, and stop
   writing frame embeddings.** It doubles the tokens of the turns it fires on to hand the model
   "Closed the stock topic."; the summaries on every parse replace it. The n8n search route
   stays but loses new embeddings; say so if n8n still uses it.
6. **Save what the dealer says about themselves?** ("I'm the purchaser", "reply in Malay",
   "always show Kuching first".) **Recommendation: yes, at once, from a closed list of five
   keys, validated against the masters, shown to staff as "Said" and deletable; never a
   grant.** "I'm the owner of Iborn" changes nothing about what he can see.
7. **RULED. Owner ruling 26 Sep 2026: retention is not time based.** Adopted rule (5.5): the
   newest 20 conversations per contact are kept (the 21st deletes the oldest); learned facts
   follow the last 10 conversations; stated facts stay until replaced or deleted by staff;
   staff facts until staff remove them; contact delete removes all of it. No expiry dates, no
   nightly sweep. Chat turns keep their own retention (BL-054), so this is not by itself a
   privacy guarantee.
8. **What may memory cost in tokens?** **Recommendation: the static parser prompt may not grow
   at all (a CI test fails above 22,100 tokens, so the memory instructions are paid for by
   cutting dead text), and the per-turn memory block is capped at +600 tokens worst case;
   production p95 may rise by at most 600 tokens (about -2.4% calls per minute worst case).**
   The alternative, strict net zero per turn, needs about 600 more tokens of cuts that are not
   yet identified.
9. **Who writes the out-of-boundary reply?** **Recommendation: the LLM writes only the one
   human sentence (the acknowledgement); every fact, name of a product, order or date comes
   from data, and a guard replaces an acknowledgement that invents a number or a code.**
10. **RULED. Owner ruling 26 Sep 2026: accepted.** The bot never stays silent: every turn
    that reaches the reply stage sends exactly one visible line, and an error never shows
    exception text.
11. **The Memory settings card.** Four of its settings are saved and never read.
    **Recommendation (revised by rulings 2 and 7): remove all four and the card**; the two
    round 1 kept (retention days, conversation gap minutes) were both time rules.
12. **Where do staff see the memory?** **Recommendation: inside the existing Chatbot card on
    the contact page**: "What the bot knows" (facts with source badges), "Recent
    conversations", and the live "Open orders". No new tab.
13. **Who gets a handover?** **Recommendation: a commercial ask (discount, credit, price
    exception) goes to the dealer's own salesperson by name; everything else, or no reachable
    salesperson, to the domain's team.**
14. **"An enterprise version of Claude Code".** The missing half is the bot DOING things
    (create a quote, raise a complaint, place an order after a confirmation), a different risk
    class. **Recommendation: open it as its own ideation issue; this plan builds the memory
    half only.**
15. **Console memory across conversations.** Console turns may write nothing outside the turn
    table (D14; two named exceptions exist). **Recommendation: a third named exception: a
    console turn may write a console-only episode row (never a fact).** Without it,
    cross-conversation memory is testable only in CI replay and in your hand pass.
16. **Malay and Chinese.** No reply text has language variants today and the escalation offer
    wording is matched by regex. **Recommendation: only the new memory lines get en / ms / zh
    now; the acknowledgement follows the dealer's language; translating the existing reports
    and canned text is its own lane.**
17. **One lane or two?** **Recommendation: two.** Lane A = S0 to S3 (memory reaches the
    parser; then a 3-weekday token and latency gate on production); lane B = S4 (what dealers
    read), started on A's measured numbers.
18. **Build the rarer pieces before measuring them?** Tallied "usual" products,
    self-statements and "what did I ask" questions are probably rare in today's 4,414 turns,
    because the bot cannot handle them. **Recommendation: build them (they are in your ask),
    and record today's counts from the 25 Sep dump in S2 as the baseline S4 is measured
    against.**
