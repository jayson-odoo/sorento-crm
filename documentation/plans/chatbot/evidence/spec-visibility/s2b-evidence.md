# AC-21 browser evidence - spec visibility policy (S2, re-run 13/14 Sep 2026, HEAD 26a07f1b4)

This is a re-verification run against the CURRENT lane HEAD, `26a07f1b4` ("fix(chatbot):
spec visibility fails closed..."), one commit ahead of the `56ced8617` the prior tester
verified (`s2-evidence.md`, screenshots `s2-step*`). That fix commit is BACKEND-ONLY
(migration comment, `references.py`, chatbot `access.py`/`lanes/business/*`,
`record_actions.py`, `spec_visibility.py`, tests - confirmed via
`git show 26a07f1b4 --stat`) and touches none of the admin CRUD routes the FE card calls
(`app/api/v1/user_management/spec_visibility.py` is untouched), so the prior run's
findings (F1/F2 below) were expected to hold unchanged; this run re-walked every AC-21
step end to end rather than assuming so, and confirms they do. New screenshots use the
`s2b-*` prefix to avoid overwriting the prior evidence.

Lane: `.claude/worktrees/spec-visibility`, feat/spec-visibility-policy @ `26a07f1b4`.
FE `:3082` (HMR), BE `:8082`, DB `sorento_ai_automation_0907` (shared prod-copy).
agent-browser session `spec-vis-s2b`, closed at end. Contact used (same as the prior
run, DB confirmed clean/Default at start): `e44ae119-6076-4b60-9c85-9a348b2698db`
("Contact 1788624217951").

**Navigation note:** the sidebar's `Users & Access` accordion trigger (and its children,
`Market Segments` / `Settings`) needed `scrollintoview` immediately before `click` every
time, even when the button already reported `expanded=false` in a snapshot - a click
issued without that immediately-preceding scroll silently toggled the accordion open/closed
without following through to the link. Once `scrollintoview` then `click` ran back to back
navigation was reliable. Recorded so the next tester does not read the flakiness as a
product bug.

## Step 1 - Contact page, Default badge, 1280px

