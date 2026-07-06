'use client';

import { Fragment, forwardRef, type ReactNode, type Ref } from 'react';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import { FileText, Folder } from 'lucide-react';
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from '@/components/ui/context-menu';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import DriveImageThumbnail from './DriveImageThumbnail';
import { isFileItem, type DriveItem } from '../../attachments/services/driveService';

function setRefs<T>(...refs: Array<Ref<T> | undefined>) {
  return (el: T | null) => {
    for (const ref of refs) {
      if (!ref) continue;
      if (typeof ref === 'function') ref(el);
      else (ref as { current: T | null }).current = el;
    }
  };
}

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

interface DriveCardProps {
  item: DriveItem;
  selected: boolean;
  draggable: boolean;
  currentDirectoryId: string | null;
  selectedIds: string[];
  onOpen: (item: DriveItem) => void;
  onToggleSelect: (id: string, next: boolean) => void;
}

/**
 * A single grid card. forwardRef + `...rest` spread so the Radix
 * `ContextMenuTrigger asChild` can inject its ref + onContextMenu/onPointer*
 * handlers onto the root div, giving cards the same right-click / long-press
 * menu as list rows (and suppressing the native browser context menu).
 */
const DriveCard = forwardRef<HTMLDivElement, DriveCardProps>(function DriveCard(
  props,
  radixRef
) {
  const {
    item,
    selected,
    draggable,
    currentDirectoryId,
    selectedIds,
    onOpen,
    onToggleSelect,
    ...rest
  } = props as DriveCardProps & Record<string, unknown>;
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

  const setRef = setRefs<HTMLElement>(
    (el) => {
      setDragRef(el);
      if (isFolder) setDropRef(el);
    },
    radixRef as Ref<HTMLElement>
  );

  return (
    <div
      ref={setRef}
      {...(draggable ? attributes : {})}
      {...(draggable ? listeners : {})}
      {...rest}
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
              thumbnailUrl={isFileItem(item) ? item.thumbnail_url : null}
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
});

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
  renderRowContextMenu,
}: {
  items: DriveItem[];
  selectedIds: string[];
  draggable: boolean;
  currentDirectoryId: string | null;
  onOpen: (item: DriveItem) => void;
  onToggleSelect: (id: string, next: boolean) => void;
  /** Builds the right-click / long-press context-menu items per card. */
  renderRowContextMenu?: (item: DriveItem) => ReactNode;
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
      {items.map((item) => {
        const card = (
          <DriveCard
            item={item}
            selected={selectedSet.has(item.id)}
            draggable={draggable}
            currentDirectoryId={currentDirectoryId}
            selectedIds={selectedIds}
            onOpen={onOpen}
            onToggleSelect={onToggleSelect}
          />
        );
        const key = `${item.kind}-${item.id}`;
        if (!renderRowContextMenu) return <Fragment key={key}>{card}</Fragment>;
        return (
          <ContextMenu key={key}>
            <ContextMenuTrigger asChild>{card}</ContextMenuTrigger>
            <ContextMenuContent className="w-52">
              {renderRowContextMenu(item)}
            </ContextMenuContent>
          </ContextMenu>
        );
      })}
    </div>
  );
}
