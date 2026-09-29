# Chatbot memory lane A (S0 to S3): build contract

Companion to `PLAN-chatbot-memory-26sep.md` and `chatbot-memory-acceptance-criteria.md`.
This file is the Phase 1 API contract plus every ruling the build assumes on top of the plan
text. The round 3 mockups (`chatbot-memory-27sep-mockup-*.html`,
`chatbot-memory-27sep-illustrations.html`) are the screens; where the round 2 plan text and a
round 3 mockup disagree, the mockup wins (owner ruling 27 Sep 00:50 MYT: "final mockup to align").

Status: lane A built, 27 Sep 2026, main d8395cb8 merged in (fix lane merge round), PR #1304 ready for the orchestrator review. Track: full.

**Round 3 text supersedes parts of this file (merged 27 Sep).** As built after round 3: the level
values are `off | conversation | episodes | full` (`past` renamed `episodes`, label unchanged);
`resolve_level` is the one resolver and the `context` event records `level_source`; facts are
learned and saved at every level (the level decides what is READ, never what is WRITTEN), dry
runs never write the profile; the parser emits `profile_statements` (a list, at most 3); `about`
is cut to 120 chars; `respond_contacts.chatbot_recall_enabled` is dropped (check constraint on
`chatbot_memory_level`); the PUT body field is `memory_level`; the `queued` stage carries
`ticket` and `wait_ms` and Chat History rows carry `queue_ticket`; the memory cards live on a
contact Chatbot tab. AC-MEM037 (tier pick persisted from chat) is not built: it conflicts with
the owner's hand pass 10 ruling of 21 Sep 2026 (a fresh ask after a tier pick reopens the
roster), pinned by `test_rearch_r10_handpass10_replay.py`.

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
| `episodes` | Past conversations | L3 + L4: plus the last 3 episode summaries |
| `full` | Full memory | L3 + L4 + L5: plus the "About this contact" profile slice |

- System: `system_settings.chatbot_memory` JSONB is exactly
  `{"enabled": false, "default_level": "full"}`. `default_level` is never `off` and never
  null (the select has no clear). The four dead keys are removed by the S0 migration.
- Contact: `respond_contacts.chatbot_memory_level VARCHAR(16) NULL`. NULL = follow the system.
- Effective level: the contact's own level when set; else `default_level` when `enabled`; else
  `off`. One function: `app/services/chatbot/turn/memory.py::effective_level(contact_level,
  system_memory) -> str`.
- `chatbot_recall_enabled` is dropped by the S0 migration (round 3, AC-MEM054); the recall
  re-parse it gated is deleted, the PUT body rejects it and the FE no longer sends it.
