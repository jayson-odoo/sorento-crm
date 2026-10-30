# UAC - ITEM-CLASS-MASTER (contract 2.11)

Plan: `PLAN-item-class-master-29oct.md`.

- **AC-1** `POST /external/ingest/item_classes` with a new code creates one `item_classes` row in
  the anchor company (code, name, description, active) and links the `source_ref`.
- **AC-2** Re-push of the same `source_ref` updates the same row: an omitted field is untouched,
  `""` clears description, name/is_active overwrite (AutoCount is master).
- **AC-3** A row that already exists with the same code in any case or padding (e.g. `serene`
  created by a product push or by hand) is adopted: outcome `updated`, same id, no second row,
  the placeholder description replaced by AutoCount's.
- **AC-4** The same code in another company is created independently; company A's row is untouched.
- **AC-5** `POST /external/read/item_classes` returns code, name, description, is_active for a
  linked `source_ref`; an unknown one is `not_found`.
- **AC-6** `POST /external/ingest/item_classes/deletions` sets `is_active = false` and keeps the
  row and its reference, even when no product carries the class (never a hard delete); products
  keep their class link; a re-push with `is_active: true` reactivates.
- **AC-7** The routes take `master_data.item_classes.edit` / `.view` / `.delete`; a principal
  without them is refused.
- **AC-8** `GET /external/contract` reports version `2.11`, `item_classes` in `entities`, and
  `fields_added.item_classes`.
- **AC-9** Code longer than 50 or name longer than 150 fails that record only (validation), not the batch.
- **AC-10** A product push with `item_class_code` after a class push links the master row (no
  `item_class_created` warning, no duplicate).
