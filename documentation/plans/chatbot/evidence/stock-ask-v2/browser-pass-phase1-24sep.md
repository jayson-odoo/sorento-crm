# Browser verification - chatbot stock ask v2, Phase 1 (S1 + S2)

Plan: `documentation/plans/chatbot/PLAN-chatbot-stock-ask-v2-24sep.md`. UAC:
`documentation/plans/chatbot/chatbot-stock-ask-v2-24sep-acceptance-criteria.md`.
Per the "at most two screenshots per lane" rule in `documentation/agents/browser-verification.md`,
this text log is the record of the walk; only two representative screenshots are committed
alongside it (`s1-product-form-placeholder-inherit-1280.png`,
`s2-contact-chatbot-toggles-375.png`).

Environment: a throwaway local Postgres + Redis + backend + frontend dev stack was stood up in
this session (no `.env`, no seeded DB existed in the sandbox). The two new permission slugs
(`master_data.chatbot_stock_limits.view` / `.edit`) do not exist in the backend yet (Phase 2
migration), so they were inserted directly as `user_permissions` rows for local verification only
- not part of the shipped diff. A seed script created one admin user, one category
(`ZZT-STOCKASK`), one product (`ZZT-STOCKASK-001`) and one contact - also not shipped.

## S1 - CategoryForm (create modal)

1. Sidebar: Products > Reference Data > Product Categories > Create Category.
2. Modal shows "Max quantity (assistant)" and "ETA offset (days)" number inputs directly under
   Display Order, both enabled (holder has `.view` + `.edit`). No helper text.
3. Filled `ZZT-ROUNDTRIP` / `ZZT Roundtrip Check` / Max quantity `50` / ETA offset `7`, clicked
   Create. Toast "Category created successfully"; `POST /api/v1/master-data/product-categories/`
   201 in the backend log.
4. Removed `master_data.chatbot_stock_limits.edit` from `user_permissions`, reloaded: reopening
   Create Category still shows both fields (holder keeps `.view`), but
   `document.querySelector('#category-...').disabled === true` for both - confirmed via `eval`.
5. Removed `.view` too, reloaded: `document.body.innerText.includes('Max quantity')` is `false`
   on both the create modal and the category detail page - the fields are absent, not just
   disabled. Restored both permission rows afterwards.

## S1 - Category detail page (`/master-data-management/product-categories/{id}`)

This is the ACTUAL live edit surface for an existing category - `CategoryForm.tsx`'s
`categoryId` (edit) branch has no reachable trigger in the current UI (`CategoriesList.tsx` never
calls `setEditingCategoryId` with a real id; the row opens this page instead, per its own code
comment "the row opens this page now, and Edit swaps each value for its input where it stands").
Phase 1 therefore also gained the two fields on this page's Basic Information card (not only on
`CategoryForm.tsx`), gated and placed the same way, so S1 is actually usable for an existing
record. Noted as a deviation from the plan's literal "CategoryForm.tsx" wording, resolved by
reading the code (PRINCIPLES.md "measure against real data").

1. Opened `ZZT Roundtrip Check` (created above), clicked Edit: "Max quantity (assistant)" and
   "ETA offset (days)" inputs, populated 50 / 7.
2. Clicked Save category (toast "Category updated successfully"), navigated to the category list
   and back into the record: the view mode shows "Max quantity (assistant) 50" / "ETA offset
   (days) 7" - real round trip, no page reload involved.
3. Edited again to set X = 100, Y = 14 for the ETA-offset placeholder check below.

## S1 - ProductForm (Specifications tab) + product detail page

1. Sidebar: Products > All Products > (seeded product) > Edit > Specifications tab. "Max
   quantity (assistant)" and "ETA offset (days)" sit directly after Reorder Level / Reorder
   Quantity (plan text said "Basic Information"; the actual reorder fields live in the
   Specifications tab per `product-schema.ts`'s own tab comment, so the two new fields were
   placed there instead - same "measure against real data" reasoning as above).
2. Filled 20 / 3, clicked Update Product: toast "Product updated successfully"; the product
   detail page's Overview > Specifications section then showed "Max quantity (assistant) 20" /
   "ETA offset (days) 3" beside Reorder Level / Reorder Quantity, `-` is the fallback pattern
   used elsewhere on the same section for unset values.
3. Placeholder check: with the category (`ZZT-STOCKASK`) carrying X=100/Y=14 (set above) and the
   product's own fields empty, the two inputs on the Specifications tab show `placeholder="100"`
   and `placeholder="14"` (confirmed both via a DOM inspection of the `placeholder` attribute and
   the attached screenshot). Screenshot: `s1-product-form-placeholder-inherit-1280.png`.

## S2 - ContactChatbotSection ("Access" tab, contact detail page)

1. Sidebar: Users & Access > People > Internal Users > (seeded contact) > Access tab. The
   "Chatbot" card gained two Switch rows, "Notify salesman" and "Packing list allowed", both off
   by default, directly under the existing Tier select - screenshot
   `s2-contact-chatbot-toggles-375.png` (375px, no clipping, consistent with the existing rows).
2. Toggled "Notify salesman" on: toast "Chatbot settings saved". Navigated to the contacts list
   and back into the same contact: "Notify salesman" reads `checked=true`, "Packing list
   allowed" still `checked=false` - confirms the PUT sends the whole profile and only the
   touched field changes (AC-SA205's "toggling one saves the whole profile with the others
   unchanged").

## Console / network

No console errors on any of the above screens beyond the pre-existing
`Missing Description for {DialogContent}` Radix a11y warning (unrelated, present on
`CategoryForm` before this change). Every save above round-tripped through the real
`PUT`/`POST` endpoints named in `categoryService.ts` / `productService.ts` /
`contactChatbotService.ts` - confirmed via the backend's own request log, not just the toast.
