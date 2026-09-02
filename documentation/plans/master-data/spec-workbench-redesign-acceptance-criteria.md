# UAC - Spec workbench redesign (Product Specifications + Spec Verification)

**Companion to:** `PLAN-spec-workbench-redesign.md`
**Status:** Pre-code. Grill closed 2 Sep 2026 (record page, registry first, Try a phrase in Actions, no explainer prose, value labels folded in, ranking to Settings, Spec Verification in scope, no new motion).
**Folds in:** `spec-value-labels-acceptance-criteria.md` (#423) as Groups D and E. That file is SUPERSEDED by this one.
**Design language:** `documentation/reference/DESIGN-LANGUAGE.md` (PR #498). First feature to run the design slots of `/feature` end to end.
**Legend:** `[BE]` pytest · `[FE]` vitest · `[E2E]` agent-browser evidence · `[MIG]` migration · `[UX]` design-language check (measurable in the browser) · `[T]` CI guard.

## Journey

**Actor:** master-data staff with `master_data.spec_registry.view` (and `.edit` to change anything), on a laptop, a few times a week. They arrive from the sidebar, Master Data > Product Specifications, because search or a flyer derived a spec wrong, or a new product family needs a key.

1. The first screen is the registry: one row per spec key (label, type, unit, values, rules, seen in, source). A status line above the grid says when the catalogue was last read and whether rules changed since. They find the key with the list search.
2. They click the row and land on the key's record page. The header carries the label, the type and unit, the source pill, a prev/next pager over the list they came from, a gear (Delete, user-made keys only) and one primary button, Edit.
3. Three underline tabs: **Values and words**, **Rules**, **Seen in products**. Edit swaps every read-only value for an input in place, on every tab at once; Save sends one update; Cancel restores. In Values and words each value row has a display label input (folded #423), its customer words, and suppression with undo.
4. In Rules they read each rule as a sentence, reorder or add one while editing, and can try the rules on a product code or pasted text without leaving the page.
5. Back on the list, **Actions** holds Add key, Try a phrase and Reread catalogue. Try a phrase opens a lightbox: they type what a customer would say and see what the engine understood and which products it would rank, each product a link.
6. A second tab on the list page, **Needs a human**, lists catalogue exceptions; a row click opens that product's Specifications tab.
7. Ranking weights live under System Settings > Search ranking, not on this page.
8. On Spec Verification the flow is unchanged; Unverify no longer asks a question, the button becomes a countdown they can cancel.

They leave with one key corrected and, if rules changed, a catalogue reread queued. Nobody else needs telling. Nothing on the screen explains itself in prose; the how-to lives in the Outline guide.

## Decisions (locked 2 Sep 2026)

- **D1** Key = record page `/master-data-management/product-specifications/[specKey]`, view and edit share one layout (ADR 3). Inline row expansion is removed.
- **D2** First screen = registry DataGrid. Search preview moves into a lightbox behind Actions > Try a phrase.
- **D3** Every explanatory paragraph in the two routes is removed. Field-level helper text stays only where ADR 1e allows it (a unit hint, a placeholder). The how-to goes to an Outline guide (backlog).
- **D4** `spec-value-labels` (#423) is folded in as Groups D and E; its migration ships in this lane.
- **D5** Ranking tab moves to System Settings as a `search-ranking` tab rendering the existing editor. It keeps `master_data.spec_registry.*` on the API side.
- **D6** The Catalogue tab's global derived-specs table is removed. Per-product derived values are the product Specifications tab and the Spec Verification worklist. Exceptions stay, as the Needs a human tab.
- **D7** No new motion. Row expand no longer exists; tab switches and edit-mode toggles do not animate; lightboxes use the shared surface spring only. `find-animation-opportunities` was skipped by ruling.
- **D8** Spec Verification is in scope for the design pass and one behaviour change: Unverify (row and bulk) becomes a deferred action (5s reversible window) instead of an AlertDialog. Verify stays immediate.
- **D9** No single-key GET is added. The record page reads the key from the registry list query (ETag-cached, small) and the pager is page-scoped from that cache (design language D4).

## Group A - Registry list page (S1)

### AC-A.1 [FE] Page shell
`page.tsx` renders `PageHeader` (title "Product Specifications", crumbs derived from `MENU_SIDEBAR`, so Master Data > Product Specifications) and an Actions dropdown with exactly: Add key, Try a phrase, Reread catalogue. Add key and Reread catalogue are hidden without `master_data.spec_registry.add` / `.edit` respectively.

### AC-A.2 [FE] Registry grid
The Specifications tab is a `DataGrid` (`tableLayout: { width: 'fixed', columnsResizable: true }`, explicit `size` per column, `truncate` + `title` on Label). Columns in order: Label, Key, Type (pill), Unit, Values (count), Rules (count, "default" pill when `rules_are_default`), Seen in (`measured_coverage`), Source (pill seed/user). Sorted by Label. `ListSearchInput` filters on label, key and synonyms client-side. Row click navigates to the record page carrying the list state in the URL. No row "..." menu (a key has one secondary action, Delete, which lives in the record gear; design language D15 allows an entity with no row menu when the gear holds only Delete).

### AC-A.3 [FE] Freshness line
Above the grid one line: "Catalogue read {formatDateTimeInMalaysia(finished_at)}" plus a warning pill "Rules changed since" when `rules_changed_since_last_read`; "Never read" when `!ever_read`; "Reading..." with a spinner while `status == running` (poll every 3s until idle, the existing `CatalogueFreshness` logic moved into a hook). No paragraph of explanation.

### AC-A.4 [FE] Needs a human tab
Second `TabsList variant="line"` tab, badge = open count. A `DataGrid` over `GET /product-specifications/exceptions` with `DataGridPagination` (server paged, `buildDataGridParams`). Columns: Product code, Description, Spec key, Reason, Seen. Row click opens `/master-data-management/products/{product_id}?tab=specifications&back=<list url>`. The "Stored" JSON column is gone (the value renders through `readableEntry`, or "Not set").

### AC-A.5 [FE] Add key
Actions > Add key opens a `Dialog` (lightbox) with Label, Type (`SearchableSelect`), Unit; the key slug previews below the label; `/similar` near-duplicate warning stays. Submit POSTs, closes, toasts, and navigates to the new record page. `AddSpecKey.tsx`'s inline form and its duplicated type list are deleted; the dialog is the one in `components/spec-table/AddSpecificationDialog.tsx` reused, or that dialog's type list extracted to one module both import.

### AC-A.6 [FE] Try a phrase
Actions > Try a phrase opens a `Dialog` holding today's `SpecSearchPreview` body: phrase input, "what was understood" chips, ranked candidates with score and matched keys, each product a link to its record. Empty result renders "No product matched" with the phrase echoed. Closing clears nothing until the page unmounts (re-open shows the last run).

### AC-A.7 [FE] Data layer
All fetches move to react-query hooks in `hooks/`: `useSpecRegistryQuery` (list, `staleTime` 60s to match the ETag), `useSpecExceptionsQuery`, `useCatalogueStatusQuery`, `useSpecRegistryMutations` (create, update, delete, addValue, rereadCatalogue). Components hold no `useEffect` + `useState` fetch pairs. Mutations invalidate the registry query and toast via `extractApiError`.

### AC-A.8 [E2E] Sidebar walk
From `/`, sidebar Master Data > Product Specifications: grid renders the seeded keys, search narrows, Needs a human tab shows the count, Actions holds the three items. 375px and 1280px.

## Group B - Key record page (S2)

### AC-B.1 [FE] Route and header
`[specKey]/page.tsx` renders `PageHeader` (crumb trail ends in the key label) and a record card: label as title, key slug as secondary text, pills for type and source, unit as a field. `DetailActions` in the design-language order: `ListPager` (page-scoped from the registry list cache, "n / N"), gear, primary. Gear holds Delete only, and only when `source == user` and the user has `master_data.spec_registry.delete`; seed keys show no gear.

### AC-B.2 [FE] View and edit share one layout
Tabs, in order: Values and words, Rules, Seen in products (`TabsList variant="line"`, scrolls at 375px). Primary button "Edit" swaps every editable field on every tab for its input in place; the button becomes Save with a Cancel beside it. Nothing moves, appears or disappears between the two modes except the inputs. Save sends ONE `PATCH /spec-registry/{spec_key}` with `user_values`, `suppressed_values`, `user_synonyms`, `suppressed_synonyms`, `value_labels`, `derivation_rules`, `label`, `unit`, `max_value`; Cancel restores the last loaded row. Unsaved changes prompt via the browser `beforeunload` only (no custom dialog).

### AC-B.3 [FE] Values and words tab
One row per merged allowed value: display label input (Group E) with the automatic wording as placeholder, the slug in a muted `code` span, the customer words as `TokenInput` chips, suppress / restore per value. Suppressed values render struck through with an Undo chip. A value the user added carries the "user" pill. Empty state when the key has no values: "No values yet" + CTA "Add value" (opens the same add-value input). Boolean keys render the single "When true" row.

### AC-B.4 [FE] Rules tab
Each effective rule as a sentence (`lib/ruleSentence.ts`), shipped rules tagged with a "default" pill. Edit mode: dnd-kit reorder, add rule (`SpecRuleEditor` form), remove. "Try on a product" is available in both modes: a product code or pasted text, POST `/{spec_key}/try`, result rendered as "Would set {value} from {evidence}" or "No match". "Preview impact" (edit mode, after a rule change) POSTs `/{spec_key}/preview` and polls `/preview/{job_id}`, rendering changed counts. Empty state: "Using the shipped rules" when `rules_are_default`, with CTA "Edit" that enters edit mode on this tab.

### AC-B.5 [FE] Seen in products tab
Facets by value, by class, by source as pill rows (top 30, `PillList` +N expansion), then a `DataGrid` of products (Code, Description, Class, Value, Source, Evidence) with `DataGridPagination` over `limit`/`offset` (25/50/100). Filtering by a facet pill narrows the grid (`value=` / `q=` params). Row click opens the product's Specifications tab with `back=`. Empty state: "Not seen on any product yet" with CTA "Reread catalogue" (when `.edit`).

### AC-B.6 [FE] Delete
Gear > Delete runs through the deferred-action engine (`useDeferredAction`, 10s hard-delete window, System Settings governs) and on commit navigates back to the list with a toast; seed keys never expose it (backend also refuses).

### AC-B.7 [FE] Deep link and cache miss
Opening `/product-specifications/{specKey}` directly (no list in cache) fetches the registry list once, selects the key, and renders; an unknown key renders the standard not-found state with "Back to Product Specifications".

### AC-B.8 [E2E] Round trip
Sidebar walk to a key, Edit, change one value's words and its label, Save, reload: both persist (label persists after S4; in Phase 1 the mock echoes it). Pager walks to the next key and back. 375px and 1280px.

## Group C - Search ranking in System Settings (S3)

### AC-C.1 [FE] Tab
System Settings gains a `search-ranking` tab ("Search ranking") registered in `layout.tsx` `navRoutes`, page at `user-management/settings/search-ranking/page.tsx`, rendering the existing ranking editor moved to `components/SearchRankingSettings.tsx` (per-row numeric input, "Changed from {default}" pill, per-row Save). It uses `useSearchPolicyQuery` / `useSearchPolicyMutations` (react-query) against `/spec-registry/policy`. Without `master_data.spec_registry.view` the API 403 renders the standard error state; the tab is still listed.

### AC-C.2 [FE] Removal
The Ranking tab and `SearchTuning.tsx` are gone from Product Specifications. `config/menu.config.test.ts` and any test naming the Ranking tab updated.

### AC-C.3 [E2E] Sidebar walk
User Management > Settings > Search ranking: change `class_boost`, Save, reload, value persists; the pill shows "Changed from 5".

## Group D - Value labels storage and API (S4, from #423 AC-A)

### AC-D.1 [MIG] Column
`product_spec_registry.value_labels JSONB NOT NULL DEFAULT '{}'`. Existing rows read `{}`. `down_revision` = the head of origin/main at branch time (run `alembic heads` in the venv; must be exactly one). Downgrade drops it.

### AC-D.2 [BE] Read
`GET /master-data/spec-registry` rows carry `value_labels` as `{ "<slug>": "<label>" }`. A test asserts the field on the serialised response (lesson: undeclared fields vanish).

### AC-D.3 [BE] Write
`PATCH /spec-registry/{spec_key}` accepts `value_labels: dict[str, str]`. Editable on seed AND user rows (staff-owned, like `user_synonyms`). Labels are trimmed; an empty label drops the key; a key that is not one of the row's merged allowed values (or a synonym key for keys without a closed list) is rejected 422 `spec_registry_label_unknown_value`; length cap 60. The dict is reassigned on write (JSONB in-place mutation is not tracked).

### AC-D.4 [BE] Seed repair leaves labels alone
Given a seed row with `value_labels = {"pp": "PP"}`, when the startup seed repair runs, the label survives.

### AC-D.5 [BE] Permission
`value_labels` in the PATCH body needs `master_data.spec_registry.edit` (the in-body re-check the route already performs for fields outside `user_values`); 403 without.

## Group E - Value labels in the UI (S2 mock, S4 real)

### AC-E.1 [FE] `readableValue` / `readableEntry` take labels
`readableValue('pp', undefined, {pp: 'PP'})` -> `PP`; `readableValue('pp')` -> `Pp`; list values map element-wise; unit still appended; numbers and booleans unaffected.

### AC-E.2 [FE] Every value display uses the label
Product Specifications tab (`SpecTable` -> `SpecValueCell`, including enum option labels), `ProductProposalGroup`, `FlyerSpecReviewScreen`, `SpecVerificationList` (invalidation diff `title`), `SpecProposalReview`: a value with a label renders the label. Each screen reads labels from the registry it already loads, or `useSpecRegistryQuery`.

### AC-E.3 [E2E]
Set `PP` on Seat cover material, Save; open a Water Closet product whose seat material is `pp`; Specifications tab shows `PP`. Clear the label, Save, reload: `Pp`.

## Group F - Spec Verification alignment (S5)

### AC-F.1 [FE] Unverify is a deferred action
Row Unverify and "Unverify selected" no longer open an `AlertDialog`. Row: `DeferredActionButton` with the 5s reversible window; bulk: `useDeferredRowAction` + the aggregate `deferredToast` with cancel-all (the S6b bulk pattern). On commit the existing `unverifyBulk` mutation runs and patches the worklist cache as today.

### AC-F.2 [BE] Engine registration
If the deferred-action engine needs a server-side handler for `spec_verification.unverify` (check `form_action_registry` for how S6b registered deletes), it is registered with the reversible window and a pytest covers commit and cancel. If the engine is client-timed for reversible actions, no backend change; say which in the PR.

### AC-F.3 [FE] Design pass only
No other behaviour change. The design pass (Group G) runs over `SpecVerificationList.tsx`; findings are fixed in-branch only when they are Group G hard-fails, otherwise filed.

## Group G - Design language, both routes (cross-cutting, verified at S6)

### AC-G.1 [UX] No explainer prose
Grep of both routes for muted paragraphs (`text-muted-foreground` on a `<p>`) returns only: empty-state sublines, error details, and a field hint of one line. Count before: about 44 on product-specifications. Count after: at most 8 across both routes, each one named in the PR.

### AC-G.2 [UX] Primitives from the roster
No `<table` outside `DataGridTable`; no hand-rolled pager (`SpecKeyProducts` Prev/Next gone); every select is `SearchableSelect` (optional ones `clearable`); every list search is `ListSearchInput`; every popup is `Dialog`/`Sheet`; every page has `PageHeader`.

### AC-G.3 [UX] Empty states
Every grid and every tab body renders an explicit empty state with one CTA (A.4, B.3, B.4, B.5, A.6). No section is hidden on missing data.

### AC-G.4 [UX] No motion added
`git diff` of the lane contains no new `transition`, `animate-`, `motion.` or `cubic-bezier` outside `components/ui`. Tab switch and edit toggle are instant. Lightboxes open with the shared surface spring (inherited, not configured).

### AC-G.5 [UX] Breakpoints
Screenshots at 375px and 1280px for: list (both tabs), record page (three tabs, view and edit), Try a phrase dialog, Add key dialog, Search ranking tab, Spec Verification list. Nothing clipped; grids scroll sideways inside their container; tab strips scroll.

### AC-G.6 [UX] Identity and copy
No UUID visible (product ids only inside hrefs). Datetimes through `formatDateTimeInMalaysia`. Status and source as `Badge` pills. No `text-[Npx]`, `z-[N]`, `duration-[N]`.

### AC-G.7 [UX] Review artefact
The reviewer's report includes the `emil-design-eng` Before / After / Why table for the UI diff, and lists which findings were fixed in-branch versus filed.

### AC-G.8 [T] Tests
vitest: registry grid renders + filters + row href; record page view/edit toggle keeps field order (snapshot of field labels in both modes is identical); Values tab label input + payload; Rules tab try-on-product; Seen-in pagination params; Add key dialog; Try a phrase dialog empty state; Search ranking tab save; Spec Verification unverify countdown commit + cancel. pytest: D.2 to D.5, F.2 if applicable. Existing 54 Spec Verification tests stay green.

## Out of scope
- Outline user guide for the workbench (backlog; the prose removed in D3 is its raw material).
- Chatbot / MCP presenters keep slug wording (#423 out-of-scope carried over).
- A server GET for one key (D9); revisit when the registry exceeds one page.
- Motion improvements to either route (D7).
