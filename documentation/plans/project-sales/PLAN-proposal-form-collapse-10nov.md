# PLAN: Proposal form, collapsible Header and Lines, + Column header in the column-header row

Status: in progress (small fix track: FE only, no migration, no auth change)
Lane: PROPOSAL-FORM-COLLAPSE. Owner ask 10 Nov 2026: "I want to make the header and lines section
to be collapsible, the column header supposed to be here" (Project Sales > Project > New proposal).

## Scout

- Form: `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/quotation-documents/components/QuotationFormClient.tsx`
  (new AND edit). Header tab renders `QuotationDocumentHeader` then `FormLines` (scope strip + `QuotationVersionEditor`).
- Reused collapsible: `sorento_crm_frontend/components/common/FormSection.tsx` (Card + Collapsible, one-line
  summary while collapsed, no animation). Already used by `ProjectForm.tsx` and the portal forms.
- "+ Column header" (bottom bar): `components/QuotationLinesGrid.tsx` edit bar, shown only while a scope has no
  column headers (`columnsEditable && !isMatrix`), calls `addHeader`, which adds the scope's first column
  HEADER (a quantity-column group, PS-QUOTE-MATRIX R11/R12), not a header row. Once a header exists the grid
  already shows the same control in the header row (`AddHeaderHeader`, `QuotationMatrixColumns.tsx`).
  So moving it into the header row keeps its meaning: no crew-ask needed.

## Change

1. Header and Lines each wrapped in `FormSection`, open by default, state local (no persistence).
   Collapsed Header summary: To name, Subject, Date, Total. Collapsed Lines summary: scope count + total.
   Cover letter / Terms tabs untouched. `QuotationDocumentHeader` itself is not edited (PROJECT-PARTY-ROLES
   will add a To picker inside it).
2. Plain scope (no headers yet), editing: the starter button leaves the bottom bar and becomes a column
   in the header row right after "Total (RM)" (before the row-actions handle), reusing `AddHeaderHeader`.
   A scope with headers keeps its existing in-row control.

## Tests (red first)

- `QuotationFormClient.test.tsx`: Header and Lines toggles, open by default, collapse hides body and shows
  the summary, expand restores; Cover letter / Terms unaffected.
- `QuotationLinesGrid` test: on a plain scope the Column header button is inside a `columnheader` cell after
  "Total (RM)", not in the bottom bar; clicking it still adds "Header 1".
