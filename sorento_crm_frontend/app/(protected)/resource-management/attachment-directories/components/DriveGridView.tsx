'use client';

import { useDraggable, useDroppable } from '@dnd-kit/core';
import { FileText, Folder } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import DriveImageThumbnail from './DriveImageThumbnail';
import { isFileItem, type DriveItem } from '../../attachments/services/driveService';

const DND_ID_ATTACHMENT_PREFIX = 'attachment-';
// Distinct from the tree's `folder-` ids (must match DND_ID_GRID_FOLDER_PREFIX
// in AttachmentDirectoriesView) so a folder in both panes has unique dnd ids.
const DND_ID_GRID_FOLDER_PREFIX = 'gridfolder-';

function isImage(item: DriveItem): boolean {
  return isFileItem(item) && !!item.mime_type && item.mime_type.startsWith('image/');
}

function itemLabel(item: DriveItem): string {
  return isFileItem(item)
    ? item.stored_filename || item.original_filename
    : item.name;
}

function DriveCard({
  item,
  selected,
  draggable,
  currentDirectoryId,
  selectedIds,
  onOpen,
  onToggleSelect,
}: {
  item: DriveItem;
  selected: boolean;
  draggable: boolean;
  currentDirectoryId: string | null;
  selectedIds: string[];
  onOpen: (item: DriveItem) => void;
  onToggleSelect: (id: string, next: boolean) => void;
}) {
  const isFolder = item.kind === 'folder';
  const dndId = isFolder
    ? `${DND_ID_GRID_FOLDER_PREFIX}${item.id}`
    : `${DND_ID_ATTACHMENT_PREFIX}${item.id}`;

  const batchIds = selected && selectedIds.length > 1 ? selectedIds : [item.id];
  const {
    attributes,
    listeners,
    setNodeRef: setDragRef,
    isDragging,
  } = useDraggable({
    id: dndId,
    disabled: !draggable,
    data: isFolder
      ? { type: 'folder', directoryId: item.id, folderName: item.name }
      : {
          type: 'attachment',
          attachmentId: item.id,
          attachmentName: itemLabel(item),
          currentDirectoryId: currentDirectoryId ?? null,
          attachmentIds: batchIds,
        },
  });

  // Folders are drop targets in grid view too (UAC E1).
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: dndId,
    data: { type: 'folder', directoryId: item.id },
    disabled: !isFolder,
  });

  const setRef = (el: HTMLElement | null) => {
    setDragRef(el);
    if (isFolder) setDropRef(el);
  };

  return (
    <div
      ref={setRef}
      {...(draggable ? attributes : {})}
      {...(draggable ? listeners : {})}
      data-testid={`drive-card-${item.kind}`}
      className={cn(
        'group relative flex flex-col rounded-lg border bg-card text-left transition-colors',
        'hover:border-primary/50',
        selected && 'ring-2 ring-primary',
        isOver && 'ring-2 ring-primary ring-inset bg-primary/10',
        isDragging && 'opacity-50',
        draggable && 'cursor-grab active:cursor-grabbing'
      )}
    >
      <div
        className="absolute start-2 top-2 z-10"
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <Checkbox
          checked={selected}
          onCheckedChange={(v) => onToggleSelect(item.id, v === true)}
          aria-label={`Select ${itemLabel(item)}`}
        />
      </div>
      <button
        type="button"
        className="flex flex-1 flex-col"
        onClick={() => onOpen(item)}
        title={itemLabel(item)}
      >
        <div className="flex aspect-square items-center justify-center overflow-hidden rounded-t-lg bg-muted">
          {isFolder ? (
            <Folder className="size-12 text-muted-foreground" />
          ) : isImage(item) ? (
            <DriveImageThumbnail
              attachmentId={item.id}
              alt={itemLabel(item)}
              className="h-full w-full"
            />
          ) : (
            <FileText className="size-12 text-muted-foreground" />
          )}
        </div>
        <div className="p-2">
          <p className="truncate text-sm" title={itemLabel(item)}>
            {itemLabel(item)}
          </p>
        </div>
      </button>
    </div>
  );
}

/**
 * Grid/card view for the Unified Drive (UAC A4). Renders the SAME folders+files
 * collection as the list view. Reflows to 2 columns at phone width (UAC H4) and
 * scales up on wider viewports.
 */
export default function DriveGridView({
  items,
  selectedIds,
  draggable,
  currentDirectoryId,
  onOpen,
  onToggleSelect,
}: {
  items: DriveItem[];
  selectedIds: string[];
  draggable: boolean;
  currentDirectoryId: string | null;
  onOpen: (item: DriveItem) => void;
  onToggleSelect: (id: string, next: boolean) => void;
}) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
        <Folder className="size-10 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">This folder is empty.</p>
      </div>
    );
  }

  const selectedSet = new Set(selectedIds);
  return (
    <div className="grid grid-cols-2 gap-3 p-1 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {items.map((item) => (
        <DriveCard
          key={`${item.kind}-${item.id}`}
          item={item}
          selected={selectedSet.has(item.id)}
          draggable={draggable}
          currentDirectoryId={currentDirectoryId}
          selectedIds={selectedIds}
          onOpen={onOpen}
          onToggleSelect={onToggleSelect}
        />
      ))}
    </div>
  );
}
