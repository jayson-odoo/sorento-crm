# PLAN: project quote line tools (duplicate line, below-default badge, line filter)

Status: Review (built; reviewer + cloud browser pass running). Small fix track by diff (no migration, no auth/RBAC change, no new ingest surface;
one read-only field added to an existing verdict response). Lane PROJECT-QUOTE-LINE-TOOLS.
UAC: `project-quote-line-tools-acceptance-criteria.md`.

## Owner request (11 Nov 2026)

Duplicate a quote line (same per-area quantities, then change the product); show which lines are
priced below the default price with a badge like "Non-standard"; filter the lines grid by
Non-standard / Below default price.

## What exists today (measured)

- Banner sentence: `reasons_text` in
  `sorento_crm_backend/app/services/project_quotation_approval_service.py:260`. It counts STORED
  line flags across every scope of the document: `is_non_standard` ("outside the project's
  series"), `is_below_floor` ("priced below the minimum price"), and `is_discounted` minus
  `is_below_floor` ("priced below the default price").
- `is_discounted` is set on save by `_apply_guardrails`
  (`sorento_crm_backend/app/services/project_quotation_service.py:750-751`): unit price below
  `line_default_price` (`:678`), which is the series selling price where the series names the
  product or set, otherwise the list price snapshot. No default means never discounted.
- The saved line response already has `is_discounted` (`app/schemas/projects.py:1596`). The FE
  type `QuotationLine` does not declare it, and the live draft verdict
  (`QuotationLineVerdictResponse`, `app/schemas/projects.py:1063`; `_judge_line`,
  `app/api/v1/projects/quotations.py:254`) returns only `is_non_standard` and `is_below_floor`.
- Non-standard badge: `LineFlags` in
  `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/QuotationLineFlags.tsx:76-104`,
  rendered under the product code by `ProductCell` (`QuotationLinesGrid.tsx:469`). It reads the
  stored flag while the draft matches the saved row, and the live verdict (`useLineVerdict`,
  debounced 400 ms) once the draft diverges.
- Line menus: the row's "Line actions" dropdown (`QuotationLinesGrid.tsx:908-943`) and the grid's
  right-click menu (`QuotationLinesGrid.tsx:2269-2295`) both call `act(key, action)`
  (`QuotationLinesGrid.tsx:1551`). Section heading rows have their own right-click menu (Rename,
  Remove section).
- Toolbar: `QuotationVersionEditor.tsx:816-826` hands the grid a `ListSearchInput` ("Search lines")
  and a `rowFilter` (`:678`). The grid hides rows that fail it without renumbering or changing
  the total (`QuotationLinesGrid.tsx:1602`).
- Area tabs: `QuotationScopeTabs.tsx`. There is NO count slot on a tab (money and other figures
  were kept off the tabs by owner ruling), so tab counts are not added.

## Rules

1. **Duplicate line.** "Duplicate line" sits in both line menus (row ⋯ and right-click), under
   "Insert a line below". Edit mode only; disabled on a line staged for removal; not offered on a
   section heading row. It inserts a new unsaved line right below the source holding a copy of the
   source's whole draft: product or set, rate, every per-area quantity cell in every column group,
   description, brand, UOM, item label, technical spec, complete set, notes, photo and drawing
   picks. The section it falls under is the source's, because it sits right below it. Focus goes to
   the new line's product picker. The first product change on the copy behaves exactly like a pick
   on a new line: rate becomes the series price or blank, and description, brand and UOM follow the
   product (the existing `fillFromProduct` / `fillFromSet`; catalogue only). Leaving the product
   unchanged keeps an exact copy.
2. **Below default price badge.** "Below default price" (the banner's words) is a `Badge` with the
   same component, variant and placement as Non-standard (`QuotationLineFlags.tsx:94-101`), beside
   it when both apply. It shows when the line is priced below its default price AND not below the
   minimum price, which is exactly the banner's "priced below the default price" clause. A line
   below the minimum price already carries the red "Minimum price RM x" pill in the Rate cell and
   counts in the banner's minimum-price clause, so it does not get a second pill. Source of truth:
   the stored `is_discounted` / `is_below_floor` while the draft matches the saved row, else the
   live verdict, which now also returns `is_discounted` computed by the same default-price rule the
   save runs (one backend function, `default_price_for`). Edit and view modes, also on a new unsaved
   scope.
3. **Filter.** A `SearchableMultiSelect` ("Flags") beside "Search lines" with options "Non-standard",
   "Below default price" and "Below minimum price". Several options = a line
   matching ANY of them; combined with the search box by AND. Each option shows how many lines on
   this tab match it (`badgeText`). Rows hide the same way search hides them: numbers and totals do
   not change. A line added (Duplicate, Add a line) or edited while the filter is on stays visible
   until the filter changes, so a row never vanishes under the caret (browser pass round 2: a
   rate typed below the minimum price used to hide the row mid-typing). Edit and view modes.

## Owner rulings (11 Nov 2026 ~14:45, answers to the card)

- Q1 yes: each "N lines are" count in the approval banner is a link. It sets the Flags filter to
  what it counts, opens the Header tab, and opens the first area tab (by sort order) whose current
  version holds such a line by its STORED flags (the ones the banner counts). The below-proposal
  count has no filter, so it stays text.
- Q2 yes: "Below minimum price" is a third filter option (stored / live `is_below_floor`), so every
  banner clause has its filter.
- Q3 yes: the filter stays on across area tabs. It is held by the page (document context on the
  read page, `FormLines` on the form page), not by the per-scope editor.

## Edge cases

- Combo / set line: duplicated as a set line (same set, same complete-set text); the server freezes
  the set parts on save as for any new set line. Badge: a set's default is its series set row, else
  the set's resolved list price.
- No default price (product not in the series and no list price): never below default.
- Zero rate: below default whenever a default exists (the save's rule); it usually also breaches the
  minimum price, so it shows the Minimum price pill instead. A blank rate mid-typing is "no price
  yet" for the live verdict, so no pill until a number is typed.
- Duplicate in a scope with several column groups and areas: every cell is copied, so the
  per-area quantities and the line total match the source.
- Duplicate on a section heading: not offered (the heading's menu is Rename / Remove section).
- Removed line: Duplicate disabled, like Insert.

## Elements -> existing components (no new layout, so no mock)

| Element | Component |
| --- | --- |
| Badge | `components/ui/badge` `Badge`, as `QuotationLineFlags.tsx:94` |
| Duplicate menu item | `DropdownMenuItem` (`QuotationLinesGrid.tsx:929`) and `ContextMenuItem` (`QuotationLinesGrid.tsx:2271`) |
| Filter | `components/common/SearchableMultiSelect` (as the Stage filter, `sales/opportunities/components/SalesOpportunitiesView.tsx:318`) |

## Slices

1. BE: `default_price_for` in `project_quotation_service.py` (used by `line_default_price` and by
   `_judge_line`), `is_discounted` on `QuotationLineVerdictResponse`. pytest first.
2. FE: `is_discounted` on the FE types; `lineFacts` pure function shared by the badges and the
   filter; "Below default price" badge; Duplicate line; Flags filter. vitest first.

## Triggers not built

- Tab counts: needs a count slot on `QuotationScopeTabs`; build when the owner asks for one.
