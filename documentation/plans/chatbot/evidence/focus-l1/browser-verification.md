# Lane 1 (chatbot-focus-multi-domain) - browser verification

PR #863, branch `feat/chatbot-focus`. Stack: FE http://localhost:3086, BE http://localhost:8086,
DB a prod clone. agent-browser session `focus-l1`. Run: 2026-09-13.

## Summary

| Step | Result |
|---|---|
| 1. Settings > Chatbot > Parser shadow version (searchable select, pick/save/reload/clear) | PASS |
| 2. Chat History Shadow chip + empty state; dry-run turns via Console; drawer panels | BLOCKED - see below |
| 3. Console picker flow (`SRTWT26...` -> "2" -> "2" again) | BLOCKED - same cause |
| 4. Console "another one" then "stock?" clarifier | BLOCKED - same cause |
| 5. 375px layout (settings field, Shadow grid/empty state) | PASS for the parts reachable |

## Step 1 - Settings > Chatbot > Parser shadow version (PASS)

Navigated Dashboards (`/`) -> sidebar "Users & Access" -> "Settings" -> "Chatbot" tab
(`/user-management/settings/chatbot`).

- Field renders as a clearable searchable select (`combobox "Parser shadow version"`) with a
  text search box in its popover, placeholder "Off", listing `v1` through `v15` (real registry
  rows: `v15 · other`, `v14 · compact`, ... `v1 · full · production`). `v15` is
  `chatbot_semantic_parser@15`, confirmed via the POST payload (see below). Screenshot:
  `01-settings-dropdown-1280.png`.
- Picked v15, scrolled the Save button into view (**it sits below the fold on this tab at
  1280x800** - a plain `click @ref` without `scrollintoview` first is a silent no-op here, per
  the standing agent-browser lesson; not a product defect, just the interaction gotcha), clicked
  Save. Network: `POST /api/v1/user-management/settings/general` -> 200, payload includes
  `"chatbot_parser_shadow_version":"chatbot_semantic_parser@15"`, response confirms the same
  value persisted server-side.
- Reloaded (`open` the same URL) - field still shows `v15 · other`. Screenshot:
  `02-settings-v15-persisted-1280.png`.
- Clicked "Clear selection" (the field's `x`), field shows "Off", scrolled to Save, clicked Save
  - payload `"chatbot_parser_shadow_version":null`, 200. Reloaded - field shows "Off". Screenshot:
  `03-settings-cleared-off-1280.png`.
- Re-set to v15 afterward (needed for step 2's shadow-filter check) and saved again, confirmed by
  reload.
- 375px: field renders stacked cleanly under "Switches", label above input, clear `x` visible,
  no clipping, `document.documentElement.scrollWidth === innerWidth` (no page-body horizontal
  scroll). Screenshot: `05-settings-375.png`.

Console errors seen on this page (verbatim): `Each child in a list should have a unique "key"
prop.%s%s See https://react.dev/link/warning-keys for more information.` - reproduced on
`/user-management/settings/chatbot` AND on the plain `/user-management/settings` (General tab),
so this is a pre-existing Settings-shell issue, not something this lane introduced. No errors
reference the shadow-version field itself.

## Steps 2-4 - BLOCKED: chatbot.turns is empty in this lane's DB

`GET /api/v1/system/chatbot/turns` (both with no filter and with an explicit
`from=2020-01-01&to=2026-09-13` range) returns `{"items": [], ...}` - zero rows, for every
contact. The Chatbot Console's `POST /api/v1/system/chatbot/console/turn` requires an existing
`chatbot.turns` row for the chosen contact to "borrow" a session-vars envelope from; with none,
it 404s:

```
{"message":"This contact has no chatbot turn to borrow a session from.",
 "detail":"no chatbot.turns envelope exists yet for contact '516499198'. Send one real WhatsApp
 message from this contact first, or pick a different contact.",
 "code":"CHATBOT_CONSOLE_NO_ENVELOPE"}
```

Tried two contacts from the picker (`~ Zilin`, `Agnes`) with `stock SRTWT2634` - both 404 with
the same code. This gate (`ConsoleContactUnknown` / `CHATBOT_CONSOLE_NO_ENVELOPE`) is
pre-existing: `git log` on `app/services/chatbot/console_service.py` shows it landed in PR #735
(growth-r1 lane 1), well before this lane's branch point - it is not something lane 1
(chatbot-focus) introduced.

I did not attempt to bootstrap an envelope via `POST /api/v1/external/chat/turn` (the real
inbound-turn path used by the Respond.io webhook): that endpoint can trigger real side effects
(escalation assignment + SLA clock start, actual outbound sends), which is unsafe to fire from a
verification pass against contacts that are real dealer records, even on a cloned DB, since
Respond.io credentials in `.env` may be live.

Net effect: I could not produce ANY console turn, therefore could not exercise or verify:
- AC-1029/1030: the Shadow grid's drift badge and summary line against a real shadow row (only
  the empty state was checkable - see below).
- AC-1035: the turn drawer's Focus / Open question / Parser drift panels (Parser drift needs a
  live+shadow pair; there are no turns at all).