- Facts are learned (tally, stated) and episodes are written at every level, Off included
  (round 3, AC-MEM049): the level decides what the parser READS, never what is WRITTEN. A
  statement is applied on every live arm (answer, casual, escalation), and one that is
  rejected is traced as `profile_statement_dropped` with its reason.

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
- Range, as built: the turns of this contact and side that are in no surviving frame's
  `turn_ids`, created before the resetting turn and not before the oldest surviving frame's
  `started_at`. Equivalent to the time cutoff on live data, and it keeps the backfill idempotent
  after a trim (a trimmed frame's turns are never re-derived).
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
| about | About | list of str, max 3 entries, each max 120, newest first (a staff save of one text replaces the list with that one entry) | stated, staff | text |
| note | Note | str, max 200 | staff | text |

- Precedence per key: staff > stated > crm > tallied. A stated write never replaces a staff
  entry; a tally never replaces a staff or stated entry.
- Staff delete of a learned or said fact: hard delete of the entry, and its values join the
  key's tombstone (`{"key": k, "source": "staff", "value": null, "removed": [...]}`). The
  tombstone blocks only a tally of the removed values: a tally may still learn other values,
  and a newer statement replaces it (owner call; the plan says a newer statement replaces).
  Whatever replaces a tombstone carries its `removed` list; deleting a tombstone again keeps
  it. Tombstones are never listed by the GET. Staff delete of a staff fact removes the entry
  and leaves no tombstone. DELETE of a CRM-only key (`customer`, `salesperson`) is 422.
- Every write is a single-key update under `SELECT ... FOR UPDATE` of the contact row, taken at
  write time. The whole-profile PUT (`PUT /{id}/chatbot`) and the generic `PUT /{id}` never
  write `facts`: one UPDATE keeps the stored facts as they are at write time.
- Facts never grant (AC-MEM036).

## 5. HTTP contract

All under `/api/v1/user-management/contacts`.

`GET /{id}` and `PUT /{id}/chatbot` responses gain `chatbot_memory_level: string | null` and
`chatbot_profile.facts` (both dict builders).

`PUT /{id}/chatbot` body gains `memory_level?: "off" | "conversation" | "episodes" |
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
"episodes" | "full"}` and 422s anything else; a partial body keeps the other stored key.
`level.system_default` in the memory GET is `off` while `enabled` is false.
`GET /` (the Contacts list) takes `chatbot_memory_level=own`: the contacts with their own
level, the Memory card's count link. `PUT /{id}` needs `user_management.contacts.edit`.
The fact PUT returns the memory GET body with `episodes: null` unless the caller also holds
`system.chat_history.view`, as the GET does. Each fact row carries `link` (the customer row
links to `/order-management/customers/{id}`, every other row `null`).

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
   the recall re-parse and the frame embedding enqueue in S3). Two effects the owner rules on
   with it (reviewer pass at d89110c0): no new frame is embedded, so
   `/external/memory/frames/search` (vector only) still answers but finds nothing new, and
   the backfill deletes the old placeholder frames, so it goes quiet; and the recall column
   drop cannot be undone for data (downgrade restores `false`). The dead pre-lane writer
   `memory.write_episode` is deleted.
2. Q15 console exception taken as recommended (section 3).
3. Level semantics of section 2 (which layers each level carries) are read off the round 3
   illustrations.
4. `about` (free text, stated or staff) is the reading of the Q6 ruling "anything a dealer says
   about themselves is remembered"; it is validated like `project` (newlines stripped, printed
   quoted, length capped).
5. (Superseded by round 3: facts are learned at every level.)
6. One schema migration for the lane (S0) carries every schema change, the contact level
   column and the usage-log turn id included; S3 adds one more migration that only publishes
   the new parser prompt version (label unmoved, the 487/513 precedent).
