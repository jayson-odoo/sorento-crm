# Chatbot memory lane A (S0 to S3): build contract

Companion to `PLAN-chatbot-memory-26sep.md` and `chatbot-memory-acceptance-criteria.md`.
This file is the Phase 1 API contract plus every ruling the build assumes on top of the plan
text. The round 3 mockups (`chatbot-memory-27sep-mockup-*.html`,
`chatbot-memory-27sep-illustrations.html`) are the screens; where the round 2 plan text and a
round 3 mockup disagree, the mockup wins (owner ruling 27 Sep 00:50 MYT: "final mockup to align").

Status: lane A build, 27 Sep 2026. Track: full.

## 1. Rulings the build applies (binding, from PR #1284)

| ruling | applied as |
|---|---|
| Q1 memory OFF by default | system switch `chatbot_memory.enabled` defaults false; every contact's own level defaults NULL (follow the system); no migration turns anything on |
| Q2 topic switch only | an episode closes only on `topic_reset`; no time, no handover close |
| Q3 accepted | deterministic digest, no LLM, no figures |
| Q6 anything the dealer says about themselves | the parser's `profile_statement` may also carry the free-text key `about` (section 4) |
| Q7 count, not time | newest 20 frames per contact and side; tally over the last 10 |
| Q8 context level, system default + per-contact override | section 2 |
| Q10 accepted | lane B (S4) |
| Round 3 mockups | the Settings Memory card is rebuilt (not removed), the contact card's recall switch becomes the level select, language moves into the facts grid, the turn drawer gains Order, Memory and Context panels |

## 2. Context level

Four values, stored as these strings:

| value | label | layers fed to the parser |
|---|---|---|
| `off` | Off | none: the user block is today's (previous response, current subject, pending, options, and the settings `Profile:` line when it has a value) |
| `conversation` | This conversation | L3: earlier messages of the live episode |
| `past` | Past conversations | L3 + L4: plus the last 3 episode summaries |
| `full` | Full memory | L3 + L4 + L5: plus the "About this contact" profile slice |

- System: `system_settings.chatbot_memory` JSONB is exactly
  `{"enabled": false, "default_level": "full"}`. `default_level` is never `off` and never
  null (the select has no clear). The four dead keys are removed by the S0 migration.
- Contact: `respond_contacts.chatbot_memory_level VARCHAR(16) NULL`. NULL = follow the system.
- Effective level: the contact's own level when set; else `default_level` when `enabled`; else
  `off`. One function: `app/services/chatbot/turn/memory.py::effective_level(contact_level,
  system_memory) -> str`.
- `chatbot_recall_enabled` is no longer read by anything after S3 (the recall re-parse is
  deleted). The column stays, untouched (Q1: no data change); the PUT body stops accepting it
  and the FE stops sending it.
- Facts are learned (tally, stated) only when the effective level is not `off`. Episodes are
  written for every live contact whatever the level (staff see them).

## 3. Episodes (S0, S1)

- Migration adds `conversation_frames.is_test boolean not null default false`, index
  `ix_conversation_frames_contact_test_last (contact_respond_id, is_test, last_activity_at desc)`,
  unique index `uq_conversation_frames_contact_test_first_turn (contact_respond_id, is_test,
  (turn_ids[1]))`.
- `memory.write_episode_for_reset(db, *, contact_respond_id, is_test, resetting_turn_id) ->
  frame | None`: the range is this contact's `chatbot.turns` on the same `is_test` side created
  after the newest frame's `last_activity_at` (same contact and side), excluding the resetting
  turn, oldest first. Empty range writes nothing. The frame: `turn_ids` all of them,
  `last_activity_at` = last turn's `created_at` (naive UTC), `opened_at`/`started_at` = first
  turn's, `closed_at` = now (naive UTC), `close_reason = topic_switch`, `status = closed`,
  `is_test`, digest fields (S1). Insert `ON CONFLICT DO NOTHING`; then delete that contact and
  side's frames beyond the newest `KEEP_EPISODES = 20` (by `last_activity_at desc`), same
  transaction.
