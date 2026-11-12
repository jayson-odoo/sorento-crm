# PLAN: Line menu "Insert a section above" is a no-op (fix for #2302)

Status: built, in review (SMALL FIX track: FE only, no migration, no auth/RBAC change)

## Problem

On a proposal/quotation form, a line's "..." menu shows "Insert a section above". Clicking it in a
real browser adds no section row and leaves focus nowhere; Save then saves only the header (crew pass
10 Nov on QT-2026-0005 line 2, dev DB sorento_prod_1104). Shipped in #2302 (PROPOSAL-FORM-COLLAPSE,
main ec8f02f6), not yet on prod.

## Expected (owner rulings in PLAN-proposal-form-collapse-10nov.md)

Clicking "Insert a section above" inserts an empty heading row (`is_section`) directly above that line,
focuses its text input, and the row saves and reloads in the same place, on proposals and quotations.
The same holds for the bottom "Add a section" button and the right-click menu's "Insert a section above".

## Approach

1. Reproduce in a real browser and in a component test (vitest), find the cause, cite file:line.
2. Red test first (commit `test(red):` alone), then the fix, then kill test.
3. Check "Insert a line below" and the right-click menu share or do not share the bug.
4. Reviewer subagent; agent-browser pass on the crew test copy (proposal + quotation: insert, type,
   save, reload) at 1280 and 375.

## Diagnosis

- `QuotationLinesGrid.tsx` `act('section')` committed the heading row, then focused its box with a
  `setTimeout(0)`.
- The menus stay mounted while they play their exit animation (`components/ui/dropdown-menu.tsx`,
  `context-menu.tsx`: `forceMount` + motion `AnimatePresence`), so that timer fired inside the exit.
- During the exit, the pointer leaving the clicked item makes Radix focus the menu content itself
  (`@radix-ui/react-menu/dist/index.mjs` `onItemLeave`). The new, still empty heading blurred and
  `SectionRow`'s `onBlur` ran `closeEmptyBand`, which dropped it. The menu then unmounted with its
  close auto-focus prevented, so focus ended on `body` and Save had nothing to write.
- jsdom tests passed: `vitest.setup.ts` skips every animation and `fireEvent.click` never moves the
  pointer.
- Same mechanism, no data lost: right-click Rename and header Duplicate lost the caret.

Fix: focus moves in the menus' `onCloseAutoFocus` (`settleMenuFocus`), which Radix runs after the
content has unmounted. Not affected: Add a section (a button), Insert a line below (focuses nothing).

## Round 2: B1, autosave brings a dropped empty heading back (crew pass on e9f4e0af6)

- Repro: edit, right-click line 1 > Insert a section above, wait for the autosave, click away (the
  empty heading goes), reopen edit: the empty heading is back.
- Cause: `useQuotationFormAutosave.ts` skipped every change while `isDirty`
  (`QuotationFormClient.tsx`, `dirty || edit.changedScopes.length > 0`) was false. Dropping the
  heading returns the lines to the saved state, so that change never reached the draft, which still
  held the heading.
- Fix: once something has been edited, every later change is saved, a change back to the saved
  state included. Save clears the server draft but keeps this tab's claim
  (`quotation_form_draft_service.record_save`), so the form pauses its autosave once Save succeeds:
  a refetch re-seeding the form while the page leaves cannot write the draft back.
- AC-ISF05: an empty heading dropped after an autosave stays gone when the form is reopened.
- AC-ISF06: after a successful Save, nothing writes the draft back.

## UAC

- AC-ISF01: "Insert a section above" from a line's "..." menu adds one heading row directly above that
  line; no line moves.
- AC-ISF02: the new heading's text input has focus right after the click.
- AC-ISF03: a heading named and saved reloads in the same place (proposal and quotation).
- AC-ISF04: a heading left empty and blurred by the user still goes (existing rule, unchanged).
