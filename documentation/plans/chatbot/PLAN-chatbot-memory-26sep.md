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
