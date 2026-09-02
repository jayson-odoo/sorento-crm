# PLAN - Spec workbench redesign: registry list, key record page, value labels, ranking to Settings, verification countdown

> The design that fulfils `spec-workbench-redesign-acceptance-criteria.md`. That file is the contract; where this plan and the UAC disagree, the UAC wins.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md` + `documentation/reference/DESIGN-LANGUAGE.md` (PR #498).

**Slug:** `spec-workbench-redesign` | **Domain:** master-data
**Status:** S1 (Group A, registry list page) done at `c21422438`. S2 (Group B record page + E.1/E.2 value labels, `value_labels` mocked per D9) done at `769c8d7d4` - record page (`[specKey]/page.tsx`) with the three tabs sharing one view/edit layout, `useSpecKeyRecord`'s one-PATCH save, Delete wired to `useDeferredAction` (needs a backend `spec_key.delete` record-action handler before it can actually commit - not registered here, out of scope for a Phase 1 FE slice), `readableValue`/`readableEntry` take value labels and every E.2-listed consumer reads them; `SpecKeyEditor.tsx`/`SpecKeyProducts.tsx` deleted. S3 (Search ranking in Settings) is next; browser verification for S2 deferred to the tester.
**Lane:** worktree `.claude/worktrees/spec-workbench-redesign`, branch `feat/spec-workbench-redesign` from `origin/main` (f09532f6c). PR #498 (design-language reference) merged 2 Sep and merged into this lane.
**Folds in:** `PLAN-spec-value-labels.md` (#423), now SUPERSEDED.
**Pilot for:** the design slots added to `/feature` by #498 (design brief, `[UX]` ACs, animate gate, emil-design-eng review table).

## 1. What is being built, in one paragraph

Two routes brought onto the design language. `/master-data-management/product-specifications` becomes a registry list (DataGrid, PageHeader, a primary Add specification button, an Actions dropdown holding Try a phrase / Reread catalogue, a one-line freshness status) and each key gets a record page at `/[specKey]` with the standard record card (pager, gear, Edit) and three underline tabs whose view and edit modes share one layout. The value display label from #423 ships inside that record page. The ranking editor moves to System Settings. Spec Verification keeps its flow and swaps its Unverify confirm dialog for the deferred-action countdown. Every explanatory paragraph goes. No new motion.

## 2. Why now (evidence, measured 2 Sep 2026 against origin/main)

- Product Specifications: 17 files, all editing by inline row expansion, no `PageHeader`, no `Dialog`, no `ListPager`, no react-query (every panel hand-rolls `useEffect` + `useState`), two hand-rolled `<table>`s (`ProductSpecsList.tsx:71-90`, `SpecKeyProducts.tsx:~175-195`), a hand-rolled Prev/Next pager (`SpecKeyProducts.tsx:205-225`), `JSON.stringify(row.stored)` shown to users (`ProductSpecsList.tsx:84`), no empty state in `SearchTuning` and `SpecKeyProducts`, breadcrumb stops at Master Data, pagination disabled by design, about 44 muted explainer paragraphs, `AddSpecKey` has a Dialog-shaped API but renders inline and duplicates the type list held in `components/spec-table/AddSpecificationDialog.tsx`. Three of these are PRINCIPLES hard-fails today.
- Spec Verification: already on the language (DataGrid, PageHeader, react-query, empty states, complete crumbs, 54 tests). One deviation from design-language D7: Unverify still confirms through an `AlertDialog`.
- #423 (value labels) is approved and unbuilt; its only UI slot is the value row of `SpecKeyEditor`, which this plan replaces, so building it separately would be built twice.
- Backend already has everything the record page needs except the label column: list with ETag, PATCH, DELETE (refuses seed), `/{spec_key}/products` with facets and offset paging, `/{spec_key}/try`, `/{spec_key}/preview`, `/similar`, `/policy`, `/catalogue-status`, `/reread-catalogue`, `/product-specifications/exceptions` (paged). No single-key GET; the list is 37 rows and cached, so the record page reads it (D9).

## 3. The design

### 3.1 Route and file layout (`sorento_crm_frontend/app/(protected)/master-data-management/product-specifications/`)

```
page.tsx                          PageHeader + Add specification + Actions + <SpecRegistryPage/>
[specKey]/page.tsx                record page
components/
  SpecRegistryPage.tsx            freshness line + grid
  SpecRegistryGrid.tsx            DataGrid of keys (A.2)
  CatalogueFreshnessLine.tsx      one line + pill (A.3)
  AddSpecificationDialog          (A.5) thin wrapper over spec-table/AddSpecificationDialog, or that dialog used directly
  TryPhraseDialog.tsx             (A.6) wraps the SpecSearchPreview body
  record/SpecKeyRecordCard.tsx    identity + DetailActions (B.1)
  record/ValuesAndWordsTab.tsx    (B.3)
  record/RulesTab.tsx             (B.4) hosts SpecRuleEditor + TryOnProduct + PreviewImpact
  record/SeenInProductsTab.tsx    (B.5) search by code + facets + paged grid
  SpecRuleEditor.tsx              kept (dnd reorder + SearchableSelect), loses its prose
  TokenInput.tsx, PillList.tsx    kept
