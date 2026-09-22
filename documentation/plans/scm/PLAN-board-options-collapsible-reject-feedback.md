# PLAN: fulfilment board line panel - collapsible Options, and Reject says it landed

Status: Small fix track - implemented. Owner finding 22 Sep 2026. Lane worktree
`sorento_crm-board-options-reject`, branch `fix/board-options-collapsible-reject-feedback`.
Frontend only, no migration, no auth change.

UAC: `board-options-collapsible-reject-feedback-acceptance-criteria.md`.

## What was found

Screen: Fulfilment planning board, "Every contributing line" list, a row expanded to
`BoardLineDecisionPanel`.

1. The Options ladder table (`BoardLadderOptionsTable`, rendered inside
   `BoardLineDecisionPanel`) always rendered open, five rows tall, above the composition
   editor. Owner: "the option here needs to be expandable, otherwise waste too much space".
2. Pressing Reject gave no system feedback. Save has two: the button flips to "Saved" with a
   check, and the board toasts "Line N saved - M to confirm". Reject had neither -
   `FulfilmentBoardPanel.decide()` explicitly skipped the toast for a rejected verdict (no
   documented reason, introduced with the "Saved" wording which never fit a rejection), and
   the panel's own `reject()` neither awaited the write nor recorded that it landed.

## The fix

- The Options block is wrapped in the existing `Collapsible` / `CollapsibleTrigger` /
  `CollapsibleContent` (`@/components/ui/collapsible`), closed by default, local state, no
  persistence. `BoardLadderOptionsTable` itself is unchanged; it still renders the same way
  inside the trail popover.
- `reject()` on the panel is now async, mirroring `save()`: it awaits `onDecide`, and only
  then marks the line rejected - a write the server refused leaves the button exactly as the
  planner pressed it.
- `savedOnce` and `rejectedOnce` are mutually exclusive, both seeded and re-seeded off the
  SAME `contribution.draft`, split by its own verdict - `useLineDraftMutation.save.onSuccess`
  patches `contribution.draft` before the write's own promise resolves, so a landed Reject
  needs its OWN read of the draft, not "any draft exists therefore Saved". `save()` clears
  `rejectedOnce`; `reject()` clears `savedOnce`.
- A `pending` flag on the panel disables the plain Save and Reject buttons (not their
  covered-line, always-disabled twins) for the length of the write, so a second click before
  the first settles is a no-op rather than a second PUT and a second toast.
- `FulfilmentBoardPanel.decide()` drops the rejected-verdict exclusion on its own toast: a
  rejection now toasts "Line N rejected - M to confirm - K rejected", read off the same
  `confirmSummaryFor` the save toast already uses.
- The Options trigger carries the same interactive classes the in-repo `CollapsibleTrigger`
  precedents do (`PlanSection`, `TagSizeControl`, `ProductAttachmentsTab`): pointer cursor,
  hover background, a focus ring, and a `min-h-8` tap height. The chevron's rotation respects
  `motion-reduce`.

## Out of scope

Closing the cell dialog synchronously right after clicking Reject, before its now-async write
settles, can show the existing "unsaved changes" prompt (the row is still `dirty` for that
one tick) - the same window Save has carried since its own async fix (B1, fix round 5) and
nothing this lane changed. Measured by the reviewer; not a regression from this lane, and not
fixed here.

## Files touched

- `sorento_crm_frontend/app/(protected)/project-sales/fulfilment-planning/components/BoardLineDecisionPanel.tsx`
  - Options block wrapped in `Collapsible`, closed by default.
  - `rejectedOnce` state, mutually exclusive with `savedOnce`, both seeded/re-seeded off
    `contribution.draft`.
  - `pending` state; `save()` and `reject()` both async, guard each other's flags, disable
    the plain buttons while in flight.
  - Reject button reads "Rejected" (disabled) once landed; no `title` on the disabled plain
    Reject (a `title` never reaches a hover on a disabled `Button`, same reason
    `CONFIRMED_LINE_TITLE` already lives in a tooltip).
- `sorento_crm_frontend/app/(protected)/project-sales/fulfilment-planning/components/FulfilmentBoardPanel.tsx`
  - `decide()` toasts a rejection too, worded for what it is.
- `sorento_crm_frontend/app/(protected)/project-sales/fulfilment-planning/components/BoardLineDecisionPanel.test.tsx`
  - Options collapsed-by-default and toggle tests; Reject lands/stays/reverts tests; a
    mutual-exclusion test against a `contribution.draft` patched to a rejected verdict after
    `onDecide` resolves (mirrors how the board itself patches the draft); a pending-disables
    test with a manually-resolved `onDecide` promise.
- `sorento_crm_frontend/app/(protected)/project-sales/fulfilment-planning/components/FulfilmentBoardPanel.test.tsx`
  - A rejection-toasts test; four pre-existing tests that click Reject then close the cell
    dialog synchronously updated to await the write first (`act`), matching the same timing
    Save has needed since its own async fix.
