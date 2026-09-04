# PLAN - Unified Drive for Resource Management → Files

**Status:** Design locked (grill complete) - not started.
**Route:** `app/(protected)/resource-management/attachment-directories/*` (in-place replace).
**Reference UX:** dreamz_ems drive (`dreamz_ems/documentation/plans/sprint-3/04-document-mgmt-drive.md`) + File Explorer.

## Problem

Current Files page (Resource Management → Files) splits navigation across two panes that
don't share a model:

- **Folders** (`attachment_directories`, self-nested via `parent_id`) live in the **left tree only**.
- **Files** (`attachments`, `directory_id` exact-match) live in the **right pane only**.
- Search filters `directory_id == current` exactly (`resources_service.py:563`) → **no subfolder descent**. To find a file in a subfolder you must manually drill into that subfolder.
- Folder navigation (left) and file navigation (right) are different surfaces → inconsistent, low usability.

Goal: a unified, File-Explorer-style Drive where folders and files coexist in one pane, navigation is consistent, and search reaches into subfolders.

## Locked design decisions (from grill)

| # | Decision |
|---|----------|
| **D1 - Deliverable** | Redesign sorento's existing Files page in place. dreamz is UX reference only. |
| **D2 - Nav model** | Keep left tree (jump-to + drag-move target). Right pane becomes the **primary** navigator: folders render as clickable rows/cards that drill in, with a **breadcrumb**. Selecting a tree node also drives the right pane; both panes navigate. |
| **D3 - Unified list** | Folders + files render as **one unified collection** in BOTH a **list view** and a **grid/card view** (Explorer-style). Folders are not a separate strip - they are items in the same list. |
| **D4 - Search scope** | Search is **recursive from the current folder** (current + all descendants). At root = whole drive. Backend already has the descendant CTE (`get_descendant_directory_ids`, `resources_service.py:186`). Optional "this folder only" narrow toggle. Empty query = browse (immediate children only); a query switches the pane to recursive subtree results. |
| **D5 - Search results** | Recursive results include **both matching files and matching folders**. Each result row shows a **Location/path** column. Click a folder hit → drill in; click a file hit → preview. "Reveal in folder" action jumps to a file's parent. Navigating into a folder **clears the active search**. |
| **D6 - Sort** | **Fully interleaved by Name** (default sort). Non-Name sorts (Size / Type / Modified / uploader) push folders to the **end** (no value for those columns). |
| **D7 - Filters / Export** | Any active file-attribute filter (Type / Access / Link status / Uploader / date) or a non-empty search **hides folders** (they can't match). Plain browse shows folders. **Export (xlsx) = files only** - folders excluded. |
| **D8 - Open action** | **Single click/tap** opens: folder → drill in; file → preview. Checkboxes own multi-select. Right-click (long-press on mobile) → context menu. No double-click. |
| **D9 - Drag-move** | Keep drag-onto-left-tree. **Add** drag a file/folder onto a folder row/card in the right pane, and onto a breadcrumb crumb, to move. Cycle-guarded (no folder into its own descendant). |
| **D10 - Root view** | Drive root = **top-level folders + `directory_id IS NULL` files**. No flat "all files" toggle - recursive search from root covers "find anything". |
| **D11 - Data fetch** | **New unified server endpoint** returns folders+files for a location (recursive when searching) as one **server-sorted, server-paginated** stream of discriminated rows; file rows carry their directory path. True interleave + correct at any folder size. |
| **D12 - View default** | **List view default**, grid toggle available, choice **persisted per-user**. |
| **D13 - Thumbnails** | Card view: `image/*` cards **lazy-load the real image** (`loading="lazy"` + IntersectionObserver, via existing CSP-sandbox serve route, CSS-scaled, CDN-cached). Non-images + folders → type icons. Real thumbnail pipeline = **backlog** (revisit if perf bites). |
| **D14 - Bulk actions** | Mixed folder+file selection allowed. All bulk actions collapse into **one "Action" dropdown button** (not separate toolbar buttons) - keep every existing action: **Export**, **Set access levels**, **Set attachment type**, **Resubmit selected**, **Delete selected**, plus **Move**. The dropdown shows only items valid for the current selection: shared actions (Move, Delete-with-folder-cascade) stay enabled on mixed selection; **file-only actions (Export, access levels, attachment type, Resubmit) are disabled/hidden when the selection contains a folder** (folders have no such attributes). Single-only actions (Rename, Replace) hidden when selection is multi. The "Action" button appears in the bulk bar once ≥1 item is selected. **Download-as-ZIP dropped** - no such endpoint/task exists in sorento today and it was not requested; out of scope (possible future follow-up, would need a backend ZIP job). |
| **D15 - Mobile (≤375px)** | Left tree → toggle **drawer**; right pane full-width with breadcrumb as primary nav. Single-tap opens, long-press = context menu. **Move via "Move to…" folder-picker dialog** (drag disabled on touch). Grid reflows to 2 columns. The "Move to…" dialog is also the universal non-drag move path on desktop (a11y). |
| **D16 - Scope** | **In-place replace, preserve all** existing features: access levels, polymorphic entity-linkages, attachment-types, bulk-import-ZIP, upload-activity drawer, my-downloads drawer, replace/resubmit, column preferences (`listing_key`). This is purely a nav + listing upgrade. |

## Defaults adopted without separate grill (sensible, Explorer-consistent)

- **Upload** targets the **current folder**; **New folder** creates a child of the current folder.
- **Location column** is shown only during recursive search; hidden while browsing.
- Drilling into a folder clears any active search query (D5).
- All current per-file context-menu actions are preserved for file rows; folders get: Open, Rename, Delete (cascade), Move to…, New subfolder.

## Affected code (from exploration)

**Frontend** (`sorento_crm_frontend/app/(protected)/resource-management/`):
- `attachment-directories/components/AttachmentDirectoriesView.tsx` - container, dnd context, resizable panes.
- `attachment-directories/components/DirectoryTreeSidebar.tsx` - left tree (kept; becomes drawer on mobile).
- `attachment-directories/components/AttachmentsInFolderPanel.tsx` - **right pane, rebuilt** into the unified list/grid + breadcrumb + recursive search + Location column.
- `attachment-directories/components/DraggableAttachmentsTable.tsx` - **extended** to render folder rows + be drop targets.
- `attachments/hooks/useAttachments.ts` - add unified-drive hook (`useDriveContents`) calling the new endpoint; keep existing hooks for other surfaces.
- New: grid/card view component, "Move to…" picker dialog (reuse SearchSelect/tree), view-mode persistence.

**Backend** (`sorento_crm_backend/`):
- `app/api/v1/resources/attachments.py` (list at :200) - add the new **unified drive endpoint** (folders+files, `directory_id`, `recursive`, `query`, sort/dir/page/limit, file filters). Reuse file-filter plumbing.
- `app/services/resources_service.py` - UNION query (folders ∪ files) with server sort/pagination + per-file directory-path resolution; reuse `get_descendant_directory_ids` (:186) for recursive; keep exact-match path (:563) for non-recursive browse.
- Attachment serializer - add `directory_path` for Location column.

## Build order (house three-phase methodology)

**Phase A - Frontend prototype (mock).** Rebuild the right pane against a mock `documentService`/`useDriveContents`: unified list + grid toggle (lazy image cards), breadcrumb, single-click drill/preview, recursive-search UX with Location column + reveal-in-folder, mixed multi-select + shared bulk bar, drag-move onto right-pane folders + crumbs + tree, "Move to…" dialog, mobile tree-drawer. Tune loading/empty/error/partial states. Verify ~1280px AND ~375px via Playwright MCP (sidebar-first nav). Document the unified-endpoint contract at the top of the service file.

**Phase B - Backend + wire.** Unified endpoint + UNION service query + `directory_path` serializer + recursive flag. Swap mock → real at the service boundary. Preserve all existing endpoints/features.

**Phase C - Tests + review.** pytest (recursive scope incl. descendants, root = top folders + null-directory files, interleave/sort, filters-hide-folders, Export-files-only, pagination over UNION, cycle-guard on move, mixed bulk delete cascade, tenant-scope isolation). Vitest (unified list/grid, breadcrumb, recursive-search render + Location, mixed selection, view-mode persistence, lazy-image card). Playwright `e2e/` (create nested folders → upload → recursive search finds a subfolder file → reveal-in-folder → drag-move → grid toggle → mixed bulk delete/restore). Test report + `/code-review` → PR.

## Open / confirm before code

- Deep-path breadcrumb collapse threshold (UI-only, no hard depth limit).
- View-mode persistence store: localStorage vs column-config `listing_key` row - confirm in Phase A.
- UNION pagination + per-file path resolution query shape - confirm in Phase B (watch N+1 on path).
