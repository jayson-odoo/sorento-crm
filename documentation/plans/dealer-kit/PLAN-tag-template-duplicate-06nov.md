# PLAN: duplicate a tag template (TAG-TEMPLATE-DUPLICATE, 6 Nov)

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface).

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
