# PLAN - NPA from Stock Inquiry with product code lineage (NPA-FROM-SI)

Lane NPA-FROM-SI, size L, issue #2200. Status: Plan (card + mock v1 posted as crew-ask 7 Nov; build waits for Q1-Q5).
Track: full (additive migration, portal surface, security-reviewer for portal access).

Builds on NEW-PRODUCT-APP (#1769, `PLAN-new-product-application-17oct.md`).
- Behaviour card (the rules; not restated here): `CARD-npa-from-si-07nov.md`.
- Mock: `mockups/npa-from-si-v1.html`.
- UAC: `npa-from-si-acceptance-criteria.md` (written once Q1-Q5 are answered).

## Design draft (with the recommended answers; revised after the owner answers)

### Data (migration `npasi_0001_lineage`, additive, `IF NOT EXISTS`)
- `stock_inquiries`: `npa_requested BOOLEAN NOT NULL DEFAULT false`, `npa_requested_by` VARCHAR(100) -> users SET NULL,
  `npa_requested_at` TIMESTAMP NULL.
- `new_product_application_line_sources`: `id`, `line_id` -> new_product_application_lines CASCADE, `product_id` ->
  products RESTRICT, `position` INT; UNIQUE (line_id, product_id); index on product_id.

### BE
- Write schema line gains `current_product_ids: list[str]` (staff + portal), company-checked, no duplicates.
- `prefill` adds remark, SI image attachment ids, current codes (exact code equality, Q3).
- `reuse_suggestions(db, company_id, product_ids)`: resolved lines whose source set equals the set exactly.
- Detail line gains `current_products[]` and `suggestions[]` (portal variant without NPA number / customer).
- `GET /procurement/new-product-applications/lineage?product_id=` (product view) -> created_from[], made_from_this[].
- SI: update/reply accepts `npa_requested`; reply adds the next-step sentence; SI detail + portal SI detail carry
  `npa_requested` and `new_product_applications[]` (portal: own SI only).
- Assistant registry: `assistant_registry/procurement.py` registers stock_inquiry, new_product_application,
  new_product_application_line.

### FE
- SI dialog checkbox; staff SI line tabs (Details / New product applications); portal SI extra tab + banner + CTA.
- Lines table Current product codes column (`SearchableMultiSelect`) + suggestion row; staff detail Use <code>.
- NPA detail Stock inquiry tab (staff + portal); product page Lineage tab.

## Test list (tester, red first, after answers)
Filled with the UAC.