7. The static prompt ceiling is 37,153 est. tokens (bytes / 3), the coordinator's figure.
   Fix lane round 2 (reviewer pass at d89110c0, S3 and B3): that figure was measured on a
   rendering that appended the four growth addenda a second time (the constant already
   carries them). `tests/chatbot/test_parser_prompt_budget.py` now renders exactly what a
   published version is (`chatbot_rearch_s4._body`: the constant, then the policy blocks
   between their markers), where the same estimator reads: base 232182ae 29,901; lane at
   d89110c0 29,866; main 11bf373e 32,231 (its own `STOCK_TASK_ADDENDUM`); this lane merged
   over it 32,395, under 37,153. `CEILING` is back at 37,153.
   **Re-pinned 29 Sep 2026 (fix round 7):** main grew the prompt past 37,153 on its own.
   Same estimator, same rendering: main fd521c20 40,599 (+10,698 since 232182ae), moved by
   the PRs the owner merged since the 26 Sep ruling: #833 (specification addendum and the
   code-first rule), #1273 (top selling), #1323 (escalation confirmation). `CEILING` is now
   40,599, main's own measured prompt at fd521c20, and it bounds the prompt WITHOUT
   `MEMORY_ADDENDUM` (lane at 8371dbee: 40,420, the lane's body edits save 179). A second
   pin, `MEMORY_ADDENDUM_CEILING = 512`, bounds the addendum itself: 339 est. tokens at the
   26 Sep baseline (lane d89110c0), 512 after round 4 (baf4c813, 28 Sep: the history
   question in any wording, the number re-run, `commercial_request`). Pinning it back at 339
   needs a prompt cut, which is the owner's open decision on #1275. The published prompt with
   the addendum is 40,935 (fixture render) / 40,859 (fresh `blank_session` render), under
   40,599 + 512 = 41,111. Note that 512 is over AC-MEM066's own 400; that too waits on #1275.
   Second re-pin the same day: main bc75eb96 (#1353, issue #1352, "a pick never overrides
   the message's own domain") measures 41,163 (+564), so `CEILING` is 41,163; this lane
   merged over it measures 40,984 without the addendum and 41,499 with it (limit 41,675).
   Published text: `mem_0002_parser_memory` publishes `chatbot_rearch_s4._body(session)`
   (the constant plus the rendered policy blocks, the way s4 and s12 build production
   versions), memory addendum included, as the next `chatbot_semantic_parser` version with
   no label, and nothing when a version already carries that exact template; `production`
   is not moved (`tests/chatbot/test_mem_0002_publishes_rendered_prompt.py`).
   - Constant `SEMANTIC_PARSER_PROMPT`: sha256
     `2ed3cfea8ffe5905342f6e57d031c9e366075baf9286430e422ab1a6251f670a`, 92,105 chars.
   - Rendered template on a fresh `bootstrap_env` database (seeded blocks): sha256
     `ceeb4ccba2049990567845e7fd67fb2d07a3776606629a1428a1abedce52ff82`, 95,657 chars,
     32,395 est. tokens with the date filled in. On that database bootstrap's own s12 step
     already carries this text as v3, so `alembic downgrade merge_27sep_three_heads` then
     `upgrade head` logs "already published as v3; nothing to do". On a real database the
     blocks come from its own `chatbot_domains`, so the template sha is that database's and
     the constant sha is the stable one.
8. The 25 Sep prod dump is not on this VM: digest goldens are built from synthetic turn rows in
   the recorded trace shape; the prod-copy goldens, the backfill run and the Q18 counts are
   posted as orchestrator steps.
   Deploy: run `python scripts/backfill_chatbot_episodes.py` right after this deploy. A
   reset the live writer handles before it runs can close a contact's whole history as
   one episode; the backfill finds any frame holding a reset past its first turn, drops
   that contact's frames and rebuilds them from the turns (`frames_rebuilt` in its output),
   so running it late still repairs it. It cuts where the live writer cuts, never at a
   reset a human had the chat for. Episode outcomes and offers are read from the signals
   the engine writes (`looked_up` status, `missed`, `sections`; `plan.ask`, `plan.denied`;
   the `memory` record's open question), and day labels are on the Kuala Lumpur clock.
9. Migrations after the merge: main's three heads off `sales_0002_team_leader`
   (`ideation_confirm_prompts`, `prod_discontinued_at_flt`, `sa2_r9_open_question`) are
   joined on main itself by `merge_27sep_three_heads` (#1308, main 11bf373e). The lane's
   own no-op `mem_0000_merge_main` is deleted (fix lane round 2) and
   `mem_0001_frames_level` -> `mem_0002_parser_memory` hang off `merge_27sep_three_heads`,
   so `alembic heads` prints one head, `mem_0002_parser_memory`. No main migration is
   edited. The prod-copy up/down/up step downgrades to `merge_27sep_three_heads` (not
   `sales_0002_team_leader`, which would also revert main's three revisions).
   Merge round test run (cloud VM, `scripts/cloud-env-setup.sh`, `.env.ci-tests`, CI's
   commands): backend xdist loadfile 18,227 passed; SCM 4,109 passed; migration tests
   serial 400 passed; serial_ddl 2 passed; chatbot set (memory fixtures and the round 9
   stock ask fixtures included) 3,212 passed, 0 failed, after the two merge-broken pins were
   fixed.
   Not merge-related: 9 `test_dealer_kit_pdf_render.py` tests need a frontend print server
   on :3040 that this VM does not run, and `test_stock_debt_routes.py::test_row_carries_
   supplier_category_total` read rows leaked by the same run (52 of 52 pass on a fresh
   database).
10. Fix lane round 2 (reviewer pass at d89110c0, main 11bf373e merged), cloud VM,
    `scripts/cloud-env-setup.sh`, `.env.ci-tests`, CI's commands: backend xdist loadfile
    18,272 passed, 9 failed (all `test_dealer_kit_pdf_render.py`, which needs the :3040
    print server this VM does not run); migration tests serial 400 passed; serial_ddl
    passed; SCM with `DATABASE_URL` exported as CI does 4,109 passed, 1 failed
    (`test_stock_debt_routes.py::test_row_carries_supplier_category_total`, rows leaked by
    earlier runs, 52 of 52 on a fresh database); chatbot set plus the touched files 3,710
    passed, 0 failed; touched vitest 13 files 62 passed (touched directories 35 files 242
    passed); `tsc --noEmit` the same 73 errors as main, none new.

## 9. S4 build notes (fix lane round 4, 28 Sep 2026)

S4 was built on this PR after the owner's go ("yeah i want S4 for memory"). What the build
decided where the plan left room, so a reviewer can check it against sections 7 and 9 S4:

- **The clarifier contract.** The clarifier's system prompt is unchanged. The engine appends
  a `reply_format` instruction plus the memory slice and `first_name` to its user message
  (`lanes/fallback.clarifier_tail`), asking for `{"ack", "language"}`. A prompt version that
  still answers `{"response"}` is the whole reply, as before; only a history question uses
  it as the ack.
- **The history list.** The open conversation comes first (level "This conversation" and
  up), then the closed conversations (level "Past conversations" and up), newest first, up
  to 5. The owner's case needs the open one: after "check stock srtwc286" then "incoming", the
  incoming ask is still open, not a frame. Every line is a deterministic summary with no
  figure in it.
- **Kinds.** `history_question` (history), `unknown` (a message the bot cannot place: the
  customer's outstanding DOs or the order team, two numbered options, when the contact is
  linked to a customer), and everything else in `low_signal` (small talk: last time plus a
  re-run offer, or the usual products and site at Full, or the domain menu).
- **Live CRM, every level.** The customer and the salesperson are read live off the primary
  customer link, never memory, so they are named at every level. Plan 7.3 lists example 4
  as red under ablation; it is not, and its case says why.
- **Who a handover names.** The Q13 rule: the salesperson only for a commercial ask (the
  parser's new `intent_hint: "commercial_request"`), the lane's team otherwise. Example 10
  therefore names the team, not Aina. Routing, assignment, SLA and the comment's own lines
  are the lane's; the engine adds `Salesperson:` and `Conversation so far:` to the comment
  and swaps the "routed to the respective PIC" line for the salesperson line.
- **`escalation_declined` copy.** It keeps "Escalation declined." (19 recorded replay cases,
  4 engine pins and the node fixtures carry it, and the plan keeps existing copy untouched).
  AC-MEM084's switch to `offer_declined` is left for the owner.

## 10. Fix round 6: readable summaries (28 Sep 2026)

Owner hand test: "the structure of our summary is quite messy". Decisions:

- **Template, not a model call.** `episode_digest._summary` is a grammar-aware template:
  what the contact asked about (topics and codes by name), what they got, what is still
  open. It stays deterministic and replayable (AC-MEM029), never quotes a figure
  (AC-MEM021), and costs no tokens at episode close. No bracket tags, no semicolon
  chains, no date, no turn count. At most 200 chars, so the printed line fits 240.
- **One stored text, two readers.** The recall reply and the parser's L4 layer print
  `episode_line`: `Mon 28 Sep, Stock: <summary>` (the day and Topic from the frame's own
  columns). The Conversations card shows the same summary and the same Topic word
  (`topic` on each row); When and Turns stay columns.
- **Old stored summaries.** Every reader goes through `readable_summary`, which renders an
  old-shape summary from the frame's `domain`, `entities` and its old tags, so tags are
  never shown. `scripts/backfill_chatbot_episodes.py` (already the post-deploy step)
  rewrites them for good from each frame's own turns, console frames included
  (`summaries_rewritten=N`). No data migration: the digest is app code and a migration
  must not import it.
- **Budget.** Three maximum-length lines: L4 248 est. tokens (cap 250, nothing dropped),
  round 5 was 250. The worst-case assembler fixture is unchanged at 1,517.
