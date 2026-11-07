# PLAN - NPA from Stock Inquiry with product code lineage (NPA-FROM-SI)

Lane NPA-FROM-SI, size L, issue #2200. Status: Build (card + mock v2 posted 7 Nov; Q1 answered (a) by the owner's v1 notes; Q2-Q5 open, built on the recommendations, all additive).
Track: full (additive migration, portal surface, security-reviewer for portal access).

Builds on NEW-PRODUCT-APP (#1769, `PLAN-new-product-application-17oct.md`).
- Behaviour card (the rules; not restated here): `CARD-npa-from-si-07nov.md`.
- Mock: `mockups/npa-from-si-v2.html` (v1 kept).
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

## API contract (as built, BE green)

Staff, base `/api/v1/procurement/new-product-applications`:

| Method + path | Who | Answer |
|---|---|---|
| GET `/products?q=` | create or open_code | `[{id, product_code, product_name, brand_name}]` (empty q = []) |
| GET `/reuse-suggestions?product_ids=a,b` | any NPA slug | `Suggestion[]` (newest first, max 3) |
| GET `/lineage?product_id=` | NPA view/approve/open_code or `master_data.products.view` | `{created_from: Row[], made_from_this: Row[]}` |
| GET `/prefill?stock_inquiry_id=` | create | as before + `remark` from the SI, line 1 `current_product_ids` + `current_products` |

- Write line gains `current_product_ids?: string[]` (left out keeps the saved codes, `[]` clears; 422
  "Product N: <code> is already a current code on this product." / "a chosen current code does not exist").
- Detail line gains `current_products: [{id, product_code, product_name, is_active}]` and `suggestions: Suggestion[]`
  (the line itself excluded). Detail gains `stock_inquiry: {id, inquiry_number, product_code, status,
  item_description, purchasing_response, quantity} | null`.
- Summary (list + detail) gains `created_codes: [{product_code, current_codes: string[], created_at}]`.
- Suggestion (staff) = `{product_id, product_code, product_name, is_active, description, created_at, application_id,
  application_no}`; portal drops `application_id`, `application_no`.
- Lineage Row = `{line_id, application_no, product_id, product_code, product_name, is_active, current_products[],
  description, expected_qty, created_at}` + `application_id, customer_name, project_name` for NPA view-all only.
- Stock inquiry: `PUT /stock-inquiries/{id}` and `POST /{id}/update-and-reply` accept `npa_requested: bool` (a
  response write, 422 outside pending_purchasing / responded; an unchanged echo is fine); the server stamps
  `npa_requested_by/at`. Detail answers `npa_requested, npa_requested_at, npa_requested_by_name`. The reply adds
  "Next step: please create a New Product Application for this inquiry." while asked and no live NPA exists.

Portal, base `/api/v1/public/portal`: GET `/new-product-application/products?q=`,
GET `/new-product-application/reuse-suggestions?product_ids=` (portal Suggestion); NPA write/detail as staff (portal
Suggestion shape); prefill scoped to the contact's company; `GET /submissions/stock_inquiry/{id}` gains
`npa_requested` and `new_product_applications: [{id, application_no, status, status_label, created_at,
created_codes}]` (the contact's OWN applications from that inquiry only).

## Test list
pytest (green): `tests/test_npa_from_si.py` (current codes, reuse exact set / order / subset / superset / closed /
undo / newest-first-3 / not itself, lineage + 403, prefill exact + remark + labels, SI ask stamp / clear / gate /
echo, reply sentence vs live NPA, summary created_codes, detail stock_inquiry) and `tests/test_npa_from_si_portal.py`
(product search company-only, round trip, foreign 422, suggestion without application / customer, detail
suggestions portal-shaped, SI ask + own applications only, created codes, prefill exact).
vitest (FE slice): multi-select product code cell sends `current_product_ids`, read-only chips, "Inquiry asked"
hint, suggestion row text per surface, "Use <code>" fills the link picker without linking, SI checkbox sends
`npa_requested`, portal SI banner + CTA only while asked and no live NPA, tabs + empty states, product Lineage tab.
