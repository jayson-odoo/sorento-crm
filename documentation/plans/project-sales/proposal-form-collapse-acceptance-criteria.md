# UAC: Proposal form fold, header-row Column header, heading rows, one column layout

Plan: `PLAN-proposal-form-collapse-10nov.md`. Lane PROPOSAL-FORM-COLLAPSE.

**PFC-1 Fold.** Given New or Edit proposal, the Header and Lines sections are open on arrival.
Clicking "Header" folds it and its toggle reads To name, Project title, date (dd/mm/yyyy) and the
RM total on one line; clicking "Lines" folds it and reads "1 scope · RM x" (or "N scopes"). Clicking
again unfolds; anything typed before folding is still there. Cover letter and Terms have no fold.

**PFC-2 Column header in the header row.** Given a scope with no column headers in an edit session,
"+ Column header" is in the table's column-header row right after "Total (RM)" and not in the bar
under the table; clicking it adds "Header 1". Not shown on a read or where columns cannot be edited.

**PFC-3 Project title.** The field is labelled "Project title", is a multi-line box that wraps a
long title at 1280px and 375px, and is prefilled with the project title on a new proposal.

**PFC-4 Duplicate.** Right-clicking a column-header group's name offers Duplicate; it inserts
"<name> (copy)" right after with the same sub-column names and no quantities, its name selected.
A sub-column's right-click offers no Duplicate; there is no Duplicate icon.

**PFC-5 No Quotation Purpose.** The form has no Quotation Purpose field, Save sends none, the
header card shows none even when one is stored, and a new revision's PDF cover, its sign page and
the previews print no Purpose row. A revision that already went out reprints as it was sent, Purpose
row included (QCF D1; RELEASE-FIX-QUOTE, 11 Nov 2026).

**PFC-6 Heading rows.** A section heading is its own full-width row with a drag handle; dragging it
moves only the heading; dragging, removing or restoring a line never moves or drops a heading.
Item numbers count lines only, identically in the editor, PDF, workbook and sign page. Add a
section adds a heading row then a line; Insert a section above adds a heading row before that line;
Remove section removes only the heading row; a heading emptied and left is removed. A saved line
that still carries a heading shows it as a heading row above it (a repeated label once), and
opening such a scope without changing it saves nothing for it. Headings never count as lines,
never get flags, never join a set on the SO draft, never become sample or spec-sheet items.

**PFC-7 One column layout.** Column visibility, order and widths are the reader's own and the same
on the edit and view pages, for plain and grid scopes. On a grid scope the fixed columns drag by
their headers; the quantity block stays together where the reader put it; reordering column-header
groups reorders them on screen.

**PFC-8 View widths.** On the view page a sub-column label such as BALCONY does not run into the
next column, and sub-columns resize by their header edge.
