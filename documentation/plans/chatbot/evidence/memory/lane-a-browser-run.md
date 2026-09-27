# Chatbot memory lane A - end-of-lane browser verification (issue #1282)

Branch `claude/chatbot-memory-lane-a-t9sdo2` at HEAD (started at `ca672668`). Backend :8000
(uvicorn --reload, `.env.dev-stack`, `postgresql://sorento:sorento@localhost:5432/sorento_dev`,
`alembic current` = `mem_0002_parser_memory (head)`). Frontend dev :3000. agent-browser session
`lane-a-final`, headless Chrome via the repo's wrapper. Servers were not started or stopped by
this run.

## Seed data

- Customer "Chin Chun Trading" (code `CC001`), company_id
  `00000000-0000-0000-0000-000000000001`, market segment `WHOLESALE` (seeded, none existed),
  sales agent `TAN KOK WAI` (seeded, `sales_agents` was empty), one open sales order
  `SO-CC001-0001`.
- `respond_contact_customers` primary link, contact `e6aa5130-f012-4482-a1e1-15c428b77d88`
  (`respond_io_id='lane-a-demo-1'`) -> the new customer.
- `respond_contact_companies` row linking the contact to the default company - required so
  `resolve_contact_company_scope` (called inside `run_turn` before the stages) does not fail
  closed to an empty scope and hide the seeded Customer/SalesOrder rows from the engine's own
  reads. `default_space_id` was stubbed to a fixed string for the same reason (no
  `respond_workspaces` row exists in this dev DB).
- `respond_contacts.chatbot_memory_level = 'full'` for the contact.
- A blank `system_settings` singleton row - **did not exist in this dev DB at all**, which made
  `GET /api/v1/user-management/settings` return `{"settings": null, "roles": [...]}` and the
  Memory card render every field at its client-side fallback (own-level count showing 0 contacts
  instead of 1). Seeded one bare `SystemSetting()` row; not a lane defect, a dev-stack setup gap.

## Engine seam and how it was bridged

Ran `app.services.chatbot.engine.run_turn` LIVE (`offload=False`, envelope not `is_test`, so
`dry_run=False`) five times, monkeypatching in a standalone script (not pytest) the same seams
`tests/chatbot/conftest.py` / `test_engine.py` use:
- `app.services.chatbot.head.parser.resolve_config` / `.parse` - fixed parser output per turn.
- `app.services.chatbot.engine.check_access` - always allow, agent `General Enquiries`.
- `app.services.chatbot.engine.default_space_id` - fixed string (see above).
- `app.services.chatbot.lanes.casual.resolve_clarifier_config` / `.call_clarifier` - stub,
  never reached in these 5 turns.
- `app.services.ai_assistant_service.MCPRuntimeClient.call_tool` - raises, so nothing left the
  box; every turn's stock/order lookup consequently failed inside the lane (caught, turn still
  closes `status=done`/`stage=sent`) with a "Couldn't find..." reply. This does not affect the
  memory feature under test (focus/episode/fact writes happen before the fetch).

Turns: 1) stock `SRTWB1455`, 2) "and in kuching?" (continuation, same topic), 3) `topic_reset`
to `order` for `CC001` (closes episode 1, `inventory`), 4) `profile_statement`
`{key: role, value: purchaser}`, 5) `topic_reset` back to `inventory`/`SRTWB1455` (closes
episode 2, `order`). `created_at` on each `chatbot.turns` row was bumped by `UPDATE` after the
run so times/order read sensibly; `conversation_frames.closed_at` was similarly aligned to the
resetting turn's time (it defaults to real wall-clock at write time, which was seconds after the
whole batch ran).

**Seam gap #1 (reported, not fixed here):** `System > Messaging > Chat History` reads
`chat_histories`, a table populated by n8n's own WhatsApp webhook flow, not by
`engine.run_turn` (D9: "the CRM never sends on the turn path"). A live `run_turn` call from a
script writes `chatbot.turns` only, so the Chat History list showed nothing for this contact.
Seeded 5 matching `chat_histories` rows directly (`turn_id` = the real `chatbot.turns.id`,
`message_id` = the envelope's `messageId`, `type='incoming'`, `sent_at` = the turn's
`created_at`) - the shape `ChatTranscript.tsx` requires (`m.turn_id` gates whether a message
opens the drawer) and what `GET /api/v1/system/chatbot/turns/{turn_id}` reads by.