- D14 third exception (Q15 recommendation, assumed): a CONSOLE turn (`is_test` and ingress
  `console`) writes `is_test = true` frames and nothing else. Every other dry run (clone,
  replay, harness) writes no frame.
- No embedding is enqueued for a frame (S3 deletes the enqueue; S0 already stops calling it
  from the new writer).
- Contact delete removes the contact's frames by `contact_respond_id = respond_io_id`.

## 4. Profile facts (S2)

Stored in `respond_contacts.chatbot_profile.facts`, one entry per key:

```json
{"key": "usual_products", "value": ["SRTWB1455"], "source": "tallied",
 "source_ref": "<frame id>", "first_seen": "2026-09-02", "last_seen": "2026-09-25",
 "seen_count": 4, "set_by": null, "removed": []}
```

| key | label | value | sources | staff value input |
|---|---|---|---|---|
| customer | Customer | str | crm (live) | read-only |
| segment | Segment | str | crm (live), staff | SearchableSelect: dealer, project, end user |
| salesperson | Salesperson | str | crm (live) | read-only |
| language | Language | `en`, `ms`, `zh` | stated, staff | SearchableSelect |
| role | Role | `purchaser`, `owner`, `sales`, `site_supervisor`, `other` | stated, staff | SearchableSelect |
| usual_products | Usual products | list of product codes, max 3 | tallied, staff | SearchableMultiSelect (server search) |
| usual_brands | Usual brands | list of brand names, max 3 | tallied, stated, staff | SearchableMultiSelect |
| usual_sites | Usual sites | list of warehouse names, max 3 | tallied, stated, staff | SearchableMultiSelect |
| project | Project | str, max 60, newlines stripped | stated, staff | text |
| about | About | list of str, max 3 entries, each max 200, newest first (a staff save of one text replaces the list with that one entry) | stated, staff | text |
| note | Note | str, max 200 | staff | text |

- Precedence per key: staff > stated > crm > tallied. A stated write never replaces a staff
  entry; a tally never replaces a staff or stated entry.
- Staff delete of a learned or said fact: hard delete of the entry, and its values join the
  key's tombstone (`{"key": k, "source": "staff", "value": null, "removed": [...]}`); the tally
  skips removed values. Staff delete of a staff fact removes the entry and leaves no tombstone.
- Every write is a single-key update under `SELECT ... FOR UPDATE` of the contact row, taken at
  write time. The whole-profile PUT preserves `facts`.
- Facts never grant (AC-MEM036).

## 5. HTTP contract

All under `/api/v1/user-management/contacts`.

`GET /{id}` and `PUT /{id}/chatbot` responses gain `chatbot_memory_level: string | null` and
`chatbot_profile.facts` (both dict builders).

`PUT /{id}/chatbot` body gains `chatbot_memory_level?: "off" | "conversation" | "past" |
"full" | null` (present and null = follow the system default; absent = leave alone). The body
drops `chatbot_recall_enabled`. `chatbot_profile` in the body never touches `facts`.

`GET /{id}/chatbot/memory` (`user_management.contacts.view`):

```json
{
  "level": {"own": "full" | null, "effective": "full", "system_default": "off"},
  "facts": [{"key": "customer", "label": "Customer", "value": "Chin Chun Trading (CC001)",
             "display": "Chin Chun Trading (CC001)",
             "source": "crm", "last_seen": null, "editable": false,
             "link": "/order-management/customers/<id>"}, ...],
  "vocabulary": [{"key": "role", "label": "Role", "kind": "choice" | "multi" | "text",
                  "options": [{"value": "purchaser", "label": "Purchaser"}] | null,
                  "max_length": 200 | null}, ...],
  "episodes": {"kept": 14, "limit": 20,
               "current": {"turn_count": 2, "first_turn_id": "...", "started_at": "...",
                           "summary": "stock SRTWB1455; and in kuching?", "domains": ["stock"]} | null,
               "rows": [{"id": "...", "date": "2026-09-25T02:10:00", "domains": ["stock"],
                         "summary": "...", "turn_count": 5, "close_reason": "topic_switch",
                         "first_turn_id": "..."}]},
  "open_orders": {"customer_name": "Chin Chun Trading" | null,
                  "rows": [{"document": "SO-2409-0112", "kind": "sales_order", "status": "Confirmed",
                            "summary": "3 lines", "date": "2026-09-18", "href": "/..."}]}
}
```

