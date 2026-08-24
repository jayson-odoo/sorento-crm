# Guide-target registry

The AI assistant can deep-link a UI element by appending `#guide_target=<key>` (URL fragment) to a route. When the page loads, `GuideTargetSpotlight` (mounted in the protected layout) reads the fragment, finds the element with the matching `data-guide-target` attribute, scrolls to it, and pulses a glow ring around it for ~3 seconds.

> **Why fragment, not query string?** Outline's editor (ProseMirror) silently strips query-bearing relative links from bold-wrapped link forms (`**[X](/path?q=v)**` → `**X**`) when a human opens the doc and ProseMirror re-serializes on auto-save. Fragments survive because they are URL-spec components and Outline's link validator leaves them alone. The component still accepts the legacy `?guide_target=` form for backward compatibility, but every guide should use the fragment form going forward.

User-guide authors can use this in Outline by writing the deep link inline:

```markdown
Click [**Upload**](/resource-management/attachment-directories#guide_target=resource-management.files.upload-button) to add a new file.
```

The annotation script (`scripts/annotate_user_guides_routes.py`) leaves explicit markdown links untouched, so this survives Outline pull/push round-trips. The system-prompt rule in `_user_guide_protocol_addendum` already mandates the AI assistant preserve inline markdown links verbatim.

## Key naming

`<module>.<page>.<element>` - kebab-case for the element. Keys are stable; renaming a key is a breaking change that requires updating every guide that links to it.

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
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.reject-button` | "Reject" detail action (project_sales OR purchasing context - single key, only one rendered at a time) | `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.edit-purchasing-response-button` | "Edit purchasing response" detail action | `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.reopen-button` | "Reopen" detail action (rejected status) | `app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx` |
| `/procurement-management/purchase-requests/{id}`, `/procurement-management/sponsorship-forms/{id}` | `procurement.approvals.change-to-pending-approval-button` | "Change to pending approval" - shared between PR and SF detail (same component) | `app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestDetail.tsx` |
| `/procurement-management/purchase-requests/{id}`, `/procurement-management/sponsorship-forms/{id}` | `procurement.approvals.send-for-approval-button` | "Send for approval" - shared | `app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestDetail.tsx` |

### Popup-internal targets (require user to open the parent dialog first)

These keys live inside dialogs/modals. The spotlight component falls back to a `MutationObserver` (30s window) so they fire after the user clicks the parent trigger.

| Page route | Target key | UI element | Source |
|---|---|---|---|
| `/resource-management/attachment-directories` | `resource-management.files.access-levels` | "Access Levels" checkbox group inside the Create Attachment dialog | `AttachmentUploadDialog.tsx` |
| `/resource-management/attachment-directories` | `resource-management.files.upload-confirm-button` | "Upload N Attachment(s)" submit button inside the Create Attachment dialog | `AttachmentUploadDialog.tsx` |
| `/resource-management/attachment-directories` | `resource-management.files.bulk-import-confirm-button` | "Import ZIP" submit button inside the Bulk Import dialog | `AttachmentBulkImportDialog.tsx` |
| `/master-data-management/products`, `/order-management/orders`, `/inventory-management/stock` | `template-upload.confirm-button` | Generic "Upload" button on shared TemplateUploadDialog (one key, multiple consumers) | `components/template/TemplateUploadDialog.tsx` |
| `/procurement-management/spo-allocations` | `procurement.spo-allocations.import-confirm-button` | "Import" button inside SPO Import dialog | `SPOImportDialog.tsx` |
| `/procurement-management/grn` | `procurement.grn.import-confirm-button` | "Upload" button inside GRN Import dialog (used for both header + lines flow) | `GRNImportDialog.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.reject-confirm-button` | Confirm "Reject" inside the Reject stock inquiry dialog | `StockInquiryDetail.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.reopen-confirm-button` | Confirm "Reopen" inside the Reopen dialog | `StockInquiryDetail.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.save-response-button` | "Save only" inside Edit purchasing response dialog | `StockInquiryDetail.tsx` |
| `/procurement-management/stock-inquiries/{id}` | `procurement.stock-inquiries.update-and-reply-button` | "Update & Reply" inside Edit purchasing response dialog | `StockInquiryDetail.tsx` |
| `/procurement-management/purchase-requests/{id}`, `/procurement-management/sponsorship-forms/{id}` | `procurement.approvals.create-link-only-button` | "Create link only" inside Send for approval dialog | `PurchaseRequestDetail.tsx` |
| `/procurement-management/purchase-requests/{id}`, `/procurement-management/sponsorship-forms/{id}` | `procurement.approvals.create-link-and-send-button` | "Create link & send email" inside Send for approval dialog | `PurchaseRequestDetail.tsx` |
| `/procurement-management/purchase-requests/{id}` | `procurement.approvals.reject-confirm-button` | Confirm action inside the Reject this submission AlertDialog | `PurchaseRequestDetail.tsx` |

## Adding a new target

1. Add `data-guide-target="<key>"` to the element in the FE (any `<Button>` accepts this via prop spread; for non-Button elements, add directly).
2. Append a row to the table above.
3. Update the relevant guide(s) in `documentation/user-guides/` to use the deep-link form, then `python scripts/sync_user_guides_outline.py push` to propagate to Outline.
4. Verify in the browser: navigate via the AI assistant link, confirm the element pulses.

## Behavior notes

- The listener strips `guide_target` from the URL after handling, so refresh / back doesn't re-fire.
- If the key doesn't match any element, the param is still stripped (silent no-op).
- Retry window is 5 attempts × 200ms to cover Suspense / late-mount paths.
- Keys are URL-safe by convention; `CSS.escape` guards the selector regardless.

## Known limitations

- **Targets nested inside closed `DropdownMenu` / `Popover`** are not rendered until the trigger is clicked, so the 1s retry window expires. The MutationObserver fallback now keeps watching for 30s - if the user opens the dropdown within that window, the spotlight fires.
- **Popup/dialog-internal targets** (every key in the section above) rely on the same MutationObserver fallback. The user must open the parent dialog within ~30 seconds of clicking the chat link, otherwise the spotlight quietly times out.
- **Detail-page action targets** (`procurement.stock-inquiries.*`, `procurement.approvals.*`) are attached to buttons that only exist on a record's detail page. The current guide deep-links point to the **list** page (no canonical record id to encode). User lands on the list and must click into a record to see the glow. This is acceptable for v1 - the deep link still gets them to the right module.
