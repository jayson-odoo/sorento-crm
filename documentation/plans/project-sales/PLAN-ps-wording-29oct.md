# PLAN-ps-wording-29oct: "To-do list template" and "Minimum price" wording

Status: in build (small fix track, size S, UI wording only, no migration, no logic change)

Source: owner team meeting 29 Oct 2026 15:40 (Project Sales module), lane PS-WORDING.

## Journey

A salesperson or setup admin reads the project task template as a "To-do list template", and a
salesperson pricing a quotation line below its floor sees the warning under the price they typed,
reading "Minimum price RM x", instead of a "Below floor" pill in the product cell.

## Rules

1. Every user-visible "template" that means the project template (`ProjectTemplate`: the
   stakeholder roles + checklist a new project copies) reads "to-do list template"
   ("To-do list template" at the start of a label or sentence). Identifiers, API paths,
   listing keys and the export filename do not change.
   Screens: Project setup (types grid count column, templates grid + card, checklist panel,
   add/edit dialog, type dialog hint, delete text + toast), Project form, Project detail fact,
   Qualify lead dialog, Stakeholders panel empty text, project service error fallbacks.
   Not touched: series "Sanitaryware template" placeholder, WhatsApp/email/letter/tag templates,
   onboarding "Access template" (different things).
2. The below-floor flag on a quotation line moves from the Product cell to the Rate (RM) cell,
   under the price (and under "List RM x"), and reads "Minimum price RM x". The source line
   under it reads "Set on <level>." (was "Floor is/was RM x, set on <level>."). With no floor
   value: pill "Minimum price", text "Below the minimum price for this item.".
   The Non-standard pill stays in the Product cell. Same verdict source (saved row while
   pristine, `useLineVerdict` once the draft diverges); React Query dedupes the one key.
3. Line save toasts (`useQuotationLineMutations`): "Below the minimum price of RM x."
   (create adds "Management has been notified.").
4. `PriceFloorPanel` (product / category forms + product detail) title reads "Minimum price".
   Only the title (crew ruling 29 Oct: brief scope, minimise change management).

Out of scope (crew ruling (a), 29 Oct; listed in the PR body as a follow-up question for the
owner, not changed): Price Floors page + sidebar entry (`config/menu.config.tsx:225`,
`price-floors/page.tsx:19`), series "Floor" columns (`SeriesProductsTable.tsx:142`,
`SeriesSetsTable.tsx:109`), quotation approval panel (`QuotationApprovalPanel.tsx:36`),
quotation re-check summary (`QuotationVersionEditor.tsx:639,644`), `PriceFloorPanel` body text
and buttons, `PriceFloorDialog`, ProductForm `disabledReason`.

## Tests (red first)

- `QuotationLineFlags.test.tsx`: Rate-cell flag shows "Minimum price RM 700.00"; no
  "Below floor"; product-cell flags never show the minimum price.
- `QuotationVersionEditor.test.tsx`: saved below-floor line shows "Minimum price RM 700.00" inside
  the Rate cell, "Set on a parent category."; live verdict shows "Minimum price RM 94.00".
- `useProjects` line mutations toast wording (existing test file if present, else new).
- `PriceFloorPanel` heading "Minimum price".
- `ProjectForm.test.tsx`, `QualifyLeadDialog.test.tsx`, `ProjectSetupClient.test.tsx`,
  `ProjectDetailClient.test.tsx`: label / heading / column "To-do list template(s)".

## Verification

Touched vitest files only (`--maxWorkers=2`), kill test, reviewer, agent-browser 1280 + 375 on
project setup, project detail, and a quotation version with a below-floor line.