hooks/
  useSpecRegistryQuery.ts         list (staleTime 60s), selectKey(specKey)
  useKeysForProductQuery.ts       debounced /keys-for-product?code= for the list search (A.2)
  useSpecRegistryMutations.ts     create / update / delete / addValue / rereadCatalogue
  useCatalogueStatusQuery.ts      3s polling while running
  useSpecKeyProductsQuery.ts      facets + page
  useSpecKeyRecord.ts             edit-mode draft state, one PATCH on save (B.2)
services/productSpecService.ts    kept; value_labels added to the PATCH payload type; contract block at the top updated
types/productSpec.types.ts        + value_labels: Record<string,string>
lib/ruleSentence.ts, lib/vocabularyEdit.ts  kept
```

Deleted: `SpecWorkbench.tsx`, `SpecRegistryTable.tsx`, `SpecKeyEditor.tsx` (its logic is split into the three tabs + `useSpecKeyRecord`), `SpecKeyProducts.tsx`, `ProductSpecsList.tsx`, `AddSpecKey.tsx`, `SearchTuning.tsx` (moved), `CatalogueFreshness.tsx` (moved into the line + hook), `SpecSearchPreview.tsx` (body moves into the dialog). Their tests move with the logic; `SpecKeyEditor.suppressedWords.test.tsx` becomes `ValuesAndWordsTab.test.tsx`.

### 3.2 Record page state (B.2)

`useSpecKeyRecord(specKey)` returns `{ row, draft, mode: 'view' | 'edit', edit(), cancel(), save(), setDraft }`. `draft` is the editable projection (`label`, `unit`, `max_value`, `user_values`, `suppressed_values`, `user_synonyms`, `suppressed_synonyms`, `value_labels`, `derivation_rules`), seeded from `row` on `edit()`. `save()` builds one `PATCH` body from the draft diff (only changed fields), calls `updateSpecKey`, invalidates the registry query, returns to view. The three tabs read `mode` and render either the value or the input for each field, same order, same wrapper, so the "field labels in both modes are identical" snapshot test (G.8) holds by construction. Field-level components take `(value, mode, onChange)`; no tab owns fetch state.

### 3.3 Pager (B.1)

`ListPager` over `useSpecRegistryQuery` rows in the list's current sort and filter (carried in the URL by `useListStateFromUrl`, the S3 apple-alignment hook). Client-side list, so "next on the last row" simply ends; no page-boundary fetch.

### 3.4 Try a phrase (A.6) and Try on a product (B.4)

Both are read-only calls that already exist (`/product-specifications/preview-search`, `/spec-registry/{spec_key}/try`). Results render as a compact list, never a paragraph. The dialog keeps its last result in component state for the page's lifetime.

### 3.5 Search ranking in Settings (C)

`user-management/settings/layout.tsx` `navRoutes` gains `'search-ranking': { title: 'Search ranking', icon: SlidersHorizontal, path: '/user-management/settings/search-ranking' }`. `search-ranking/page.tsx` renders `components/SearchRankingSettings.tsx` (today's `SearchTuning.tsx` with react-query hooks and the prose removed). It does not use `SettingsProvider`; its data is the spec-registry policy API, same permission slugs as today.

### 3.6 Value labels (D, E)

Exactly the folded plan: one JSONB column `value_labels` on `product_spec_registry`, `_serialise` adds it, `SpecKeyUpdate` accepts it with the 422 `spec_registry_label_unknown_value` validation, reassign on write. `lib/spec-readable.ts` `readableValue(value, unit?, labels?)` / `readableEntry(entry, labels?)`. Readers listed in AC-E.2 pass `labelsByKey` built from the registry they already hold.

### 3.7 Spec Verification (F)

`SpecVerificationList.tsx`: the row Unverify becomes `DeferredActionButton` (reversible window); bulk uses `useDeferredRowAction` + `deferredToast`. The `AlertDialog` and its state go. The Coverage cell gains the `open_exceptions` warning pill (F.4, D11): the field is already fetched and typed, never rendered. Backend: read `app/services/form_action_registry.py` (or wherever S6b registered `delete` handlers) before deciding F.2; the plan's expectation is that reversible actions are client-timed and need no handler, in which case F.2 is a one-line PR note.

### 3.8 Copy (D3, D10, G.1)

Type wording map, one module `lib/specTypeLabel.ts`: `enum` -> Choice, `number` -> Number, `boolean` -> Yes or no, `string` -> Text. Every pill and select option reads through it.

Every `<p className="text-muted-foreground">` in both routes is deleted unless it is an empty-state subline, an error detail, or a one-line field hint. Column and field labels carry the meaning ("Words customers say", "Seen in", "Rules changed since"). The removed text is pasted into `documentation/backlogs/backlog.md` under "Outline guide: Product Specifications workbench" so the guide author has it.

### 3.9 Motion (D7)

None added. Inherited only: lightbox surface spring, pressed states from `PRESSED_CLASS`. The frequency gate says this is a tens-per-week staff surface; nothing here earns motion.

## 4. Slices and order

| Slice | Phase | Scope | Executor |
| --- | --- | --- | --- |
| S1 | 1 (FE, mocks only for `value_labels`) | Group A: list page, freshness line, Add specification + Try a phrase dialogs, react-query hooks; delete the old shell | coder (Sonnet), worktree = lane |
| S2 | 1 | Group B + E.1/E.2 with `value_labels` mocked on the registry response: record page, three tabs, edit-in-place, pager, delete via deferred action | coder (Sonnet) |
| S3 | 1 | Group C: Search ranking tab, remove Ranking tab | coder (Sonnet), can run with S2 if a second slot is free |
| S4 | 2 (BE, test-first) | Group D: migration, model, serialise, PATCH validation, tests; swap the S2 mock; E.3 | coder (Sonnet) |
| S5 | 1 + 2 | Group F: Spec Verification unverify countdown, exceptions pill (F.4) (+ F.2 handler if needed) | coder (Sonnet) |
| S6 | 3 | Group G: reviewer (Opus) with the emil-design-eng table, browser evidence at both widths, DoD gate | reviewer + tester |

Browser verification per slice with agent-browser, sidebar walk from `/`, own `--session` name, both widths. One verification sweep per slice (30 Aug rigour ruling): blockers fixed in-branch, the rest filed.

### 4.1 Where each slice comes from

S1, S2, S3: the grill of 2 Sep (record page, registry first, Actions dropdown, prose out, ranking to Settings). S4, E: #423. S5: design-language D7 applied to the sibling page the user ruled in. S6: `/feature` step 8 + 9 with the new design pass.

## 5. Testing seams (agreed before Phase 2)

- `productSpecService.ts` is the only module that knows URLs; hooks are tested with a mocked service, components with mocked hooks (the DataGrid rows need `useListingColumnPreferences` mocked in jsdom, per memory).
- `useSpecKeyRecord` is a pure state hook: tested with `renderHook` for edit / cancel / save-diff.
- Backend: `tests/test_spec_registry_pr2_routes.py` owns the PATCH; D.2 to D.5 land there against Postgres (`tests/_pg_fixture.py`), seeding the registry row in-test (CI has no data).
- Spec Verification: the existing 54 tests are the regression net; the countdown gets two new tests (commit, cancel).

## 6. Not built (deferred to `documentation/backlogs/backlog.md`)

- Outline guide for the workbench (raw material = the removed prose).
- Single-key GET endpoint (trigger: registry beyond one page, or a deep link that must not pay for the list).
- 200ms menu spring preset (design-language ruling, separate follow-up).
- Chatbot / MCP presenters using value labels.

## 7. Risks

- **Scope creep inside S2.** The record page absorbs `SpecKeyEditor` (532 lines) and `SpecRuleEditor`; keeping their behaviour while re-homing it is the biggest slice. Mitigation: `useSpecKeyRecord` is written first, tabs are thin; the existing suppressed-words test is ported before the old file is deleted.
- **Alembic head.** `down_revision` must be the single head of origin/main at S4 time; re-check `alembic heads` before the PR (memory: dual-head).
- **Deferred delete for a seed key.** Backend refuses; the UI never offers it (B.1). A test asserts the gear is absent for `source == seed`.
- **Settings tab without the spec permission.** A settings viewer without `master_data.spec_registry.view` sees the error state on one tab. Accepted (C.1); revisit if a real role hits it.
- **#498 not yet merged.** The coder brief points at the reference by path on `docs/design-language-S0` until it lands.
