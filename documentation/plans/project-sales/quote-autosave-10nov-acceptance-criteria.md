# UAC: proposal / quotation autosave with history (QUOTE-AUTOSAVE)

Plan: `PLAN-quote-autosave-10nov.md`. Owner answers of 10 Nov 2026 ~15:10 MYT are binding.

## Autosave (Q1)

- AC-1: One second after the last edit on the proposal / quotation form, the form's whole state is
  saved to its draft. The header shows "Saving...", then "Saved h:mm".
- AC-2: An autosave never changes the record: its fields, its `updated_at`, its lines. It sends no
  floor-breach alert to management and writes no audit row.
- AC-3: Opening the form, template defaults and opening a saved scope are not edits: nothing is
  saved until something is typed.
- AC-4: Leaving the form any way (sidebar, crumb, Back, refresh, closing the tab) saves what was
  typed. There is no "leave this page?" prompt.
- AC-5: Offline, the header shows "Save failed Retry"; the edit is kept in this browser and sent on
  its own when the connection returns, or on the next open of the form.

## A new proposal (Q2)

- AC-6: New proposal writes a draft private to the person and the project. No record exists and no
  number is used until the first Save.
- AC-7: Reopening New proposal on the same project opens that person's draft. Another person's New
  proposal on the same project starts empty.
- AC-8: The first Save creates the proposal with its number, exactly as Save did before, and the
  draft becomes the new proposal's (its History starts with this Save).

## Save and History (Q3)

- AC-9: Save applies the draft through the existing save: every alert and approval check fires as
  before, once per Save. It writes one History entry and clears the draft.
- AC-10: A Save the server refuses keeps the draft and writes no History entry.
- AC-11: History lists every entry newest first as "Version N", with who, when and the total. View
  shows the entry read-only.
- AC-12: Restore keeps the state being left as "Before restore to version N" (the draft, or with no
  draft the latest Save), then the entry becomes the draft. The record changes only on Save.
- AC-13: Issue and Request approval refuse while a draft is unsaved: "Save or discard the draft
  first."
- AC-14: A document an approval holds refuses its draft; an issued revision's lines stay read-only.

## Two tabs (Q4)

- AC-15: Each open of the form claims the draft. The tab opened earlier becomes view-only within
  15 s (or on its next edit, or when it is focused): banner "Opened in another tab / by <name> at
  <time>", every field locked, Save and Discard draft off, a Reload button.
- AC-16: What the older tab had typed and not sent is kept as a History entry
  ("Not saved: opened in another tab").

## Discard draft (Q5)

- AC-17: There is no Cancel. "Discard draft" shows only while a draft exists and starts a 5 s
  countdown with Cancel; when it lapses the draft is gone and the form returns to the record (or
  the project's quotations for a new proposal). Typing during the countdown does not bring it back.

## Read page

- AC-18: The proposal / quotation page says "Unsaved draft, last edited <date time> by <name>." with
  "Continue editing" while a draft exists.
