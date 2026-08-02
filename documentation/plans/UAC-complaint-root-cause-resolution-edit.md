# UAC - Complaint root cause / resolution edit-and-notify

Acceptance criteria for the complaint root-cause / resolution edit popups. Implemented 2026-07-27 and
browser-verified; this file exists so the shipped behaviour is pinned by criteria and covered by tests
like the other two workstreams. Regression lines are hard blockers.

Legend: ☐ pending · ☑ passed.

## Journey

A complaint handler looking at a complaint sees Root Cause and Resolution as read-only text with a
"Notify salesperson" button, while the Technical Team Response beside them can be edited in a popup and
sent to the contact in one action. The two fields therefore could only be changed by leaving the page
for the full edit form. New journey: **Edit** beside each field opens a popup with the value pre-selected,
and the handler either saves the record (**Update**) or saves and tells the contact what the root cause /
resolution is (**Update & Reply**) without leaving the detail page.

## A. Entry points

- A1 ☑ Root Cause row has an **Edit** control beside the existing "Notify salesperson" button.
- A2 ☑ Resolution row has the same.
- A3 ☑ Gear menu offers **Edit root cause** and **Edit resolution**.
- A4 ☑ All entry points are suppressed when the handling lock is held by someone else or the complaint is
  voided (`businessCtasEnabled`).
- A5 ☑ Header keeps only two wide buttons so it does not overflow at phone width.

## B. Popup

- B1 ☑ Title / label / placeholder differ per field ("Edit root cause" vs "Edit resolution").
- B2 ☑ Value is a searchable select over the root-cause / resolution master data, per the searchable
  dropdown standard. No raw UUID visible.
- B3 ☑ Opens pre-selected with the complaint's current value; "- None -" available to clear.
- B4 ☑ Re-opening after Cancel re-seeds from the record, so a cancelled edit never leaks into the next one.
- B5 ☑ Footer is exactly Cancel / Update / Update & Reply, mirroring "Edit technical team response".
- B6 ☐ Scrollable and usable at ~375px (shared dialog max-height rule).

## C. Actions

- C1 ☑ **Update** saves the FK only; no Respond.io message is sent.
- C2 ☑ **Update & Reply** saves the FK, then sends the existing notify message for that field.
- C3 ☑ Update & Reply is disabled when the selection is "- None -" (nothing to tell the contact).
- C4 ☑ Update & Reply is hidden entirely when the complaint has no linked Respond.io conversation.
- C5 ☑ Every action is disabled while a mutation is in flight; buttons show progress copy.
- C6 ☑ On success the popup closes and the detail refetches: the field, and "Last notified" for reply.
- C7 ☑ On failure the popup stays open and the error toast comes from the mutation hook.
- C8 ☐ The update lands before the notify call, since the notify endpoint reads the saved record.

## D. Tests

- D1 ☑ vitest: renders both kinds, Update calls save with the seeded value, Update & Reply chains
  save-then-notify, disabled when unset, hidden without a conversation, Cancel saves nothing,
  all actions disabled while pending. (8 cases, `ComplaintNotifiableFieldDialog.test.tsx`.)
- D2 ☐ pytest: notify endpoints reject when the field is unset (422) and when no Respond contact is linked;
  `*_notified_at` is stamped on success.
- D3 ☑ Browser-verified end to end: PUT then POST `notify-resolution` both 200, detail re-rendered with the
  new value and "Last notified", 0 console errors.

## E. No-regression

- E1 ☑ "Notify salesperson" keeps its previous behaviour and disabled conditions.
- E2 ☑ "Edit technical team response" flow unchanged.
- E3 ☐ Full complaint pytest file green.
