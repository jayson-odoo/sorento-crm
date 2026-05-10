# Guide-target registry

The AI assistant can deep-link a UI element by appending `?guide_target=<key>` to a route. When the page loads, `GuideTargetSpotlight` (mounted in the protected layout) finds the element with the matching `data-guide-target` attribute, scrolls to it, and pulses a glow ring around it for ~3 seconds.

User-guide authors can use this in Outline by writing the deep link inline:

```markdown
Click [**Upload**](/resource-management/attachment-directories?guide_target=resource-management.files.upload-button) to add a new file.
```

The annotation script (`scripts/annotate_user_guides_routes.py`) leaves explicit markdown links untouched, so this survives Outline pull/push round-trips. The system-prompt rule in `_user_guide_protocol_addendum` already mandates the AI assistant preserve inline markdown links verbatim.

## Key naming

`<module>.<page>.<element>` — kebab-case for the element. Keys are stable; renaming a key is a breaking change that requires updating every guide that links to it.

## Registered keys

| Page route | Target key | UI element | Source |
|---|---|---|---|
| `/resource-management/attachment-directories` | `resource-management.files.upload-button` | "Upload" toolbar button | `app/(protected)/resource-management/attachment-directories/components/AttachmentsInFolderPanel.tsx` |
| `/resource-management/attachment-directories` | `resource-management.files.bulk-import-button` | "Bulk import (ZIP)" toolbar button | `app/(protected)/resource-management/attachment-directories/components/AttachmentsInFolderPanel.tsx` |
| `/resource-management/attachment-directories` | `resource-management.files.add-folder-button` | Folders sidebar "Add" (top-level folder) | `app/(protected)/resource-management/attachment-directories/components/DirectoryTreeSidebar.tsx` |
| `/master-data-management/products` | `master-data.products.upload-button` | "Upload" item in the Products list Import dropdown | `app/(protected)/master-data-management/products/components/ProductsList.tsx` |
| `/procurement-management/spo-allocations` | `procurement.spo-allocations.import-options-button` | SPO Allocations toolbar "Import options" trigger | `app/(protected)/procurement-management/spo-allocations/components/SPOAllocationsList.tsx` |
| `/procurement-management/grn` | `procurement.grn.import-options-button` | GRN toolbar "Import options" trigger | `app/(protected)/procurement-management/grn/components/GRNList.tsx` |
| `/order-management/orders` | `order-management.delivery-orders.import-button` | Delivery Orders toolbar "Import" trigger | `app/(protected)/order-management/orders/components/OrdersList.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.approve-button` | "Approve (send to purchasing)" detail action | `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.reject-button` | "Reject" detail action (project_sales OR purchasing context — single key, only one rendered at a time) | `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.edit-purchasing-response-button` | "Edit purchasing response" detail action | `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.reopen-button` | "Reopen" detail action (rejected status) | `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx` |
| `/procurement-management/purchase-requests/{id}`, `/procurement-management/sponsorship-forms/{id}` | `procurement.approvals.change-to-pending-approval-button` | "Change to pending approval" — shared between PR and SF detail (same component) | `app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestDetail.tsx` |
| `/procurement-management/purchase-requests/{id}`, `/procurement-management/sponsorship-forms/{id}` | `procurement.approvals.send-for-approval-button` | "Send for approval" — shared | `app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestDetail.tsx` |

## Adding a new target

1. Add `data-guide-target="<key>"` to the element in the FE (any `<Button>` accepts this via prop spread; for non-Button elements, add directly).
2. Append a row to the table above.
3. Update the relevant guide(s) in `docs/user-guides/` to use the deep-link form, then `python scripts/sync_user_guides_outline.py push` to propagate to Outline.
4. Verify in the browser: navigate via the AI assistant link, confirm the element pulses.

## Behavior notes

- The listener strips `guide_target` from the URL after handling, so refresh / back doesn't re-fire.
- If the key doesn't match any element, the param is still stripped (silent no-op).
- Retry window is 5 attempts × 200ms to cover Suspense / late-mount paths.
- Keys are URL-safe by convention; `CSS.escape` guards the selector regardless.

## Known limitations

- **Targets nested inside closed `DropdownMenu` / `Popover`** are not rendered until the trigger is clicked, so the 1s retry window expires and the spotlight no-ops. Example: `master-data.products.upload-button` (lives inside the Products list "Import" dropdown). Workaround: add the target on the visible **trigger** instead of the hidden item, OR write the guide to step 1 click the dropdown trigger first.
- **Detail-page action targets** (`procurement.stock-inquiries.*`, `procurement.approvals.*`) are attached to buttons that only exist on a record's detail page. The current guide deep-links point to the **list** page (no canonical record id to encode). User lands on the list and must click into a record to see the glow. This is acceptable for v1 — the deep link still gets them to the right module.
