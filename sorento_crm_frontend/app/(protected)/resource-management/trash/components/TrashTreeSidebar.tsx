'use client';

import { useState, useCallback, useMemo } from 'react';
import { ChevronRight, ChevronDown, ChevronUp, Folder, FolderOpen, MoreHorizontal, RotateCcw, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { ScrollAreaZag } from '@/components/ui/scroll-area-zag';
import { cn } from '@/lib/utils';
import type { AttachmentDirectoryTreeNode } from '../../attachments/services/directoryService';
import { useDirectoryTree, useRestoreDirectory, usePermanentDeleteDirectory } from '../../attachments/hooks/useAttachments';

export const TRASH_VIEW_ID = '__trash__';
export const TRASH_FOLDER_PREFIX = 'trash:';

function collectAllFolderIds(nodes: AttachmentDirectoryTreeNode[]): Set<string> {
  const ids = new Set<string>();
  for (const node of nodes) {
    ids.add(node.id);
    if (node.children?.length) {
      collectAllFolderIds(node.children).forEach((id) => ids.add(id));
    }
  }
  return ids;
}

function findNodeById(nodes: AttachmentDirectoryTreeNode[], targetId: string): AttachmentDirectoryTreeNode | null {
  for (const node of nodes) {
    if (node.id === targetId) return node;
    if (node.children?.length) {
      const found = findNodeById(node.children, targetId);
      if (found) return found;
    }
  }
  return null;
}

function collectSubtreeFolderIds(node: AttachmentDirectoryTreeNode): Set<string> {
  const ids = new Set<string>([node.id]);
  if (node.children?.length) {
    node.children.forEach((child) =>
      collectSubtreeFolderIds(child).forEach((id) => ids.add(id))
    );
  }
  return ids;
}

function DeletedFolderRow({
  node,
  depth,
  selectedId,
  expandedIds,
  onSelect,
  onRestore,
  onPermanentDelete,
  onToggleExpand,
}: {
  node: AttachmentDirectoryTreeNode;
  depth: number;
  selectedId: string | null;
  expandedIds: Set<string>;
  onSelect: (id: string) => void;
  onRestore: (id: string) => void;
  onPermanentDelete: (id: string, name: string) => void;
  onToggleExpand: (id: string) => void;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const trashFolderId = TRASH_FOLDER_PREFIX + node.id;
  const isSelected = selectedId === trashFolderId;
  const isExpanded = expandedIds.has(node.id);

  return (
    <div className="flex flex-col">
      <div
        className={cn(
          'group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer min-w-0',
          isSelected && 'bg-accent text-accent-foreground',
          'text-muted-foreground hover:text-foreground'
        )}
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => onSelect(trashFolderId)}
      >
        <button
          type="button"
          className="p-0.5 hover:bg-muted rounded shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            onToggleExpand(node.id);
          }}
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          <ChevronRight
            className={cn('size-4 text-muted-foreground transition-transform', isExpanded && 'rotate-90')}
          />
        </button>
        {hasChildren && isExpanded ? (
          <FolderOpen className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <Folder className="size-4 shrink-0 text-muted-foreground" />
        )}
        <span className="whitespace-nowrap truncate flex-1" title={node.name}>
          {node.name}
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
            <Button
              variant="ghost"
              size="sm"
              className="size-7 shrink-0 opacity-0 group-hover:opacity-100"
              aria-label="Folder actions"
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onRestore(node.id)}>
              <RotateCcw className="size-4 mr-2" />
              Restore folder and contents
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => onPermanentDelete(node.id, node.name)}
            >
              <Trash2 className="size-4 mr-2" />
              Permanently delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child) => (
            <DeletedFolderRow
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              expandedIds={expandedIds}
              onSelect={onSelect}
              onRestore={onRestore}
              onPermanentDelete={onPermanentDelete}
              onToggleExpand={onToggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface TrashTreeSidebarProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export default function TrashTreeSidebar({ selectedId, onSelect }: TrashTreeSidebarProps) {
  const { data: deletedTree = [], isLoading } = useDirectoryTree(true);
  const restoreMutation = useRestoreDirectory();
  const permanentDeleteMutation = usePermanentDeleteDirectory();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [permanentDeleteDialogOpen, setPermanentDeleteDialogOpen] = useState(false);
  const [permanentDeleteTarget, setPermanentDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const allFolderIds = useMemo(() => collectAllFolderIds(deletedTree), [deletedTree]);

  const selectedFolderId = selectedId?.startsWith(TRASH_FOLDER_PREFIX)
    ? selectedId.slice(TRASH_FOLDER_PREFIX.length)
    : null;

  const subtreeFolderIds = useMemo(() => {
    if (!selectedFolderId) return null;
    const node = findNodeById(deletedTree, selectedFolderId);
    return node ? collectSubtreeFolderIds(node) : null;
  }, [deletedTree, selectedFolderId]);

  const handleExpandAll = useCallback(() => {
    const idsToExpand = subtreeFolderIds ?? allFolderIds;
    setExpandedIds((prev) => {
      const next = new Set(prev);
      idsToExpand.forEach((id) => next.add(id));
      return next;
    });
  }, [subtreeFolderIds, allFolderIds]);

  const handleCollapseAll = useCallback(() => {
    const idsToCollapse = subtreeFolderIds ?? allFolderIds;
    setExpandedIds((prev) => {
      const next = new Set(prev);
      idsToCollapse.forEach((id) => next.delete(id));
      return next;
    });
  }, [subtreeFolderIds, allFolderIds]);

  const handleToggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handlePermanentDelete = () => {
    if (!permanentDeleteTarget) return;
    permanentDeleteMutation.mutate(permanentDeleteTarget.id, {
      onSuccess: () => {
        setPermanentDeleteDialogOpen(false);
        setPermanentDeleteTarget(null);
        onSelect(TRASH_VIEW_ID);
      },
    });
  };

  return (
    <div className="flex h-full w-full min-w-0 flex-col border-r bg-muted/30">
      <div className="flex items-center justify-between gap-1 p-2 border-b">
        <span className="text-sm font-medium truncate">Deleted folders</span>
        <div className="flex items-center gap-0.5 shrink-0">
          <Button
            variant="ghost"
            size="sm"
            className="size-8 p-0"
            title={selectedFolderId ? 'Expand all in selected folder' : 'Expand all'}
            onClick={handleExpandAll}
          >
            <ChevronDown className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="size-8 p-0"
            title={selectedFolderId ? 'Collapse all in selected folder' : 'Collapse all'}
            onClick={handleCollapseAll}
          >
            <ChevronUp className="size-4" />
          </Button>
        </div>
      </div>
      <ScrollAreaZag className="flex-1">
        <div className="min-w-max p-1 py-2">
          <button
            type="button"
            className={cn(
              'w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left',
              selectedId === TRASH_VIEW_ID && 'bg-accent text-accent-foreground'
            )}
            onClick={() => onSelect(TRASH_VIEW_ID)}
          >
            <Folder className="size-4 text-muted-foreground shrink-0" />
            All deleted items
          </button>
          {isLoading ? (
            <div className="px-2 py-2 text-sm text-muted-foreground">Loading…</div>
          ) : deletedTree.length === 0 ? (
            <div className="px-2 py-2 text-sm text-muted-foreground">No deleted folders</div>
          ) : (
            deletedTree.map((node) => (
              <DeletedFolderRow
                key={node.id}
                node={node}
                depth={0}
                selectedId={selectedId}
                expandedIds={expandedIds}
                onSelect={(id) => onSelect(id)}
                onRestore={(id) =>
                  restoreMutation.mutate(id, { onSuccess: () => onSelect(TRASH_VIEW_ID) })
                }
                onPermanentDelete={(id, name) => {
                  setPermanentDeleteTarget({ id, name });
                  setPermanentDeleteDialogOpen(true);
                }}
                onToggleExpand={handleToggleExpand}
              />
            ))
          )}
        </div>
      </ScrollAreaZag>

      <Dialog open={permanentDeleteDialogOpen} onOpenChange={(open) => { if (!open) { setPermanentDeleteDialogOpen(false); setPermanentDeleteTarget(null); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Permanently delete folder</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Permanently delete &quot;{permanentDeleteTarget?.name}&quot;? This folder and all subfolders will be removed forever.
            All attachments in this folder and its subfolders will be permanently deleted. This cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPermanentDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handlePermanentDelete}
              disabled={permanentDeleteMutation.isPending}
            >
              Permanently delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
