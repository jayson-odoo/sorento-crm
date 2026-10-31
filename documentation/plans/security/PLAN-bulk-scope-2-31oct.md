# PLAN: scope the remaining bulk writes to the company

Status: in review (reviewer READY, security reviewer READY). Full track, not small fix: the diff adds a permission gate to a route and changes
company scoping, so reviewer and security reviewer both run. No migration, no new permission slug.

Lane: SEC-BULK-SCOPE-2. Follows #2027 (`PLAN-bulk-scope-30oct.md`), whose survey listed these.

## Changes

The company scope filter (`app/services/company_scope.py`) covers ORM SELECTs only, so a bulk
`query(...).update()` / `.delete()` or a Core `update()` reaches every company's rows by id. Each
write below now reads its rows through the scoped ORM query and writes them row by row, the way
the single-row path does; an id outside the caller's scope is not found and not counted.

1. `PromotionService.bulk_update_access_levels` (`PATCH /marketing/promotions/bulk`): scoped read,
   set per row. The route asks for the existing `marketing.promotions.edit` (it was sign-in only);
   the promotions list shows Set Access Levels only with it, like Resubmit.
2. `SPOAllocationService.bulk_delete_allocations` (`DELETE /procurement/spo-allocations/bulk`):
   already read its rows scoped for the audit, then deleted by the caller's ids; now deletes the
   rows it read, like `delete_allocation`. Route already gated on
   `procurement.spo_allocations.delete`.
3. `AttachmentService.bulk_set_attachment_type` and `apply_bulk_access_levels`
   (`POST /resources/attachments/bulk-attachment-type`, `/bulk-access-levels/apply`): scoped read
   of the attachments, set per row. Propagation to product links, promotions and packing lists
   reads those rows scoped too, from the attachments actually in scope (so a soft-deleted file in
   the list no longer propagates either). Forms carry no company and
   are unchanged. Attachment is a shared model (a NULL-company file is visible from every company),
   which is what the single edit sees too. Route gates unchanged: there is no attachment edit slug,
   the single edit (`PUT /attachments/{id}`) is sign-in only, and both routes already run
   `assert_can_write_attachments`.

## Acceptance

- A1 each of the four bulk writes naming another company's row leaves it unchanged, count 0.
- A2 a mixed list writes only the caller's own rows.
- A3 own-company rows still update / delete.
- A4 promotion bulk access levels answers 403 without `marketing.promotions.edit`.
- A5 attachment access-level propagation does not reach another company's promotion or packing
  list linked to a shared attachment.

Tests: `sorento_crm_backend/tests/test_bulk_write_company_scope.py`.

## Left as they are

- The LOW items in #2027's survey stay untouched (queued separately).
- Follow-up (security review S1, predates this lane): `bulk-access-levels/apply` with propagation
  still rewrites the caller's own company's promotions, product links and packing lists without
  their edit slugs. A per-target permission check before each propagation leg closes it.
- The promotions list's Set Access Levels gate has no component test: the bulk toolbar needs a
  row selection, which the DataGrid never reaches under jsdom. The route's 403 is tested.
