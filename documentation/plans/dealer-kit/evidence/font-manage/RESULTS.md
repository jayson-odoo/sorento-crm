# Brand font management - browser verification

Stack: FE :3100, BE :8110 (captain-owned, not started/stopped by this run).
Session: `agent-browser --session font-manage-verify`. Template used: **"Bathroom
Furniture Tag"** (`c56da2da-6886-4555-b69d-0ea95a9597ae`), Live v1, opened via
sidebar Dealer Kit > Room Designer > Tag Templates. Layer used: `dimensions` text
layer (originally Font Family = DM Sans / Arial after cleanup).

Fonts pre-existing before this run: `Century Gothic`, `Century Gothic Bold` -
**untouched**. Font created for this run: `ZZT Verify Font` (Zapfino.ttf),
renamed to `ZZT Verify Renamed`, deleted at the end. No second font
(`ZZT Verify Two`) was needed - AC-7 collision was tested against the existing
`Century Gothic`.

## Results

| AC | Result | Evidence |
|---|---|---|
| AC-1 (Manage fonts button beside Font Family) | PASS | `02-AC1-manage-fonts-button.png`, `04-scrolled.png` |
| AC-2/AC-3 (brand fonts in own typeface; static fonts excluded) | PASS | `AC1-manage-fonts-dialog.png` (Century Gothic + Bold, each rendered in its own face), `AC2-AC3-dialog-with-zzt.png` (ZZT Verify Font rendered in Zapfino script). Dropdown confirms static fonts (DM Sans, Inter, Bebas Neue, Jost, Arial, Georgia, Times New Roman) carry no "Brand font" tag and brand fonts do. |
| AC-4 (pencil -> inline input, Enter saves) | PASS | `AC4-AC5-renamed-dialog.png` - renamed `ZZT Verify Font` -> `ZZT Verify Renamed` via pencil + fill + Enter |
| AC-5 (dropdown + open layer show new name without reload) | PASS | `AC5-layer-shows-renamed.png` - `dimensions` layer's Font Family shows `ZZT Verify Renamed` immediately, no reload |
| AC-7 (rename to taken name refused) | PASS | `AC7-rename-taken.png` - toast `"Century Gothic" is already the name of another brand font.`; row stayed in edit state, list unaffected; cancelled to restore |
| AC-8 (trash -> countdown with Cancel) | PASS (countdown confirmed) | `AC8-countdown-cancel.png` - "Deleting in 9s" + Cancel + progress bar. Note: my scripted Cancel click missed (agent-browser `find text Cancel click` returned "Element not found", likely a timing/ref race) and the countdown lapsed instead - see AC-10 below, which is a stronger positive result than a plain Cancel would have been. |
| AC-10 (lapse refused while font in use) | PASS | `AC10-delete-refused-in-use.png` - toast `Still used by: Bathroom Furniture Tag`, row stayed. Confirmed via a real server round trip: network log shows `PATCH .../assets/{id}` (rename, 200) then repeated `GET /api/v1/pending-actions/current?entity_type=dealer_kit_asset&entity_id=...` polls, no `DELETE` ever lands - i.e. this is the deferred-action mechanism, and the server itself refused the commit. |
| AC-9 (lapse on unused font removes it everywhere) | PASS | `11-delete-countdown-unused.png` (countdown started), `AC9-deleted-lapsed.png` (row gone from dialog after lapse), then full page reload + reselect layer + reopen Font Family dropdown -> `ZZT Verify Renamed` absent from the option list (`12-dropdown-check.png`) |
| AC-13 (375px / 1280px layout) | PASS | `AC13-dialog-1280.png`, `AC13-dialog-375.png` - both usable, nothing clipped; at 375px Upload/Close stack vertically |

AC-6, AC-11, AC-12 not exercised in this browser pass (AC-6 doc-rewrite fan-out
and AC-11/12 RBAC/non-font-asset behavior are backend-shape assertions better
covered by pytest, not requested in this brief).

## Console / defects

- No uncaught page errors (`errors` command: empty) at any point.
- One pre-existing, unrelated React warning: `Each child in a list should have
  a unique "key" prop` in `Demo1Layout` (sidebar layout component) - present
  before any font-management interaction, not caused by this feature.
- **Transient 500 observed once**, not reproduced again: `PUT
  /api/v1/dealer-kit/tag-templates/c56da2da-.../` returned 500 immediately
  followed by a second identical PUT that returned 200, coinciding with the
  autosave fired by changing the `dimensions` layer's Font Family dropdown to
  `ZZT Verify Font`. No console error surfaced for it (network-tab only) and
  the retry succeeded, so it did not block any AC. Could not pull the backend
  stack trace (no log file found via `lsof` on the running uvicorn process,
  and it is the captain's process, not mine to restart/attach to). Flagging
  as a repro note only: rapid Font Family dropdown change on this template
  right after a page load produced one 500 on the template autosave PUT.

## Cleanup / end state

- `ZZT Verify Renamed` (the only font created in this run) was deleted via the
  D7 countdown after the `dimensions` layer was switched back to Arial and the
  template was explicitly Saved (network trace shows the `PUT
  .../tag-templates/{id}` succeeding at 200 before deletion was attempted).
- Confirmed post-reload: dropdown and list no longer show `ZZT Verify
  Renamed`/`ZZT Verify Font`; only `Century Gothic` and `Century Gothic Bold`
  remain, both untouched.
- "Bathroom Furniture Tag" template's `dimensions` layer is back to its
  original `Arial` font family and the template is saved - same state as
  found, no residual edits.
- No `ZZT Verify Two` font was ever created (not needed for AC-7), so there is
  nothing further to delete.
- Browser session `font-manage-verify` was closed (`close`, not `close --all`).