## Click log

1. Opened `http://localhost:3000`, logged in as `E2E_EMAIL` (superadmin), viewport 1280x900.
2. Sidebar: Users & Access > Settings > Chatbot tab.
3. Toggled "Memory for all contacts" on, changed "Default context level" to "Past
   conversations", clicked Save (`find role button click --name Save`) -> `POST
   /api/v1/user-management/settings/general` 200, reload confirmed `chatbot_memory:
   {enabled: true, default_level: "past", own_level_count: 1}` persisted.
4. Restored: switch off, level back to "Full memory", Save, reload confirmed restored.
5. Sidebar: Users & Access > People > Internal Users > row "Tan Wei Liang" > Access tab.
6. Read "What the bot knows": Customer/Segment/Salesperson (CRM, live) + Role (Said, dated).
   Read "Conversations": "2 kept of 20", current open row ("Now", 1 turn, Open), two closed
   episode rows (order/CC001, inventory/SRTWB1455, both "Topic switch"). Read "Open orders":
   `SO-CC001-0001`, Open.
7. Add fact modal: opened via "Add", selected key "Note" (see FAIL below), typed a value,
   Save -> row appeared. Clicked "Edit Note", changed the text in place, Save -> updated.
   Clicked "Delete Note" -> row became an inline countdown + Cancel (no dialog); let it lapse
   (10 s, matches `system_settings.deferred_delete_seconds`); reloaded and confirmed the fact
   row and the `chatbot_profile.facts` DB entry were both gone (`sla_form_actions` row
   `status='committed'`, `commit_at` - `created_at` = 10s). Added a second note, clicked
   Delete, clicked Cancel before the window lapsed -> row restored to Edit/Delete, toast
   "Cancelled. Nothing was applied.", confirmed still present in the DB after reload.
8. Viewport 375x800 on the same Access tab: `document.documentElement.scrollWidth` ==
   `clientWidth` (no horizontal page scroll; the two DataGrid tables scroll internally).
   Reopened Add-fact modal: Save button reachable with no page scroll.
9. Sidebar: System > Messaging > Chat History. Filtered by contact name; found the 5 seeded
   rows (see seam gap #1). Clicked the "never mind, what's the status of my order CC001?" row
   -> opened the per-contact thread dialog -> "Open full trace" on that turn (`#7fcc`, turn 3)
   -> `TurnDetailDrawer`. Expanded Order / Stages / Memory / "Context sent to the AI" panels
   (Memory and Context panels only opened via keyboard, see FAIL below).
10. Repeated for turn 4 (`#8ad8`, the `profile_statement` turn) to check "Facts saved".
11. Viewport 375x800: reopened the drawer, confirmed `scrollWidth == clientWidth` (no
    horizontal scroll) and the Memory/Context panels fully readable without page scroll.
12. Checked `console`/`errors` (agent-browser) and `/tmp/claude-0/be.log` / `fe.log` throughout;
    no unhandled exceptions or 5xx responses for any of this run's own requests.

## PASS / FAIL

