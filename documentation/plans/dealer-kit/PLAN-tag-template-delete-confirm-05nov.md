# PLAN: tag template delete confirm + soft delete (TAG-TEMPLATE-DELETE-CONFIRM)

Status: in progress (small fix track: one coder, one reviewer; additive nullable column)

## Why

Owner go, 5 Nov. On Dealer Kit > Tag Templates the row's "Delete template" icon starts a
10s countdown and then hard-deletes the template: every version, every
`product_tag_template` / `combo_tag_template` link (ON DELETE CASCADE) and every request
line's `tag_template_id` (SET NULL) go with it. One mis-click on prod is data loss.

## Decisions

- D1. Owner ruling overrides D7 "no confirmation dialog" for this one surface: the row icon
  opens the shared `components/common/ConfirmDeleteDialog`. Its text names the template and
  the number of products, combos and request lines that use it.
- D2. Delete becomes a soft delete: new nullable `dealer_kit.tag_template.archived_at`.
  `tag_template_service.delete_template` / `bulk_delete` stamp it instead of `db.delete`, so
  versions and links stay and a restore is `archived_at = NULL`.
- D3. Archived templates are hidden from the list, the published (request designer) list,
  detail-by-id reads through the CRUD routes, and the product/combo template pickers.
- D4. Confirm then call the DELETE route directly (it is now reversible), no countdown after
  the confirm: two gates in a row is one too many. The bulk toolbar delete keeps its countdown
  and also soft-deletes.

## Tests (red first)

- BE: DELETE keeps the row (archived_at set), its versions and its product/combo links and the
  request line's template id; GET list and `?published=true` hide it; usage endpoint counts.
- FE: clicking "Delete template" opens the confirm dialog naming the template and counts;
  Cancel sends no request.
