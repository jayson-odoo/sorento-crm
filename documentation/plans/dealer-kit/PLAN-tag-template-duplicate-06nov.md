# PLAN: duplicate a tag template (TAG-TEMPLATE-DUPLICATE, 6 Nov)

Status: in progress, code + tests green in sandbox (full track: item 6 carries an additive migration `ttord_0001_tag_template_sort`).

Owner (6 Nov ~10:10): "template needs to have duplicate function also".

## What exists (measured)

- `TagTemplate.doc` / `print_size` are the DRAFT, the editor reads and writes them on every Save;
  a version row is an immutable publish snapshot (`sorento_crm_backend/app/models/dealer_kit.py:705-771`).
  So the draft is always the latest state of the template; a published version is never newer.
- Background is not a column: it is part of `doc` (layers). Assets are referenced by id inside the
  layer props, so copying `doc` references them, nothing is re-uploaded.
- Archived templates (`archived_at`, #2206) never come back from `_get_template_or_404`
  (`app/api/v1/dealer_kit/tag_templates.py`), so a duplicate of one answers 404 and the list never shows it.
- List row actions: icon `Button variant="ghost"` with `title` + `aria-label`, lucide icons
  (`sorento_crm_frontend/app/(protected)/dealer-kit/tag-templates/components/TagTemplatesList.tsx`).
- The editor page has no overflow menu; Publish is its one header action (S7, AC-S7-2), so the
  duplicate lives in the list only.

## Behaviour

1. `POST /api/v1/dealer-kit/tag-templates/{id}/duplicate` (gate `dealer_kit.tag_templates.manage`, same as create).
2. New row: name `"<name> (copy)"`, then `"<name> (copy 2)"`, `(copy 3)`... if taken among live templates
   of the caller's company; same family, price type, `print_size`, and a deep copy of the source's DRAFT
   `doc` (the latest state; live version only differs when the draft has unpublished edits, and those are
   the newer ones). Unpublished (Draft, no version rows: the first Publish makes it v1).
3. Not copied: product/combo links, product defaults, request lines, versions.
4. FE: "Duplicate" icon (lucide `Copy`) in the row actions; on success toast "Duplicated as <name>" and
   open the copy in the editor (`router.push`), the same thing a row click does.

## Tests (red first)

Backend `tests/test_tag_template_duplicate.py`: identical doc, new id, draft (no pointer, no versions),
no product/combo links, source untouched, `(copy)` / `(copy 2)` naming, archived source 404, view-only user 403.
Frontend `TagTemplatesList.duplicate.test.tsx`: the row button posts and navigates to the copy.

## Owner add-ons (6 Nov, same lane)

2. Editor prev/next + "N / M": the shared `components/common/ListPager.tsx` (`useListPager`) in the
   editor header (`tag-templates/components/TemplateRecordPager.tsx`). Its page comes from
   `tag-templates/lib/listQuery.ts`, the same function and React Query key the list uses, so order,
   search and filters carry over from the row link. The editor is keyed on the id: a step unmounts
   the old editor, whose cleanup flushes the pending autosave (the editor's existing unsaved guard).
3. Insert field: the token sits on its own monospace line under the label and wraps; the row's
   `title` is the full token; the Radix viewport's `display: table` box is forced to `block`.
4. Combo Tag preview: `ToggleGroup` (`components/ui/toggle-group.tsx`) of the linked templates,
   Default LP, Default SP, then the rest; opens on the first; Open (DesignViewer) opens what is drawn.
   The product itself has no Tag preview today, so this applies where the preview exists (combos).
5. List toolbar: the standard `DataGridListToolbar` (`components/ui/data-grid-list-toolbar.tsx`)
   `filters: { kind: 'custom' }` + chips + search, as `PriceTagRequestsList.tsx` does; Price type,
   Family and Status multi-select (`SearchableMultiSelect`, `lib/list-filters/multiValue.ts`);
   every column sorts on the server (`GET /tag-templates?sort=&dir=`).
6. Drag reorder: `DataGridTableDndRows` + `DataGridTableDndRowHandle`
   (`components/ui/data-grid-table-dnd-rows.tsx`, the SO lines pattern in
   `project-sales/[projectId]/components/SalesOrderLinesTable.tsx`). `POST /tag-templates/reorder`
   (manage) reassigns the dragged rows' own slots. New = end, duplicate = right below its source.
7. One `TemplateSettingsForm` (`tag-templates/components/TemplateSettingsForm.tsx`): Name, Family,
   Price type, Width, Height, same labels and validation, rendered by New (`TagTemplateDialog`) and
   Settings (`TemplateSettingsDialog`, which now saves Price type too). The only host difference is
   the family list (an existing template keeps its kind: price tag or spec sheet). Duplicate has no
   dialog (it copies at once), so it has no fields to share. TAG SIZE panel vs Settings size:
   **linked both ways**, one value (`template.doc.width_mm/height_mm`), one write path
   (`handleResizeTemplate`); the panel keeps presets, W/H and Per A4 + Turn.

## Tests (as shipped)

Backend: `tests/test_tag_template_duplicate.py`, `tests/test_tag_template_list_order.py`
(12/13 red on main before the change; per-company order kill-tested).
Frontend: `TagTemplatesList.toolbar.test.tsx`, `TemplateRecordPager.test.tsx`,
`InsertFieldDialog.fullToken.test.tsx`, `ComboTagPreview.switcher.test.tsx`,
`TemplateSettingsForm.test.tsx`, plus the item 7 block in `[id]/page.test.tsx`.

## Open for the owner

- The product page's template pickers keep their family-then-name order (not the drag order).
- The product itself has no Tag preview, so item 4's switcher lives on the combo preview only.