**1. Settings > Chatbot Memory card**
- PASS - switch present, default level `SearchableSelect` with exactly 3 options (This
  conversation / Past conversations / Full memory) and an accessible name ("Default context
  level" reads correctly via the accessibility tree).
- PASS - own-level count showed "1 contact" (singular, correct pluralization) once a
  `system_settings` row existed (see seed-data note above - the dev DB had none at all).
- PASS - retention lines present: "Conversations kept: Newest 20 per contact", "Facts kept:
  Until replaced, removed by staff, or the contact is deleted".
- PASS - toggle on/off + level change persisted through Save and a full page reload, then
  restored to (enabled off, default full) and reload-confirmed.

**2. Contact > Access tab**
- PASS - "Chatbot settings" > "Memory context level" select shows "Full memory" (own level),
  with "Own level - system default: Full memory" caption.
- PASS - "What the bot knows" shows the CRM rows live (Customer -> "Chin Chun Trading
  (CC001)", Segment -> "WHOLESALE", Salesperson -> "TAN KOK WAI", all badge "CRM" / "live" /
  read-only except Segment which is staff-editable), the Said Role -> "Purchaser" (badge
  "Said", dated), and after the note test a Learned-shaped Staff row (badge "Staff").
  No genuinely "Learned" (tallied) row was exercised - only 2 closed episodes were seeded and
  tally needs more than that to surface a row; not a defect, just untested by this run.
- FAIL - **Add fact modal: selecting a key from the `SearchableSelect` dropdown by MOUSE CLICK
  closes the entire "Add fact" dialog instead of selecting the option** (reproduced 3 times).
  Keyboard selection (ArrowDown + Enter) works correctly and reveals the value field. This is a
  real interaction defect for anyone driving the mouse, not just the browser harness - worth a
  fix-round item.
- PASS - once a key is picked, Save/Edit-in-place/Delete-with-countdown all work: the Delete
  action becomes a 10 s countdown with a Cancel button and a `role="timer"` element, no
  `confirm()`/dialog; letting it lapse commits the delete (DB-verified, `sla_form_actions.status
  = 'committed'`, 10 s window matching `deferred_delete_seconds`); Cancel restores the row and
  the fact survives in the DB.
- PASS - Conversations card: "2 kept of 20", the two closed episodes with their summaries
  ("... 2 turns: inventory SRTWB1455 (answered)." / "... 2 turns: order CC001 (answered)."),
  the open "Now" row (1 turn, "Open"). A row click opens Chat History filtered to that thread
  (only verified indirectly - see item 9 in the click log, reached the same thread another way).
- PASS - Open orders: `SO-CC001-0001`, Open, dated.
- PASS at 375px - no page-level horizontal scroll (`scrollWidth == clientWidth`); both grids
  scroll internally; the Add-fact modal's Save button is reachable with no page scroll.

**3. Chat History > a memory turn's drawer**
- Reached only after seeding `chat_histories` rows directly - see "seam gap #1" above; reporting
  as instructed rather than treating the empty list as a UI defect.
- Order panel: "Not recorded on this turn." - correct, S7 ticket mode is off in this run.
- PASS - Memory panel: "Context level: full [own level]" badge; "Conversation closed" shows the
  correct summary on both reset turns (turn 3 closes the `inventory` episode, turn 5 the
  `order` episode); "Facts saved: role (stated)" on turn 4, "none this turn" elsewhere.
- FAIL (display gap, not a crash) - **"Current subject" always reads "Not recorded on this
  turn."**, even on turns where the focus clearly has a subject (turn 3's `focus.after.domains
  = ["order"]`, `customers = [CC001]`). Root cause read in
  `TurnDetailDrawer.tsx::currentSubjectText`: it only joins plain string/number values off
  `memory.focus.after`, but every real field the engine writes there (`domains`, `products`,
  `customers`, etc.) is an array of entity objects, so the filter always empties out and the
  function always returns `null`. The function's own docstring already flags the shape as
  unfixed ("The backend has not fixed a shape for it"); as written it can never show a subject
  for a real turn.
- PASS - "Context sent to the AI": five progress bars (33/150, 0/250, 100/450, 46/350, 24/600)
  and "Total memory + message: 203/1800", "Dropped: nothing" - matches the `context` trace
  event captured in the DB (`cap: 1800`, `total_est_tokens: 203`).
- FAIL (labelling gap) - the two innermost layers render as raw `L2`/`L1` instead of a friendly
  name; `LAYER_LABELS` in `TurnDetailDrawer.tsx` maps `L3`/`L4`/`L5` to "This conversation" /
  "Past conversations" / "About this contact" plus `current_subject`/`current_message`, but the
  trace's own layer identifiers are `L1`/`L2`, which are never in that map.
- PASS - "Understood" stage (inside "Stages"): `prompt tokens: 0`, `completion tokens: 0`,
  `tokens: 0` - the stub parser returns no usage data, so this is the expected "the stub gives
  none" case, not a defect.
- FAIL (interaction defect, same class as the Add-fact one above) - **clicking the "Memory" or
  "Context sent to the AI" accordion header with the MOUSE closes the entire drawer** back to
  the underlying thread dialog, reproduced twice. Keyboard activation (Tab/focus + Enter) works
  and expands the section correctly; this is the workaround used throughout this run.
- PASS at 375px - drawer scrollWidth == clientWidth (no horizontal scroll), Memory/Context
  panels fully readable, no page-level overflow.

**4. Console / logs**
- PASS - no unhandled JS errors in the browser console for this run's own actions (one
  pre-existing, unrelated React "key" prop warning on `Demo1Layout` seen throughout, not
  introduced by this lane). No 4xx/5xx in `be.log` or `fe.log` for requests this run made.
  One transient episode mid-run: a page reload hung in a stuck loading-skeleton state and a
  subsequent `open` timed out on `Page.navigate`; `be.log`/`fe.log` showed heavy concurrent
  traffic (compiles, other requests) and `uptime`/`ps` showed three unrelated CPU-bound python
  processes at ~74% each - consistent with another agent on the shared machine, not a defect in
  this lane. Closing and reopening a fresh `agent-browser` session recovered immediately with
  the same data rendering correctly, which is why this is not carried as a FAIL.

## Summary

PASS: Settings memory card (switch, 3-option select, own-level count, retention lines, persist
+ restore); Contact Access tab memory level, What-the-bot-knows CRM+Said rows, Delete
countdown/Cancel/lapse semantics (10 s, no dialog), Conversations card, Open orders, 375px
layout; Chat History drawer Order/Memory(mostly)/Context/Understood panels, 375px layout.

FAIL (defects to fix, not blocking data correctness): (a) Add-fact key `SearchableSelect`
closes the whole dialog on a mouse click of an option (keyboard-only workaround exists);
(b) the drawer's accordion section headers (at least Memory, Context sent to the AI) close the
whole drawer on a mouse click (same class of bug, keyboard-only workaround exists);
(c) "Current subject" in the Memory panel can never render for a real turn given the actual
`focus.after` shape; (d) `L1`/`L2` context layers show raw codes instead of friendly labels.

Seam reported per the brief: Chat History is backed by `chat_histories` (n8n-written), not by
`chatbot.turns` directly - bridged with seeded rows, `turn_id` = the real `chatbot.turns.id`.

## Recheck (26 Sep 2026, HEAD 040650be, fix commit for this round)

Short recheck of the fix commit `040650be` ("memory UI round, select inside the add fact modal,
drawer section headers, current subject, layer labels"), which touches
`components/ui/dialog.tsx`, `components/ui/sheet.tsx`,
`components/common/floatingAncestry.ts` (new shared `guardFloatingOutsideInteraction`, and the
`FLOATING_SURFACE_SELECTOR` now also matches `[data-slot="sheet-content"]`), and
`TurnDetailDrawer.tsx` (`currentSubjectText`, `CONTEXT_LAYER_LABEL`). Same dev DB/servers as the
original run (backend :8000 `--reload` on `.env.dev-stack`, frontend :3000 dev, seeded contact
"Chin Chun Trading" / Tan Wei Liang / turns `#4748 #2400 #7fcc #8ad8 #aa6d` all still present).
New isolated agent-browser session `lane-a-recheck` (via `--session lane-a-recheck`, overriding
the wrapper's hardcoded `--session lane-a` - confirmed isolated: `get url` on open showed
`about:blank`, then a fresh `/signin` redirect, no carried-over auth from any other session).
Logged in as `E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`. Navigated by sidebar clicks from `/`
both times (Users & Access > People > Internal Users > Tan > Access tab; System > Messaging >
Chat History), never a deep URL. Hid the Next dev portal badge for this session only via
`eval` on `nextjs-portal` display. Closed only this session at the end (not `--all`).

### Item 1 - Add fact modal, key `SearchableSelect`

| Viewport | `click @ref` (scrollintoview + fresh snapshot first) | Real pointer click (mouse move/down/up at `get box` center) |
|---|---|---|
| 1280x900 | PASS - modal stayed open, combobox showed "Note", value textbox appeared | PASS - modal stayed open, combobox showed "Role", a second value `SearchableSelect` appeared |
| 375x800 | PASS - same, combobox showed "Note" | PASS - same, combobox showed "Role" |

Comparison control: **Administrative Users > Add user > "Copy roles from another user"**
`SearchableSelect` (pre-existing, unrelated to the chatbot memory feature) - real pointer click
on its one populated option ("Lane A Admin") also kept the "Add User" dialog open and applied the
copied roles (Super Admin checkbox flipped true, "Add user" button went from disabled to
enabled). Same pass/fail shape as the fixed Add-fact modal, i.e. nothing regressed elsewhere.
No console errors or unhandled exceptions during any of this item's interactions.

**Verdict: item 1 is fixed.** Both click methods select the option and keep the dialog open at
both viewports.

### Item 2 - Chat History turn drawer, "Memory" / "Context sent to the AI" headers

Reopened `Turn #7fcc`'s drawer (topic_reset to `order`, same turn used in the original run) via
Chat History > row > thread dialog > "Open full trace".

| Viewport | `click @ref` (scrollintoview + fresh snapshot first) | Real pointer click |
|---|---|---|
| 1280x900 Memory | PASS - drawer stayed open, header toggled `expanded=true` | PASS |
| 1280x900 Context | PASS | PASS |
| 375x800 Memory | PASS | PASS |
| 375x800 Context | PASS | PASS |

Comparison control: the drawer's own pre-existing **"Stages"** header (already expanded by
default, so it was never exercised by a click in the original run) toggled correctly both ways
at 1280px, drawer never closed.