A fact's `value` is the stored raw value (`"ms"`, `["SRTWB1455"]`); `display` is the label the
grid prints (`"Malay"`, `"SRTWB1455, M486-75-BL"`). `episodes.rows` is the newest 10. `open_orders.rows` the newest 5 open sales orders of the
primary linked customer. Facts are ordered by the vocabulary order.

`PUT /{id}/chatbot/facts/{key}` (`user_management.contacts.edit`), body `{"value": str | [str]}`:
sets a staff fact; 422 on an unknown key, a CRM-only key, a value outside its choices, or over
its length/count limit. Returns the memory GET body.

`DELETE /{id}/chatbot/facts/{key}` (`user_management.contacts.edit`): hard delete through the
deferred-action path (the FE fires it when the countdown lapses; the same server-deferred
mechanism every other delete uses). 204.

`GET /api/v1/user-management/settings` carries `chatbot_memory: {"enabled", "default_level",
"own_level_count"}`; `PUT` accepts `{"enabled"?: bool, "default_level"?: "conversation" |
"past" | "full"}` and 422s anything else.

## 6. Trace (S0, S3)

- `understood.facts` gains `prompt_tokens`, `completion_tokens` (provider numbers).
- `queue` event (S7 mode only): `{"ticket": n, "waited_ms": ms}`.
- `memory` event: `{"level": {"own", "effective"}, "focus": {before, after, writer},
  "profile": {"before": {facts_count, tier, language}, "after": {...}, "writer"},
  "episodes": {"read": [frame ids fed to the parser], "written": {"id", "turn_count",
  "close_reason", "summary"} | null, "writer": "tail"}, "facts_saved": [{"key", "source"}],
  "open_question": {...}, "written", "dry_run"}`.
- `context` event (S3): `{"level", "layers": [{"layer", "est_tokens", "cap", "dropped"}],
  "total_est_tokens", "cap": 1800}`.
- `trace_detail` returns `memory`, `context` and `order` (`{"ticket", "waited_ms",
  "previous": {"turn_id", "created_at", "message"} | null, "next": {...} | null}`) exactly as
  above; the FE types follow the backend.

## 7. Usage log

`ai_assistant_usage_logs.chatbot_turn_id VARCHAR(64) NULL` (S0 migration), written for every
chatbot parser row.

## 8. Rulings assumed (the owner rules in the morning)

1. Q5 ("why we delete?") is still a question: the build takes the plan recommendation (delete
   the recall re-parse and the frame embedding enqueue in S3).
2. Q15 console exception taken as recommended (section 3).
3. Level semantics of section 2 (which layers each level carries) are read off the round 3
   illustrations.
4. `about` (free text, stated or staff) is the reading of the Q6 ruling "anything a dealer says
   about themselves is remembered"; it is validated like `project` (newlines stripped, printed
   quoted, length capped).
5. Facts are learned only at a level other than `off`.
6. One schema migration for the lane (S0) carries every schema change, the contact level
   column and the usage-log turn id included; S3 adds one more migration that only publishes
   the new parser prompt version (label unmoved, the 487/513 precedent).
7. The 25 Sep prod dump is not on this VM: digest goldens are built from synthetic turn rows in
   the recorded trace shape; the prod-copy goldens, the backfill run and the Q18 counts are
   posted as orchestrator steps.
