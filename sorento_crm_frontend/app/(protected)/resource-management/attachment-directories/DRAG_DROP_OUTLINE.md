# Drag-and-Drop: Move Attachments to Folders (Outline)

## Goal

On the Attachment Directories page, allow users to **drag an attachment row** from the table and **drop it onto a folder** in the left sidebar (or "All attachments") to move that attachment into that folder. The backend already supports this via `PUT /attachments/{id}` with `{ directory_id: string | null }`.

## Tech Stack

- **@dnd-kit/core** (already in the project): `DndContext`, `useDraggable`, `useDroppable`, `PointerSensor`/`MouseSensor`/`TouchSensor`, `DragEndEvent`, `DragOverEvent` (optional).
- No need for `@dnd-kit/sortable` here - we are not reordering; we are drag-from-table, drop-on-folder.

## Data Model for DnD

- **Draggable** (attachment row): `id` = `attachment-${attachment.id}`, `data` = `{ type: 'attachment', attachmentId, attachmentName }`.
- **Droppable** (folder item): `id` = `folder-${directoryId}` (use `folder-all` for "All attachments" when `directoryId` is null), `data` = `{ type: 'folder', directoryId: string | null }`.

## Implementation Steps

### 1. Backend / API (no change)

- `PUT /api/v1/resource-management/attachments/{attachment_id}` with body `{ directory_id: string | null }` is already implemented and updates the attachment’s folder.

### 2. Frontend: API and hook

- **attachmentService.ts**  
  Add `updateAttachment(attachmentId: string, data: { directory_id?: string | null }): Promise<Attachment>` that calls `PUT .../attachments/${attachmentId}` with JSON body.

- **useAttachments.ts**  
  Add `useUpdateAttachment()`: `useMutation` that calls `updateAttachment`, and on success invalidates `['attachments']` and `['attachment-directories-tree']` (optional), and shows a toast (e.g. "Moved to folder").

### 3. Wrap the view in a single DndContext

- **AttachmentDirectoriesView.tsx**  
  Wrap the entire layout (sidebar + right panel) in one `<DndContext>`. Use `sensors` (e.g. `MouseSensor`, `TouchSensor` with a small activation constraint so clicks don’t start drag).  
  **onDragEnd**: read `active.id` and `over?.id`; if `over` is a folder droppable, parse `attachmentId` and `directoryId` from the ids/data, then call `updateAttachment(attachmentId, { directory_id: directoryId })`. If the user dropped outside any droppable, do nothing.

### 4. Sidebar: make each folder a droppable

- **DirectoryTreeSidebar.tsx**  
  For each folder row (and the "All attachments" row), render a **droppable**:
  - Use `useDroppable({ id: 'folder-${node.id}' or 'folder-all', data: { type: 'folder', directoryId: node.id ?? null } })`.
  - Attach `setNodeRef` and `isOver` to the row container (or a wrapper) so the row can show a visual “drop target” state (e.g. highlight when `isOver`).
  - "All attachments" uses `id: 'folder-all'`, `data: { type: 'folder', directoryId: null }`.

### 5. Attachment table: make each row draggable

- **AttachmentsInFolderPanel.tsx**  
  For each attachment row (or a drag handle in the first column):
  - Use `useDraggable({ id: 'attachment-${attachment.id}', data: { type: 'attachment', attachmentId: attachment.id, attachmentName: attachment.original_filename } })`.
  - Attach `setNodeRef`, `listeners`, `attributes` to the row (or to a drag-handle button so only the handle starts the drag).
  - Optional: show a drag handle icon (e.g. `GripVertical`) so it’s clear the row is draggable; apply `listeners` and `attributes` only to that handle.
  - When `isDragging`, apply a style (e.g. opacity, transform) so the row looks like it’s being dragged; you can use a custom drag overlay in the DndContext if you want a floating preview.

### 6. Drag overlay (optional)

- In **AttachmentDirectoriesView** (or a child), use `<DragOverlay>` from `@dnd-kit/core` to render a small card (e.g. filename + icon) while dragging. Use `active?.data` to get the attachment name.

### 7. Edge cases and UX

- **Same folder**: If dropped on the same folder the attachment is already in, either no-op or still call the API (idempotent). Prefer no-op to avoid unnecessary requests.
- **Disabled / no permission**: If the app later adds permissions, disable drag or drop when the user cannot move attachments.
- **Toast**: On success, toast “Moved to [folder name]” or “Moved to All attachments”. On error, toast the error from the mutation.
- **Optimistic update**: Optional: optimistically update the attachment’s `directory_id` in the cache so the list updates immediately; revert on mutation error.

## File Summary

| File | Change |
|------|--------|
| `attachments/services/attachmentService.ts` | Add `updateAttachment(id, { directory_id })`. |
| `attachments/hooks/useAttachments.ts` | Add `useUpdateAttachment()` with cache invalidation and toast. |
| `attachment-directories/components/AttachmentDirectoriesView.tsx` | Wrap layout in `DndContext`; handle `onDragEnd` and call `updateAttachment` when drop target is a folder. |
| `attachment-directories/components/DirectoryTreeSidebar.tsx` | For each folder row and "All attachments", add `useDroppable`; optional `isOver` styling. |
| `attachment-directories/components/AttachmentsInFolderPanel.tsx` | For each attachment row (or a handle), add `useDraggable`; optional drag handle icon and drag overlay. |

## Order of Implementation

1. Add `updateAttachment` and `useUpdateAttachment`.
2. Add `DndContext` in `AttachmentDirectoriesView` with `onDragEnd` calling the mutation (you can temporarily use a button or console to test the mutation).
3. Add droppables in `DirectoryTreeSidebar`.
4. Add draggables in `AttachmentsInFolderPanel`.
5. Add drag handle and/or overlay and polish (same-folder no-op, toasts, styling).