- AC-1014 picker flow ("2" resolves, "2" again is a new message).
- AC-1025/1020 "another one" -> "stock?" clarifier flow.
- Step 3/4's exact reply texts requested in the brief: **not obtainable**, no dry-run turn ever
  completed (every send attempt 404'd before reaching the parser).

This is a data/environment gap in the verification stack, not a lane defect I can attribute to
the coder's changes - flagging back to the captain: either seed a `chatbot.turns` row (envelope)
per test contact before this lane's browser pass, or confirm whether the console's "borrow an
envelope" gate should be relaxed for a contact with none (a genuinely new dealer messaging the
bot for the first time hits the same gate on the real `/external/chat/turn` path too, per the
same service - worth the captain/product owner confirming that's intended, since "first ever
message from a new dealer" is a real journey the plan's own script (step 1) describes).

## Step 5 - 375px (partially PASS, rest N/A due to the block above)

- Settings field: see step 1, `05-settings-375.png`.
- Chat History with Shadow chip on: renders the page-level empty copy ("No shadow turns in this
  range. Set a parser shadow version in Settings > Chatbot.") above the grid, and the grid's own
  empty-row repeats the same copy (truncated, with the grid's own internal horizontal scrollbar -
  that is the DataGrid's normal narrow-viewport behavior, not a page-body scroll:
  `document.documentElement.scrollWidth === innerWidth === 375`). Screenshot:
  `06-chat-history-shadow-375.png`.
- Drawer's two-parse-column layout at 375px: **not checked** - no turn exists to open a drawer
  on.

Console errors on Chat History (verbatim, same as Settings): `Each child in a list should have a
unique "key" prop...` (repeats several times), plus `Warning: Missing \`Description\` or
\`aria-describedby={undefined}\` for {DialogContent}.` (repeats several times). Both look
app-shell-wide (not shadow/focus-specific) - not attributed to this lane without further digging,
but reported verbatim as instructed.

## Files

- `01-settings-dropdown-1280.png` - dropdown open, v1-v15 listed, search box.
- `02-settings-v15-persisted-1280.png` - v15 survives a reload after Save.
- `03-settings-cleared-off-1280.png` - cleared + saved + reload shows Off.
- `04-chat-history-shadow-empty-1280.png` - Shadow chip on, named empty state.
- `05-settings-375.png` - field at 375px.
- `06-chat-history-shadow-375.png` - Shadow chip + empty state at 375px.

---

## Re-run 2026-09-13, session `focus-l1b` - unblocked

Coordinator unblocked the DB (`chatbot.turns` now carries rows) and named a contact with a real
envelope: **"Jayson Jayson", Respond id `437264483`**. Re-ran steps 2, 3, 4 and the drawer/375px
half of step 5 against that contact in the Chatbot Console (dry runs).

**Daemon note:** mid-run, fighting the Filters date-picker's segmented spinbuttons pinned one of
my own session's Chrome renderer processes at 100%+ CPU for 20+ minutes and wedged the shared
agent-browser daemon for every command (`get url` itself stopped returning). Killed only the OS
processes under **my own** session's Chrome profile dir (`agent-browser-chrome-1d8401eb...`,
confirmed by start time, distinct from another agent's older profile dir left running on the same
machine) - not `close --all`, not another agent's browser. The daemon recovered immediately after;
re-logged in and carried on. Root cause: the segmented date-input widget does not accept `fill`/
`type`/keyboard digit entry the way a plain text input does - avoid it; it was not needed for any
of the checks below since the default 24h range already covers "now."

### Step 2 - dry-run turns + Shadow-never-fires (PASS)

Console > Contact `Jayson` (437264483, confirmed via the POST payload's `contact_respond_id`) >
sent `stock SRTWT2635` (SRTWT2635 picked off the Products list/API: single exact match, active,
not discontinued) then `SRTWT2635` alone.

- Turn 1 reply: `"Stock details found for the requested products.\n\n1. *Product Code:*
  SRTWT2635\n*Warehouse:* BUKIT RAJA\n*System Location:* BRW-SMC\n*Quantity On Hand:* 3\n
  *Outstanding:* 3\n\n_Data last updated: 04/09/2026 17:30:59_"`. `session_vars.focus.products`
  set to SRTWT2635, `focus.domains: ["inventory"]`, source `current_message`.
- Turn 2 (bare code) reply: identical stock line for SRTWT2635, `focus.products` still SRTWT2635
  (source `current_message`, turn advanced 2->3) - the bare code correctly reruns the domain
  already in focus (AC-1006/1007 shape). Screenshot: `07-console-stock-turns-1280.png`.
- Shadow check: `GET /api/v1/system/chatbot/turns?ingress=shadow&limit=10` returned `{"items":
  [], "summary": {"count": 0, ...}}` immediately after both sends - **zero shadow rows**, with
  the shadow version confirmed set to `chatbot_semantic_parser@15` at the time (verified via
  `GET /api/v1/user-management/settings`, reading the correct nested `settings.
  chatbot_parser_shadow_version` key this time - my first pass at this check in this session
  mis-read the response shape and wrongly logged a `None`; the UI's displayed value was right
  all along, not a stale-display bug). Confirms AC-1027: a dry run is never shadowed, even with
  shadow enabled.

### Step 3 - picker flow (PASS, with a real-data correction to the brief's own suggested prefix)

`SRTWT26` and `CWCX7605` (both real family prefixes with 11 and 4 matches respectively) did
**not** produce a `product_pick`: the engine treats a prefix matching several real, distinct SKUs
as "answer every match" (a fan-out reply enumerating all of them, or - for `promo for CWCX7605` -
resolving to a single canonical entity and asking a `tier_pick` instead). `product_pick` is raised
only by the miss-suggest ("did you mean") lane, which fires on a **near-miss** (a code that
doesn't exactly exist but is close to real ones), per
`app/services/chatbot/lanes/business/miss_suggest.py`. Switched to `stock SRTWT2643` (not a real
code; edit-distance-1 from `SRTWT2634`/2633/2632) to reproduce it:

- Reply: `"Couldn't find \"SRTWT2643\" (product). Did you mean:\n1. SRTWT2632 - no stock
  details\n2. SRTWT2633 - no stock details\n3. SRTWT2634 - no stock details\nReply with a code to
  continue, or would you like me to escalate to warehouse team?"`. `open_question.kind ==
  "product_pick"`, options frozen with `idx`/`uuid`/`product` per row. Screenshot:
  `08-console-picker-offered-1280.png`.
- Reply **"2"**: resolved to the SECOND frozen option, `SRTWT2633` (`focus.products` ==
  SRTWT2633, `source: "pick"`), then reran the alive `inventory` domain for it (no stock/incoming/
  order found, escalate offer to purchasing). Screenshot: `09-console-picker-resolved-2-1280.png`.
- Reply **"2" again**: **not** re-read as a second pick. The `product_pick` question had already
  closed (replaced by the `team_pick` escalate offer from the previous turn); "2" alone, with no
  product/warehouse named, was handled as a new low-signal business_query and got: `"That would
  search every stock we have - I need at least one filter to narrow it down. Give me a product
  code or warehouse, and I can look it up."` The `team_pick` question stayed open and unanswered
  (untouched by "2", consistent with AC-1020: a message that doesn't answer the open question and
  names no new subject leaves it open). Screenshot:
  `10-console-picker-2-again-new-message-1280.png`.

### Step 4 - "another one" / "stock?" clarifier (PASS on retry - see prompt-version note)

**First attempt used the console's own "Prompt version" selector at its default `v13 · full`**
(a selector distinct from the Settings shadow-version field - the console lets an operator run
the LIVE reply itself on any registry version). Under v13, three separate topic-reset phrasings
in a row - `"another one"`, `"something else"`, and the literal `"别的"` from AC-1008 itself - all
left `focus.products`/`focus.domains` completely unchanged (still the picked SRTWT2633), so the
follow-up `"stock?"` just reran the old product instead of asking. This traces to prompt version,
not to the dialogue engine: **v13 predates this lane's parser** (`chatbot_semantic_parser@15` is
the version this lane ships, per AC-1021/1027) - it does not implement the new focus/topic-reset
contract, so testing against it doesn't exercise this lane's code. Retried with the console's
Prompt version switched to `v15 · other` (the SAME dropdown as Settings, present a second time on
the Console page):

- Fresh `stock SRTWT2635` -> `focus.products = SRTWT2635`, confirmed `prompt_version: 15` in the
  response.
- `"another one"` -> reply `"Could you tell me what you'd like to switch to?"`,
  `session_vars.focus: null` and `open_question: null` - product, domain and the open question
  all cleared in one shot. Screenshot: `11-console-another-one-v15-1280.png`.
- `"stock?"` -> reply `"That would search every stock we have - I need at least one filter to
  narrow it down. Give me a product code or warehouse, and I can look it up."` `focus.domains =
  ["inventory"]` (correctly picked up the domain word) but no product filled in and no
  `open_question` raised - the domain word alone did **not** silently answer against a stale
  product; it asked for the missing piece, matching AC-1025/1020's intent even though the wording
  is "give me a product code or warehouse" rather than the literal "which product?" from the
  brief. Screenshot: `12-console-stock-question-clarifier-v15-1280.png`.

**Flag for the captain:** the Console's default Prompt version is v13, an older registry row that
predates this lane's parser contract. Any future console-based verification of Lane 1 behaviour
must explicitly switch it to the lane's own version first, or it silently tests the wrong parser
and looks like a focus/topic-reset regression that isn't one.

### Drawer check (Focus / Open question / Parser drift panels) - BLOCKED, real finding

The Console has its own `trace` link (next to Reset) that deep-links to
`/system-management/chat-history?turn=<turn_id>`, evidently meant to open the turn drawer directly
for the console turn just sent. Followed it for the `stock SRTWT2635` turn above
(`turn=6fd8b7f3-6681-4be5-ad66-c03e432f3c2f`): **no drawer opened** - Chat History rendered its
normal empty grid ("No messages in this range..."), and `network requests --filter 6fd8b7f3`
showed **zero requests fired** for that turn id at all - the drawer component only opens for a
row already present in the grid's loaded data; it does not fetch by id independently.

Checked why the grid never has the row: `GET /api/v1/system/chatbot/turns` (both plain and with
`from=2026-09-13T00:00:00Z&to=2026-09-13T23:59:59Z`) returns **zero items** for today, even
immediately after several successful console sends that each got a 200 with a real `turn_id` and
`reply_text`. The one pre-existing `ingress: "console"` row in the table is from **2026-09-07**
and carries a stalled n8n-callback shape (`"error":"n8n lane did not complete within 10 minutes"`)
- an artifact of an older, asynchronous console implementation. Under the current lane's
synchronous dry-run design, a console turn is generated and returned to the browser but **never
written to `chatbot.turns` at all** (consistent with D14's "a dry run makes exactly the same
[read] calls a live turn makes" - there are apparently no writes left to suppress because there
never was one). Net effect: **no console-originated turn can ever be opened in the drawer**, so
AC-1035's Focus / Open question / Parser drift panels could not be exercised against any of the
turns above, and the Console's own `trace` link is a dead link for every turn it produces.

This is a real, reproducible gap, not an environment/data problem this time - it reproduced
identically for every one of the 9 console turns sent in this session. Flagging to the captain:
either the drawer needs to fetch a console turn by id independently of the grid (matching what
the `trace` link implies it should do), or the console's `trace` link should be removed/labelled
differently until a console turn is actually persisted somewhere the drawer can read.

### 375px - console layout only (drawer unreachable, see above)

Chatbot Console at 375px: no page-body horizontal scroll (`document.documentElement.scrollWidth
=== innerWidth === 375`), Contact / Prompt version fields and the message composer all usable.
Screenshot: `13-console-375.png`. The drawer's two-parse-column layout at 375px remains
**unchecked** - there is no way to open the drawer for a console turn (see above), and no shadow
row exists to open it for either.

Console errors during this whole session (verbatim, same two as the first run, both reproduced on
`/system-management/chat-history` and `/system-management/chatbot-console` too): `Each child in a
list should have a unique "key" prop.%s%s See https://react.dev/link/warning-keys for more
information.` and `Warning: Missing \`Description\` or \`aria-describedby={undefined}\` for
{DialogContent}.` - same pre-existing, app-shell-wide pair as before, not new.

### Updated summary

| Step | Result |
|---|---|
| 2. Dry-run turns via Console (Jayson Jayson, 437264483); Shadow never fires | PASS |
| 3. Console picker flow (near-miss code -> "2" resolves -> "2" again is new message) | PASS |
| 4. "another one" / "stock?" clarifier | PASS on v15 (v13 default gave a false negative - see note) |
| Drawer (Focus/Open question/Parser drift panels) for a console turn | BLOCKED - console turns are never persisted to `chatbot.turns`, the Console's own `trace` link is dead |
| 5 (375px), console half | PASS for the console page itself; drawer half still unreachable |

### Additional files (this re-run)

- `07-console-stock-turns-1280.png` - two stock dry-run turns, SRTWT2635.
- `08-console-picker-offered-1280.png` - "did you mean" product_pick roster (SRTWT2643 near-miss).
- `09-console-picker-resolved-2-1280.png` - "2" resolves to SRTWT2633.
- `10-console-picker-2-again-new-message-1280.png` - "2" again treated as a new low-signal message.
- `11-console-another-one-v15-1280.png` - "another one" clears focus + open_question under v15.
- `12-console-stock-question-clarifier-v15-1280.png` - "stock?" asks for the missing filter.
- `13-console-375.png` - Chatbot Console at 375px.
