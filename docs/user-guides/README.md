# Sorento CRM — User Guides

End-user documentation organised by department. The AI assistant is intended to source from these files when answering "what do I do?" / "how do I…" questions.

## Structure

- **[`_shared/`](./_shared/)** — flows reused by multiple departments (e.g. the generic Resource Management upload flow). Department guides link here instead of repeating the same steps.
- **[`purchasing/`](./purchasing/)** — purchasing department: packing list upload, product attachments, folder management, stock inquiry review, product master upload, SPO upload.
- *(future)* `warehouse/`
- *(future)* `marketing/`
- *(future)* `project-sales-admin/`
- *(future)* `project-sales-rep/`

## Conventions

Every guide follows the same shape:

1. One-line summary of when to use the flow.
2. **Steps** — short numbered list with exact UI labels in **bold**.
3. **What's captured** / **What gets created** — the data the system records.
4. **How you'll be notified** — in-app toast vs. email vs. background processing.
5. **Bulk import** (where supported).
6. **See also** — cross-links to related guides.

UI labels are quoted **verbatim** from the React components, not paraphrased — if a label changes in the code, the guide must change too.

## Status

- ✅ Purchasing — drafted, fact-checked against the codebase. Not yet validated against a running instance.
- ⏳ Warehouse, Marketing, Project Sales Admin, Project Sales Rep — pending.

## Source-of-truth notes

- Generic attachment uploads (Pattern A) fire an outbound webhook to **n8n** with the file URL and attachment-type name. The columns the parser expects (e.g. for a packing-list Excel) are defined in the n8n workflow attached to that attachment type, **not** in this codebase. Ask your integrations admin for the current template if a parser fails.
- The only attachment types seeded by Alembic migrations are **Promotion** (`code = 'promotion'`) and **Complaint Document** (`code = 'complaint_document'`). All other types (*Packing List*, *Product Attachment*, *Product Photo*, *Marketing Form*, etc.) are tenant-specific and must be created under **Resource Management → Attachment Types**.
- Module-specific imports (Pattern B) — `product_import`, `spo_import`, `grn_listing_import`, `grn_lines_import`, `stock_import`, `order_tracking_import`, `delivery_order_detail_import` — are processed by the backend's import-job pipeline and surface progress via `LatestImportStatusPanel` on the relevant module's list page.
