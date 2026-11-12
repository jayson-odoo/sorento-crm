# PLAN: Price tag request, tick several items from one search (PRICETAG-MULTI-ADD)

Status: Plan. Behaviour card filed to the owner (12/11/2026); no product code until answered. Track: M (LEAD pattern), no migration expected.

## Owner ask (12 Nov ~13:20)

"for price tag request ... allow to add multiple product so the user can search DIY and add multiple, which will
add multiple rows ... instead of they need to type the same prefix or suffix every time they want to add the item"

## What exists today (measured)

| Piece | Where |
| --- | --- |
| Lines table, one row per item, Item cell is a single `SearchableSelect` ("Search a set or product...") | `sorento_crm_frontend/components/dealer-kit/PriceTagLinesTable.tsx:678-693` |
| Row state + pick logic (`handleItemSelect`, `addLine`, `fetchItemOptions`) | `sorento_crm_frontend/hooks/usePriceTagLineEditor.ts:168-172`, `:572-673` |
| Duplicate rule: a set/product already on another line is REFUSED inline ("CODE is already on this request."), and the server refuses it too (DUPLICATE_LINE) | `usePriceTagLineEditor.ts:630-643` |
| Search endpoint `GET .../lookups/price-tag-items?q=` : sets first then products, each ordered by code, each capped at `limit` (default 20, max 50), no paging, inactive rows excluded | `sorento_crm_backend/app/api/v1/public/portal_price_tag.py:815-837`, `app/services/price_tag_request_service.py:2988-3034`, `app/services/dealer_kit/tag_data_service.py:166-205` |
| Item options carry no discontinued flag today (only part / variant pickers show the "Discontinued" hint) | `sorento_crm_backend/app/schemas/price_tag.py:1294-1308`, `PriceTagLinesTable.tsx:383,409` |
| One form for every screen: CRM create/edit (`app/(protected)/dealer-kit/price-tag-requests/components/PriceTagRequestPage.tsx:7`), portal create/edit (`app/(auth)/portal/price_tag_request/new`, `[id]`, and the `c/[slug]` copies) all render `PriceTagRequestForm` -> `PriceTagLinesTable` | |
| Multi-pick primitive with ticks + "Select all" + load more, stays open across ticks, but commits each tick at once (no "Add N" footer) | `sorento_crm_frontend/components/common/SearchableMultiSelect.tsx` |
| No line table in the app adds several rows from one search today (quotation, sample request, order intake checked); the closest "tick then Add N" is a dialog | `app/(protected)/master-data-management/costing/components/AddCostingProductsDialog.tsx:59` |

## Proposed behaviour (pending owner answers)

See the behaviour card posted as `crew-ask` on the PR, and the mock at
`documentation/mockups/pricetag-multi-add/index.html`.

## Standing rules that apply

- Every picker searchable by name and code (unchanged).
- Portal and CRM identical (one component).
- Products only from the catalogue (no free text).
- Long titles clamped in pickers.
- No feature explanation text inside the UI.
- Usable at 375 px and 1280 px.
- One filled main button per step ("Add N" is the popup's only filled button).
