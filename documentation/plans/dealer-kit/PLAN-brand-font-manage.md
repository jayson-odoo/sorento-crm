# PLAN: Brand font management (rename + delete)

Status: Implemented, awaiting review (7 Sep 2026)
Branch: `feat/dealer-kit-font-manage` (worktree `.claude/worktrees/font-manage`)
UAC: `brand-font-manage-acceptance-criteria.md`

## Journey

A designer opens the price tag editor, opens the Font Family dropdown and sees
two brand fonts they no longer want (`centurygothic`, `Century Gothic Bold`).
Today there is no way to remove or rename them: the inspector only has
"Upload font", the backend only has list + upload. The captain's ask (7 Sep):
"we need UI ... renaming, deleting also need".

## What exists (measured on origin/main 59dffc60d)

- Brand font = `dealer_kit.asset` row with `kind='font'` + `attachments` row +
  bytes in storage. Listed by `listFontAssets()` and appended to
  `STATIC_FONT_OPTIONS` in `useKitLibrary` (`useTagBindings.ts`).
- **A text layer stores the font by NAME** (`props.fontFamily`), never by asset
  id. `asset_service.referenced_asset_ids` scans docs for asset IDS, so it says
  "unreferenced" for every font. A font guard has to match on family name.
- Documents holding text layers: `tag_template.doc` (layers), `page_version.doc`
  (tag sheets: `sheets[].tags[].layers[]`), `page.draft_doc` (same shapes).
  Walkers: `tag_sheet_asset_ids` / `_layer_asset_ids` in `asset_service.py`;
  containment shapes: `_tag_layer_shapes`.
- Row deletion + byte purge already exist: `delete_unreferenced` (rows, in the
  caller's transaction, asset before attachment) and `purge_objects` (after
  commit). Reuse both.
- `FontUploadDialog.tsx` is opened from `InspectorPanel`'s "Upload font" ghost
  button, wired in `TagCanvasEditor.tsx` (lines ~400, ~3477, ~3577) with
  `library.remember(asset)` on success.
- Permission: `dealer_kit.library.manage` gates list + upload. Reuse it for
  rename + delete. No new permission, no grant sweep.

## Design (simplest thing that works)

### Backend (`app/api/v1/dealer_kit/assets.py`, `app/services/dealer_kit/asset_service.py`)

1. `PATCH /api/v1/dealer-kit/assets/{asset_id}` body `{"name": str}` → `AssetResponse`.
   - 404 if the asset is not visible in scope. 422 if the trimmed name is empty
     or over 200 characters (the `Asset.name` column ceiling - rejected, never
     silently sliced, or the row and the rewritten docs would disagree about
     the family's own name).
   - For `kind='font'`: 409 `FONT_NAME_TAKEN` if another font asset (same company)
     already carries the new name (two `@font-face` rules for one family would be
     ambiguous). Then rename the row AND rewrite `props.fontFamily == old` to the
     new name in every doc that names it: `tag_template.doc`, the published
     `tag_template_version.doc` (Restore copies a version's doc straight back
     into the draft, so a font only an old version still names has to track a
     rename too), `page_version.doc`, `page.draft_doc`. Same transaction. Scoped
     to the RENAMED ASSET'S OWN COMPANY (`company_scope(db, frozenset({company_id}))`,
     never `company_scope(db, None)`) - unlike `referenced_asset_ids`'s
     deliberately global guard, a font's name is not unique across companies, so
     a global rewrite would silently touch another company's identically-named
     font. `PageVersion`/`TagTemplateVersion` are not themselves company-owned,
     so each is joined to its parent (`Page`/`TagTemplate`) so the company
     predicate has a `CompanyScopedMixin` mapper in the statement to attach to.
     An asset with no resolvable company scopes to zero rows, never every
     company. Use jsonb containment to find candidate docs, then walk + rewrite
     in Python and reassign the column (`flag_modified`) so SQLAlchemy sees the
     change.
   - For any other kind: rename the row only (docs hold the id, AC-D3).