Badge: **Default**. Chips: **Thickness**, **board_thickness** (raw key, unlabelled).
Rule: **Hide these**. "Hidden today: Thickness" - board_thickness still omitted from the
summary. **Unchanged from the prior run (F1)**: `board_thickness` is still not a row in
`product_spec_registry` at all (confirmed via direct SQL - zero rows, active or not), so
`hidden_keys`'s "ignored on read" rule for a key that "has since left the registry
entirely" (AC-10) legitimately drops it from the summary. This key ships from the sibling
`chore/sink-thickness-loader` lane (out of scope here per
`PLAN-spec-visibility-policy.md` line 6-7); the fix commit's "full registry" change
(computing hidden keys against every row, active or not) cannot help a key that has no
row at all. Screenshot: `s2b-step1-1280.png`. PASS (matches the UAC's own caveat).

## Step 2 - Show only + Material, save, reload, remove override, 1280px

1. Clicked "Show only": chips carried across unchanged (Thickness, board_thickness),
   confirming AC-3's rule-flip carry-across still holds post-fix.
2. Removed the `board_thickness` chip (required - see finding below), ticked
   **Material**. Chips: Thickness, Material.
3. Saved: **PUT 200 OK**. Badge -> **Contact override**. Chips: Material, Thickness (2,
   not 1 - AC-3's carry-across again, not a defect). "Hidden today" now lists every
   registry key except Material and Thickness (47 keys, screenshot
   `s2b-step2-after-save-1280.png`).
   **Finding (unchanged, F2): a save at any tier that still carries `board_thickness`
   422s** (`"Unknown spec key: board_thickness"`) because `validated_spec_keys` only
   accepts ACTIVE registry keys and the picker pre-fills `board_thickness` from the
   inherited Default row. Confirmed still present on `26a07f1b4` - the fix commit did not
   touch the FE picker or the write-time validator, only the READ-time `hidden_keys`
   full-registry computation, so this is unchanged and still traces to the same
   sibling-lane registry gap, not a regression.
4. Navigated away (contacts list) and back: badge **Contact override**, chips unchanged,
   persisted. Screenshot `s2b-step2-reload-1280.png`.
5. Clicked **Remove override**: a fresh snapshot immediately after confirmed the button
   was replaced by a **Cancel** button (deferred pending action, no confirm dialog - D7).
   Let it lapse per instruction; by the time the NEXT screenshot ran (a few seconds
   later, while inspecting refs) the countdown had already lapsed and the card had
   reverted to **Default** (chips Thickness + board_thickness again) - so
   `s2b-step2-countdown-1280.png` in fact shows the already-reverted Default state
   (byte-identical to `s2b-step2-back-to-default-1280.png` and `s2b-step1-1280.png`),
   not the live countdown; the countdown's existence was still confirmed via the
   snapshot's `button "Cancel"` element between clicking Remove and it lapsing. Confirmed
   server-side via `GET /api/v1/user-management/spec-visibility/contacts/<id>` with the
   backend's `EXTERNAL_API_KEY`: `"override": null`, `"effective": {"source": "default",
   ...}` - the row is genuinely gone, not a stale client read. Screenshot:
   `s2b-step2-back-to-default-1280.png`.

## Step 3 - Market segments + Settings default, 1280px

- **Market Segments > Retail** ("Spec visibility" row action): badge **Default**, chips
  Thickness + board_thickness, "Hidden today: Thickness". No override row (correctly
  inherits). Screenshot `s2b-step3-retail-1280.png`.
- **Market Segments > Project**: badge **Market segment: Project**, placeholder "All
  specs" (empty Hide list), **"Hidden today: Nothing hidden"**. Matches UAC exactly.
  Screenshot `s2b-step3-project-1280.png`.
- **Settings > Spec Visibility** tab (beside Stock Visibility in the tab strip): default
  card, badge Default, chips Thickness + board_thickness, "Hidden today: Thickness".
  Screenshot `s2b-step3-settings-1280.png`.
- Attempted edit (add Material, Save): chips became Thickness, board_thickness, Material
  -> **PUT /default 422 "Unknown spec key: board_thickness"** - same F2 root cause at
  the Default tier. Screenshots `s2b-step3-settings-edit-1280.png`,
  `s2b-step3-settings-422-toast.png`. Because the write never committed, the DB row is
  untouched - confirmed via direct SQL immediately after
  (`excluded_spec_keys = {thickness,board_thickness}`, identical to the value recorded
  before this step and before the whole run started). No restore step was needed.

## Step 4 - 375px, contact page + Settings

- Contact page: Stock visibility + Spec visibility cards render full-width, not clipped,
  chips wrap onto their own line. Opened the Spec keys picker: search box,
  "Select all (49)", scrollable checklist, fully usable. Screenshots
  `s2b-step4-contact-375.png`, `s2b-step4-contact-picker-375.png`.
- Settings > Spec Visibility at 375px: card renders correctly and is not clipped;
  the tab strip truncates the active tab label ("Spec Visi...") - the SAME shared
  tab-strip behaviour every other tab shows at this width, not specific to this card.
  Screenshot `s2b-step4-settings-375.png`.

## Console / errors

`console` showed only `[debug] JWT token extracted successfully` lines throughout (app-wide
auth logging, unrelated). `errors` returned empty at every checkpoint. No regressions
introduced by the `26a07f1b4` fix commit as far as this browser walk can observe (it does
not touch the admin CRUD surface the FE calls).

## AC-21 result table (post-fix re-verification)

| Step | Expectation | Result |
|---|---|---|
| 1 | Default badge, Hidden today: Thickness, Drainer board / countertop thickness | PARTIAL PASS - board_thickness still has no registry row at all (sibling-lane gap, unchanged, expected) |
| 2a | Show only + tick Material + Save -> Contact override, one chip Material | PASS with the same documented deviation (2 chips via AC-3 carry-across; board_thickness had to be removed first to clear the 422) |
| 2b | Reload -> persists | PASS |
| 2c | Remove override, countdown no dialog, lapse, reload -> Default | PASS, server-confirmed |
| 3a | Project -> Nothing hidden | PASS |
| 3b | Retail -> Default, two hidden keys | PASS |
| 3c | Settings default card renders | PASS |
| 3d | Settings edit + save + restore | Save still blocked by the same registry-gap 422; DB unchanged, no restore needed |
| 4 | 375px usable, not clipped | PASS (contact page and Settings) |

## Evidence files

`documentation/plans/chatbot/evidence/spec-visibility/`: this run added
`s2b-step1-1280.png`, `s2b-step2-before-save-1280.png`, `s2b-step2-after-save-1280.png`,
`s2b-step2-reload-1280.png`, `s2b-step2-countdown-1280.png`,
`s2b-step2-back-to-default-1280.png`, `s2b-step3-retail-1280.png`,
`s2b-step3-project-1280.png`, `s2b-step3-settings-1280.png`,
`s2b-step3-settings-edit-1280.png`, `s2b-step3-settings-422-toast.png`,
`s2b-step4-contact-375.png`, `s2b-step4-contact-picker-375.png`,
`s2b-step4-settings-375.png`. The prior tester's `s2-*` files (against `56ced8617`) are
left in place for history; both sets agree.
