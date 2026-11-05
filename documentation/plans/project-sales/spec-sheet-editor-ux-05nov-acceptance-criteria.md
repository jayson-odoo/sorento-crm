# UAC: spec sheet page editor UX (05 Nov)

Plan: `PLAN-spec-sheet-editor-ux-05nov.md`. Screen: Project Sales > Projects > a project >
Spec sheets > a sheet (the page editor).

- AC-1 Full screen. The editor toolbar has a "Full screen" button. Pressing it fills the window
  with the toolbar, the Pages rail, the page stack and the Inspector (no app sidebar, top bar or
  page header). "Exit full screen" or Escape returns. A page being edited keeps its selection
  and undo across the toggle. Same control as the price tag designer
  (`dealer-kit/components/FocusMode.tsx`).
- AC-2 Pages rail folds. On desktop the rail has a "Pages" title with a hide chevron; hidden, a
  single show chevron remains and the page stack widens (Fit width follows).
- AC-3 Inspector folds. Same, titled "Inspector", on the right. A selected layer is still
  selected when it is shown again.
- AC-4 Apply to. The Inspector shows "Apply to" with a two-option segmented control
  "This page | Every page", "This page" picked by default. Clicking the picked option again keeps
  it picked. Every page behaves exactly as before (each changed page becomes an edited page).
- AC-5 Templates. Anyone who can edit the sheet sees a "Templates" button in the header. It opens
  "Pick templates" prefilled with the sheet's cover, page and single item templates; Save re-pins
  the sheet to the picks and keeps its rows and page edits. A viewer does not see the button.
- AC-6 Phone (375px): no fold controls (the rail is a strip and the Inspector a bottom sheet, as
  before); Full screen works. Desktop 1280px: nothing clipped.
