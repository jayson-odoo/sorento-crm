# PLAN: Proposal form fold, header-row Column header, heading rows, one column layout

Status: built, in review (FULL track: carries migration `pfc_0001_line_is_section`; no auth or RBAC
change, no new ingest surface). UAC: `proposal-form-collapse-acceptance-criteria.md` alongside.
Lane: PROPOSAL-FORM-COLLAPSE, PR #2302.

Owner asks, 10 Nov 2026 (13:40 to 15:10 MYT), on Project Sales > Project > New / Edit proposal and
the proposal view page, with the crew rulings on the behaviour card (Q1 to Q4) and the model note.

## Items

1. **Header and Lines fold.** Both wrapped in the existing `components/common/FormSection.tsx`
   (new props `keepMounted`, `bodyClassName`). Open on arrival, no persistence. Folded Header reads
   `To · Project title · Date · Total`; folded Lines reads `N scope(s) · RM total`. Folded bodies
   stay mounted (hidden) so nothing typed is lost. Cover letter and Terms tabs untouched.
2. **+ Column header in the column-header row.** It adds the scope's first column HEADER (a
   quantity-column group, PS-QUOTE-MATRIX R11/R12), not a header row, so moving it keeps its
   meaning. Plain scope, editing: a column after Total (RM) (`ADD_FIRST_HEADER_COLUMN`); the bar
   under the table keeps Add a line / Add a section. A grid scope keeps its in-row control.
3. **Project title (Q1 b).** The Subject field is labelled "Project title" and is a wrapping
   textarea. No printout labels it "Subject" (PDF and sign page print it unlabelled); the only
   remaining "Subject" was the letter-template merge field, now "Project title on this quotation".
4. **Duplicate a column-header group (Q2 b).** Right-click on the group header > Duplicate: a copy
   right after it, named "<group> (copy)" and selected for rename, same sub-column names with fresh
   keys, blank quantities. No icon (owner: keep the UI minimum).
5. **Quotation Purpose removed.** Off the form and the header card, not sent on save, and never
   printed (cover rows on the PDF, sign page and both previews skip it in
   `quotation_cover_service.rows_for_design`). Column kept, stored values just stop showing.
6. **Section headings are their own rows (Q4 a + "a heading shouldnt be tied to line").**
   `projects.quotation_lines.is_section` (additive, default false). A heading row carries
   `band_label` only, has its own `sort_order`, adds nothing anywhere. FE: a full-width row with the
   line drag handle (DataGrid `renderFullRow`), numbering skips it, Add a section / Insert a section
   above add a heading row, Remove section drops only that row. A line that still carries a heading
   from before is shown (and seeded) as a heading row above it, a repeated label once; it is written
   as a heading row on that version's next Save that changes it. Issued versions never change.
7. **One column layout (Q3 a).** Per user, the DataGrid precedent, on ONE key
   (`projects.projects.view::quotation-lines`) for edit and view, plain and grid scopes. Fixed
   columns drag the DataGrid way on the two-row header too. A hidden anchor column (`qty_block`)
   places the quantity block; the document's own `mx-*` columns are never stored in the reader's
   order, so they always follow the anchor and the document's header order.
8. **View page widths.** Read-mode sub-columns default wide enough for their label; resizable.

## Readers of quotation lines and how each treats a heading row

See the PR body for the file:line list (backend, MCP, frontend), from a full grep of
`ProjectQuotationLine` / `quotation_lines` / `band_label` readers.

## Tests

- pytest: `tests/test_quotation_section_rows.py` (save path), `tests/test_quotation_section_rows_outputs.py`
  (PDF, workbook, sign page, counts, flags, SO draft), cover tests updated for Purpose, template
  token label test.
- vitest: form fold + no Purpose + carried heading stays clean (`QuotationFormClient.test.tsx`),
  grid header-row button, duplicate, heading rows, read widths (`QuotationLinesGrid.matrix.test.tsx`),
  layout (`QuotationLinesGrid.layout.test.tsx`), draft helpers (`quotationLineDraft.test.ts`),
  sign page heading rows (`QuotationSignScopes.columns.test.tsx`).

## Left out, on purpose

- The cover-design settings still list the Purpose row (it can no longer print). Removing it from
  the design roster is lane QUOTE-COVER-FIELDS's cover-row change.
