# PLAN: SPEC-ICON-COMBINED follow-up (crew pass findings, 9 Nov)

Status: Build. Track: small fix track (size S, no migration, no auth/RBAC change, no new ingest surface).
Follows PR #2291 (merged, main ba0e7578). Plan of the parent: `_archive`-bound
`documentation/plans/dealer-kit/PLAN-spec-icon-combined-09nov.md`.

## Findings and causes (measured)

1. The "shown because ..." hint is cut off ("Trap = S ...") even at 1440 px. Cause: the hint span is
   `min-w-0 max-w-40 truncate` (`sorento_crm_frontend/app/(protected)/master-data-management/products/[id]/components/SpecValueIcons.tsx`),
   added in #2291 fix round 1 for 375 px.
2. Two conditioned icons on one value shrink the value text "150 mm" to 0 px (1440 and 375). Cause: the
   trailing block is `flex shrink-0` and holds the icons AND every hint, while the value button is
   `min-w-0 truncate` (`sorento_crm_frontend/components/spec-table/SpecValueCell.tsx:119-135`), so the
   value is the only thing that can shrink.
3. Numeric specs (Trap outlet length) have no Icon order field. Cause: `carriesIcons` in
   `.../product-specifications/components/record/HeaderTab.tsx:62` is `boolean || allowed_values.length`,
   predating numeric keys carrying icons (PRICETAG-UPGRADE-VARIANTS S4). The backend accepts
   `icon_order` for any key (`app/api/v1/master_data/spec_registry.py:333,1322`).
4. The staff tag preview leaves out feature icons. Cause: `staff_tag_preview`
   (`sorento_crm_backend/app/api/v1/dealer_kit/tag_data.py:293-299`) builds `TagPreviewOut` without
   `feature_icons=result["feature_icons"]`; the portal twin passes it (`app/api/v1/public/portal_price_tag.py:1014`).
   Quick fix: one argument.

## Fix

F1. Hints move to their own line(s) under the value, full text, wrapping (no truncate, no max width).
F2. The value text keeps its width: the first line is value + icons; icons wrap to the next line rather
    than squeezing the value to nothing.
F3. Icon order shows for numeric keys too (view and edit).
F4. Staff tag preview passes `feature_icons`.

## Tests (red first)

- vitest SpecValueIcons / SpecValueCell: hint text is the full reason in an element without
  `truncate` / `max-w-*`; with two conditioned icons both hints render in full on their own line;
  the value button is not allowed to shrink below its content (no `min-w-0` on it when trailing exists).
- vitest HeaderTab: a numeric key shows "Icon order" in view and edit; enum and boolean unchanged.
- pytest: `POST /api/v1/dealer-kit/tag-preview` returns the feature icon rules (with `conditions`).
- Browser: Specifications tab at 1440 and 375 with two conditioned icons on one value.

## Hand-test script fixes (for the next script)

Step 8 needs Edit first; the designer has only "Preview combo"; an admin cannot create price tag
requests (use a dealer portal request or an existing one).