2. `DELETE /api/v1/dealer-kit/assets/{asset_id}` → 204.
   - 404 if not visible.
   - For `kind='font'`: 409 `FONT_IN_USE` when any of the FOUR documents above
     has a text layer whose `props.fontFamily` equals the asset name, read
     under the same own-company scope as the rename. Message names up to 5
     template titles, e.g. `Still used by: Standard 70x38, Promo A6`. Tag
     sheets with no title count as "a price tag request".
   - For any other kind: 409 `ASSET_IN_USE` when `referenced_asset_ids` names it.
   - Otherwise `delete_unreferenced` + commit + `purge_objects`.
3. New service helpers, next to the existing walkers so the doc shape lives in
   one place: `_font_family_shapes(name)` (mirror of `_tag_layer_shapes`, holder
   `{"fontFamily": name}`), `font_family_users(db, name, company_id) -> list[str]`
   (titles), `rename_font_family(db, old, new, company_id) -> int` (docs
   rewritten).

No migration. No new table. No new permission.

### Frontend

1. `services/assetService.ts`: `renameAsset(id, name)` and `deleteAsset(id)`,
   both through `lib/api-client` + `extractApiError`.
2. `FontUploadDialog.tsx` becomes the one "Brand fonts" dialog (keep the file
   name, retitle). Top: the list of brand fonts, each row shows the name
   rendered in its own family, a pencil (inline rename input, Enter/Save,
   Escape/Cancel) and a trash. Trash becomes a deferred countdown delete (`DeferredActionButton` / `useDeferredAction`, D7: no confirm dialog, `ConfirmDeleteDialog` is retired); a 409 shows
   the backend message in the toast. Empty state: "No brand fonts yet". Bottom:
   the existing upload form unchanged. Static Google fonts are NOT listed (they
   are not assets and cannot be managed).
3. Inspector button label `Upload font` → `Manage fonts`. Prop name
   `onUploadFont` stays (fewer touched lines).
4. `useKitLibrary` gains `forget(id)` and `rename(id, name)` so the dropdown
   updates without a round trip; `reload()` still runs after every mutation so
   the list matches the server.
5. `TagCanvasEditor.tsx`: on rename, rewrite `props.fontFamily === old` to the
   new name in the OPEN document's layers (unsaved edits must not save the dead
   name back). On delete of a font the open doc uses, the backend refuses, so
   nothing to do client-side.
6. The public print page loads fonts by name from `font_assets()`; after a
   rename both the asset name and every doc agree, so nothing changes there.

## Tests

Backend (`tests/test_dealer_kit_font_manage.py`, Postgres via `tests/_pg_fixture.py`,
seed users/roles the way `test_dealer_kit_tag_assets.py` does, storage via
`tests/_fake_storage.patch_storage`):

- rename font rewrites a template doc AND a tag-sheet page_version AND page.draft_doc; asset name changes; response carries the new name
- rename rewrites a published `tag_template_version.doc` (a font only an old version still names)
- rename does not touch another company's identically-named font or template
- rename to an existing font name → 409 `FONT_NAME_TAKEN`
- rename a non-font asset only changes the row
- delete unreferenced font → 204, asset + attachment rows gone, both storage objects purged
- delete a font used by a template → 409 `FONT_IN_USE`, message contains the template title, rows untouched
- delete is refused when only a published template version names the font
- delete is not blocked by another company's identically-named template
- delete a badge referenced by a template → 409 `ASSET_IN_USE`
- outsider without `dealer_kit.library.manage` → 403 on both routes

Frontend (vitest):

- `assetService.test.ts`: `renameAsset` sends PATCH with `{name}`; `deleteAsset` sends DELETE; both surface `extractApiError` messages
- `FontUploadDialog.test.tsx`: lists fonts; rename saves on Enter and calls `onRenamed(asset, oldName)`; trash → countdown lapses → `onDeleted(id)`; Cancel during the countdown keeps the row; a 409 on delete toasts the backend message and keeps the row
- `useTagBindings.test.tsx`: `forget` drops the option; `rename` swaps the label

## Phases

- Phase 1 FE against a mocked service (dialog, inspector label, library hooks).
- Phase 2 BE test-first (pytest red → green), then swap the mock for the real service.
- Phase 3 `/code-review`, browser verification on the dev server, DoD gate, PR.
