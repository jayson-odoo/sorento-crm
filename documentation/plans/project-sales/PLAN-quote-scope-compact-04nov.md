# PLAN: quotation Lines tab, drop the duplicate scope header (QUOTE-SCOPE-COMPACT)

Status: built, in review (PR #2159). Small fix track (frontend only, no migration, no RBAC change).

## Journey
Owner, 4 Nov: "why do I need a section for the scope where my scope is already at the top?,
the delete button we can jsut put it under the right click of the scope right?"

## Measured facts
- Scope tabs already carry a right-click menu with Rename and Remove scope
  (`[documentId]/components/QuotationScopeTabs.tsx:117-136`).
- The duplicate header is the `Card` in `components/QuotationFormClient.tsx` (`FormLines`):
  scope title, Edit scope pen, outcome pill, Remove scope button. New and Edit proposal both
  render `FormLines`.
- The lines table already sits in its own bordered box (`QuotationLinesGrid.tsx`), hence
  card-inside-card.
- Remove scope has no confirm today and must not get one: it is staged until Save, and
  PRINCIPLES.md forbids confirm dialogs on destructive actions.

## Change
1. Drop the Card and its header; keep the `<section aria-label>` region (no visible title).
2. Outcome pill (saved scope) moves to the strip row, right of the tabs.
3. The ACTIVE tab gets a "Scope actions" ⋯ trigger (DropdownMenu, the same items as the
   right-click menu), shown below `sm` and on coarse pointers. Pattern reused from the row
   "Line actions" menu, `QuotationLinesGrid.tsx` (DropdownMenu + MoreHorizontal).
4. No change to lines, totals, sections, columns.

## UAC
- AC-1 No scope card header: no "Edit scope" pen and no "Remove scope" button in the scope region.
- AC-2 Right-click on a tab: Rename opens Edit scope; Remove scope stages the removal.
- AC-3 The active tab has a "Scope actions" trigger opening the same Rename / Remove scope.
- AC-4 An issued saved scope offers Remove scope disabled.
- AC-5 Usable at 375 and 1280, no horizontal page scroll.

## Evidence
Browser pass on a sandbox stack (seeded project, New proposal, scopes "Scope 1" and "b"):
`evidence/quote-scope-compact/` holds before/after at 1280 and 375, the right-click menu at
1280 and the touch menu at 375. scrollWidth equals the viewport at both widths; the ⋯ trigger is
hidden at 1280 with a mouse and visible at 375 with touch; Rename from the touch menu opens the
Edit scope dialog.
