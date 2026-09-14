# AC-21 browser evidence - spec visibility policy (S2, 13 Sep 2026)

Lane: `.claude/worktrees/spec-visibility`, feat/spec-visibility-policy @ 56ced8617.
FE :3082 (HMR), BE :8082, DB `sorento_ai_automation_0907` (shared prod-copy).
agent-browser session `spec-vis-s2` (isolated `--session`, closed at end).
Contact used: `e44ae119-6076-4b60-9c85-9a348b2698db` ("Contact 1788624217951").

Note on tooling: several early clicks on options inside the Spec keys multi-select
dropdown silently no-op'd (dropdown just closes) because the target option was
below the visible fold of the internal scroll container - a `scrollintoview`/search-filter
before click fixes it (documented CLAUDE.md gotcha: "off-screen click in a scroll
container is a silent no-op"). Not a product defect; noted here so the captain does
not mistake the early failed attempts (visible in the network log) for real save
failures.

## Step 1 - Contact page, Default badge, 1280px

Navigated Contacts (via topbar "Switch layout" grid icon, as the S1 pass found) >
row > contact detail.

- Badge: **Default**. PASS.
- Chips in Spec keys picker: **Thickness**, **board_thickness** (raw key, not a
  label - see finding F1 below). Rule: **Hide these**.
- "Hidden today:" line: **"Hidden today: Thickness"** - only names Thickness, not
  the second key, exactly as the brief's caveat predicted.
- **Finding F1 (expected, registry gap, not a lane defect):** `board_thickness` is
  not yet an active key in `product_spec_registry` (ships with the sibling
  `chore/sink-thickness-loader` lane). The card renders the raw key `board_thickness`
  as its own chip/label (no humanised text) and the "Hidden today" summary omits it
  entirely rather than showing the slug. `GET .../keys` (49 active keys) confirms
  `board_thickness` is absent from the registry.
- Screenshot: `s2-step1-1280.png`.
- PASS (matches AC-2's "record exactly what shows" caveat for a missing registry key).

## Step 2 - Show only + Material, save, reload, remove override, 1280px

1. Clicked "Show only". Chips carried across unchanged (Thickness, board_thickness) -
   matches AC-3 ("flipping the rule carries the ticked keys across"). "Hidden today"
   line stayed at the last-SAVED effective value ("Hidden today: Thickness") while
   the rule was mid-edit, i.e. the summary reflects the persisted/effective policy,
   not the unsaved draft - consistent with AC-2's "effective hidden labels" wording.
2. Ticked **Material** (now 3 chips: Thickness, board_thickness, Material).
3. Clicked Save spec visibility -> **PUT returned 422** `"Unknown spec key:
   board_thickness"`. **Finding F2 (registry-gap consequence, real but expected
   given F1):** because the picker pre-fills `board_thickness` from the inherited
   Default row, and the write endpoint validates every key in the payload against
   the active registry (AC-12), the FIRST save attempt at ANY tier that still
   carries `board_thickness` will 422 until that key exists in the registry. The
   admin must remove the `board_thickness` chip before they can save anything at
   that tier today.
4. Removed the `board_thickness` chip, kept Thickness + Material, Save ->
   **200 OK**. Badge flipped to **Contact override**, chips **Material, Thickness**
   (2 chips, not 1 - the brief's "one chip Material" assumed a fresh empty picker;
   actual behaviour per AC-3 carries the inherited-preview chip(s) forward, so
   Thickness stayed ticked). "Hidden today" now lists every registry key except
   Thickness and Material (47 keys). "Remove override" button appeared, "Save spec
   visibility" disabled (clean state) - matches AC-4 dirty tracking.
   Screenshots: `s2-step2-before-save-1280.png`, `s2-step2-after-save-1280.png`.
5. Navigated away (Back to contacts) and back into the same contact via a fresh
   click, and separately via a full page reload
   (`open http://localhost:.../contacts/<id>`): both times, badge **Contact
   override**, chips **Material, Thickness**, "Hidden today" unchanged. PASS.
   Screenshot: `s2-step2-reload-1280.png`.
6. Clicked **Remove override**: a countdown timer + **Cancel** button appeared in
   place of Save, **no confirm dialog** - matches the D7 deferred-action pattern.
   Let it lapse (per the task's own instruction for this step); reload confirmed
   the card fell back to **Default**, chips Thickness + board_thickness again.
   Confirmed server-side via `GET /api/v1/user-management/spec-visibility/contacts/<id>`
   with the backend's `EXTERNAL_API_KEY`: `"override": null`, `"effective":
   {"source": "default", ...}` - the row is genuinely gone, not just a stale client
   read. PASS. Screenshot: `s2-step2-back-to-default-1280.png`.

## Step 3 - Market segments + Settings default, 1280px

- **Market Segments > Project** row > "Spec visibility" action button (in the
  overflow columns - table needed a horizontal `scrollintoview`, another
  scroll-container gotcha, not a bug): modal "Spec visibility - Project", badge
  "Market segment: Project", placeholder "All specs" (Hide these + []), **"Hidden
  today: Nothing hidden"**. Matches UAC exactly. PASS.
  Screenshot: `s2-step3-project-1280.png`.
- **Market Segments > Retail**: modal "Spec visibility - Retail", badge
  **Default** (no override row for Retail - correctly inherits), chips Thickness +
  board_thickness, "Hidden today: Thickness". No "Remove policy" button (nothing to
  remove). PASS. Screenshot: `s2-step3-retail-1280.png`.
- **Settings > Spec Visibility** tab (beside Stock Visibility, tab strip needed a
  horizontal scroll into view): default card, badge **Default**, chips Thickness +
  board_thickness, Hide these, "Hidden today: Thickness". PASS (AC-6 placement).
  Screenshot: `s2-step3-settings-1280.png`.
- Attempted the instructed edit (add Material, Save): ticked Material (now
  Thickness, board_thickness, Material), clicked Save -> **PUT /default 422
  "Unknown spec key: board_thickness"**, same F2 root cause - the migration-seeded
  Default row itself carries `board_thickness`, so even a same-tier round trip at
  Settings hits the registry gap. **Because the write never committed, the DB was
  never touched** - reloading `/user-management/settings/spec-visibility` and a
  direct `GET /api/v1/user-management/spec-visibility/default` both confirm the
  row is still exactly the migration seed: `excluded_specs: [thickness,
  board_thickness]`. No restore step was needed; the DB is already exactly as
  found. Screenshot of the failed-edit state: `s2-step3-settings-edit-1280.png`.
- Re-verified Project and Retail segment rows via direct API reads after all of the
  above: Project `excluded_specs: []`, Retail inherits default with `excluded_specs:
  [thickness, board_thickness]` - both unchanged. DB confirmed left as found.

## Step 4 - 375px, contact page + Settings

- Contact page at 375px: Stock visibility + Spec visibility cards render full-width,
  no clipping, chips wrap onto their own line under the label. Opened the Spec
  keys picker: search box, "Select all (49)", checkbox list all visible and
  scrollable, usable. PASS. Screenshots: `s2-step4-contact-375.png`,
  `s2-step4-contact-picker-375.png`.
- Settings > Spec Visibility at 375px: card renders correctly; the settings tab
  strip truncates the active tab label to "Spec Visil..." but this is the shared
  tab-strip's existing horizontal-scroll behaviour (same truncation pattern on
  every other tab at this width) and not specific to this card. PASS.
  Screenshot: `s2-step4-settings-375.png`.

## Console / errors

`console` showed only `[debug] JWT token extracted successfully` lines throughout
the run (existing app-wide auth logging, unrelated to this feature).
`errors` (uncaught page errors) returned empty at every checkpoint. No regressions.

## AC-21 result table

| Step | Expectation | Result |
|---|---|---|
| 1 | Default badge, Hidden today: Thickness, Drainer board / countertop thickness | PARTIAL PASS - badge and Thickness label correct; second label reads as raw key `board_thickness` and is omitted from the summary line because the key is not yet in the active registry (expected per the brief's own caveat, tracked as F1) |
| 2a | Show only + tick Material + Save -> Contact override, one chip Material | PASS with a noted deviation: two chips (Thickness, Material) survive because AC-3's rule-flip carry-across keeps the inherited Thickness chip; `board_thickness` had to be removed first to get past the registry-gap 422 (F2) |
| 2b | Reload -> persists | PASS |
| 2c | Remove override, countdown no dialog, lapse, reload -> Default | PASS, server-confirmed via API |
| 3a | Project -> Nothing hidden | PASS |
| 3b | Retail -> Default, two hidden keys | PASS |
| 3c | Settings default card renders | PASS |
| 3d | Settings edit + save + restore | Save blocked by F2 (same registry gap); DB left unchanged because the write never committed - restore step was moot |
| 4 | 375px usable, not clipped | PASS (contact page and Settings) |

## Evidence files

`documentation/plans/chatbot/evidence/spec-visibility/`:
`s2-step1-1280.png`, `s2-step2-before-save-1280.png`,
`s2-step2-after-save-1280.png`, `s2-step2-reload-1280.png`,
`s2-step2-countdown-1280.png`, `s2-step2-back-to-default-1280.png`,
`s2-step3-project-1280.png`, `s2-step3-retail-1280.png`,
`s2-step3-settings-1280.png`, `s2-step3-settings-edit-1280.png`,
`s2-step3-settings-422-toast.png`, `s2-step4-contact-375.png`,
`s2-step4-contact-picker-375.png`, `s2-step4-settings-375.png`,
plus debug screenshots taken while isolating the scroll-container click issue
(`debug-*.png`).
