# UAC: price tag request layout (PRICETAG-REQUEST-LAYOUT)

Plan: `PLAN-pricetag-request-layout-10nov.md`. Mock: `documentation/mockups/pricetag-request-layout/index.html` (v3, owner approved 10 Nov with one condition: the AI extract is reused exactly as today).

| ID | Criterion | Test |
| --- | --- | --- |
| AC-1 | The salesperson's request form has three sections in this order: Customers, Price tags, Additional information. Only Customers is open on a new form. | `PriceTagRequestForm.layout.test.tsx`, `PriceTagRequestForm.sections.test.tsx` |
| AC-2 | Customers is a chip multi-select; several customers can be picked; picking one opens Price tags. | `RequestCustomersSelect.test.tsx`, `sections.test.tsx`, browser pass |
| AC-3 | One request stores every customer (`customers`), the first mirrored into `debtor_code` / `debtor_name`; an older request reads as its one debtor; a repeated customer is kept once; a blank name is refused; submit with no customer is refused. | `tests/test_price_tag_multi_customer.py` |
| AC-4 | Price tags shows the preferred default (List price / Selling price) and ONE question, "Upload a file" or "Type the items"; nothing else until it is answered. | `layout.test.tsx` |
| AC-5 | Upload a file shows the existing Sales Order dropzone with its per-file AI extract, unchanged, and no Add line; the extracted lines show under it. Type the items shows the lines table and Add line, and no dropzone. A link switches paths and keeps the lines. | `layout.test.tsx`, `aiExtractApply.test.tsx`, browser pass |
| AC-6 | A saved draft reopens on Upload when it has a file, else on Type the items when it has lines. | `layout.test.tsx` |
| AC-7 | Additional information starts folded and stays folded when lines arrive; it opens on a loaded request that already holds notes or a Need by. | `layout.test.tsx`, `sections.test.tsx` |
| AC-8 | Preview is the page's one main button; there is no Approve on the page. Preview runs the Approve checks (customer, lines, templates, prices, preview drawn) and, when they pass, opens the preview popup whose main button is Approve, beside Back to edit. | `layout.test.tsx`, `approve.test.tsx`, `previewButton.test.tsx`, browser pass |
| AC-9 | The popup's Approve saves, builds the sheet and approves exactly as the old page button did; Back to edit closes it without approving. | `approve.test.tsx`, `layout.test.tsx`, browser pass |
| AC-10 | Need by (revise mode) is the shared DatePicker, dd/mm/yyyy; a changed date must be after today. | `edit.test.tsx` |
| AC-11 | The CRM list and the portal list show "First customer +N" (every name in the tooltip) and search finds any customer; marketing's request page lists every customer. | `test_price_tag_multi_customer.py` (search), lists by review |
| AC-12 | The read-only view has the same three sections in the same order as the edit form; the status chip renders through `<Badge status>`. | `sectionOrder.test.tsx` |
| AC-13 | Usable with no horizontal scroll at 375px and 1280px. | browser pass |
