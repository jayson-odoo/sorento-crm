# UAC: fulfilment board line panel - collapsible Options, and Reject says it landed

Plan: `PLAN-board-options-collapsible-reject-feedback.md`. Every AC has a vitest test.

- AC-1 The Options ladder is closed by default: with `contribution.options` non-empty, the
  table's own rows are not in the document, and the toggle (`data-testid`
  `line-options-toggle-<key>`) reads `aria-expanded="false"`.
- AC-2 Clicking the toggle renders the table; clicking it again hides it. The toggle is
  reachable and readable as a control (pointer cursor, hover background, focus ring, a sane
  tap height), not a bare label.
- AC-3 Pressing Reject with a reason typed, once the write resolves true, flips the button to
  "Rejected" (disabled) and the board toasts "Line N rejected - M to confirm - K rejected".
  Save reads "Save decision" beside it, never "Saved", for a line that was just rejected, not
  saved.
- AC-4 Editing the reason after a landed rejection puts "Reject" back (enabled, once the
  reason is non-blank) - an edit undoes the landed state the same way it already does for
  Save.
- AC-5 A line whose `contribution.draft` the board patches to a rejected decision (the real
  shape `useLineDraftMutation.save.onSuccess` produces, ahead of the write's own promise
  settling) never shows "Saved" and "Rejected" together; conversely a line whose draft is
  approved/amended, or that a fresh Save just landed on a previously rejected line, shows only
  "Saved".
- AC-6 A second click on Reject (or Save) before the first write resolves does not fire a
  second `onDecide` call - the button disables itself for the length of the write, independent
  of its own landed/enabled state.
