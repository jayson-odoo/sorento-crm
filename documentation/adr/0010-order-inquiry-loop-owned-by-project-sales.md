# 10. The Order Inquiry loop is owned by Project Sales

Date: 2026-08-13
Status: accepted

## Context

"Order Inquiry" named two things, built by two owners, against one artefact.

- The projects module **derives** instruction rows from a published project sales order and
  **exports** Joey's spreadsheet (`project_order_inquiry_service.py`, headings pinned to the
  real file).
- An SCM importer already on `main` (`app/services/scm/order_inquiry_service.py`) **ingests**
  that same spreadsheet as demand, creating core `sales_orders` rows stamped
  `demand_origin = 'scm_order_inquiry'`.

One sheet, two homes, no stated owner.

Three things the client settled on 2026-08-13: the sheet carries ONLY project demand;
publishing a project sales order does NOT write core `sales_orders`; and the Excel round
trip stays the writer, because Joey's edit between export and import is the point of the
sheet. The human adjustment is the buy signal, not the publish.

## Decision

**The whole loop - derive, export, human edit, import, create `sales_orders` - is owned by
the Project Sales module.** The SCM importer relocates to projects ownership. SCM keeps
exactly the role it already had: reader. `scm.committed_v` and `demand.py` read core
`sales_orders` and never a module table.

The export-import round trip inside a single module is deliberate, not an accident to be
simplified away. It exists because a person edits the numbers in the middle. If Joey ever
stops editing the sheet, flipping to publish-writes-through is a switch, not a rebuild.

**Duplicate prevention is module-side.** This is the client-approved "option 1", refined
against the code. The sheet is exported before AutoCount has issued the SO number, so a
sheet-created `sales_orders` row carries the project's `provisional_ref` as its `so_number`.
The outstanding-book importer matches on `so_number` only and inserts on a miss, so the same
demand would land twice under two numbers. The fix lives at the one place where both
references are known at once: `project_so_ingest_service`, at the moment it learns
`autocount_doc_no`.

- When no row holds the real number, it **renumbers** the sheet-created row - matched on
  `so_number = provisional_ref` AND `demand_origin = 'scm_order_inquiry'` - to the real one.
- When the outstanding book has already created the real-numbered row, it **links** `so_id`
  to that row and retires the provisional one, so committed demand is never counted twice.

Rows not stamped by the sheet are never touched, and `outstanding_import_service` is
unchanged.

**The `demand_origin` literal stays `'scm_order_inquiry'`** even though ownership moves. The
string is baked into raw SQL (`scm/demand.py`), into migration 346's backfill, and into the
`OrderLinkClaim` CHECK constraint. Renaming it is a data migration that purchases no
correctness. It is recorded here so the mismatch between the string and the owning module
reads as a decision rather than a leftover.

**`sales_orders.source_doc_no` is NOT used as an adoption key.** `so_history_service` already
stamps that column on the same rows with its own doc-number semantics; claiming it would
collide.

**The route path `/api/v1/scm/order-inquiry/*` and the permission `scm.reorder.run` stay
stable through the relocation pass**, so the FE upload dialog keeps working. Moving them into
the projects namespace is a recorded follow-up, not part of the move.

## Consequences

- An optional module is now a writer of a core table. Precedented rather than new: SCM
  already extends `customers`, `suppliers` and `picking_lines`.
- Uninstalling `projects` stops the demand feed but leaves behind the `sales_orders` it
  created. They are real orders, so that is the correct outcome, and it is the same
  reasoning as ADR 0009's purge rule.
- The ownership table in `PLAN-scm-order-inquiry-as-demand.md` gains no project-publish row,
  because publish never writes.
