'use client';

import {
  Search,
  Download,
  Trash2,
  RefreshCw,
  RotateCcw,
  Tag,
  Plus,
  Pencil,
  FolderInput,
  FolderOpen,
  CornerUpLeft,
} from 'lucide-react';
import { ContextMenuItem, ContextMenuSeparator } from '@/components/ui/context-menu';
import {
  isFileItem,
  isFolderItem,
  type DriveItem,
} from '../../attachments/services/driveService';

export interface DriveRowActionHandlers {
  onOpen: (item: DriveItem) => void;
  onPreview: (attachmentId: string) => void;
  onDownload: (item: DriveItem) => void;
  onRevealInFolder: (item: DriveItem) => void;
  onRename: (item: DriveItem) => void;
  onMove: (item: DriveItem) => void;
  onResubmit: (attachmentId: string) => void;
  onRestore: (attachmentId: string) => void;
  onDelete: (item: DriveItem) => void;
  /** Folder-only actions. */
  onRenameFolder: (item: DriveItem) => void;
  onNewSubfolder: (item: DriveItem) => void;
  onDeleteFolder: (item: DriveItem) => void;
}

/**
 * Per-row actions rendered as Radix ContextMenu items (right-click / long-press).
 * Replaces the old right-most "Actions" column. Items are gated by item kind and
 * trash state to mirror exactly what the previous "..." menu offered (review C).
 */
export default function DriveRowActions({
  item,
  isTrashView,
  recursive,
  resubmitting,
  handlers,
}: {
  item: DriveItem;
  isTrashView: boolean;
  recursive: boolean;
  resubmitting: boolean;
  handlers: DriveRowActionHandlers;
}) {
  // ---- Folder rows --------------------------------------------------------
  if (isFolderItem(item)) {
    return (
      <>
        <ContextMenuItem onClick={() => handlers.onOpen(item)}>
          <FolderOpen className="size-4" />
          Open
        </ContextMenuItem>
        {!isTrashView && (
          <>
            <ContextMenuItem onClick={() => handlers.onNewSubfolder(item)}>
              <Plus className="size-4" />
              New subfolder
            </ContextMenuItem>
            <ContextMenuItem onClick={() => handlers.onRenameFolder(item)}>
              <Pencil className="size-4" />
              Rename
            </ContextMenuItem>
            <ContextMenuItem onClick={() => handlers.onMove(item)}>
              <FolderInput className="size-4" />
              Move to…
            </ContextMenuItem>
            <ContextMenuSeparator />
            <ContextMenuItem variant="destructive" onClick={() => handlers.onDeleteFolder(item)}>
              <Trash2 className="size-4" />
              Delete
            </ContextMenuItem>
          </>
        )}
      </>
    );
  }

  // ---- File rows ----------------------------------------------------------
  const isDeleted = isFileItem(item) && item.is_deleted;
  return (
    <>
      <ContextMenuItem onClick={() => handlers.onOpen(item)}>
        <FolderOpen className="size-4" />
        Open
      </ContextMenuItem>
      <ContextMenuItem onClick={() => handlers.onPreview(item.id)}>
        <Search className="size-4" />
        Preview
      </ContextMenuItem>
      <ContextMenuItem onClick={() => handlers.onDownload(item)}>
        <Download className="size-4" />
        Download
      </ContextMenuItem>
      {recursive && (
        <ContextMenuItem onClick={() => handlers.onRevealInFolder(item)}>
          <CornerUpLeft className="size-4" />
          Reveal in folder
        </ContextMenuItem>
      )}
      {!isTrashView && !isDeleted && (
        <>
          <ContextMenuSeparator />
          <ContextMenuItem onClick={() => handlers.onRename(item)}>
            <Tag className="size-4" />
            Rename
          </ContextMenuItem>
          <ContextMenuItem onClick={() => handlers.onMove(item)}>
            <FolderInput className="size-4" />
            Move to…
          </ContextMenuItem>
          <ContextMenuItem
            disabled={resubmitting}
            onClick={() => handlers.onResubmit(item.id)}
          >
            <RefreshCw className={`size-4 ${resubmitting ? 'animate-spin' : ''}`} />
            Resubmit to n8n
          </ContextMenuItem>
        </>
      )}
      {isTrashView && (
        <>
          <ContextMenuSeparator />
          <ContextMenuItem onClick={() => handlers.onRestore(item.id)}>
            <RotateCcw className="size-4" />
            Restore
          </ContextMenuItem>
        </>
      )}
      <ContextMenuSeparator />
      <ContextMenuItem variant="destructive" onClick={() => handlers.onDelete(item)}>
        <Trash2 className="size-4" />
        {isTrashView ? 'Permanently delete' : 'Move to trash'}
      </ContextMenuItem>
    </>
  );
}