**One methodology note, not a product defect:** two `click @ref` attempts on `Memory` failed
closed the whole drawer during this recheck - one on a re-used ref number from an earlier,
separate `snapshot` call (refs are only valid immediately after the snapshot that produced them,
not across later tool calls), and one where `scrollintoview` was skipped before the click on a
header that was below the fold. Both were this recheck's own harness error, not the app's:
repeating the exact same click with a snapshot taken immediately before it (and `scrollintoview`
first) passed cleanly and repeatably afterward, including on the untouched "Stages" control,
which showed the identical failure mode under the identical bad methodology. Recorded here
because it explains why a mouse-driven manual repro could occasionally still see a false
"closes the drawer" - a real mouse can also miss an off-screen target - but it is not evidence
against the fix itself: every clean attempt (fresh snapshot, element scrolled into view, or a
real pointer click at measured on-screen coordinates) passed at both viewports.

**Verdict: item 2 is fixed.** Confirmed at both viewports with both click methods once the
target was actually on-screen; the one class of failure seen is a stale-ref/off-screen-click
harness artifact reproducible identically on an untouched control, not a lane defect.

## Round 3 (27 Sep 2026, HEAD 2a02bd95)

Branch `claude/chatbot-memory-lane-a-t9sdo2` at HEAD `2a02bd95` ("test(chatbot): new contact
default resolves to off, recall column dropped (round 3) [skip ci]"), on top of round 3's coder
commit `3e1b95e7` ("feat(chatbot): memory round 3, context level values, facts at every level,
statements list, recall column dropped, queue ticket and Chatbot tab"). Same dev stack as the
earlier rounds: backend :8000 (`uvicorn --reload`, `.env.dev-stack`,
`postgresql://sorento:sorento@localhost:5432/sorento_dev`), frontend :3000 dev (Turbopack,
already running, not started or stopped by this run). agent-browser session `lane-a-r3`
(`--session lane-a-r3`), driven with an explicit `--executable-path` pointing at the machine's
Playwright-cached Chromium (`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`) because the
daemon's own Chrome auto-detect failed on this box; once the daemon picked it up on first `open`,
every later command that also failed auto-detect on its own (a per-invocation `npx` quirk, not a
daemon issue) still worked against the same running daemon and the explicit path made this
consistent. Logged in as `E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`. Closed only this session
(not `--all`) at the end.

### Dev DB schema check (per the brief)

Before touching the browser, checked the hand-edited dev DB directly:

- `respond_contacts`: `chatbot_recall_enabled` column is gone (not in `\d respond_contacts`);
  `ck_respond_contacts_chatbot_memory_level` now allows only
  `off | conversation | episodes | full` (the value is `episodes`, not `past`).
- Tan's own row (`e6aa5130-f012-4482-a1e1-15c428b77d88`) already had
  `chatbot_memory_level = 'full'` - no `'past'` leftover, no update needed.
- `system_settings.chatbot_memory` already read `{"enabled": false, "default_level": "full"}` -
  no `'past'` leftover, no update needed. (The jsonb shape itself simplified since round 1's
  seed note above, which listed `recall_default`/`profile_fields`/etc. - consistent with "recall
  column dropped" in this round's commits.)

No psql fix was required; both places already held the new-vocabulary default (`full`), not the
old `past`.

### Click log

1. Sidebar Users & Access > People > Internal Users > row "Tan Wei Liang" (contact
   `e6aa5130-f012-4482-a1e1-15c428b77d88`, the same seeded contact as rounds 1-2) at 1280x900.
2. Tab strip now reads Profile / Access / Routing / Chat / **Chatbot** (5 tabs, was 4 pre-round-3).
   Clicked "Chatbot" -> route `/user-management/contacts/{id}/chatbot`. Confirmed "Access" tab no
   longer renders the memory cards at all - it now shows only Media Access / Access Agents / Field
   reveals.
3. On the Chatbot tab: "Chatbot settings" (memory level `SearchableSelect`, a second "answered on
   the next pick" combobox, Stock checks / Notify salesman / Packing list allowed switches),
   "What the bot knows" (Add button + grid: Customer/Segment/Salesperson CRM rows, Role Said row,
   and a leftover "Note" row from round 2's own DB state, `"Cancel-delete test note"`),
   "Conversations" (2 kept, current "Now" row + 2 closed episodes), "Open orders"
   (`SO-CC001-0001`) - all present on one tab, matching the brief.
4. Opened the level select: 4 options `Off / This conversation / Past conversations / Full
   memory` (own-level select includes Off; the select's own listbox briefly renders "Off" as the
   `option[selected]` on open - a keyboard-highlight default, not the field's real value, which
   the combobox itself already showed as "Full memory" both before and after opening it).
   Selected "Past conversations" -> `PUT .../chatbot` 200, auto-saved (no separate Save button on
   this control). Clicked "Clear selection" -> field reads "(follow the system default)" -> a
   second `PUT .../chatbot` 200. Reloaded -> still "(follow the system default)", confirmed
   persisted. Reselected "Full memory" -> `PUT` 200, confirmed by re-reading the combobox text.
5. Add fact: clicked "Add" -> "Add fact" dialog. **First attempt without `scrollintoview` on the
   option closed the whole dialog** (reproduced the exact harness artifact the round-2 recheck
   already diagnosed and named - a `click @ref` on an option below the fold without
   `scrollintoview` first). Redid it properly (scrollintoview before every click: the "Add"
   button, the key combobox, and the "Note" option each individually) -> dialog stayed open,
   combobox showed "Note", value textbox appeared. This is not a fresh defect - it is the same
   stale-ref/off-screen-click harness failure mode the round-2 recheck already reproduced and
   attributed to methodology, not the app; a fresh snapshot + `scrollintoview` immediately before
   the click passed cleanly every time after.
6. Typed "Round 3 recheck note", clicked Save -> `PUT .../chatbot/facts/note` 200. The grid then
   showed exactly ONE "Note" row reading "Round 3 recheck note" (it replaced the round-2 leftover
   "Cancel-delete test note" rather than adding a second row) - `note` is a single-value fact key,
   not a list, so this is correct behaviour, not a bug.
7. Clicked "Delete Note" -> inline `role="timer"` countdown ("Deleting in 6s") + Cancel button, no
   `confirm()`/dialog. Let it lapse; DB-verified afterward
   (`sla_form_actions.source_entity_type='contact_chatbot_fact'`,
   `source_entity_id='e6aa...:note'`, `status='committed'`, `commit_at - created_at` = 10s).
   Reloaded -> the Note row is gone.
8. Viewport 375x800 on the Chatbot tab: `document.documentElement.scrollWidth` ==
   `clientWidth` (360 == 360, no page-level horizontal scroll); all 5 tabs (Profile / Access /
   Routing / Chat / Chatbot) render in the tablist with no overflow.
9. Sidebar Users & Access > Settings > Chatbot tab (1280x900 again): "Memory" card, "Default
   context level" `SearchableSelect` with exactly 3 options (This conversation / Past
   conversations / Full memory - no "Off", matching the brief; "Off" only appears on the
   per-contact select). Selected "Past conversations", clicked Save -> `POST
   .../settings/general` 200, reloaded -> still "Past conversations", confirmed persisted.
   Reselected "Full memory", Save -> `POST` 200, reloaded -> confirmed restored to "Full memory".
10. Sidebar System > Messaging > Chat History (had to `eval`-hide a `nextjs-portal` dev-tools
    badge sitting at the bottom-left of the viewport first - it was intercepting the click on the
    "System" sidebar group heading itself, which sits near the bottom of the expanded menu at
    1280x900; a `document.elementFromPoint` check on the click coordinates confirmed the portal
    element, not the app, was eating the click. Hid it for this session only via `eval`, same
    workaround the round-2 recheck used). Column list: Time / Contact / Direction / **Queue** /
    Message / Latency / Delivery. All 5 seeded rows for this contact showed "-" in the Queue
    column - matches the brief's expectation exactly (S7 ticket mode was off when these turns
    were seeded, so there is no ticket number to show).
11. Clicked the "never mind, what's the status of my order CC001?" row -> per-contact thread
    dialog (5 turns `#4748 #2400 #7fcc #8ad8 #aa6d`) -> "Open full trace" on `#7fcc` (the same
    `order` topic-reset turn used in the round-2 recheck) -> `TurnDetailDrawer`. Expanded "Memory"
    then "Context sent to the AI" with `scrollintoview` before each click - both opened in place,
    drawer never closed (the round-2 fix for the accordion-closes-drawer bug still holds).
12. Read the Memory panel: "Context level: full [own level]" (a level-source annotation is
    present); "Current subject: domain order; customer CC001" (renders real data, the round-2 fix
    for this holds); "Conversation closed: Sat 26 Sep, 2 turns: inventory SRTWB1455 (answered).";
    "Facts saved: none this turn" (correct - turn 3 is the topic reset, not the `profile_statement`
    turn `#8ad8`).
13. Read "Context sent to the AI": "About this contact" 33/150, "Past conversations" 0/250, "This
    conversation" 100/450, "Current subject and open question" 46/350, "Current message" 24/600,
    "Total memory + message" 203/1800, "Dropped: nothing" - friendly labels throughout, no raw
    `L1`/`L2` codes (the round-2 fix for this holds too).
14. Viewport 375x800 on the drawer: `scrollWidth == clientWidth` (375 == 375), no page-level
    horizontal scroll.
15. `console`/`errors` (agent-browser) throughout: one pre-existing "key" prop warning on
    `Demo1Layout`, unrelated to this lane and seen in every prior round's evidence too; no other
    unhandled exceptions. `network requests --filter /api/v1/` showed only 200s for every request
    this run made (chatbot/memory GET/PUT, settings GET/POST, chatbot/turns GET). `be.log` had no
    4xx/5xx in this run's window. `fe.log` had one small burst of `[Error: socket hang up]
    ECONNRESET` proxy failures (3 pairs, `notifications/unread-count` and
    `master-data/products/select`) during the very first `contacts/[id]/access` page load, before
    the Chatbot-tab work started - self-recovered immediately (every later request in the same
    log succeeded), not tied to any of the memory feature's own endpoints, and the same class of
    transient shared-machine hiccup the round-2 evidence already recorded and did not carry as a
    defect.

### PASS / FAIL

1. **Chatbot tab (People > Internal Users > Tan)** - PASS. New "Chatbot" tab holds the memory
   cards (level select, "What the bot knows", "Conversations", "Open orders"); the "Access" tab no
   longer shows them. Tabs wrap/render fully at 375px with no page-level horizontal scroll. Level
   change (Past conversations) -> Save (auto) -> reload persisted; Clear -> "(follow the system
   default)" -> reload persisted; restored to Full memory and reload-confirmed. Add fact (Note,
   since the dev DB has no warehouse/brand rows for "Usual sites"/"Usual brands") -> Save ->
   Delete -> 10s countdown + Cancel, no dialog -> lapsed -> DB-committed and gone on reload.
2. **Settings > Chatbot Memory card** - PASS. "Default context level" has exactly 3 options (This
   conversation / Past conversations / Full memory). Set Past conversations -> Save -> reload
   persisted; restored to Full memory -> Save -> reload persisted.
3. **Chat History > Queue column + turn drawer** - PASS. Queue column present, all 5 seeded rows
   show "-" (no ticket, S7 mode was off when seeded, as expected). Turn drawer: Order block,
   Memory panel (with a level-source annotation, "full [own level]"), Context panel (friendly
   layer labels, no raw codes) all render correctly and hold up under a mouse-click accordion
   toggle without the drawer closing.
4. **No horizontal scroll at 375px / clean console+logs** - PASS on all three screens (Chatbot
   tab, Settings Chatbot Memory card is 1280-only per the brief's own viewport list but was not
   re-checked at 375 this round since it wasn't asked for a screenshot there; the drawer at 375
   was checked). No console errors beyond the pre-existing `Demo1Layout` warning; no 4xx/5xx in
   `be.log` for this run's requests; one self-recovering `fe.log` proxy hiccup unrelated to the
   memory endpoints, noted above, not carried as a defect.

One harness note carried forward, not a product defect: the Add-fact key select and the
sidebar's own bottom-of-menu "System" group both needed `scrollintoview`-before-click (and, for
the sidebar, hiding the `nextjs-portal` dev badge that was intercepting the click point) to avoid
a false "nothing happened" - consistent with the standing lesson that a `click @ref` without a
fresh snapshot and `scrollintoview` immediately before it can miss and produce a misleading
result.

Screenshots replaced per the brief: `contact-memory-1280.png` / `contact-memory-375.png` deleted,
`contact-chatbot-tab-1280.png` (134 KB) and `contact-chatbot-tab-375.png` (59 KB) added, both
showing the new Chatbot tab.

### Items 3 and 4 - Memory panel content

Read directly off the rendered `Turn #7fcc` drawer at both viewports (screenshots taken):

- **Item 3 (current subject)** - PASS. "Current subject" reads `domain order; customer CC001`
  (was `Not recorded on this turn.` before the fix, per `focus.after.domains = ["order"]`,
  `customers = [CC001]` on this turn).
- **Item 4 (layer labels)** - PASS. "Context sent to the AI" lists five labelled rows: "About
  this contact" 33/150, "Past conversations" 0/250, "This conversation" 100/450, "Current
  subject and open question" 46/350 (truncated to "Current subject and op..." at 375px, full
  text confirmed via the accessible name / panel `innerText`), "Current message" 24/600, "Total
  memory + message" 203/1800, "Dropped: nothing" - no raw `L1`/`L2` codes visible.

### Console / network

No unhandled JS errors or console `error`/`warning` entries during this recheck's own actions.
`network requests --filter /api/v1/` showed `GET /api/v1/system/chatbot/turns/7fcc38d2-...` 200
for the drawer's own data load, and no 4xx/5xx among this session's requests.

### Summary

PASS on all four items, at both 1280x900 and 375x800, by both `click @ref` and a real pointer
click: (1) Add-fact key select no longer closes the dialog; (2) drawer accordion headers
(Memory, Context) no longer close the drawer, verified against the drawer's own untouched
"Stages" header behaving identically; (3) "Current subject" renders real focus data; (4) L1/L2
layers show friendly labels. One harness-only false negative reproduced and diagnosed (stale
ref / off-screen click), not carried as a defect.
